"""Focused retrieval-query construction.

Embedding the raw forwarded body is noisy (forward headers, signatures, refs,
boilerplate — the preprocessor deliberately keeps the wrapper). So build a
focused query from the most question-like signal available, and record which
strategy was used (query_source) for debugging/eval.
"""
from __future__ import annotations

from app.config import get_settings
from app.models.state import AgentState


def build_query(state: AgentState) -> tuple[str, str]:
    """Return (query_text, query_source). query_source is one of:
    subject_plus_evidence | subject_plus_body_excerpt | body_clean_fallback."""
    limit = get_settings().rag_query_char_limit
    email = state.email
    subject = (email.subject or "").strip()
    body = (email.body_clean or "").strip()
    evidence = ""
    if state.llm_output is not None:
        evidence = (state.llm_output.classification.evidence_short or "").strip()

    if subject and evidence:
        return f"{subject} {evidence}".strip(), "subject_plus_evidence"
    if subject:
        return f"{subject} {body[:limit]}".strip(), "subject_plus_body_excerpt"
    return body[:limit], "body_clean_fallback"
