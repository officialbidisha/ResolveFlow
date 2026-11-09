# Concurrency model

What runs where, and why each primitive was chosen. Code: `graph/nodes/fetch_evidence.py`,
`graph/request_context.py`, `app/limits.py`, `app/main.py`. Tests: `tests/test_concurrency.py`.

## The workload

Everything slow in ResolveFlow is **network-bound**: GitHub REST, OpenAI, Pinecone,
Postgres. A thread waiting on a socket releases the GIL, so the GIL is not the
bottleneck. There is no CPU-heavy pure-Python hot path in the request flow, so
`multiprocessing` is not used.

## GIL: what it does and does not decide here

- It does **not** limit throughput here: threads blocked in `requests` overlap fine.
- It does **not** make shared state safe. Nothing in the request path mutates
  shared in-process state (per-user state lives in Postgres; `_state` in `main.py`
  is written once in `lifespan`). If that ever changes, protect it with a lock or
  move it to Postgres. `counter += 1` is not atomic under the GIL.
- Where it would matter: CPU-bound pure-Python work, e.g. chunking a very large
  corpus in `ingest.py`. That is a one-shot script, so it is left alone.

## asyncio: `fetch_evidence`

Dependency graph of the five GitHub reads:

```
get_issue ─────────────┐
get_comments ──────────┤
get_codeowners ────────┼─> raw_evidence
get_linked_pull_request -> get_check_runs ─┘   (checks need the PR head SHA)
```

`afetch_evidence` runs the first three and the PR->checks chain together with
`asyncio.gather` over `asyncio.to_thread`. Sequential cost is the sum of five
calls; concurrent cost is roughly the longest chain (two calls).

Decisions:
- **`to_thread` over an async HTTP client.** `tools/github_client.py` is a shared,
  deliberately thin `requests` client (also used by `ingest.py` and the sync path).
  Rewriting it for `httpx` would change a safety-relevant module for no gain on
  this workload.
- **`gather` over `TaskGroup`.** A thread already inside a blocking call cannot be
  cancelled, so TaskGroup's sibling cancellation would not stop it, and it wraps
  errors in `ExceptionGroup`, which would degrade the 502 detail `main.py` returns.
  The calls are read-only, so stragglers finishing is harmless.
- **Both variants registered** via `RunnableLambda(fetch_evidence, afunc=afetch_evidence)`.
  `ainvoke` (the API) takes the concurrent path; `invoke` (REPL, scripts) keeps
  the sequential one.
- Other nodes stay sync. LangGraph runs sync nodes in a thread pool under
  `ainvoke`, and each does a single LLM/retrieval call with nothing to overlap.
  `eval/harness.py` calls `independent_review` synchronously, so making it async
  would break the safety-gate suite for no benefit.

## ContextVar: request identity

`trace_id` and `user_id` live in ContextVars, not globals, so concurrent requests
cannot see each other's values. They are copied into `to_thread` workers and into
LangGraph's thread-pool nodes (tested), but **not** into a bare `threading.Thread`
(also tested, as a documented caveat). They are used for log correlation only,
never for authorization: that comes from the session row in `app/db.py`.

The inbound `X-Request-ID` is accepted but length-capped and rejected if it has
non-printable characters (newlines), so it cannot forge log lines.

## Semaphore: `/api/analyze`

`AnalysisGate` caps concurrent analyze runs (`MAX_CONCURRENT_ANALYSES`, default 4).
- Waits at most `ANALYZE_QUEUE_WAIT_SECONDS` (default 10), then 503 + `Retry-After`.
- The slot is released in a `finally`, so exceptions and client-disconnect
  cancellation cannot leak slots (tested).
- Taken **before** the daily-quota increment, so a shed request does not cost the
  user one of their daily analyses.
- Created in `lifespan`, inside the running loop, not at import time.
- **Per process.** `render.yaml` allows `maxInstances: 3`, so the real ceiling is
  limit x instances. A global limit needs shared state (Postgres/Redis).
- `/api/resume` is deliberately not gated: a human already approved, the work is
  light, and shedding it would strand an approved action.

## Token-in-checkpoint issue (resolved)

`github_token` used to be part of `GraphState` and was passed as input to
`ainvoke`, so LangGraph's Postgres checkpointer persisted the user's GitHub OAuth
token in the checkpoint tables. It is now bound per request in
`graph/credentials.py` (a ContextVar, which propagates into the executor threads
like the trace id above) and read by `execute()` at write time. It is not passed
through `config["configurable"]` either, because LangGraph copies configurable
values into checkpoint metadata. `tests/test_approval_path.py` and
`eval/harness.py` scan the checkpointer's stored bytes for the token.

Still open: `sessions.github_token` is plaintext at rest, and checkpoint rows
written before this change still contain tokens until those threads are deleted.
