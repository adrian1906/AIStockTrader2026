"""Compiles each trader's recorded session narratives into a readable digest.

Meant to run a couple of times a day (see DIGEST_TIMES in trading_floor.py) rather than
after every trading round - a round happens every RUN_EVERY_N_MINUTES, which would be far
more reading than anyone wants, so raw narratives accumulate in the sessions table and get
compiled into a digest only at the configured times.

The raw narrative (tool calls, their arguments, their results, the model's own messages) is
grounding material, not something a human should have to read directly - it's dense and full
of raw JSON. A cheap model turns it into a few actual paragraphs: what was consulted, how it
was read, and what was decided (including an explicit "chose not to trade" and why).
"""

from datetime import datetime

from openai import AsyncOpenAI

from .database import read_latest_digest, read_sessions_since, write_digest
from .trading_floor import names

DIGEST_MODEL = "gpt-5.4-mini"

SUMMARY_SYSTEM_PROMPT = """You summarize a trading agent's activity for the person overseeing it, \
who wants to understand the agent's process, not just its outcome. You'll be given a raw record of \
tool calls, their arguments, their results, and the agent's own messages, covering one or more \
trading rounds for one trader.

Write a few clear, readable paragraphs (plain prose, not bullet points) covering, per round if there \
are several: what sources or data the agent consulted and what it found, how it interpreted that \
information, and what action it took - including an explicit "chose not to trade" with its stated \
reasoning, if that's what happened. Stay strictly grounded in the record: never invent numbers, \
sources, or reasoning that isn't actually there. Write for a reader with no context on the raw log \
format - they just want to know what the agent actually did and why."""


def _render_step(step: dict) -> str:
    if step["type"] == "tool_call":
        args = step.get("args") or ""
        args = args if args not in ("", "{}") else ""
        return f"- Consulted `{step['tool']}`" + (f" with `{args}`" if args else "")
    if step["type"] == "tool_output":
        return f"  - Returned: {step['output']}"
    if step["type"] == "message":
        return f"- Said: {step['text']}"
    return ""


def _render_raw_narrative(name: str, since: str) -> tuple[str, int]:
    """The raw step-by-step record, as grounding material for the summarizer - not for direct

    display. Returns the rendered text and how many rounds it covers.
    """
    sessions = read_sessions_since(name, since)
    lines = []
    for session in sessions:
        lines.append(f"## Round at {session['datetime']} ({session['kind']})")
        for step in session["narrative"]:
            rendered = _render_step(step)
            if rendered:
                lines.append(rendered)
        lines.append("")
    return "\n".join(lines), len(sessions)


async def summarize_narrative(name: str, raw_narrative: str) -> str:
    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model=DIGEST_MODEL,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"Trader: {name}\n\n{raw_narrative}"},
        ],
    )
    return response.choices[0].message.content


async def compile_and_store_digest(slot: str) -> None:
    """Build and persist a digest per trader, covering everything since each one's last digest."""
    start_of_today = datetime.now().strftime("%Y-%m-%d 00:00:00")
    for name in names:
        latest = read_latest_digest(name)
        since = latest["datetime"] if latest else start_of_today
        raw_narrative, round_count = _render_raw_narrative(name, since)
        if round_count == 0:
            report = "No trading rounds recorded in this period."
        else:
            report = await summarize_narrative(name, raw_narrative)
        write_digest(name, slot, report)
