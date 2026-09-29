"""
Unit tests for the response-parsing helpers in `claude_client.py`.

These exist specifically because a live run against the real Anthropic API
surfaced a real bug: `citations` entries on a `TextBlock` come back as
**plain dicts**, not typed sub-objects, at the pinned SDK version --
`getattr(citation, "url", ...)` silently returns `None` for a dict instead
of raising, so the bug produced no error, just an always-empty source list.
A mocked-only test suite never would have caught this; these tests pin the
exact response shape observed from the real API so it can't regress
silently again.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.claude_client import _extract_citations, _join_text_blocks


def _text_block(text: str, citations: list[dict] | None = None) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text, citations=citations)


def _search_result_block() -> SimpleNamespace:
    return SimpleNamespace(type="web_search_tool_result", tool_use_id="srvtoolu_1", content=[])


def test_join_text_blocks_concatenates_only_text_blocks_in_order() -> None:
    content = [
        _search_result_block(),
        _text_block("Hello "),
        _text_block("world."),
    ]

    assert _join_text_blocks(content) == "Hello world."


def test_extract_citations_reads_dict_shaped_citation_entries() -> None:
    # This is the exact shape the real API returns: a plain dict per
    # citation, not an object with a `.url` attribute.
    content = [
        _text_block(
            "Anthropic's valuation is $965B.",
            citations=[
                {
                    "type": "web_search_result_location",
                    "url": "https://example.com/a",
                    "title": "Source A",
                    "cited_text": "...",
                    "encrypted_index": "...",
                }
            ],
        )
    ]

    sources = _extract_citations(content)

    assert sources == [{"title": "Source A", "url": "https://example.com/a"}]


def test_extract_citations_dedupes_by_url_across_blocks() -> None:
    content = [
        _text_block("First claim.", citations=[{"url": "https://example.com/a", "title": "A"}]),
        _text_block("Second claim.", citations=[{"url": "https://example.com/a", "title": "A"}]),
        _text_block("Third claim.", citations=[{"url": "https://example.com/b", "title": "B"}]),
    ]

    sources = _extract_citations(content)

    assert [s["url"] for s in sources] == ["https://example.com/a", "https://example.com/b"]


def test_extract_citations_falls_back_to_url_when_title_missing() -> None:
    content = [_text_block("Claim.", citations=[{"url": "https://example.com/a"}])]

    sources = _extract_citations(content)

    assert sources == [{"title": "https://example.com/a", "url": "https://example.com/a"}]


def test_extract_citations_ignores_blocks_and_citations_without_a_url() -> None:
    content = [
        _search_result_block(),
        _text_block("No citations here.", citations=None),
        _text_block("Malformed citation.", citations=[{"title": "no url"}]),
    ]

    assert _extract_citations(content) == []
