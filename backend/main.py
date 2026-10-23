"""The UnderCover backend."""

import json
import sqlite3
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from agent import main as agent
from backend import db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create and seed the database on startup."""
    db.init()
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


class Step(BaseModel):
    kind: str
    text: str


class Decision(BaseModel):
    decision: Literal["approve", "decline", "refer"]
    payout: float
    reason: str
    policy_section: str


class Payment(BaseModel):
    amount: float


class SignOff(BaseModel):
    handler_id: str


class Failure(BaseModel):
    error: str


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


@app.get("/api/instructions", operation_id="get_instructions")
def get_instructions() -> str:
    """Get the UnderCover Agent's instructions."""
    with db.connect() as connection:
        return document(connection, "instructions")


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers() -> list[dict[str, Any]]:
    """List the claims handlers."""
    with db.connect() as connection:
        rows = connection.execute("SELECT data FROM handlers ORDER BY handler_id")
        return [json.loads(row["data"]) for row in rows]


def require_status(connection: sqlite3.Connection, claim_id: str, status: str) -> None:
    """Raise 409 unless the claim has the given status."""
    current = claim_status(connection, claim_id)
    if current != status:
        raise HTTPException(409, f"Claim {claim_id} is {current}, not {status}")


def set_status(connection: sqlite3.Connection, claim_id: str, status: str) -> None:
    """Move a claim to a new status."""
    connection.execute(
        "UPDATE claims SET status = ? WHERE claim_id = ?", (status, claim_id)
    )


def approval_limit(connection: sqlite3.Connection) -> float:
    """Return the payout above which a handler must sign off."""
    return json.loads(document(connection, "company"))["payout_approval_limit"]


def state(claim_id: str, status: str) -> dict[str, str]:
    """Return a claim's id and status after a change."""
    return {"claim_id": claim_id, "status": status}


@app.post("/api/claims/{claim_id}/start", operation_id="start_claim")
def start_claim(claim_id: str) -> dict[str, str]:
    """Mark a waiting claim as in progress before the agent works on it."""
    with db.connect() as connection:
        require_status(connection, claim_id, "waiting")
        set_status(connection, claim_id, "in_progress")
    return state(claim_id, "in_progress")


@app.post("/api/claims/{claim_id}/steps", operation_id="add_step")
def add_step(claim_id: str, step: Step) -> dict[str, str]:
    """Record one step the agent took on a claim."""
    with db.connect() as connection:
        status = claim_status(connection, claim_id)
        connection.execute(
            "INSERT INTO steps (claim_id, kind, text) VALUES (?, ?, ?)",
            (claim_id, step.kind, step.text),
        )
    return state(claim_id, status)


@app.post("/api/claims/{claim_id}/decision", operation_id="decide_claim")
def decide_claim(claim_id: str, decision: Decision) -> dict[str, str]:
    """Approve, decline or refer a claim, with the payout, reason and section."""
    with db.connect() as connection:
        require_status(connection, claim_id, "in_progress")
        if row_or_none(connection, "decisions", claim_id):
            raise HTTPException(409, f"Claim {claim_id} is already decided")
        if decision.decision == "approve" and decision.payout <= 0:
            raise HTTPException(400, "An approval needs a payout above 0")
        if decision.decision != "approve" and decision.payout != 0:
            raise HTTPException(400, f"A {decision.decision} must have a payout of 0")
        connection.execute(
            "INSERT INTO decisions (claim_id, decision, payout, reason, policy_section)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                claim_id,
                decision.decision,
                decision.payout,
                decision.reason,
                decision.policy_section,
            ),
        )
        if decision.decision != "approve":
            status = "decided"
        elif decision.payout > approval_limit(connection):
            status = "awaiting_sign_off"
        else:
            status = "in_progress"
        set_status(connection, claim_id, status)
    return state(claim_id, status)


@app.post("/api/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, payment: Payment) -> dict[str, str]:
    """Pay an approved claim its payout; over the limit, a handler signs off first."""
    with db.connect() as connection:
        decision = row_or_none(connection, "decisions", claim_id)
        if decision is None or decision["decision"] != "approve":
            raise HTTPException(409, f"Claim {claim_id} is not approved")
        if row_or_none(connection, "payments", claim_id):
            raise HTTPException(409, f"Claim {claim_id} is already paid")
        if payment.amount != decision["payout"]:
            raise HTTPException(
                400,
                f"The approved payout is ${decision['payout']:,.2f},"
                f" not ${payment.amount:,.2f}",
            )
        if claim_status(connection, claim_id) == "awaiting_sign_off":
            raise HTTPException(
                409,
                f"A payout over ${approval_limit(connection):,.2f} waits for a handler"
                " to sign off. The handler's sign-off releases the payment.",
            )
        pay(connection, claim_id, payment.amount)
    return state(claim_id, "decided")


def pay(connection: sqlite3.Connection, claim_id: str, amount: float) -> None:
    """Record a payment and close the claim. No real money moves."""
    connection.execute(
        "INSERT INTO payments (claim_id, amount) VALUES (?, ?)", (claim_id, amount)
    )
    set_status(connection, claim_id, "decided")


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, sign_off: SignOff) -> dict[str, str]:
    """Sign off a payout over the limit as a handler, which releases the payment."""
    with db.connect() as connection:
        require_status(connection, claim_id, "awaiting_sign_off")
        handler = record(connection, "handlers", "handler_id", sign_off.handler_id)
        if not handler["can_approve_over_limit"]:
            raise HTTPException(403, f"{handler['name']} can't sign off this payout")
        connection.execute(
            "INSERT INTO sign_offs (claim_id, handler_id) VALUES (?, ?)",
            (claim_id, sign_off.handler_id),
        )
        payout = connection.execute(
            "SELECT payout FROM decisions WHERE claim_id = ?", (claim_id,)
        ).fetchone()["payout"]
        pay(connection, claim_id, payout)
    return state(claim_id, "decided")


@app.post("/api/claims/{claim_id}/run", operation_id="run_agent", status_code=202)
def run_agent(claim_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Start the UnderCover Agent on a waiting claim; it works in the background."""
    start_claim(claim_id)
    thread_id = str(uuid.uuid4())
    background_tasks.add_task(agent.work, claim_id, thread_id)
    return {"claim_id": claim_id, "status": "in_progress", "thread_id": thread_id}


@app.post("/api/claims/{claim_id}/failure", operation_id="fail_claim")
def fail_claim(claim_id: str, failure: Failure) -> dict[str, str]:
    """Record that the agent's run failed; an unfinished claim goes back to waiting."""
    with db.connect() as connection:
        status = claim_status(connection, claim_id)
        connection.execute(
            "INSERT INTO steps (claim_id, kind, text) VALUES (?, 'error', ?)",
            (claim_id, failure.error),
        )
        if status == "in_progress":
            connection.execute("DELETE FROM decisions WHERE claim_id = ?", (claim_id,))
            status = "waiting"
            set_status(connection, claim_id, status)
    return state(claim_id, status)
