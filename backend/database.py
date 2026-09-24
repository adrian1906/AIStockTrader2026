import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

DB = "accounts.db"


with sqlite3.connect(DB) as conn:
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS accounts (name TEXT PRIMARY KEY, account TEXT)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            datetime DATETIME,
            type TEXT,
            message TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            datetime TEXT,
            kind TEXT,
            narrative TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            datetime TEXT,
            slot TEXT,
            report TEXT
        )
    ''')
    conn.commit()

def write_account(name, account_dict):
    json_data = json.dumps(account_dict)
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO accounts (name, account)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET account=excluded.account
        ''', (name.lower(), json_data))
        conn.commit()

def read_account(name):
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT account FROM accounts WHERE name = ?', (name.lower(),))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None
    
def write_log(name: str, type: str, message: str):
    """
    Write a log entry to the logs table.
    
    Args:
        name (str): The name associated with the log
        type (str): The type of log entry
        message (str): The log message
    """
    now = datetime.now().isoformat()
    
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO logs (name, datetime, type, message)
            VALUES (?, datetime('now'), ?, ?)
        ''', (name.lower(), type, message))
        conn.commit()

def write_session(name: str, kind: str, narrative: list[dict]) -> None:
    """Record one trading round's step-by-step narrative (tool calls, their results, and

    the model's own messages), for later compilation into a digest.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (name, datetime, kind, narrative)
            VALUES (?, ?, ?, ?)
        ''', (name.lower(), timestamp, kind, json.dumps(narrative)))
        conn.commit()


def read_sessions_since(name: str, since: str) -> list[dict]:
    """All recorded rounds for this trader at or after the given 'YYYY-MM-DD HH:MM:SS' timestamp."""
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT datetime, kind, narrative FROM sessions
            WHERE name = ? AND datetime >= ?
            ORDER BY datetime ASC
        ''', (name.lower(), since))
        return [
            {"datetime": row[0], "kind": row[1], "narrative": json.loads(row[2])}
            for row in cursor.fetchall()
        ]


def write_digest(name: str, slot: str, report: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO digests (name, datetime, slot, report)
            VALUES (?, ?, ?, ?)
        ''', (name.lower(), timestamp, slot, report))
        conn.commit()


def read_latest_digest(name: str) -> dict | None:
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT datetime, slot, report FROM digests
            WHERE name = ?
            ORDER BY datetime DESC
            LIMIT 1
        ''', (name.lower(),))
        row = cursor.fetchone()
        return {"datetime": row[0], "slot": row[1], "report": row[2]} if row else None


def read_digests_since(name: str, since: str) -> list[dict]:
    """Every compiled digest for this trader at or after the given 'YYYY-MM-DD HH:MM:SS'

    timestamp, oldest first - for pulling a range (e.g. the past week) rather than just
    the latest one.
    """
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT datetime, slot, report FROM digests
            WHERE name = ? AND datetime >= ?
            ORDER BY datetime ASC
        ''', (name.lower(), since))
        return [{"datetime": row[0], "slot": row[1], "report": row[2]} for row in cursor.fetchall()]


def read_log(name: str, last_n=10):
    """
    Read the most recent log entries for a given name.
    
    Args:
        name (str): The name to retrieve logs for
        last_n (int): Number of most recent entries to retrieve
        
    Returns:
        list: A list of tuples containing (datetime, type, message)
    """
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT datetime, type, message FROM logs 
            WHERE name = ? 
            ORDER BY datetime DESC
            LIMIT ?
        ''', (name.lower(), last_n))
        
        return reversed(cursor.fetchall())