import { useEffect, useState } from "react";
import { GITHUB_LOGIN_URL, analyze, getCurrentUser, logout, resume } from "./api";
import type { CurrentUser } from "./api";
import type { GraphResult } from "./types";

const EXAMPLE_URLS = [
  "https://github.com/facebook/react/issues/36765",
  "https://github.com/facebook/react/issues/36932",
];

type Phase = "idle" | "analyzing" | "resuming";

function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge badge-severity-${severity}`}>{severity}</span>;
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const cls = outcome === "approve" ? "badge-approve" : "badge-escalate";
  return <span className={`badge ${cls}`}>{outcome.replace(/_/g, " ")}</span>;
}

function ClassificationBadge({ classification }: { classification: string }) {
  return <span className="badge badge-classification">{classification.replace(/_/g, " ")}</span>;
}

function CheckPill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`check-pill ${ok ? "check-ok" : "check-fail"}`}>
      <span className="check-dot" />
      {label}
    </span>
  );
}

export default function App() {
  const [issueUrl, setIssueUrl] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GraphResult | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [userLoading, setUserLoading] = useState(true);

  const busy = phase !== "idle";

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .finally(() => setUserLoading(false));
  }, []);

  async function handleLogout() {
    await logout();
    setUser(null);
    setResult(null);
  }

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    if (!user) {
      setError("Sign in with GitHub first.");
      return;
    }
    if (!issueUrl.trim()) {
      setError("Paste an issue URL first.");
      return;
    }
    setError(null);
    setPhase("analyzing");
    try {
      const data = await analyze(issueUrl.trim());
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setResult(null);
    } finally {
      setPhase("idle");
    }
  }

  async function handleDecision(approved: boolean) {
    if (!result) return;
    setError(null);
    setPhase("resuming");
    try {
      const data = await resume(result.thread_id, approved);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPhase("idle");
    }
  }

  return (
    <div className="page">
      <header className="header">
        <div className="auth-bar">
          <div className="eyebrow">LangGraph &middot; approval-gated execution</div>
          {!userLoading &&
            (user ? (
              <div className="auth-status">
                <span className="mono">{user.login}</span>
                <button type="button" className="auth-link" onClick={handleLogout}>
                  Log out
                </button>
              </div>
            ) : (
              <a className="auth-link auth-signin" href={GITHUB_LOGIN_URL}>
                Sign in with GitHub
              </a>
            ))}
        </div>
        <h1>ResolveFlow</h1>
        <p className="thesis">
          Diagnoses a GitHub issue and proposes a fix — but never writes back to GitHub
          without passing an independent LLM review <em>and</em> your explicit approval.
        </p>
      </header>

      {!userLoading && !user && (
        <div className="banner banner-info">
          Sign in with your own GitHub account to analyze an issue — reads/writes run as
          you, not the deployment owner. Limited to{" "}
          <span className="mono">30 analyses/day</span> per account.
        </div>
      )}

      <form className="analyze-form" onSubmit={handleAnalyze}>
        <input
          type="text"
          value={issueUrl}
          onChange={(e) => setIssueUrl(e.target.value)}
          placeholder="https://github.com/owner/repo/issues/123"
          disabled={busy || !user}
          aria-label="GitHub issue URL"
        />
        <button type="submit" disabled={busy || !user}>
          {phase === "analyzing" && <span className="spinner" />}
          {phase === "analyzing" ? "Analyzing…" : "Analyze"}
        </button>
      </form>

      <div className="examples">
        Try:{" "}
        {EXAMPLE_URLS.map((url, i) => (
          <span key={url}>
            <button
              type="button"
              className="example-link"
              onClick={() => setIssueUrl(url)}
              disabled={busy || !user}
            >
              {url.replace("https://github.com/", "")}
            </button>
            {i < EXAMPLE_URLS.length - 1 && <span className="example-sep">&middot;</span>}
          </span>
        ))}
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      {result?.evidence && (
        <section className="card">
          <div className="card-head">
            <h2>{result.evidence.title || "(untitled)"}</h2>
            {result.classification && (
              <ClassificationBadge classification={result.classification} />
            )}
          </div>
          <div className="meta-row">
            <span className="mono">
              {result.evidence.repo} #{result.evidence.issue_number}
            </span>
            <span className="dim">
              labels: {result.evidence.labels.length ? result.evidence.labels.join(", ") : "—"}
            </span>
          </div>
          {result.evidence.body && (
            <details className="expander">
              <summary>Issue body</summary>
              <p className="body-text">{result.evidence.body}</p>
            </details>
          )}
          {result.evidence.comments.length > 0 && (
            <details className="expander">
              <summary>Comments ({result.evidence.comments.length})</summary>
              {result.evidence.comments.map((c, i) => (
                <p className="body-text" key={i}>
                  {c}
                </p>
              ))}
            </details>
          )}
        </section>
      )}

      {result?.classification === "human_review" && (
        <div className="banner banner-info">
          Routed to <span className="mono">human_review</span> — the conservative fallback
          classification. No diagnosis is attempted for it by design.
        </div>
      )}

      {result?.diagnosis && (
        <section className="card">
          <h3 className="section-label">Diagnosis</h3>
          <p className="root-cause">{result.diagnosis.root_cause}</p>
          <div className="meta-row">
            <span className="dim">Severity</span>
            <SeverityBadge severity={result.diagnosis.severity} />
          </div>
          {result.diagnosis.missing_info.length > 0 && (
            <div className="sub-block">
              <span className="dim">Missing info</span>
              <ul>
                {result.diagnosis.missing_info.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="sub-block">
            <span className="dim">Recommended next steps</span>
            <ul>
              {result.diagnosis.recommended_next_steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
          <div className="citations">
            {result.diagnosis.citations.map((c) => (
              <span className="citation-chip" key={c}>
                {c}
              </span>
            ))}
          </div>
        </section>
      )}

      {result?.review_result && (
        <section className="card">
          <div className="card-head">
            <h3 className="section-label">Independent review</h3>
            <OutcomeBadge outcome={result.review_result.outcome} />
          </div>
          <div className="checks-row">
            <CheckPill label="groundedness_ok" ok={result.review_result.groundedness_ok} />
            <CheckPill label="risk_ok" ok={result.review_result.risk_ok} />
            <CheckPill label="permission_ok" ok={result.review_result.permission_ok} />
          </div>
          <p className="reasoning-text">{result.review_result.reasoning}</p>
          {result.review_result.outcome === "escalate_to_human" && (
            <div className="banner banner-info">
              Escalated to a human — no proposed action was generated, nothing to approve.
            </div>
          )}
        </section>
      )}

      {result?.pending_approval && (
        <section className="card card-gate">
          <h3 className="section-label section-label-gate">Pending human approval</h3>
          <p className="gate-caption">
            This is the exact comment <span className="mono">execute</span> will post —
            nothing gets recomputed after you decide.
          </p>
          <pre className="proposed-comment">{result.pending_approval.proposed_action.comment}</pre>
          {result.pending_approval.proposed_action.label && (
            <div className="label-to-add">
              Label to add: <span className="mono">{result.pending_approval.proposed_action.label}</span>
            </div>
          )}
          <div className="gate-actions">
            <button
              type="button"
              className="btn-approve"
              disabled={busy}
              onClick={() => handleDecision(true)}
            >
              {phase === "resuming" && <span className="spinner" />}
              {phase === "resuming" ? "Posting…" : "Approve — post to GitHub"}
            </button>
            <button
              type="button"
              className="btn-reject"
              disabled={busy}
              onClick={() => handleDecision(false)}
            >
              Reject
            </button>
          </div>
        </section>
      )}

      {result?.execution_result && (
        <div className="banner banner-success">
          Posted to GitHub.
          {result.execution_result.comment &&
            "id" in result.execution_result.comment && (
              <span className="mono"> comment #{String(result.execution_result.comment.id)}</span>
            )}
        </div>
      )}

      {result?.execution_result?.label_error && (
        <div className="banner banner-info">
          Comment posted, but couldn't add the label — you likely don't have
          triage/write access on this repo. Commenting is open to any signed-in
          user; labeling isn't.
        </div>
      )}

      {result?.rejected && (
        <div className="banner banner-info">Rejected — nothing was posted to GitHub.</div>
      )}

      <footer className="footer">
        <span>fetch_evidence → classify → generate_diagnosis → independent_review → await_approval → execute</span>
        <a href="https://github.com/officialbidisha/ResolveFlow" target="_blank" rel="noopener noreferrer">
          github.com/officialbidisha/ResolveFlow
        </a>
      </footer>
    </div>
  );
}
