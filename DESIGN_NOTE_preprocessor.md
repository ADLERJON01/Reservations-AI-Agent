# Design Note — Preprocessor (Agent #1), incl. preprocessor v2

**Status:** v2 changes implemented 2026-06-28 in `app/agents/preprocessor.py` +
`app/models/state.py` (EmailInput) and **are live** (they run on every email,
including the v1 path). Tests: `tests/test_preprocessor.py` (12 cases, green).

**Source of truth:** `app/agents/preprocessor.py` · `app/models/state.py`
(`EmailInput`). Consumed by the Classifier (#2) and persisted to the `emails` table.

---

## 1. Role and boundaries (unchanged)
Deterministic, no LLM. Parses one raw `.txt` email thread into a cleaned `EmailInput`
and derives the locked `input_metadata` snapshot. By design it does **not** strip
forwarding wrappers (forwarding-invariance is the Classifier prompt's job), does
**not** extract booking fields (that's #2), and retains anonymized `MASKED_*` tokens
verbatim.

## 2. Why v2 (the motivation)
Dataset analysis showed the corpus is dominated by **forwarded, multilingual, noisy**
emails: long tracking/redirect URLs, legal/GDPR/confidentiality blocks, marketing and
social-media footers, and deep quoted threads. Two concrete problems followed for a
local 3B with a 6,000-char body budget:
1. **Noise dilution + budget waste** — boilerplate and giant tracking URLs consumed
   the character budget and diluted the model's attention, pushing the *actual* content
   past truncation (one thread: 13.1k → 8.1k chars after cleaning; a stop-sales email:
   5.6k → 2.1k).
2. **Thread-closure misclassification** — the model classified on the *bulk* of a
   quoted thread and missed that the **latest** message was a closure ("Brilliant,
   thank you"). This was the single worst category failure mode in the v2.0 eval
   (`thread_closure` recall 0.20).

So preprocessing was treated as a **core reliability component**, not cosmetic cleanup,
and was kept regardless of the taxonomy outcome.

## 3. The three v2 changes (what + why)

### 3.1 Strip tracking/redirect URLs
Remove angle-bracket link targets (`text<https://…>`, `<mailto:…>` — the visible text
precedes them, so the URL is never content), known tracking/CDN domains
(`awstrack.me`, `exclaimer.net`, `pstmrk.it`, `googleapis.com`, Salesforce image
servlets, `mailchi.mp`), and any remaining bare URL ≥ 90 chars. **Why:** these carry
zero classification signal and are the single largest source of wasted budget.

### 3.2 Strip legal/marketing/social boilerplate — **keep signatures**
Drop GDPR/confidentiality blocks (from a recognizable opener to the next thread
separator), marketing footers ("#TheTimeofYourLife", "Travelife", "think before
printing"), and social-media rows. **Why keep signatures:** the name/role/company line
("Grape Escapes Ltd | Travel Consultant", "OSTTOUR s.r.o. — Cestovná kancelária") is
**the single best cue for `sender_type`** and partner identity — exactly what we relied
on while hand-labeling. Stripping it would actively hurt classification. This was a
deliberate scope correction (an earlier proposal to "strip signatures" was rejected for
this reason). Verified: "Grape Escapes Ltd" survives; "CONFIDENTIAL…" is removed.

### 3.3 `latest_message` segmentation
Split the most-recent message from the older quoted thread (new `EmailInput` fields
`latest_message` / `thread_history`). The classifier user prompt (v2/v1.1) presents
`[MOST RECENT MESSAGE]` first and `[EARLIER THREAD — context]` after. **Why:** anchors
the model on the message that should drive classification (closures, withdrawals).
**Conservative by design:** falls back to the whole body when no thread is detected, so
content is never lost; labels are kept **soft** (no "classify ONLY by this") so
wrapper-forwarded emails — where the top segment is just a signature and the real
request sits below — don't regress.

## 4. Measured impact
- `thread_closure` recall **0.20 → 0.60** (v2.0 → v2.1), with the cleaning + latest-
  message split as the main drivers.
- `sender_type` **+12** in v2.1 (cleaner input) — *note:* this gain did **not** carry
  into the v1.1 run (sender_type fell to 57%), an open anomaly to investigate.
- Trade-off observed: the latest-message emphasis can **over-trigger closures** on
  emails ending in a polite "thanks" (v2.1 false closures on 155/325/335). Mitigated by
  soft labels + the prompt rule "a polite closing at the end of a *real* request is not
  a closure"; not fully eliminated.

## 5. Important consequences (honesty / threats to validity)
- **These changes are live and affect the v1 path too** — the live classifier reads
  `body_clean`, which is now cleaner. This was implemented in service of the v2/v1.1
  experiment but touches shared code.
- **The v1 "79.6%" baseline predates this change** (it was measured on the old
  preprocessor). So comparisons against 79.6% bundle the preprocessor improvement;
  state this whenever citing the v1→v1.1 delta.
- `num_ctx` was raised to 8192 (`app/config.py`, `app/llm/ollama_native.py`) so a long
  body + a longer prompt cannot silently truncate from the front. Also live.

## 6. Future work
- Re-baseline v1 on the new preprocessor for a perfectly clean v1→v1.1 comparison.
- Investigate the `sender_type` regression in v1.1.
- Consider preprocessor-level message-boundary parsing to further improve
  closure/wrapper handling (the prompt alone plateaus on a 3B).

### Change log
- **2026-06-28** — created. Documents preprocessor v2 (URL/boilerplate stripping +
  `latest_message` segmentation) and its live-pipeline consequences.