"""The UnderCover database: SQLite, seeded from the business data in data/."""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEFAULT_DB = ROOT / "backend" / "undercover.db"

SCHEMA = """
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE policies (policy_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE customers (customer_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE handlers (handler_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE documents (name TEXT PRIMARY KEY, content TEXT NOT NULL);
CREATE TABLE steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE decisions (
    claim_id TEXT PRIMARY KEY,
    decision TEXT NOT NULL,
    payout REAL NOT NULL,
    reason TEXT NOT NULL,
    policy_section TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE sign_offs (
    claim_id TEXT PRIMARY KEY,
    handler_id TEXT NOT NULL,
    signed_off_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE payments (
    claim_id TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def db_path() -> Path:
    """Return the database file, from UNDERCOVER_DB or the default."""
    return Path(os.getenv("UNDERCOVER_DB", str(DEFAULT_DB)))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection that returns rows by name, commits and closes."""
    with closing(sqlite3.connect(db_path())) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            yield connection


def load(name: str) -> Any:
    """Load one of the JSON files in data/."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def seed(connection: sqlite3.Connection) -> None:
    """Create the tables and load the queue and the records behind it."""
    connection.executescript(SCHEMA)
    for claim in load("claims.json"):
        connection.execute(
            "INSERT INTO claims VALUES (?, 'waiting', ?)",
            (claim["claim_id"], json.dumps(claim)),
        )
    for table, key, name in [
        ("policies", "policy_id", "policies.json"),
        ("customers", "customer_id", "customers.json"),
        ("handlers", "handler_id", "handlers.json"),
    ]:
        connection.executemany(
            f"INSERT INTO {table} VALUES (?, ?)",  # noqa: S608
            [(row[key], json.dumps(row)) for row in load(name)],
        )
    documents = {
        "company": (DATA / "company.json").read_text(encoding="utf-8"),
        "plans": (DATA / "plans.json").read_text(encoding="utf-8"),
        "policy_wording": (DATA / "policy_wording.md").read_text(encoding="utf-8"),
        "instructions": (ROOT / "backend" / "instructions.md").read_text(
            encoding="utf-8"
        ),
    }
    connection.executemany("INSERT INTO documents VALUES (?, ?)", documents.items())


def init() -> None:
    """Create and seed the database if it doesn't exist yet."""
    if db_path().exists():
        return
    with connect() as connection:
        seed(connection)
