"""Preprocessor (#1): unit tests on known raw emails + an oracle test that
validates header parsing against the Phase 1 jsonl (which was derived from the
same .txt files). The jsonl is used ONLY as a test oracle, never at runtime.
"""
import json

import pytest

from app.agents.preprocessor import (
    clean_body,
    estimate_thread_length,
    parse_date,
    preprocess,
    to_input_metadata,
)
from app.config import get_settings
from app.models.state import InputMetadata

RAW_DIR = get_settings().inputs_dir / "raw_emails"
DATASET = get_settings().dataset_path


# --- unit: email_1 (direct channel email, no forward) ---
def test_email_1_parses_headers_and_cleans_body():
    email = preprocess(RAW_DIR / "email_1.txt")
    assert email.email_id == "email_1"
    assert email.source_file == "email_1.txt"
    assert email.subject.startswith("Booking.com Booking for # 6310459722")
    assert email.from_raw == "Trade <MASKED_EMAIL_851d9c9d5e>"
    assert email.date_parsed == "2026-02-19T15:34:15+00:00"
    # cleaning: caution banner + logo placeholder gone, MASKED_ tokens retained
    assert "CAUTION: EXTERNAL EMAIL" not in email.body_clean
    assert "[channel manager logo]" not in email.body_clean
    assert "MASKED_NAME_309cba58cd" in email.body_clean
    assert "New Reservation" in email.body_clean


def test_email_1_is_single_segment():
    email = preprocess(RAW_DIR / "email_1.txt")
    assert estimate_thread_length(email.body_raw) == 1


# --- unit: email_18 (one Portuguese forward block) ---
def test_email_18_detects_forwarded_segment():
    email = preprocess(RAW_DIR / "email_18.txt")
    assert estimate_thread_length(email.body_raw) == 2


# --- input_metadata contract ---
def test_input_metadata_has_exactly_locked_keys():
    email = preprocess(RAW_DIR / "email_1.txt")
    meta = to_input_metadata(email)
    assert isinstance(meta, InputMetadata)
    locked = {
        "source_file", "subject", "from_raw", "to_raw", "cc_raw",
        "date_raw", "date_parsed", "thread_length_estimate", "body_clean_length",
    }
    assert set(meta.model_dump().keys()) == locked
    assert meta.body_clean_length == len(email.body_clean)
    assert meta.thread_length_estimate >= 1


# --- helper edge cases ---
def test_parse_date_tolerant():
    assert parse_date("2026-02-19 15:34:15+00:00") == "2026-02-19T15:34:15+00:00"
    assert parse_date(None) is None
    assert parse_date("not a date") is None


def test_clean_body_empty():
    assert clean_body("") == ""


# --- oracle: parsed headers match the jsonl derived from the same .txt ---
def _load_oracle(limit: int = 60) -> list[dict]:
    rows = []
    with open(DATASET) as f:
        for line in f:
            rows.append(json.loads(line))
            if len(rows) >= limit:
                break
    return rows


@pytest.mark.skipif(not DATASET.exists(), reason="Phase 1 jsonl oracle not present")
def test_header_parsing_matches_jsonl_oracle():
    mismatches = []
    for row in _load_oracle():
        email = preprocess(RAW_DIR / row["source_file"])
        for field in ("subject", "from_raw", "to_raw", "cc_raw", "date_parsed"):
            if getattr(email, field) != row.get(field):
                mismatches.append((row["email_id"], field))
    assert not mismatches, f"header divergences vs oracle: {mismatches[:10]}"
