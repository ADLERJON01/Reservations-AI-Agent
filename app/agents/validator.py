"""Validator Agent (#3).

A second LLM call that re-reads the email + the Classifier's proposed JSON and
judges whether it is faithful to the email. LLM semantic critique ONLY — no
deterministic checks (those are Audit #4's job). Flag-only; it never rewrites.

Skips when there is no llm_output to critique. revised_confidence is stored for
logging/calibration but never gates routing (decision 2026-06-06).
"""
from __future__ import annotations

from typing import Optional

from app.agents.prompts import build_validator_system_prompt, build_validator_user_prompt
from app.config import get_settings
from app.llm.client import LLMClient
from app.llm.ollama_native import OllamaNativeClient
from app.models.validator import ValidatorResult
from app.models.state import AgentState, ValidatorOutput

AGENT_NAME = "validator"


def validate(state: AgentState, client: Optional[LLMClient] = None) -> AgentState:
    """Critique state.llm_output, populating state.validator."""
    state.agent_path.append(AGENT_NAME)

    # Nothing to critique — the Classifier produced no valid output.
    if state.llm_output is None:
        state.validator = ValidatorOutput(validation_result="skipped")
        return state

    settings = get_settings()
    client = client or OllamaNativeClient()
    model = settings.primary_model

    system_prompt = build_validator_system_prompt()
    user_prompt = build_validator_user_prompt(state.email, state.llm_output)

    last_error: Optional[str] = None
    attempts = settings.classifier_max_retries + 1   # reuse the deterministic LLM-call settings
    for attempt in range(attempts):
        if attempt == 0:
            temperature = settings.classifier_temperature
            seed = settings.classifier_seed
        else:
            temperature = settings.classifier_retry_temperature
            seed = settings.classifier_seed + attempt

        result = client.call_structured(
            system_prompt, user_prompt,
            response_model=ValidatorResult,
            model=model, temperature=temperature, seed=seed,
        )
        if result.valid and result.output is not None:
            vr: ValidatorResult = result.output
            state.validator = ValidatorOutput(
                validation_result=vr.validation_result,
                flagged_fields=vr.flagged_fields,
                reasoning_short=vr.reasoning_short,
                revised_confidence=vr.revised_confidence,
            )
            return state
        last_error = result.error

    # Critique failed to produce a valid verdict — record it and leave "skipped".
    state.validator = ValidatorOutput(validation_result="skipped")
    state.errors.append({
        "agent_name": AGENT_NAME,
        "error_type": "invalid_llm_output",
        "message": last_error or "unknown",
        "retry_count": settings.classifier_max_retries,
    })
    return state
