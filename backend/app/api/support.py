import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_support
from app.models import Notification, Organization, Ticket, ToolRun, User


router = APIRouter(prefix="/support", tags=["support"])


@router.get("/overview")
def overview(user: User = Depends(require_support), db: Session = Depends(get_db)):
    counts = {
        status: db.scalar(sa.select(sa.func.count()).select_from(Ticket).where(Ticket.status == status))
        for status in ["OPEN", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED"]
    }
    return {
        "ticket_counts": counts,
        "published_documents": db.scalar(
            sa.select(sa.func.count())
            .select_from(__import__("app.models", fromlist=["Document"]).Document)
            .where(__import__("app.models", fromlist=["Document"]).Document.status == "PUBLISHED")
        ),
        "failed_notifications": db.scalar(
            sa.select(sa.func.count())
            .select_from(Notification)
            .where(Notification.status == "FAILED")
        ),
    }


@router.get("/operations")
def operations(user: User = Depends(require_support), db: Session = Depends(get_db)):
    tools = list(db.scalars(sa.select(ToolRun).order_by(ToolRun.created_at.desc()).limit(30)))
    notifications = list(
        db.scalars(sa.select(Notification).order_by(Notification.created_at.desc()).limit(30))
    )
    return {
        "tool_runs": [
            {
                "id": item.id,
                "tool_name": item.tool_name,
                "status": item.status,
                "duration_ms": item.duration_ms,
                "error_message": item.error_message,
                "created_at": item.created_at,
            }
            for item in tools
        ],
        "notifications": [
            {
                "id": item.id,
                "ticket_id": item.ticket_id,
                "status": item.status,
                "attempt_count": item.attempt_count,
                "error_message": item.error_message,
                "created_at": item.created_at,
            }
            for item in notifications
        ],
    }


@router.get("/organizations")
def organizations(user: User = Depends(require_support), db: Session = Depends(get_db)):
    return [
        {"id": organization.id, "name": organization.name, "slug": organization.slug}
        for organization in db.scalars(sa.select(Organization).order_by(Organization.name))
    ]
