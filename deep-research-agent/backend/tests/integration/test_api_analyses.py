"""
Integration tests for the analysis job lifecycle (create -> poll -> completed).

`_poll_until_terminal` uses `asyncio.timeout()` (3.11+) as a deadline guard
around the polling loop, rather than a hand-rolled `time() + timeout`
comparison -- it's the idiomatic way to bound an async wait in modern
Python and reads clearly as "give up after N seconds" at the call site.
"""

from __future__ import annotations

import asyncio

from httpx import AsyncClient

SPECIALIST_AGENTS = {"company_agent", "market_agent", "financial_agent", "news_agent"}


async def _poll_until_terminal(
    client: AsyncClient, job_id: str, *, budget_seconds: float = 5.0
) -> dict:
    async with asyncio.timeout(budget_seconds):
        while True:
            response = await client.get(f"/analyses/{job_id}")
            body = response.json()
            if body["status"] in {"completed", "failed"}:
                return body
            await asyncio.sleep(0.05)


async def test_create_analysis_returns_202_and_job_id(client: AsyncClient) -> None:
    response = await client.post("/analyses", json={"target_company": "Acme Corp"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert len(body["job_id"]) > 0


async def test_analysis_job_runs_the_full_graph_to_completion(client: AsyncClient) -> None:
    create_response = await client.post(
        "/analyses", json={"target_company": "Acme Corp", "competitors": ["Foo Inc"]}
    )
    job_id = create_response.json()["job_id"]

    final_state = await _poll_until_terminal(client, job_id)

    assert final_state["status"] == "completed"
    visited_nodes = {event["node"] for event in final_state["trace"]}
    # The four specialists run as a parallel fan-out, so order isn't
    # deterministic between them -- assert set membership, not a fixed
    # sequence -- but planner must precede them and finalizer must follow.
    assert visited_nodes >= SPECIALIST_AGENTS
    assert visited_nodes >= {"planner", "synthesizer", "critic", "finalizer"}
    node_order = [event["node"] for event in final_state["trace"]]
    assert node_order[0] == "planner"
    assert node_order[-1] == "finalizer"
    assert final_state["report_markdown"]


async def test_get_unknown_analysis_returns_404_with_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/analyses/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "job_not_found"


async def test_create_analysis_rejects_too_short_target_company(client: AsyncClient) -> None:
    response = await client.post("/analyses", json={"target_company": "A"})

    assert response.status_code == 422


async def test_list_analyses_includes_created_job(client: AsyncClient) -> None:
    create_response = await client.post("/analyses", json={"target_company": "Acme Corp"})
    job_id = create_response.json()["job_id"]

    list_response = await client.get("/analyses")

    assert list_response.status_code == 200
    job_ids = [job["job_id"] for job in list_response.json()]
    assert job_id in job_ids
