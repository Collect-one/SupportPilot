import hashlib
import uuid
from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.api.serializers import document_dict
from app.config import get_settings
from app.database import get_db
from app.dependencies import require_support
from app.models import Document, DocumentChunk, User, utcnow


router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_SUFFIXES = {".md", ".txt", ".pdf"}


@router.post("", status_code=202)
def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持 Markdown、TXT 和文本型 PDF")
    content = file.file.read(settings.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=422, detail="不能上传空文件")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="文件不能超过 20 MB")
    digest = hashlib.sha256(content).hexdigest()
    if db.scalar(sa.select(Document).where(Document.sha256 == digest)):
        raise HTTPException(status_code=409, detail="相同内容的文档已经存在")
    logical_name = Path(filename).stem[:180]
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": logical_name})
    latest_version = db.scalar(
        sa.select(sa.func.max(Document.version)).where(Document.logical_name == logical_name)
    ) or 0
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = settings.upload_dir / f"{uuid.uuid4()}{suffix}"
    stored_path.write_bytes(content)
    document = Document(
        logical_name=logical_name,
        filename=filename,
        version=latest_version + 1,
        content_type=file.content_type or "application/octet-stream",
        file_path=str(stored_path.resolve()),
        sha256=digest,
        size_bytes=len(content),
        uploaded_by_id=user.id,
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="相同内容或版本的文档已经存在") from exc
    return document_dict(db, document)


@router.get("")
def list_documents(
    user: User = Depends(require_support), db: Session = Depends(get_db)
):
    documents = db.scalars(sa.select(Document).order_by(Document.created_at.desc()))
    return [document_dict(db, document) for document in documents]


@router.get("/{document_id}")
def get_document(
    document_id: uuid.UUID,
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    document = db.scalar(
        sa.select(Document).where(Document.id == document_id).with_for_update()
    )
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    result = document_dict(db, document)
    result["chunks"] = [
        {
            "id": chunk.id,
            "position": chunk.position,
            "heading": chunk.heading,
            "page_number": chunk.page_number,
            "content": chunk.content,
        }
        for chunk in db.scalars(
            sa.select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.position)
            .limit(30)
        )
    ]
    return result


@router.post("/{document_id}/publish")
def publish_document(
    document_id: uuid.UUID,
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    if document.status != "READY":
        raise HTTPException(status_code=409, detail="只有解析完成的文档可以发布")
    db.execute(
        sa.update(Document)
        .where(
            Document.logical_name == document.logical_name,
            Document.status == "PUBLISHED",
            Document.id != document.id,
        )
        .values(status="DISABLED")
    )
    document.status = "PUBLISHED"
    document.published_at = utcnow()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="已有其他版本并发发布，请刷新后重试") from exc
    return document_dict(db, document)


@router.post("/{document_id}/disable")
def disable_document(
    document_id: uuid.UUID,
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    if document.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="只有已发布文档可以停用")
    document.status = "DISABLED"
    db.commit()
    return document_dict(db, document)


@router.post("/{document_id}/retry")
def retry_document(
    document_id: uuid.UUID,
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    stale_processing = (
        document.status == "PROCESSING"
        and document.lease_expires_at is not None
        and document.lease_expires_at < utcnow()
    )
    if (document.status != "FAILED" and not stale_processing) or document.retry_count >= 3:
        raise HTTPException(status_code=409, detail="该文档当前不能重试")
    document.status = "UPLOADED"
    document.error_message = None
    document.processing_started_at = None
    document.lease_expires_at = None
    db.commit()
    return document_dict(db, document)
