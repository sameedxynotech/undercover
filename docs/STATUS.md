# Status

The claims pilot from `docs/SPEC.md` is built, following `docs/PLAN.md`.

- `backend/`: FastAPI on SQLite. The database is `backend/undercover.db`, or the path in `UNDERCOVER_DB`. It is created and seeded from `data/` on startup when missing (never from `data/evals/` or `data/security/`). Delete it to reset the pilot, or to pick up a change to the agent's instructions in `backend/instructions.md`.
  - Read routes for the claims queue, claims, policies, customers, plans, the policy wording, the agent's instructions and the handlers.
  - Write routes to start a claim, record the agent's steps, decide, pay, sign off and record a failed run. `run_agent` starts the agent on a claim in the background.
  - A payout over $1,000 is refused by `pay_claim` until a handler signs off, and the sign-off releases the payment. No real money moves.
- `agent/`: the UnderCover Agent, `run(claim_id, thread_id)`. It reads its instructions, the claim, the policy, the customer, the plans and the wording through the API, decides, pays, and records each step. If a run fails or ends without finishing the claim, the claim goes back to `waiting` with the error as a step.
- `dashboard/`: React in UnderCover's brand, with three pages:
  - The queue (`#/`) shows every claim's status, with counts by status.
  - The claim page (`#/claims/CLM-1001`) shows the claim in full with its policy and claim history, the decision, the agent's steps live, a Run agent button, and the sign-off for payouts over $1,000.
  - The instructions page (`#/instructions`) shows the agent's instructions, read only.
- `e2e/`: Playwright tests of the queue, a decided claim, the sign-off and the instructions. They run their own backend (port 8001) and dashboard (port 5174) on a fresh database.

## Running it

- `npm run dev` starts the backend on port 8000 and the dashboard on http://localhost:5173.
- `uv run -m agent CLM-1001` runs the agent on one claim from the command line, with the backend running.
- The agent uses `openai/gpt-6-luna` on OpenRouter, which needs credits on the account. Set `MODEL_NAME=openrouter/free` in `.env` to use the free models instead. They are limited to 50 requests a day, roughly five claims.
- `npm run check` runs every check.

## Not yet done

- Checking the agent's accuracy against the handlers' decisions in `data/evals/`.
