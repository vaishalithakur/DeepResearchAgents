# Fieldnote Intelligence

A multi-agent competitive intelligence analyst. Give it a company name and it researches the
competitive landscape, funding signals, and recent developments in parallel, then hands back a
structured, cited brief.

- **Backend**: FastAPI (async, background jobs) + LangGraph (planner → four parallel research
  specialists → synthesizer/critic revision loop → finalizer) + Claude's native server-side web
  search tool for grounded, cited findings + LangSmith tracing.
- **Frontend**: React (Vite) — submit a target company, watch each specialist agent light up as it
  works, then read the finished report with source citations.
- **Production practices**: typed settings, structured logging, centralized error handling, rate
  limiting, dependency injection, a fully-mocked test suite (no network calls, no API cost), ruff +
  mypy in CI, multi-stage Docker builds, GitHub Actions.

Read `ARCHITECTURE.md` alongside this file for the design rationale behind the graph topology, the
fan-out/fan-in pattern, and the observability setup.

---

## 1. Prerequisites (install these first)

| Tool | Version | Check |
|---|---|---|
| Python | 3.11+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| npm | 10+ | `npm --version` |
| Docker Desktop (optional, for containerized run) | latest | `docker --version` |
| An Anthropic API key | — | https://console.anthropic.com/settings/keys |

macOS: `brew install python@3.11 node`
Windows: install Python from python.org (check "Add to PATH") and Node from nodejs.org.
Linux: use your package manager, or `pyenv`/`nvm` if you want version isolation.

---

## 2. Run it locally (no Docker) — fastest path to a working demo

### 2.1 Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt   # installs runtime + test + lint tooling

cp .env.example .env
# open .env and paste your real key into ANTHROPIC_API_KEY=

uvicorn app.main:app --reload --port 8000
```

Visit **http://localhost:8000/docs** — FastAPI's auto-generated Swagger UI. Try `GET /health`.

### 2.2 Frontend (in a second terminal)

```bash
cd frontend
npm install
npm run dev
```

Visit **http://localhost:5173**. Vite's dev-server proxy (`vite.config.js`) forwards `/api/*` to
the backend on port 8000, so there's no CORS setup needed in dev.

Enter a target company (competitors are optional — the planner discovers them if you leave the
field blank) and hit **Run analysis**. Watch the agent-trace board light up: a planner step, then
four specialist agents (company, market, financial, news) working in parallel, then a
synthesizer/critic pair drafting and reviewing the report, then the finished brief with citations.

---

## 3. Run the tests

```bash
cd backend
source .venv/bin/activate
pytest                    # runs the full backend suite with coverage
pytest tests/unit         # just the node/job-store unit tests (fast, no ASGI app)
pytest -k critic          # run tests matching a keyword
pytest -x                 # stop on first failure — good while debugging
```

No tests hit the real Anthropic API — `tests/conftest.py` wires in a fake Claude client (including
a fake `complete_with_search`), so the suite runs in well under a second and never costs API
credits or flakes on network issues.

### Lint & type-check (what CI runs)

```bash
ruff check .              # style/correctness lint
ruff format --check .     # formatting check (use `ruff format .` to auto-fix)
mypy app                  # static type-check
```

---

## 4. Run it with Docker (closer to production)

```bash
cd backend && cp .env.example .env   # fill in ANTHROPIC_API_KEY
cd ..
docker compose up --build
```

- Frontend: **http://localhost:8080** (nginx serving the built React app, proxying `/api/*` to
  the backend container)
- Backend directly: **http://localhost:8000**

`docker compose down` to stop. This is the same shape you'd hand to a stakeholder or deploy to a
single VM — two containers, one compose file, health-checked startup ordering.

---

## 5. Project layout

```
deep-research-agent/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory + lifespan (incl. LangSmith env bridge)
│   │   ├── config.py            # typed Settings (pydantic-settings)
│   │   ├── logging_config.py    # structlog setup
│   │   ├── exceptions.py        # domain errors + handlers
│   │   ├── middleware.py        # request-id/timing middleware
│   │   ├── agents/
│   │   │   ├── state.py         # LangGraph state (TypedDict)
│   │   │   ├── nodes.py         # planner/synthesizer/critic/finalizer
│   │   │   ├── specialists.py   # shared factory for the 4 parallel research agents
│   │   │   ├── graph.py         # StateGraph assembly (fan-out/fan-in + revision loop)
│   │   │   └── claude_client.py # Anthropic API wrapper (retries, web search, LangSmith)
│   │   ├── services/
│   │   │   ├── job_store.py        # async in-memory job store
│   │   │   └── analysis_service.py # background task orchestration
│   │   ├── api/                 # routers: health, analyses
│   │   └── models/schemas.py    # Pydantic request/response contracts
│   ├── tests/{unit,integration}
│   ├── Dockerfile, requirements*.txt, pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/analysis/ (AnalysisForm, AgentTraceBoard, ReportView, ...)
│   │   ├── api/client.js        # fetch-based client
│   │   └── styles/index.css
│   ├── Dockerfile, nginx.conf
├── docker-compose.yml
├── .github/workflows/ci.yml
├── Makefile
└── ARCHITECTURE.md              # <- read this for the design rationale
```

---

## 6. Observability (LangSmith)

Tracing is off by default. To turn it on, set in `backend/.env`:

```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=ls-...          # https://smith.langchain.com/settings
LANGSMITH_PROJECT=fieldnote-competitive-intelligence
```

With tracing on, every analysis run shows up in your LangSmith project as a nested trace: the
graph run, each node run underneath it (including the four parallel specialists), and every
Claude API call underneath its node — token usage, latency, and cost included. See
`ARCHITECTURE.md` for how this is wired without needing `langchain-anthropic`.

---

## 7. Debugging tips

- **"ANTHROPIC_API_KEY not set" / 401 errors**: check `backend/.env` has a real key and that you
  restarted uvicorn after editing it (env vars are read once at startup via `pydantic-settings`).
- **400 error mentioning `anthropic-workspace-id`**: your API key is identity-linked rather than
  workspace-scoped. Find your workspace ID in the Console (Settings → Workspaces → click the
  workspace) and set `ANTHROPIC_WORKSPACE_ID` in `backend/.env` — `ClaudeClient` sends it as a
  default header on every request once set.
- **Frontend shows "backend offline"**: confirm the backend is running on port 8000 and check the
  browser console/Network tab for the failed `/api/health` request.
- **An analysis stays "pending"/"running" forever**: check the uvicorn terminal for a traceback —
  the background task logs are your best debugging tool; also check `job.error` in the
  `GET /analyses/{id}` response.
- **Tests fail with a real network/API error**: you likely added a node that calls Claude without
  going through the mocked paths in `conftest.py`. Every node should take its dependencies as
  constructor arguments so tests can substitute fakes.

---

## 8. Scaling this to production (what I'd change, and why I didn't build it here)

This repo intentionally keeps some things simple for a single-process demo:

- **Job store**: in-memory `dict` behind an `asyncio.Lock`, fine for one process. For multiple
  uvicorn workers or replicas, swap `JobStore` for a Redis- or Postgres-backed implementation —
  the interface is narrow enough that it's a single new class, not a rewrite.
- **Background tasks**: `asyncio.create_task` works for one process; for real durability
  (survive a restart mid-job, retry on crash) you'd move job execution to a task queue (Celery,
  Arq, or a durable workflow engine) with the FastAPI process only enqueuing work.
- **LangGraph checkpointing**: this graph is stateless between runs. LangGraph supports a
  `checkpointer` (e.g. backed by Postgres) so a long-running graph can be paused/resumed/replayed
  — worth adding once analyses need to survive a process restart mid-run.
- **Rate limiting**: `slowapi`'s in-memory limiter resets per-process; a multi-instance deployment
  needs a shared store (Redis) for limits to be enforced correctly across instances.
- **Secrets**: `.env` is fine locally; in production use a secrets manager (AWS Secrets Manager,
  GCP Secret Manager, Vault) injected as environment variables at deploy time, never baked into
  the image.
- **Observability**: LangSmith tracing (§6) covers the agent pipeline; structlog's JSON output in
  production is ready to ship to any log aggregator, and OpenTelemetry tracing would round out
  cross-service latency breakdowns once there's more than one service.
