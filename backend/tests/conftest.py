import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_support_pilot.db")
os.environ.setdefault("AUTO_CREATE_TABLES", "true")
os.environ.setdefault("SEED_DEMO", "true")
os.environ.setdefault("DEMO_KNOWLEDGE_DIR", "../docs/demo-knowledge")
os.environ.setdefault("UPLOAD_DIR", "./test_uploads")

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def customer_headers(client):
    return login(client, "alice@nova.test", "customer123")


@pytest.fixture
def other_customer_headers(client):
    return login(client, "bob@apex.test", "customer123")


@pytest.fixture
def support_headers(client):
    return login(client, "support@flowpilot.test", "support123")
