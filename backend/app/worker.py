import time
from datetime import timedelta

import sqlalchemy as sa

from app.database import SessionLocal
from app.config import get_settings
from app.models import Document, Notification, utcnow
from app.services.documents import process_document
from app.services.notifications import deliver_ticket_notification


def run_notification_once() -> bool:
    with SessionLocal() as db:
        notification = db.scalar(
            sa.select(Notification)
            .where(Notification.status == "PENDING")
            .order_by(Notification.created_at)
            .with_for_update(skip_locked=True)
        )
        if not notification:
            return False
        deliver_ticket_notification(db, notification)
        return True


def run_once() -> bool:
    with SessionLocal() as db:
        document = db.scalar(
            sa.select(Document)
            .where(
                sa.or_(
                    Document.status == "UPLOADED",
                    sa.and_(
                        Document.status == "PROCESSING",
                        Document.lease_expires_at < utcnow(),
                    ),
                ),
                Document.retry_count < 3,
            )
            .order_by(Document.created_at)
            .with_for_update(skip_locked=True)
        )
        if not document:
            return False
        document.status = "PROCESSING"
        document.processing_started_at = utcnow()
        document.lease_expires_at = utcnow() + timedelta(
            seconds=get_settings().worker_lease_seconds
        )
        db.commit()
        try:
            process_document(db, document.id)
        except Exception:
            return True
        return True


def main() -> None:
    while True:
        try:
            processed = run_notification_once() or run_once()
        except Exception:
            processed = False
        if not processed:
            time.sleep(2)


if __name__ == "__main__":
    main()
