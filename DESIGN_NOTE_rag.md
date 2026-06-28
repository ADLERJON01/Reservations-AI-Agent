# Design Note — RAG Agent (#6) Spec & Dev Plan

**Purpose:** give an **independent reviewer** enough context to critique the spec
and development plan for the RAG agent before it's built. Self-contained — you
should not need the rest of the repo. Decisions already made are **DECIDED**;
points we want a view on are in §8.

Date: 2026-06-07 · Project: Pestana AI Email Agent (master's thesis prototype).

> **v1.1 update (2026-06-28):** the RAG candidate gate changed. It was
> `category == service_or_information_inquiry AND request_type == policy_or_general_question`;
> it is now `category == service_or_information_inquiry AND inquiry_answer_source == kb_policy`
> (a new, more robust facet — see `DESIGN_NOTE_taxonomy.md` Part II). The RAG agent's
> answerable/borderline/not-answerable logic is unchanged. Note: under draft-only +
> human-in-the-loop, **false RAG candidates are accepted** (a wrong draft is discarded,
> never sent); the gate optimises draft usefulness, not safety-of-last-resort.

---

## 1. Project in one paragraph

A local, **draft-only, human-in-the-loop** prototype that classifies, audits, and
(later) drafts replies for hotel reservation emails. Never sends mail, never
touches internal systems, never executes operational actions. Runs on a MacBook
M1 via Ollama. Guiding principle: **"LLM describes, code decides."** The system
processes **378 anonymized emails**; the FAQ knowledge base has **193 English
entries**.

Pipeline (8 agents):
```
#1 Preprocessor → #2 Classifier+Extractor → #3 Validator → #4 Audit → #5 Router
   → (#6 RAG if applicable) → #7 Output Generator → #8 Guardrails → DB → API/Dashboard
```

## 2. What is already built & working

Agents **#1–#5 are built, tested (53 offline tests), and wired into LangGraph**
as a linear `StateGraph` over a shared `AgentState`. The Router (#5) is pure
Python (guard clauses), deterministic, and **locked at routing_rules v1.1.0**
(no confidence gating; deterministic Audit is the backbone; the Validator flag is
a contributing signal, not a gate). A 40-email batch validated routing coverage
(100% schema-valid, no rule gaps). LLM calls use Ollama's native structured-output
API (primary model `ministral-3:3b`), validated by Pydantic.

## 3. RAG's role & trigger (DECIDED)

Conditional agent, runs **only when the Router set `rag_required=true`** — i.e.
category `service_or_information_inquiry` AND request_type
`policy_or_general_question` (the Router's R030 "candidate" path, action
`draft_reply_with_rag`). RAG **retrieves from the FAQ KB and decides
`kb_answerable`**; it does **not** draft the reply (that's #7). **No LLM in RAG**
— embeddings + cosine similarity only. Deterministic given the index.

Note: policy questions are **rare** (0 of 40 in the batch; part of the ~9%
service-inquiry slice), so RAG fires infrequently — latency is not a hot path.

## 4. Knowledge base & ingestion (DECIDED)

- Source: `pestana_faqs_en.jsonl`, 193 entries, fields:
  `topic / subtopic / question / answer / source_url / language` (all `en`).
- **One ChromaDB document per FAQ** (no chunking — each FAQ is short).
- **Embed `question + " " + answer`**; store `topic/subtopic/question/answer/
  source_url` as metadata. Stable `source_id = faq_{index:03d}`.
- Persistent ChromaDB collection (cosine space), gitignored path `.chroma/`.
- Ingestion is a **one-time CLI** (`python -m app.rag.ingest`), idempotent (upsert).

## 5. Embedding model (DECIDED: BGE-M3)

**`BAAI/bge-m3`** via sentence-transformers. Rationale: the KB is English but
reservation emails (hence some policy questions) can be **Portuguese**; BGE-M3 is
a strong **multilingual** retriever (PT↔EN cross-lingual), and since RAG runs
rarely its higher inference cost is irrelevant here.
- **Trade-off accepted:** ~568M params (~1–2 GB loaded) coexisting with Ollama on
  the M1. Mitigated by **lazy-loading** (only when RAG fires) + one-time offline
  ingestion. Owner accepted the memory trade-off.
- **Threshold must be recalibrated for BGE-M3** (its cosine distribution differs
  from the generic 0.65 starting point) — kept as config, tuned at eval.

## 6. Retrieval, `kb_answerable`, and output (DECIDED)

- Embed the query = the email's `body_clean` (truncated) with BGE-M3.
- Top-`k` (**default 3**) by cosine similarity; `score = 1 − distance`.
- **`kb_answerable = (best score ≥ threshold)`** (config `kb_answerable_threshold`,
  start 0.65, recalibrate).
- Output matches the locked `agent_output_schema.retrieval` block:
  ```
  retrieval = { used: true,
    sources: [ {source_id, source_title (=question), source_url_or_path (=source_url),
                chunk_text (=answer), score}, ... ] }   # top-k, best first
  ```
  When RAG doesn't run, `retrieval.used = false`.

## 7. Post-RAG routing resolution (DECIDED approach)

RAG **does not invent an action.** It sets `kb_answerable` on the signals and
**re-invokes the Router's `route()`** so all routing stays in one place. This
extends `route()` for the policy-question branch:
- `kb_answerable is None` (pre-RAG) → `R030` → `draft_reply_with_rag` (candidate)
- `kb_answerable is True` → **`R030A`** → `draft_reply_with_rag` (confirmed)
- `kb_answerable is False` → **`R030B`** → `escalate_to_reservations_team`

This adds two rule_ids to the just-locked `routing_rules.json` → a **v1.2.0
CHANGELOG bump** (additive; no existing mapping broken).

## 8. Graph integration — first conditional edge (DECIDED)

```
… → router → (conditional) ─ rag_required? ─► rag → END
                            └─ else ──────────► END
```
`build_pipeline_graph` gains an injectable `rag_retriever` param. Still no channel
reducers needed (single branch, sequential). The `rag` node appends `"rag"` to
`agent_path`.

## 9. Development plan / files

| Action | File | What |
|---|---|---|
| CREATE | `app/rag/retriever.py` | `Retriever` protocol + `ChromaRetriever` (load collection, embed query, top-k → sources). Injectable. |
| CREATE | `app/rag/ingest.py` | `build_index()` — load FAQs, embed, upsert; CLI `__main__`. |
| CREATE | `app/agents/rag.py` | `rag(state, retriever=None)` — retrieve → set `retrieval` + `kb_answerable` → re-run `route()` → update action. |
| MODIFY | `app/agents/router.py` | add `R030A/R030B` branches + catalog entries; regenerate artifact. |
| MODIFY | `app/models/state.py` | `RetrievalSource`, `RetrievalOutput`, `AgentState.retrieval`. |
| MODIFY | `app/graph.py` | conditional edge after router; `rag_retriever` injection. |
| MODIFY | `app/config.py` | `embedding_model="BAAI/bge-m3"`, `chroma_path`, `kb_path`, `rag_top_k=3`, `kb_answerable_threshold=0.65`. |
| MODIFY | `outputs/routing_rules.json` + `CHANGELOG.md` | v1.2.0 (R030A/B). |
| CREATE | `tests/test_rag.py` | offline (fake retriever) + gated live (real index). |
| UPDATE | `.gitignore` | add `.chroma/`. |

## 10. Determinism & testing (DECIDED)

- Agent logic (threshold, re-route, state writes) is tested **offline with an
  injected fake retriever** — no chromadb/sentence-transformers needed in unit
  tests. Cases: answerable→`draft_reply_with_rag`; not-answerable→
  `escalate_to_reservations_team`; skip-when-not-policy.
- A **gated integration test** builds/loads the real index and checks an obvious
  policy question retrieves a sensible FAQ (skipped if deps/index absent).

## 11. OPEN — what we want the reviewer's opinion on
> **Resolved — see §13 (Post-review reconciliation).** The questions below are kept
> as posed; §13 records what was adopted/rejected and why.

1. **Embedding model:** is **BGE-M3** the right call here, or overkill given RAG
   fires rarely and the KB is small/English? Alternatives: `multilingual-e5-base`
   (~278M, lighter) or `paraphrase-multilingual-MiniLM-L12-v2` (~118M). Does the
   PT-query / EN-KB cross-lingual need justify the size?
2. **What to embed & query:** embed `question+answer` vs `question`-only? Query
   with full `body_clean` vs a focused extracted question? Forwarded emails carry
   noise — does the query text need cleaning beyond `body_clean`?
3. **Answerability:** hard threshold (`kb_answerable = score ≥ θ`) vs a
   **borderline band** (e.g. retrieve-but-flag for human confirmation between two
   thresholds)? Is a single cosine threshold robust enough for a safety-relevant
   draft/escalate decision?
4. **Routing resolution:** is "RAG sets `kb_answerable` then re-invokes `route()`
   with R030A/R030B" the cleanest design, vs RAG directly setting the action? Any
   issue bumping the just-locked routing rules to v1.2.0 for this?
5. **Scope:** no chunking (FAQs are short) — agreed? Should retrieved sources ever
   be surfaced for non-policy categories (e.g. to assist escalation context)?
6. **Anything missed** — especially where "LLM describes, code decides" could be
   violated, or where a single embedding similarity is too fragile for a
   safety-relevant decision.

## 12. Hard constraints (any proposal must respect)
Draft-only · no internal-system access · no operational actions ·
human-in-the-loop · grounded responses only · local on M1.

---

## 13. Post-review reconciliation (DECIDED 2026-06-12) — what we build

After the independent review, adopted the cheap/high-value corrections and
rejected the speculative ingestion platform (YAGNI for a frozen 193-entry KB).

**Adopted:**
- **Focused query (not raw `body_clean`)** via a small `query_builder` with a
  **3-value `query_source`** (debug label):
  `subject_plus_evidence` (subject + classifier `evidence_short`) →
  `subject_plus_body_excerpt` (subject + `body_clean[:N]`) →
  `body_clean_fallback`. Reuses `evidence_short` as a focused-question proxy;
  if it proves weak, `query_source` tells us.
- **Validated score semantics:** cosine collection + **normalized embeddings**;
  store **`raw_distance`** and a documented `score = 1 − distance`.
- **Richer retrieval debug** (`query_text`, `query_source`, `embedding_model`,
  `top_k`, `threshold`) in the **runtime `RetrievalOutput`** — NOT a bump to the
  locked `agent_output_schema.retrieval`.
- **Thin generic interface:** one `KnowledgeChunk` + `RetrievalSource`
  (`source_type`/`metadata`) and a single FAQ ingestion function.

**Rejected / deferred:**
- The **loader/chunking/YAML-source platform** — build it only when a 2nd source
  type actually exists (refactor is cheap then). Interface kept generic; feature
  set not.
- **Answerability bands** — `borderline` and `not_answerable` both escalate, and
  two thresholds can't be calibrated without a RAG eval set. v1 = **single config
  threshold**; store scores; revisit the band at calibration.
- **Embedding benchmark** — owner chose BGE-M3; keep `embedding_model`
  config-swappable and benchmark at eval (needs the RAG eval set).
- **RAG eval set** — needed for threshold/model calibration; parallel track,
  doesn't block the build.

*End of design note.*
