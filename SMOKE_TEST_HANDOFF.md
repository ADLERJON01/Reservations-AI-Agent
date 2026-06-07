# Sandbox Handoff — Local Model Selection Smoke Test (Task #1)

Pick-up doc for a fresh Claude Code session continuing this work. Read this
first, then [`SMOKE_DECISION.md`](SMOKE_DECISION.md) for the full reasoning.
Everything here lives in `/Sandbox/` and is **exploratory** — no production code.

---

## 1. What this was

A first-cut screen of three local LLMs (via Ollama) to find which can reliably
emit the locked classification + extraction JSON contract, fast enough on an
M1. Goal was to **eliminate broken/too-slow models**, not to pick the final one.

**Outcome:**

| Decision | Model | Headline |
|---|---|---|
| **Primary** | `ministral-3:3b` | 100% schema-valid · 83% category accuracy · ~29s median |
| **Fallback** | `llama3.2:3b` | 100% schema-valid · 40% accuracy · ~17s median (fast but weak classifier) |
| **Eliminated** | `qwen3.5:4b` | 0% schema-valid (never emits the full nested contract) |

Full numbers, per-email breakdown, and per-model failure analysis are in
[`SMOKE_DECISION.md`](SMOKE_DECISION.md). Raw per-call data in
[`smoke_results.json`](smoke_results.json).

---

## 2. Files in `/Sandbox/`

| File | What it is |
|---|---|
| `SMOKE_TEST_BRIEF.md` | The original task brief (input, not generated here). |
| `smoke_sample.json` | **Frozen** 10-email stratified sample + hand-labelled `expected_category` and the reason for each pick. The reproducibility anchor. |
| `schema_model.py` | Pydantic model (`EmailExtraction`) derived from `llm_output_schema.json` + `taxonomy.json` v1.0.0. Enums are `Literal[...]`, so out-of-vocabulary values fail validation. This is the contract gate. |
| `run_smoke.py` | The comparison harness. Runs the models over the sample and scores validity / category accuracy / latency / repeatability. |
| `smoke_results.json` | Raw results (`meta` + per-call `runs` + `summary`) from the last run. |
| `SMOKE_DECISION.md` | The decision note (primary/fallback/eliminated + justification + parked items). |
| `SMOKE_TEST_HANDOFF.md` | This file. |
| `.venv/` | Python venv with the deps (see below). Not checked in anywhere; recreate if missing. |

---

## 3. Environment & how to reproduce

**Prerequisites (state as of 2026-05-31):**
- **Ollama 0.24.0** running locally on `http://localhost:11434`.
- Three models pulled: `qwen3.5:4b`, `llama3.2:3b`, `ministral-3:3b`.
  - `llama3.2:3b` and `llama3.2:latest` are the **same model** (digest
    `a80c4f17acd5`, 3.2B params, Q4_K_M). We standardised on the explicit
    `:3b` tag.
  - Pull anything missing with `ollama pull <tag>`.
- **Python venv** at `/Sandbox/.venv` with: `instructor 1.15.1`, `litellm 1.86.2`,
  `openai 2.38.0`, `pydantic 2.13.4`, `requests 2.34.2`.
  System `python3` has only `pydantic` — **use the venv**, not system python.

**Recreate the venv if needed:**
```bash
cd /Sandbox
python3 -m venv .venv
./.venv/bin/pip install instructor litellm pydantic requests
```

**Run the smoke test:**
```bash
cd /Sandbox
./.venv/bin/python run_smoke.py                      # defaults: 3 repeats, temp 0.4, all 3 models
./.venv/bin/python run_smoke.py --models ministral-3:3b --repeats 5
```
A full run (3 models × 10 emails × 3 repeats = 90 calls) takes ~35–45 min on
M1; most of that is qwen burning the retry triple on every failure. Results
overwrite `smoke_results.json` and a summary table prints at the end.

**Inputs it reads (READ-ONLY, do not modify):**
- `../Implementation/inputs/cleaned_dataset/emails_extracted_new.jsonl` (378 emails)
- `../Implementation/outputs/llm_output_schema.json`, `taxonomy.json` (v1.0.0)

---

## 4. Key decisions & gotchas (don't re-learn these the hard way)

1. **The brief's proposed stack (LiteLLM + Instructor) was abandoned.**
   - It could not disable "thinking" on the reasoning models (`qwen3.5`,
     `ministral-3`): a single call took **200–400s** of reasoning traces.
   - Its default **tool-calling** mode broke the small models.
   - We switched to **Ollama's native structured-output API** — raw
     `POST /api/chat` with `think:false` and `format=<EmailExtraction schema>` —
     still validated by the same Pydantic model. This is the path that works on
     Ollama and is what `run_smoke.py` uses now. (`instructor`/`litellm` are
     still installed in the venv but unused by the current runner.)
   - **Open question (parked):** can the Instructor route be made to work with
     `think=False` + JSON mode, if that stack is required downstream?

2. **Use the explicit Ollama tags.** `llama3.2:3b` (not `:latest` in docs/code,
   even though they're identical) to avoid ambiguity.

3. **`think:false` is mandatory** for the reasoning models or latency explodes.

4. **qwen's failure is structural, not semantic.** It emits a *flat, partial*
   object (just `predicted_category` + evidence + reasoning), drops the required
   facets and the whole `extraction` block, and sometimes wraps output in
   ` ```json ` fences. Its category *values* were often topically right — it just
   won't honor the nested schema. Cheap things to try before final judgement:
   (a) strip ``` fences before validating (would have rescued ~3 calls),
   (b) flatten/inline the schema `$defs`, (c) leave thinking on with a big token
   budget.

5. **Repeatability needs temp > 0 + per-repeat seeds.** At temp 0 every repeat is
   identical and repeatability is trivially 100%. The harness uses temp 0.4 with
   `seed = 100*(repeat+1)`, so re-runs are deterministic *per seed* but vary
   across repeats — that's intentional.

6. **Latency is output-bound.** Booking-notification emails (heavy extraction)
   cost 2–3× more than short emails on every model. Plan throughput accordingly.

---

## 5. ⚠️ The labels problem (read before "build the eval set")

The next phase will want a properly-sized labelled evaluation set. **Usable gold
labels in the current taxonomy do not really exist yet.** Specifically:
- The dataset (`emails_extracted_new.jsonl`) has **no category field** — it's raw
  email fields only. That's why the smoke sample was **hand-labelled**.
- `../Implementation/outputs/manual_label_validated.csv` covers only **74 of 378**
  emails, uses an **older 6-category taxonomy** in `proposed_category`
  (`partner_or_agency_communication`, `automated_reservation_notification`, …),
  and its validated `my_category` column is **empty**.

So "expand to a sized labelled set" is really **"produce gold labels in the
v1.0.0 7-category taxonomy first"** — a meaningfully larger task than it sounds.
`../Implementation/outputs/borderline_cases.md` is the best existing guide to the
tricky calls and was used to validate the smoke-sample picks.

---

## 6. Suggested next steps (all parked from the brief)

1. **Produce gold labels** in the v1.0.0 taxonomy for a sized sample (see §5).
2. **Prompt engineering A/B** on the frozen sample: add few-shot / contrastive
   examples. Expected to lift `llama3.2:3b` a lot (its errors are systematic —
   it over-triggers `system_or_channel_delivery_exception`) and fix
   `ministral-3:3b`'s two borderline misses (`email_4`, `email_334`). Watch the
   latency cost of a heavier prompt. *(Designed but NOT run — would overfit to 10
   emails; needs the real eval set to mean anything.)*
3. **Measure extraction field-level accuracy** — this cut only eyeballed the
   *category*, not the dozens of extraction fields.
4. **Revisit qwen** with the cheap fixes in §4.4 before writing it off for good.
5. **Production scaffolding** (`/Implementation/`, Task #5) — only after the model
   decision is finalised. **Not** started here.

---

*Generated 2026-05-31. This is a first cut on a 10-email eyeball sample — a
screen to eliminate broken models, not a final evaluation.*
