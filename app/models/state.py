"""AgentState — the shared object passed between pipeline agents.

This is the value LangGraph (#11) will thread through the graph. Kept as a plain
Pydantic model so it is usable and testable before LangGraph is wired in. Each
agent reads the fields it needs and writes its own output slot; nothing is
mutated in place destructively.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.audit import AuditOutput
from app.models.llm_output import EmailExtraction
from app.models.output import OutputArtifacts
from app.models.retrieval import RetrievalOutput
from app.models.router_signals import RecommendedAction, RouterSignals


class EmailInput(BaseModel):
    """Cleaned email the pipeline operates on, produced by the Preprocessor (#1)
    from a raw .txt thread. Persisted to the `emails` table; the Classifier reads
    `body_clean`. Header fields retain anonymized MASKED_* tokens verbatim."""
    email_id: str
    source_file: Optional[str] = None
    subject: Optional[str] = None
    from_raw: Optional[str] = None
    to_raw: Optional[str] = None
    cc_raw: Optional[str] = None
    date_raw: Optional[str] = None
    date_parsed: Optional[str] = None
    body_raw: Optional[str] = None
    body_clean: Optional[str] = None


class InputMetadata(BaseModel):
    """The locked `input_metadata` snapshot (agent_output_schema.json v1.0.0).
    Metadata-only by design — stores the body's length, not its text."""
    source_file: Optional[str] = None
    subject: Optional[str] = None
    from_raw: Optional[str] = None
    to_raw: Optional[str] = None
    cc_raw: Optional[str] = None
    date_raw: Optional[str] = None
    date_parsed: Optional[str] = None
    thread_length_estimate: Optional[int] = None
    body_clean_length: Optional[int] = None


class ValidatorOutput(BaseModel):
    """Validator (#3) — LLM semantic critique only (no deterministic checks here)."""
    validation_result: str = "skipped"          # confirmed | flagged | skipped
    flagged_fields: List[str] = Field(default_factory=list)
    reasoning_short: str = ""
    revised_confidence: Optional[float] = None    # logged only; does not gate routing


class AgentState(BaseModel):
    """Shared pipeline state. Agents fill in their slots as the email flows through."""
    email: EmailInput

    # filled by each agent in turn (None until that agent has run)
    llm_output: Optional[EmailExtraction] = None
    validator: Optional[ValidatorOutput] = None
    audit: Optional[AuditOutput] = None
    router_signals: Optional[RouterSignals] = None
    recommended_action: Optional[RecommendedAction] = None
    routing_reason: Optional[str] = None
    applied_rule_id: Optional[str] = None
    retrieval: Optional[RetrievalOutput] = None
    output: Optional[OutputArtifacts] = None

    # provenance / diagnostics
    model_name: Optional[str] = None              # LLM that produced llm_output
    agent_path: List[str] = Field(default_factory=list)
    errors: List[dict] = Field(default_factory=list)  # {agent_name, error_type, message, retry_count}
