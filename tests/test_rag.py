"""RAG (#6): offline tests with an injected fake retriever (no chromadb /
sentence-transformers needed). Covers the agent's answerable/not-answerable
re-routing, the skip path, the query builder, the router R030A/B branches, and
the conditional graph edge.
"""
import pytest

from app.agents.rag import rag
from app.agents.router import RULES, route
from app.config import get_settings
from app.graph import build_pipeline_graph, run_state
from app.llm.client import LLMResult
from app.models.llm_output import EmailExtraction
from app.models.output import GeneratedReply
from app.models.retrieval import RetrievalSource
from app.models.router_signals import RouterSignals
from app.models.state import AgentState, EmailInput, ValidatorOutput
from app.models.validator import ValidatorResult


def _policy_output(evidence="what is the cancellation policy"):
    return EmailExtraction.model_validate({
        "classification": {
            "predicted_category": "service_or_information_inquiry",
            "sender_type": "direct_guest", "request_type": "policy_or_general_question",
            "booking_lifecycle_stage": "n/a", "expects_human_response": "yes",
            "urgency_signal": "routine", "confidence": 0.8,
            "evidence_short": evidence, "reasoning_short": "asks about a policy",
        },
        "extraction": {},
    })


class _FakeRetriever:
    """Returns one source with a fixed score; records the query it was given."""
    def __init__(self, score: float):
        self._score = score
        self.last_query = None

    def retrieve(self, query, *, top_k=3):
        self.last_query = query
        return [RetrievalSource(source_id="faq_001", source_title="Cancellation policy",
                                chunk_text="You can cancel free of charge until ...",
                                score=self._score, raw_distance=1.0 - self._score)]


def _policy_state() -> AgentState:
    return AgentState(
        email=EmailInput(email_id="e", subject="Question", body_clean="Can I cancel?"),
        llm_output=_policy_output(),
        router_signals=RouterSignals(category="service_or_information_inquiry",
                                     request_type="policy_or_general_question",
                                     rag_required=True),
        recommended_action="draft_reply_with_rag", applied_rule_id="R030_INQ_POLICY",
    )


# --- agent: answerable / not-answerable / skip ---
def test_rag_answerable_keeps_draft():
    st = rag(_policy_state(), retriever=_FakeRetriever(score=0.90))
    assert st.retrieval.used is True
    assert st.retrieval.kb_answerable is True
    assert st.recommended_action == "draft_reply_with_rag"
    assert st.applied_rule_id == "R030A_INQ_POLICY_ANSWERABLE"
    assert "rag" in st.agent_path


def test_rag_not_answerable_escalates():
    st = rag(_policy_state(), retriever=_FakeRetriever(score=0.40))
    assert st.retrieval.kb_answerable is False
    assert st.recommended_action == "escalate_to_reservations_team"
    assert st.applied_rule_id == "R030B_INQ_POLICY_UNANSWERABLE"


def test_rag_skips_when_not_required():
    fake = _FakeRetriever(score=0.9)
    state = AgentState(email=EmailInput(email_id="e"),
                       router_signals=RouterSignals(rag_required=False))
    st = rag(state, retriever=fake)
    assert st.retrieval.used is False
    assert fake.last_query is None          # retriever never called
    assert "rag" in st.agent_path


# --- query builder: 3 query_source values ---
def test_query_source_subject_plus_evidence():
    from app.rag.query_builder import build_query
    q, src = build_query(_policy_state())
    assert src == "subject_plus_evidence"
    assert "Question" in q and "cancel" in q.lower()


def test_query_source_body_excerpt_when_no_evidence():
    from app.rag.query_builder import build_query
    st = _policy_state()
    st.llm_output.classification.evidence_short = ""
    q, src = build_query(st)
    assert src == "subject_plus_body_excerpt"


def test_query_source_body_fallback_when_no_subject():
    from app.rag.query_builder import build_query
    st = _policy_state()
    st.email.subject = None
    st.llm_output.classification.evidence_short = ""
    q, src = build_query(st)
    assert src == "body_clean_fallback"


# --- router R030A/B branches resolve on kb_answerable ---
def test_route_r030a_b_and_candidate():
    base = dict(category="service_or_information_inquiry",
                request_type="policy_or_general_question")
    assert route(RouterSignals(**base, kb_answerable=None)).rule_id == "R030_INQ_POLICY"
    assert route(RouterSignals(**base, kb_answerable=True)).rule_id == "R030A_INQ_POLICY_ANSWERABLE"
    assert route(RouterSignals(**base, kb_answerable=False)).rule_id == "R030B_INQ_POLICY_UNANSWERABLE"


def test_rules_catalog_ids_unique():
    ids = [r.id for r in RULES]
    assert len(ids) == len(set(ids))


# --- conditional graph edge: rag fires only for the policy path ---
def test_graph_runs_rag_for_policy_question():
    # The draft path now runs through #7; inject a fake reply_client (citing the
    # faq_001 the retriever returns) so the test stays offline and deterministic.
    reply = GeneratedReply(reply_text="You can cancel free of charge until 48h before.",
                           used_source_ids=["faq_001"])
    graph = build_pipeline_graph(
        classifier_client=_FakeClient(LLMResult(True, _policy_output(), None, 1.0, "m")),
        validator_client=_FakeClient(LLMResult(True, _confirmed(), None, 1.0, "m")),
        rag_retriever=_FakeRetriever(score=0.9),
        reply_client=_FakeClient(LLMResult(True, reply, None, 1.0, "m")),
    )
    out = run_state(AgentState(email=EmailInput(email_id="e", subject="Q", body_clean="Can I cancel?")), graph)
    assert "rag" in out.agent_path
    assert out.recommended_action == "draft_reply_with_rag"
    assert out.applied_rule_id == "R030A_INQ_POLICY_ANSWERABLE"
    assert out.output.draft_reply == "You can cancel free of charge until 48h before."
    assert out.output.used_source_ids == ["faq_001"]


def test_graph_skips_rag_for_non_policy():
    booking = EmailExtraction.model_validate({
        "classification": {"predicted_category": "booking_notification",
                           "sender_type": "automated_system", "request_type": "none",
                           "booking_lifecycle_stage": "new", "expects_human_response": "no",
                           "urgency_signal": "routine", "confidence": 0.9,
                           "evidence_short": "x", "reasoning_short": "y"},
        "extraction": {}})
    graph = build_pipeline_graph(
        classifier_client=_FakeClient(LLMResult(True, booking, None, 1.0, "m")),
        validator_client=_FakeClient(LLMResult(True, _confirmed(), None, 1.0, "m")),
        rag_retriever=_FakeRetriever(score=0.9),
    )
    out = run_state(AgentState(email=EmailInput(email_id="e", body_clean="x")), graph)
    assert "rag" not in out.agent_path


class _FakeClient:
    def __init__(self, result):
        self._result = result

    def call_structured(self, system_prompt, user_prompt, *, response_model,
                        model=None, temperature=None, seed=None):
        return self._result


def _confirmed():
    return ValidatorResult(validation_result="confirmed", flagged_fields=[],
                           reasoning_short="ok", revised_confidence=0.9)


# --- live retrieval against the real BGE-M3 index (skipped if absent) ---
def _index_ready() -> bool:
    try:
        import chromadb  # noqa: F401
        import sentence_transformers  # noqa: F401
    except Exception:
        return False
    return (get_settings().chroma_path / "chroma.sqlite3").exists()


@pytest.mark.skipif(not _index_ready(), reason="RAG index / deps not available")
def test_live_retrieval_cancellation():
    from app.rag.retriever import ChromaRetriever
    hits = ChromaRetriever().retrieve("What is the cancellation policy?", top_k=3)
    assert hits
    assert any("cancel" in (h.source_title or "").lower() for h in hits)
    assert 0.0 <= hits[0].score <= 1.0
