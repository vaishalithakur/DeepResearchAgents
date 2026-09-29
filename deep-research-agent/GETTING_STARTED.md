# Getting Started From Zero — Setup, VS Code, and Your Week to Mastery

This assumes you have never set up a dev environment before. Follow it top to bottom, in order.
Don't skip steps even if they look obvious — this is written so nothing is assumed.

---

## Part 1 — Install the tools (do this once)

You need five things on your laptop. Install them in this order.

### 1.1 A terminal (you probably already have one)

- **macOS**: press `Cmd + Space`, type "Terminal", hit enter.
- **Windows**: press the Windows key, type "PowerShell", hit enter. (Use PowerShell, not the old
  `cmd.exe`.)
- **Linux**: you know where it is.

Every command below with a `$` in front is something you type into this terminal, then press
Enter. Don't type the `$` itself.

### 1.2 Git (version control — lets you download/manage code)

- **macOS**: open Terminal and run:
  ```
  $ git --version
  ```
  If it's not installed, macOS will prompt you to install "Command Line Developer Tools" — click
  Install.
- **Windows**: download and run the installer from https://git-scm.com/download/win — accept all
  the defaults.
- **Linux**: `sudo apt install git` (Ubuntu/Debian) or your distro's equivalent.

Verify it worked:
```
$ git --version
git version 2.xx.x
```

### 1.3 Python 3.11 or newer

- **macOS**:
  ```
  $ brew install python@3.11
  ```
  (If you don't have Homebrew yet, install it first from https://brew.sh — the site gives you one
  command to paste into Terminal.)
- **Windows**: go to https://www.python.org/downloads/, download the latest 3.11+ installer.
  **Important**: on the first install screen, check the box **"Add python.exe to PATH"** before
  clicking Install — this is the single most common thing people forget.
- **Linux**: `sudo apt install python3.11 python3.11-venv`

Verify:
```
$ python3 --version
Python 3.11.x
```
(On Windows, the command might be `python` instead of `python3` — try both.)

### 1.4 Node.js 20 or newer (for the React frontend)

- **macOS**: `brew install node`
- **Windows/Linux**: download the "LTS" installer from https://nodejs.org and run it, accepting
  the defaults.

Verify:
```
$ node --version
v20.x.x
$ npm --version
10.x.x
```

### 1.5 VS Code (the code editor you'll work in)

Download from https://code.visualstudio.com and install it like any normal application.

### 1.6 (Optional but recommended) Docker Desktop

Only needed for the "run it in containers" step later in the week, not for day-to-day
development. Download from https://www.docker.com/products/docker-desktop — install it, then open
it once so it finishes its own setup.

### 1.7 An Anthropic API key

Go to https://console.anthropic.com/settings/keys, sign up/log in, and create an API key. Copy it
somewhere safe (a notes app) — you'll paste it into a config file in a minute. **Never share this
key or commit it to a public repository** — treat it like a password.

---

## Part 2 — Unzip the project and open it in VS Code

1. Find `deep-research-agent.zip` wherever you downloaded it, and unzip it. On macOS, double-click
   it. On Windows, right-click → "Extract All". You'll get a folder called `deep-research-agent`.
2. Open VS Code.
3. Go to **File → Open Folder...** (macOS: **File → Open...**) and select the `deep-research-agent`
   folder. VS Code's file explorer on the left should now show `backend/`, `frontend/`, `README.md`,
   etc.
4. Open the built-in terminal **inside VS Code**: menu bar → **Terminal → New Terminal**, or the
   shortcut `` Ctrl+` `` (backtick, the key above Tab). A terminal panel opens at the bottom,
   already pointed at the `deep-research-agent` folder. **Use this terminal for every command
   below** — it saves you from `cd`-ing around manually.

### 2.1 Install two VS Code extensions (makes everything easier)

Click the Extensions icon in the left sidebar (looks like four squares), search for and install:

- **Python** (by Microsoft) — gives you syntax highlighting, autocomplete, and lets VS Code know
  about your virtual environment (explained below).
- **ESLint** (by Microsoft) — same idea, for the JavaScript/React side.

You don't strictly need more than these two to get going. Nice-to-haves later: **Pylance**
(usually installs automatically with the Python extension), **Docker** (by Microsoft, if you'll
use Docker), **GitLens** (richer git history view).

---

## Part 3 — What a "virtual environment" is, and why you need one

Different Python projects need different, sometimes conflicting, versions of libraries. A
**virtual environment** (venv) is an isolated folder holding one project's own copy of Python
packages, so installing something for this project never breaks another project on your machine.
You create one venv per project, once, and "activate" it every time you work on that project.

You'll see this in the commands below:
```
$ python3 -m venv .venv          # creates the isolated environment (do this once)
$ source .venv/bin/activate      # "enters" it (do this every time you open a new terminal)
```
On Windows PowerShell, activation is: `.venv\Scripts\activate` instead.

When it's active, your terminal prompt gets a `(.venv)` prefix — that's your visual confirmation
you're "inside" the right environment before installing anything or running the app.

---

## Part 4 — Run the backend (FastAPI + LangGraph)

In the VS Code terminal:

```
$ cd backend
$ python3 -m venv .venv
$ source .venv/bin/activate
```
*(Windows: `.venv\Scripts\activate`)*

```
$ pip install -r requirements-dev.txt
```
This downloads every Python package the project needs (FastAPI, LangGraph, the Anthropic SDK,
pytest, etc.) into `.venv`. It'll take a minute or two the first time.

Now set up your API key:
```
$ cp .env.example .env
```
*(Windows: `copy .env.example .env`)*

Open the new `.env` file in VS Code (click it in the file explorer on the left) and replace
`sk-ant-api03-your-key-here` with the real key you copied earlier. Save the file (`Ctrl+S` /
`Cmd+S`).

(Optional) if you want to see each analysis run traced in [LangSmith](https://smith.langchain.com),
set `LANGSMITH_TRACING=true` and paste a key into `LANGSMITH_API_KEY=` in the same `.env` file.
Leave it as `false` if you don't have a LangSmith account — everything else works fine either way.

Now start the server:
```
$ uvicorn app.main:app --reload --port 8000
```

You should see log lines ending in something like `Uvicorn running on http://127.0.0.1:8000`.
Open your web browser and go to **http://localhost:8000/docs** — you should see an interactive
API documentation page. That means the backend is alive. Leave this terminal running.

**To stop the server**: click into that terminal and press `Ctrl+C`.

### Selecting the right Python interpreter in VS Code

The first time you open a `.py` file, VS Code might not know about your `.venv`. Press
`Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux) to open the Command Palette, type
"Python: Select Interpreter", and choose the one that shows a path ending in
`backend/.venv/bin/python`. This makes VS Code's autocomplete and error-checking match exactly
what you're actually running — do this once per project.

---

## Part 5 — Run the frontend (React)

Open a **second** terminal in VS Code (click the `+` icon in the terminal panel, or
`` Ctrl+Shift+` ``) so your backend keeps running in the first one.

```
$ cd frontend
$ npm install
```
This downloads all the JavaScript packages (React, Vite, etc.) — also takes a minute the first
time.

```
$ npm run dev
```

You'll see a message like `Local: http://localhost:5173/`. Open that URL in your browser. You
should now see the "Fieldnote Intelligence" app: a form on the left to start an analysis, an empty
state on the right prompting you to enter a company.

**Try it**: type a company name (e.g. "Anthropic") into "Target company" on the left and hit **Run
analysis**. Watch the agent-trace board on the right: a planner step, then four specialist agent
cards (company, market, financial, news) lighting up as they research in parallel, then a
synthesizer and critic step, then the finished report with source citations.

If you see "backend offline" in the top-right status pill, double check the first terminal is
still running the backend without errors.

**To stop the frontend**: click into that terminal and press `Ctrl+C`.

---

## Part 6 — The absolute basics, explained

A few concepts that everything else depends on, in plain terms:

- **Terminal / command line**: a text-based way to run programs, instead of clicking icons. Every
  command is just the name of a program plus arguments telling it what to do.
- **`localhost` / `127.0.0.1`**: both mean "this computer, right now." When something says
  `http://localhost:8000`, that's a website being served *from your own laptop*, not the internet
  — that's why it stops working the moment you stop the server.
- **Port**: a number identifying *which* program on your computer a request should go to. `8000`
  is the backend, `5173` is the frontend dev server. Two programs can't use the same port at the
  same time.
- **Environment variable**: a named piece of configuration (like your API key) that lives outside
  your code, so secrets never get hard-coded into files you might accidentally share or commit to
  git. `.env` is where this project keeps them locally; `.env.example` is a template with no real
  secrets, safe to share.
- **`pip` vs `npm`**: both are "package managers" — programs that download and install libraries
  other people wrote so you don't reinvent them. `pip` is Python's; `npm` is JavaScript's.
- **API**: a defined way for one program to ask another program to do something over the network
  (here, HTTP requests). "Calling the Claude API" means your backend sends a request to
  Anthropic's servers and gets a response back.
- **Frontend vs backend**: the frontend (React) is what runs in the user's browser and draws the
  screen. The backend (FastAPI) runs on a server, holds the real logic and the API key, and the
  frontend talks to it over HTTP. The API key should *never* live in frontend code — anyone could
  open their browser's dev tools and steal it.

---

## Part 7 — Run the tests (do this early — it builds real confidence)

Still in the `backend` terminal, with `.venv` active:
```
$ pytest
```
You should see `22 passed` at the bottom. This is the single fastest way to confirm your setup is
correct — if the tests pass, your environment is good, no guesswork needed.

Try breaking something on purpose to see a test fail and understand the feedback loop: open
`backend/app/agents/nodes.py`, find the `finalizer` function, and temporarily change
`state.get("draft_report", "")` to `state.get("draft_report", "") + "!!"`. Save, rerun `pytest` —
watch `test_finalizer_copies_draft_and_dedupes_sources_by_url` fail with a clear diff showing what
it expected vs. what it got. Undo your change (`Ctrl+Z` in the editor, then save again), rerun,
watch it pass. This is exactly the workflow you'll use for real changes.

---

## Part 8 — Debugging inside VS Code (instead of only reading logs)

This is worth setting up on day 1 — it will save you hours over the week.

1. In VS Code, click the **Run and Debug** icon in the left sidebar (a play button with a bug).
2. Click **"create a launch.json file"**, choose **Python**, then **FastAPI**.
3. VS Code generates a config. Make sure the `module` or `program` points at running
   `uvicorn app.main:app` from inside the `backend` folder (VS Code usually gets this right
   automatically once it detects FastAPI).
4. Click the green **Run/Debug** arrow. Now set a **breakpoint** by clicking in the left margin
   next to any line of code (a red dot appears) — for example, inside
   `backend/app/api/routes_analyses.py`'s `create_analysis` function.
5. Trigger that code path (submit an analysis in the browser). VS Code will pause execution right
   there, and you can hover over variables to see their actual values, step through line by line
   with the toolbar that appears, and understand exactly what's happening — far more effective
   than scattering `print()` statements everywhere.

You can do the same for tests: right-click any test function in `backend/tests/` and choose
**"Debug Test"** from the menu VS Code adds once the Python extension recognizes pytest.

---

## Part 9 — Understanding the codebase

Once it's running, `ARCHITECTURE.md` in the project root is the doc to read next — it walks
through the LangGraph pipeline (planner → four parallel specialist agents → synthesizer/critic
revision loop → finalizer), why the design decisions were made the way they were, and how the web
search and LangSmith tracing integrations work. Read it alongside the code it references:

- `backend/app/agents/state.py`, `nodes.py`, `specialists.py`, `graph.py` — the graph itself.
- `backend/app/agents/claude_client.py` — the Anthropic API wrapper (retries, web search, tracing).
- `backend/app/services/analysis_service.py`, `job_store.py` — job orchestration.
- `backend/tests/` — read a test's name, guess what it checks, then read the body and see if you
  were right. `conftest.py` explains the mocking pattern every other test relies on.

---

## Part 10 — If something goes wrong

- **`command not found: python3` / `pip` / `npm`**: the install in Part 1 didn't finish or wasn't
  added to your PATH. Close and reopen your terminal completely (a fresh terminal window, not just
  a new tab) and try again; on Windows this is the most common fix.
- **`ModuleNotFoundError` when running the backend**: your virtual environment probably isn't
  active. Look for `(.venv)` at the start of your terminal prompt — if it's missing, run
  `source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows) again.
- **Port already in use**: something else is already running on 8000 or 5173. Find and stop it
  (often a leftover terminal from earlier), or ask the tool to use a different port
  (`uvicorn app.main:app --reload --port 8001`, then update your requests accordingly).
- **Tests or the app fail with an "Anthropic API" error**: check `backend/.env` actually has your
  real key (not the placeholder text), and that you restarted `uvicorn` after editing it. If the
  error specifically mentions `anthropic-workspace-id`, your key is identity-linked rather than
  workspace-scoped — find your workspace ID in the Console (Settings → Workspaces) and set
  `ANTHROPIC_WORKSPACE_ID` in `backend/.env`.
- **Stuck for more than 15 minutes on the same error**: paste the exact error message into a fresh
  chat with Claude, along with which command you ran and which file you were editing — a precise
  error message is almost always solvable quickly once someone (or something) can see it directly.
