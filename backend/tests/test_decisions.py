import sqlite3

import pytest

CLAIM = "/api/claims/CLM-1001"


def decide(client, decision, payout, claim=CLAIM):
    return client.post(
        f"{claim}/decision",
        json={
            "decision": decision,
            "payout": payout,
            "reason": "The reason.",
            "policy_section": "3. Trip Delay",
        },
    )


def started(client, claim=CLAIM):
    assert client.post(f"{claim}/start").json()["status"] == "in_progress"
    return client


def test_start_only_a_waiting_claim(client):
    started(client)
    response = client.post(f"{CLAIM}/start")
    assert response.status_code == 409
    assert client.post("/api/claims/CLM-9999/start").status_code == 404


def test_steps_are_listed_in_order(client):
    client.post(f"{CLAIM}/steps", json={"kind": "tool", "text": "first"})
    client.post(f"{CLAIM}/steps", json={"kind": "model", "text": "second"})
    steps = client.get(CLAIM).json()["steps"]
    assert [(step["kind"], step["text"]) for step in steps] == [
        ("tool", "first"),
        ("model", "second"),
    ]


@pytest.mark.parametrize("decision", ["decline", "refer"])
def test_decline_or_refer_decides_the_claim(client, decision):
    response = decide(started(client), decision, 0)
    assert response.json() == {"claim_id": "CLM-1001", "status": "decided"}
    claim = client.get(CLAIM).json()
    assert claim["decision"]["decision"] == decision
    assert claim["decision"]["policy_section"] == "3. Trip Delay"
    assert claim["payment"] is None


def test_decline_with_a_payout_is_refused(client):
    assert decide(started(client), "decline", 10).status_code == 400


def test_approve_needs_a_payout(client):
    assert decide(started(client), "approve", 0).status_code == 400


def test_decide_only_a_claim_in_progress(client):
    assert decide(client, "approve", 420).status_code == 409


def test_decide_twice_is_refused(client):
    decide(started(client), "approve", 420)
    response = decide(client, "approve", 420)
    assert response.status_code == 409
    assert "already decided" in response.json()["detail"]


def test_approve_and_pay_within_the_limit(client):
    decide(started(client), "approve", 420)
    assert client.get(CLAIM).json()["status"] == "in_progress"
    response = client.post(f"{CLAIM}/payment", json={"amount": 420})
    assert response.json()["status"] == "decided"
    assert client.get(CLAIM).json()["payment"]["amount"] == 420


def test_the_limit_itself_pays_straight_through(client):
    assert decide(started(client), "approve", 1000).json()["status"] == "in_progress"
    response = client.post(f"{CLAIM}/payment", json={"amount": 1000})
    assert response.json()["status"] == "decided"


def test_paying_a_declined_claim_is_refused(client):
    decide(started(client), "decline", 0)
    assert client.post(f"{CLAIM}/payment", json={"amount": 10}).status_code == 409


def test_paying_a_different_amount_is_refused(client):
    decide(started(client), "approve", 420)
    response = client.post(f"{CLAIM}/payment", json={"amount": 500})
    assert response.status_code == 400
    assert client.get(CLAIM).json()["payment"] is None


def test_paying_twice_is_refused(client):
    decide(started(client), "approve", 420)
    client.post(f"{CLAIM}/payment", json={"amount": 420})
    assert client.post(f"{CLAIM}/payment", json={"amount": 420}).status_code == 409


def test_over_the_limit_payment_waits_for_sign_off(client):
    response = decide(started(client), "approve", 1250)
    assert response.json()["status"] == "awaiting_sign_off"

    response = client.post(f"{CLAIM}/payment", json={"amount": 1250})
    assert response.status_code == 409
    assert "sign off" in response.json()["detail"]
    claim = client.get(CLAIM).json()
    assert claim["status"] == "awaiting_sign_off"
    assert claim["payment"] is None

    response = client.post(f"{CLAIM}/sign-off", json={"handler_id": "HND-01"})
    assert response.json()["status"] == "decided"
    claim = client.get(CLAIM).json()
    assert claim["payment"]["amount"] == 1250
    assert claim["sign_off"]["handler_id"] == "HND-01"
    assert claim["sign_off"]["handler_name"] == "Dana Whitfield"
    assert claim["sign_off"]["signed_off_at"]
    listed = client.get("/api/claims").json()[0]
    assert (listed["decision"], listed["payout"]) == ("approve", 1250)


def test_sign_off_only_a_claim_awaiting_it(client):
    decide(started(client), "approve", 420)
    response = client.post(f"{CLAIM}/sign-off", json={"handler_id": "HND-01"})
    assert response.status_code == 409


def test_sign_off_needs_a_handler_who_can(client, tmp_path):
    decide(started(client), "approve", 1250)
    with sqlite3.connect(tmp_path / "test.db") as connection:
        connection.execute(
            "UPDATE handlers SET data = json_set(data, '$.can_approve_over_limit',"
            " json('false')) WHERE handler_id = 'HND-03'"
        )
    response = client.post(f"{CLAIM}/sign-off", json={"handler_id": "HND-03"})
    assert response.status_code == 403
    response = client.post(f"{CLAIM}/sign-off", json={"handler_id": "HND-99"})
    assert response.status_code == 404


def test_failure_puts_an_unfinished_claim_back_in_the_queue(client):
    decide(started(client), "approve", 420)
    response = client.post(f"{CLAIM}/failure", json={"error": "The model timed out"})
    assert response.json()["status"] == "waiting"
    claim = client.get(CLAIM).json()
    assert claim["decision"] is None
    assert claim["steps"][-1]["kind"] == "error"
    assert claim["steps"][-1]["text"] == "The model timed out"


def test_failure_after_a_decision_keeps_it(client):
    decide(started(client), "decline", 0)
    response = client.post(f"{CLAIM}/failure", json={"error": "Late error"})
    assert response.json()["status"] == "decided"
