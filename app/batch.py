"""Batch runner — run the pipeline over a set of emails, persist results, and
print an aggregate report. Reused for the stratified subset now and the full
378 later.

Sampling note: with no v1.0.0 gold labels we cannot truly stratify by category,
so the default sample = the 10 category-labelled smoke emails (guarantees all 7
categories appear) + a deterministic systematic spread across the dataset.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from sqlmodel import Session

from app.config import get_settings
from app.db.models import AgentOutputRecord, EmailRecord, get_engine, init_db
from app.graph import run_pipeline
from app.models.state import AgentState

# Key "always-expected" extraction fields for a new/paid booking (llm_output_schema §6),
# used as an extraction-completeness proxy.
_KEY_BOOKING_FIELDS = [
    ("booking_identity", "source_channel"), ("booking_identity", "booking_reference"),
    ("booking_identity", "hotel_name"), ("guest", "guest_name"),
    ("stay", "check_in_date"), ("stay", "check_out_date"),
    ("financials", "total_amount"), ("financials", "currency"),
]


def select_sample(n: int = 40) -> list[str]:
    """Smoke's category-labelled emails + a systematic spread, deduped, up to n."""
    s = get_settings()
    smoke_path = s.project_root.parent / "Sandbox" / "smoke_sample.json"
    ids: list[str] = [item["email_id"] for item in json.loads(smoke_path.read_text())["sample"]]

    all_ids = [p.stem for p in sorted((s.inputs_dir / "raw_emails").glob("email_*.txt"),
                                      key=lambda p: int(p.stem.split("_")[1]))]
    step = max(1, len(all_ids) // max(1, (n - len(ids))))
    for i in range(0, len(all_ids), step):
        if len(ids) >= n:
            break
        if all_ids[i] not in ids:
            ids.append(all_ids[i])
    return ids[:n]


def _persist(state: AgentState, session: Session) -> None:
    e = state.email
    session.merge(EmailRecord(
        email_id=e.email_id, source_file=e.source_file, subject=e.subject,
        from_raw=e.from_raw, to_raw=e.to_raw, cc_raw=e.cc_raw,
        date_raw=e.date_raw, date_parsed=e.date_parsed,
        body_raw=e.body_raw, body_clean=e.body_clean))
    session.add(AgentOutputRecord(
        email_id=e.email_id, recommended_action=state.recommended_action,
        payload=state.model_dump(mode="json")))


def run_batch(ids: list[str], persist_db: bool = True) -> list[AgentState]:
    s = get_settings()
    raw = s.inputs_dir / "raw_emails"
    if persist_db:
        init_db()
    engine = get_engine() if persist_db else None

    results: list[AgentState] = []
    t0 = time.perf_counter()
    for i, eid in enumerate(ids, 1):
        st = run_pipeline(raw / f"{eid}.txt")
        results.append(st)
        if persist_db:
            with Session(engine) as session:
                _persist(st, session)
                session.commit()
        cat = st.llm_output.classification.predicted_category if st.llm_output else "INVALID"
        print(f"[{i}/{len(ids)}] {eid:<11} {cat:<38} -> {st.recommended_action} "
              f"({st.applied_rule_id})", flush=True)
    print(f"\nelapsed: {(time.perf_counter()-t0)/60:.1f} min", flush=True)
    _report(results)
    return results


def _report(rows: list[AgentState]) -> None:
    n = len(rows)
    invalid = sum(1 for r in rows if r.llm_output is None)
    cats = Counter(r.llm_output.classification.predicted_category if r.llm_output else "INVALID" for r in rows)
    actions = Counter(r.recommended_action for r in rows)
    rules = Counter(r.applied_rule_id for r in rows)
    findings = Counter(r.audit.audit_finding if r.audit else "?" for r in rows)
    vflag = sum(1 for r in rows if r.validator and r.validator.validation_result == "flagged")

    bookings = [r for r in rows if r.llm_output
                and r.llm_output.classification.predicted_category == "booking_notification"]

    def _completeness(r: AgentState) -> float:
        ext = r.llm_output.extraction
        present = sum(1 for grp, fld in _KEY_BOOKING_FIELDS
                      if getattr(getattr(ext, grp), fld) not in (None, ""))
        return present / len(_KEY_BOOKING_FIELDS)

    def _bar(counter: Counter) -> str:
        return "\n".join(f"    {k:<42} {v:>3}  ({100*v//n}%)" for k, v in counter.most_common())

    print(f"\n{'='*64}\nBATCH REPORT  (n={n})\n{'='*64}")
    print(f"schema-invalid (no llm_output): {invalid}/{n}")
    print(f"validator flagged:              {vflag}/{n}")
    print(f"\ncategory distribution:\n{_bar(cats)}")
    print(f"\nrecommended_action distribution:\n{_bar(actions)}")
    print(f"\naudit_finding distribution:\n{_bar(findings)}")
    print(f"\nrule_id distribution:\n{_bar(rules)}")
    if bookings:
        comp = sum(_completeness(r) for r in bookings) / len(bookings)
        miss = sum(1 for r in bookings if r.audit and r.audit.audit_finding == "missing_fields")
        print(f"\nbooking_notification extraction quality ({len(bookings)} bookings):")
        print(f"    mean key-field completeness: {comp:.0%}")
        print(f"    flagged missing_fields:      {miss}/{len(bookings)}")
    # coverage red flags
    surprises = {rid: c for rid, c in rules.items() if rid in {"R024_BN_OTHER", "R999_FALLBACK"}}
    print(f"\ncoverage check (should be empty): {surprises or 'OK — no R024/R999 fired'}")


def _ollama_up() -> bool:
    s = get_settings()
    try:
        return requests.get(f"{s.ollama_base_url}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    if not _ollama_up():
        sys.exit("Ollama not reachable at " + get_settings().ollama_base_url)
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    run_batch(select_sample(count))
