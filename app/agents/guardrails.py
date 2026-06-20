"""Guardrails Agent (#8) — the independent, deterministic safety net.

Runs LAST. Scans the ONE customer-facing artifact (output.draft_reply) for claims
the system is forbidden to make, and writes the locked `guardrails` block. It is
deliberately NOT an LLM: a safety layer must be more trustworthy (transparent,
reproducible, testable) than the thing it guards. It does not trust #7's output —
that is the point of a separate agent (defense-in-depth). The human reviewer is
the ultimate gate; #8 is the automated layer in front of them.

Design (post-review, 2026-06-20):
  - Scope: scans ONLY draft_reply. Every non-draft path has draft_reply=None ⇒
    no-op (passed=True). The deterministic internal artifacts are reviewer-facing
    and grounded, so they are out of scope. Project invariant (enforced in the
    API/dashboard, not here): only draft_reply is ever customer-facing.
  - Core 5 hard-block rules; no soft "warning" tier in v1.
  - On block: redact (draft_reply→None, preserve the withheld text + violated
    rules in internal_notes) and set passed=False + escalation_reason. It does NOT
    overwrite recommended_action — the Router owns routing; the dashboard derives a
    "blocked" status from passed=False.
  - Patterns target claim STRUCTURES (agent-performed / "your X is confirmed"),
    not bare keywords, so policy descriptions ("you can cancel …") are not blocked.
  - Bilingual EN + PT (accent-folded). High-precision: tolerates false negatives
    (odd paraphrases reach the human) over false positives (blocking a good reply).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List

from app.models.guardrails import BlockedClaim, GuardrailsOutput
from app.models.state import AgentState

AGENT_NAME = "guardrails"

_BLOCK_REASON = ("Draft contained forbidden operational/system claim(s); "
                 "withheld for manual review.")

# Negation cues — for the guarantee/availability rules, a negated sentence
# ("we cannot guarantee", "not available") must NOT be blocked. Errs to safe.
_NEGATION = re.compile(r"\b(?:not|no|never|cannot|cant|unable|nao|nunca|sem)\b")


@dataclass(frozen=True)
class GuardRule:
    id: str
    category: str
    reason: str
    regex: re.Pattern
    negation_guard: bool = False


def _rule(rule_id: str, category: str, reason: str, patterns: List[str],
          negation_guard: bool = False) -> GuardRule:
    return GuardRule(rule_id, category, reason,
                     re.compile("|".join(patterns)), negation_guard)


# ---- Core 5 forbidden-claim rules (patterns are written accent-folded + lowercase) ----
RULES: List[GuardRule] = [
    _rule("GR001_ACTION_PERFORMED", "ACTION",
          "Claims an operational action (booking change/cancellation/confirmation) was performed.",
          [r"\b(?:i|we)\s+(?:have\s+|'ve\s+|just\s+)?(?:confirmed|booked|cancelled|canceled|modified|changed|rebooked|amended)\s+(?:your\s+|the\s+)?(?:booking|reservation|stay|room|dates?)\b",
           r"\byour\s+(?:booking|reservation|stay|room|dates?)\s+(?:has\s+been|have\s+been|is\s+now|are\s+now|was|were)\s+(?:confirmed|cancelled|canceled|modified|changed|rebooked|amended)\b",
           r"\b(?:a\s+sua\s+|a\s+)?(?:reserva|estadia)\s+(?:foi|esta|ja\s+foi)\s+(?:confirmada|cancelada|alterada|modificada)\b",
           r"\b(?:confirmei|cancelei|alterei|modifiquei)\s+(?:a\s+sua\s+|a\s+)?(?:reserva|estadia)\b"]),
    _rule("GR002_SYSTEM_ACCESS", "SYSTEM_ACCESS",
          "Claims access to an internal reservation system.",
          [r"\b(?:i|we)\s+(?:have\s+|'ve\s+)?(?:checked|verified|looked\s+up|found|reviewed|accessed|consulted)\b[^.]*\b(?:system|pms|crs|records?|reservation\s+system|booking\s+system|channel\s+manager)\b",
           r"\b(?:in|on)\s+our\s+(?:system|records|pms|crs)\b",
           r"\byour\s+(?:booking|reservation)\s+in\s+our\s+(?:system|records)\b",
           r"\b(?:verifiquei|consultei|encontrei|confirmei)\b[^.]*\b(?:no\s+nosso\s+sistema|nos\s+nossos\s+registos|no\s+sistema|na\s+nossa\s+base)\b",
           r"\bno\s+nosso\s+sistema\b"]),
    _rule("GR003_FIRM_COMMITMENT", "COMMITMENT",
          "Makes a firm reservation/upgrade guarantee the agent cannot make.",
          [r"\byour\s+(?:room|upgrade|booking|reservation|rate)\s+(?:is|has\s+been)\s+(?:reserved|guaranteed|secured)\b",
           r"\b(?:i|we)\s+guarantee\s+(?:you\s+)?(?:that\s+)?(?:your|the|a|this)\b",
           r"\bo\s+seu\s+(?:quarto|upgrade)\s+(?:esta|foi)\s+(?:reservado|garantido)\b",
           r"\bgarant(?:imos|o)\s+(?:que\s+)?(?:o\s+seu|a\s+sua|o|a)\b"],
          negation_guard=True),
    _rule("GR004_PAYMENT_REFUND", "PAYMENT",
          "Claims a payment/refund/invoice was processed.",
          [r"\byour\s+(?:payment|refund|invoice|deposit|charge)\s+(?:has\s+been|is|was)\s+(?:processed|confirmed|issued|completed|refunded|received)\b",
           r"\b(?:i|we)\s+(?:have\s+|'ve\s+)?(?:processed|issued|refunded|charged|completed)\s+(?:your\s+|the\s+)?(?:payment|refund|invoice|deposit)\b",
           r"\bthe\s+refund\s+(?:has\s+been|is|was)\s+(?:processed|issued|sent|on\s+its\s+way)\b",
           r"\bo\s+seu\s+(?:pagamento|reembolso)\s+(?:foi|esta)\s+(?:processado|confirmado|efetuado|emitido)\b",
           r"\b(?:a\s+fatura|o\s+reembolso)\s+foi\s+(?:emitida|emitido|processado|processada)\b"]),
    _rule("GR005_AVAILABILITY_PRICE", "AVAILABILITY",
          "Claims availability/price the agent cannot confirm without internal access.",
          [r"\b(?:the|this)\s+(?:room|rate|price|suite|rooms)\s+(?:is|are)\s+(?:available|confirmed|guaranteed)\b",
           r"\bwe\s+(?:can|are\s+able\s+to)\s+offer\s+(?:you\s+)?(?:this|the|a)\s+(?:room|rate|price|upgrade|suite)\b",
           r"\bavailability\s+is\s+confirmed\b",
           r"\bo\s+(?:quarto|preco|valor)\s+(?:esta|fica)\s+(?:disponivel|confirmado|garantido)\b",
           r"\b(?:os\s+quartos|quartos)\s+estao\s+disponiveis\b"],
          negation_guard=True),
]

_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")


def _normalize(text: str) -> str:
    """Lowercase, fold accents (PT), normalize apostrophes, collapse whitespace."""
    text = text.replace("’", "'").replace("`", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _scan(draft: str) -> List[BlockedClaim]:
    """One BlockedClaim per offending sentence (first matching rule wins)."""
    blocked: List[BlockedClaim] = []
    for sentence in (s.strip() for s in _SENTENCE_SPLIT.split(draft)):
        if not sentence:
            continue
        norm = _normalize(sentence)
        for rule in RULES:
            if not rule.regex.search(norm):
                continue
            if rule.negation_guard and _NEGATION.search(norm):
                continue  # negated guarantee/availability → err to safe
            blocked.append(BlockedClaim(claim_text=sentence, rule_id=rule.id,
                                        reason=rule.reason))
            break
    return blocked


def _redact(state: AgentState, draft: str, blocked: List[BlockedClaim]) -> None:
    """Withhold the unsafe draft but preserve it (for audit) in internal_notes."""
    rules = ", ".join(sorted({c.rule_id for c in blocked}))
    notice = ("🚫 DRAFT BLOCKED BY GUARDRAILS — DO NOT SEND.\n"
              f"Reason: {_BLOCK_REASON}\n"
              f"Violated rule(s): {rules}\n"
              f"Withheld draft (audit only):\n{draft}")
    prev = state.output.internal_notes
    state.output.internal_notes = notice + (f"\n\n---\n{prev}" if prev else "")
    state.output.draft_reply = None


def check_guardrails(state: AgentState) -> AgentState:
    """Scan draft_reply; pass-through for every other path."""
    state.agent_path.append(AGENT_NAME)
    draft = state.output.draft_reply if state.output else None
    if not draft or not draft.strip():
        state.guardrails = GuardrailsOutput(passed=True)
        return state

    blocked = _scan(draft)
    if not blocked:
        state.guardrails = GuardrailsOutput(passed=True)
        return state

    state.guardrails = GuardrailsOutput(passed=False, blocked_claims=blocked,
                                        escalation_reason=_BLOCK_REASON)
    _redact(state, draft, blocked)
    return state
