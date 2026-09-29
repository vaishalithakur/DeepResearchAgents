from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_ok_and_config_snapshot(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "claude_model" in body


async def test_response_carries_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert "x-request-id" in {k.lower() for k in response.headers}
