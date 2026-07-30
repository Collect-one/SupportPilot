import base64
import hashlib
import hmac
import time

import httpx
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Notification, Ticket, utcnow
from app.services.text import redact_sensitive


CATEGORY_LABELS = {
    "ACCOUNT": "账号",
    "CONFIG": "产品配置",
    "API": "API / 集成",
    "BILLING": "计费",
    "INCIDENT": "故障",
    "FEATURE": "功能建议",
    "OTHER": "其他",
}

PRIORITY_LABELS = {
    "LOW": "低",
    "NORMAL": "普通",
    "HIGH": "高",
}


def _display_label(value: str, labels: dict[str, str]) -> str:
    return labels.get(value, value)


def enqueue_ticket_notification(
    db: Session, ticket: Ticket, source_notification_id=None
) -> Notification:
    previous_attempts = db.scalar(
        sa.select(sa.func.max(Notification.attempt_count)).where(
            Notification.ticket_id == ticket.id
        )
    ) or 0
    notification = Notification(
        ticket_id=ticket.id,
        source_notification_id=source_notification_id,
        status="PENDING",
        attempt_count=previous_attempts + 1,
    )
    db.add(notification)
    db.flush()
    return notification


def deliver_ticket_notification(db: Session, notification: Notification) -> Notification:
    settings = get_settings()
    ticket = db.get(Ticket, notification.ticket_id)
    if not ticket:
        notification.status = "FAILED"
        notification.error_message = "ticket_missing"
        db.commit()
        return notification
    if not settings.feishu_webhook_url:
        notification.status = "DISABLED"
        notification.error_message = "未配置飞书 Webhook"
        db.commit()
        return notification
    summary = redact_sensitive(ticket.description)[:240]
    category = _display_label(ticket.category, CATEGORY_LABELS)
    priority = _display_label(ticket.priority, PRIORITY_LABELS)
    payload = {
        "msg_type": "text",
        "content": {
            "text": (
                f"新技术支持工单 {ticket.number}\n"
                f"{ticket.product_module} · {category} · {priority}\n"
                f"{summary}\n{settings.app_base_url}/support/tickets/{ticket.id}"
            )
        },
    }
    if settings.feishu_webhook_secret:
        timestamp = str(int(time.time()))
        signing_key = f"{timestamp}\n{settings.feishu_webhook_secret}".encode("utf-8")
        signature = base64.b64encode(
            hmac.new(signing_key, digestmod=hashlib.sha256).digest()
        ).decode("ascii")
        payload["timestamp"] = timestamp
        payload["sign"] = signature
    try:
        response = httpx.post(settings.feishu_webhook_url, json=payload, timeout=8)
        response.raise_for_status()
        body = response.json()
        code = body.get("code", body.get("StatusCode", 0)) if isinstance(body, dict) else -1
        if code not in (0, "0"):
            notification.status = "FAILED"
            notification.error_message = f"feishu_code_{code}"
        else:
            notification.status = "SENT"
            notification.sent_at = utcnow()
    except httpx.TimeoutException:
        notification.status = "FAILED"
        notification.error_message = "timeout"
    except httpx.HTTPStatusError as exc:
        notification.status = "FAILED"
        notification.error_message = f"http_status_{exc.response.status_code}"
    except (httpx.RequestError, ValueError):
        notification.status = "FAILED"
        notification.error_message = "transport_or_response_error"
    db.commit()
    return notification


def process_notification(db: Session, notification_id) -> Notification | None:
    notification = db.scalar(
        sa.select(Notification)
        .where(Notification.id == notification_id, Notification.status == "PENDING")
        .with_for_update(skip_locked=True)
    )
    if not notification:
        return db.get(Notification, notification_id)
    return deliver_ticket_notification(db, notification)


def send_ticket_notification(db: Session, ticket: Ticket) -> Notification:
    notification = enqueue_ticket_notification(db, ticket)
    db.commit()
    return process_notification(db, notification.id) or notification
