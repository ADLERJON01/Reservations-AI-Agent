"""LLM client seam.

Native Ollama is the default (and only working) implementation. LiteLLM +
Instructor are parked-but-kept-open behind the LLMClient protocol — see
instructor_stub.py and HANDOVER.md §7.
"""
from app.llm.client import LLMClient, LLMResult
from app.llm.ollama_native import OllamaNativeClient

__all__ = ["LLMClient", "LLMResult", "OllamaNativeClient"]
