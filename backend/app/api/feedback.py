import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_customer
from app.models import Conversation, Feedback, Message, User
from app.schemas import FeedbackCreate


router = APIRouter(prefix="/messages", tags=["feedback"])


@router.post("/{message_id}/feedback")
def submit_feedback(
    message_id: uuid.UUID,
    payload: FeedbackCreate,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    message = db.get(Message, message_id)
    if not message or message.role != "ASSISTANT":
        raise HTTPException(status_code=404, detail="回答不存在")
    conversation = db.get(Conversation, message.conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="回答不存在")
    feedback = db.scalar(
        sa.select(Feedback).where(Feedback.message_id == message_id, Feedback.user_id == user.id)
    )
    if feedback:
        feedback.resolved = payload.resolved
        feedback.reason = payload.reason
    else:
        feedback = Feedback(
            message_id=message_id,
            user_id=user.id,
            resolved=payload.resolved,
            reason=payload.reason,
        )
        db.add(feedback)
    db.commit()
    return {"id": feedback.id, "resolved": feedback.resolved, "reason": feedback.reason}
