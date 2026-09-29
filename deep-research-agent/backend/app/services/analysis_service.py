"""
Analysis orchestration service.

`start_job` returns immediately after recording a `pending` job and
scheduling `_run_graph` as a background `asyncio.Task` -- the HTTP request
that created the job never blocks on the (potentially 30-60s) multi-agent
graph run. Clients poll `GET /analyses/{job_id}` for progress, which is
simple, debuggable, and doesn't require sticky WebSocket connections behind
a load balancer.

`graph.astream(...)` yields one dict per completed LangGraph "super-step".
Because `planner` fans out to four specialist agents that run in parallel,
a single super-step can yield **multiple** node keys at once (e.g.
`{"company_agent": {...}, "market_agent": {...}, ...}`) rather than always
one -- `_record_step` handles every key in a yielded chunk, not just the
first, so the frontend's agent-trace board can show all four lighting up
together.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from langgraph.graph.state import CompiledStateGraph

from app.config import Settings
from app.models.schemas import JobStatus, SourceRef
from app.services.job_store import JobStore

_COPIED_STATE_KEYS = ("competitors", "research_plan", "key_facts", "sources")


class AnalysisService:
    def __init__(self, graph: CompiledStateGraph, job_store: JobStore, settings: Settings) -> None:
        self._graph = graph
        self._jobs = job_store
        self._settings = settings
        # Track in-flight background tasks so we can (a) hold a strong
        # reference -- an un-referenced asyncio.Task can be garbage
        # collected mid-run -- and (b) cancel them cleanly on shutdown
        # instead of letting the interpreter tear them down mid-await.
        self._tasks: set[asyncio.Task] = set()

    async def start_job(
        self,
        target_company: str,
        competitors: list[str] | None = None,
        focus_areas: list[str] | None = None,
    ) -> str:
        job_id = uuid.uuid4().hex[:12]
        await self._jobs.create(job_id, target_company, competitors)

        task = asyncio.create_task(
            self._run_graph(job_id, target_company, competitors, focus_areas)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job_id

    async def shutdown(self) -> None:
        """Cancel any still-running analysis jobs. Called from app lifespan teardown."""
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run_graph(
        self,
        job_id: str,
        target_company: str,
        competitors: list[str] | None,
        focus_areas: list[str] | None,
    ) -> None:
        await self._jobs.update(job_id, status=JobStatus.running)

        initial_state = {
            "target_company": target_company,
            "competitors": competitors or [],
            "focus_areas": focus_areas or [],
            "max_revisions": self._settings.max_research_revisions,
            "findings": [],
            "trace": [],
        }

        try:
            async for step in self._graph.astream(initial_state):
                for node_name, partial_state in step.items():
                    await self._record_step(job_id, node_name, partial_state)

            # `report_markdown` was already populated in `_record_step` as soon
            # as the `finalizer` node emitted `final_report`; here we only need
            # to flip the job's terminal status.
            await self._jobs.update(job_id, status=JobStatus.completed)
        except Exception as exc:  # noqa: BLE001 - convert any node failure into a failed job
            await self._jobs.update(job_id, status=JobStatus.failed, error=str(exc))

    async def _record_step(self, job_id: str, node_name: str, partial_state: dict) -> None:
        detail = ""
        if partial_state.get("trace"):
            detail = partial_state["trace"][-1]

        await self._jobs.append_trace(
            job_id, node=node_name, status=JobStatus.running, detail=detail
        )

        updates: dict = {}
        for key in _COPIED_STATE_KEYS:
            if key not in partial_state:
                continue
            if key == "sources":
                # Graph state carries sources as plain TypedDicts; convert to
                # the API-contract `SourceRef` model here so the field is
                # actually validated/typed once it lands on the job record,
                # instead of assigning raw dicts via `setattr`.
                updates["sources"] = [SourceRef(**s) for s in partial_state["sources"]]
            else:
                updates[key] = partial_state[key]
        if "revision_count" in partial_state:
            updates["revision_count"] = partial_state["revision_count"]
        if "final_report" in partial_state:
            updates["report_markdown"] = partial_state["final_report"]
        if updates:
            await self._jobs.update(job_id, **updates)
