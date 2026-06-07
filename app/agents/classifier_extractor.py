"""Classifier+Extractor Agent (#2).

One LLM call per email: emits the locked classification + extraction contract,
validated by the EmailExtraction Pydantic gate. Deterministic (temp 0 + fixed
seed), primary-model-only. "Describe, not decide" — no routing/audit/validation.

On success: writes state.llm_output, records model_name, appends to agent_path.
On failure (still invalid after bounded retries): leaves llm_output None and
appends a structured error — downstream routing sends it to manual_review.
"""
from __future__ import annotations

from typing import Optional

from app.agents.prompts import build_system_prompt, build_user_prompt
from app.config import get_settings
from app.llm.client import LLMClient
from app.llm.ollama_native import OllamaNativeClient
from app.models.llm_output import EmailExtraction
from app.models.state import AgentState

AGENT_NAME = "classifier_extractor"


def classify(state: AgentState, client: Optional[LLMClient] = None) -> AgentState:
    """Run the Classifier+Extractor over state.email, populating state.llm_output."""
    settings = get_settings()
    client = client or OllamaNativeClient()
    model = settings.primary_model

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(state.email)

    state.agent_path.append(AGENT_NAME)
    state.model_name = model

    # Attempt 0: deterministic primary call. Retries (if any) nudge temperature up,
    # since a temp-0 retry is greedy and would reproduce the same invalid output.
    last_error: Optional[str] = None
    attempts = settings.classifier_max_retries + 1
    for attempt in range(attempts):
        if attempt == 0:
            temperature = settings.classifier_temperature
            seed = settings.classifier_seed
        else:
            temperature = settings.classifier_retry_temperature
            seed = settings.classifier_seed + attempt

        result = client.call_structured(
            system_prompt, user_prompt,
            response_model=EmailExtraction,
            model=model, temperature=temperature, seed=seed,
        )
        if result.valid and result.output is not None:
            state.llm_output = result.output
            return state
        last_error = result.error

    # All attempts failed — leave llm_output None and record the failure.
    state.errors.append({
        "agent_name": AGENT_NAME,
        "error_type": "invalid_llm_output",
        "message": last_error or "unknown",
        "retry_count": settings.classifier_max_retries,
    })
    return state
