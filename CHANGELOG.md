# Changelog

All notable changes to ResolveFlow are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **GitHub OAuth ("Sign in with GitHub") so any visitor can use the live
  app under their own identity.** Root cause: every request previously ran
  under one shared `GITHUB_TOKEN` (the deployment owner's), so a stranger
  using the public site would read/write GitHub *as the owner* — wrong
  attribution, and a single shared rate limit. `app/main.py` gained
  `/api/auth/github/login` + `/callback` (Authorization Code flow via
  `httpx`) + `/me` + `/logout`; `app/db.py` adds a `sessions` table (opaque
  cookie -> real GitHub token, kept server-side, never sent to the
  browser) in the same Postgres as the checkpointer, on its own
  `psycopg_pool.AsyncConnectionPool` (the checkpointer's `AsyncPostgresSaver`
  owns its own schema and connection, not reused for app tables).
  `tools/github_client.py`'s functions all gained an optional `token`
  param (falls back to `GITHUB_TOKEN` when unset, so `ingest.py` and local
  scripts are unaffected); `graph/state.py` gained `github_token`, threaded
  through by `fetch_evidence.py`/`execute.py` so the graph reads/writes as
  the logged-in visitor.
- **Two things this opened up that needed closing, not just the happy
  path:** (1) the owner's `OPENAI_API_KEY`/`PINECONE_API_KEY` still fund
  every `generate_diagnosis`/`independent_review` call regardless of who's
  asking — added a per-GitHub-user daily cap (`analyze_calls` table,
  `DAILY_ANALYZE_LIMIT = 10`, atomic `INSERT ... ON CONFLICT ... count + 1`)
  so one visitor can't run up the owner's bill. (2) `/api/resume/{thread_id}`
  previously accepted any `thread_id` from anyone — with multiple real
  users that meant one visitor could approve/reject *another visitor's*
  paused action. Added a `thread_owners` table recording who started each
  run; `/api/resume` now 403s if the caller isn't that thread's owner.

### Fixed
- **Registered the Pydantic state schemas with LangGraph's checkpoint
  serializer.** `graph/serde.py` builds a `JsonPlusSerializer` with
  `allowed_msgpack_modules` covering `IssueEvidence`/`CheckRun`/`LinkedPR`/
  `Diagnosis`/`ReviewResult`, passed to both `MemorySaver`
  (`graph/build.py`) and `AsyncPostgresSaver` (`app/main.py`). Closes the
  "Known issue" below and roadmap item 3 in `README.md` — resuming a
  paused run no longer logs a deprecation warning, and won't break once a
  future LangGraph version enforces `LANGGRAPH_STRICT_MSGPACK`.

### Changed
- **`app/main.py`'s checkpointer swapped from `SqliteSaver` to
  `AsyncPostgresSaver`.** Root cause: Render's free-tier web services have
  an ephemeral filesystem (no persistent disk without a paid add-on) —
  every spin-down/spin-up cycle after idle gets a fresh container, wiping
  local `checkpoints.db` along with it. Any run paused at `await_approval`
  during that window would silently lose its pending approval on resume:
  the checkpointer would have no history for that `thread_id`. A real
  Postgres instance isn't on the app host's disk at all, so it survives
  container recycling. `AsyncPostgresSaver` has no sync API, so this made
  the whole file async: `async def` endpoints, `await saver.setup()`,
  `.ainvoke()` instead of `.invoke()`. Graph node functions themselves
  stay synchronous — LangGraph runs sync nodes in a thread pool
  automatically under `ainvoke()`, so nothing in `graph/nodes/*.py`
  needed to change. Requires a real `DATABASE_URL` now (Neon/Supabase/
  Render Postgres all work) — not yet verified against a live Postgres
  instance end-to-end, only that the module imports and the FastAPI app
  builds correctly; do that verification before relying on it in
  production.

### Removed
- `ui.py` (Streamlit) and the `streamlit` dependency. Now that the React
  frontend + FastAPI backend are deployed and verified end-to-end (see
  [0.7.0] below), the Streamlit UI was a redundant, unmaintained second
  surface — it drove `compiled_graph` directly with `MemorySaver`, which
  can't survive across separate HTTP requests the way the deployed app
  needs to, so it was never going to be the production path. `graph/build.py`
  still exports `compiled_graph` (`MemorySaver`) as a local/ad-hoc
  convenience — e.g. for a REPL or future tests — just not as an app
  entry point anymore.
- `faiss-cpu`, `scikit-learn`, `langchain-community` from `pyproject.toml`
  — leftover from the pre-Pinecone TF-IDF/FAISS retrieval stack (see
  [0.5.0]); confirmed zero imports before removing. `uv sync` dropped 10
  packages total once transitive deps (`scipy`, `sqlalchemy`, `joblib`,
  etc.) were included.

## [0.7.0] — React frontend, deployed

### Added
- `app/main.py`: FastAPI backend exposing the compiled graph over HTTP
  (`POST /api/analyze`, `POST /api/resume/{thread_id}`). Compiles the
  graph with `SqliteSaver` (persistent, opened once at startup) instead
  of `ui.py`'s `MemorySaver` — a real HTTP API has "analyze" and
  "resume" land on separate requests, sometimes seconds apart, so the
  checkpointer has to survive between them, not just within one Python
  process's memory.
- `graph/build.py` now exports the uncompiled `graph` alongside
  `compiled_graph`, so callers needing a different checkpointer than
  `ui.py`'s `MemorySaver` can compile it themselves.
- `frontend/`: React + TypeScript (Vite) UI, same visual identity as the
  published architecture-diagram artifact (IBM Plex Mono/Sans; amber =
  approval gate, blue = reasoning, green = write, matching the graph's
  node roles). Renders evidence, diagnosis, independent review (with
  groundedness/risk/permission check pills), and the pending-approval
  gate with Approve/Reject driving the real `interrupt()`/resume flow.

### Deployed
- Backend on Render (`resolveflow-1h99.onrender.com`) — free tier, so
  it spins down after inactivity (~50s cold start on the first request
  after idle).
- Frontend on Vercel (`resolveflow-web-officialbidishas-projects.vercel.app`).
- Verified end-to-end on the live production URLs, both outcomes: a real
  issue reaching `escalate_to_human`, and a real issue reaching
  `pending_approval` → reject, confirming the SQLite-backed checkpointer
  actually persists state across genuinely separate HTTP requests in
  production, not just in a local test.

### Known issue
- Deploying via `deploy_to_vercel` hit a real platform quirk: a second
  deployment to an already-existing project consistently 403'd
  ("permission" error) regardless of payload size, while a first deploy
  to a brand-new project name always succeeded. Worked around by
  deploying the complete, final build in a single shot to a fresh
  project rather than iterating. New Vercel projects also default to
  "Vercel Authentication" (SSO-gated deployments) — disabled manually
  via Project Settings → Deployment Protection so the demo is actually
  publicly viewable.

## [Unreleased]

### Changed
- **Corpus grown from 40 single-repo issues (~130 chunks) to ~600 issues
  across 4 real repos (~2,750 chunks)**: `facebook/react`,
  `langchain-ai/langchain`, `microsoft/terminal`, `vercel/next.js`. A
  40-issue single-repo corpus meant a random real issue almost never had
  a genuine topical match to retrieve against — every "real diagnosis"
  demo required hand-constructed evidence.
- `ingest.py`'s `source` id is now repo-prefixed
  (`f"{repo}-issue-{number}"` instead of `f"issue-{number}"`) — plain
  issue numbers collide across repos (`facebook/react#10` and
  `langchain-ai/langchain#10` would otherwise both become `"issue-10"`,
  corrupting the citation id scheme).
- `ingest.py` now clears the index before re-ingesting
  (`index.delete(delete_all=True)`) — re-running it is idempotent again,
  since the id-scheme change would otherwise leave old-scheme vectors as
  stale duplicates rather than getting overwritten.

### Verified
- On the bigger corpus, a real, empty-body issue
  (`facebook/react#36932`, "experimental_taintUniqueValue throws
  RangeError for large binary values") retrieved two real near-duplicate
  reports with actual technical detail and produced a **correct**,
  specific root cause ("`String.fromCharCode.apply` exceeds the JS
  engine's max-argument limit on large buffers") — versus a confidently
  *wrong* diagnosis ("React DevTools extension compatibility issue") on
  the same query against the old 40-issue corpus, which retrieved three
  unrelated chunks. `independent_review` correctly escalated it anyway
  (severity: high always escalates by design) — grounded and correct
  doesn't override the risk gate.

### Known limitation
- `groundedness_ok` only checks that a citation id was among the
  *retrieved* snippets — never that the cited text actually *supports*
  the claim. The old-corpus `taintUniqueValue` run above is the concrete
  case: citations were technically "grounded" (retrieved ids) while the
  diagnosis was factually wrong. A real fix would need a semantic
  check — e.g. a second pass asking whether each citation's text actually
  entails the claim it's attached to — not just id membership.

### Fixed
- **`IssueEvidence.is_information_sparse` couldn't fire on real GitHub
  issues.** Old rule: body under 40 raw characters *and* zero comments.
  Empirically checked against ~380 real closed/open issues across
  `facebook/react`, `microsoft/terminal`, `denoland/deno`, `vercel/next.js`,
  `sveltejs/svelte`, `vitejs/vite` — zero matched. Issue templates pad
  every report past 40 characters with headers/checkboxes regardless of
  actual reporter effort (5th-percentile raw body length across the
  sample: 389 chars), and active repos almost always get at least one
  bot/triage comment, so `not self.comments` almost never holds either.
  Net effect: this classification branch was practically unreachable from
  real traffic.

  New rule: strip markdown template scaffolding (headers, checkbox lines,
  HTML comments) before measuring, drop the zero-comments requirement
  entirely (a triage comment says nothing about how much the *reporter*
  wrote), keep the 40-char threshold applied to what's left. Also handles
  a real edge case found during testing: some issue bodies contain
  literal `\n` text instead of real line breaks, which would otherwise
  make the whole body read as one line and get wrongly discarded as a
  single "header". Re-verified against the same ~380-issue sample: fires
  on 2.1% (2/96 in a spot-check), both genuinely low-signal real issues,
  zero false positives against a detailed real bug report used as a
  negative control.

### Known issue
- LangGraph logs a deprecation warning when deserializing the Pydantic
  schema types (`IssueEvidence`, `Diagnosis`, `ReviewResult`) from the
  checkpoint — msgpack doesn't recognize them as registered types yet.
  Harmless today; will need `allowed_msgpack_modules` before a future
  LangGraph version enforces `LANGGRAPH_STRICT_MSGPACK`.

### Next up
- `eval/` — scenario coverage across deterministic, sparse, and
  adversarial issues. Still empty.
- Tests for the node functions and the compiled graph.

## [0.6.0] — Approval-gated execution

### Added
- `graph/nodes/await_approval.py`: builds the exact GitHub comment/label
  execute will post — a fixed template for `deterministic` (failing CI),
  or built from `diagnosis.root_cause`/`recommended_next_steps` for an
  approved `ai_investigation` diagnosis — then pauses via LangGraph's
  `interrupt()`. Every path to `execute` goes through this one gate; none
  skip it.
- `execute`: implemented for real. Posts `state["proposed_action"]`
  **verbatim** via `tools/github_client.py` (`post_comment` + optional
  `add_label`) — never recomputes the action after a human approved it.
  Still refuses to run at all without `state["approved"] is True`,
  checked in the node itself as a second guarantee independent of graph
  routing.
- `graph/build.py`: compiled with a `MemorySaver` checkpointer (required
  for `interrupt()`/resume). `deterministic` and the `independent_review`
  `approve` outcome both route to `await_approval`, which then routes to
  `execute` only if `state["approved"]` — otherwise straight to `END`.
- `ui.py`: real approve/reject flow. Each analysis run gets its own
  `thread_id`; hitting `await_approval` shows the exact proposed
  comment/label with Approve/Reject buttons, which resume the paused
  thread via `Command(resume=True/False)`.

### Verified
- End-to-end through the real compiled graph (mocked GitHub reads/writes,
  real OpenAI + Pinecone calls): `ai_investigation` → approve → interrupt
  pauses with the exact proposed action → resume → `execute` posts that
  exact same content, confirmed by assertion, not inspection.
- `escalate_to_human` outcome routes to `END` with no crash, no proposed
  action generated.
- `execute` still raises `PermissionError` when called without
  `approved=True`, called directly.
- `deterministic` branch's `await_approval`/`execute` logic verified
  directly with synthetic state, not through a live run — `check_runs` is
  hardcoded `[]` in `fetch_evidence.py` (a pre-existing, deliberate scope
  cut noted in that file's own docstring, not something this change
  touches), so `classify` can't actually reach `deterministic` from a
  real GitHub fetch yet.

## [0.5.0] — Retrieval on real Pinecone data

### Changed
- **Retrieval corpus migrated from a local synthetic index to a real one.**
  `ingest.py` pulls closed issues from a live GitHub repo (`facebook/react`),
  chunks them, embeds them with `text-embedding-3-small`, and writes them
  into a Pinecone index (`resolveflow-issues`) — replacing the small
  hand-written `docs/runbook.md` / `docs/known_issues.md` corpus.
- `ingest.py` now creates the Pinecone index itself if it doesn't exist
  (`pc.has_index` / `pc.create_index`, `ServerlessSpec`), instead of
  assuming it was created manually via the console first, and resolves the
  index host dynamically — `PINECONE_INDEX_HOST` is no longer needed in
  `.env`.
- `tools/retrieval.py` rewritten to query that Pinecone index directly
  (`PineconeVectorStore.similarity_search`), replacing the old TF-IDF/FAISS
  index over `docs/*.md`. Same `retrieve_evidence(query, k)` contract as
  before, so `generate_diagnosis`/`independent_review` needed no changes.
  Verified end-to-end: real query → Pinecone → structured `Diagnosis` with
  a citation actually present in `retrieved_ids`.

## [0.4.0] — Diagnosis + independent review

### Added
- `generate_diagnosis`: real OpenAI (`gpt-4o-mini`) call with structured
  output (`Diagnosis` schema), grounded via RAG over `docs/*.md`
  (TF-IDF vectors + FAISS — deliberately not a real embedding model; see
  `tools/retrieval.py` docstring for why).
- `independent_review`: a **separate** OpenAI call that critiques the
  diagnosis, but the actual approve / escalate-to-human / reject gate is
  computed in code (citation-vs-retrieved-id check, severity allowlist) —
  never trusted from the LLM's self-report.
- `ai_investigation` branch wired end-to-end in `graph/build.py`.
- Verified live against real GitHub issues through both the compiled
  graph and the Streamlit UI.

### Still missing
- `interrupt()` / human-approval gate before `execute` — the "approve"
  branch currently routes straight to `END`, not to `execute`.

## [0.3.0] — Streamlit UI

### Added
- `ui.py`: a Streamlit front end that drives `compiled_graph` directly —
  paste an issue URL, watch it move through fetch → normalize → classify.

## [0.2.0] — Real evidence pipeline

### Added
- `fetch_evidence`: real GitHub REST API calls via `tools/github_client.py`.
- `normalize_evidence`: raw GitHub JSON → validated `IssueEvidence`.
- Switched the LLM provider from Anthropic to OpenAI (`langchain-openai`).
- `graph/build.py`: first working `StateGraph` — `fetch_evidence →
  normalize_evidence → classify`, with conditional routing on
  classification.

## [0.1.0] — Project skeleton

### Added
- `schemas/` — `IssueEvidence`, `Diagnosis`, `ReviewResult` (Pydantic).
- `tools/github_client.py` — GitHub REST client.
- `graph/state.py` — the shared `GraphState` TypedDict.
- `classify` node — rule-based routing into `deterministic` /
  `ai_investigation` / `human_review` (see the node's own docstring for
  why rule-based, not learned).
- `execute` node stubbed: raises unless `state["approved"] is True` —
  the permission check lives in the node itself, not just at an API
  boundary, so no future refactor can route around it. Logic itself is
  `NotImplementedError` (not yet built).

## [0.0.1] — Planning

### Added
- `PLAN.md` — original 5-day/2-person build plan (later compressed to a
  solo, thinner slice — see README "Status").
