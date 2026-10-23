from agent import main as agent


def test_run_agent_starts_the_claim_and_the_agent(client, monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "work", lambda *args: calls.append(args))
    response = client.post("/api/claims/CLM-1001/run")
    assert response.status_code == 202
    assert response.json()["status"] == "in_progress"
    assert calls == [("CLM-1001", response.json()["thread_id"])]
    assert client.get("/api/claims/CLM-1001").json()["status"] == "in_progress"


def test_run_agent_only_on_a_waiting_claim(client, monkeypatch):
    monkeypatch.setattr(agent, "work", lambda *args: None)
    client.post("/api/claims/CLM-1001/start")
    assert client.post("/api/claims/CLM-1001/run").status_code == 409
