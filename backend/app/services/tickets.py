from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Ticket, TicketEvent, TicketSequence, User, utcnow
from app.schemas import TicketCreate, TicketUpdate
from app.services.text import redact_sensitive


VALID_CATEGORIES = {"ACCOUNT", "CONFIG", "API", "BILLING", "INCIDENT", "FEATURE", "OTHER"}
VALID_PRIORITIES = {"LOW", "NORMAL", "HIGH"}
SUPPORT_STATUSES = {"OPEN", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"}
TRANSITIONS = {
    "OPEN": {"IN_PROGRESS", "RESOLVED"},
    "IN_PROGRESS": {"WAITING_CUSTOMER", "RESOLVED"},
    "WAITING_CUSTOMER": {"IN_PROGRESS", "RESOLVED"},
    "RESOLVED": {"OPEN", "CLOSED"},
    "CLOSED": {"OPEN"},
}


def _next_sequence(db: Session, month: str) -> int:
    values = {"month": month, "last_value": 1}
    if db.bind and db.bind.dialect.name == "postgresql":
        statement = postgresql_insert(TicketSequence).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[TicketSequence.month],
            set_={"last_value": TicketSequence.last_value + 1},
        ).returning(TicketSequence.last_value)
        return int(db.scalar(statement))
    if db.bind and db.bind.dialect.name == "sqlite":
        statement = sqlite_insert(TicketSequence).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[TicketSequence.month],
            set_={"last_value": TicketSequence.last_value + 1},
        ).returning(TicketSequence.last_value)
        return int(db.scalar(statement))
    sequence = db.get(TicketSequence, month, with_for_update=True)
    if not sequence:
        sequence = TicketSequence(month=month, last_value=1)
        db.add(sequence)
        db.flush()
    else:
        sequence.last_value += 1
    return sequence.last_value


def generate_ticket_number(db: Session) -> str:
    month = datetime.now(timezone.utc).strftime("%Y%m")
    return f"KT-{month}-{_next_sequence(db, month):04d}"


def _event(
    db: Session,
    ticket: Ticket,
    actor: User,
    event_type: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            author_id=actor.id,
            event_type=event_type,
            content=content,
            metadata_json=metadata or {},
        )
    )


def create_ticket(db: Session, customer: User, data: TicketCreate) -> tuple[Ticket, bool]:
    if not customer.organization_id:
        raise HTTPException(status_code=400, detail="客户账号缺少企业信息")
    if data.priority == "HIGH":
        raise HTTPException(status_code=422, detail="客户不能直接指定高优先级，人工支持将根据影响确认")
    if data.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail="未知工单分类")
    if data.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=422, detail="未知工单优先级")
    if db.bind and db.bind.dialect.name == "postgresql":
        lock_key = f"{customer.organization_id}:{data.idempotency_key}"
        db.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )

    existing = db.scalar(
        sa.select(Ticket).where(
            Ticket.organization_id == customer.organization_id,
            Ticket.idempotency_key == data.idempotency_key,
        )
    )
    if existing:
        return existing, False

    ticket = Ticket(
        number=generate_ticket_number(db),
        organization_id=customer.organization_id,
        customer_id=customer.id,
        conversation_id=data.conversation_id,
        title=redact_sensitive(data.title),
        description=redact_sensitive(data.description),
        product_module=redact_sensitive(data.product_module),
        category=data.category,
        priority=data.priority,
        workspace_id=redact_sensitive(data.workspace_id or "") or None,
        environment=redact_sensitive(data.environment or "") or None,
        error_code=redact_sensitive(data.error_code or "") or None,
        reproduction_steps=redact_sensitive(data.reproduction_steps or "") or None,
        business_impact=redact_sensitive(data.business_impact or "") or None,
        idempotency_key=data.idempotency_key,
    )
    try:
        with db.begin_nested():
            db.add(ticket)
            db.flush()
            _event(db, ticket, customer, "CREATED", "客户提交了工单")
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            sa.select(Ticket).where(
                Ticket.organization_id == customer.organization_id,
                Ticket.idempotency_key == data.idempotency_key,
            )
        )
        if existing:
            return existing, False
        raise
    return ticket, True


def add_comment(db: Session, ticket: Ticket, author: User, content: str) -> None:
    clean = redact_sensitive(content)
    _event(db, ticket, author, "COMMENT", clean)
    if author.role == "CUSTOMER" and ticket.status == "WAITING_CUSTOMER":
        old_status = ticket.status
        ticket.status = "IN_PROGRESS"
        _event(
            db,
            ticket,
            author,
            "STATUS_CHANGED",
            "客户已补充信息，工单恢复处理中",
            {"from": old_status, "to": ticket.status},
        )


def change_status(db: Session, ticket: Ticket, actor: User, new_status: str) -> bool:
    old_status = ticket.status
    if new_status not in SUPPORT_STATUSES:
        raise HTTPException(status_code=422, detail="未知工单状态")
    if new_status == old_status:
        return False
    if new_status not in TRANSITIONS.get(old_status, set()):
        raise HTTPException(status_code=409, detail=f"不能从 {old_status} 变更为 {new_status}")
    if actor.role == "CUSTOMER" and not (
        (old_status == "RESOLVED" and new_status in {"CLOSED", "OPEN"})
        or (old_status == "CLOSED" and new_status == "OPEN")
    ):
        raise HTTPException(status_code=403, detail="客户不能执行该状态变更")

    ticket.status = new_status
    if new_status == "RESOLVED":
        ticket.resolved_at = utcnow()
    elif new_status == "CLOSED":
        ticket.closed_at = utcnow()
    elif new_status == "OPEN":
        ticket.resolved_at = None
        ticket.closed_at = None
    _event(
        db,
        ticket,
        actor,
        "STATUS_CHANGED",
        f"状态由 {old_status} 更新为 {new_status}",
        {"from": old_status, "to": new_status},
    )
    if new_status == "OPEN" and old_status in {"RESOLVED", "CLOSED"}:
        _event(db, ticket, actor, "REOPENED", "工单已重新打开")
        return True
    return False


def update_ticket(
    db: Session, ticket: Ticket, actor: User, update: TicketUpdate
) -> tuple[bool, bool]:
    fields = update.model_fields_set
    if actor.role != "SUPPORT" and fields & {"category", "priority", "assignee_id"}:
        raise HTTPException(status_code=403, detail="客户不能修改工单分派信息")
    if update.category is not None and update.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail="未知工单分类")
    if update.priority is not None and update.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=422, detail="未知工单优先级")

    assignee = None
    if "assignee_id" in fields and update.assignee_id is not None:
        assignee = db.get(User, update.assignee_id)
        if not assignee or assignee.role != "SUPPORT" or not assignee.active:
            raise HTTPException(status_code=422, detail="处理人账号无效")

    reopened = False
    became_high = False
    if update.status is not None:
        reopened = change_status(db, ticket, actor, update.status)
    if actor.role == "SUPPORT" and update.category is not None and update.category != ticket.category:
        previous = ticket.category
        ticket.category = update.category
        _event(
            db,
            ticket,
            actor,
            "CATEGORY_CHANGED",
            f"分类由 {previous} 更新为 {ticket.category}",
            {"from": previous, "to": ticket.category},
        )
    if actor.role == "SUPPORT" and update.priority is not None and update.priority != ticket.priority:
        previous = ticket.priority
        ticket.priority = update.priority
        became_high = update.priority == "HIGH"
        _event(
            db,
            ticket,
            actor,
            "PRIORITY_CHANGED",
            f"优先级由 {previous} 更新为 {ticket.priority}",
            {"from": previous, "to": ticket.priority},
        )
    if actor.role == "SUPPORT" and "assignee_id" in fields and update.assignee_id != ticket.assignee_id:
        previous = ticket.assignee_id
        ticket.assignee_id = assignee.id if assignee else None
        _event(
            db,
            ticket,
            actor,
            "ASSIGNED",
            f"处理人更新为 {assignee.display_name if assignee else '未分派'}",
            {"from": str(previous) if previous else None, "to": str(ticket.assignee_id) if ticket.assignee_id else None},
        )
    return reopened, became_high


def claim_ticket(db: Session, ticket: Ticket, actor: User) -> None:
    previous = ticket.assignee_id
    ticket.assignee_id = actor.id
    _event(
        db,
        ticket,
        actor,
        "ASSIGNED",
        f"{actor.display_name} 已认领工单",
        {"from": str(previous) if previous else None, "to": str(actor.id)},
    )
    if ticket.status == "OPEN":
        change_status(db, ticket, actor, "IN_PROGRESS")
