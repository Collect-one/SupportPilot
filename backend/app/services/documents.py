import uuid
from datetime import timedelta
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentChunk, utcnow
from app.services.text import chunk_sections, get_embedding, parse_file, tokenize


def process_document(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise ValueError("文档不存在")
    document.status = "PROCESSING"
    document.error_message = None
    document.processing_started_at = document.processing_started_at or utcnow()
    document.lease_expires_at = utcnow() + timedelta(seconds=get_settings().worker_lease_seconds)
    db.commit()
    try:
        sections = chunk_sections(parse_file(Path(document.file_path)))
        if not sections:
            raise ValueError("文档中没有可用文本")
        db.execute(sa.delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        for position, section in enumerate(sections):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    position=position,
                    heading=section.heading,
                    page_number=section.page_number,
                    content=section.content,
                    tokenized_text=" ".join(tokenize(section.content)),
                    embedding=get_embedding(section.content),
                )
            )
        document.status = "READY"
        document.processing_started_at = None
        document.lease_expires_at = None
        db.commit()
    except Exception as exc:
        db.rollback()
        document = db.get(Document, document_id)
        if document:
            document.retry_count += 1
            document.status = "FAILED"
            document.error_message = str(exc)[:2000]
            document.processing_started_at = None
            document.lease_expires_at = None
            db.commit()
        raise
    return document
