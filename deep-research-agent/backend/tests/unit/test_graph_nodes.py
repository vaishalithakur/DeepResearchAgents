"""
Unit tests for graph node factories.

These tests call the node coroutines directly with a hand-built state dict
-- no LangGraph `StateGraph`, no HTTP layer, no network. That's the payoff
of the `make_<name>_node(deps) -> node_fn` factory pattern in `nodes.py` /
`specialists.py`: each node is a pure-ish function of (deps, state) ->
partial_state, so it's as easy to unit test as any other function.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.agents.claude_client import SearchCompletion
from app.agents.nodes import (
    make_critic_node,
    make_finalizer_node,
    make_planner_node,
    make_synthesizer_node,
)
from app.agents.specialists import make_specialist_node
from app.config import Settings


def _settings(*, max_competitors: int = 4, max_research_revisions: int = 2) -> Settings:
    # Constructed via the env-alias keys (not the field names) so an
    # override reliably wins even when a local `.env` also defines these --
    # pydantic-settings resolves multi-source precedence by alias, and a
    # field-name kwarg can otherwise silently lose to a `.env` value despite
    # `populate_by_name=True`.
    return Settings(
        MAX_COMPETITORS=max_competitors,
        MAX_RESEARCH_REVISIONS=max_research_revisions,
    )


class _StubClaude:
    def __init__(
        self,
        complete_response: str = "{}",
        search_response: SearchCompletion | None = None,
    ) -> None:
        self.complete = AsyncMock(return_value=complete_response)
        self.complete_with_search = AsyncMock(
            return_value=search_response or SearchCompletion(text="[]", sources=[])
        )


# --- planner -----------------------------------------------------------------


async def test_planner_uses_supplied_competitors_without_a_discovery_search() -> None:
    claude = _StubClaude(
        complete_response=(
            '{"company_agent": "Q1", "market_agent": "Q2", '
            '"financial_agent": "Q3", "news_agent": "Q4"}'
        )
    )
    planner = make_planner_node(claude, _settings())

    result = await planner({"target_company": "Acme", "competitors": ["Foo", "Bar"]})

    assert result["competitors"] == ["Foo", "Bar"]
    claude.complete_with_search.assert_not_called()
    assert result["research_plan"]["company_agent"] == ["Q1"]
    assert result["research_plan"]["news_agent"] == ["Q4"]


async def test_planner_discovers_competitors_via_search_when_not_supplied() -> None:
    claude = _StubClaude(
        complete_response="{}",
        search_response=SearchCompletion(text='["Foo", "Bar", "Baz"]', sources=[]),
    )
    planner = make_planner_node(claude, _settings(max_competitors=2))

    result = await planner({"target_company": "Acme"})

    assert result["competitors"] == ["Foo", "Bar"]
    claude.complete_with_search.assert_called_once()


async def test_planner_falls_back_to_empty_plan_on_bad_json() -> None:
    claude = _StubClaude(complete_response="not json at all")
    planner = make_planner_node(claude, _settings())

    result = await planner({"target_company": "Acme", "competitors": ["Foo"]})

    assert result["research_plan"]["company_agent"] == []


# --- specialist agents ---------------------------------------------------------


async def test_specialist_node_returns_finding_tagged_with_its_agent_key() -> None:
    claude = _StubClaude(
        search_response=SearchCompletion(
            text="summary text",
            sources=[{"title": "T", "url": "https://example.com"}],
        )
    )
    node = make_specialist_node("market_agent", claude, _settings())

    result = await node(
        {
            "target_company": "Acme",
            "competitors": ["Foo"],
            "research_plan": {"market_agent": ["How does Acme compare to Foo?"]},
        }
    )

    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["agent"] == "market_agent"
    assert finding["summary"] == "summary text"
    assert finding["sources"] == [{"title": "T", "url": "https://example.com"}]
    assert finding["sub_question"] == "How does Acme compare to Foo?"
    assert "market_agent" in result["trace"][0]


# --- synthesizer -----------------------------------------------------------------


async def test_synthesizer_splits_leading_key_facts_json_from_report_body() -> None:
    claude = _StubClaude(
        complete_response=(
            '```json\n{"founded": "2021", "headquarters": "SF"}\n```' "\n\n## Report\n\nBody text"
        )
    )
    synthesizer = make_synthesizer_node(claude)

    state = {
        "target_company": "Acme",
        "competitors": ["Foo"],
        "findings": [
            {"agent": "company_agent", "sub_question": "Q", "summary": "Summary A", "sources": []}
        ],
        "critique": "Add more nuance",
    }
    result = await synthesizer(state)

    assert result["draft_report"] == "## Report\n\nBody text"
    assert result["key_facts"] == {"founded": "2021", "headquarters": "SF"}
    prompt_used = claude.complete.call_args.kwargs["prompt"]
    assert "Summary A" in prompt_used
    assert "Add more nuance" in prompt_used


async def test_synthesizer_defaults_key_facts_to_empty_dict_without_json_block() -> None:
    claude = _StubClaude(complete_response="## Report\n\nJust prose, no json block.")
    synthesizer = make_synthesizer_node(claude)

    result = await synthesizer({"target_company": "Acme", "findings": []})

    assert result["key_facts"] == {}


# --- critic -----------------------------------------------------------------


async def test_critic_accepts_when_model_says_acceptable() -> None:
    claude = _StubClaude(complete_response='{"acceptable": true, "feedback": ""}')
    critic = make_critic_node(claude, _settings())

    result = await critic({"target_company": "Acme", "draft_report": "draft", "revision_count": 0})

    assert result["needs_revision"] is False
    assert result["revision_count"] == 1


async def test_critic_requests_revision_when_model_says_not_acceptable() -> None:
    claude = _StubClaude(complete_response='{"acceptable": false, "feedback": "Missing citations"}')
    critic = make_critic_node(claude, _settings())

    result = await critic({"target_company": "Acme", "draft_report": "draft", "revision_count": 0})

    assert result["needs_revision"] is True
    assert result["critique"] == "Missing citations"


async def test_critic_stops_looping_once_revision_budget_is_exhausted() -> None:
    claude = _StubClaude(complete_response='{"acceptable": false, "feedback": "still bad"}')
    critic = make_critic_node(claude, _settings(max_research_revisions=1))

    result = await critic({"target_company": "Acme", "draft_report": "draft", "revision_count": 1})

    # Budget already spent -> critic must force acceptance regardless of the
    # model's opinion, or the graph would cycle forever.
    assert result["needs_revision"] is False
    claude.complete.assert_not_called()


# --- finalizer -----------------------------------------------------------------


async def test_finalizer_copies_draft_and_dedupes_sources_by_url() -> None:
    finalizer = make_finalizer_node()

    state = {
        "draft_report": "final text",
        "findings": [
            {
                "agent": "company_agent",
                "sub_question": "Q1",
                "summary": "S1",
                "sources": [
                    {"title": "A", "url": "https://a.com"},
                    {"title": "B", "url": "https://b.com"},
                ],
            },
            {
                "agent": "market_agent",
                "sub_question": "Q2",
                "summary": "S2",
                "sources": [{"title": "B dup", "url": "https://b.com"}],
            },
        ],
    }
    result = await finalizer(state)

    assert result["final_report"] == "final text"
    assert [s["url"] for s in result["sources"]] == ["https://a.com", "https://b.com"]
