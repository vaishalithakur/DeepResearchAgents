from __future__ import annotations

import pytest

from app.exceptions import JobNotFoundError
from app.models.schemas import JobStatus
from app.services.job_store import JobStore


async def test_create_then_get_round_trips() -> None:
    store = JobStore()

    created = await store.create("job-1", "Acme", ["Foo", "Bar"])
    fetched = await store.get("job-1")

    assert created.job_id == fetched.job_id == "job-1"
    assert fetched.status == JobStatus.pending
    assert fetched.target_company == "Acme"
    assert fetched.competitors == ["Foo", "Bar"]


async def test_get_unknown_job_raises_job_not_found_error() -> None:
    store = JobStore()

    with pytest.raises(JobNotFoundError):
        await store.get("does-not-exist")


async def test_append_trace_accumulates_events_in_order() -> None:
    store = JobStore()
    await store.create("job-1", "Acme")

    await store.append_trace("job-1", node="planner", status=JobStatus.running, detail="planned")
    await store.append_trace(
        "job-1", node="company_agent", status=JobStatus.running, detail="researched"
    )

    job = await store.get("job-1")
    assert [e.node for e in job.trace] == ["planner", "company_agent"]
    assert job.trace[0].detail == "planned"


async def test_update_sets_arbitrary_fields_and_bumps_updated_at() -> None:
    store = JobStore()
    created = await store.create("job-1", "Acme")

    await store.update("job-1", status=JobStatus.completed, report_markdown="# Done")

    job = await store.get("job-1")
    assert job.status == JobStatus.completed
    assert job.report_markdown == "# Done"
    assert job.updated_at >= created.updated_at


async def test_list_recent_orders_newest_first_and_respects_limit() -> None:
    store = JobStore()
    for i in range(5):
        await store.create(f"job-{i}", f"Company {i}")

    recent = await store.list_recent(limit=3)

    assert len(recent) == 3
    assert recent[0].job_id == "job-4"  # most recently created first
