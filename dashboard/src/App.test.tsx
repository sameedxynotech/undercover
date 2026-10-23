import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { stubApi, summary } from "./stubApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

it("shows the queue with counts by status", async () => {
  stubApi({
    "GET /api/claims": [
      summary,
      {
        ...summary,
        claim_id: "CLM-1002",
        status: "waiting",
        decision: null,
        payout: null,
      },
    ],
  });
  render(<App />);
  expect(await screen.findByText("CLM-1002")).toBeDefined();
  const counts = screen.getByLabelText("Claims by status");
  expect(within(counts).getByText("Waiting").previousSibling?.textContent).toBe(
    "1",
  );
  expect(within(counts).getByText("Decided").previousSibling?.textContent).toBe(
    "1",
  );
  expect(screen.getAllByText("$420.00")).toHaveLength(3);
  expect(screen.getAllByText("Trip delay")).toHaveLength(2);
});

it("says when the backend can't be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(<App />);
  expect(await screen.findByText("Error: offline")).toBeDefined();
});

it("shows the agent's instructions", async () => {
  stubApi({ "GET /api/instructions": "You are the UnderCover Agent." });
  window.location.hash = "#/instructions";
  render(<App />);
  expect(
    await screen.findByText("You are the UnderCover Agent."),
  ).toBeDefined();
});

it("follows the hash to a claim", async () => {
  stubApi({ "GET /api/claims": [summary] });
  render(<App />);
  await screen.findByText("CLM-1001");
  act(() => {
    window.location.hash = "#/claims/CLM-1001";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(await screen.findByText("Loading CLM-1001...")).toBeDefined();
});
