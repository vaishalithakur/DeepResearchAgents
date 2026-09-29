"""
Thin wrapper around `anthropic.AsyncAnthropic`.

Why wrap it at all instead of calling the SDK directly from nodes/routes?
- One place to configure retries/timeouts/model defaults.
- One place to translate SDK exceptions into our `UpstreamModelError`.
- Makes nodes trivially mockable in unit tests: tests patch
  `ClaudeClient.complete` / `.complete_with_search`, never the network.
- One place to wire up LangSmith tracing (`wrap_anthropic`), so every call
  through this client -- regardless of which graph node made it -- shows up
  as a nested LLM run under that node's trace.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.agents.state import SourceRef
from app.config import Settings
from app.exceptions import UpstreamModelError
from app.logging_config import get_logger

logger = get_logger(__name__)

_RETRYABLE = (anthropic.APITimeoutError, anthropic.APIConnectionError, anthropic.RateLimitError)

_WEB_SEARCH_TOOL = "web_search_20250305"


@dataclass
class SearchCompletion:
    """Result of a search-enabled completion: the text plus every citation
    Claude actually used, deduped by URL."""

    text: str
    sources: list[SourceRef] = field(default_factory=list)


class ClaudeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Identity-linked API keys (tied to a user across multiple
        # workspaces, rather than scoped to one workspace) require every
        # request to declare which workspace it acts in, via this header --
        # a plain workspace-scoped key doesn't need it, so this is a no-op
        # unless `ANTHROPIC_WORKSPACE_ID` is set.
        default_headers = (
            {"anthropic-workspace-id": settings.anthropic_workspace_id}
            if settings.anthropic_workspace_id
            else None
        )
        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, default_headers=default_headers
        )

        if settings.langsmith_enabled:
            # Wrapping the client instance (rather than decorating individual
            # methods) means every `.messages.create()` call below -- plain
            # or search-enabled -- auto-logs as a nested LLM run in
            # LangSmith, under whichever graph node's run is currently active.
            from langsmith import wrappers

            # `wrap_anthropic` postdates this SDK pin's bundled type stubs.
            client = wrappers.wrap_anthropic(client)  # type: ignore[attr-defined]

        self._client = client

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_RETRYABLE),
    )
    async def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Single-shot, non-streaming completion with no tools. Used for
        planning/writing/reviewing steps that don't need fresh web data."""
        try:
            response = await self._client.messages.create(
                model=self._settings.claude_model,
                max_tokens=max_tokens or self._settings.claude_max_tokens,
                system=system or "",
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIStatusError as exc:
            logger.error("claude_api_status_error", status=exc.status_code, body=str(exc))
            raise UpstreamModelError(f"Claude API error: {exc.status_code}") from exc

        return _join_text_blocks(response.content)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_RETRYABLE),
    )
    async def complete_with_search(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        max_uses: int | None = None,
    ) -> SearchCompletion:
        """
        Completion backed by Claude's server-side web search tool: Claude
        decides if/when to search, executes the searches itself, and returns
        the final text plus inline citations -- no client-side tool loop.

        A search *failure* (rate limited, no results, etc.) comes back as a
        normal 200 response with an error-shaped `web_search_tool_result`
        block, not an exception, so we degrade to whatever text Claude did
        produce rather than failing the whole node.
        """
        # The server-side web search tool predates this SDK pin's `ToolParam`
        # type stub (which only models client-side tools with an
        # `input_schema`), so its shape is asserted as `Any` here.
        web_search_tool: Any = {
            "type": _WEB_SEARCH_TOOL,
            "name": "web_search",
            "max_uses": max_uses or self._settings.web_search_max_uses,
        }
        try:
            response = await self._client.messages.create(
                model=self._settings.claude_model,
                max_tokens=max_tokens or self._settings.claude_max_tokens,
                system=system or "",
                messages=[{"role": "user", "content": prompt}],
                tools=[web_search_tool],
            )
        except anthropic.APIStatusError as exc:
            logger.error("claude_api_status_error", status=exc.status_code, body=str(exc))
            raise UpstreamModelError(f"Claude API error: {exc.status_code}") from exc

        text = _join_text_blocks(response.content)
        sources = _extract_citations(response.content)
        return SearchCompletion(text=text, sources=sources)


def _join_text_blocks(content: Sequence[Any]) -> str:
    parts = [
        getattr(block, "text", "") for block in content if getattr(block, "type", None) == "text"
    ]
    return "".join(parts).strip()


def _extract_citations(content: Sequence[Any]) -> list[SourceRef]:
    """
    Citations attach *inline* on each `text` block's `citations` array (not
    on the `web_search_tool_result` block, which just holds candidate
    results -- not necessarily what was actually cited). The block itself
    (`TextBlock`) is a real SDK object, but at this SDK version each entry
    in its `citations` array comes back as a **plain dict**, not a typed
    sub-object -- `getattr(citation, "url", ...)` silently returns `None`
    for a dict (it has no `.url` attribute), so citation fields must be read
    with `.get(...)`, not `getattr(...)`.
    """
    seen: dict[str, SourceRef] = {}
    for block in content:
        if getattr(block, "type", None) != "text":
            continue
        for citation in getattr(block, "citations", None) or []:
            url = citation.get("url") if isinstance(citation, dict) else None
            if not url or url in seen:
                continue
            title = citation.get("title") if isinstance(citation, dict) else None
            seen[url] = SourceRef(title=title or url, url=url)
    return list(seen.values())
