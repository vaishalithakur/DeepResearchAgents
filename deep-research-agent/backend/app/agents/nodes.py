"""
Graph node implementations for the non-specialist steps: `planner`,
`synthesizer`, `critic`, `finalizer`. The four parallel research specialists
live in `agents/specialists.py` (one shared factory, not four near-duplicate
functions here).

Each is produced by a `make_<name>_node(claude, settings)` factory that
closes over its dependencies and returns an `async def node(state) -> dict`
coroutine -- the exact shape LangGraph expects. This is plain dependency
injection: tests build nodes with a fake/mocked `ClaudeClient` and call them
directly with a hand-built `AnalysisState`, with zero LangGraph or network
involvement.

Every node:
  1. reads what it needs from `state`,
  2. does its work,
  3. returns a **partial** state update (LangGraph merges it in).
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.claude_client import ClaudeClient
from app.agents.specialists import SPECIALIST_AGENTS
from app.agents.state import SourceRef
from app.config import Settings
from app.logging_config import get_logger

logger = get_logger(__name__)

NodeFn = Any  # Callable[[AnalysisState], Awaitable[dict]] -- kept loose for LangGraph's typing


def make_planner_node(claude: ClaudeClient, settings: Settings) -> NodeFn:
    async def planner(state: dict) -> dict:
        target = state["target_company"]
        supplied_competitors = [c.strip() for c in (state.get("competitors") or []) if c.strip()]

        if supplied_competitors:
            competitors = supplied_competitors[: settings.max_competitors]
            discovery_trace = f"planner: using {len(competitors)} supplied competitor(s)"
        else:
            discovery_prompt = (
                f"Identify the {settings.max_competitors} most relevant real competitors of "
                f'"{target}" today. Use web search to ground this in current information. '
                "Respond with ONLY a JSON array of company name strings, no prose, no "
                "markdown fences."
            )
            discovery = await claude.complete_with_search(
                prompt=discovery_prompt,
                system="You are a meticulous market analyst.",
                max_tokens=300,
                max_uses=settings.web_search_max_uses,
            )
            competitors = _safe_json_list(discovery.text, fallback=[])[: settings.max_competitors]
            discovery_trace = f"planner: discovered {len(competitors)} competitor(s)"

        focus_areas = state.get("focus_areas") or list(SPECIALIST_AGENTS)
        plan_prompt = (
            f"Target company: {target}\n"
            f"Competitors: {', '.join(competitors) or 'none identified'}\n"
            f"Focus areas: {', '.join(focus_areas)}\n\n"
            "For each of these four research agents -- company_agent, market_agent, "
            "financial_agent, news_agent -- write ONE focused sub-question tailored to this "
            "specific company. Respond with ONLY a JSON object mapping agent name to "
            'sub-question string, no prose, no markdown fences, e.g. {"company_agent": "...", '
            '"market_agent": "...", "financial_agent": "...", "news_agent": "..."}.'
        )
        plan_raw = await claude.complete(
            prompt=plan_prompt, system="You are a meticulous research planner.", max_tokens=400
        )
        plan = _safe_json_object(plan_raw, fallback={})
        research_plan = {
            agent: [plan[agent]] if isinstance(plan.get(agent), str) else []
            for agent in SPECIALIST_AGENTS
        }

        return {
            "competitors": competitors,
            "research_plan": research_plan,
            "trace": [discovery_trace, "planner: produced per-agent research plan"],
        }

    return planner


def make_synthesizer_node(claude: ClaudeClient) -> NodeFn:
    async def synthesizer(state: dict) -> dict:
        target = state["target_company"]
        competitors = state.get("competitors") or []
        findings_block = "\n\n".join(
            f"### {f['agent']} ({f['sub_question']})\n{f['summary']}"
            for f in state.get("findings", [])
        )
        critique_note = ""
        if state.get("critique"):
            critique_note = (
                "\n\nThe previous draft was reviewed and needs improvement:\n"
                f"{state['critique']}\nRevise accordingly using the same findings above."
            )

        prompt = (
            f"Target company: {target}\n"
            f"Known/discovered competitors: {', '.join(competitors) or 'none'}\n\n"
            f"Specialist findings:\n{findings_block}"
            f"{critique_note}\n\n"
            "First, output ONLY a fenced ```json code block containing a flat object of key "
            'facts you were able to determine, e.g. {"founded": "...", "headquarters": "...", '
            '"website": "...", "employee_estimate": "..."} -- use "unknown" for any field you '
            "could not determine.\n\n"
            "Then, after that block, write a well-structured markdown competitive "
            "intelligence report with these sections, in this order: Executive Summary, "
            "Company Snapshot, Competitive Landscape, Financial & Funding Signals, Recent "
            "Developments, Risks & Opportunities, Sources. Use headings and bullet points."
        )
        raw = await claude.complete(
            prompt=prompt,
            system="You are a precise competitive intelligence analyst.",
            max_tokens=3000,
        )
        draft, key_facts_raw = _split_report_and_json(raw)
        key_facts = _safe_json_object(key_facts_raw, fallback={})

        return {
            "draft_report": draft,
            "key_facts": {str(k): str(v) for k, v in key_facts.items()},
            "trace": ["synthesizer: drafted report"],
        }

    return synthesizer


def make_critic_node(claude: ClaudeClient, settings: Settings) -> NodeFn:
    async def critic(state: dict) -> dict:
        revision_count = state.get("revision_count", 0)

        if revision_count >= settings.max_research_revisions:
            budget = settings.max_research_revisions
            return {
                "needs_revision": False,
                "trace": [f"critic: revision budget ({budget}) reached, accepting draft"],
            }

        prompt = (
            f"Target company: {state['target_company']}\n\n"
            f"Draft report:\n{state['draft_report']}\n\n"
            "Critically review this draft. Check especially for citation coverage (are "
            "claims backed by findings?) and factual consistency. Respond with ONLY JSON: "
            '{"acceptable": true|false, "feedback": "..."}, where "feedback" is at most two '
            "sentences. Mark acceptable=true unless there is a real factual gap, missing "
            "citation, or structural problem worth fixing."
        )
        raw = await claude.complete(
            prompt=prompt, system="You are a skeptical, concise editor.", max_tokens=500
        )
        verdict = _safe_json_object(raw, fallback={"acceptable": True, "feedback": ""})
        needs_revision = not bool(verdict.get("acceptable", True))

        return {
            "needs_revision": needs_revision,
            "critique": verdict.get("feedback", ""),
            "revision_count": revision_count + 1,
            "trace": [
                f"critic: revision {revision_count + 1} -> "
                f"{'needs revision' if needs_revision else 'accepted'}"
            ],
        }

    return critic


def make_finalizer_node() -> NodeFn:
    async def finalizer(state: dict) -> dict:
        deduped: dict[str, SourceRef] = {}
        for finding in state.get("findings", []):
            for source in finding.get("sources", []):
                url = source.get("url")
                if url and url not in deduped:
                    deduped[url] = source

        return {
            "final_report": state.get("draft_report", ""),
            "sources": list(deduped.values()),
            "trace": ["finalizer: report finalized"],
        }

    return finalizer


# --- small parsing helpers ---------------------------------------------------------


def _safe_json_list(raw: str, *, fallback: list[str]) -> list[str]:
    try:
        parsed = json.loads(_strip_fences(raw))
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return parsed
    except json.JSONDecodeError:
        logger.warning("json_list_parse_failed", raw=raw[:200])
    return fallback


def _safe_json_object(raw: str, *, fallback: dict) -> dict:
    try:
        parsed = json.loads(_strip_fences(raw))
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        logger.warning("json_object_parse_failed", raw=raw[:200])
    return fallback


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _split_report_and_json(raw: str) -> tuple[str, str]:
    """Synthesizer emits a fenced ```json key-facts block *first*, then the
    (much longer) markdown report -- in that order deliberately, so the key
    facts survive intact even if the report itself gets cut off by the
    token budget."""
    text = raw.strip()
    if not text.startswith("```"):
        return text, "{}"
    closing = text.find("```", 3)
    if closing == -1:
        # The fenced block itself never closed -- nothing usable either way.
        return "", text
    return text[closing + 3 :].strip(), text[: closing + 3]
