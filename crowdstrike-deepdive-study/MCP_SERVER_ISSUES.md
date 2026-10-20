# MCP server: what to say, and the issues

Companion to `mcp_server_reference.py` (illustrative code, not the production source) and `mcp-handshake.json`.

## 0. Honesty frame (say this first)

> "Here's a small reference version of the pattern. The shipped version was simpler: one coarse tool wrapping the agent, behind a proxy. I'll tell you which parts are shipped and which are what I'd do next."

| Shipped (defend) | Design only (label it) |
|---|---|
| Agent exposed over MCP via near-core proxy | Per-tool exposure (`find_tools`) |
| Session key `(orgId, mcpSessionId, botId)` | Identity from headers only |
| 60 s proxy timeout, 2 retries | Write confirmation + idempotency key |
| Retrieval top 5 @ 0.7 → `enabled_tools` from the skill doc's `tools:` list | Per-user tool permissions |
| Local latency sample p50 ~35 s, p95 ~98 s | |

Do **not** claim: "8 entities across 10+ teams" (not found in the drill), any resume metric, or that the user-identity header was read (it was not).

## 1. 60-second architecture answer

MCP is JSON-RPC 2.0: `initialize` (negotiate version + capabilities: `tools.listChanged`, `resources.subscribe`) → `tools/list` → `tools/call`. The host (the LLM client) sees tool names and schemas only. My server turns those calls into the agent. Session state lives server-side under `(org, mcp-session, bot)` so a multi-turn conversation keeps its plan and pending approvals.

## 2. Selective tool calling

**Problem:** with N tools in the prompt, the model picks the wrong one more often, token cost grows, and risky write tools sit next to harmless reads.
**Mechanism (shipped):** embed the request, retrieve the top 5 skill docs at ≥ 0.7, union their `tools:` lists into `enabled_tools`. The plan is then validated against that set, and a step naming a tool outside it is rejected (`validate_plan` in HM_ROUND_PREP.md).
**Key line:** the allowlist is enforced in code at validation time, not only by the model's good behavior.

### Issues with it (the interview gold)

1. **Threshold calibration.** My reference test: the query `"user"` matched nothing at 0.7 while the full sentence matched. Phrasing sensitivity is real. There was no calibrated confidence gate. Fix: build a labelled set of (request → correct tools), sweep the threshold, and report recall@k.
2. **Recall vs precision asymmetry.** A missing tool = task fails (visible). An extra tool = slightly worse accuracy (silent). So bias toward recall for reads, precision for writes.
3. **Empty set behavior.** When nothing clears the threshold, do not fall back to "all tools." That defeats the point. Return a clear "can't do that" or ask a clarifying question.
4. **Multi-step requests.** "Why can't Priya access X?" needs FindUser → FindPermissionSets → FindPublicGroups → FindQueues. Retrieval on the *whole utterance* can miss the later steps; docs listing co-required tools in `tools:` is the workaround, and it is manual and drifts.
5. **Stale index.** Tools change, the embedding index doesn't. Needs re-index on deploy, and a test that every tool in the catalog is reachable by at least one doc.
6. **Retrieval is not authorization.** Narrowing the menu is a relevance feature. Who may call a write tool is a separate permission check against the user's identity.

## 3. MCP server challenges

1. **Coarse tool vs many tools.** One `ask_agent` tool is easy to onboard but opaque: no per-step approval, no per-step authz, the client LLM can't reason about steps, and latency is the whole run. Many fine tools give control but bloat the client's context. Middle path: a few task-level tools plus `find_tools`.
2. **Latency vs timeout.** p95 ~98 s against a 60 s proxy timeout means a meaningful tail times out, and then **retries re-run a long agent**. Fixes: stream progress notifications, or return a task id and poll (async task pattern), and keep the timeout above the p95 or cut the p95.
3. **Retries and side effects.** Retrying a timed-out write can apply it twice. Retry reads only, or require an idempotency key (see `confirm_action`). The server cannot know whether the first attempt landed.
4. **Identity.** Tool *arguments* are model-controlled, so a prompt-injected `org_id` is an authz bypass. Identity must come from the trusted transport (headers set by the proxy). Weak spot: in the shipped version the user-identity header was never read, so be ready to say that plainly and what the fix is.
5. **Prompt injection through tool results.** Setup data (user names, descriptions) is attacker-influenceable text that flows back to the model. Treat results as data, keep writes behind confirmation, and keep the confirmation message deterministic (not LLM-written).
6. **Session state.** In-memory `SESSIONS` dies on restart and breaks with >1 replica. Needs a shared store (Redis/DB) with a TTL, or sticky routing. Memory grows without eviction.
7. **Version/capability drift.** `listChanged` means clients may cache stale tool lists. Version the tools; never change a schema in place.
8. **Observability.** Log per call: session key, tool, enabled set, retrieval scores, latency, outcome. Without scores you can't debug "why did it not offer tool X."
9. **SDK churn (hit this today).** `mcp` 2.x renamed `FastMCP` to `MCPServer` and broke v1 code. Pin the version. Good small story about dependency pinning.

## 4. Likely questions → one-line answers

- *Why MCP and not direct function calling?* Standard protocol so many hosts reuse one server; discovery and capability negotiation come built-in. Cost: extra hop and latency.
- *stdio vs HTTP?* stdio for local single-user tools; streamable HTTP behind a proxy for multi-tenant, which is why the session key exists.
- *How do you stop the model calling a write tool unprompted?* Enabled-set allowlist + confirmation step for `writes: True` + identity-based permission check.
- *How would you evaluate selective calling?* Labelled requests, recall@k, wrong-tool rate with/without narrowing, end-to-end task success.
- *What would you change first?* Read the identity header and enforce per-user tool permissions; then async/streaming for the tail latency.

## 5. To practice (type these yourself)

1. Re-type `select_tools` and `confirm_action` from memory, then explain each line.
2. Replace the Jaccard stub with a real embedding call and plot precision/recall as the threshold moves.
3. Add the `x-org-id` header check and a test that a mismatched header is rejected.
