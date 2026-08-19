"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type JobStatus = "pending" | "processing" | "completed" | "failed";
type ReviewStatus = "pending_review" | "approved" | "rejected";

type Job = {
  id: string;
  input_path: string;
  incident_id: string | null;
  status: JobStatus;
  error_message: string | null;
  attempt_count: number;
  max_attempts: number;
  claimed_by: string | null;
  created_at: string;
};

type RetrievalTrace = {
  citation_id: string;
  score: number;
  content_hash: string;
  source_file: string;
};

type Report = {
  id: string;
  job_id: string;
  incident_id: string;
  root_cause: string;
  supporting_evidence: string[];
  recommended_actions: string[];
  verification_steps: string[];
  confidence: number;
  citation_ids: string[];
  status: ReviewStatus;
  reviewed_by: string | null;
  reviewer_feedback: string | null;
  reviewed_at: string | null;
  embedding_model: string;
  analysis_model: string;
  prompt_version: string;
  retrieval_backend: string;
  retrieval_limit: number;
  minimum_relevance_score: number;
  retrieved_sections: RetrievalTrace[];
  created_at: string;
};

type ReviewEvent = {
  id: string;
  previous_status: ReviewStatus;
  new_status: ReviewStatus;
  reviewed_by: string;
  reviewer_feedback: string | null;
  created_at: string;
};

type IncidentCatalogEntry = {
  incident_id: string;
  title: string;
  service: string;
  summary: string;
  input_path: string;
};

const formatTime = (value: string | null) => {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
};

export default function Home() {
  const [apiBase, setApiBase] = useState(() => {
    if (typeof window === "undefined") return "http://localhost:8000";
    return window.localStorage.getItem("rootpilot-api-base") ?? "http://localhost:8000";
  });
  const [token, setToken] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [incidents, setIncidents] = useState<IncidentCatalogEntry[]>([]);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [events, setEvents] = useState<ReviewEvent[]>([]);
  const [incidentId, setIncidentId] = useState("");
  const [feedback, setFeedback] = useState("");
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const headers = new Headers(init?.headers);
      headers.set("Content-Type", "application/json");
      if (token.trim()) headers.set("Authorization", `Bearer ${token.trim()}`);

      const response = await fetch(`${apiBase.replace(/\/$/, "")}${path}`, {
        ...init,
        headers,
      });

      if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try {
          const body = (await response.json()) as { detail?: string };
          if (body.detail) detail = body.detail;
        } catch {
          // Preserve the HTTP status when a proxy returns a non-JSON body.
        }
        throw new Error(detail);
      }

      return (await response.json()) as T;
    },
    [apiBase, token],
  );

  const refresh = useCallback(async () => {
    try {
      const [nextJobs, nextReports, nextIncidents] = await Promise.all([
        request<Job[]>("/jobs?limit=100"),
        request<Report[]>("/investigation-reports?limit=100"),
        request<IncidentCatalogEntry[]>("/incidents"),
      ]);
      setJobs(nextJobs);
      setReports(nextReports);
      setIncidents(nextIncidents);
      setIncidentId((current) => {
        if (nextIncidents.some((item) => item.incident_id === current)) {
          return current;
        }
        return nextIncidents[0]?.incident_id ?? "";
      });
      setConnected(true);
      setError(null);
      setLastUpdated(new Date());
      window.localStorage.setItem("rootpilot-api-base", apiBase);

      setSelectedReport((currentSelection) => {
        if (!currentSelection) return null;
        return (
          nextReports.find((item) => item.id === currentSelection.id) ??
          currentSelection
        );
      });
    } catch (caught) {
      setConnected(false);
      setError(caught instanceof Error ? caught.message : "Unable to load RootPilot");
    }
  }, [apiBase, request]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const stats = useMemo(
    () => ({
      active: jobs.filter((job) => job.status === "pending" || job.status === "processing").length,
      review: reports.filter((report) => report.status === "pending_review").length,
      approved: reports.filter((report) => report.status === "approved").length,
      failed: jobs.filter((job) => job.status === "failed").length,
    }),
    [jobs, reports],
  );

  const createJob = async (event: FormEvent) => {
    event.preventDefault();
    const incident = incidents.find((item) => item.incident_id === incidentId);
    if (!incident) {
      setError("Select an available incident before queuing an investigation.");
      return;
    }
    setBusy(true);
    try {
      await request<Job>("/jobs", {
        method: "POST",
        body: JSON.stringify({
          incident_id: incident.incident_id,
          max_attempts: 3,
        }),
      });
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to queue investigation");
    } finally {
      setBusy(false);
    }
  };

  const openReport = async (report: Report) => {
    setSelectedReport(report);
    try {
      setEvents(
        await request<ReviewEvent[]>(
          `/investigation-reports/${report.id}/review-events`,
        ),
      );
    } catch (caught) {
      setEvents([]);
      setError(caught instanceof Error ? caught.message : "Unable to load audit history");
    }
  };

  const review = async (status: "approved" | "rejected") => {
    if (!selectedReport) return;
    if (status === "rejected" && !feedback.trim()) {
      setError("Reviewer feedback is required when rejecting a report.");
      return;
    }
    setBusy(true);
    try {
      const updated = await request<Report>(
        `/investigation-reports/${selectedReport.id}/review`,
        {
          method: "PATCH",
          body: JSON.stringify({
            status,
            reviewed_by: "dashboard-operator",
            reviewer_feedback: feedback.trim() || null,
          }),
        },
      );
      setSelectedReport(updated);
      setFeedback("");
      await refresh();
      await openReport(updated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record review");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RootPilot operations home">
          <span className="brand-mark">RP</span>
          <span><strong>RootPilot</strong><small>Incident intelligence</small></span>
        </a>
        <div className="connection-strip">
          <span className={`status-dot ${connected ? "online" : "offline"}`} />
          <span>{connected ? "Control plane online" : "Connection required"}</span>
          <button className="quiet-button" onClick={() => void refresh()} disabled={busy}>
            Refresh
          </button>
        </div>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">Operations command center</p>
          <h1>Move from incident signal<br />to grounded decision.</h1>
          <p className="hero-copy">
            Queue investigations, inspect retrieved evidence, and keep every human
            decision attributable from one focused workspace.
          </p>
        </div>
        <form className="connection-card" onSubmit={(event) => { event.preventDefault(); void refresh(); }}>
          <label>
            API endpoint
            <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
          </label>
          <label>
            Bearer token
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              type="password"
              placeholder="Required when production auth is enabled"
              autoComplete="off"
            />
          </label>
          <button className="primary-button" type="submit">Connect workspace</button>
          <small>Token stays in memory and is cleared when this tab closes.</small>
        </form>
      </section>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button onClick={() => setError(null)} aria-label="Dismiss error">×</button>
        </div>
      )}

      <section className="stat-grid" aria-label="Operational summary">
        <article><span>Active jobs</span><strong>{stats.active}</strong><small>Pending or processing</small></article>
        <article><span>Awaiting review</span><strong>{stats.review}</strong><small>Human decision required</small></article>
        <article><span>Approved RCAs</span><strong>{stats.approved}</strong><small>Grounded and accepted</small></article>
        <article><span>Failed runs</span><strong>{stats.failed}</strong><small>Across current history</small></article>
      </section>

      <section className="workspace-grid">
        <div className="panel queue-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">New investigation</p><h2>Queue an incident</h2></div>
            <span className="number-badge">01</span>
          </div>
          <form className="queue-form" onSubmit={createJob}>
            <label>
              Prepared incident
              <select value={incidentId} onChange={(event) => setIncidentId(event.target.value)}>
                {incidents.map((incident) => (
                  <option key={incident.incident_id} value={incident.incident_id}>
                    {incident.incident_id} · {incident.title}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary-button" type="submit" disabled={busy || !connected || !incidentId}>
              {busy ? "Working…" : "Queue investigation"}
            </button>
          </form>
          <div className="job-list">
            {jobs.slice(0, 8).map((job) => (
              <article className="job-row" key={job.id}>
                <span className={`status-pill ${job.status}`}>{job.status}</span>
                <div><strong>{job.incident_id ?? "Unassigned incident"}</strong><small>{job.id.slice(0, 8)} · attempt {job.attempt_count}/{job.max_attempts}</small></div>
                <time>{formatTime(job.created_at)}</time>
              </article>
            ))}
            {!jobs.length && <p className="empty-state">No jobs yet. Queue the first investigation above.</p>}
          </div>
        </div>

        <div className="panel reports-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Review inbox</p><h2>Grounded assessments</h2></div>
            <span className="number-badge">02</span>
          </div>
          <div className="report-list">
            {reports.map((report) => (
              <button className="report-row" key={report.id} onClick={() => void openReport(report)}>
                <span className={`status-pill ${report.status}`}>{report.status.replace("_", " ")}</span>
                <span className="report-main"><strong>{report.incident_id}</strong><small>{report.root_cause}</small></span>
                <span className="confidence"><b>{Math.round(report.confidence * 100)}%</b><small>confidence</small></span>
                <span className="arrow">→</span>
              </button>
            ))}
            {!reports.length && <p className="empty-state">Completed investigations will appear here for review.</p>}
          </div>
        </div>
      </section>

      <footer>
        <span>RootPilot production console</span>
        <span>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Not synchronized"}</span>
      </footer>

      {selectedReport && (
        <div className="drawer-backdrop" role="presentation" onMouseDown={() => setSelectedReport(null)}>
          <aside className="report-drawer" role="dialog" aria-modal="true" aria-labelledby="report-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="drawer-head">
              <div><p className="eyebrow">{selectedReport.incident_id}</p><h2 id="report-title">Investigation report</h2></div>
              <button className="close-button" onClick={() => setSelectedReport(null)} aria-label="Close report">×</button>
            </div>
            <div className="assessment-lead">
              <span className={`status-pill ${selectedReport.status}`}>{selectedReport.status.replace("_", " ")}</span>
              <strong>{Math.round(selectedReport.confidence * 100)}% confidence</strong>
            </div>
            <section><h3>Most likely root cause</h3><p className="root-cause">{selectedReport.root_cause}</p></section>
            <section className="detail-columns">
              <div><h3>Supporting evidence</h3><ul>{selectedReport.supporting_evidence.map((item) => <li key={item}>{item}</li>)}</ul></div>
              <div><h3>Recommended actions</h3><ol>{selectedReport.recommended_actions.map((item) => <li key={item}>{item}</li>)}</ol></div>
            </section>
            <section><h3>Verification</h3><ol>{selectedReport.verification_steps.map((item) => <li key={item}>{item}</li>)}</ol></section>
            <section>
              <h3>Retrieved evidence</h3>
              <div className="trace-list">
                {selectedReport.retrieved_sections.map((trace) => (
                  <div key={trace.citation_id}><code>{trace.citation_id}</code><span>{trace.score.toFixed(4)}</span></div>
                ))}
                {!selectedReport.retrieved_sections.length && selectedReport.citation_ids.map((citation) => (
                  <div key={citation}><code>{citation}</code><span>legacy trace</span></div>
                ))}
              </div>
            </section>
            <section className="provenance-grid">
              <div><span>Analysis model</span><strong>{selectedReport.analysis_model}</strong></div>
              <div><span>Embedding model</span><strong>{selectedReport.embedding_model}</strong></div>
              <div><span>Prompt</span><strong>{selectedReport.prompt_version}</strong></div>
              <div><span>Retriever</span><strong>{selectedReport.retrieval_backend} · top {selectedReport.retrieval_limit}</strong></div>
            </section>
            {selectedReport.status === "pending_review" ? (
              <section className="review-box">
                <h3>Human decision</h3>
                <textarea value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Optional approval note; required for rejection" rows={3} />
                <div><button className="reject-button" disabled={busy} onClick={() => void review("rejected")}>Reject assessment</button><button className="approve-button" disabled={busy} onClick={() => void review("approved")}>Approve RCA</button></div>
              </section>
            ) : (
              <section className="audit-box">
                <h3>Audit history</h3>
                {events.map((event) => (
                  <div key={event.id}><span className={`status-dot ${event.new_status === "approved" ? "online" : "offline"}`} /><p><strong>{event.reviewed_by}</strong> changed {event.previous_status.replace("_", " ")} to {event.new_status}.<small>{formatTime(event.created_at)}{event.reviewer_feedback ? ` · ${event.reviewer_feedback}` : ""}</small></p></div>
                ))}
              </section>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}
