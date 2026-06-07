"""Integration smoke for the native Ollama client.

Skipped automatically unless a local Ollama server is reachable, so the suite
stays green offline / in CI. Run with Ollama up to exercise the real path.
"""
import pytest
import requests

from app.config import get_settings
from app.llm import LLMResult, OllamaNativeClient
from app.models.llm_output import EmailExtraction


def _ollama_up() -> bool:
    s = get_settings()
    try:
        return requests.get(f"{s.ollama_base_url}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _ollama_up(), reason="Ollama server not reachable")

SYSTEM = "You are an email classification + extraction engine. Output one JSON object matching the schema exactly."
USER = (
    "--- EMAIL ---\nSubject: Booking confirmation 12345\n"
    "From: noreply@channel.example\n\nBody: Your booking is confirmed for 2 nights.\n--- END EMAIL ---"
)


def test_returns_valid_extraction_against_real_ollama():
    client = OllamaNativeClient()
    result = client.call_structured(SYSTEM, USER, response_model=EmailExtraction, seed=100)
    assert isinstance(result, LLMResult)
    assert result.valid, f"expected valid extraction, got error: {result.error}"
    assert result.output is not None
    assert result.output.classification.predicted_category  # an allowed enum value
