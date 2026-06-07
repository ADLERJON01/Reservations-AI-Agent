"""Pipeline agents.

Intentionally empty in the scaffold. Agents land here in build order:
  1 preprocessor → 2 classifier_extractor → 3 validator → 4 audit → 5 router
  → (wire into LangGraph) → 6 rag → 7 output_generator → 8 guardrails.

Reminder of the division of labour (memory: architecture-routing-signals):
  - validator (#3): LLM semantic critique ONLY.
  - audit (#4): ALL deterministic checks (grounding, consistency, completeness),
    broadened beyond booking_notification.
  - router (#5): pure decision layer; consumes RouterSignals, emits recommended_action.
"""
