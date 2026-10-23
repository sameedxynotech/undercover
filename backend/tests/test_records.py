import json
import sqlite3
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


def held_back_claim_ids():
    ids = set()
    for name in [
        "evals/held_out_claims.json",
        "evals/harder/claims.json",
        "evals/even_harder/claims.json",
        "security/claims.json",
    ]:
        ids |= {claim["claim_id"] for claim in json.loads((DATA / name).read_text())}
    return ids


def test_seeds_the_queue_and_nothing_held_back(client, tmp_path):
    with sqlite3.connect(tmp_path / "test.db") as connection:
        seeded = {row[0] for row in connection.execute("SELECT claim_id FROM claims")}
    assert len(seeded) == 25
    assert not seeded & held_back_claim_ids()


def test_list_claims(client):
    claims = client.get("/api/claims").json()
    assert len(claims) == 25
    assert {claim["status"] for claim in claims} == {"waiting"}
    assert claims[0] == {
        "claim_id": "CLM-1001",
        "customer_name": "Maya Patel",
        "claim_type": "trip_delay",
        "submitted_on": "2026-06-24",
        "summary": "Flight home canceled by the airline, rebooked the next morning",
        "amount_claimed": 420.0,
        "status": "waiting",
        "decision": None,
        "payout": None,
    }


def test_get_claim(client):
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting"
    assert len(claim["items"]) == 3
    assert claim["documents"][0]["type"] == "carrier_report"
    assert claim["decision"] is None
    assert claim["payment"] is None
    assert claim["sign_off"] is None
    assert claim["steps"] == []


def test_get_policy(client):
    policy = client.get("/api/policies/POL-2001").json()
    assert policy["plan"] == "premium"


def test_get_customer_with_history(client):
    customer = client.get("/api/customers/CUS-3001").json()
    assert customer["previous_claims"][0]["claim_id"] == "CLM-0412"


def test_get_plans(client):
    plans = client.get("/api/plans").json()
    assert [plan["plan"] for plan in plans["plans"]] == ["economy", "premium", "first"]


def test_get_policy_wording(client):
    wording = client.get("/api/policy-wording").json()
    assert wording.startswith("# UnderCover Travel Insurance: Policy Wording")


def test_list_handlers(client):
    handlers = client.get("/api/handlers").json()
    assert [handler["handler_id"] for handler in handlers] == [
        "HND-01",
        "HND-02",
        "HND-03",
    ]


def test_unknown_ids_are_404(client):
    for path in [
        "/api/claims/CLM-9999",
        "/api/policies/POL-9999",
        "/api/customers/CUS-9999",
    ]:
        assert client.get(path).status_code == 404


def test_every_operation_has_an_id_a_summary_and_no_optional_inputs(client):
    spec = client.get("/openapi.json").json()
    for operations in spec["paths"].values():
        for operation in operations.values():
            assert operation["operationId"]
            assert operation["description"]
            for parameter in operation.get("parameters", []):
                assert parameter["required"]
            body = operation.get("requestBody")
            if body:
                assert body["required"]


def test_get_instructions(client):
    instructions = client.get("/api/instructions").json()
    assert instructions.startswith("You are the UnderCover Agent.")
