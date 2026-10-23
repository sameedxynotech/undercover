import { useState } from "react";
import {
  post,
  useApi,
  type Claim,
  type Customer,
  type Handler,
  type Policy,
} from "./api";
import { money, time, words } from "./format";
import { StatusBadge } from "./StatusBadge";

export function ClaimPage({ claimId }: Readonly<{ claimId: string }>) {
  const {
    data: claim,
    error,
    reload,
  } = useApi<Claim>(`/api/claims/${claimId}`, 1000);

  if (error && !claim) return <p className="notice">{error}</p>;
  if (!claim) return <p className="notice">Loading {claimId}...</p>;

  return (
    <>
      <section className="claim-header">
        <div>
          <a href="#/">Back to the queue</a>
          <h2>
            <span className="mono">{claim.claim_id}</span> {claim.summary}
          </h2>
          <p className="muted">
            {words(claim.claim_type)} in {claim.incident_location} on{" "}
            {claim.incident_date}, submitted {claim.submitted_on}
          </p>
        </div>
        <div className="claim-actions">
          <StatusBadge status={claim.status} />
          {claim.status === "waiting" && (
            <RunAgent claimId={claim.claim_id} onStarted={reload} />
          )}
        </div>
      </section>
      <div className="columns">
        <div className="column">
          <DecisionPanel claim={claim} onSignedOff={reload} />
          <ClaimDetails claim={claim} />
        </div>
        <div className="column">
          <Steps claim={claim} />
          <PolicyPanel policyId={claim.policy_id} />
          <CustomerPanel customerId={claim.customer_id} />
        </div>
      </div>
    </>
  );
}

function RunAgent({
  claimId,
  onStarted,
}: Readonly<{
  claimId: string;
  onStarted: () => void;
}>) {
  const [busy, setBusy] = useState(false);

  const start = () => {
    setBusy(true);
    void post(`/api/claims/${claimId}/run`, {}).finally(() => {
      setBusy(false);
      onStarted();
    });
  };

  return (
    <button type="button" onClick={start} disabled={busy}>
      Run agent
    </button>
  );
}

function DecisionPanel({
  claim,
  onSignedOff,
}: Readonly<{
  claim: Claim;
  onSignedOff: () => void;
}>) {
  const { decision, payment, sign_off: signOff } = claim;

  if (!decision) {
    return (
      <section className="panel">
        <h3>Decision</h3>
        <p className="muted">
          {claim.status === "in_progress"
            ? "The agent is working on this claim."
            : "No decision yet."}
        </p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h3>Decision</h3>
      <p className={`decision decision-${decision.decision}`}>
        {words(decision.decision)}
        {decision.decision === "approve" && (
          <span className="mono"> {money(decision.payout)}</span>
        )}
      </p>
      <p>{decision.reason}</p>
      <p className="muted">Policy section: {decision.policy_section}</p>
      {claim.status === "awaiting_sign_off" && (
        <SignOffForm claim={claim} onSignedOff={onSignedOff} />
      )}
      {signOff && (
        <p className="muted">
          Signed off by {signOff.handler_name} on {time(signOff.signed_off_at)}
        </p>
      )}
      {payment && (
        <p className="paid">
          Paid <span className="mono">{money(payment.amount)}</span> on{" "}
          {time(payment.paid_at)}
        </p>
      )}
    </section>
  );
}

function SignOffForm({
  claim,
  onSignedOff,
}: Readonly<{
  claim: Claim;
  onSignedOff: () => void;
}>) {
  const { data: handlers } = useApi<Handler[]>("/api/handlers");
  const [handlerId, setHandlerId] = useState("");
  const eligible = (handlers ?? []).filter(
    (handler) => handler.can_approve_over_limit,
  );
  const chosen = handlerId || eligible.at(0)?.handler_id;

  const signOff = () => {
    if (!chosen) return;
    void post(`/api/claims/${claim.claim_id}/sign-off`, {
      handler_id: chosen,
    }).then(onSignedOff);
  };

  return (
    <div className="sign-off">
      <p>
        This payout is over $1,000.00, so the payment waits for a handler to
        sign off.
      </p>
      <label>
        Handler{" "}
        <select
          value={chosen ?? ""}
          onChange={(event) => {
            setHandlerId(event.target.value);
          }}
        >
          {eligible.map((handler) => (
            <option key={handler.handler_id} value={handler.handler_id}>
              {handler.name}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={signOff} disabled={!chosen}>
        Sign off and pay {money(claim.decision?.payout ?? 0)}
      </button>
    </div>
  );
}

function ClaimDetails({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <>
      <section className="panel">
        <h3>The customer's story</h3>
        <p>{claim.story}</p>
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Category</th>
              <th className="number">Amount</th>
            </tr>
          </thead>
          <tbody>
            {claim.items.map((item) => (
              <tr key={item.description}>
                <td>{item.description}</td>
                <td>{words(item.category)}</td>
                <td className="number mono">{money(item.amount)}</td>
              </tr>
            ))}
            <tr className="total">
              <td>Total claimed</td>
              <td />
              <td className="number mono">{money(claim.amount_claimed)}</td>
            </tr>
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h3>Documents</h3>
        {claim.documents.map((document) => (
          <article key={document.name} className="document">
            <h4>
              {document.name}{" "}
              <span className="muted">{words(document.type)}</span>
            </h4>
            <p>{document.content}</p>
          </article>
        ))}
      </section>
    </>
  );
}

function Steps({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel">
      <h3>What the agent did</h3>
      {claim.steps.length === 0 ? (
        <p className="muted">The agent hasn't worked on this claim yet.</p>
      ) : (
        <ol className="steps">
          {claim.steps.map((step) => (
            <li key={step.step_id} className={`step step-${step.kind}`}>
              <span className="step-kind">{words(step.kind)}</span>
              <span className="step-text">{step.text}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function PolicyPanel({ policyId }: Readonly<{ policyId: string }>) {
  const { data: policy } = useApi<Policy>(`/api/policies/${policyId}`);
  if (!policy) return null;

  return (
    <section className="panel">
      <h3>
        Policy <span className="mono">{policy.policy_id}</span>
      </h3>
      <dl>
        <dt>Plan</dt>
        <dd>{words(policy.plan)}</dd>
        <dt>Add-ons</dt>
        <dd>
          {policy.add_ons.length
            ? policy.add_ons.map(words).join(", ")
            : "None"}
        </dd>
        <dt>Bought</dt>
        <dd className="mono">{policy.purchased_on}</dd>
        <dt>Trip</dt>
        <dd>
          {policy.trip.destination},{" "}
          <span className="mono">
            {policy.trip.departs_on} to {policy.trip.returns_on}
          </span>
        </dd>
        <dt>Trip cost</dt>
        <dd className="mono">{money(policy.trip.trip_cost)}</dd>
        <dt>Travelers</dt>
        <dd>{policy.travelers.join(", ")}</dd>
      </dl>
    </section>
  );
}

function CustomerPanel({ customerId }: Readonly<{ customerId: string }>) {
  const { data: customer } = useApi<Customer>(`/api/customers/${customerId}`);
  if (!customer) return null;

  return (
    <section className="panel">
      <h3>{customer.name}</h3>
      <p className="muted">
        Customer since {customer.customer_since}, {customer.email}
      </p>
      <h4>Claim history</h4>
      {customer.previous_claims.length === 0 ? (
        <p className="muted">No earlier claims.</p>
      ) : (
        <ul className="history">
          {customer.previous_claims.map((previous) => (
            <li key={previous.claim_id}>
              <span className="mono">{previous.claim_id}</span>{" "}
              {previous.filed_on}: {previous.summary}. {words(previous.outcome)}
              , paid <span className="mono">{money(previous.amount_paid)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
