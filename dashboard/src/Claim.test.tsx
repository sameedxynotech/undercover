import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Claim } from "./api";
import { ClaimPage } from "./Claim";
import {
  claim,
  customer,
  decision,
  handlers,
  policy,
  stubApi,
} from "./stubApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubClaim(shown: Claim) {
  return stubApi({
    "GET /api/claims/CLM-1001": shown,
    "GET /api/policies/POL-2001": policy,
    "GET /api/customers/CUS-3001": customer,
    "GET /api/handlers": handlers,
    "POST /api/claims/CLM-1001/run": { status: "in_progress" },
    "POST /api/claims/CLM-1001/sign-off": { status: "decided" },
  });
}

it("shows a decided claim in full", async () => {
  stubClaim(claim);
  render(<ClaimPage claimId="CLM-1001" />);
  expect(await screen.findByText("The delay is covered.")).toBeDefined();
  expect(screen.getByText("Policy section: 3. Trip Delay")).toBeDefined();
  expect(
    screen.getByText("My flight home from Rome was canceled."),
  ).toBeDefined();
  expect(screen.getByText("One night: $420.00.")).toBeDefined();
  expect(screen.getByText('get_claim({"claim_id": "CLM-1001"})')).toBeDefined();
  expect(screen.getByText("Approved, $420.00")).toBeDefined();
  expect(await screen.findByText(/Checked bag arrived late/)).toBeDefined();
  expect(await screen.findByText("Premium")).toBeDefined();
  expect(screen.queryByText("Run agent")).toBeNull();
});

it("runs the agent on a waiting claim", async () => {
  const fetch = stubClaim({
    ...claim,
    status: "waiting",
    decision: null,
    payment: null,
    steps: [],
  });
  render(<ClaimPage claimId="CLM-1001" />);
  expect(await screen.findByText("No decision yet.")).toBeDefined();
  expect(
    screen.getByText("The agent hasn't worked on this claim yet."),
  ).toBeDefined();
  fireEvent.click(screen.getByText("Run agent"));
  expect(fetch).toHaveBeenCalledWith(
    "/api/claims/CLM-1001/run",
    expect.objectContaining({ method: "POST" }),
  );
});

it("says when the agent is working", async () => {
  stubClaim({ ...claim, status: "in_progress", decision: null, payment: null });
  render(<ClaimPage claimId="CLM-1001" />);
  expect(
    await screen.findByText("The agent is working on this claim."),
  ).toBeDefined();
});

it("signs off a payout over the limit", async () => {
  const fetch = stubClaim({
    ...claim,
    status: "awaiting_sign_off",
    decision: { ...decision, payout: 1250 },
    payment: null,
  });
  render(<ClaimPage claimId="CLM-1001" />);
  const button = await screen.findByText("Sign off and pay $1,250.00");
  await screen.findByText("Dana Whitfield");
  fireEvent.click(button);
  expect(fetch).toHaveBeenCalledWith(
    "/api/claims/CLM-1001/sign-off",
    expect.objectContaining({ body: JSON.stringify({ handler_id: "HND-01" }) }),
  );
});

it("shows who signed off", async () => {
  stubClaim({
    ...claim,
    sign_off: {
      handler_id: "HND-01",
      handler_name: "Dana Whitfield",
      signed_off_at: "2026-10-23 19:30:00",
    },
  });
  render(<ClaimPage claimId="CLM-1001" />);
  expect(await screen.findByText(/Signed off by Dana Whitfield/)).toBeDefined();
});

it("says when a claim can't be found", async () => {
  stubApi({});
  render(<ClaimPage claimId="CLM-9999" />);
  expect(
    await screen.findByText("Error: /api/claims/CLM-9999 returned 404"),
  ).toBeDefined();
});
