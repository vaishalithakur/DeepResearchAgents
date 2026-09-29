"""
Graph assembly.

Topology:

    START -> planner -> [company_agent, market_agent, financial_agent, news_agent]
                                          |  (parallel fan-out)
                                          v  (fan-in: LangGraph waits for all four
                                          |   predecessors before running `synthesizer`,
                                          |   via plain multiple `add_edge` calls -- no
                                          |   special join node needed)
                                     synthesizer -+-> finalizer -> END
                                          ^        |
                                          |     critic
                                          +--(needs_revision)--+

`planner` fans out to four independent specialist agents that each make one
search-enabled Claude call; their `Finding`s merge into `state["findings"]`
via the `operator.add` reducer declared in `agents/state.py`. Once all four
complete, `synthesizer` drafts the report and `critic` reviews it. Unlike a
naive "loop back to research" design, a rejected draft here loops back to
`synthesizer` (not the specialists) -- a rejected draft is usually a
writing/structure problem, not a missing-data problem, so re-running four
searches on every revision would be wasted latency and cost. `revision_count`
in the state, enforced inside the critic node, guarantees the cycle
terminates even if the model never marks a draft acceptable -- LangGraph
itself does not cap cycles for you, so this bound is our responsibility.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.claude_client import ClaudeClient
from app.agents.nodes import (
    make_critic_node,
    make_finalizer_node,
    make_planner_node,
    make_synthesizer_node,
)
from app.agents.specialists import SPECIALIST_AGENTS, make_specialist_node
from app.agents.state import AnalysisState
from app.config import Settings


def _route_after_critic(state: AnalysisState) -> str:
    """Conditional edge function: decides the next node after `critic`."""
    return "synthesizer" if state.get("needs_revision") else "finalizer"


def build_analysis_graph(claude: ClaudeClient, settings: Settings) -> CompiledStateGraph:
    graph = StateGraph(AnalysisState)

    graph.add_node("planner", make_planner_node(claude, settings))
    for agent_key in SPECIALIST_AGENTS:
        graph.add_node(agent_key, make_specialist_node(agent_key, claude, settings))
    graph.add_node("synthesizer", make_synthesizer_node(claude))
    graph.add_node("critic", make_critic_node(claude, settings))
    graph.add_node("finalizer", make_finalizer_node())

    graph.add_edge(START, "planner")
    for agent_key in SPECIALIST_AGENTS:
        graph.add_edge("planner", agent_key)
        graph.add_edge(agent_key, "synthesizer")
    graph.add_edge("synthesizer", "critic")
    graph.add_conditional_edges(
        "critic",
        _route_after_critic,
        {"synthesizer": "synthesizer", "finalizer": "finalizer"},
    )
    graph.add_edge("finalizer", END)

    return graph.compile()
