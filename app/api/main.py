"""FastAPI application — scaffold.

Only /health is live. The /process-email endpoint (HANDOVER task #12) is stubbed
to make the contract visible; it returns 501 until the pipeline is wired.

Run: uvicorn app.api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.config import get_settings

app = FastAPI(title="Pestana AI Email Agent", version="0.1.0")


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "primary_model": s.primary_model,
        "fallback_model": s.fallback_model,
        "ollama": s.ollama_chat_url,
    }


@app.post("/process-email", status_code=501)
def process_email(email: dict) -> dict:
    """Run the full pipeline on one email. Not implemented until agents are wired."""
    raise HTTPException(status_code=501, detail="Pipeline not yet implemented (HANDOVER task #12).")
