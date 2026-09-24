from .traders import Trader
from typing import List
import asyncio
from datetime import datetime
from .tracers import LogTracer
from agents import add_trace_processor
from .market import is_market_open
from dotenv import load_dotenv
import os

load_dotenv(override=True)

RUN_EVERY_N_MINUTES = int(os.getenv("RUN_EVERY_N_MINUTES", "60"))
RUN_EVEN_WHEN_MARKET_IS_CLOSED = (
    os.getenv("RUN_EVEN_WHEN_MARKET_IS_CLOSED", "false").strip().lower() == "true"
)
USE_MANY_MODELS = os.getenv("USE_MANY_MODELS", "false").strip().lower() == "true"

# Times of day (local, "HH:MM", comma-separated) at which each trader's recorded
# sessions since the last digest get compiled into a Markdown report - see backend/digest.py.
# Checked once per scheduler tick, so it fires on the first tick at or after each time,
# which can lag by up to RUN_EVERY_N_MINUTES.
DIGEST_TIMES = [t.strip() for t in os.getenv("DIGEST_TIMES", "08:00,12:00,17:00").split(",") if t.strip()]

names = ["Warren", "George", "Ray", "Cathie"]
lastnames = ["Patience", "Bold", "Systematic", "Crypto"]

if USE_MANY_MODELS:
    model_names = [
        "gpt-5.5",
        "deepseek-v4-flash",
        "gemini-3.5-flash",
        "grok-4.3",
    ]
    short_model_names = ["GPT 5.5", "DeepSeek V4", "Gemini 3.5 Flash", "Grok 4.3"]
else:
    model_names = ["gpt-5.4-mini"] * 4
    short_model_names = ["GPT 5.4 mini"] * 4


def create_traders() -> List[Trader]:
    traders = []
    for name, lastname, model_name in zip(names, lastnames, model_names):
        traders.append(Trader(name, lastname, model_name))
    return traders


def _due_digest_slots(last_sent: dict[str, str]) -> list[str]:
    """Digest slots whose time has passed today and haven't been sent yet today."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    due = []
    for slot in DIGEST_TIMES:
        hour, minute = map(int, slot.split(":"))
        slot_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= slot_time and last_sent.get(slot) != today:
            due.append(slot)
    return due


async def run_every_n_minutes():
    from .digest import compile_and_store_digest

    add_trace_processor(LogTracer())
    traders = create_traders()
    last_digest_sent: dict[str, str] = {}
    while True:
        if RUN_EVEN_WHEN_MARKET_IS_CLOSED or is_market_open():
            await asyncio.gather(*[trader.run() for trader in traders])
        else:
            print("Market is closed, skipping run")
        for slot in _due_digest_slots(last_digest_sent):
            compile_and_store_digest(slot)
            last_digest_sent[slot] = datetime.now().strftime("%Y-%m-%d")
        await asyncio.sleep(RUN_EVERY_N_MINUTES * 60)


if __name__ == "__main__":
    print(f"Starting scheduler to run every {RUN_EVERY_N_MINUTES} minutes")
    asyncio.run(run_every_n_minutes())
