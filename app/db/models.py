"""Minimal persistence stub.

Two tables — the input email snapshot and the full pipeline output. Deliberately
thin: the agent output is stored as a JSON blob for now so persistence doesn't
block on the agent_output_schema being finalised. Promote individual columns
later if querying needs them (HANDOVER task #12).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, create_engine

from app.config import get_settings

_engine = None


class EmailRecord(SQLModel, table=True):
    """The cleaned email the pipeline ran on, produced by the Preprocessor (#1).
    Mirrors EmailInput; input_metadata snapshots a subset of these columns."""
    __tablename__ = "emails"

    email_id: str = Field(primary_key=True)
    source_file: Optional[str] = None
    subject: Optional[str] = None
    from_raw: Optional[str] = None
    to_raw: Optional[str] = None
    cc_raw: Optional[str] = None
    date_raw: Optional[str] = None
    date_parsed: Optional[str] = None
    body_raw: Optional[str] = None
    body_clean: Optional[str] = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentOutputRecord(SQLModel, table=True):
    """Full pipeline output for one email (stored as a JSON blob for now)."""
    __tablename__ = "agent_outputs"

    id: Optional[int] = Field(default=None, primary_key=True)
    email_id: str = Field(foreign_key="emails.email_id", index=True)
    recommended_action: Optional[str] = None
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def get_engine():
    """Lazily create the SQLite engine from settings."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().db_url, echo=False)
    return _engine


def init_db() -> None:
    """Create tables if they don't exist."""
    SQLModel.metadata.create_all(get_engine())
