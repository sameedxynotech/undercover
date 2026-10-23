# Status

The claims pilot from `docs/SPEC.md`, built to `docs/PLAN.md`.

Built so far:

- `backend/`: FastAPI on SQLite. The database is `backend/undercover.db`, or the path in `UNDERCOVER_DB`; it is created and seeded from `data/` on startup when missing. Delete it to reset. Read routes for the claims queue, claims, policies, customers, plans, the policy wording and the handlers. Write routes to start a claim, record the agent's steps, decide, pay, sign off and record a failed run. A payout over $1,000 is refused by `pay_claim` until a handler signs off, and the sign-off releases the payment.
- `agent/`: the hello-world skeleton, `run(claim_id, thread_id)` with one tool.
- `dashboard/`: one page that shows whether the backend is up.
- `e2e/`: one test of that page.

## Running it

- `npm run dev` starts the backend on port 8000 and the dashboard on port 5173.
- `npm run check` runs every check.
