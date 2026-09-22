"""Share prices from the Massive market data API, or a simulator when no key is set.

Set MASSIVE_API_KEY to use live data. Without it, prices come from market_simulator
so the whole trading floor still runs out of the box.

With a key configured, a failed fetch never falls back to a simulated price - a
fabricated number could corrupt real trades and account history. It retries briefly
to ride out transient blips, then raises MarketDataUnavailable so callers fail loudly
instead of trading on fake data.
"""

import os
import time
from dotenv import load_dotenv
from massive import RESTClient
from .market_simulator import simulated_price

load_dotenv(override=True)

massive_api_key = os.getenv("MASSIVE_API_KEY")


class MarketDataUnavailable(RuntimeError):
    """Raised when a live price can't be fetched from Massive after retries."""


# Massive's free tier allows ~5 requests/minute, and a trading floor with several
# traders can easily ask for the same symbol's price many times a minute. Cache
# each symbol's price for a bit so we don't burn through that quota unnecessarily.
CACHE_TTL_SECONDS = 60
_price_cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, fetched_at)

# Retry the whole tier chain a few times with backoff before giving up, so a
# momentary network blip or transient Massive error doesn't immediately fail a trade.
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0


def _last_trade(client: RESTClient, symbol: str) -> float:
    return float(client.get_last_trade(symbol).price)


def _snapshot(client: RESTClient, symbol: str) -> float:
    snapshot = client.get_snapshot_ticker("stocks", symbol)
    return float(snapshot.min.close or snapshot.prev_day.close)


def _previous_close(client: RESTClient, symbol: str) -> float:
    return float(client.get_previous_close_agg(symbol)[0].close)


# Best price first, prior close last. Lower tier plans reject the earlier calls,
# so we remember the first tier that works and start there next time.
price_methods = [_last_trade, _snapshot, _previous_close]
plan_tier = 0


def get_share_price(symbol: str) -> float:
    """Return the current price for a symbol.

    Without a Massive key, this is simulated by design. With a key, it's always a
    real Massive price or an exception - never a silent fallback to simulated data.
    """
    if massive_api_key:
        return get_share_price_massive(symbol)
    return simulated_price(symbol)


def get_share_price_massive(symbol: str) -> float:
    """Best real price the plan allows, remembering the working tier to avoid repeat failures.

    Cached briefly per symbol so repeated lookups (e.g. valuing a portfolio held by
    several traders) don't blow through the plan's rate limit. Retries the tier chain
    a few times with backoff before raising MarketDataUnavailable.
    """
    global plan_tier
    cached = _price_cache.get(symbol)
    if cached and time.monotonic() - cached[1] < CACHE_TTL_SECONDS:
        return cached[0]

    client = RESTClient(massive_api_key)
    last_error: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        for tier in range(plan_tier, len(price_methods)):
            try:
                price = price_methods[tier](client, symbol)
                plan_tier = tier
                _price_cache[symbol] = (price, time.monotonic())
                return price
            except Exception as e:
                last_error = e
                continue
        if attempt < RETRY_ATTEMPTS - 1:
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise MarketDataUnavailable(f"No Massive price available for {symbol}") from last_error


def is_market_open() -> bool:
    """Whether the US market is open; True on simulated data or if Massive is unreachable."""
    if not massive_api_key:
        return True
    try:
        client = RESTClient(massive_api_key)
        return client.get_market_status().market == "open"
    except Exception:
        return True
