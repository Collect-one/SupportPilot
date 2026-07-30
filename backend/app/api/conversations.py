import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.serializers import message_dict, proposal_dict
from app.database import get_db
from app.dependencies import get_current_user, require_customer
from app.models import ActionProposal, Citation, Conversation, DocumentChunk, Message, User
from app.schemas import (
    AgentResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    MessageCreate,
)
from app.services.agent import process_customer_message


router = APIRouter(prefix="/conversations", tags=["conversations"])


def _get_conversation(db: Session, conversation_id: uuid.UUID, user: User) -> Conversation:
    statement = (
        sa.select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(
            selectinload(Conversation.messages)
            .selectinload(Message.citations)
            .joinedload(Citation.chunk)
            .joinedload(DocumentChunk.document)
        )
    )
    conversation = db.scalar(statement)
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    if user.role != "SUPPORT" and conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conversation


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    conversation = Conversation(
        organization_id=user.organization_id,
        user_id=user.id,
        title=payload.title,
    )
    db.add(conversation)
    db.commit()
    return conversation


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    user: User = Depends(require_customer), db: Session = Depends(get_db)
):
    return list(
        db.scalars(
            sa.select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
        )
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _get_conversation(db, conversation_id, user)
    proposals = {
        proposal.message_id: proposal
        for proposal in db.scalars(
            sa.select(ActionProposal)
            .where(ActionProposal.conversation_id == conversation.id)
            .order_by(ActionProposal.created_at.desc())
        )
    }
    messages = []
    for message in conversation.messages:
        proposal = proposals.get(message.id) if message.status == "ACTION_PROPOSED" else None
        messages.append(message_dict(message, proposal, db))
    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": messages,
    }


@router.post("/{conversation_id}/messages", response_model=AgentResponse)
def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    conversation = _get_conversation(db, conversation_id, user)
    assistant, proposal, tools = process_customer_message(db, conversation, user, payload.content)
    db.commit()
    db.refresh(assistant)
    for citation in assistant.citations:
        _ = citation.chunk.document
    result = message_dict(assistant, proposal, db)
    return {
        "status": assistant.status,
        "answer": assistant.content,
        "citations": result["citations"],
        "clarification_question": assistant.content
        if assistant.status == "NEEDS_CLARIFICATION"
        else None,
        "action_proposal": proposal_dict(proposal, db),
        "tool_runs": [
            {"tool_name": tool.tool_name, "status": tool.status, "duration_ms": tool.duration_ms}
            for tool in tools
        ],
        "trace_id": assistant.trace_id,
        "latency_ms": assistant.latency_ms or 0,
        "message_id": assistant.id,
    }
