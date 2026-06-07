"""Validator (#3): orchestration via an injected fake client, prompt-builder
checks, and a gated live classify->validate integration test.
"""
import requests
import pytest

from app.agents.classifier_extractor import classify
from app.agents.preprocessor import preprocess
from app.agents.prompts import build_validator_system_prompt, build_validator_user_prompt
from app.agents.validator import AGENT_NAME, validate
from app.config import get_settings
from app.llm.client import LLMResult
from app.models.llm_output import EmailExtraction
from app.models.validator import ValidatorResult
from app.models.state import AgentState, EmailInput

RAW_DIR = get_settings().inputs_dir / "raw_emails"

LLM_OUTPUT = EmailExtraction.model_validate({
    "classification": {
        "predicted_category": "booking_notification",
        "sender_type": "automated_system",
        "request_type": "none",
        "booking_lifecycle_stage": "new",
        "expects_human_response": "no",
        "urgency_signal": "routine",
        "confidence": 0.9,
        "evidence_short": "New Reservation",
        "reasoning_short": "templated channel booking event",
    },
    "extraction": {},
})

CONFIRMED = ValidatorResult(validation_result="confirmed", flagged_fields=[],
                            reasoning_short="all fields supported", revised_confidence=0.9)
FLAGGED = ValidatorResult(validation_result="flagged",
                          flagged_fields=["extraction.guest.guest_name"],
                          reasoning_short="guest name not in email", revised_confidence=0.4)


class _FakeClient:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def call_structured(self, system_prompt, user_prompt, *, response_model,
                        model=None, temperature=None, seed=None):
        self.calls.append({"response_model": response_model, "temperature": temperature,
                           "seed": seed})
        return self._results.pop(0)


def _state_with_output() -> AgentState:
    return AgentState(
        email=EmailInput(email_id="email_1", subject="s", from_raw="f",
                         body_clean="New Reservation"),
        llm_output=LLM_OUTPUT,
    )


# --- orchestration ---
def test_validate_confirmed():
    client = _FakeClient([LLMResult(True, CONFIRMED, None, 1.0, "ministral-3:3b")])
    state = validate(_state_with_output(), client=client)
    assert state.validator.validation_result == "confirmed"
    assert state.validator.flagged_fields == []
    assert state.validator.revised_confidence == 0.9
    assert AGENT_NAME in state.agent_path
    assert state.errors == []
    assert client.calls[0]["response_model"] is ValidatorResult


def test_validate_flagged_carries_paths():
    client = _FakeClient([LLMResult(True, FLAGGED, None, 1.0, "ministral-3:3b")])
    state = validate(_state_with_output(), client=client)
    assert state.validator.validation_result == "flagged"
    assert state.validator.flagged_fields == ["extraction.guest.guest_name"]


def test_validate_skips_when_no_llm_output():
    client = _FakeClient([])  # must not be called
    state = AgentState(email=EmailInput(email_id="e"))
    state = validate(state, client=client)
    assert state.validator.validation_result == "skipped"
    assert AGENT_NAME in state.agent_path
    assert client.calls == []


def test_validate_invalid_records_error_and_skips():
    fail = LLMResult(False, None, "ValidationError: x", 1.0, "ministral-3:3b")
    client = _FakeClient([fail, fail])  # primary + 1 retry
    state = validate(_state_with_output(), client=client)
    assert state.validator.validation_result == "skipped"
    assert len(state.errors) == 1
    assert state.errors[0]["agent_name"] == AGENT_NAME
    assert len(client.calls) == 2
    assert client.calls[1]["temperature"] == get_settings().classifier_retry_temperature


# --- prompt builders ---
def test_validator_prompts_include_email_and_proposed_output():
    sys = build_validator_system_prompt()
    assert "confirmed" in sys and "flagged" in sys
    assert "Only flag" in sys or "Do NOT propose corrected values" in sys
    user = build_validator_user_prompt(
        EmailInput(email_id="e", subject="SUBJ", from_raw="F", body_clean="hello body"),
        LLM_OUTPUT)
    assert "SUBJ" in user and "hello body" in user
    assert "PROPOSED OUTPUT" in user
    assert "booking_notification" in user  # serialized proposed JSON is present


# --- live integration ---
def _ollama_up() -> bool:
    s = get_settings()
    try:
        return requests.get(f"{s.ollama_base_url}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")
def test_classify_then_validate_real_email():
    email = preprocess(RAW_DIR / "email_1.txt")
    state = classify(AgentState(email=email))
    assert state.llm_output is not None, state.errors
    state = validate(state)
    assert state.validator.validation_result in {"confirmed", "flagged"}
    assert 0.0 <= state.validator.revised_confidence <= 1.0
