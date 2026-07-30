def test_health_and_readiness(client):
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["database"] in {"sqlite", "postgresql"}


def test_login_rejects_wrong_password(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@nova.test", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_customer_cannot_access_support_overview(client, customer_headers):
    response = client.get("/api/v1/support/overview", headers=customer_headers)
    assert response.status_code == 403
