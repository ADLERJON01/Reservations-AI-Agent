"""Single source of truth for settings and paths.

Everything that touches the filesystem or the model runtime resolves through
here, so the package has no scattered hardcoded paths — which keeps the move
from this flat ``app/`` layout to an installable package trivial later.

Override any field via environment variables prefixed ``PESTANA_``
(e.g. ``PESTANA_PRIMARY_MODEL=mistral:7b``).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor: this file lives at <PROJECT_ROOT>/app/config.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PESTANA_", extra="ignore")

    # --- model runtime (Ollama) ---
    # Primary/fallback chosen by the model-selection smoke test (see SMOKE_DECISION.md).
    primary_model: str = "ministral-3:3b"
    fallback_model: str = "llama3.2:3b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_path: str = "/api/chat"
    request_timeout_s: int = 300       # big booking emails can run 40-58s on M1
    num_predict: int = 2000
    temperature: float = 0.4           # generic client default; classifier overrides to 0.0

    # --- Classifier+Extractor (#2): deterministic, primary-only ---
    classifier_temperature: float = 0.0      # temp 0 → reproducible batch
    classifier_seed: int = 0                 # fixed per-email seed
    classifier_max_retries: int = 1          # bounded salvage retries on invalid output
    classifier_retry_temperature: float = 0.3  # temp 0 retry is futile (greedy); nudge up
    body_char_limit: int = 6000              # truncate body_clean in the user prompt

    # --- RAG (#6): conditional retrieval over the FAQ KB ---
    embedding_model: str = "BAAI/bge-m3"     # multilingual; swappable, benchmark at eval
    chroma_path: Path = PROJECT_ROOT / ".chroma"
    kb_path: Path = PROJECT_ROOT / "inputs" / "knowledge_base" / "pestana_faqs_en.jsonl"
    rag_top_k: int = 3
    kb_answerable_threshold: float = 0.65    # cosine; RECALIBRATE for BGE-M3 at eval
    rag_query_char_limit: int = 512          # focused-query length cap

    # --- paths (all under PROJECT_ROOT; inputs are READ ONLY) ---
    project_root: Path = PROJECT_ROOT
    inputs_dir: Path = PROJECT_ROOT / "inputs"
    outputs_dir: Path = PROJECT_ROOT / "outputs"
    dataset_path: Path = PROJECT_ROOT / "inputs" / "cleaned_dataset" / "emails_extracted_new.jsonl"
    db_url: str = Field(default=f"sqlite:///{PROJECT_ROOT / 'pestana_agent.db'}")

    @property
    def ollama_chat_url(self) -> str:
        return f"{self.ollama_base_url}{self.ollama_chat_path}"


@lru_cache
def get_settings() -> Settings:
    """Cached accessor — import this, don't instantiate Settings directly."""
    return Settings()
