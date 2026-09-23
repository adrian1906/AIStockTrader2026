"""HTTP API over the trading floor, for a separate frontend to consume.

The Gradio dashboard in demo/ reads accounts.db in-process. This serves the same
data as JSON so a decoupled web frontend can render it. Everything here is
read-only; the trading floor writes the database out of band.

Run it from the project root so it shares the engine's accounts.db:

    uvicorn backend.api:app --port 8000

If frontend/dist exists (built with `npm run build`), it's served from this same
process at "/" - one process, one port, no CORS - which is what you want for a
single tunnelled origin rather than juggling the Vite dev server separately.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend import market
from backend.accounts import Account
from backend.database import read_log
from backend.trading_floor import names, lastnames, short_model_names

# Mirrors the log colours in demo/ so the frontend reproduces the same panel.
LOG_COLORS = {
    "trace": "#87CEEB",
    "agent": "#00dddd",
    "function": "#00dd00",
    "generation": "#dddd00",
    "response": "#aa00dd",
    "account": "#dd0000",
}
DEFAULT_LOG_COLOR = "#87CEEB"

roster = [
    {"name": name, "lastname": lastname, "model_name": model_name}
    for name, lastname, model_name in zip(names, lastnames, short_model_names)
]
roster_by_name = {trader["name"].lower(): trader for trader in roster}

app = FastAPI(title="Trading Floor")


def average_cost(account: Account, symbol: str) -> float:
    """Average price paid across this symbol's buys, for per-holding profit."""
    spend = sum(t.price * t.quantity for t in account.transactions if t.symbol == symbol and t.quantity > 0)
    bought = sum(t.quantity for t in account.transactions if t.symbol == symbol and t.quantity > 0)
    return spend / bought if bought else 0.0


def holdings_detail(account: Account) -> list[dict]:
    """Current holdings enriched with price, market value and unrealised profit.

    A symbol whose live price can't be fetched is reported as unavailable rather
    than falling back to a fabricated number or failing the whole request.
    """
    details = []
    for symbol, quantity in account.holdings.items():
        cost = average_cost(account, symbol)
        try:
            price = market.get_share_price(symbol)
        except market.MarketDataUnavailable:
            details.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": None,
                    "avg_cost": cost,
                    "market_value": None,
                    "unrealized_pnl": None,
                }
            )
            continue
        details.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "price": price,
                "avg_cost": cost,
                "market_value": price * quantity,
                "unrealized_pnl": (price - cost) * quantity,
            }
        )
    return details


def require_trader(name: str) -> dict:
    trader = roster_by_name.get(name.lower())
    if not trader:
        raise HTTPException(status_code=404, detail=f"Unknown trader {name}")
    return trader


@app.get("/api/traders")
def get_traders() -> list[dict]:
    """The four traders on the floor."""
    return roster


@app.get("/api/market")
def get_market() -> dict:
    """Which price source is live, and whether the market is open."""
    source = "massive" if market.massive_api_key else "simulator"
    return {"source": source, "is_market_open": market.is_market_open()}


def trader_state(name: str) -> dict:
    """A trader's full state: value, profit, holdings, transactions and history."""
    trader = require_trader(name)
    account = Account.get(name)
    holdings = holdings_detail(account)
    # Symbols with an unavailable price (market_value None) are excluded from the
    # total rather than corrupting it - the response still marks them separately.
    portfolio_value = account.balance + sum(h["market_value"] for h in holdings if h["market_value"] is not None)
    return {
        "name": trader["name"],
        "lastname": trader["lastname"],
        "model_name": trader["model_name"],
        "balance": account.balance,
        "strategy": account.strategy,
        "portfolio_value": portfolio_value,
        "pnl": account.calculate_profit_loss(portfolio_value),
        "holdings": holdings,
        "transactions": account.list_transactions(),
        "time_series": [{"datetime": ts, "value": value} for ts, value in account.portfolio_value_time_series],
    }


@app.get("/api/traders/{name}")
def get_trader(name: str) -> dict:
    """A trader's full state: value, profit, holdings, transactions and history."""
    return trader_state(name)


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def trader_report_markdown(name: str) -> str:
    """Render a trader's state as a human-readable Markdown report."""
    state = trader_state(name)
    lines = [
        f"# {state['name']} {state['lastname']} ({state['model_name']})",
        "",
        f"- **Balance:** {_money(state['balance'])}",
        f"- **Portfolio value:** {_money(state['portfolio_value'])}",
        f"- **P&L:** {_money(state['pnl'])}",
        f"- **Strategy:** {state['strategy']}",
        "",
        "## Holdings",
    ]
    if state["holdings"]:
        lines.append("| Symbol | Qty | Price | Avg Cost | Market Value | Unrealized P&L |")
        lines.append("|---|---|---|---|---|---|")
        for h in state["holdings"]:
            lines.append(
                f"| {h['symbol']} | {h['quantity']} | {_money(h['price'])} | {_money(h['avg_cost'])} "
                f"| {_money(h['market_value'])} | {_money(h['unrealized_pnl'])} |"
            )
    else:
        lines.append("_No current holdings._")

    lines += ["", "## Recent Transactions"]
    transactions = state["transactions"][-10:]
    if transactions:
        for t in reversed(transactions):
            side = "BUY" if t["quantity"] > 0 else "SELL"
            lines.append(
                f"- `{t['timestamp']}` **{side}** {abs(t['quantity'])} {t['symbol']} @ {_money(t['price'])}"
                f" — {t['rationale']}"
            )
    else:
        lines.append("_No transactions yet._")

    return "\n".join(lines) + "\n"


@app.get("/api/traders/{name}/report", response_class=PlainTextResponse)
def get_trader_report(name: str) -> str:
    """The same data as /api/traders/{name}, rendered as a Markdown report for humans."""
    return trader_report_markdown(name)


@app.get("/api/traders/{name}/logs")
def get_trader_logs(name: str, last_n: int = 13) -> list[dict]:
    """Recent trace and account log lines, oldest first, with their panel colour."""
    require_trader(name)
    rows = list(read_log(name, last_n))
    return [
        {"datetime": ts, "type": kind, "message": message, "color": LOG_COLORS.get(kind, DEFAULT_LOG_COLOR)}
        for ts, kind, message in rows
    ]


# Registered last so it never shadows the /api/* routes above - StaticFiles(html=True)
# serves index.html for "/" and falls back to it for unknown paths, which is fine
# since this is a single-page dashboard with no client-side routes to miss.
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
