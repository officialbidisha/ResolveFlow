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

function GithubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg height={size} width={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

function CheckPill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`check-pill ${ok ? "check-ok" : "check-fail"}`}>
      <span className="check-dot" />
      {label}
    </span>
  );
}

type StepStatus = "pending" | "active" | "done" | "skipped";

const PIPELINE_STEPS: { key: string; label: string }[] = [
  { key: "fetch", label: "Fetch" },
  { key: "classify", label: "Classify" },
  { key: "diagnose", label: "Diagnose" },
  { key: "review", label: "Review" },
  { key: "approve", label: "Approve" },
  { key: "execute", label: "Execute" },
];

// Mirrors the actual graph, not a decorative progress bar: fetch_evidence ->
// classify -> generate_diagnosis -> independent_review -> await_approval ->
// execute. deterministic/human_review classifications skip the LLM
// diagnose/review steps entirely, and a reject skips execute -- both shown
// as "skipped", not stuck "pending" forever.
function pipelineStatuses(result: GraphResult | null, phase: Phase): StepStatus[] {
  if (!result) {
    return PIPELINE_STEPS.map((_, i) => (i === 0 && phase === "analyzing" ? "active" : "pending"));
  }

  const classification = result.classification;
  const isLlmPath = classification === "ai_investigation";
  // Both of these are genuinely terminal -- the run is finished and will
  // never reach an approval gate, not just "hasn't gotten there yet".
  const terminalNoGate = classification === "human_review" || result.review_result?.outcome === "escalate_to_human";

  const fetch: StepStatus = "done";
  const classify: StepStatus = classification ? "done" : "active";

  const diagnose: StepStatus = !classification
    ? "pending"
    : !isLlmPath
      ? "skipped"
      : result.diagnosis
        ? "done"
        : "active";

  const review: StepStatus = !isLlmPath
    ? "skipped"
    : result.review_result
      ? "done"
      : diagnose === "done"
        ? "active"
        : "pending";

  const approve: StepStatus = terminalNoGate
    ? "skipped"
    : result.pending_approval
      ? "active"
      : result.rejected || result.execution_result
        ? "done"
        : "pending";

  const execute: StepStatus = terminalNoGate
    ? "skipped"
    : result.execution_result
      ? "done"
      : result.rejected
        ? "skipped"
        : phase === "resuming"
          ? "active"
          : "pending";

  return [fetch, classify, diagnose, review, approve, execute];
}

function Pipeline({ result, phase }: { result: GraphResult | null; phase: Phase }) {
  const statuses = pipelineStatuses(result, phase);
  return (
    <div className="pipeline" aria-label="Pipeline progress">
      {PIPELINE_STEPS.map((step, i) => (
        <div className={`pipeline-step pipeline-${statuses[i]}`} key={step.key}>
          <span className="pipeline-dot" />
          <span className="pipeline-label">{step.label}</span>
          {i < PIPELINE_STEPS.length - 1 && <span className="pipeline-line" />}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [issueUrl, setIssueUrl] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GraphResult | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [userLoading, setUserLoading] = useState(true);
  const [slowHint, setSlowHint] = useState(false);

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
    // Render's free tier spins the backend down after ~15 min idle; a cold
    // start takes 30-50s to wake. Past a normal LLM round trip, swap the
    // label so a slow first request reads as "expected" instead of "hung."
    const slowTimer = setTimeout(() => setSlowHint(true), 4000);
    try {
      const data = await analyze(issueUrl.trim());
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setResult(null);
    } finally {
      clearTimeout(slowTimer);
      setSlowHint(false);
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
          {user ? (
            <div className="auth-status">
              <span className="mono">{user.login}</span>
              <button type="button" className="auth-link" onClick={handleLogout}>
                Log out
              </button>
            </div>
          ) : (
            <a className="auth-signin" href={GITHUB_LOGIN_URL}>
              <GithubIcon size={14} />
              Sign in with GitHub
            </a>
          )}
        </div>
        <h1>ResolveFlow</h1>
        <p className="thesis">
          Diagnoses a GitHub issue and proposes a fix — but never writes back to GitHub
          without passing an independent LLM review <em>and</em> your explicit approval.
        </p>
        <Pipeline result={result} phase={phase} />
      </header>

      {!userLoading && !user && (
        <div className="signin-gate">
          <div className="signin-gate-icon">
            <GithubIcon size={26} />
          </div>
          <h2 className="signin-gate-title">Sign in to analyze an issue</h2>
          <p className="signin-gate-copy">
            Reads and writes run as you, not the deployment owner. Limited to{" "}
            <span className="mono">30 analyses/day</span> per account.
          </p>
          <a className="signin-cta" href={GITHUB_LOGIN_URL}>
            <GithubIcon size={17} />
            Sign in with GitHub
          </a>
        </div>
      )}

      {(userLoading || user) && (
        <>
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
              {phase === "analyzing"
                ? slowHint
                  ? "Still working — waking up the server can take up to a minute…"
                  : "Analyzing…"
                : "Analyze"}
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
        </>
      )}

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
