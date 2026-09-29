"""
The four specialist research agents (company / market / financial / news).

Each is a thin, identically-shaped Claude call scoped to a different focus
area -- built from one shared factory instead of four near-duplicate node
functions. They run as a genuine LangGraph parallel fan-out (see
`agents/graph.py`): `planner` fans out to all four at once, and their
results fan back in to `synthesizer` via the `findings` list's append
reducer (`agents/state.py`).
"""

from __future__ import annotations

from typing import Any

from app.agents.claude_client import ClaudeClient
from app.agents.state import Finding
from app.config import Settings
from app.logging_config import get_logger

logger = get_logger(__name__)

NodeFn = Any  # Callable[[AnalysisState], Awaitable[dict]] -- kept loose for LangGraph's typing

SPECIALIST_AGENTS: tuple[str, ...] = (
    "company_agent",
    "market_agent",
    "financial_agent",
    "news_agent",
)

_FOCUS: dict[str, str] = {
    "company_agent": (
        "Research the company's business model, core products/services, positioning, and "
        "target customers."
    ),
    "market_agent": (
        "Research the competitive landscape: how the company compares to its competitors, "
        "market share signals, and what differentiates it."
    ),
    "financial_agent": (
        "Research funding history, valuation, revenue signals, and major investors, to the "
        "extent this is publicly known."
    ),
    "news_agent": (
        "Research the most recent developments: product launches, leadership changes, "
        "partnerships, or other news from roughly the last 12 months."
    ),
}


def make_specialist_node(agent_key: str, claude: ClaudeClient, settings: Settings) -> NodeFn:
    focus_instructions = _FOCUS[agent_key]
    label = agent_key.replace("_agent", "").replace("_", " ")

    async def specialist(state: dict) -> dict:
        target = state["target_company"]
        competitors = state.get("competitors") or []
        planned_questions = (state.get("research_plan") or {}).get(agent_key) or []
        sub_question = planned_questions[0] if planned_questions else f"{focus_instructions}"

        prompt = (
            f"Target company: {target}\n"
            + (f"Known competitors: {', '.join(competitors)}\n" if competitors else "")
            + f"\nResearch focus: {focus_instructions}\n"
            f"Specific question to answer: {sub_question}\n\n"
            "Use web search to ground your answer in current, real information. Write a "
            "concise (5-8 sentence) factual brief. Be explicit about uncertainty if "
            "information is thin or conflicting."
        )
        result = await claude.complete_with_search(
            prompt=prompt,
            system=f"You are a meticulous {label} specialist on a competitive intelligence team.",
            max_tokens=600,
            max_uses=settings.web_search_max_uses,
        )

        finding = Finding(
            agent=agent_key,
            sub_question=sub_question,
            summary=result.text,
            sources=result.sources,
        )

        return {
            "findings": [finding],
            "trace": [f"{agent_key}: gathered findings ({len(result.sources)} sources)"],
        }

    return specialist
