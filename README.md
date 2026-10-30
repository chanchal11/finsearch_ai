# Investment Agent App

Production-oriented, **SOLID** multi-agent investment research engine built with the [Strands Agents SDK](https://strandsagents.com/), Alpha Vantage, Tavily, and an in-memory TTL cache. The same orchestration core runs unchanged behind **Streamlit** (interactive streaming UI) or **FastAPI** (REST + SSE).

## Architecture

| Layer | Responsibility |
| --- | --- |
| `src/providers/` | Vendor adapters (`IFinancialDataProvider`, `INewsDataProvider`) |
| `src/tools/` | Financial math & Markdown formatters (depend on interfaces only) |
| `src/agents/` | Specialist personas + Managing Director orchestrator |
| `src/services/` | Framework-agnostic `InvestmentCommitteeService` |
| `app.py` / `api.py` | Delivery mechanisms (no business logic) |

## Setup (uv — recommended)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) once, then from the repo root:

**Linux / macOS / WSL**

```bash
cd finsearch_ai
uv python pin 3.14          # optional; uses .python-version if present
uv sync --all-groups        # creates .venv, installs deps + dev tools, editable package
cp .env.example .env        # add API keys + STRANDS_MODEL
```

**Windows (PowerShell)**

```powershell
cd finsearch_ai
uv python pin 3.14
uv sync --all-groups
Copy-Item .env.example .env
```

You do **not** need `source .venv` / `Activate.ps1` for daily use — prefix commands with `uv run` (see below). To activate anyway: `.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (Unix).

### After changing dependencies

```bash
uv add some-package          # add runtime dep (updates pyproject.toml + uv.lock)
uv add --dev ruff            # or use dependency-groups in pyproject.toml
uv lock                      # refresh lockfile only
uv sync --all-groups         # install from lock
```

### Required environment

- `ALPHA_VANTAGE_API_KEY`
- `TAVILY_API_KEY`
- `STRANDS_PROVIDER` — `bedrock` (default), `ollama`, or `groq`
- `STRANDS_MODEL` — Bedrock model id, an Ollama model name such as `llama3.1`, or a Groq model id such as `llama-3.3-70b-versatile`
- `OLLAMA_HOST` — Ollama server URL, used only when `STRANDS_PROVIDER=ollama` (default `http://127.0.0.1:11434`)
- `GROQ_API_KEY` — required when `STRANDS_PROVIDER=groq`
- `GROQ_BASE_URL` — Groq OpenAI-compatible endpoint (default `https://api.groq.com/openai/v1`)
- Provider credentials matching your model (AWS for Bedrock; Ollama needs the server running and the model pulled)

## Run Streamlit UI

```bash
uv run streamlit run app.py
```

PowerShell: same command (`uv run` works on Windows).

Features: ticker + peers input, live token streaming, specialist tool status, cache inspection and purge.

## Run FastAPI

```bash
uv run uvicorn api:app --reload --port 8000
```

### Endpoints

- `POST /api/v1/evaluate` — synchronous JSON report
- `GET /api/v1/evaluate/stream?symbol=AAPL&peers=MSFT,GOOGL` — SSE token/tool events
- `DELETE /api/v1/cache` — purge TTL cache
- `GET /health` — liveness

## Extending providers (Open/Closed)

Implement `IFinancialDataProvider` or `INewsDataProvider` in `src/providers/` and wire the instance in `src/bootstrap.py`. Agents and tools remain untouched.

## Disclaimer

This project is for research and education. It is not investment advice.
