"""RAG Agent (#6).

Conditional: runs only when the Router set rag_required (policy/general question).
Retrieves from the FAQ KB, decides kb_answerable from the best similarity, then
RE-INVOKES the Router's route() so the final action is decided in one place
("code decides") — RAG never sets the action itself. No LLM here (the drafting
is the Output Generator's job).
"""
from __future__ import annotations

from typing import Optional

from app.agents.router import route
from app.config import get_settings
from app.models.retrieval import RetrievalOutput
from app.models.state import AgentState
from app.rag.query_builder import build_query
from app.rag.retriever import Retriever

AGENT_NAME = "rag"


def rag(state: AgentState, retriever: Optional[Retriever] = None) -> AgentState:
    """Retrieve KB sources for a policy question, set kb_answerable, re-route."""
    state.agent_path.append(AGENT_NAME)
    sig = state.router_signals

    # Only runs for the policy-question candidate path; otherwise a no-op.
    if sig is None or not sig.rag_required:
        state.retrieval = RetrievalOutput(used=False)
        return state

    s = get_settings()
    if retriever is None:
        from app.rag.retriever import get_default_retriever
        retriever = get_default_retriever()

    query_text, query_source = build_query(state)
    sources = retriever.retrieve(query_text, top_k=s.rag_top_k)
    best = max((src.score for src in sources), default=0.0)
    kb_answerable = best >= s.kb_answerable_threshold

    state.retrieval = RetrievalOutput(
        used=True, sources=sources,
        query_text=query_text, query_source=query_source,
        embedding_model=s.embedding_model, top_k=s.rag_top_k,
        threshold=s.kb_answerable_threshold, kb_answerable=kb_answerable,
    )

    # Resolve the final action via the Router with kb_answerable now known.
    sig.kb_answerable = kb_answerable
    decision = route(sig)
    state.recommended_action = decision.recommended_action
    state.routing_reason = decision.routing_reason
    state.applied_rule_id = decision.rule_id
    return state
