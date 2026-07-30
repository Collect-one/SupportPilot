def create_conversation(client, headers):
    response = client.post(
        "/api/v1/conversations", json={"title": "新对话"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_answer_contains_grounded_citation(client, customer_headers):
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
    assert data["citations"]
    assert data["citations"][0]["document_name"] == "01-账号与工作空间"
    assert isinstance(data["citations"][0]["score"], float)


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
