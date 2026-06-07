"""Preprocessor Agent (#1).

Deterministic. Parses one raw .txt email thread into a cleaned EmailInput (for
the Classifier + the `emails` table) and derives the locked input_metadata
snapshot. No LLM.

Scope boundaries:
  - Does NOT strip forwarding wrappers — forwarding-invariance ("classify by
    inner content") is the Classifier prompt's job, per the locked spec.
  - Does NOT extract booking fields — that's the Classifier+Extractor (#2).
  - Retains anonymized MASKED_* tokens verbatim.

Raw .txt format (custom flat header block, NOT RFC822):
    subject: <...>
    from: <...>
    to: <...>
    cc: <...>
    date: <...>
    body:
    <body text...>
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models.state import EmailInput, InputMetadata

# Header keys that appear, each on its own line, before the `body:` marker.
_HEADER_KEYS = ("subject", "from", "to", "cc", "date")
_BODY_MARKER = "body:"

# --- body-cleaning patterns (conservative; mirror observable Phase 1 cleaning) ---
# "CAUTION: EXTERNAL EMAIL. Do not click links..." security banner.
_CAUTION_RE = re.compile(r"^\s*CAUTION:\s*EXTERNAL EMAIL.*$", re.IGNORECASE | re.MULTILINE)
# Bracketed image/logo placeholders, e.g. "[channel manager logo]", "[image: ...]".
_BRACKET_PLACEHOLDER_RE = re.compile(r"^\s*\[[^\]]*\b(?:logo|image|cid|banner)\b[^\]]*\]\s*$",
                                     re.IGNORECASE | re.MULTILINE)
# Collapse 3+ consecutive newlines down to a blank-line separator.
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

# --- thread-segmentation patterns (for thread_length_estimate) ---
# A run of underscores Outlook inserts above a forwarded block.
_UNDERSCORE_RULE_RE = re.compile(r"^_{5,}\s*$", re.MULTILINE)
# "-----Original Message-----" style separators.
_ORIGINAL_MSG_RE = re.compile(r"^-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE | re.MULTILINE)
# Quoted forward/reply header lines in EN/PT, e.g. "De:", "From:", "Enviado:", "Sent:".
_QUOTED_HEADER_RE = re.compile(r"^\s*(?:De|From|Enviado|Sent|Para|To|Assunto|Subject)\s*:",
                               re.IGNORECASE | re.MULTILINE)


def parse_raw_txt(source: str, *, email_id: Optional[str] = None,
                  source_file: Optional[str] = None) -> EmailInput:
    """Parse raw .txt content into an EmailInput. `source` is the file text."""
    headers, body_raw = _split_headers_and_body(source)
    body_clean = clean_body(body_raw)
    return EmailInput(
        email_id=email_id or (Path(source_file).stem if source_file else ""),
        source_file=source_file,
        subject=headers.get("subject"),
        from_raw=headers.get("from"),
        to_raw=headers.get("to"),
        cc_raw=headers.get("cc"),
        date_raw=headers.get("date"),
        date_parsed=parse_date(headers.get("date")),
        body_raw=body_raw,
        body_clean=body_clean,
    )


def preprocess(path: str | Path) -> EmailInput:
    """Entry point: read a raw .txt file from disk and parse it."""
    p = Path(path)
    return parse_raw_txt(p.read_text(encoding="utf-8"), email_id=p.stem, source_file=p.name)


def _split_headers_and_body(source: str) -> tuple[dict[str, Optional[str]], str]:
    """Split the leading `key:` header block from the body (after `body:`)."""
    headers: dict[str, Optional[str]] = {}
    lines = source.splitlines()
    body_start = len(lines)
    for i, line in enumerate(lines):
        if line.strip().lower() == _BODY_MARKER:
            body_start = i + 1
            break
        stripped = line.lstrip()
        for key in _HEADER_KEYS:
            prefix = f"{key}:"
            if stripped.lower().startswith(prefix):
                value = stripped[len(prefix):].strip()
                headers[key] = value or None
                break
    body_raw = "\n".join(lines[body_start:]).strip("\n")
    return headers, body_raw


def clean_body(body_raw: str) -> str:
    """Conservative cleanup of a raw body. Keeps MASKED_* tokens verbatim."""
    if not body_raw:
        return ""
    text = _CAUTION_RE.sub("", body_raw)
    text = _BRACKET_PLACEHOLDER_RE.sub("", text)
    # normalize whitespace: trim each line, collapse blank-line runs, trim ends
    text = "\n".join(ln.rstrip() for ln in text.splitlines())
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def parse_date(date_raw: Optional[str]) -> Optional[str]:
    """Parse "2026-02-19 15:34:15+00:00" -> ISO 8601. Tolerant; None on failure."""
    if not date_raw:
        return None
    try:
        return datetime.fromisoformat(date_raw.strip()).isoformat()
    except ValueError:
        return None


def estimate_thread_length(source_or_body: str) -> int:
    """Heuristic count of messages in the thread: 1 outer + forwarded/replied
    segments. Detected via underscore rules, "Original Message" separators, or
    clusters of quoted forward/reply headers. Always >= 1."""
    if not source_or_body:
        return 1
    separators = (
        len(_UNDERSCORE_RULE_RE.findall(source_or_body))
        + len(_ORIGINAL_MSG_RE.findall(source_or_body))
    )
    if separators == 0:
        # No explicit rule line: fall back to detecting a quoted-header cluster.
        # A forwarded block carries >=3 quoted headers (De/Enviado/Para/Assunto...).
        if len(_QUOTED_HEADER_RE.findall(source_or_body)) >= 3:
            separators = 1
    return 1 + separators


def to_input_metadata(email: EmailInput, *, body_for_thread_estimate: Optional[str] = None) -> InputMetadata:
    """Derive the locked input_metadata snapshot from a parsed EmailInput.

    thread_length_estimate is computed over the raw body (it carries the
    forwarded headers that body_clean preserves anyway).
    """
    thread_src = body_for_thread_estimate or email.body_raw or email.body_clean or ""
    return InputMetadata(
        source_file=email.source_file,
        subject=email.subject,
        from_raw=email.from_raw,
        to_raw=email.to_raw,
        cc_raw=email.cc_raw,
        date_raw=email.date_raw,
        date_parsed=email.date_parsed,
        thread_length_estimate=estimate_thread_length(thread_src),
        body_clean_length=len(email.body_clean or ""),
    )
