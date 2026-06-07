"""LangGraph wiring of the core triage pipeline (#1–#5).

The pipeline is linear: classifier_extractor → validator → audit → router. Each
node reuses the existing agent function (which takes and returns the full
AgentState), so the graph is a thin orchestration layer over already-tested
agents. Preprocessing (#1) runs before the graph builds the initial AgentState.

LLM clients are injectable so the graph is testable offline without Ollama.
Linear flow means plain overwrite semantics accumulate agent_path/errors
correctly — no channel reducers needed (add them only if branches run in
parallel later, e.g. a conditional RAG edge).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from langgraph.graph import END, StateGraph

from app.agents.audit import audit
from app.agents.classifier_extractor import classify
from app.agents.preprocessor import preprocess
from app.agents.router import route_email
from app.agents.validator import validate
from app.llm.client import LLMClient
from app.models.state import AgentState


def build_pipeline_graph(classifier_client: Optional[LLMClient] = None,
                         validator_client: Optional[LLMClient] = None):
    """Compile the #2–#5 StateGraph. Inject clients for offline testing; leave
    them None to use the default OllamaNativeClient."""
    g = StateGraph(AgentState)
    g.add_node("classifier_extractor", lambda s: classify(s, client=classifier_client))
    g.add_node("validator", lambda s: validate(s, client=validator_client))
    g.add_node("audit", audit)
    g.add_node("router", route_email)

    g.set_entry_point("classifier_extractor")
    g.add_edge("classifier_extractor", "validator")
    g.add_edge("validator", "audit")
    g.add_edge("audit", "router")
    g.add_edge("router", END)
    return g.compile()


_DEFAULT_GRAPH = None


def get_pipeline():
    """Lazily-compiled default graph (real Ollama clients)."""
    global _DEFAULT_GRAPH
    if _DEFAULT_GRAPH is None:
        _DEFAULT_GRAPH = build_pipeline_graph()
    return _DEFAULT_GRAPH


def run_state(state: AgentState, graph=None) -> AgentState:
    """Invoke the graph on a prepared AgentState. invoke() returns a dict; we
    coerce it back to AgentState."""
    graph = graph or get_pipeline()
    result = graph.invoke(state)
    return result if isinstance(result, AgentState) else AgentState(**result)


def run_pipeline(path: str | Path, graph=None) -> AgentState:
    """Full entry: preprocess a raw .txt email, then run #2–#5."""
    p = Path(path)
    state = AgentState(email=preprocess(p), agent_path=["preprocessor"])
    return run_state(state, graph)
