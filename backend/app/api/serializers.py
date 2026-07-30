import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import (
    ActionProposal,
    Citation,
    Document,
    DocumentChunk,
    Message,
    Ticket,
    ToolRun,
    User,
)


def user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "organization_id": user.organization_id,
        "organization_name": user.organization.name if user.organization else None,
    }


def proposal_dict(proposal: ActionProposal | None, db: Session | None = None) -> dict | None:
    if not proposal:
        return None
    ticket = db.get(Ticket, proposal.confirmed_ticket_id) if db and proposal.confirmed_ticket_id else None
    return {
        "id": proposal.id,
        "action_type": proposal.action_type,
        "payload": proposal.payload,
        "expires_at": proposal.expires_at,
        "confirmed_ticket_id": proposal.confirmed_ticket_id,
        "confirmed_ticket_number": ticket.number if ticket else None,
    }


def citation_dict(citation) -> dict:
    chunk = citation.chunk
    return {
        "id": citation.id,
        "chunk_id": citation.chunk_id,
        "document_id": chunk.document_id,
        "document_name": chunk.document.logical_name,
        "version": chunk.document.version,
        "heading": chunk.heading,
        "page_number": chunk.page_number,
        "excerpt": citation.excerpt,
        "score": citation.score,
    }


def message_dict(
    message: Message, proposal: ActionProposal | None = None, db: Session | None = None
) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "status": message.status,
        "content": message.content,
        "trace_id": message.trace_id,
        "latency_ms": message.latency_ms,
        "created_at": message.created_at,
        "citations": [citation_dict(citation) for citation in message.citations],
        "action_proposal": proposal_dict(proposal, db),
    }


def ticket_dict(
    db: Session,
    ticket: Ticket,
    include_events: bool = False,
    include_handoff: bool = False,
) -> dict:
    customer = db.get(User, ticket.customer_id)
    assignee = db.get(User, ticket.assignee_id) if ticket.assignee_id else None
    organization = customer.organization if customer else None
    result = {
        "id": ticket.id,
        "number": ticket.number,
        "organization_id": ticket.organization_id,
        "customer_id": ticket.customer_id,
        "assignee_id": ticket.assignee_id,
        "conversation_id": ticket.conversation_id,
        "title": ticket.title,
        "description": ticket.description,
        "product_module": ticket.product_module,
        "category": ticket.category,
        "priority": ticket.priority,
        "workspace_id": ticket.workspace_id,
        "environment": ticket.environment,
        "error_code": ticket.error_code,
        "reproduction_steps": ticket.reproduction_steps,
        "business_impact": ticket.business_impact,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "customer_name": customer.display_name if customer else None,
        "organization_name": organization.name if organization else None,
        "assignee_name": assignee.display_name if assignee else None,
        "events": [],
        "handoff_context": None,
    }
    if include_events:
        result["events"] = [
            {
                "id": event.id,
                "event_type": event.event_type,
                "content": event.content,
                "metadata_json": event.metadata_json,
                "created_at": event.created_at,
                "author_name": event.author.display_name if event.author else None,
            }
            for event in ticket.events
        ]
    if include_handoff and ticket.conversation_id:
        recent = list(
            db.scalars(
                sa.select(Message)
                .where(Message.conversation_id == ticket.conversation_id)
                .order_by(Message.created_at.desc())
                .limit(10)
            )
        )
        recent.reverse()
        citations = list(
            db.scalars(
                sa.select(Citation)
                .join(Message)
                .where(Message.conversation_id == ticket.conversation_id)
                .order_by(Message.created_at.desc(), Citation.rank)
                .limit(12)
            )
        )
        tools = list(
            db.scalars(
                sa.select(ToolRun)
                .where(ToolRun.conversation_id == ticket.conversation_id)
                .order_by(ToolRun.created_at.desc())
                .limit(12)
            )
        )
        result["handoff_context"] = {
            "recent_messages": [
                {
                    "id": str(message.id),
                    "role": message.role,
                    "status": message.status,
                    "content": message.content,
                    "created_at": message.created_at,
                }
                for message in recent
            ],
            "citations": [
                {
                    "message_id": str(citation.message_id),
                    "document_name": citation.chunk.document.logical_name,
                    "version": citation.chunk.document.version,
                    "heading": citation.chunk.heading,
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
                    "output": tool.output_json,
                    "error": tool.error_message,
                }
                for tool in tools
            ],
        }
    return result


def document_dict(db: Session, document: Document) -> dict:
    chunk_count = db.scalar(
        sa.select(sa.func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
    )
    return {
        "id": document.id,
        "logical_name": document.logical_name,
        "filename": document.filename,
        "version": document.version,
        "status": document.status,
        "content_type": document.content_type,
        "sha256": document.sha256,
        "size_bytes": document.size_bytes,
        "error_message": document.error_message,
        "retry_count": document.retry_count,
        "processing_started_at": document.processing_started_at,
        "lease_expires_at": document.lease_expires_at,
        "published_at": document.published_at,
        "created_at": document.created_at,
        "chunk_count": chunk_count,
    }
