## Autonomous Local Multi-Agent System (ALMAS)

**ALMAS** is a fully local, self-triggering multi-agent research and debate system.
It uses a local Ollama server as the inference engine, LangGraph to orchestrate a
stateful workflow, and LangChain for tool integration and web search.

### 1. Features

- **Local-only inference**: Uses a local Ollama instance via its OpenAI-compatible API.
- **Signal scouting**: A scout agent queries DuckDuckGo for trending tech/science topics.
- **Topic moderation**: A moderator agent selects one topic based on novelty.
- **Multi-agent debate**: Two personas debate the topic for exactly 3 turns each:
  - **The Techno-Optimist**
  - **The Ethical Skeptic**
- **Archiving**: A secretary agent saves each debate to:
  - A local SQLite database (`data/almas.sqlite3`)
  - A human-readable Markdown snapshot in `data/*.md`
- **Autonomous loop**: The system restarts itself on a configurable interval.

### 2. Prerequisites

- **Python** 3.10+ recommended.
- **Ollama** installed and running locally.
- Sufficient disk space and network access for web search (DuckDuckGo).

### 3. Setting up Ollama

1. Install Ollama from the official site.
2. Pull a suitable model (for example Llama 3 8B):

```bash
ollama pull llama3
```

3. Start the Ollama server with its OpenAI-compatible API (default on recent versions):

```bash
ollama serve
```

By default, `main.py` expects Ollama's OpenAI-compatible endpoint at:

- base URL: `http://localhost:11434/v1`
- model name: `llama3` (configurable)

If you need to override these defaults, set:

```bash
export OLLAMA_BASE_URL="http://localhost:11434/v1"
export OLLAMA_API_KEY="local-only"   # dummy, never leaves your machine
```

> Note: The `OLLAMA_API_KEY` is only used to satisfy client libraries that expect
> a key; the value is a local dummy string and is **never** sent to external APIs.

### 4. Python environment setup

From the project root (where `main.py` and `requirements.txt` reside):

```bash
python -m venv .venv
source .venv/bin/activate   # on macOS / Linux
# .venv\Scripts\activate    # on Windows PowerShell

pip install --upgrade pip
pip install -r requirements.txt
```

All dependencies are open-source and geared for local execution:

- `langgraph`
- `langchain`, `langchain-community`, `langchain-openai`
- `ddgs` (DuckDuckGo search)
- `fastapi`, `uvicorn[standard]` (for the optional local dashboard)

### 5. Running ALMAS

Make sure Ollama is running first (`ollama serve`) and that a model such as
`llama3` is available locally.

Then, from the project root:

```bash
python main.py
```

On startup, ALMAS will:

- Discover trending tech/science topics with DuckDuckGo.
- Let the moderator select one topic.
- Run a 3-turn-per-side debate between the two personas.
- Archive the result into:
  - `data/almas.sqlite3` (SQLite database, `debates` table)
  - `data/debate_YYYYMMDD_HHMMSS.md`
- Sleep for a configured interval, then repeat.

### 6. Configuring the autonomous loop

By default, ALMAS waits **1 hour (3600 seconds)** between full cycles.
You can adjust this via the `ALMAS_INTERVAL_SECONDS` environment variable:

```bash
export ALMAS_INTERVAL_SECONDS=900   # 15 minutes
python main.py
```

### 7. Data storage and long-term memory

- All persistent data lives under the local `data/` directory created next to `main.py`.
- The SQLite database `almas.sqlite3` contains a `debates` table with:
  - `created_at`
  - `topic`
  - `transcript`
  - `topics_json` (structured candidate topics)
  - `topics_raw` (raw search JSON)
- Each debate also has a Markdown snapshot `data/debate_*.md` for quick inspection.

You can use these archives as long-term "memory" or feed them into additional tools
or dashboards, all while staying fully local.

### 8. Optional: Local web dashboard

You can run a simple read-only dashboard to browse stored debates in your browser.
It reads directly from the local SQLite database and does not call any external APIs.

1. Install the extra dependencies (already listed in `requirements.txt`):

```bash
pip install -r requirements.txt
```

2. Start the dashboard from the project root:

```bash
uvicorn dashboard:app --reload --port 8000
```

3. Open your browser to:

- `http://localhost:8000/` — list of recent debates
- Click a debate to see its full transcript.

You can keep `python main.py` running in one terminal to continuously generate
new debates while the dashboard is open in your browser.

