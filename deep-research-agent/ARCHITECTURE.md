# Architecture

How Fieldnote Intelligence turns "analyze Acme Corp" into a structured, cited competitive
intelligence brief. This is the doc to read to understand *why* the system is shaped the way it
is, not just what each file does.

---

## The pipeline

```
START -> planner -> [company_agent, market_agent, financial_agent, news_agent]
                                          |  (parallel fan-out)
                                          v  (fan-in: LangGraph waits for all four
                                          |   predecessors before running synthesizer,
                                          |   via plain multiple add_edge calls -- no
                                          |   special join node needed)
                                     synthesizer -+-> finalizer -> END
                                          ^        |
                                          |     critic
                                          +--(needs_revision)--+
```

1. **`planner`** takes the target company (and, optionally, user-supplied competitors/focus
   areas). If no competitors were given, it discovers 3-4 real ones with a search-enabled Claude
   call, then writes one tailored sub-question per specialist agent (the `research_plan`).
2. **Four specialist agents** (`company_agent`, `market_agent`, `financial_agent`, `news_agent`)
   run **in parallel** — a genuine LangGraph fan-out, not a `for` loop. Each makes one
   search-enabled Claude call scoped to its focus area and returns a `Finding`. All four write
   into the same `findings` list via an append reducer (`operator.add`), so `synthesizer` only
   runs once every specialist has finished (LangGraph's native fan-in: multiple `add_edge` calls
   into one node).
3. **`synthesizer`** turns the four findings into a structured markdown report plus a small
   `key_facts` JSON block for the UI's summary cards.
4. **`critic`** reviews the draft for citation coverage and factual consistency, bounded by a
   revision budget (`settings.max_research_revisions`) so the cycle can't run forever.
5. **`finalizer`** dedupes citations by URL and sets the final report.

## State: `agents/state.py`

`AnalysisState` is a `TypedDict(total=False)`. Two fields carry `Annotated[..., operator.add]`
reducers instead of plain overwrite:

- `findings` — each of the four parallel specialists appends its own `Finding` instead of
  clobbering the others'. This is *the* mechanism that makes the fan-out/fan-in pattern work.
- `trace` — every node appends a human-readable line, which is what drives the frontend's live
  agent-trace board.

Everything else (`draft_report`, `key_facts`, `research_plan`, ...) is a plain overwrite: each
node that sets a field is meant to fully replace the previous value.

## Why the critic loops back to `synthesizer`, not the specialists

A naive design loops a rejected draft back to re-run research. This project deliberately loops
back to `synthesizer` instead: a rejected draft is almost always a *writing or structure* problem
(missing a section, thin citations, a weak executive summary), not a missing-data problem. Re-running
four search-enabled Claude calls on every revision would burn latency and API cost for no benefit
in the common case. `synthesizer` gets the same findings plus the critic's `critique` and rewrites
from there.

## Why one specialist factory instead of four functions

`agents/specialists.py` has a single `make_specialist_node(agent_key, claude, settings)` factory,
parameterized by a per-agent focus-instruction constant, rather than four near-identical
`make_company_node` / `make_market_node` / ... functions. Each specialist's actual logic — build a
prompt from `target_company` + `competitors` + its slice of `research_plan`, call
`claude.complete_with_search`, return a tagged `Finding` — is identical; only the focus text
differs. `agents/graph.py` calls the factory once per key in `SPECIALIST_AGENTS` to both build the
nodes and wire the fan-out/fan-in edges, so adding a fifth specialist later is a one-line addition
to that tuple plus a focus string, not a new function.

## Web search: `agents/claude_client.py`

`ClaudeClient.complete_with_search()` uses Claude's **server-side** web search tool
(`web_search_20250305`): Claude decides if/when to search, executes the searches itself, and
returns the final text plus inline citations in the same response — no client-side tool-call loop
to write or maintain. Citations aren't a separate block; they attach to individual `text` blocks
via a `citations` array, so `_extract_citations` walks every text block rather than reading the
`web_search_tool_result` block directly (that block holds *candidate* results, not necessarily
what Claude actually cited). A search failure (rate limited, no results) comes back as a normal
200 response with an error-shaped result block, not an exception — so the client degrades to
whatever text Claude did produce instead of failing the whole node over one flaky search.

## Observability: LangSmith

LangGraph auto-traces one run per node once `langsmith` is installed and the right environment
variables are set — no `@traceable` decorators needed on node functions. For LLM-call-level spans
(token usage, latency, cost) nested *inside* those node runs, `ClaudeClient` wraps the underlying
`anthropic.AsyncAnthropic` instance with `langsmith.wrappers.wrap_anthropic()` at construction
time, gated on `settings.langsmith_enabled`.

One nuance worth knowing: `pydantic-settings` only populates the `Settings` object, not
`os.environ` — but LangSmith's tracer reads environment variables directly, since it has no API
surface `Settings` can hand values to. `main.py`'s lifespan bridges the handful of relevant
`LANGSMITH_*` values from `Settings` into `os.environ` once, before the graph is built (tracing
hooks are established at graph-build/first-run time, so this has to happen first).

## Job orchestration

`AnalysisService.start_job()` creates a `pending` job in the in-memory `JobStore` and schedules
`_run_graph` as a tracked `asyncio.Task`, returning immediately with `202 Accepted` — the HTTP
request never blocks on the multi-agent run. `graph.astream(...)` yields one dict per completed
LangGraph super-step; because the four specialists run in parallel, a single super-step can
contain **multiple** node keys at once, and `_record_step` handles every key in that chunk (not
just one), which is what lets the frontend's agent-trace board show all four specialists
progressing together instead of always appearing to run one at a time.

The `JobStore` is intentionally a small, in-memory, single-process interface — a deliberate choice
to keep the demo simple, not an oversight. Swapping in a Redis- or Postgres-backed implementation
later is "write one new class against the same four methods," not a rewrite of anything that calls
it.
