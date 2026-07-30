import uuid


def create_ticket(client, headers, key=None):
    response = client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": "生产工作流持续失败",
            "description": "运行记录显示未知错误，需要人工排查",
            "product_module": "工作流",
            "category": "INCIDENT",
            "priority": "NORMAL",
            "idempotency_key": key or str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_cross_organization_ticket_is_hidden(client, customer_headers, other_customer_headers):
    ticket = create_ticket(client, customer_headers)
    response = client.get(f"/api/v1/tickets/{ticket['id']}", headers=other_customer_headers)
    assert response.status_code == 404
    assert client.get("/api/v1/tickets", headers=other_customer_headers).json() == []


def test_support_claims_resolves_and_customer_closes(
    client, customer_headers, support_headers
):
    ticket = create_ticket(client, customer_headers)
    claimed = client.post(
        f"/api/v1/tickets/{ticket['id']}/claim", headers=support_headers
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["status"] == "IN_PROGRESS"
    assert claimed.json()["assignee_name"] == "陈工"

    comment = client.post(
        f"/api/v1/tickets/{ticket['id']}/comments",
        headers=support_headers,
        json={"content": "已定位配置问题，请客户重新发布工作流。"},
    )
    assert comment.status_code == 200
    resolved = client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        headers=support_headers,
        json={"status": "RESOLVED"},
    )
    assert resolved.json()["status"] == "RESOLVED"

    closed = client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        headers=customer_headers,
        json={"status": "CLOSED"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"


def test_customer_cannot_assign_ticket(client, customer_headers):
    ticket = create_ticket(client, customer_headers)
    response = client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        headers=customer_headers,
        json={"priority": "LOW"},
    )
    assert response.status_code == 403


def test_customer_cannot_create_high_priority_ticket(client, customer_headers):
    response = client.post(
        "/api/v1/tickets",
        headers=customer_headers,
        json={
            "title": "请求高优先级",
            "description": "客户提交时不能直接指定高优先级",
            "category": "INCIDENT",
            "priority": "HIGH",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 422
