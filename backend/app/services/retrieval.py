import re
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Document, DocumentChunk
from app.services.text import cosine_similarity, get_embedding, tokenize


IDENTIFIER_PATTERN = re.compile(
    r"\b(?:[A-Z]{2,12}[-_]\d{3,8}|\d{5}|ws_[A-Za-z0-9_-]{3,})\b",
    re.IGNORECASE,
)


@dataclass
class SearchResult:
    chunk: DocumentChunk
    score: float
    semantic_score: float
    keyword_coverage: float
    exact_identifier: bool


@dataclass
class EvidenceDecision:
    sufficient: bool
    conflicting: bool
    reason: str


def extract_identifiers(text: str) -> set[str]:
    return {value.lower() for value in IDENTIFIER_PATTERN.findall(text)}


def search_chunks(db: Session, query: str, limit: int = 5) -> list[SearchResult]:
    query_embedding = get_embedding(query)
    statement = (
        sa.select(DocumentChunk)
        .join(Document)
        .where(Document.status == "PUBLISHED")
        .options(joinedload(DocumentChunk.document))
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        statement = statement.order_by(
            DocumentChunk.embedding.cosine_distance(query_embedding)
        ).limit(40)
    else:
        statement = statement.limit(1500)
    candidates = list(db.scalars(statement).unique())

    query_tokens = set(tokenize(query))
    meaningful_tokens = {
        token for token in query_tokens if len(token) >= 2 or token.isascii() and len(token) >= 3
    }
    query_identifiers = extract_identifiers(query)
    ranked: list[SearchResult] = []
    for chunk in candidates:
        semantic = float(max(cosine_similarity(query_embedding, list(chunk.embedding)), 0.0))
        chunk_tokens = set(chunk.tokenized_text.split())
        keyword = float(
            len(meaningful_tokens & chunk_tokens) / max(len(meaningful_tokens), 1)
        )
        chunk_identifiers = extract_identifiers(chunk.content)
        exact_identifier = bool(query_identifiers and query_identifiers <= chunk_identifiers)
        exact_term = any(
            len(token) >= 4 and token in chunk.content.lower() for token in meaningful_tokens
        )
        score = semantic * 0.62 + keyword * 0.28
        if exact_term:
            score += 0.08
        if exact_identifier:
            score += 0.28
        ranked.append(
            SearchResult(
                chunk=chunk,
                score=float(min(score, 1.0)),
                semantic_score=semantic,
                keyword_coverage=keyword,
                exact_identifier=exact_identifier,
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]


def evaluate_evidence(query: str, results: list[SearchResult]) -> EvidenceDecision:
    if not results:
        return EvidenceDecision(False, False, "no_results")
    top = results[0]
    identifiers = extract_identifiers(query)
    if identifiers and not top.exact_identifier:
        return EvidenceDecision(False, False, "identifier_not_found")

    # The same exact identifier in two published documents with near-equal scores is ambiguous.
    exact_matches = [result for result in results if result.exact_identifier]
    if len(exact_matches) > 1:
        first, second = exact_matches[:2]
        if (
            first.chunk.document_id != second.chunk.document_id
            and first.score - second.score < 0.04
            and first.chunk.content.strip() != second.chunk.content.strip()
        ):
            return EvidenceDecision(False, True, "conflicting_identifier_sources")

    threshold = get_settings().retrieval_threshold
    sufficient = top.exact_identifier or (
        top.score >= threshold
        and (top.keyword_coverage >= 0.10 or top.semantic_score >= threshold + 0.10)
    )
    if not sufficient:
        return EvidenceDecision(False, False, "low_relevance")

    # A weak top result with an indistinguishable runner-up is not reliable enough to cite.
    if len(results) > 1 and not top.exact_identifier:
        margin = top.score - results[1].score
        if top.score < threshold + 0.08 and margin < 0.015:
            return EvidenceDecision(False, True, "ambiguous_sources")
    return EvidenceDecision(True, False, "sufficient")


def has_sufficient_evidence(results: list[SearchResult], query: str = "") -> bool:
    return evaluate_evidence(query, results).sufficient
