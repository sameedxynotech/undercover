import { useApi } from "./api";

export function Instructions() {
  const { data: instructions } = useApi<string>("/api/instructions");

  return (
    <section className="panel">
      <h2>The agent's instructions</h2>
      <p className="muted">Read only. These are what the agent works from.</p>
      <pre className="instructions">{instructions ?? "Loading..."}</pre>
    </section>
  );
}
