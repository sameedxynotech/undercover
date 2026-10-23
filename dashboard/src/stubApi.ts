import { vi } from "vitest";
import type {
  Claim,
  ClaimSummary,
  Customer,
  Decision,
  Handler,
  Policy,
} from "./api";

export const summary: ClaimSummary = {
  claim_id: "CLM-1001",
  customer_name: "Maya Patel",
  claim_type: "trip_delay",
  submitted_on: "2026-06-24",
  summary: "Flight home canceled",
  amount_claimed: 420,
  status: "decided",
  decision: "approve",
  payout: 420,
};

export const decision: Decision = {
  decision: "approve",
  payout: 420,
  reason: "The delay is covered.",
  policy_section: "3. Trip Delay",
  decided_at: "2026-10-23 19:19:47",
};

export const claim: Claim = {
  claim_id: "CLM-1001",
  policy_id: "POL-2001",
  customer_id: "CUS-3001",
  claim_type: "trip_delay",
  submitted_on: "2026-06-24",
  incident_date: "2026-06-18",
  incident_location: "Rome, Italy",
  summary: "Flight home canceled",
  story: "My flight home from Rome was canceled.",
  items: [
    { description: "Airport hotel", category: "accommodation", amount: 420 },
  ],
  amount_claimed: 420,
  documents: [
    { name: "Hotel receipt", type: "receipt", content: "One night: $420.00." },
  ],
  status: "decided",
  decision,
  sign_off: null,
  payment: { amount: 420, paid_at: "2026-10-23 19:19:49" },
  steps: [
    {
      step_id: 1,
      kind: "tool_call",
      text: 'get_claim({"claim_id": "CLM-1001"})',
      created_at: "2026-10-23 19:19:40",
    },
    {
      step_id: 2,
      kind: "thought",
      text: "Approved, $420.00",
      created_at: "2026-10-23 19:19:50",
    },
  ],
};

export const policy: Policy = {
  policy_id: "POL-2001",
  plan: "premium",
  add_ons: [],
  purchased_on: "2026-04-22",
  sold_through: "Meridian Air checkout",
  trip: {
    destination: "Rome, Italy",
    departs_on: "2026-06-10",
    returns_on: "2026-06-18",
    trip_cost: 3100,
  },
  travelers: ["Maya Patel"],
};

export const customer: Customer = {
  customer_id: "CUS-3001",
  name: "Maya Patel",
  email: "maya.patel@example.com",
  customer_since: "2023-04-11",
  previous_claims: [
    {
      claim_id: "CLM-0412",
      filed_on: "2024-08-19",
      claim_type: "baggage_delay",
      summary: "Checked bag arrived late",
      outcome: "approved",
      amount_paid: 140,
    },
  ],
};

export const handlers: Handler[] = [
  {
    handler_id: "HND-01",
    name: "Dana Whitfield",
    role: "Senior Claims Handler",
    can_approve_over_limit: true,
  },
];

export function stubApi(routes: Record<string, unknown>) {
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    if (!(key in routes))
      return Promise.resolve(new Response("{}", { status: 404 }));
    return Promise.resolve(new Response(JSON.stringify(routes[key])));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
