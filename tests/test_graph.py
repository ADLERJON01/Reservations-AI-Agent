"""LangGraph wiring (#1–#5): offline tests with injected fake clients verify the
full chain runs in order and the failure path routes correctly; a gated live
test runs the real pipeline end-to-end.
"""
import requests
import pytest

from app.config import get_settings
from app.graph import build_pipeline_graph, run_pipeline, run_state
from app.llm.client import LLMResult
from app.models.llm_output import EmailExtraction
from app.models.state import AgentState, EmailInput
from app.models.validator import ValidatorResult

RAW_DIR = get_settings().inputs_dir / "raw_emails"

# A complete, clean "new" booking notification → audit clean → router audit_only.
CLEAN_BOOKING = EmailExtraction.model_validate({
    "classification": {
        "predicted_category": "booking_notification", "sender_type": "automated_system",
        "request_type": "none", "booking_lifecycle_stage": "new",
        "expects_human_response": "no", "urgency_signal": "routine",
        "confidence": 0.9, "evidence_short": "New Reservation", "reasoning_short": "templated",
    },
    "extraction": {
        "booking_identity": {"source_channel": "Booking.com", "booking_reference": "631",
                             "hotel_name": "Pestana - Brussels", "notification_type": "new"},
        "guest": {"guest_name": "MASKED_NAME_x"},
        "stay": {"check_in_date": "2026-03-06", "check_out_date": "2026-03-08", "adults": 2},
        "financials": {"total_amount": 208.17, "currency": "EUR"},
    },
})
CONFIRMED = ValidatorResult(validation_result="confirmed", flagged_fields=[],
                            reasoning_short="ok", revised_confidence=0.9)


class _FakeClient:
    def __init__(self, result):
        self._result = result

    def call_structured(self, system_prompt, user_prompt, *, response_model,
                        model=None, temperature=None, seed=None):
        return self._result


def _graph(classifier_result, validator_result=None):
    return build_pipeline_graph(
        classifier_client=_FakeClient(classifier_result),
        validator_client=_FakeClient(validator_result) if validator_result else None,
    )


def test_graph_runs_full_chain_in_order():
    graph = _graph(LLMResult(True, CLEAN_BOOKING, None, 1.0, "m"),
                   LLMResult(True, CONFIRMED, None, 1.0, "m"))
    state = AgentState(email=EmailInput(email_id="e", body_clean="New Reservation"),
                       agent_path=["preprocessor"])
    out = run_state(state, graph)
    assert out.agent_path == ["preprocessor", "classifier_extractor", "validator",
                              "audit", "router", "output_generator", "guardrails"]
    assert out.llm_output is not None
    assert out.audit.audit_finding == "clean"
    assert out.recommended_action == "audit_only"
    assert out.applied_rule_id == "R023_BN_CLEAN"


def test_graph_failure_path_routes_to_manual_review():
    # classifier returns invalid → llm_output None → validator/audit skip → router manual_review
    graph = _graph(LLMResult(False, None, "ValidationError", 1.0, "m"))
    state = AgentState(email=EmailInput(email_id="e", body_clean="x"))
    out = run_state(state, graph)
    assert out.llm_output is None
    assert out.recommended_action == "manual_review_unclear"
    assert out.applied_rule_id == "R001_SCHEMA_INVALID"
    # every node still ran (validator/audit skip internally but record their step)
    assert out.agent_path == ["classifier_extractor", "validator", "audit",
                              "router", "output_generator", "guardrails"]
    assert out.validator.validation_result == "skipped"
    assert out.audit.audit_finding == "n/a"


# --- live end-to-end ---
def _ollama_up() -> bool:
    s = get_settings()
    try:
        return requests.get(f"{s.ollama_base_url}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")
def test_run_pipeline_real_email():
    out = run_pipeline(RAW_DIR / "email_1.txt")
    assert out.agent_path == ["preprocessor", "classifier_extractor", "validator",
                              "audit", "router", "output_generator", "guardrails"]
    assert out.recommended_action is not None
    assert out.applied_rule_id
