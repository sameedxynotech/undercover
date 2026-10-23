import { useApi, type ClaimSummary, type Status } from "./api";
import { money, STATUS_LABELS, words } from "./format";
import { StatusBadge } from "./StatusBadge";

const STATUSES: Status[] = [
  "waiting",
  "in_progress",
  "awaiting_sign_off",
  "decided",
];

export function Queue() {
  const { data: claims, error } = useApi<ClaimSummary[]>("/api/claims", 3000);

  if (error && !claims) return <p className="notice">{error}</p>;
  if (!claims) return <p className="notice">Loading the queue...</p>;

  return (
    <>
      <section className="counts" aria-label="Claims by status">
        {STATUSES.map((status) => (
          <div key={status} className={`count count-${status}`}>
            <span className="count-number">
              {claims.filter((claim) => claim.status === status).length}
            </span>
            <span>{STATUS_LABELS[status]}</span>
          </div>
        ))}
      </section>
      <section className="panel">
        <h2>Claims queue</h2>
        <table>
          <thead>
            <tr>
              <th>Claim</th>
              <th>Customer</th>
              <th>Type</th>
              <th>Submitted</th>
              <th className="number">Claimed</th>
              <th>Status</th>
              <th>Decision</th>
              <th className="number">Payout</th>
            </tr>
          </thead>
          <tbody>
            {claims.map((claim) => (
              <tr key={claim.claim_id}>
                <td>
                  <a className="mono" href={`#/claims/${claim.claim_id}`}>
                    {claim.claim_id}
                  </a>
                </td>
                <td>{claim.customer_name}</td>
                <td>{words(claim.claim_type)}</td>
                <td className="mono">{claim.submitted_on}</td>
                <td className="number mono">{money(claim.amount_claimed)}</td>
                <td>
                  <StatusBadge status={claim.status} />
                </td>
                <td>{claim.decision ? words(claim.decision) : ""}</td>
                <td className="number mono">
                  {claim.payout === null ? "" : money(claim.payout)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
