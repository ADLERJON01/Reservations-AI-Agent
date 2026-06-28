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

# --- noise-stripping patterns (preprocessor v2) ---
# Angle-bracket link targets, e.g. "Manage booking<https://...>" / "<mailto:...>": the
# visible text precedes them, so the target itself is never content.
_ANGLE_LINK_RE = re.compile(r"\s*<(?:https?|mailto):[^>]*>", re.IGNORECASE)
# Bare tracking / redirect / CDN URLs that carry no classification value.
_TRACKING_URL_RE = re.compile(
    r"https?://\S*?(?:awstrack\.me|exclaimer\.net|pstmrk\.it|googleapis\.com|"
    r"salesforce\.com/servlet|mailchi\.mp|\.awstrack\.me|track\.)\S*", re.IGNORECASE)
# Any remaining very long bare URL (>=90 chars) — almost always a tracking link.
_LONG_URL_RE = re.compile(r"https?://\S{90,}")

# Marketing / social / print-footer one-liners — dropped wholesale (no signal).
_JUNK_LINE_RE = re.compile(
    r"^\s*(?:"
    r"#?\s*the\s*time\s*of\s*your\s*life.*"
    r"|click\s*&?\s*follow\s*us.*|follow\s*us!?\s*"
    r"|#?shareourpassion.*|#mtsglobe.*|#thetimeofyourlife.*"
    r"|we\s*are\s*a\s*member\s*of\s*travelife.*"
    r"|somos\s*apenas\s*h[oó]spedes.*|we\s*are\s*all\s*planet\s*guests.*"
    r"|get\s*on\s*the\s*grape\s*vine.*"
    r"|please\s*do\s*not\s*print.*|pense\s*no\s*ambiente.*"
    r"|\[(?:facebook|instagram|linkedin|youtube|twitter|x|pinterest|logo|image|cid|abta|atol)[^\]]*\].*"
    r")\s*$", re.IGNORECASE)

# Legal / GDPR / confidentiality block openers. These ALWAYS trail a message, so we
# strip from the opener to the next thread separator (or end). Keeps signatures —
# they sit above these blocks and don't match these openers.
_LEGAL_OPENER_RE = re.compile(
    r"^\s*(?:"
    r"confidential[.:]|confidencial[.:]"
    r"|this (?:e-?mail|message)(?: and its| including| is intended| may have).*"
    r"|esta (?:mensagem|comunica[cç][aã]o)\b.*"
    r"|in accordance with the provisions.*"
    r"|o grupo pestana respeita.*|pestana group respects.*"
    r"|we hereby inform you that you may.*"
    r"|transmission of electronic mail.*"
    r"|RBC (?:Capital Markets|Europe|EUROPE LIMITED).*|ROYAL BANK OF CANADA.*"
    r")", re.IGNORECASE)


def _is_separator_line(line: str) -> bool:
    return bool(_UNDERSCORE_RULE_RE.match(line) or _ORIGINAL_MSG_RE.match(line))


def _strip_boilerplate(text: str) -> str:
    """Drop marketing/social one-liners and legal/GDPR blocks; keep signatures."""
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        if _is_separator_line(line):          # a separator ends any legal-block skip
            skipping = False
            out.append(line)
            continue
        if skipping:
            continue
        if _LEGAL_OPENER_RE.match(line):
            skipping = True
            continue
        if _JUNK_LINE_RE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


def parse_raw_txt(source: str, *, email_id: Optional[str] = None,
                  source_file: Optional[str] = None) -> EmailInput:
    """Parse raw .txt content into an EmailInput. `source` is the file text."""
    headers, body_raw = _split_headers_and_body(source)
    body_clean = clean_body(body_raw)
    latest_message, thread_history = split_latest_message(body_clean)
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
        latest_message=latest_message,
        thread_history=thread_history,
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
    """Conservative cleanup of a raw body. Keeps MASKED_* tokens + signatures verbatim."""
    if not body_raw:
        return ""
    text = _CAUTION_RE.sub("", body_raw)
    text = _BRACKET_PLACEHOLDER_RE.sub("", text)
    # strip tracking/redirect link noise (preprocessor v2) before line-based cleanup
    text = _ANGLE_LINK_RE.sub("", text)
    text = _TRACKING_URL_RE.sub("", text)
    text = _LONG_URL_RE.sub("", text)
    text = _strip_boilerplate(text)                 # legal/marketing/social, keeps signatures
    # normalize whitespace: trim each line, collapse blank-line runs, trim ends
    text = "\n".join(ln.rstrip() for ln in text.splitlines())
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def split_latest_message(clean_body: str) -> tuple[str, str]:
    """Best-effort split of the most-recent message from the older quoted thread.

    Forwarded threads are newest-first: an optional separator/header block, the latest
    message, then the next quoted message. We skip the latest message's own routing
    header and cut at the next boundary (underscore rule, "Original Message", or a
    run of >=2 quoted-header lines). Conservative: returns (whole_body, "") when no
    older message is detected, so content is never lost."""
    if not clean_body:
        return "", ""
    lines = clean_body.split("\n")
    n = len(lines)

    def header_run_len(i: int) -> int:
        j = i
        while j < n and _QUOTED_HEADER_RE.match(lines[j]):
            j += 1
        return j - i

    # 1) skip leading blanks + separator rules
    i = 0
    while i < n and (lines[i].strip() == "" or _UNDERSCORE_RULE_RE.match(lines[i])):
        i += 1
    # 2) skip the latest message's own routing header block, if present
    if i < n and header_run_len(i) >= 1:
        i += header_run_len(i)
    start = i
    # 3) advance to the next boundary = start of the older/quoted message
    k = start
    while k < n:
        if (_UNDERSCORE_RULE_RE.match(lines[k]) or _ORIGINAL_MSG_RE.match(lines[k])
                or header_run_len(k) >= 2):
            break
        k += 1
    if k >= n:
        return clean_body.strip(), ""               # single message / no older thread
    latest = "\n".join(lines[start:k]).strip()
    history = "\n".join(lines[k:]).strip()
    if not latest:                                  # latest was empty (pure wrapper) — don't split
        return clean_body.strip(), ""
    return latest, history


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
