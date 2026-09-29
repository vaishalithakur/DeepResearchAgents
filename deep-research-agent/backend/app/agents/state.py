"""
LangGraph state definition.

LangGraph threads a single mutable "state" object through every node in the
graph. Each node receives the current state and returns a *partial* dict of
updates; LangGraph merges that into the running state using the reducers
declared here (or plain overwrite if none is declared).

We use a TypedDict (LangGraph's recommended pattern) rather than a Pydantic
model for the state itself, because LangGraph performs a shallow merge on
plain dict keys most efficiently, and it keeps node functions dependency
free from the graph runtime for easier unit testing.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class SourceRef(TypedDict):
    title: str
    url: str


class Finding(TypedDict):
    agent: str
    sub_question: str
    summary: str
    sources: list[SourceRef]


class AnalysisState(TypedDict, total=False):
    # --- inputs -----------------------------------------------------------
    target_company: str
    competitors: list[str]
    focus_areas: list[str]
    max_revisions: int

    # --- planner output -----------------------------------------------------
    research_plan: dict[str, list[str]]

    # --- specialist agent output ---------------------------------------------
    # `operator.add` makes this an *append* reducer: each of the four
    # specialist nodes (company/market/financial/news), run in parallel via
    # LangGraph's fan-out, adds its own finding to the list instead of
    # overwriting it -- this is what makes the fan-in into `synthesizer` work.
    findings: Annotated[list[Finding], operator.add]

    # --- synthesizer / critic loop --------------------------------------------
    draft_report: str
    key_facts: dict[str, str]
    critique: str
    needs_revision: bool
    revision_count: int

    # --- final output ------------------------------------------------------
    final_report: str
    sources: list[SourceRef]

    # --- observability -----------------------------------------------------
    # Every node appends a human-readable trace line; used to drive the
    # frontend's live "agent trace" board.
    trace: Annotated[list[str], operator.add]
