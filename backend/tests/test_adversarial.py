import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.api.tickets import TICKET_ACTOR_OPTIONS
from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import Document, Notification, Organization, Ticket, ToolRun, User, utcnow
from app.schemas import TicketCreate
from app.seed import seed_demo
from app.services.notifications import enqueue_ticket_notification, send_ticket_notification
from app.services.tickets import create_ticket as create_ticket_service
from app.services.text import get_embedding
from app.worker import run_notification_once, run_once


def create_ticket(client, headers, key=None):
    response = client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": "生产工作流持续失败",
            "description": "需要人工结合运行记录排查",
            "product_module": "工作流",
            "category": "INCIDENT",
            "priority": "NORMAL",
            "idempotency_key": key or str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_conversation(client, headers):
    response = client.post(
        "/api/v1/conversations", headers=headers, json={"title": "新对话"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_invalid_assignee_rolls_back_status_change(client, customer_headers, support_headers):
    ticket = create_ticket(client, customer_headers)
    response = client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        headers=support_headers,
        json={"status": "IN_PROGRESS", "assignee_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422
    current = client.get(f"/api/v1/tickets/{ticket['id']}", headers=support_headers).json()
    assert current["status"] == "OPEN"
    assert not any(event["event_type"] == "STATUS_CHANGED" for event in current["events"])


def test_ticket_list_query_count_is_constant(client, support_headers):
    with SessionLocal() as db:
        for index in range(20):
            organization = Organization(name=f"查询测试企业 {index}", slug=f"query-org-{index}")
            customer = User(
                organization=organization,
                email=f"query-customer-{index}@example.test",
                display_name=f"客户 {index}",
                password_hash="not-used",
                role="CUSTOMER",
            )
            assignee = User(
                email=f"query-support-{index}@example.test",
                display_name=f"支持 {index}",
                password_hash="not-used",
                role="SUPPORT",
            )
            db.add_all([organization, customer, assignee])
            db.flush()
            db.add(
                Ticket(
                    number=f"KT-209901-{index:04d}",
                    organization_id=organization.id,
                    customer_id=customer.id,
                    assignee_id=assignee.id,
                    title=f"查询计数工单 {index}",
                    description="验证列表查询不会逐条加载关联用户",
                    product_module="工作流",
                    category="INCIDENT",
                    priority="NORMAL",
                    idempotency_key=f"query-count-{index}",
                )
            )
        db.commit()

    selects = []

    def count_selects(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    sa.event.listen(engine, "before_cursor_execute", count_selects)
    try:
        response = client.get("/api/v1/tickets", headers=support_headers)
    finally:
        sa.event.remove(engine, "before_cursor_execute", count_selects)

    assert response.status_code == 200, response.text
    assert len(response.json()) >= 20
    assert len(selects) <= 5


def test_ticket_lock_query_does_not_join_nullable_relationships():
    statement = (
        sa.select(Ticket)
        .options(*TICKET_ACTOR_OPTIONS)
        .where(Ticket.id == sa.bindparam("ticket_id"))
        .with_for_update()
    )

    sql = str(statement.compile(dialect=postgresql.dialect())).upper()
    assert " FOR UPDATE" in sql
    assert " JOIN " not in sql


def test_disabled_organization_invalidates_existing_token(client, customer_headers):
    with SessionLocal() as db:
        organization = db.scalar(
            sa.select(Organization).where(Organization.slug == "nova-data")
        )
        organization.active = False
        db.commit()
    response = client.get("/api/v1/auth/me", headers=customer_headers)
    assert response.status_code == 401


def test_action_proposals_are_bound_to_their_messages(client, customer_headers):
    conversation_id = create_conversation(client, customer_headers)
    proposal_ids = []
    for content in ("请创建工单排查第一次故障", "请提交一个计费异常工单"):
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=customer_headers,
            json={"content": content},
        )
        assert response.status_code == 200
        proposal_ids.append(response.json()["action_proposal"]["id"])
    detail = client.get(
        f"/api/v1/conversations/{conversation_id}", headers=customer_headers
    ).json()
    bound_ids = [
        message["action_proposal"]["id"]
        for message in detail["messages"]
        if message["action_proposal"]
    ]
    assert bound_ids == proposal_ids


def test_invalid_model_json_returns_structured_error(
    client, customer_headers, monkeypatch
):
    class BadResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "not-json"}}]}

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_base_url", "https://provider.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr("app.services.agent.httpx.post", lambda *args, **kwargs: BadResponse())
    conversation_id = create_conversation(client, customer_headers)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=customer_headers,
        json={"content": "API 返回 40103 是什么意思？"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ERROR"
    assert response.json()["trace_id"]
    with SessionLocal() as db:
        failed = db.scalar(
            sa.select(ToolRun)
            .where(ToolRun.tool_name == "generate_grounded_answer")
            .order_by(ToolRun.created_at.desc())
        )
        assert failed.status == "FAILED"
        assert failed.error_message == "invalid_model_json"


def test_embedding_dimension_mismatch_is_rejected(monkeypatch):
    class BadEmbedding:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2]}]}

    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_base_url", "https://provider.invalid/v1")
    monkeypatch.setattr(settings, "embedding_model", "test-embedding")
    monkeypatch.setattr("app.services.text.httpx.post", lambda *args, **kwargs: BadEmbedding())
    try:
        get_embedding("dimension check")
    except ValueError as exc:
        assert "维度不匹配" in str(exc)
    else:
        raise AssertionError("dimension mismatch was not rejected")


def test_demo_seed_is_idempotent_when_source_hash_changes(client):
    with SessionLocal() as db:
        document = db.scalar(sa.select(Document).order_by(Document.logical_name))
        logical_name = document.logical_name
        version = document.version
        document.sha256 = "0" * 64
        db.commit()

    with SessionLocal() as db:
        seed_demo(db)
        duplicates = db.scalar(
            sa.select(sa.func.count())
            .select_from(Document)
            .where(Document.logical_name == logical_name, Document.version == version)
        )
        assert duplicates == 1


def test_worker_recovers_expired_processing_lease(client, monkeypatch):
    with SessionLocal() as db:
        document = db.scalar(sa.select(Document).limit(1))
        document.status = "PROCESSING"
        document.processing_started_at = utcnow() - timedelta(minutes=20)
        document.lease_expires_at = utcnow() - timedelta(minutes=10)
        document.retry_count = 0
        document_id = document.id
        db.commit()

    claimed = []

    def fake_process(db, target_id):
        claimed.append(target_id)
        document = db.get(Document, target_id)
        document.status = "READY"
        document.processing_started_at = None
        document.lease_expires_at = None
        db.commit()

    monkeypatch.setattr("app.worker.process_document", fake_process)
    assert run_once() is True
    assert claimed == [document_id]


def test_notification_error_never_stores_webhook_url(
    client, customer_headers, monkeypatch
):
    ticket_data = create_ticket(client, customer_headers)
    settings = get_settings()
    secret_url = "https://open.feishu.cn/open-apis/bot/v2/hook/sensitive-token"
    monkeypatch.setattr(settings, "feishu_webhook_url", secret_url)

    def fail(*args, **kwargs):
        raise httpx.RequestError(f"failed posting to {secret_url}")

    monkeypatch.setattr("app.services.notifications.httpx.post", fail)
    with SessionLocal() as db:
        ticket = db.get(Ticket, uuid.UUID(ticket_data["id"]))
        notification = send_ticket_notification(db, ticket)
        assert notification.status == "FAILED"
        assert secret_url not in (notification.error_message or "")
        stored = db.get(Notification, notification.id)
        assert stored.error_message == "transport_or_response_error"


def test_notification_uses_human_readable_labels(client, customer_headers, monkeypatch):
    ticket_data = create_ticket(client, customer_headers)
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "feishu_webhook_url",
        "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
    )
    captured = {}

    class SuccessfulResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 0}

    def post(*args, **kwargs):
        captured.update(kwargs["json"])
        return SuccessfulResponse()

    monkeypatch.setattr("app.services.notifications.httpx.post", post)
    with SessionLocal() as db:
        ticket = db.get(Ticket, uuid.UUID(ticket_data["id"]))
        notification = send_ticket_notification(db, ticket)
        assert notification.status == "SENT"

    text = captured["content"]["text"]
    assert "工作流 · 故障 · 普通" in text
    assert "INCIDENT" not in text
    assert "NORMAL" not in text


def test_notification_dispatch_crash_keeps_ticket_and_pending_outbox(
    client, customer_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.tickets.process_notification",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated crash")),
    )
    ticket_data = create_ticket(client, customer_headers, "outbox-crash-key")
    with SessionLocal() as db:
        ticket = db.get(Ticket, uuid.UUID(ticket_data["id"]))
        notification = db.scalar(
            sa.select(Notification).where(Notification.ticket_id == ticket.id)
        )
        assert ticket is not None
        assert notification.status == "PENDING"


def test_worker_recovers_pending_notification(
    client, customer_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.tickets.process_notification",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated crash")),
    )
    ticket_data = create_ticket(client, customer_headers, "outbox-worker-key")
    assert run_notification_once() is True
    with SessionLocal() as db:
        notification = db.scalar(
            sa.select(Notification).where(
                Notification.ticket_id == uuid.UUID(ticket_data["id"])
            )
        )
        assert notification.status == "DISABLED"


def test_failed_notification_can_only_be_retried_once(
    client, customer_headers, support_headers
):
    ticket_data = create_ticket(client, customer_headers, "retry-source-key")
    with SessionLocal() as db:
        source = db.scalar(
            sa.select(Notification).where(
                Notification.ticket_id == uuid.UUID(ticket_data["id"])
            )
        )
        source.status = "FAILED"
        source.error_message = "timeout"
        source_id = source.id
        db.commit()

    path = f"/api/v1/tickets/{ticket_data['id']}/notify?source_notification_id={source_id}"
    first = client.post(path, headers=support_headers)
    second = client.post(path, headers=support_headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    with SessionLocal() as db:
        attempts = db.scalars(
            sa.select(Notification).where(
                Notification.ticket_id == uuid.UUID(ticket_data["id"])
            )
        ).all()
        assert len(attempts) == 2


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL concurrency test")
def test_postgres_concurrent_idempotency_has_one_ticket_and_notification(client):
    key = f"concurrent-{uuid.uuid4()}"

    def submit():
        with SessionLocal() as db:
            customer = db.scalar(sa.select(User).where(User.email == "alice@nova.test"))
            ticket, created = create_ticket_service(
                db,
                customer,
                TicketCreate(
                    title="并发幂等测试",
                    description="相同请求只能创建一次",
                    product_module="工作流",
                    category="INCIDENT",
                    priority="NORMAL",
                    idempotency_key=key,
                ),
            )
            if created:
                enqueue_ticket_notification(db, ticket)
            db.commit()
            return ticket.id, ticket.number, created

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: submit(), range(8)))

    assert len({result[0] for result in results}) == 1
    assert sum(result[2] for result in results) == 1
    with SessionLocal() as db:
        ticket = db.scalar(sa.select(Ticket).where(Ticket.idempotency_key == key))
        notifications = db.scalars(
            sa.select(Notification).where(Notification.ticket_id == ticket.id)
        ).all()
        assert len(notifications) == 1
