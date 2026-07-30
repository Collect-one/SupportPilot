import uuid

import sqlalchemy as sa

from app.database import SessionLocal
from app.models import ToolRun


def create_conversation(client, headers):
    response = client.post(
        "/api/v1/conversations", json={"title": "新对话"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_customer_answer_hides_citations_but_support_trace_keeps_them(
    client, customer_headers, support_headers
):
    conversation_id = create_conversation(client, customer_headers)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "API 返回 40103 是什么意思？"},
        headers=customer_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ANSWERED"
    assert "40103" in data["answer"]
    assert "citations" not in data
    assert "tool_runs" not in data

    trace_id = data["trace_id"]
    forbidden = client.get(
        f"/api/v1/support/rag-traces/{trace_id}", headers=customer_headers
    )
    assert forbidden.status_code == 403
    audit = client.get(
        f"/api/v1/support/rag-traces/{trace_id}", headers=support_headers
    )
    assert audit.status_code == 200, audit.text
    detail = audit.json()
    assert detail["decision_status"] == "SUFFICIENT"
    assert detail["candidates"]
    assert detail["citations"][0]["document_name"] == "01-账号与工作空间"
    assert detail["candidates"][0]["semantic_score"] >= 0
    assert detail["tool_runs"][0]["tool_name"] == "search_knowledge"

    conversation = client.get(
        f"/api/v1/conversations/{conversation_id}", headers=customer_headers
    ).json()
    assert all("citations" not in message for message in conversation["messages"])


def test_new_question_does_not_reuse_previous_answer_context(
    client, customer_headers, support_headers
):
    conversation_id = create_conversation(client, customer_headers)
    first = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "API 返回 40103 是什么意思？"},
        headers=customer_headers,
    )
    assert first.json()["status"] == "ANSWERED"

    second = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "今天的天气怎么样？"},
        headers=customer_headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "UNRESOLVED"
    assert "citations" not in second.json()
    assert second.json()["action_proposal"] is None

    detail = client.get(
        f"/api/v1/support/rag-traces/{second.json()['trace_id']}",
        headers=support_headers,
    ).json()
    assert detail["decision_status"] == "NOT_SEARCHED"
    assert detail["candidates"] == []
    assert detail["citations"] == []
    assert detail["tool_runs"] == []


def test_legacy_trace_keeps_final_citations_without_candidate_snapshot(
    client, customer_headers, support_headers
):
    conversation_id = create_conversation(client, customer_headers)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "API 返回 40103 是什么意思？"},
        headers=customer_headers,
    )
    trace_id = response.json()["trace_id"]
    with SessionLocal() as db:
        runs = list(db.scalars(sa.select(ToolRun).where(ToolRun.trace_id == uuid.UUID(trace_id))))
        for run in runs:
            run.trace_id = None
        db.commit()

    detail = client.get(
        f"/api/v1/support/rag-traces/{trace_id}", headers=support_headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["decision_status"] == "LEGACY"
    assert detail.json()["legacy_partial"] is True
    assert detail.json()["candidates"] == []
    assert detail.json()["citations"]

    listing = client.get(
        "/api/v1/support/rag-traces?decision=LEGACY", headers=support_headers
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1


def test_ticket_requires_confirmation_and_is_idempotent(client, customer_headers):
    conversation_id = create_conversation(client, customer_headers)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "请转人工并创建工单，我的生产工作流持续失败"},
        headers=customer_headers,
    )
    data = response.json()
    assert data["status"] == "ACTION_PROPOSED"
    proposal_id = data["action_proposal"]["id"]
    assert client.get("/api/v1/tickets", headers=customer_headers).json() == []

    first = client.post(
        f"/api/v1/action-proposals/{proposal_id}/confirm",
        json={"payload": {"workspace_id": "ws_demo123456"}},
        headers=customer_headers,
    )
    second = client.post(
        f"/api/v1/action-proposals/{proposal_id}/confirm",
        json={},
        headers=customer_headers,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["workspace_id"] == "ws_demo123456"
    assert len(client.get("/api/v1/tickets", headers=customer_headers).json()) == 1


def test_sensitive_token_is_redacted(client, customer_headers):
    conversation_id = create_conversation(client, customer_headers)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "请创建工单，API key=sk-super-secret-value-123456789 无法使用"},
        headers=customer_headers,
    )
    payload = response.json()["action_proposal"]["payload"]
    assert "super-secret" not in payload["description"]
    assert "已脱敏" in payload["description"]
