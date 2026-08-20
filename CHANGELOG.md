# Changelog

All notable changes to ResolveFlow are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- **Retrieval corpus is migrating from a local synthetic index to a real one.**
  `ingest.py` now pulls closed issues from a live GitHub repo
  (`facebook/react`), chunks them, embeds them with
  `text-embedding-3-small`, and writes them into a Pinecone index
  (`resolveflow-issues`). This replaces the small hand-written
  `docs/runbook.md` / `docs/known_issues.md` corpus.

### Known issue
- `tools/retrieval.py` has **not** been updated to query Pinecone yet — it
  still builds a TF-IDF/FAISS index over `docs/*.md`, which no longer
  exists. `generate_diagnosis` will fail until `retrieve_evidence` is
  repointed at the Pinecone index. Tracked as the next task.

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
