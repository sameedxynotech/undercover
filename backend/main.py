"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

from backend import db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create and seed the database on startup."""
    db.init()
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


def record(connection: sqlite3.Connection, table: str, key: str, value: str) -> Any:
    """Return one JSON record by its id, or raise 404."""
    row = connection.execute(
        f"SELECT data FROM {table} WHERE {key} = ?",  # noqa: S608
        (value,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"No record {value}")
    return json.loads(row["data"])


def document(connection: sqlite3.Connection, name: str) -> str:
    """Return one of the stored documents."""
    return connection.execute(
        "SELECT content FROM documents WHERE name = ?", (name,)
    ).fetchone()["content"]


def row_or_none(
    connection: sqlite3.Connection, table: str, claim_id: str
) -> dict[str, Any] | None:
    """Return a claim's row from a table, or None."""
    row = connection.execute(
        f"SELECT * FROM {table} WHERE claim_id = ?",  # noqa: S608
        (claim_id,),
    ).fetchone()
    return dict(row) if row else None


def claim_status(connection: sqlite3.Connection, claim_id: str) -> str:
    """Return a claim's status, or raise 404."""
    row = connection.execute(
        "SELECT status FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"No record {claim_id}")
    return row["status"]


def full_claim(connection: sqlite3.Connection, claim_id: str) -> dict[str, Any]:
    """Return a claim with its status, decision, sign-off, payment and steps."""
    claim = record(connection, "claims", "claim_id", claim_id)
    claim["status"] = claim_status(connection, claim_id)
    claim["decision"] = row_or_none(connection, "decisions", claim_id)
    claim["sign_off"] = row_or_none(connection, "sign_offs", claim_id)
    claim["payment"] = row_or_none(connection, "payments", claim_id)
    claim["steps"] = [
        dict(row)
        for row in connection.execute(
            "SELECT step_id, kind, text, created_at FROM steps"
            " WHERE claim_id = ? ORDER BY step_id",
            (claim_id,),
        )
    ]
    return claim


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims() -> list[dict[str, Any]]:
    """List the claims queue with each claim's status and payout."""
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT c.status, c.data, d.decision, d.payout, u.data AS customer"
            " FROM claims c LEFT JOIN decisions d USING (claim_id)"
            " JOIN customers u ON u.customer_id = json_extract(c.data, '$.customer_id')"
            " ORDER BY c.claim_id"
        ).fetchall()
    claims = []
    for row in rows:
        claim = json.loads(row["data"])
        claims.append(
            {
                "claim_id": claim["claim_id"],
                "customer_name": json.loads(row["customer"])["name"],
                "claim_type": claim["claim_type"],
                "submitted_on": claim["submitted_on"],
                "summary": claim["summary"],
                "amount_claimed": claim["amount_claimed"],
                "status": row["status"],
                "decision": row["decision"],
                "payout": row["payout"],
            }
        )
    return claims


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str) -> dict[str, Any]:
    """Get a claim in full, with its decision, payment and the agent's steps."""
    with db.connect() as connection:
        return full_claim(connection, claim_id)


@app.get("/api/policies/{policy_id}", operation_id="get_policy")
def get_policy(policy_id: str) -> dict[str, Any]:
    """Get a policy: its plan, add-ons, trip and travelers."""
    with db.connect() as connection:
        return record(connection, "policies", "policy_id", policy_id)


@app.get("/api/customers/{customer_id}", operation_id="get_customer")
def get_customer(customer_id: str) -> dict[str, Any]:
    """Get a customer with their earlier claims."""
    with db.connect() as connection:
        return record(connection, "customers", "customer_id", customer_id)


@app.get("/api/plans", operation_id="get_plans")
def get_plans() -> dict[str, Any]:
    """Get the plans' limits, waiting periods and deductibles, and the add-ons."""
    with db.connect() as connection:
        return json.loads(document(connection, "plans"))


@app.get("/api/policy-wording", operation_id="get_policy_wording")
def get_policy_wording() -> str:
    """Get the policy wording, the contract that decisions follow."""
    with db.connect() as connection:
        return document(connection, "policy_wording")


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers() -> list[dict[str, Any]]:
    """List the claims handlers."""
    with db.connect() as connection:
        rows = connection.execute("SELECT data FROM handlers ORDER BY handler_id")
        return [json.loads(row["data"]) for row in rows]
