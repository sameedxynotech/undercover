"""The UnderCover Agent."""

import json
import os
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"
STEP_LENGTH = 400


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def api(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    """Call the backend and return the JSON response, raising on an error."""
    with backend() as client:
        response = client.request(method, path, json=body)
    response.raise_for_status()
    return response.json()


def ask(method: str, path: str, body: dict[str, Any] | None = None) -> str:
    """Call the backend for a tool, returning a refusal as text for the model."""
    with backend() as client:
        response = client.request(method, path, json=body)
    if response.is_error:
        return f"Refused ({response.status_code}): {response.json()['detail']}"
    return response.text


@tool
def get_claim(claim_id: str) -> str:
    """Get a claim: the customer's story, the items claimed and the documents."""
    claim = api("GET", f"/api/claims/{claim_id}")
    for key in ["steps", "decision", "sign_off", "payment"]:
        del claim[key]
    return json.dumps(claim)


@tool
def get_policy(policy_id: str) -> str:
    """Get a policy: its plan, add-ons, purchase date, trip and travelers."""
    return ask("GET", f"/api/policies/{policy_id}")


@tool
def get_customer(customer_id: str) -> str:
    """Get a customer with their earlier claims."""
    return ask("GET", f"/api/customers/{customer_id}")


@tool
def get_plans() -> str:
    """Get every plan's limits, waiting periods and deductible, and the add-ons."""
    return ask("GET", "/api/plans")


@tool
def get_policy_wording() -> str:
    """Get the policy wording, the contract that every decision follows."""
    return api("GET", "/api/policy-wording")


@tool
def decide_claim(
    claim_id: str,
    decision: Literal["approve", "decline", "refer"],
    payout: float,
    reason: str,
    policy_section: str,
) -> str:
    """Record the decision: the payout (0 unless approved), the reason in two or
    three sentences, and the section of the policy wording that settles it."""
    return ask(
        "POST",
        f"/api/claims/{claim_id}/decision",
        {
            "decision": decision,
            "payout": payout,
            "reason": reason,
            "policy_section": policy_section,
        },
    )


@tool
def pay_claim(claim_id: str, amount: float) -> str:
    """Pay an approved claim its exact payout."""
    return ask("POST", f"/api/claims/{claim_id}/payment", {"amount": amount})


TOOLS = [
    get_claim,
    get_policy,
    get_customer,
    get_plans,
    get_policy_wording,
    decide_claim,
    pay_claim,
]


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def shorten(text: str) -> str:
    """Shorten a long text for the steps list."""
    return text if len(text) <= STEP_LENGTH else text[:STEP_LENGTH] + "..."


def steps(message: BaseMessage) -> list[dict[str, str]]:
    """Turn one message from the agent's run into steps for the dashboard."""
    found = []
    if isinstance(message, AIMessage):
        if message.text:
            found.append({"kind": "thought", "text": message.text})
        found.extend(
            {"kind": "tool_call", "text": f"{call['name']}({json.dumps(call['args'])})"}
            for call in message.tool_calls
        )
    elif isinstance(message, ToolMessage):
        found.append({"kind": "tool_result", "text": shorten(message.text)})
    return found


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Run the agent on one claim and return its final reply."""
    api("POST", f"/api/claims/{claim_id}/start")
    return work(claim_id, thread_id, llm)


def work(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Work a claim that is already in progress and return the final reply."""
    instructions = api("GET", "/api/instructions")
    agent = create_agent(llm or model(), tools=TOOLS, system_prompt=instructions)
    reply = ""
    try:
        for update in agent.stream(
            {"messages": [{"role": "user", "content": f"Claim {claim_id}"}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="updates",
        ):
            for node in update.values():
                for message in node["messages"]:
                    for step in steps(message):
                        api("POST", f"/api/claims/{claim_id}/steps", step)
                    reply = message.text
        if api("GET", f"/api/claims/{claim_id}")["status"] == "in_progress":
            raise RuntimeError("The agent finished without completing the claim")
    except Exception as error:
        api("POST", f"/api/claims/{claim_id}/failure", {"error": str(error)})
        raise
    return reply
