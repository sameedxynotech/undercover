import itertools

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import main

CLAIM = "/api/claims/CLM-1001"
_ids = itertools.count()


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies in place of a real model."""

    def bind_tools(self, tools, **kwargs):
        return self


def call(name, **args):
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": str(next(_ids))}]
    )


def stub(*replies):
    return StubModel(messages=iter(replies))


def decision(decision, payout):
    return call(
        "decide_claim",
        claim_id="CLM-1001",
        decision=decision,
        payout=payout,
        reason="The reason.",
        policy_section="3. Trip Delay",
    )


READ = [
    call("get_claim", claim_id="CLM-1001"),
    call("get_policy", policy_id="POL-2001"),
    call("get_customer", customer_id="CUS-3001"),
    call("get_plans"),
    call("get_policy_wording"),
]


def test_approves_and_pays(client):
    replies = [
        *READ,
        decision("approve", 420),
        call("pay_claim", claim_id="CLM-1001", amount=420),
        AIMessage(content="Approved, $420.00."),
    ]
    assert main.run("CLM-1001", "thread-1", stub(*replies)) == "Approved, $420.00."
    claim = client.get(CLAIM).json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 420
    kinds = [step["kind"] for step in claim["steps"]]
    assert kinds.count("tool_call") == 7
    assert kinds.count("tool_result") == 7
    assert kinds[-1] == "thought"
    assert claim["steps"][0]["text"] == 'get_claim({"claim_id": "CLM-1001"})'
    assert claim["steps"][1]["text"].startswith('{"claim_id": "CLM-1001"')


@pytest.mark.parametrize("outcome", ["decline", "refer"])
def test_declines_or_refers(client, outcome):
    replies = [*READ, decision(outcome, 0), AIMessage(content=outcome)]
    main.run("CLM-1001", "thread-1", stub(*replies))
    claim = client.get(CLAIM).json()
    assert claim["status"] == "decided"
    assert claim["decision"]["decision"] == outcome
    assert claim["payment"] is None


def test_cannot_pay_over_the_limit(client):
    replies = [
        decision("approve", 1250),
        call("pay_claim", claim_id="CLM-1001", amount=1250),
        AIMessage(content="Approved; the payment waits for sign-off."),
    ]
    main.run("CLM-1001", "thread-1", stub(*replies))
    claim = client.get(CLAIM).json()
    assert claim["status"] == "awaiting_sign_off"
    assert claim["payment"] is None
    refusal = claim["steps"][-2]["text"]
    assert refusal.startswith("Refused (409): A payout over $1,000.00")


def test_a_failed_run_goes_back_to_the_queue(client):
    with pytest.raises(RuntimeError):
        main.run("CLM-1001", "thread-1", stub(call("get_claim", claim_id="CLM-1001")))
    claim = client.get(CLAIM).json()
    assert claim["status"] == "waiting"
    assert claim["steps"][-1]["kind"] == "error"


def test_finishing_without_a_decision_is_a_failure(client):
    with pytest.raises(RuntimeError):
        main.run("CLM-1001", "thread-1", stub(AIMessage(content="Done.")))
    claim = client.get(CLAIM).json()
    assert claim["status"] == "waiting"
    assert claim["steps"][-1]["text"] == (
        "The agent finished without completing the claim"
    )


def test_long_tool_results_are_shortened(client):
    main.run(
        "CLM-1001",
        "thread-1",
        stub(*READ[4:], decision("decline", 0), AIMessage(content="Declined.")),
    )
    wording = client.get(CLAIM).json()["steps"][1]["text"]
    assert len(wording) == main.STEP_LENGTH + 3
    assert wording.endswith("...")


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "openai/gpt-6-luna"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
