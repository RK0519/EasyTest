import { useEffect, useMemo, useRef, useState } from "react";

const STAGES = [
  ["crawling", "Map the site"],
  ["planning", "Find the flows"],
  ["generating", "Write test cases"],
];

export default function App() {
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(6);
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ flow: "All", priority: "All", type: "All", source: "All" });
  const [open, setOpen] = useState(null);
  const timer = useRef(null);

  const running = job && job.status === "running";

  useEffect(() => () => clearInterval(timer.current), []);

  async function start(e) {
    e.preventDefault();
    setError("");
    setJob(null);
    setOpen(null);
    setFilters({ flow: "All", priority: "All", type: "All", source: "All" });
    try {
      const r = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), max_pages: Number(maxPages) }),
      });
      if (!r.ok) throw new Error("The server rejected the request.");
      const { job_id } = await r.json();
      setJob({ id: job_id, status: "running", stage: "queued", message: "Starting", flows: [], test_cases: [], warnings: [] });
      clearInterval(timer.current);
      timer.current = setInterval(async () => {
        try {
          const j = await (await fetch(`/api/jobs/${job_id}`)).json();
          setJob(j);
          if (j.status !== "running") clearInterval(timer.current);
        } catch {
          setError("Lost connection to the backend. Is it running on port 8000?");
          clearInterval(timer.current);
        }
      }, 1500);
    } catch (err) {
      setError(err.message || "Could not reach the backend. Is it running on port 8000?");
    }
  }

  const cases = job?.test_cases || [];
  const options = useMemo(() => ({
    flow: ["All", ...new Set(cases.map((c) => c.flow))],
    priority: ["All", "High", "Medium", "Low"],
    type: ["All", "Positive", "Negative", "Boundary", "Edge"],
    source: ["All", "Observed", "Inferred"],
  }), [cases]);
  const shown = cases.filter((c) => Object.entries(filters).every(([k, v]) => v === "All" || c[k] === v));

  const stageIdx = job ? STAGES.findIndex(([k]) => k === job.stage) : -1;

  return (
    <main className="shell">
      <header className="top">
        <h1>EasyTest</h1>
        <p>Paste a website address. The agent maps its pages, works out the main user journeys, and writes functional test cases for each one.</p>
        <form onSubmit={start} className="entry">
          <input
            value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.zerodha.com" aria-label="Website URL" required disabled={running}
          />
          <label className="pages">
            Pages to visit
            <input type="number" min="1" max="15" value={maxPages} onChange={(e) => setMaxPages(e.target.value)} disabled={running} />
          </label>
          <button disabled={running || !url.trim()}>{running ? "Working…" : "Generate test cases"}</button>
        </form>
        {error && <p className="alert" role="alert">{error}</p>}
      </header>

      {job && (
        <section className="status" aria-live="polite">
          <ol className="steps">
            {STAGES.map(([k, label], i) => {
              const state = job.status === "done" || i < stageIdx ? "done" : i === stageIdx && job.status === "running" ? "active" : "idle";
              return <li key={k} className={state}>{label}</li>;
            })}
          </ol>
          <p className={job.status === "error" ? "alert" : "msg"}>{job.message}</p>
          {job.warnings?.map((w, i) => <p key={i} className="warn">{w}</p>)}
        </section>
      )}

      {job?.site_type && (
        <section className="overview">
          <h2>{job.site_type}</h2>
          <p>{job.summary}</p>
          <ul className="flows">
            {job.flows.map((f) => (
              <li key={f.name}>
                <strong>{f.name}</strong>
                <span className={`tag ${f.observed ? "obs" : "inf"}`}>{f.observed ? "Observed" : "Inferred"}</span>
                <span className="desc">{f.description}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {cases.length > 0 && (
        <section className="results">
          <div className="bar">
            <h2>{shown.length} of {cases.length} test cases</h2>
            <a className="btn" href={`/api/jobs/${job.id}/export`}>Download Excel</a>
          </div>
          <div className="filters">
            {Object.keys(options).map((k) => (
              <label key={k}>{k}
                <select value={filters[k]} onChange={(e) => setFilters({ ...filters, [k]: e.target.value })}>
                  {options[k].map((o) => <option key={o}>{o}</option>)}
                </select>
              </label>
            ))}
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Flow</th><th>Test case</th><th>Type</th><th>Priority</th><th>Source</th></tr></thead>
              <tbody>
                {shown.map((c) => (
                  <>
                    <tr key={c.id} className={open === c.id ? "sel" : ""} onClick={() => setOpen(open === c.id ? null : c.id)}>
                      <td>{c.id}</td><td>{c.flow}</td><td>{c.title}</td><td>{c.type}</td>
                      <td><span className={`pri ${c.priority}`}>{c.priority}</span></td>
                      <td>{c.source}</td>
                    </tr>
                    {open === c.id && (
                      <tr key={c.id + "d"} className="detail"><td colSpan="6">
                        <dl>
                          <dt>Preconditions</dt><dd>{c.preconditions || "None"}</dd>
                          <dt>Steps</dt><dd><ol>{c.steps.map((s, i) => <li key={i}>{s}</li>)}</ol></dd>
                          <dt>Test data</dt><dd>{c.test_data || "None"}</dd>
                          <dt>Expected result</dt><dd>{c.expected_result}</dd>
                        </dl>
                      </td></tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
