import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    organization_id: uuid.UUID | None
    organization_name: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=160)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class CitationOut(BaseModel):
    id: uuid.UUID
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    version: int
    heading: str | None
    page_number: int | None
    excerpt: str
    score: float


class ActionProposalOut(BaseModel):
    id: uuid.UUID
    action_type: str
    payload: dict[str, Any]
    expires_at: datetime
    confirmed_ticket_id: uuid.UUID | None = None
    confirmed_ticket_number: str | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    status: str | None
    content: str
    trace_id: uuid.UUID
    latency_ms: int | None
    created_at: datetime
    action_proposal: ActionProposalOut | None = None


class ConversationSummary(ORMModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]


class AgentResponse(BaseModel):
    status: str
    answer: str
    clarification_question: str | None = None
    action_proposal: ActionProposalOut | None = None
    trace_id: uuid.UUID
    latency_ms: int
    message_id: uuid.UUID


class RagTraceCandidate(BaseModel):
    rank: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    version: int
    heading: str | None = None
    page_number: int | None = None
    excerpt: str
    score: float
    semantic_score: float
    keyword_coverage: float
    exact_identifier: bool


class RagTraceCitation(BaseModel):
    rank: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    version: int
    heading: str | None = None
    page_number: int | None = None
    excerpt: str
    score: float


class RagTraceToolRun(BaseModel):
    tool_name: str
    status: str
    duration_ms: int
    error_message: str | None = None


class RagTraceSummary(BaseModel):
    trace_id: uuid.UUID
    conversation_id: uuid.UUID
    customer_name: str
    organization_name: str
    question: str
    answer_status: str
    decision_status: str
    decision_reason: str | None = None
    top_score: float | None = None
    candidate_count: int
    citation_count: int
    latency_ms: int | None = None
    legacy_partial: bool
    created_at: datetime


class RagTraceList(BaseModel):
    items: list[RagTraceSummary]
    total: int
    offset: int
    limit: int


class RagTraceDetail(RagTraceSummary):
    answer: str
    candidates: list[RagTraceCandidate]
    citations: list[RagTraceCitation]
    tool_runs: list[RagTraceToolRun]


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=5, max_length=12000)
    product_module: str = Field(default="其他", max_length=80)
    category: str = "OTHER"
    priority: str = "NORMAL"
    workspace_id: str | None = Field(default=None, max_length=100)
    environment: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)
    reproduction_steps: str | None = Field(default=None, max_length=6000)
    business_impact: str | None = Field(default=None, max_length=3000)
    conversation_id: uuid.UUID | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)


class ProposalConfirm(BaseModel):
    payload: dict[str, Any] | None = None


class TicketCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=6000)


class TicketUpdate(BaseModel):
    status: str | None = None
    category: str | None = None
    priority: str | None = None
    assignee_id: uuid.UUID | None = None


class TicketEventOut(ORMModel):
    id: uuid.UUID
    event_type: str
    content: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    author_name: str | None = None


class TicketOut(ORMModel):
    id: uuid.UUID
    number: str
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    assignee_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    title: str
    description: str
    product_module: str
    category: str
    priority: str
    workspace_id: str | None
    environment: str | None
    error_code: str | None
    reproduction_steps: str | None
    business_impact: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    organization_name: str | None = None
    assignee_name: str | None = None
    events: list[TicketEventOut] = []
    handoff_context: dict[str, Any] | None = None


class DocumentOut(ORMModel):
    id: uuid.UUID
    logical_name: str
    filename: str
    version: int
    status: str
    content_type: str
    sha256: str
    size_bytes: int
    error_message: str | None
    retry_count: int
    processing_started_at: datetime | None
    lease_expires_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    chunk_count: int = 0


class FeedbackCreate(BaseModel):
    resolved: bool
    reason: str | None = Field(default=None, max_length=120)
