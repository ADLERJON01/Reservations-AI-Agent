"""Classifier+Extractor (#2): orchestration via an injected fake client (no
Ollama), prompt-builder checks, and a gated live integration test.
"""
import requests
import pytest

from app.agents.classifier_extractor import AGENT_NAME, classify
from app.agents.preprocessor import preprocess
from app.agents.prompts import (
    CATEGORY_GUIDE,
    FACET_GUIDE,
    SYSTEM_PROMPT,
    build_system_prompt,
    build_user_prompt,
)
from app.config import get_settings
from app.llm.client import LLMResult
from app.models.llm_output import EmailExtraction
from app.models.state import AgentState, EmailInput

RAW_DIR = get_settings().inputs_dir / "raw_emails"

VALID_OUTPUT = EmailExtraction.model_validate({
    "classification": {
        "predicted_category": "booking_notification",
        "sender_type": "automated_system",
        "request_type": "none",
        "booking_lifecycle_stage": "new",
        "inquiry_answer_source": "not_applicable",
        "requires_human_followup": "no",
        "urgency_signal": "routine",
        "confidence": 0.9,
        "evidence_short": "New Reservation",
        "reasoning_short": "templated channel booking event",
    },
    "extraction": {},
})


class _FakeClient:
    """Records calls and returns a scripted sequence of LLMResults."""
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def call_structured(self, system_prompt, user_prompt, *, response_model,
                        model=None, temperature=None, seed=None):
        self.calls.append({"model": model, "temperature": temperature, "seed": seed,
                           "response_model": response_model})
        return self._results.pop(0)


def _state() -> AgentState:
    return AgentState(email=EmailInput(email_id="email_1", subject="s",
                                       from_raw="f", body_clean="New Reservation"))


# --- orchestration: success ---
def test_classify_success_populates_state():
    client = _FakeClient([LLMResult(True, VALID_OUTPUT, None, 1.0, "ministral-3:3b")])
    state = classify(_state(), client=client)
    assert state.llm_output is VALID_OUTPUT
    assert AGENT_NAME in state.agent_path
    assert state.model_name == get_settings().primary_model
    assert state.errors == []
    # first call is deterministic: temp 0, fixed seed
    assert client.calls[0]["temperature"] == get_settings().classifier_temperature
    assert client.calls[0]["seed"] == get_settings().classifier_seed


# --- orchestration: invalid then retry then give up (primary-only) ---
def test_classify_all_invalid_records_error_and_no_output():
    fail = LLMResult(False, None, "ValidationError: x", 1.0, "ministral-3:3b")
    client = _FakeClient([fail, fail])  # primary + 1 retry (max_retries default 1)
    state = classify(_state(), client=client)
    assert state.llm_output is None
    assert len(state.errors) == 1
    err = state.errors[0]
    assert err["agent_name"] == AGENT_NAME
    assert err["error_type"] == "invalid_llm_output"
    assert err["retry_count"] == get_settings().classifier_max_retries
    # retry nudged temperature up and changed the seed (temp-0 retry would be futile)
    assert len(client.calls) == 2
    assert client.calls[1]["temperature"] == get_settings().classifier_retry_temperature
    assert client.calls[1]["seed"] != client.calls[0]["seed"]


def test_classify_retry_then_success():
    fail = LLMResult(False, None, "bad", 1.0, "ministral-3:3b")
    ok = LLMResult(True, VALID_OUTPUT, None, 1.0, "ministral-3:3b")
    client = _FakeClient([fail, ok])
    state = classify(_state(), client=client)
    assert state.llm_output is VALID_OUTPUT
    assert state.errors == []


# --- prompt builders ---
def test_system_prompt_contains_key_rules():
    sp = build_system_prompt()
    assert "MASKED_*" in sp
    assert "0.00" in sp
    assert 'never output the string "null"'.lower() in sp.lower()
    # all 7 categories + all 5 facets present
    for cat in ("booking_notification", "booking_change_or_cancellation",
                "service_or_information_inquiry", "payment_billing_or_rate_issue",
                "inventory_availability_or_stop_sales",
                "system_or_channel_delivery_exception", "other_or_unclear"):
        assert cat in CATEGORY_GUIDE
    for facet in ("sender_type", "request_type", "inquiry_answer_source",
                  "booking_lifecycle_stage", "requires_human_followup", "urgency_signal"):
        assert facet in FACET_GUIDE
    assert SYSTEM_PROMPT in sp


def test_user_prompt_truncates_and_includes_fields():
    email = EmailInput(email_id="e", subject="SUBJ", from_raw="FROM",
                       body_clean="X" * 10000)
    prompt = build_user_prompt(email, body_char_limit=100)
    assert "SUBJ" in prompt and "FROM" in prompt
    assert prompt.count("X") == 100  # truncated to the limit


# --- live integration (skipped unless Ollama is up) ---
def _ollama_up() -> bool:
    s = get_settings()
    try:
        return requests.get(f"{s.ollama_base_url}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")
def test_classify_real_email_is_valid_and_deterministic():
    email = preprocess(RAW_DIR / "email_1.txt")
    s1 = classify(AgentState(email=email))
    s2 = classify(AgentState(email=email))
    assert s1.llm_output is not None, s1.errors
    assert s1.llm_output.classification.predicted_category
    # temp 0 + fixed seed → same category across runs
    assert (s1.llm_output.classification.predicted_category
            == s2.llm_output.classification.predicted_category)
