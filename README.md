# AI Stock Trader 2026

This is a fork of [Ed Donner](https://github.com/ed-donner)'s **Trading Floor** project — the
[`6_mcp`](https://github.com/ed-donner/agents/tree/main/6_mcp/) capstone from his
[*Complete Agentic AI Engineering Course*](https://github.com/ed-donner/agents). All credit for the
original design goes to Ed; this fork carries local modifications on top of it.

Four autonomous LLM trading agents — Warren, George, Ray and Cathie, each modelled after a different
real-world investing style — run on a schedule, research the market via an MCP-tool-equipped
researcher sub-agent, and place simulated trades against a paper-money account.

The trading engine (`backend/trading_floor.py`) is a separate, long-running process from the two
dashboards that display its results. A Gradio dashboard and a decoupled TypeScript/Vite frontend
both read the same `accounts.db` read-only - **neither one runs the agents**; the engine has to be
started on its own for the numbers to actually move.

## Architecture

- **`backend/`** — the trading engine: account state (`accounts.py`), share prices (`market.py`),
  the trader agents and their MCP servers (`traders.py`, `trading_floor.py`, `mcp_servers.py`), and a
  read-only FastAPI layer (`api.py`) for the decoupled frontend.
- **`demo/`** — a Gradio dashboard that reads `accounts.db` in-process.
- **`frontend/`** — a small TypeScript/Vite app that polls `backend/api.py` over HTTP instead.
- **`1_lab1.ipynb`** through **`4_lab4.ipynb`** — exploratory MCP experiments (Playwright, Context7,
  a memory/vector-db demo) from the original course, unrelated to this app and not imported by
  anything here; kept for reference.
- **`5_lab5.ipynb`** — a notebook that exercises `backend.api` directly; kept around for ad hoc
  exploration.

## Market data

Share prices come from the [Massive](https://massive.com) stock market API when `MASSIVE_API_KEY` is
set, falling back through progressively less real-time endpoints (last trade → intraday snapshot →
previous close) depending on your plan tier, with a short per-symbol cache to stay under rate limits.
Without a key, prices are simulated so the app still runs out of the box.

If a live price genuinely can't be fetched, `get_share_price` raises `MarketDataUnavailable` rather
than silently substituting a simulated value — a failed trade is preferable to a trade or account
report built on fabricated data.

## Setup

1. Install dependencies (Python 3.11+):

   ```bash
   pip install -r requirements.txt
   cd frontend && npm install
   ```

2. Create a `.env` file in the project root with whichever of these you're using:

   ```
   OPENAI_API_KEY=...          # for the default gpt-5.4-mini traders
   DEEPSEEK_API_KEY=...        # optional, for USE_MANY_MODELS=true
   GOOGLE_API_KEY=...          # optional, for USE_MANY_MODELS=true
   GROK_API_KEY=...            # optional, for USE_MANY_MODELS=true
   OPENROUTER_API_KEY=...      # optional, for openrouter-routed models

   MASSIVE_API_KEY=...         # optional; omit to run on simulated prices
   PUSHOVER_USER=...           # optional, for push notifications
   PUSHOVER_TOKEN=...          # optional, for push notifications

   RUN_EVERY_N_MINUTES=60               # optional, default 60
   RUN_EVEN_WHEN_MARKET_IS_CLOSED=false # optional
   DIGEST_TIMES=08:00,12:00,17:00       # optional, default 08:00,12:00,17:00 - see GET /api/traders/{name}/digest
   USE_MANY_MODELS=false                # optional, spreads traders across 4 different models
   ```

3. Reset/seed the four trader accounts:

   ```bash
   python -m backend.reset
   ```

4. Start the trading engine (its own process, runs every `RUN_EVERY_N_MINUTES`):

   ```bash
   python -m backend.trading_floor
   ```

5. Run a dashboard to watch it - either works, pick one:

   ```bash
   # Gradio dashboard
   python app.py

   # or the decoupled frontend, for local dev (hot reload, proxies /api to :8000):
   uvicorn backend.api:app --port 8000
   cd frontend && npm run dev   # opens on :5173
   ```

`accounts.db` is created on first run and is gitignored — it's local paper-trading state, not
something to commit.

## Running the frontend as a single origin (for a tunnel/remote demo)

For anything other than local dev, build the frontend once and let `backend/api.py` serve it
directly - one process, one port, no CORS, and only one hostname to expose:

```bash
cd frontend && npm run build   # writes frontend/dist/
cd ..
uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

`backend/api.py` auto-detects `frontend/dist/` and mounts it at `/`, alongside the existing
`/api/*` routes, whenever that directory exists. Rebuild (`npm run build`) after any frontend
change; the mount just serves whatever is currently in `dist/`.

To actually reach it from outside your machine, put a tunnel (e.g. Cloudflare Tunnel) in front of
`http://127.0.0.1:8000` rather than binding the server to a public interface directly.
