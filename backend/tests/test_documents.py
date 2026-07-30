from app.database import SessionLocal
from app.models import Document
from app.services.documents import process_document


def test_document_requires_processing_before_publish(client, support_headers):
    response = client.post(
        "/api/v1/documents",
        headers=support_headers,
        files={"file": ("排障补充.md", "# 新错误码\n\nDEMO-12345 表示演示故障。", "text/markdown")},
    )
    assert response.status_code == 202, response.text
    document_id = response.json()["id"]
    rejected = client.post(
        f"/api/v1/documents/{document_id}/publish", headers=support_headers
    )
    assert rejected.status_code == 409

    with SessionLocal() as db:
        process_document(db, __import__("uuid").UUID(document_id))
    published = client.post(
        f"/api/v1/documents/{document_id}/publish", headers=support_headers
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"


def test_duplicate_document_is_rejected(client, support_headers):
    file_data = {"file": ("same.md", "# 完全相同内容", "text/markdown")}
    first = client.post("/api/v1/documents", headers=support_headers, files=file_data)
    second = client.post("/api/v1/documents", headers=support_headers, files=file_data)
    assert first.status_code == 202
    assert second.status_code == 409
