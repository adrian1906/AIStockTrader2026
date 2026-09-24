"""Compiles each trader's recorded session narratives into a readable Markdown digest.

Meant to run a couple of times a day (see DIGEST_TIMES in trading_floor.py) rather than
after every trading round - a round happens every RUN_EVERY_N_MINUTES, which would be far
more reading than anyone wants, so raw narratives accumulate in the sessions table and get
compiled into a digest only at the configured times.
"""

from datetime import datetime

from .database import read_latest_digest, read_sessions_since, write_digest
from .trading_floor import names


def _render_step(step: dict) -> str:
    if step["type"] == "tool_call":
        args = step.get("args") or ""
        args = args if args not in ("", "{}") else ""
        return f"- **Consulted** `{step['tool']}`" + (f" with `{args}`" if args else "")
    if step["type"] == "tool_output":
        return f"  - Returned: {step['output']}"
    if step["type"] == "message":
        return f"- **Said:** {step['text']}"
    return ""


def build_trader_digest(name: str, since: str) -> str:
    sessions = read_sessions_since(name, since)
    lines = [f"# {name} — process digest", f"_Rounds since {since}_", ""]
    if not sessions:
        lines.append("_No trading rounds recorded in this period._")
        return "\n".join(lines) + "\n"

    for session in sessions:
        lines.append(f"## Round at {session['datetime']} ({session['kind']})")
        for step in session["narrative"]:
            rendered = _render_step(step)
            if rendered:
                lines.append(rendered)
        lines.append("")
    return "\n".join(lines) + "\n"


def compile_and_store_digest(slot: str) -> None:
    """Build and persist a digest per trader, covering everything since each one's last digest."""
    start_of_today = datetime.now().strftime("%Y-%m-%d 00:00:00")
    for name in names:
        latest = read_latest_digest(name)
        since = latest["datetime"] if latest else start_of_today
        report = build_trader_digest(name, since)
        write_digest(name, slot, report)
