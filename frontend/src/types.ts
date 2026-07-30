export interface User {
  id: string
  email: string
  display_name: string
  role: 'CUSTOMER' | 'SUPPORT'
  organization_id: string | null
  organization_name: string | null
}

export interface ActionProposal {
  id: string
  action_type: string
  payload: Record<string, any>
  expires_at: string
  confirmed_ticket_id: string | null
  confirmed_ticket_number: string | null
}

export interface Message {
  id: string
  role: 'USER' | 'ASSISTANT' | 'SUPPORT'
  status: string | null
  content: string
  trace_id: string
  latency_ms: number | null
  created_at: string
  action_proposal: ActionProposal | null
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages?: Message[]
}

export interface TicketEvent {
  id: string
  event_type: string
  content: string | null
  metadata_json: Record<string, any>
  created_at: string
  author_name: string | null
}

export interface Ticket {
  id: string
  number: string
  organization_id: string
  customer_id: string
  assignee_id: string | null
  conversation_id: string | null
  title: string
  description: string
  product_module: string
  category: string
  priority: string
  workspace_id: string | null
  environment: string | null
  error_code: string | null
  reproduction_steps: string | null
  business_impact: string | null
  status: string
  created_at: string
  updated_at: string
  customer_name: string | null
  organization_name: string | null
  assignee_name: string | null
  events: TicketEvent[]
  handoff_context: {
    recent_messages: Array<{ id: string; role: string; status: string | null; content: string; created_at: string }>
    citations: Array<{ message_id: string; document_name: string; version: number; heading: string | null; excerpt: string; score: number }>
    tool_runs: Array<{ tool_name: string; status: string; duration_ms: number; output: Record<string, unknown>; error: string | null }>
  } | null
}

export interface DocumentRecord {
  id: string
  logical_name: string
  filename: string
  version: number
  status: string
  content_type: string
  sha256: string
  size_bytes: number
  error_message: string | null
  retry_count: number
  processing_started_at: string | null
  lease_expires_at: string | null
  published_at: string | null
  created_at: string
  chunk_count: number
  chunks?: Array<{
    id: string
    position: number
    heading: string | null
    page_number: number | null
    content: string
  }>
}

export interface RagTraceCandidate {
  rank: number
  chunk_id: string
  document_id: string
  document_name: string
  version: number
  heading: string | null
  page_number: number | null
  excerpt: string
  score: number
  semantic_score: number
  keyword_coverage: number
  exact_identifier: boolean
}

export interface RagTraceCitation {
  rank: number
  chunk_id: string
  document_id: string
  document_name: string
  version: number
  heading: string | null
  page_number: number | null
  excerpt: string
  score: number
}

export interface RagTraceSummary {
  trace_id: string
  conversation_id: string
  customer_name: string
  organization_name: string
  question: string
  answer_status: string
  decision_status: string
  decision_reason: string | null
  top_score: number | null
  candidate_count: number
  citation_count: number
  latency_ms: number | null
  legacy_partial: boolean
  created_at: string
}

export interface RagTraceDetail extends RagTraceSummary {
  answer: string
  candidates: RagTraceCandidate[]
  citations: RagTraceCitation[]
  tool_runs: Array<{ tool_name: string; status: string; duration_ms: number; error_message: string | null }>
}

export interface RagTraceList {
  items: RagTraceSummary[]
  total: number
  offset: number
  limit: number
}
