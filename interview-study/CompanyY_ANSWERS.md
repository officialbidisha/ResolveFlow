# Company Y, Oct 9: your answers, built from drill2

Source: `drill2.md` (office Claude, Oct 7) checked against `Bidisha_Das_Resume_Company Y.tex`.
Earlier numbers marked "drill1" come from `a4sdrill.md` (Oct 4–5).
All answers are written at the pattern level: generic service names, no internal identifiers. That is how you say them out loud.

---

## 0. Fix these five before Thursday

| # | Risk | Why it matters | What to do |
|---|---|---|---|
| 1 | **Every resume number came back NOT FOUND.** That covers 60→5 days, 20→3 min, 150+ users/8 teams, ~40% throughput, and 8 capabilities/10+ teams. | Karan will ask "how did you measure that?" A number with no method fails, and fails worse than having no number. | You are now the only source. Write one line per number (metric, source system, window), see §1. If you can't, say the mechanism without the number. |
| 2 | **"Privileged actions run under the requesting user's own permissions"** is unproven. The user ID header on the action call was never read. | This is his Azure AD territory. Drill2's follow-up #2: if the header carries an integration user, the permission check isn't the admin's. | Run prompt §7 Q1. Learn the answer in §3.2, including the honest "confused deputy" part. |
| 3 | **Office Claude didn't find your Slack agent.** Resume says Python + TypeScript, Slack Bolt. What it found is the Setup agent exposed as an **MCP server** behind a proxy, owned by a "Setup in Slack" team. There was no Bolt app, no 3-second ack, no Slack→Company W user mapping. | If your Bolt app lives in another repo, fine. If not, the bullet describes something else. | Run prompt §7 Q2 with the repo name. Know which one is yours. |
| 4 | **The infra bullet (AWS/Docker/K8s/CI-CD/on-call) is mostly NOT FOUND.** That covers pipeline file, Helm, HPA, Terraform, IRSA, SLOs and paging. | This is exactly what sank Company X. | Use the verified container/gunicorn/monitoring details in §3.7–3.9, and the "reason from first principles" answers for the parts you don't own. |
| 5 | **Five "agentic SDLC" workflows for access management.** Drill2 never named five. "SDLC" is also a stretch for access management. | Karan runs Agentic SDLC. He'll ask "how is access management SDLC?" | Name your five from memory (e.g. public groups, group membership, permission set assignment…). Use the §3.14 answer for the SDLC question. |

**On claiming "I built the whole loop":** say "I" for what you designed (the graph, the skills, the approval flow, the actions, the evals). Say "we" or "the platform" for the planner service, gateways, clusters and Data Cloud. A Fellow-level interviewer respects precise ownership, and an overclaim gets found with one follow-up question.

---

## 1. Resume, line by line

| Resume line | Verdict | What's verified that you can use | Exposure |
|---|---|---|---|
| Five agentic workflows, ~60 → ~5 days (~92%) | **AT RISK** (number not found; five not named) | Skills/NLDs per task, todo-based execution, approval, Core actions (§3.1) | Number method; naming all five |
| Retrieval-to-action architecture; versioned Skills; metadata grounding; permission-aware tools; MCP, REST, Metadata/Tooling API, Java/Spring/TS | **STRONG** on the architecture | 4-node graph, one skill doc per todo, tool retrieval thresholds, access checks in code, MCP server | Fine, provided you know §3.1–3.6 cold |
| Onboarded 8 capabilities to Headless 360, 10+ teams | **AT RISK** (not found) | One MCP server, one coarse tool wrapping the whole agent, proxy, session key, latency sample (§3.11) | "Name the eight" |
| Slack agent: Python/TS, Bolt, HITL, user's own permissions, 150+ users/8 teams, 20 → <3 min | **AT RISK** | Only the MCP path (60s × 2 retries, 3-min ceiling, p50 ~35s / p95 ~98s local sample) | Bolt app location, user mapping, 3-s ack, the numbers |
| AI eval framework: retrieval, tool selection, permissions, structured output, failure paths, replayed prod failures; authorization kept deterministic in code | **DEFENSIBLE** | Harness CLI, PASS/FAIL/SOFT_FAIL, kappa audits, utterance suites (drill1: 524 utterances, ~82% pass, ~88% stable, κ ≈ 0.65), access checks in code | "Do evals block a release?" No (§3.10). "Replayed prod failures": no written path found |
| AWS/Docker/K8s/CI-CD, Splunk, event-driven, ~40% throughput, on-call | **HIGHEST RISK** | Container image, gunicorn config, graceful-drain chain, monitoring-as-code, FIT-test deploy gate | Pipeline, Helm, HPA, Terraform, paging. "40%": only "~50% faster on specific utterances" exists, and that is latency, not throughput |
| Mentor 5+ engineers | Not checked; low risk | — | Have one concrete mentoring example |
| ResolveFlow 50-scenario / 86% / 24% | **AT RISK** (old audit: public repo has 11 safety tasks + 6 capability checks, OpenAI only) | — | Still unresolved from Oct 2. Decide the wording |

**Number defense template.** Fill one line per number before Thursday:
> "[Number] is [metric], measured from [start event] to [end event] in [system], over [window / N requests], [median or mean]. The honest caveat is [what else changed]."

If you can't fill a line, use the mechanism only, e.g. *"it took access requests from a multi-week manual queue to self-service in days. The main lever was removing the manual triage-and-implement handoff."*

Don't swap in the "50% faster" figure for "40% throughput". They measure different things, and he will notice.

---

## 2. The 90-second walkthrough (practice out loud)

> "An admin types *'Create a public group Sales Ops and add users X and Y'* in Setup.
>
> **Route.** The UI picks the agent version through org- and user-level access checks plus a feature gate. That's also how we roll back.
>
> **Session.** The request goes through the Agent API, which keeps session state in Redis, and a worker, to the planner service. The planner service hands the graph to a Python reasoning service that executes it.
>
> **Plan.** The graph has four nodes: Knowledge, Assistant, Executor and Discovery. The Knowledge step retrieves skill docs. Here the sentence becomes **two tasks**: create the group, and manage its membership. Each task is backed by exactly one versioned skill doc. Planning is incremental, not upfront, because V1's upfront plan took 8–12 seconds and anything past ~3 seconds of silence reads as a dead agent.
>
> **Gate.** The plan is shown and must be explicitly approved. Only single-task plans auto-approve, and this one has two tasks. The Executor can only call tools enabled for the current state, and only while the task status is *running*.
>
> **Act.** The call into Core uses mTLS for service identity. The Core action runs its own access check in code, against the user context and the permissions the skill declares, such as View Setup. Membership is draft-then-commit: a dry run, then the commit.
>
> **Verify and learn.** Each task moves Start → actions → Update status, so a failure is attributable to one step. Eval suites in a harness replay utterances against test orgs. Graph changes are promoted weekly, and a per-org gate can fall back to the stable graph."

---

## 3. Likely questions, with answers

### 3.1 "What happens when an admin types X?"
Use §2. Then stop and let him pick where to go deeper. Don't monologue past 90 seconds.

### 3.2 "How do you guarantee the agent can't do something the user can't?" (his #1 topic)
> "Two identities on every call into Core. **Workload identity** is the mTLS certificate: it proves the call came from our planner service. In production there is no fallback. The legacy token path only runs in local and dev, and if the cert client is missing the service raises an error instead of silently degrading to weaker auth. **User identity** travels separately as request context. Core rebuilds the user context from it, so the action's access check, plus the permissions the skill declares, is evaluated for the admin who asked. The model never makes the authorization decision. It can only choose among tools enabled in the current state, and the action re-checks access in code."

**If he pushes ("what stops a compromised service from asserting any user?"):**
> "That's the confused-deputy risk of this pattern. Core trusts a mesh-authenticated service to assert the user. The mitigations are a tight allowlist of which services may assert user context, and binding the user to a signed, short-lived token instead of a header. In Azure AD terms that's an on-behalf-of token exchange, where the downstream token carries both the user and the actor. That's where I'd take it."

⚠ **Verify first (prompt §7 Q1):** which user ID Core actually sees. If it's an integration user, change the resume line, and do not say the sentence above as fact.

### 3.3 "How does human approval work?"
> "Three independent layers. One: **plan approval**. The plan is shown, the user approves, and execution can't start before that. Only single-task plans auto-approve. Two: **tool-level confirmation**, a per-action flag that pauses before a specific write. Three: **skill-level draft-then-commit** for membership. The first call is a dry run, the second commits."

**Senior follow-up (also a complex-problem story, §4a):**
> "One thing I'd fix: the tool-confirmation flag is defined in two places, the graph and the action definition, and they disagree. Which one wins depends on which compile path builds the session. A safety flag must have one source of truth, and if two sources exist it should fail closed: if any of them says confirm, confirm."

### 3.4 "Why incremental planning instead of plan-then-execute?"
> "V1 planned everything upfront and it took 8–12 seconds. Past about 3 seconds of silence users think the agent is dead. Incremental planning gets the first useful output fast. Each task runs Start → actions → Update status, so failures stay attributable to one task, and org-data lookup is its own Discovery node rather than folded into the planner."

### 3.5 "What if step 2 fails after step 1 committed?"
> "Creating the group and adding members are two separate actions with two separate commits. There's no transaction across them. If membership fails, an empty group exists. Today nothing rolls it back. I'd harden it three ways. First, make create idempotent by name, looking up before creating, so a retry neither fails on a duplicate name nor makes a second group. Second, treat group creation as the **pivot step**: after it, only go forward, and retry the membership step, which is naturally idempotent because adding an existing member is a no-op. Third, only compensate by deleting the empty group if the user abandons the request. Deleting something a human may already have seen is riskier than leaving it."

### 3.6 "How do you roll back a bad change?"
> "Graph rollback is per-org through a feature gate that swaps the agent from the current version to the stable one. It's a client-side switch with no deploy, so it's fast. Its limit is that actions, schemas and skill docs ship on the Core release train, and the gate doesn't revert them. So graph changes have to stay compatible with both the current and previous action versions: expand-then-contract, like a DB migration. What I'd change is to version skills together with the graph, so rollback is one pointer move."

### 3.7 "How is it deployed?" (the Company X question)
> "Containers on our internal Kubernetes platform, which runs on AWS. The platform team owns the clusters, base images and pipeline framework. Service teams own their image, deployment values and alerts. Take the reasoning service. Base image is RHEL 9 with a minimal Python 3.12. Dependencies are installed with `uv` from a matching build image, so the runtime image carries no build tooling, and it runs as a non-root user. It's served by gunicorn with Uvicorn workers, six by default and configurable through env. Functional integration tests gate deploys, rollout is staggered across instances, and alerts and dashboards are defined as code in Terraform per service."

**Honest boundary, said once, then pivot:**
> "I don't own the cluster-level settings. Happy to reason through how I'd size and scale this workload, though."

Then go to §3.8.

### 3.8 "How would you scale it? Requests/limits, HPA?" (reason from first principles)
> "CPU is the wrong scaling signal for an LLM-bound service. A worker waiting 30 seconds on a model call uses almost no CPU. I'd scale on **in-flight turns per pod** against a target below worker capacity. Min replicas would be sized to survive losing a zone. The **scale-down stabilization window** would be longer than the longest turn, so the autoscaler doesn't kill pods mid-conversation. Memory requests would be sized per worker, times the worker count. The PodDisruptionBudget would keep enough pods up during node drains."

### 3.9 Three concrete runtime details (very good with a Fellow)
- **Graceful drain:** "Timeouts nest. The turn drain deadline is less than gunicorn's graceful timeout, which is less than its hard timeout, which is less than Kubernetes' termination grace period (in our config roughly 620 < 640 < 700 < ~900 s). If any outer timeout is shorter than an inner one, SIGKILL lands mid-turn and the user's stream breaks." *(Verified for the voice/WebSocket path. For text SSE, say "the same principle".)*
- **`preload_app = False`:** "We don't load the app in the gunicorn master. Forking after creating an async HTTP client copies its pool and event-loop state into every worker, and copy-on-write breaks it. Each worker builds its own client after the fork."
- **`max_requests 5000, jitter 100`:** "Workers recycle after ~5000 requests to bound slow memory growth. The jitter stops all workers recycling at the same moment."

### 3.10 "How do you know it works? Evals?"
> "We run a harness that drives utterance suites against test orgs and grades them PASS, FAIL or SOFT_FAIL. Deterministic checks cover which tool was called, the arguments, and whether the permission check fired. An LLM judge covers response quality. We audit the judge against human labels with Cohen's kappa. The last audit was about 0.65, the low end of 'substantial' agreement, so the judge alone shouldn't block a release. The latest multi-run report was about 82% pass and 88% stable across runs. Today it's **advisory, not a hard gate**. I'd gate the weekly graph promotion on no regressions in the deterministic checks against the stable set, and keep judge-scored dimensions as warnings until agreement is above ~0.7."

### 3.11 "Tell me about the MCP integration."
> "The Setup agent is exposed as an MCP server with one coarse tool, 'chat with setup agent'. It wraps the whole agent rather than exposing each action. A proxy speaks MCP outward and the Agent API inward, and sessions are keyed on org, MCP session and bot. That keeps tenant scoping in the key, and every inner action still runs its own access check. The coarse tool is deliberate: external agents get a conversation, not raw write primitives, so approval and access checks can't be bypassed. The trade-off is latency. A local sample showed turns at p50 ~35 s and p95 ~98 s, under a 3-minute ceiling."

⚠ Drill2 lists the proxy at 60 s × 2 retries. If 60 s is per attempt, that's below the p95, so slow-but-successful turns get retried, and retrying a turn that already wrote is a duplicate side effect. **Confirm before using this.** If it holds, it's an excellent "timeout chain" point (§4c).

### 3.12 "How do you debug it? Observability?" (his #2 topic)
> "Each layer writes structured records to Splunk. LLM-timing records carry a trace ID, template, generation ID, durations and token counts. Action records carry action, status, latency and target. Alerts and dashboards are defined in Terraform per service. The gap I'd call out: **a request with an approval isn't one trace.** The plan turn and the execution turn are separate HTTP requests through a stream and a worker, so a query keyed on the first trace ID misses the execution. The fix is a stable correlation key, session ID plus plan ID, stamped on every hop and every turn alongside org ID and user ID. Then 'where is request X?' is one query."

That is his `traceId` / `tenantId` / `userId` vocabulary. Use those words.

**If asked about SLOs:**
> "We don't have formal ones for this agent yet. I'd propose: turn success rate; time-to-first-token p95 under ~3 s, since that's the silence threshold; end-to-end turn p95; and approval-to-execution success."

Make clear these are proposals, not current targets.

### 3.13 "How does tool selection work?"
> "Two stages. System primitives come from a semantic search: about 50 candidates, keep those with similarity ≥ 0.7, then the top 2. If no skill matches, a global vector fallback gives up to 5 candidate tools per goal. The threshold is a precision gate that keeps weak matches out of the model's context."

(Not "top-5 at 0.7". Drill2 corrected that.)

### 3.14 "How is access management 'agentic SDLC'?"
> "The workflows automate access management, which is configuration rather than code. The SDLC part is how the agent itself is built and shipped. Skills are versioned artifacts, graph changes go through a weekly promotion with a rollback gate, eval suites act as the regression tests, and writes are approval-gated. That's the same loop a Company Y agent needs: plan, gate, act, verify, roll back."

Bridge to his New Relic × Copilot work: observability detects → issue filed → agent drafts → human reviews → post-merge validation.

### 3.15 "Tell me about an incident."
Verified incident (only tell it as *yours* if you were involved):
> "A data-query action started returning 500s, and users got a generic 'unexpected error'. The cause was in a dependency: the egress mesh call to an API-protection service failed creating request context. Three retries hit the same failure, then a 500. It self-resolved within hours. Lessons: retries don't help when the dependency itself is down, so classify the error and break the circuit. The user should see 'a dependency is unavailable, nothing was changed', not a generic apology. And alert on dependency error rate, not just our own 500s."

### 3.16 "What would you change first?"
Pick three:
1. One correlation ID across the approval pause.
2. Fail-closed single source of truth for confirmation flags.
3. Idempotent create plus a forward-only pivot for multi-step plans.

Backups: an eval gate on weekly promotion; config applied by the pipeline (one service's platform config is still applied by hand, outside CI, which is a drift risk).

---

## 4. Complex-problem stories (from verified material)

Drill2 didn't include Session 10, so these come from what office Claude found in the system, **not** from your commit history. **Run the Session 10 prompt** to confirm which ones you actually worked on, and only tell those as "I solved".

| Story | Category | Hook line |
|---|---|---|
| **a. Safety flag in two places** | Identity/safety | "The confirmation flag lived in the graph and in the action, they disagreed, and the winner depended on the compile path. Fix: one source of truth, fail closed." |
| **b. Partial failure in a two-step plan** | Distributed systems | "Create-group committed, membership failed, and there was no transaction across them. Fix: idempotent create, forward-only after the pivot, compensate only on abandon." (§3.5) |
| **c. Correlation across the approval pause / timeout chain** | Observability/reliability | "One user request = several HTTP turns. Traces broke at the pause, and per-hop timeouts didn't nest. Fix: stable session+plan ID on every hop, and inner < outer timeouts with deadline propagation." |
| **d. mTLS fail-fast** | Identity | "Production must never silently fall back to weaker auth. A misconfigured cert fails loudly." |

Shape for each (2 minutes): **symptom → why it was hard → how you found it → options → what you did → result → what you'd still change.**

---

## 5. When you don't know

- "I don't own that layer. The platform team does. Here's how I'd reason about it…" Then reason (§3.8).
- "I don't have that number at hand. The mechanism was…"
- "I haven't verified that in production. My understanding is X, and I'd confirm by Y."

Never invent a config value. With him, one caught bluff costs more than five honest boundaries.

---

## 6. Corrections vs earlier prep docs

- Tool retrieval: **0.7 → top 2** on system primitives. **5** is the fallback limit. It is not "top-5 at 0.7".
- The stable gate is open for one test org only in source, and it reverts **only the graph**.
- Production service-to-Core auth is **mTLS**. The token path is local/dev only.
- "200 req/s per tenant" and "OTel at 1%" were not re-verified in drill2. Don't quote them.

---

## 7. One more office-Claude prompt (closes the three biggest gaps)

Paste after the usual preamble:

```
1. For a production Setup agent action call into Core (e.g. CreateGroup), read the
   request builder in the reasoner's core action executor and Core's handling of it:
   which header/field carries the user id, who sets it, and is it the admin who typed
   the request or an integration/service user? Show the code path that sets UserContext
   for currentUserHasAccess.
2. Find the Slack access-management agent built with Slack Bolt (Python and/or
   TypeScript), not the Setup MCP server. Search for repos/commits by me containing
   "@slack/bolt" or "slack_bolt". If found: where it runs, how it acks within 3 seconds,
   how the Slack user maps to a Company W user, and how approvals work.
3. For each of these, find any source (dashboard, launch doc, retro, perf review,
   Slack): ~60 days -> ~5 days for access requests; ~20 min -> <3 min turnaround;
   150+ users across 8 teams; ~40% throughput; eight capabilities onboarded to
   Headless 360 across 10+ teams. Say NOT FOUND if absent.
4. Am I on an on-call rotation for any service in this loop? Which paging tool and
   schedule? Any pages I acknowledged in the last 12 months?
5. Is the MCP proxy's 60s timeout per attempt, and does RETRY_COUNT=2 retry a turn
   that may already have executed a write?
```
