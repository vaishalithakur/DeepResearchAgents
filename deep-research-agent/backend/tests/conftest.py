"""
Shared test fixtures.

Key idea: we never let a test hit the real Anthropic API or the real web.
`FakeClaudeClient` subclasses the real `ClaudeClient` (so it satisfies the
same type everywhere it's injected) but overrides `complete` /
`complete_with_search` with canned, deterministic responses -- there's no
separate web-search fixture to patch anymore (unlike the old DuckDuckGo
`tools.py`), since search now happens inside `ClaudeClient` itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.agents.claude_client import ClaudeClient, SearchCompletion
from app.main import create_app

PLANNER_STYLE_RESPONSE = '["Sub Q1?", "Sub Q2?"]'
SEARCH_STYLE_RESPONSE = SearchCompletion(
    text="a concise, search-grounded summary",
    sources=[{"title": "Example", "url": "https://example.com"}],
)


class FakeClaudeClient(ClaudeClient):
    """Network-free stand-in for `ClaudeClient`."""

    def __init__(
        self,
        complete_return: str = PLANNER_STYLE_RESPONSE,
        search_return: SearchCompletion = SEARCH_STYLE_RESPONSE,
    ) -> None:
        # Intentionally NOT calling super().__init__(): we never want a real
        # anthropic.AsyncAnthropic constructed in tests.
        self.complete = AsyncMock(return_value=complete_return)  # type: ignore[method-assign]
        self.complete_with_search = AsyncMock(  # type: ignore[method-assign]
            return_value=search_return
        )


@pytest_asyncio.fixture
async def fake_claude() -> FakeClaudeClient:
    return FakeClaudeClient()


@pytest_asyncio.fixture
async def app(fake_claude: FakeClaudeClient):
    """
    A fully started FastAPI app (lifespan has run: settings, job store, and
    the compiled LangGraph all exist) with its Claude client's network-facing
    methods monkeypatched onto the *same* instance the graph closed over.
    """
    application = create_app()
    async with LifespanManager(application):
        application.state.claude_client.complete = fake_claude.complete
        application.state.claude_client.complete_with_search = fake_claude.complete_with_search
        yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
