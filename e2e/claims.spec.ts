import { expect, test, type APIRequestContext } from "@playwright/test";

async function decide(
  request: APIRequestContext,
  claimId: string,
  decision: string,
  payout: number,
) {
  await request.post(`/api/claims/${claimId}/start`);
  await request.post(`/api/claims/${claimId}/steps`, {
    data: { kind: "tool_call", text: `get_claim({"claim_id": "${claimId}"})` },
  });
  await request.post(`/api/claims/${claimId}/decision`, {
    data: {
      decision,
      payout,
      reason: "The wording settles this claim.",
      policy_section: "5. Baggage and Personal Effects",
    },
  });
}

test("the queue lists every claim", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Claims queue" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(25);
  await expect(page.getByRole("link", { name: "CLM-1001" })).toBeVisible();
});

test("a decided claim shows its decision and the agent's steps", async ({
  page,
  request,
}) => {
  await decide(request, "CLM-1005", "decline", 0);
  await page.goto("/#/claims/CLM-1005");
  await expect(page.getByText("Decline", { exact: true })).toBeVisible();
  await expect(page.getByText("The wording settles this claim.")).toBeVisible();
  await expect(
    page.getByText("Policy section: 5. Baggage and Personal Effects"),
  ).toBeVisible();
  await expect(
    page.getByText('get_claim({"claim_id": "CLM-1005"})'),
  ).toBeVisible();
  await expect(
    page.locator(".claim-actions").getByText("Decided"),
  ).toBeVisible();
});

test("a payout over $1,000 waits for a handler's sign-off", async ({
  page,
  request,
}) => {
  await decide(request, "CLM-1011", "approve", 1250);
  const payment = await request.post("/api/claims/CLM-1011/payment", {
    data: { amount: 1250 },
  });
  expect(payment.status()).toBe(409);

  await page.goto("/#/claims/CLM-1011");
  const status = page.locator(".claim-actions");
  await expect(status.getByText("Waiting for sign-off")).toBeVisible();
  await page
    .getByRole("button", { name: "Sign off and pay $1,250.00" })
    .click();
  await expect(status.getByText("Decided")).toBeVisible();
  await expect(page.getByText(/^Paid \$1,250\.00/)).toBeVisible();
  await expect(page.getByText(/Signed off by Dana Whitfield/)).toBeVisible();
});

test("the agent's instructions are shown read only", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Instructions" }).click();
  await expect(page.getByText(/^You are the UnderCover Agent\./)).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
});
