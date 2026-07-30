import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload

from app.api.serializers import ticket_dict
from app.database import get_db
from app.dependencies import get_current_user, require_customer, require_support
from app.models import ActionProposal, Conversation, Notification, Ticket, TicketEvent, User, utcnow
from app.schemas import (
    ProposalConfirm,
    TicketCommentCreate,
    TicketCreate,
    TicketOut,
    TicketUpdate,
)
from app.services.notifications import enqueue_ticket_notification, process_notification
from app.services.tickets import add_comment, claim_ticket as claim_ticket_service, create_ticket, update_ticket as update_ticket_service


router = APIRouter(tags=["tickets"])

TICKET_ACTOR_OPTIONS = (
    selectinload(Ticket.customer).selectinload(User.organization),
    selectinload(Ticket.assignee),
)


def _dispatch_notification(db: Session, notification_id: uuid.UUID | None) -> None:
    if not notification_id:
        return
    try:
        process_notification(db, notification_id)
    except Exception:
        db.rollback()


def _ticket_or_404(
    db: Session, ticket_id: uuid.UUID, user: User, lock: bool = False
) -> Ticket:
    statement = (
        sa.select(Ticket)
        .where(Ticket.id == ticket_id)
        .execution_options(populate_existing=True)
        .options(
            *TICKET_ACTOR_OPTIONS,
            selectinload(Ticket.events).selectinload(TicketEvent.author),
        )
    )
    if lock:
        statement = statement.with_for_update()
    ticket = db.scalar(statement)
    if not ticket or (user.role == "CUSTOMER" and ticket.organization_id != user.organization_id):
        raise HTTPException(status_code=404, detail="工单不存在")
    return ticket


@router.post("/action-proposals/{proposal_id}/confirm", response_model=TicketOut)
def confirm_action(
    proposal_id: uuid.UUID,
    payload: ProposalConfirm,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    proposal = db.scalar(
        sa.select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update()
    )
    if not proposal or proposal.user_id != user.id or proposal.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="待确认操作不存在")
    if proposal.confirmed_ticket_id:
        ticket = _ticket_or_404(db, proposal.confirmed_ticket_id, user)
        return ticket_dict(db, ticket, True)
    if proposal.expires_at < utcnow():
        raise HTTPException(status_code=410, detail="操作确认已过期，请重新生成")
    merged = {**proposal.payload, **(payload.payload or {})}
    merged["conversation_id"] = proposal.conversation_id
    merged["idempotency_key"] = proposal.payload["idempotency_key"]
    try:
        ticket_data = TicketCreate.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    ticket, created = create_ticket(db, user, ticket_data)
    proposal.confirmed_at = utcnow()
    proposal.confirmed_ticket_id = ticket.id
    notification = enqueue_ticket_notification(db, ticket) if created else None
    db.commit()
    if created:
        _dispatch_notification(db, notification.id)
    return ticket_dict(db, _ticket_or_404(db, ticket.id, user), True, True)


@router.post("/tickets", response_model=TicketOut, status_code=201)
def create_ticket_route(
    payload: TicketCreate,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(status_code=404, detail="来源对话不存在")
    ticket, created = create_ticket(db, user, payload)
    notification = enqueue_ticket_notification(db, ticket) if created else None
    db.commit()
    if created:
        _dispatch_notification(db, notification.id)
    return ticket_dict(db, _ticket_or_404(db, ticket.id, user), True, True)


@router.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    organization_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = sa.select(Ticket).options(*TICKET_ACTOR_OPTIONS).order_by(Ticket.updated_at.desc())
    if user.role == "CUSTOMER":
        statement = statement.where(Ticket.organization_id == user.organization_id)
    elif organization_id:
        statement = statement.where(Ticket.organization_id == organization_id)
    if status:
        statement = statement.where(Ticket.status == status)
    if category:
        statement = statement.where(Ticket.category == category)
    if priority:
        statement = statement.where(Ticket.priority == priority)
    return [ticket_dict(db, ticket) for ticket in db.scalars(statement).unique()]


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ticket_dict(db, _ticket_or_404(db, ticket_id, user), True, True)


@router.post("/tickets/{ticket_id}/comments", response_model=TicketOut)
def comment_ticket(
    ticket_id: uuid.UUID,
    payload: TicketCommentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = _ticket_or_404(db, ticket_id, user, lock=True)
    add_comment(db, ticket, user, payload.content)
    db.commit()
    return ticket_dict(db, _ticket_or_404(db, ticket_id, user), True, True)


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = _ticket_or_404(db, ticket_id, user, lock=True)
    reopened, became_high = update_ticket_service(db, ticket, user, payload)
    notification = enqueue_ticket_notification(db, ticket) if reopened or became_high else None
    db.commit()
    if reopened or became_high:
        _dispatch_notification(db, notification.id)
    return ticket_dict(db, _ticket_or_404(db, ticket_id, user), True, True)


@router.post("/tickets/{ticket_id}/claim", response_model=TicketOut)
def claim_ticket(
    ticket_id: uuid.UUID,
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    ticket = _ticket_or_404(db, ticket_id, user, lock=True)
    claim_ticket_service(db, ticket, user)
    db.commit()
    return ticket_dict(db, _ticket_or_404(db, ticket_id, user), True, True)


@router.post("/tickets/{ticket_id}/notify")
def notify_ticket(
    ticket_id: uuid.UUID,
    source_notification_id: uuid.UUID,
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    ticket = _ticket_or_404(db, ticket_id, user, lock=True)
    source = db.scalar(
        sa.select(Notification)
        .where(
            Notification.id == source_notification_id,
            Notification.ticket_id == ticket.id,
        )
        .with_for_update()
    )
    latest = db.scalar(
        sa.select(Notification)
        .where(Notification.ticket_id == ticket.id)
        .order_by(Notification.attempt_count.desc(), Notification.created_at.desc())
        .limit(1)
    )
    if not source or source.status != "FAILED" or not latest or latest.id != source.id:
        raise HTTPException(status_code=409, detail="该通知已被重发或不是最新失败记录")
    notification = enqueue_ticket_notification(db, ticket, source_notification_id)
    db.commit()
    _dispatch_notification(db, notification.id)
    db.refresh(notification)
    return {"id": notification.id, "status": notification.status, "error": notification.error_message}
