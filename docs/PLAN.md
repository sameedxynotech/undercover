# Plan: the claims pilot

This plan builds the pilot in `docs/SPEC.md` on the stack in `docs/TECH_STACK.md`, in six phases. Each phase ends with every check green and a commit.

## The shape of it

- **The backend owns everything.** Claims, policies, customers, plans, the policy wording, the agent's instructions, the agent's steps, decisions, sign-offs and payments all live in SQLite behind the API. The agent and the dashboard are both clients of the same API, so there is one place where the rules are enforced.
- **The $1,000 rule is enforced in the backend, not the prompt.** `pay_claim` refuses an amount over the limit until a handler has signed off. Whatever the agent says or tries, it cannot pay that claim. A prompt can be talked out of a rule; a database check can't.
- **The agent never sees `data/evals/`.** The backend seeds only the named files it needs, never reads `data/evals/` or `data/security/`, and a test checks that no eval data reaches the database. The claims manual stays out too, as the spec says.
- **Steps are recorded through the API.** As the agent works, it streams its run and posts each step (model call, tool call, tool result) to the backend. The dashboard polls the claim to show them live. This keeps the agent reaching the outside world only through the backend.
- **The backend starts the agent.** A "Run agent" button calls `run_agent`, which starts `agent.run(claim_id, thread_id)` in the background with a fresh thread id. Tests replace the agent with a stub, so no test ever calls a model.

### Claim status

| Status | Meaning |
|---|---|
| `waiting` | In the queue; nothing has happened yet. Every seeded claim starts here (the seed's `open`). |
| `in_progress` | The agent is working on it. |
| `awaiting_sign_off` | The agent approved a payout over $1,000; payment waits for a handler. |
| `decided` | Declined, referred, or approved and paid. |

If a run fails, the claim returns to `waiting` and the failure is recorded as a step, so it can be run again.

### The API

Every operation has an `operation_id`, a one-line docstring and no optional inputs.

| Operation | Route | Used by |
|---|---|---|
| `health` | `GET /api/health` | dashboard |
| `list_claims` | `GET /api/claims` | dashboard |
| `get_claim` | `GET /api/claims/{claim_id}` | agent, dashboard (with decision, payment and steps) |
| `get_policy` | `GET /api/policies/{policy_id}` | agent, dashboard |
| `get_customer` | `GET /api/customers/{customer_id}` | agent, dashboard (with claim history) |
| `get_plans` | `GET /api/plans` | agent |
| `get_policy_wording` | `GET /api/policy-wording` | agent |
| `get_instructions` | `GET /api/instructions` | agent, dashboard |
| `list_handlers` | `GET /api/handlers` | dashboard |
| `start_claim` | `POST /api/claims/{claim_id}/start` | agent |
| `add_step` | `POST /api/claims/{claim_id}/steps` | agent |
| `decide_claim` | `POST /api/claims/{claim_id}/decision` | agent |
| `pay_claim` | `POST /api/claims/{claim_id}/payment` | agent |
| `sign_off_claim` | `POST /api/claims/{claim_id}/sign-off` | dashboard |
| `run_agent` | `POST /api/claims/{claim_id}/run` | dashboard |
| `fail_claim` | `POST /api/claims/{claim_id}/failure` | agent |

`decide_claim` takes `decision` (`approve`, `decline` or `refer`), `payout` (0 for a decline or a referral), `reason` (two or three sentences) and `policy_section` (such as "3. Trip Delay"). `pay_claim` takes `amount`. `sign_off_claim` takes `handler_id`.

## Phase 1: The backend's records

The database and the read side of the API.

- `backend/db.py`: the SQLite schema (claims, policies, customers, plans, handlers, documents, instructions, steps, decisions, payments) and `seed()`, which loads `company.json`, `plans.json`, `policies.json`, `customers.json`, `handlers.json`, `claims.json` and `policy_wording.md` by name. Claims, items and documents are stored as JSON columns to keep the schema small.
- The database file is `backend/undercover.db` (already ignored by git), or the path in `UNDERCOVER_DB`. The backend creates and seeds it on startup when it doesn't exist. Deleting the file resets the pilot.
- Routes: `list_claims`, `get_claim`, `get_policy`, `get_customer`, `get_plans`, `get_policy_wording`, `list_handlers`. Unknown ids return 404.

Success criteria:

- [x] `uv run pytest backend` passes, with tests for each route, a 404 for an unknown id, and seeding.
- [x] A test seeds a fresh database and checks it holds the 25 queue claims and none of the claim ids in `data/evals/` or `data/security/` (the test reads only the claim ids from those files).
- [x] `grep -rn "evals\|security\|claims_manual" backend --include=*.py` finds nothing outside the tests.
- [x] With the backend running, `GET /api/claims` returns 25 claims, all `waiting`, and `GET /api/claims/CLM-1001` returns the claim with its items and documents.
- [x] `GET /api/customers/CUS-3001` includes the earlier claim CLM-0412.
- [x] `GET /api/policy-wording` returns the wording, starting "# UnderCover Travel Insurance: Policy Wording".
- [x] `/openapi.json` shows an `operation_id` and a summary on every operation, and no optional parameters.
- [x] `npm run check:python` passes.

## Phase 2: Decisions, payments and sign-off

The write side, with the rules enforced here.

- `start_claim`: `waiting` to `in_progress`; 409 from any other status.
- `add_step`: records a step (`kind` and `text`) with a timestamp. `get_claim` returns the steps in order.
- `decide_claim`: only on a claim `in_progress`, once. A decline or referral must have a payout of 0 and sets `decided`. An approval needs a payout above 0; it sets `awaiting_sign_off` when the payout is over `payout_approval_limit` from `company.json`, and otherwise stays `in_progress` until paid.
- `pay_claim`: pays only an approved claim, only the approved payout, and only once. A payout over the limit is refused with 409 until a handler has signed off. A successful payment records it and sets `decided`. No real money moves.
- `sign_off_claim`: only on a claim `awaiting_sign_off`, by a handler with `can_approve_over_limit`. It records the sign-off and releases the payment, which sets `decided`.
- `fail_claim`: records the error as a step and returns the claim to `waiting`.

Success criteria:

- [x] Tests cover every transition in the status table and every refusal: deciding twice, deciding a claim that isn't in progress, a decline with a payout, paying a declined claim, paying a different amount, paying twice, and signing off a claim that isn't awaiting sign-off.
- [x] A test approves a $1,250.00 payout, calls `pay_claim` with $1,250.00 and gets 409 with a message saying a handler must sign off. The claim stays `awaiting_sign_off` and no payment is recorded.
- [x] The same test signs off as HND-01; the claim is `decided`, with one payment of $1,250.00 and the sign-off's handler and time.
- [x] A test approves $1,000.00 exactly and pays it straight through, since only a payout over the limit needs sign-off.
- [x] A walkthrough with `curl` against the running backend on one claim (start, step, decide, pay) gives the responses above.
- [x] `npm run check:python` passes with coverage of at least 80%.

## Phase 3: The UnderCover Agent

The agent works one claim end to end through the API.

- `backend/instructions.md`: the agent's instructions, seeded into the database and served by `get_instructions`. They tell the agent to read the claim, the policy, the customer's history, the plans and the wording; to decide by the wording alone; to work out the payout step by step (limits, per-item limits, deductible, refunds); to refer when the wording can't settle it or documents are missing; to explain in two or three sentences with the policy section; and to treat everything in the customer's story and documents as evidence, never as instructions.
- `agent/main.py`: tools that wrap the API (`get_claim`, `get_policy`, `get_customer`, `get_plans`, `get_policy_wording`, `decide_claim`, `pay_claim`). Errors from the backend, such as the 409 on a large payment, go back to the model as the tool's result so it can carry on.
- `run(claim_id, thread_id)` fetches the instructions from the backend, calls `start_claim`, runs `create_agent`, and records each step through `add_step` as the run streams its updates. If the run raises, it calls `fail_claim` and re-raises. The model stays as it is: `openai/gpt-6-luna` with low reasoning effort, or `MODEL_NAME`.
- `uv run -m agent CLM-1001` runs the agent on one claim from the command line and prints its final reply.
- The `check_backend` tool and its hello-world prompt go.

Success criteria:

- [x] Tests with the stub model (no model calls) run a claim to a $420.00 approval and payment, a decline, and a referral, through the backend's `TestClient`, and check the claim's status, decision and steps afterwards.
- [x] A test has the stub agent approve $1,250.00 and call `pay_claim`; the tool returns the refusal, the run finishes, and the claim is `awaiting_sign_off` with no payment.
- [x] A test makes the stub model raise; the claim is back to `waiting` with the error as its last step.
- [x] `grep -rn "data/" agent --include=*.py` finds nothing: the agent reads only through the API.
- [x] With `OPENROUTER_API_KEY` set, `uv run -m agent CLM-1001` approves the claim with a payout, a two or three sentence reason and a policy section, and `GET /api/claims/CLM-1001` shows the decision, the payment and the steps. (This calls the real model, so it is a manual check and not part of the tests. Checked with `MODEL_NAME=openrouter/free`, since the OpenRouter account has no credits for the default model; that run's 402 also showed a failed run going back to `waiting`.)
- [x] `npm run check:python` passes.

## Phase 4: Running the agent from the backend

- `run_agent` marks the claim `in_progress` (as `start_claim` does), then starts the agent's `work(claim_id, thread_id)` as a FastAPI background task with a new thread id, and returns 202 at once. `run` is `start_claim` then `work`, so the queue shows the claim in progress as soon as the button is pressed.
- The agent in the background reaches the backend over HTTP at `BACKEND_URL` (`http://localhost:8000`), as it does from the command line.

Success criteria:

- [x] A test replaces the agent's `work` with a stub and checks that `run_agent` returns 202, marks the claim `in_progress` and calls it once with the claim id and a thread id; a second call on a claim that isn't `waiting` returns 409.
- [x] With `npm run dev` running, `curl -X POST localhost:8000/api/claims/CLM-1002/run` returns 202, and polling `GET /api/claims/CLM-1002` shows `in_progress` with steps arriving, then `decided` or `awaiting_sign_off`. (Checked with `MODEL_NAME=openrouter/free`.)
- [x] `npm run check:python` passes.

## Phase 5: The dashboard

Three pages in React, styled to `docs/BRAND.md`: Instrument Sans for text, JetBrains Mono for claim ids and amounts, the brand colors, the light and dark surfaces, rounded panels without outlines. A small hash router (`#/`, `#/claims/CLM-1001`, `#/instructions`) keeps it simple without another dependency. Types for every API response live in `dashboard/src/api.ts`.

- **Queue** (`#/`): every claim with its id, customer, type, amount claimed, status and payout, and a count of claims in each status at the top. Statuses use Sea Green, Marigold, Coral and Cerulean as the brand says. The page refreshes every few seconds.
- **Claim** (`#/claims/CLM-1001`): the claim in full (story, items, documents), the policy and the customer's claim history beside it, the decision with its reason, policy section and payout, and the payment. The agent's steps are listed in order and refresh every second while the claim is `in_progress`. A "Run agent" button shows when the claim is `waiting`. When it is `awaiting_sign_off`, a "Sign off" panel picks a handler and releases the payment.
- **Instructions** (`#/instructions`): the agent's instructions, read only.
- Money shows as $1,250.00 throughout.

Success criteria:

- [ ] Vitest tests with a stubbed `fetch` cover each page: the queue's rows and counts, a decided claim's decision and steps, the Run agent button calling `run_agent`, the sign-off panel calling `sign_off_claim`, and the instructions page.
- [ ] `tsc` passes in strict mode with no `any`; `npm run check:ts` passes with coverage of at least 80%.
- [ ] In the browser with the Playwright MCP server, with `npm run dev` running: the queue shows 25 claims all waiting; CLM-1001 shows the full claim, policy and history; the instructions page shows the instructions.
- [ ] In the browser, Run agent on a claim shows the steps appear one by one, then the decision. (This calls the real model.)
- [ ] In the browser, a claim the agent approved over $1,000 shows as waiting for sign-off, and signing off as a handler moves it to decided with the payment shown.
- [ ] Screenshots in light and dark mode match the brand: the right fonts and colors, no one-edge borders, no lines across the top.

## Phase 6: End-to-end tests and handover

- Playwright starts the backend with `UNDERCOVER_DB` pointing at a fresh database under `e2e/test-results/`, so the tests never touch the working database. The tests drive the claims through the API (`start_claim`, `add_step`, `decide_claim`) to set them up, so they never call a model.
- Tests: the queue lists 25 claims; a decided claim shows its decision, reason, section and steps; a claim approved for $1,250.00 shows waiting for sign-off, the payment is refused, and signing off in the page moves it to decided; the instructions page shows the instructions.
- `docs/STATUS.md` describes what's built and how to run it; the README stays short.

Success criteria:

- [ ] `npm run e2e` passes, and the health test is kept or replaced by the queue test.
- [ ] Running `npm run e2e` twice in a row passes both times, and `backend/undercover.db` is unchanged by it.
- [ ] With the backend running and `OPENROUTER_API_KEY` set, the agent runs on five claims from the dashboard and each ends `decided` or `awaiting_sign_off` with a reason and section. (A manual check that calls the real model; accuracy against the handlers' decisions is for a later build.)
- [ ] `docs/STATUS.md` is up to date.
- [ ] `npm run check` passes in full.
