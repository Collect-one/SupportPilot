import uuid
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, aliased, joinedload

from app.database import get_db
from app.dependencies import require_support
from app.models import (
    Citation,
    Conversation,
    Document,
    DocumentChunk,
    Message,
    Notification,
    Organization,
    Ticket,
    ToolRun,
    User,
)
from app.schemas import RagTraceDetail, RagTraceList


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
            .select_from(Document)
            .where(Document.status == "PUBLISHED")
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


def _rag_trace_rows(db: Session, trace_id: uuid.UUID | None = None):
    question_message = aliased(Message)
    question = (
        sa.select(question_message.content)
        .where(
            question_message.conversation_id == Message.conversation_id,
            question_message.role == "USER",
            question_message.created_at <= Message.created_at,
        )
        .order_by(question_message.created_at.desc())
        .limit(1)
        .correlate(Message)
        .scalar_subquery()
    )
    citation_count = (
        sa.select(sa.func.count())
        .select_from(Citation)
        .where(Citation.message_id == Message.id)
        .correlate(Message)
        .scalar_subquery()
    )
    statement = (
        sa.select(
            Message,
            Conversation,
            User,
            Organization,
            ToolRun,
            question.label("question"),
            citation_count.label("citation_count"),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(User, Conversation.user_id == User.id)
        .join(Organization, Conversation.organization_id == Organization.id)
        .outerjoin(
            ToolRun,
            sa.and_(
                ToolRun.trace_id == Message.trace_id,
                ToolRun.tool_name == "search_knowledge",
            ),
        )
        .where(Message.role == "ASSISTANT")
        .order_by(Message.created_at.desc())
    )
    if trace_id is not None:
        statement = statement.where(Message.trace_id == trace_id)
    return list(db.execute(statement))


def _decision(search_run: ToolRun | None, citation_count: int) -> tuple[str, str | None]:
    if not search_run:
        return ("LEGACY" if citation_count else "NOT_SEARCHED", None)
    if search_run.status == "FAILED":
        return "FAILED", search_run.error_message
    decision = (search_run.output_json or {}).get("decision", {})
    if isinstance(decision, str):
        reason = decision
        sufficient = reason == "sufficient"
        conflicting = reason in {"ambiguous_sources", "conflicting_identifier_sources"}
    else:
        reason = decision.get("reason")
        sufficient = bool(decision.get("sufficient"))
        conflicting = bool(decision.get("conflicting"))
    if conflicting:
        return "CONFLICT", reason
    if sufficient:
        return "SUFFICIENT", reason
    return "INSUFFICIENT", reason


def _trace_summary(row) -> dict:
    message, conversation, customer, organization, search_run, question, citation_count = row
    output = search_run.output_json or {} if search_run else {}
    candidates = output.get("candidates", [])
    decision_status, decision_reason = _decision(search_run, citation_count)
    return {
        "trace_id": message.trace_id,
        "conversation_id": conversation.id,
        "customer_name": customer.display_name,
        "organization_name": organization.name,
        "question": question or "",
        "answer_status": message.status or "UNKNOWN",
        "decision_status": decision_status,
        "decision_reason": decision_reason,
        "top_score": output.get("top_score"),
        "candidate_count": len(candidates) if candidates else int(output.get("matches") or 0),
        "citation_count": citation_count,
        "latency_ms": message.latency_ms,
        "legacy_partial": bool(citation_count and not candidates),
        "created_at": message.created_at,
    }


@router.get("/rag-traces", response_model=RagTraceList)
def rag_traces(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    decision: Literal[
        "SUFFICIENT", "INSUFFICIENT", "CONFLICT", "FAILED", "NOT_SEARCHED", "LEGACY"
    ]
    | None = None,
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    items = [_trace_summary(row) for row in _rag_trace_rows(db)]
    if decision:
        items = [item for item in items if item["decision_status"] == decision]
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "offset": offset,
        "limit": limit,
    }


@router.get("/rag-traces/{trace_id}", response_model=RagTraceDetail)
def rag_trace_detail(
    trace_id: uuid.UUID,
    user: User = Depends(require_support),
    db: Session = Depends(get_db),
):
    rows = _rag_trace_rows(db, trace_id)
    if not rows:
        raise HTTPException(status_code=404, detail="RAG 验收记录不存在")
    row = rows[0]
    message, _, _, _, search_run, _, _ = row
    summary = _trace_summary(row)
    citations = list(
        db.scalars(
            sa.select(Citation)
            .where(Citation.message_id == message.id)
            .options(joinedload(Citation.chunk).joinedload(DocumentChunk.document))
            .order_by(Citation.rank)
        ).unique()
    )
    tools = list(
        db.scalars(
            sa.select(ToolRun)
            .where(ToolRun.trace_id == trace_id)
            .order_by(ToolRun.created_at)
        )
    )
    return {
        **summary,
        "answer": message.content,
        "candidates": (search_run.output_json or {}).get("candidates", [])
        if search_run
        else [],
        "citations": [
            {
                "rank": citation.rank,
                "chunk_id": citation.chunk_id,
                "document_id": citation.chunk.document_id,
                "document_name": citation.chunk.document.logical_name,
                "version": citation.chunk.document.version,
                "heading": citation.chunk.heading,
                "page_number": citation.chunk.page_number,
                "excerpt": citation.excerpt,
                "score": citation.score,
            }
            for citation in citations
        ],
        "tool_runs": [
            {
                "tool_name": tool.tool_name,
                "status": tool.status,
                "duration_ms": tool.duration_ms,
                "error_message": tool.error_message,
            }
            for tool in tools
        ],
    }
