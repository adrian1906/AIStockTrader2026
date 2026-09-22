# AI Stock Trader 2026

This is a fork of [Ed Donner](https://github.com/ed-donner)'s **Trading Floor** project — the
[`6_mcp`](https://github.com/ed-donner/agents/tree/main/6_mcp/) capstone from his
[*Complete Agentic AI Engineering Course*](https://github.com/ed-donner/agents). All credit for the
original design goes to Ed; this fork carries local modifications on top of it.

Four autonomous LLM trading agents — Warren, George, Ray and Cathie, each modelled after a different
real-world investing style — run on a schedule, research the market via an MCP-tool-equipped
researcher sub-agent, and place simulated trades against a paper-money account. A Gradio dashboard and
a separate read-only web frontend both show live account state, holdings and activity logs.

## Architecture

- **`backend/`** — the trading engine: account state (`accounts.py`), share prices (`market.py`),
  the trader agents and their MCP servers (`traders.py`, `trading_floor.py`, `mcp_servers.py`), and a
  read-only FastAPI layer (`api.py`) for the decoupled frontend.
- **`demo/`** — a Gradio dashboard that reads `accounts.db` in-process.
- **`frontend/`** — a small TypeScript/Vite app that polls `backend/api.py` over HTTP instead.
- **`1_lab1.ipynb`–`5_lab5.ipynb`** — the original course notebooks that build up to this app.

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
   USE_MANY_MODELS=false                # optional, spreads traders across 4 different models
   ```

3. Reset/seed the four trader accounts:

   ```bash
   python -m backend.reset
   ```

4. Run it:

   ```bash
   # Gradio dashboard (starts the trading floor + UI together)
   python app.py

   # or, for the decoupled frontend:
   uv run uvicorn backend.api:app --port 8000   # from a shell with the backend deps installed
   cd frontend && npm run dev
   ```

`accounts.db` is created on first run and is gitignored — it's local paper-trading state, not
something to commit.
