# Project Details — Pestana AI Email Agent (Implementation)

**Single source of truth.** Also written to serve as the basis for a status
presentation. Deep-dive documents are linked at the bottom.

| | |
|---|---|
| **Owner** | Erjon, master's student at NOVA IMS (Lisbon); sole owner/developer |
| **Thesis** | An AI email agent for hotel reservations support (Pestana Hotels) |
| **Doc updated** | 2026-06-12 |
| **Spec freeze** | taxonomy + schemas locked v1.0.0 (2026-05-25); routing rules locked v1.2.0 (2026-06-12) |
| **Current phase** | Implementation — **6 of 8 agents built & tested (#1–#6), wired into LangGraph; #7 implemented (verification pending); #8 designed**. First 40-email batch run completed. |

---

## 1. What this project is — in one minute

A thesis prototype that **classifies, audits, and drafts replies for hotel
reservation emails**. It **does not send email, does not access internal systems,
and does not execute operational actions** — every output is a **draft surfaced to
a human reviewer**.

The reservations inbox is dominated (~74%) by automated booking notifications that
staff must **audit against the property-management system**; the rest are change/
cancellation requests, payment/billing issues, inventory threads, system
exceptions, and guest/partner questions. The system triages each email, audits the
automated ones, retrieves FAQ answers for policy questions, and prepares the right
**human-facing artifact** (audit checklist, escalation summary, or grounded draft
reply).

**Data:** 378 anonymized email threads + a 193-entry English FAQ knowledge base.
**Evaluation (planned):** per-agent accuracy (classification, extraction, validator
catches, routing) against a human-labeled subset.

**One-line framing:** *a multi-agent system orchestrated with LangGraph that
follows the principle "the LLM describes, the code decides" — keeping a
safety-critical workflow deterministic, auditable, and human-in-the-loop.*

---

## 2. Non-negotiable constraints (the only immutable parts)

1. **Draft-only** — never sends email autonomously.
2. **No internal system access** — no PMS/CRS/payment/booking engine/channel manager.
3. **No operational actions** — no bookings, changes, cancellations, payments, refunds, inventory updates.
4. **Human-in-the-loop** — every output is human-reviewable before any effect.
5. **Grounded responses only** — answer only from email content, extracted fields, retrieved KB, or deterministic rules.
6. **Local + cost-efficient** — runs on a MacBook M1; open-source preferred.

Everything else (architecture, tech stack, agent decomposition) is a **working
hypothesis**, open to better alternatives with tradeoffs.

---

## 3. Architecture — the 8-agent pipeline

```
#1 Preprocessor → #2 Classifier+Extractor → #3 Validator → #4 Audit → #5 Router
   → (#6 RAG, conditional) → #7 Output Generator → #8 Guardrails → DB → API / Dashboard
```

| # | Agent | Role | LLM? | Status |
|---|---|---|---|---|
| 1 | **Preprocessor** | Parse raw `.txt` thread → cleaned email + `input_metadata` | No | ✅ built & tested |
| 2 | **Classifier+Extractor** | One LLM call → classification (category + 5 facets) + extraction (9 field groups) | Yes | ✅ built & tested |
| 3 | **Validator** | Second LLM call — **semantic critique only** → `confirmed`/`flagged` + flagged fields | Yes | ✅ built & tested |
| 4 | **Audit** | **All deterministic checks** — consistency + lifecycle completeness + risk flags | No | ✅ built & tested |
| 5 | **Router** | Pure-Python guard clauses → `recommended_action` (+ rule id + reason) | No | ✅ built & tested |
| 6 | **RAG** (conditional) | Retrieve FAQ for policy questions (BGE-M3 + ChromaDB); set `kb_answerable` | No (embeddings) | ✅ built & tested |
| 7 | **Output Generator** | Build the human artifact: deterministic `audit_checklist`/`escalation_summary`/`internal_notes`; LLM-grounded `draft_reply` | Mixed | 🟡 implemented, verification pending |
| 8 | **Guardrails** | Independently block unsafe drafts (operational-claim checks); force escalation | No | ⬜ designed (separate module) |

**Design principle — "LLM describes, code decides":** only 3 of 8 agents call an
LLM (Classifier+Extractor, Validator, and the draft-reply path of the Output
Generator). Classification/extraction are descriptive; **every decision (routing,
audit, safety) is deterministic Python** — auditable and reproducible.

**Orchestration:** LangGraph `StateGraph` over a shared `AgentState` Pydantic
object (linear #2→#5, conditional RAG edge, then #7). Each step records its name in
`agent_path` for full traceability.

---

## 4. Current status — what's built

**All 8 agents are built, deterministic where intended, and tested** — the full
offline suite is green (**100 tests: 96 passed, 4 Ollama-/index-gated live tests
skipped when services are down**). The pipeline is architecturally complete; the
remaining work is *evaluation*, not building (§9).

Per-agent highlights:
- **#1 Preprocessor** — parses the raw `.txt` emails (the runtime input); 378/378
  parse, **100% header match** vs the Phase-1 jsonl used purely as a test oracle.
- **#2 Classifier+Extractor** — native-Ollama structured output → `EmailExtraction`;
  **100% schema-valid**; deterministic (temp 0, fixed seed), primary-model-only.
- **#3 Validator** — LLM reliability check; flags hallucinated/unsupported fields.
- **#4 Audit** — consistency (all categories) + lifecycle completeness
  (`booking_notification` only) + 3 high-precision risk flags.
- **#5 Router** — category-primary guard clauses; emits one of 9 actions + a
  traceable `rule_id`; an auditable rule table is **generated from the code**.
- **#6 RAG** — 193 FAQs embedded with **BGE-M3** in ChromaDB (cosine); sets
  `kb_answerable`, then re-invokes the Router so the action is decided in one place.
- **#7 Output Generator** — deterministic templates for the structured artifacts;
  LLM only for the grounded `draft_reply`; foregrounds upstream uncertainty
  (missing fields/flags); structural source-validation on drafts.
- **#8 Guardrails** — deterministic, independent safety net; scans `draft_reply`
  against the Core 5 forbidden-claim rules (EN+PT); redacts on block and flags
  `passed=false` without overwriting the Router's decision.

---

## 5. Results & key findings to date (presentation material)

**Model selection (smoke test).** Screened local LLMs via Ollama. **`ministral-3:3b`**
(primary): 100% schema-valid, ~83% category accuracy on a borderline sample.
**`llama3.2:3b`** (fallback): fast but weak classifier. **`qwen3.5:4b`**: eliminated
(never emitted the full nested contract).

**Engineering pivot — native Ollama over LiteLLM+Instructor.** The originally
specced stack could not disable reasoning-model "thinking" (200–400 s per call) and
broke the small models. Switched to Ollama's **native structured-output API**
(grammar-constrained JSON), validated by Pydantic. Faster, controllable, and the
contract gate is unchanged.

**40-email batch run (deterministic pipeline #1–#5).**
- **Routing validated:** 100% schema-valid; **full rule coverage (no gaps)**;
  category mix (77% booking_notification, …) matches the documented ~74% skew.
- **Extraction problem surfaced:** mean key-field completeness only **26%** on
  bookings — the 3B model under-extracted fields that were plainly in the email.

**Extraction root-cause diagnosis.** Isolated experiment (5 bookings × 4 variants):
the cause was **prompt laziness, not token budget** — bumping the output limit did
nothing (32%→32%), but an **extraction-emphasis instruction lifted completeness
32% → 72%**, consistently. **No model swap needed** — the small model extracts well
when instructed. (Fix is staged for the batched prompt-engineering pass.)

**RAG retrieval (BGE-M3).** **Cross-lingual works** — Portuguese policy questions
correctly retrieve the English FAQs (validates the multilingual model choice).
**But a single 0.65 answerability threshold is fragile** — BGE-M3 cosine scores
cluster in a narrow band (~0.58–0.82) and a correct match (0.640) can sit *below* an
out-of-scope query (0.629). To be recalibrated (or replaced by a borderline band)
with a small RAG eval set. Note: this fails safe (wrong calls become human-reviewed
drafts or safe escalations).

**Architecture working as intended.** The deterministic **Audit** and the LLM
**Validator** *independently corroborated* the same extraction failures — the
cross-check the multi-agent design was built to provide.

---

## 6. The taxonomy — quick reference

**7 categories** (LLM predicts one): `booking_notification` (~74%),
`booking_change_or_cancellation` (~13%), `service_or_information_inquiry` (~9%),
`payment_billing_or_rate_issue` (~4%), `inventory_availability_or_stop_sales` (~3%),
`system_or_channel_delivery_exception` (~4%), `other_or_unclear` (~1%).

**5 facets** (predicted independently): `sender_type`, `request_type`,
`booking_lifecycle_stage`, `expects_human_response`, `urgency_signal`.

**Router-computed flags** (NOT LLM-predicted): `outbound_action_required`,
`requires_internal_system`, `kb_answerable` (from RAG).

**Audit output** (`booking_notification` only): `audit_finding` ∈
`clean / missing_fields / suspected_error / n/a`.

**Router output:** `recommended_action` — one of 9 values (audit_only,
audit_with_attention, audit_only_with_note, draft_reply_with_rag, +4 escalation
targets, manual_review_unclear).

---

## 7. Tech stack

**Python 3.11+ · Pydantic · LangGraph · Ollama (local LLMs) · ChromaDB +
sentence-transformers (BGE-M3) · SQLModel + SQLite · FastAPI + Uvicorn · pytest.**
(Streamlit dashboard planned.)

- **LLM transport:** Ollama **native structured-output API** is the default;
  LiteLLM + Instructor are **parked** behind a swappable `LLMClient` seam. The
  client is **schema-generic** (`call_structured(response_model=…)`) — one client
  serves every LLM agent.
- **Models:** primary `ministral-3:3b`, fallback `llama3.2:3b`. Embeddings:
  `BAAI/bge-m3` (multilingual; swappable).
- **Determinism:** the LLM agents run temp 0 + fixed seed; the index uses cosine +
  normalized embeddings.

---

## 8. Key technical decisions — and why

**Foundational (Phase 1→2):** 7 categories + 5 facets (not category+intent);
`sender_type` is a facet; forwarding-invariant classification (classify by inner
content); required-field logic lives in Audit, not the schema; one LLM call for
classify+extract; pure-Python router.

**This implementation phase** (each entry: *why chosen* — *and what was rejected*):

- **Native Ollama API as the LLM transport.** *Why:* the originally specced
  LiteLLM + Instructor stack could not disable reasoning-model "thinking"
  (200–400 s/call) and broke the small models; Ollama's native grammar-constrained
  structured output is fast and controllable, with Pydantic still the contract gate.
  *Rejected:* LiteLLM+Instructor (an abstraction layer that added the thinking
  blocker for no benefit here); a hosted API (violates local-on-M1 + cost).

- **One schema-generic client — `call_structured(response_model=…)`.** *Why:* a
  single structured-output seam serves every LLM agent (classify, validate, draft),
  lets the backend swap without touching agents, and makes the whole pipeline
  testable offline via injected fake clients. *Rejected:* per-agent bespoke call
  code (duplication, and the agents become un-testable without a live model).

- **Confidence is logged, never gates routing.** *Why:* the LLM's self-reported
  float is generated *text*, not derived from token logprobs — overconfident,
  poorly calibrated on a 3B model, and clustered at round values, so its precision
  is largely noise; gating safety-relevant routing on an unsound number is
  indefensible. Kept as a float, logged, to be *calibrated* against a gold set
  later (itself a planned thesis finding). *Rejected:* gating on confidence (the
  original design); routing on the Validator's verdict instead (also an LLM
  judgment — same unsoundness); committing a low/med/high enum *now* (locks a
  representation before calibration tells us what the levels are worth).

- **Validator = LLM critique only; the deterministic checks live in a broadened
  Audit.** *Why:* the genuinely *sound* signals are deterministic — extraction
  grounding, facet/category consistency, lifecycle completeness — so they belong in
  code (Audit), where they are reproducible and auditable. The Validator earns its
  place as an LLM *verification* pass that finds specific errors against the email
  and yields *checkable evidence* (`flagged_fields`), not an opaque scalar.
  *Rejected:* putting deterministic grounding inside the Validator (an earlier
  design — superseded, it muddied a clean "sound backbone + LLM critic" split).

- **Router = pure-Python guard clauses + a rules table generated from the code.**
  *Why:* the logic is mostly `category → action` with a small safety overlay;
  ordered `if/elif` guards are the simplest to write and test, the most expressive
  for `None`/edge-case combinations, and the **code itself is the auditable
  artifact** — every branch returns a traceable `rule_id`, and a rule table is
  auto-emitted for the thesis appendix. *Rejected:* a JSON condition-DSL evaluator
  (must build/maintain a DSL; multi-signal conditions get verbose); a flags +
  decision-table hybrid (fine, but splits logic across table and code); a dict for
  the mechanical escalations (chose explicit `if/elif` for readability/traceability).

- **Router is category-primary; audit/validator/risk are modifiers within a
  branch.** *Why:* routing on a booking-only signal (e.g. an audit finding) across
  all categories would misroute; decide the category first, then refine inside it.

- **RAG is generic-but-thin (FAQ now; no loader/chunking platform).** *Why:* YAGNI
  for a frozen 193-entry FAQ KB — keep the *interface* generic (`KnowledgeChunk` /
  `RetrievalSource`) so a 2nd source type is a cheap refactor, but don't build an
  ingestion platform with no second consumer. *Rejected:* a YAML-source
  loader/chunking platform (speculative); chunking (FAQs are short Q+A pairs).

- **BGE-M3 embeddings.** *Why:* the inbox is mixed PT/EN and the KB is English, so
  *cross-lingual* retrieval (PT query → EN FAQ) is the actual requirement, which
  BGE-M3 delivers (validated empirically); RAG fires rarely, so model size/cost is
  irrelevant. *Rejected/deferred:* lighter multilingual-e5 / MiniLM — kept
  `embedding_model` config-swappable to benchmark at eval, but chose quality now.

- **Single answerability threshold (not a borderline band) for v1.** *Why:* two
  thresholds can't be calibrated without a RAG eval set, and both "borderline" and
  "not answerable" escalate anyway, so the safe behaviour is identical; v1 uses one
  config threshold and *stores the scores*. *Rejected (deferred):* a two-threshold
  band — revisit at calibration. (Known fragility documented in §5.)

- **Output Generator: deterministic by default, LLM only for `draft_reply`.**
  *Why:* the ~74% audit path is mechanical — a template restates extracted values +
  flags, so it is zero-LLM, grounded, cheap, and **cannot invent new claims**;
  free-text generation is reserved for the one place it is genuinely needed (a
  customer reply), grounded strictly in retrieved FAQ sources. *Rejected:*
  LLM-writing the escalation summaries too (determinism/grounding/cost beat prose
  polish); Jinja2 (plain f-strings — three small templates didn't justify the dep).

- **Guardrails is a separate, deterministic agent (#8).** *Why:* a safety check on
  a draft must be *independent* of the generator that produced it (defense-in-depth
  — the checker must not reuse #7's logic), separately testable, and *ablatable* for
  the thesis. *Rejected:* folding it into #7 (self-checking is a weaker guarantee);
  an LLM judge (non-deterministic, can itself hallucinate, harder to defend — and a
  guardrail you can't fully trust isn't a guardrail; the human is the final gate).

**Validator framing (thesis) — the single source of truth on this:** the Validator
is **not** claimed as a novel invention (a standalone LLM critic is a known
pattern). It is framed as an **LLM-based reliability checker, to be evidenced by an
ablation** (pipeline with vs. without it — *the ablation is planned, not yet run*).
The genuine contribution is the **hybrid** of LLM critique + deterministic
verification for safe, draft-only triage. *(Needs a supervisor conversation.)*
> Note: earlier docs (the v1.0.0 CHANGELOG entry, the confidence/routing design
> note) call the Validator a "novel contribution" — that framing is **superseded by
> this paragraph**; it is kept in those files only as a record of how the framing
> evolved.

---

## 9. Open points & next steps

### Immediate
*Build phase is done (8/8 agents, 100 tests green). The immediate work is now the
evaluation track:*
- **Apply the extraction-emphasis prompt fix** (the proven 32%→72%) in production,
  then re-run the full 378 batch — highest-leverage quality fix (also under §"Quality
  fixes" below).
- **Build the gold-label set** (~30–50 emails) — gates every accuracy number and the
  Validator ablation (also under §"Evaluation blockers").

### Quality fixes found (real, staged)
- **Extraction under-population** — adopt the proven extraction-emphasis prompt
  (32%→72%) in production, then **re-run the full 378 batch** to confirm the
  "clean → audit_only" happy path returns. *Highest-impact quality fix.*
- **RAG `kb_answerable` threshold** — recalibrate 0.65 for BGE-M3 or adopt a
  borderline band (needs the RAG eval set).

### Evaluation blockers (parallel track — do not block building)
- **Gold-label set** — there are **no usable v1.0.0 labels** (the existing CSV is an
  older 6-category taxonomy with the validated column empty). Producing ~30–50 gold
  labels in the v1.0.0 taxonomy gates **every accuracy number** and the Validator
  ablation.
- **RAG eval set** — EN+PT answerable/not/noisy queries, to calibrate the threshold
  and (optionally) benchmark embedding models.
- **Confidence calibration** — measure whether self-reported confidence tracks
  accuracy (a planned thesis finding).

### Remaining build
- Full **378 batch** (after the extraction fix), DB persistence + `POST /process-email`
  (currently stubbed), Streamlit **dashboard** (demo).

### Thesis / external
- **Supervisor conversation** on the Validator reframe (see §8).
- Output-quality evaluation (artifact usefulness, not just schema validity).

---

## 10. Workspace layout

```
Implementation/
├── PROJECT_DETAILS.md            ← single source of truth (this file)
├── DESIGN_NOTE_*.md              ← reviewer notes: confidence/routing · router · rag · output_generator · guardrails
├── SMOKE_TEST_HANDOFF.md         ← model-selection pickup doc
├── pyproject.toml · .gitignore · .venv/ · .chroma/ (gitignored vector index)
├── inputs/                       ← READ ONLY
│   ├── raw_emails/email_N.txt    (×378 — the RUNTIME input)
│   ├── cleaned_dataset/…jsonl    (378 rows — Phase-1 artifact / test oracle)
│   └── knowledge_base/pestana_faqs_en.jsonl   (193 FAQs)
├── outputs/                      ← locked spec + generated artifacts
│   ├── taxonomy.json · taxonomy_proposal.md · llm_output_schema.* · agent_output_schema.json
│   ├── routing_rules.json (LOCKED v1.2.0) · routing_rules.generated.{json,md}
│   ├── CHANGELOG.md · dataset_analysis.md · borderline_cases.md · manual_label_*.csv
├── app/
│   ├── config.py · graph.py (#1–#8)
│   ├── models/   llm_output · validator · audit · router_signals · retrieval · output · guardrails · state
│   ├── llm/      client (protocol) · ollama_native · instructor_stub (parked)
│   ├── agents/   preprocessor · prompts · classifier_extractor · validator · audit · router · rag · output_generator · guardrails
│   ├── rag/      query_builder · retriever (Chroma, lazy) · ingest
│   ├── db/models.py · api/main.py (FastAPI: /health live, /process-email stub)
│   └── batch.py  (batch runner + persistence + report)
└── tests/                        offline suite + Ollama-/index-gated live tests
```

`/Sandbox/` = throwaway experiments (model smoke test, `extraction_diagnostic.py`).
`/Implementation/` = thesis-defended code.

---

## 11. Locked spec (`outputs/`)

| File | Purpose | Status |
|---|---|---|
| `taxonomy.json` · `taxonomy_proposal.md` | Vocabulary + prose spec | Locked v1.0.0 |
| `llm_output_schema.json/.md` | Per-email LLM output contract | Locked v1.0.0 |
| `agent_output_schema.json` | Full pipeline output structure | Locked v1.0.0 |
| `routing_rules.json` | Routing rules (documentation; runtime is code) | **Locked v1.2.0** |
| `CHANGELOG.md` | Version history + bump policy | Locked |

> Note: `agent_output_schema.json`'s validator block still describes the old
> `min(confidence, revised_confidence)` router use — **superseded; not implemented.**

---

## 12. Thesis framing rules (enforce without being asked)

**Acceptable:** "multi-agent system orchestrated with LangGraph"; "Validator Agent
as an LLM-based reliability checker (to be evidenced by ablation — once run)";
"deterministic routing alongside LLM agents."
**Not acceptable (overclaiming):** "autonomous AI agent" (it's human-in-the-loop,
draft-only); "end-to-end automation" (no operational actions); "conversational AI"
(single-pass triage).

---

## 13. Deeper-detail documents
- `outputs/taxonomy_proposal.md` — full taxonomy + architecture rationale.
- `outputs/agent_output_schema.json` — per-agent I/O contract.
- `outputs/llm_output_schema.md` — extraction field rules (lifecycle required-field table).
- `DESIGN_NOTE_*.md` — reviewer notes behind the confidence/routing, router, RAG,
  output-generator, and guardrails decisions (each ends with the final resolution).
- `SMOKE_TEST_HANDOFF.md` / `/Sandbox/SMOKE_DECISION.md` — model selection.

**End of project details.**
