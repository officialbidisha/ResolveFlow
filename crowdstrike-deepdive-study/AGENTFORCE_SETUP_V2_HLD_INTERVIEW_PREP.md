# Agentforce for Setup v2 HLD — Interview Prep for Karan Bhatia (GitLab, 2026-10-09)

Source: `High-Level_Design_Agentforce_for_Setup_v2.pdf` (29 pp, "Last Updated: Jan 16, 2026", **Status: Socialization**).
Companion to: `GITLAB_INTERVIEW_QUESTION_BANK`, `OFFICE_CLAUDE_QUESTIONS`, `GITLAB_KARAN_BHATIA_DEEP_DIVE`.
Written 2026-10-04. Everything marked **[HLD]** is stated in the PDF. Everything marked **[GAP]** is *not* in the PDF.

---

## 0. Read this first — three honesty flags

**Flag 1 — whose work is this?** The HLD lists six authors. Your resume describes access-management agentic
workflows, the Slack agent, Headless 360/MCP onboarding and an eval framework. It does **not** claim Agentforce for
Setup v2. Karan *will* ask "what was your part?" Before Oct 9 you must be able to say, in one sentence, which of these
is true, and it must be verified (see §6, prompt G1):

| Truth | What you say |
|---|---|
| I contributed to A4S v2 (NLDs, evals, actions, retrieval…) | "I owned X; the team owned Y." Name X specifically. |
| I'm on an adjacent team and consume/learned from it | "I studied this design closely because my own system uses the same pattern: ..." |
| I only read the doc | Say that. Then lean on *your own* systems and use this as a design you can critique. |

An interviewer who is a VP/Fellow will catch a blurred answer in two follow-ups. A clean "adjacent, here's what I know
and here's where my knowledge stops" is far stronger than an inflated one.

**Flag 2 — proposals vs shipped.** The HLD is a *design proposal*. These are explicitly **not** shipped as of the doc:
parallel action execution ("Feature Request"), streaming "thinking out loud" ("we will advocate"), AXL generative UI
("planning to leverage"), Prism-backed discovery ("will eventually swap"), a mechanism for bespoke UI on generic actions
("currently no mechanism"), and the whole v2 release itself ("plan is to release by TDX'26, April/May 2026").
Never say "we do X" for these. Say "the design proposes X."

**Flag 3 — the HLD is 9 months old.** It's October. Whether v2 shipped, what the 10–20% latency gap is now, whether the
C360 retrieval scalability risk resolved — you don't know. Don't quote the Jan numbers as current.

---

## 1. The doc in 60 seconds (say this out loud)

> v1 was a topic-and-instruction ReAct agent with ~45 hand-written Java actions in the pilot. That doesn't scale to the
> long tail of Setup tasks. v2 splits the agent into a **Supervisor (ConversationManager)** and three **Specialists**:
> a **Knowledge Node** (retrieval), a **Reasoner Node** (turns a goal into a JSON `executionPlan`) and an **Executor
> Node** (runs the plan with *no LLM*, deterministic code). Capabilities become **Natural Language Documents (NLDs)** —
> Markdown files — stored in **Data Cloud**, so adding a capability means adding a document, not Java. A small set of
> **generic CRUD actions** execute the plan; a **RAG funnel** narrows hundreds of actions to 3–5 before the LLM picks.
> A human approves every modifying plan.

Your own architectural thesis ties to it: **thinking is non-deterministic, doing is deterministic, and a hard boundary
sits between them with a human gate.** That is the same shape as ResolveFlow (reasoning vs authorization).

---

## 2. Fact sheet (so you never misquote)

| Topic | Fact **[HLD]** |
|---|---|
| v1 | Agentforce 2.0, topics + instructions + bespoke Java actions; pilot already has **45 bespoke actions** |
| v2 runtime | Agentforce 3.0, **Daisy + AgentGraph DSL**, stateful Agent Graph (moves off a "simplistic ReAct loop") |
| Storage | Knowledge base in **Data Cloud**; NLDs stored as `.md` in **Core**, ingested via **mDLOs** |
| Nodes | ConversationManager (supervisor); Knowledge, Reasoner, Executor (specialists). Control always returns to the CM |
| Triage | `TriageRequestIntent` → `INFORMATION_SEEKING` or `ACTION_SEEKING`. Complex multi-part data queries count as ACTION_SEEKING |
| Reasoner paths | **High-Velocity** (one matching Workflow NLD → translate to plan) vs **Dynamic Synthesis** (multi-NLD, guided journey, hybrid) |
| NLD types | Higher Order (which direction), Workflow (step breakdown), Best Practices (extension of API docs) |
| Plan pipeline | `GatherMoreDetails` → scaffold ingestion → `compilePlan` (Stage A parallel RAG over action catalog; Stage B one monolithic LLM call → JSON `executionPlan`) |
| Action funnel | Vector search narrows catalog to **top 3–5** candidates per step; LLM picks one |
| Executor | **No LLM**, "100% fidelity", resolves inter-step data deps (e.g. `userId` from step 1 → step 3) |
| Validation | Agent "validates the plan and calculates a confidence score"; high-confidence plans go to the user for approval. **The doc does not say how the score is computed or what happens to low-confidence plans** |
| Generic actions | Discovery; `QueryDataSource` (replaces v1 `HelpNavigationAction`); `APIGrounding`; `TenantGrounding`; `ExecuteSOQL`; `ExecuteEntityCreate/Read/Update/Delete` (REST; planner supplies API family Data/Tooling + entity name) |
| Display | List Support, Record Support actions; AXL surface (proposal) emits a UEM doc for the Agentforce Conversation Client from a **surface-specific allowlist** — "no new LWC code is generated" |
| Retrieval path | 11 steps (§4.2) incl. Org CS connected app/ECA → `TokenExchange` → **orgJWT** → **SFAP AI Gateway** → **DC1** → **UKD dataspace** |
| Ingestion | `Metadata Extraction BT Action` (CREATE/READ). Status: `New → Processing → Syncing → Data_Copied → Ingestion_Requested → Ingestion_Complete`. Provisioning is **one-time per C360 org** and triggered when an **Org Permission** is enabled; extraction **runs periodically within the Core monolith** |
| Migration | v2 co-exists with v1 behind a **permission gate**; v1 topics/instructions → NLDs; bespoke actions retired over time (e.g. `UpdateUserRecordFields → ExecuteEntityUpdate`) |
| Risks | (1) C360 centralized retrieval "still uncertain, limited scalability"; (2) AgentGraph **10–20% slower** than ReAct planner; (3) AgentGraph bugs/parity gaps; (4) file-based DSL agent delayed |
| Timeline | Release by **TDX'26 (Apr/May 2026)** |

**Careful with this stat:** "v2 aims to solve the 30–40% of use cases that represent over 90% of user needs but are too
numerous to hard-code." As written it's confusing (v1 was the "hero" cases). Don't quote it unless you can explain it.

---

## 3. Questions Karan can ask — architecture & design

For each: the **anchor** (what the HLD gives you), a **skeleton** (structure of a good answer), and a **probe** (the
follow-up he'll throw). Answer in your own words — the skeleton is a spine, not a script.

### 3.1 "Why did v1 not scale? Technical reasons, not a feature list."
- Anchor: topics/instructions steer the LLM to bespoke actions; catalog is "scoped by the topic"; 45 bespoke Java actions; each new capability = new Java.
- Skeleton: (1) action selection depends on the LLM interpreting hand-written prose → brittle; (2) capability growth is linear in engineering effort; (3) no explicit planning/clarification step; (4) long-tail tasks too numerous to hand-code.
- Probe: *"Couldn't you just have written better topics?"* → Prose instructions can't be tested/versioned like data, and they compete for the same context window.

### 3.2 "Why separate Thinking from Doing? What breaks if the executor can reason?"
- Anchor: design goal "hard boundary between Thinking (non-deterministic) and Doing (deterministic)"; Trust = "if the agent builds a plan, it must execute exactly as described."
- Skeleton: the human approved a *specific* plan; if the executor re-reasons, what ran ≠ what was approved → approval is meaningless, audit trail breaks, behaviour not reproducible, can't unit-test it.
- Probe: *"What if the plan is wrong at step 3 because step 2 returned something unexpected?"* → **[GAP]** the HLD doesn't describe failure handling. Honest answer: executor halts and surfaces to the user; re-planning goes back through the Reasoner and re-approval. Say it's your reasoning, not the doc.

### 3.3 "Walk me through the RAG funnel for action selection."
- Anchor: §1.4. NLD steps narrow concept space → parallel vector search per step → top 3–5 → single compile LLM call.
- Skeleton: three layers of narrowing (NLD scaffold, vector retrieval, LLM fine choice). The LLM never *searches*, it only *chooses among five*.
- Probe: *"What if the right action isn't in the top 5?"* → silent miss; recall@k matters more than LLM quality here. You'd measure retrieval recall on a labelled step→action set and monitor "no suitable action" rate. **[GAP]** HLD gives no fallback — say so.
- Probe: *"Why one monolithic compile call instead of per-step?"* → global coherence (merging steps, data flow between steps) at the cost of one big context and one big failure unit. Trade-off, name both.

### 3.4 "Information-seeking vs action-seeking — why classify first?"
- Anchor: Triage; complex multi-part data queries go to ACTION_SEEKING.
- Skeleton: different blast radius (read vs write), different cost (retrieval only vs full plan pipeline), different UX (answer vs approval).
- Probe: *"What if the classifier is wrong and calls a write 'information seeking'?"* → the Knowledge Node has read-only tools, so a misclassification toward info-seeking can't write. The dangerous direction (read treated as write) just costs latency. **That asymmetry is a good point to make.**

### 3.5 "What's the hardest trade-off in this design?"
- Anchor: risks section — 10–20% slower than ReAct, more thinking = more accurate.
- Say it first, unprompted. Reads as maturity.

### 3.6 "How does it stay deterministic with an LLM in the loop?" (staff-level)
- Skeleton: LLM output is confined to (a) intent label, (b) clarification questions, (c) a JSON plan. The plan is *data*, validated and shown to a human, then executed by code. The LLM never holds a write capability.
- Probe: *"Is the JSON plan schema-validated?"* → **[GAP]** not stated in the HLD. Ask office Claude (G3).

### 3.7 "Generic CRUD actions vs bespoke actions — security and trade-offs?" (the question you are best placed for)
- Anchor: ExecuteEntityCreate/Read/Update/Delete take `API family + entity name`; bespoke kept for "highly complex… mission-critical logic."
- Skeleton: generic = coverage and low maintenance, but the capability surface is *the whole API*; bespoke = narrow, testable, bounded. Mitigate generic with: permission enforcement at the platform layer (the user's own perms), entity allowlist (`APIGrounding` only for entities publicly exposed via Data/Tooling API), schema contract validation, HITL on every modification, and the NLD `permissions` metadata.
- Bridge to your resume: **your "operation allowlists + schema validation" is exactly this mitigation.** This is a lived answer if your role includes it.
- Probe: *"If the agent is fully compromised, what's the worst it can do?"* → bounded by the invoking user's permissions + allowlist + approval gate; walk the layers.

### 3.8 "Staff-level gaps I'd expect you to spot in this design" (use as your *critique*, not as claims)
These are not in the HLD. Raising them yourself shows senior judgment. Label each "the doc doesn't say; here's how I'd think about it."

1. **Plan staleness (TOCTOU).** The plan is compiled from org state, shown for approval, then executed later. Org state can change in between (user already frozen, record deleted). → Executor should re-validate preconditions at execution time, or the plan should carry version/etag preconditions.
2. **Partial failure in a multi-step plan.** Create user (ok) → assign permission set (ok) → group membership (fails). No saga/compensation described. → Is there rollback, or "report what was done"? Idempotency keys per step so a retry doesn't double-create.
3. **LLM-generated SOQL (`ExecuteSOQL`).** The doc says the snippet is "provided by the LLM" and "typically comes from an NLD." Injection/over-broad query risk; need allowlisted objects/fields, row limits, read-only enforcement.
4. **Indirect prompt injection via org metadata.** `TenantGrounding` ingests *customer org metadata* (names, descriptions, labels) into a vector index that the LLM reads. A field description can contain instructions. → treat grounded text as untrusted data, never as instructions; the Executor can't be steered because it has no LLM.
5. **NLD supply chain.** NLDs are LLM-generated then human-reviewed, then they *steer production actions*. A wrong NLD step is a production bug at scale. → versioning, eval gate before ingestion, canary by `scopes`, fast rollback.
6. **Confidence score.** Undefined in the HLD. LLM self-reported confidence is poorly calibrated; prefer verifiable signals (all entities resolved, all required inputs bound, schema-valid, NLD matched).
7. **Serial execution bottleneck** (the HLD raises this itself): steps 2–4 independent after step 1. Proposal = stages with `execution_mode: parallel`. Your angle: it's a DAG; independent reads parallelise safely, *writes* need care (ordering, partial failure).

---

## 4. Data Cloud / Data 360 — "everything possible"

This is where CrowdStrike went wrong. Know the mechanism cold, *and* know where you personally touched it (§6, E-prompts).

### 4.1 What lives where **[HLD]**
```
 Source of truth for NLDs / API grounding:   .md files in Core
 Source of truth for Help / product docs:    UKD (Unified Knowledge dataspace) in C360 DC,
                                              owned by the content teams (not you)
 Customer org metadata grounding:            customer org metadata ingested into Data Cloud,
                                              text index + vector index ("Semantic Metadata Grounding")
```
Two retrieval indexes: (a) existing **Unified Search Index** for product/help docs with a different retrieval query + pre-filters; (b) a **separate NLD/API-grounding index** built from vectorised DMOs created from mDLOs.

### 4.2 The 11-hop retrieval chain (be able to draw it) **[HLD]**
```
Customer Org (A4S agent)
  1 invocable QueryDataSource action (prompt + source)
  2 auth via Org CS (Connected App / ECA)
  3 custom TokenExchange handler -> orgJWT as OrgCS/HelpPortal user, per tenant org
  4 call Retriever + orgJWT -> SFAP AI Gateway
  5 Gateway routes into DC1 (Data Cloud) -> UKD dataspace
  6 Help Agent Retriever queries Unified Search Index -> chunks
  7-9 ingestion side: UKD is single source of truth for SF docs (C360 teams own it);
      mDLOs populated by Metadata Extraction Framework; provisioned when an Org Permission is enabled;
      extraction runs periodically in Core monolith
  10 NLD Retriever queries NLD Search Index (mDMO)
  11 results return via gateway to the planner
Optional: serve NLD source doc from Core classpath to avoid a round trip to C360
```

### 4.3 Ingestion state machine **[HLD]**
`New → Processing → Syncing → Data_Copied → Ingestion_Requested → Ingestion_Complete`, triggered by the org-level
**Metadata Extraction BT Action** (`CREATE` starts background extraction and returns an Extraction Id; `READ` polls).
Step A (one-time per C360 org) provisions the mDLOs. Say "periodic extract-and-sync, not real-time."

### 4.4 Questions he can ask (and honest status of each)

| Question | What the HLD lets you say | Needs office Claude? |
|---|---|---|
| How does ingestion work end to end? | State machine above; `.md` in Core → mDLO → DMO (vectorised) → index | Only for *your* part |
| DLO vs DMO vs mDLO — define them | DLO = raw ingested object; DMO = harmonised model object; **mDLO = metadata DLO** in this design. Vectorised DMOs feed the search index. (General Data Cloud knowledge — be ready to define in your own words) | No |
| How fresh is the data? | Periodic extraction; mechanism known, **no cadence in HLD** | **Yes (E3)** — don't quote a number |
| How is tenant isolation enforced? | Per-tenant orgJWT minted by TokenExchange; request goes through the AI Gateway | **Yes (E4)** — and see ambiguity below |
| Chunking / embedding model / top-k / reranking? | **Not in HLD** | **Yes (E5)** |
| Pre-filter vs post-filter for ACL/scopes? | HLD mentions "appropriate pre-filters" for the UKD index; NLD `scopes` metadata (`Agentforce for Setup`, `Agentforce Vibes`) | **Yes** |
| What happens when ingestion fails? | Status machine implies stuck states; **no failure/retry semantics in HLD** | **Yes (E7)** |
| Why Data Cloud and not a vector DB you run? | Reuses existing search infra, ingestion framework, governance, Help Agents' retriever and chunking/ranking logic. Counter-risk the HLD itself names: centralized C360 instance "limited scalability" | No (reasoning) |
| Latency per hop? | **Not in HLD** | **Yes** |
| How do you evaluate retrieval quality? | **Not in HLD.** Your own eval framework covers retrieval quality — connect to it | Only if your eval touches NLD retrieval |
| Cost drivers? | Not in HLD. Reason: embedding on ingest, index storage, per-query retrieval, LLM compile call per plan | Optional |

**Ambiguity you must resolve (G2):** the HLD says mDLOs are provisioned "once per C360 org" *and* "when an Org Permission is
enabled," and also describes a "centralized C360 DC instance." Is the NLD/API index **shared across all customer orgs
(global knowledge, one index)** or **per-tenant**? Likely: global content (NLDs/docs) is shared; only org-metadata
grounding is tenant-specific. But the doc is ambiguous, and Karan's specialty is multi-tenancy — **he will ask this.**
Don't guess; get the answer.

**Bridge to Karan:** orgJWT per tenant ≙ his `tenantId` correlation attribute. Say: "I'd propagate `traceId`,
`tenantId`, `userId` and extraction/plan id through every hop — including across the human-approval pause — so a bad
retrieval is traceable to a tenant and an index version." That is his own blog's vocabulary.

---

## 5. Deployment & pipeline — read this twice

**The HLD contains no AWS, CI/CD, Kubernetes, or pipeline content.** It only tells you *logical* placement:
- Agent runtime: **AI Cloud — Daisy / AgentGraph** (a platform you consume).
- Planner/actions/extraction job: **Core monolith** (Java) — NLD `.md` files live on the Core classpath; extraction "runs periodically within the core monolith."
- Knowledge store: **Data Cloud (C360 / DC1)**.
- Entry: **SFAP AI Gateway**.
- Rollout: **permission-gated co-existence** with v1; one-time per-org provisioning when the org permission is enabled.

So for "where is it deployed / what's the pipeline" you have **three honest tiers**:

1. **Platform tier (HLD-supported, say confidently):** the logical topology above and the rollout strategy (permission-gated, v1/v2 co-existence, content migrated v1→NLD, bespoke actions retired incrementally). Describe it as a *progressive-delivery-by-feature-gate* pattern.
2. **Content pipeline (HLD-supported):** "NLD CI/CD" — scenario → LLM draft (from Help + API specs + bespoke action descriptions) → Markdown + JSON metadata → **human review by feature owners** → `.md` in Core → Metadata Extraction → mDLO → vectorised DMO → search index. That's a real pipeline; describe it stage by stage.
3. **Your services' AWS/Docker/K8s/CI-CD (NOT in the HLD):** your resume claims these. This is the CrowdStrike trap. **Don't improvise.** Run `OFFICE_CLAUDE_QUESTIONS` §A–C and fill in OWN/PATTERN/THIN. Until then the safe sentence is:
   > "At the pattern level it's containerised and orchestrated for fault isolation with event-driven components. Let me get you the exact configuration rather than guess from memory."

Questions he'll ask here and what you need:

| Question | You need |
|---|---|
| Where does your service run? Why that compute? | Real compute + the *why* (office Claude A1–A5) |
| Walk me through merged-PR → prod, every gate | Real pipeline file + stages (B1–B3) |
| How do you roll back a bad deploy? Have you? | Real command + one real instance (B5–B6) |
| Do evals run in CI? Do they block release? Prompt/NLD change triggers? | Real job + recent run (B7). **For NLDs: is there an eval gate before ingestion?** (H3) |
| What's your SLO / how do you know the agent is healthy? | D4–D5 |
| How do you deploy a model/prompt/NLD change vs a code change? | The NLD-as-data path (content pipeline above) is a strong, true-to-HLD answer *if* you can say how it's validated |

---

## 6. "Tell me about a challenging problem you solved" — build 3 stories

Karan will spend most of the time here. Don't borrow the HLD's problems as your own. Use them only as **design
discussion** (§3.8). Your three stories must come from work you can prove. Candidate pool from your resume — pick the
three where you have a *real incident, a real number with its method, and a real decision you'd defend*:

| Candidate | Why it fits Karan | Danger |
|---|---|---|
| Permission-aware execution ("runs under requesting user's own permissions") | His Azure AD/IAM background; identity propagation, token lifetime, revocation between request and approval | Be exact on token minting/lifetime (A7) |
| Eval framework + replayed production failures | "Observability for agent correctness" | Know what's in CI vs manual |
| ~35% fewer misconfigured access requests | Measured impact | Know the methodology (baseline, window) |
| Throughput +40% / fault isolation | Scaling / multi-tenant | **Methodology unknown — see F1–F5; don't use until verified** |
| Slack agent (150+ users, 20 min → <3 min) | End-to-end product | Know latency breakdown |
| Hotstar player failure −70% (graceful degradation) | Real distributed-systems story, not AI | Strong, verifiable, old enough to be solid |

**Story template — fill in each blank with a specific fact. If you can't, that story isn't ready.**

```
1. Context & stakes (1 sentence, a number)
2. Symptom — how did it first show up? (alert / user report / metric, with a timestamp)
3. First hypothesis — and why you were wrong or right
4. How you narrowed it (the exact query / log / trace you used)
5. Root cause LAYER (retrieval / planning / tool-API / auth-token / cache / infra) — and the actual mechanism
6. Options you considered, what you rejected, why (trade-off)
7. The fix + how you verified it (metric before/after, with method)
8. What you'd do differently / the regression test or eval case you added
9. What YOU did vs what a teammate/platform team did
```

**Probes he'll use on any story:** "What was the alternative?" "How do you know it worked?" "What was the blast
radius if you'd been wrong?" "What did you personally do?" "How would you have caught this earlier?" — rehearse each
with each story.

---

## 7. Hostile / gotcha questions to rehearse

1. "Which part of this did *you* build?" → §0 Flag 1.
2. "You said 100% fidelity — what about a plan that was correct when approved but stale when run?" → §3.8 #1.
3. "Isn't generic CRUD just giving an LLM root?" → §3.7.
4. "The v2 agent is 10–20% slower. Why ship it?" → reliability and long-tail coverage; latency closes via streaming/parallelism/Daisy++ (those are *proposals* — label them).
5. "How do you know your NLDs are correct?" → LLM-drafted + human review is the HLD's only stated control; say you'd add evals as a release gate. **[GAP]**
6. "How do you test a non-deterministic planner?" → test at the seams: intent classification, retrieval recall@k, plan schema validity, executor determinism (pure code), end-to-end golden tasks, and replay of production failures.
7. "Two admins issue conflicting commands for the same record." → optimistic concurrency / preconditions on write; don't rely on the model to coordinate. **[GAP]** in HLD.
8. "Show me a time your estimate or design was wrong." → have one real example ready.

---

## 8. Questions to ASK him (he's ~2 months into GitLab)

- "Where's the biggest gap between the public Duo Agent Platform vision and what's shipped today?"
- "When an agent opens an MR at machine rate, where does governance live — in the platform, or per agent?" (bridge to your permission gates)
- "How do you think about per-tenant isolation for agent context/memory on a shared platform?" (his specialty)
- "What does the observability story look like for an agent run — can you trace one MR from the triggering signal through every tool call?" (his New Relic × Copilot loop)

---

## 9. Office-Claude prompts — what to run, in what order

**Yes, you need office Claude. Same preamble as `OFFICE_CLAUDE_QUESTIONS` (VERIFIED vs INFERRED, cite the source, say
"not found," separate what you authored from what the platform owns).**

Run the existing sections **A–F first** (AWS, CI/CD, K8s, Splunk + incident, Data Cloud for your systems, 40%/on-call).
They remain the highest-risk items and this HLD covers none of them. Then add these **new** prompts, which the existing
file doesn't have:

**G — Your relationship to Agentforce for Setup v2 (highest priority, ask first)**
- G1. Search commits, PRs, code reviews, design-doc comments, and Slack threads for my involvement with Agentforce for Setup v2 / A4S / AgentGraph / NLDs / `compilePlan` / Metadata Extraction. List every artifact with a link. Classify my role: authored / reviewed / consumed / none. If none, say "not found."
- G2. Is the NLD / API-grounding index **shared across all customer orgs, or per-tenant**? Which data is tenant-specific (org metadata grounding) vs global? Where is each stored and how is each isolated? Cite the source.
- G3. Is the `executionPlan` JSON schema-validated before it reaches the Executor? Where's the schema defined? What does the Executor do when a step fails — halt, retry, compensate? Is there idempotency per step?

**H — Current status (the HLD is Jan 2026)**
- H1. Did v2 ship at TDX'26? What's the current rollout state (permission gate %, orgs enabled)? Which HLD items shipped vs. remain proposals: parallel execution, streaming, AXL surface, Prism-backed discovery, bespoke-action retirement?
- H2. What is the current latency vs. the ReAct planner (HLD said AgentGraph was 10–20% slower)? Current retrieval p50/p95 per hop (AI Gateway → DC1 → retriever)? Did the C360 centralized-retrieval scalability risk get resolved?
- H3. How are NLDs validated before ingestion? Is there an eval/regression gate in CI for NLD or prompt changes? How are NLDs versioned and rolled back? How many NLDs exist and which are the most-used?
- H4. How is the **confidence score** computed? What happens to low-confidence plans?
- H5. Retrieval parameters in production: chunking, embedding model, top-k, score thresholds, hybrid/rerank, pre-filters. Were they tuned with eval data?
- H6. Ingestion cadence and freshness for org-metadata grounding and NLDs; failure/retry behaviour of the Metadata Extraction BT Action (what happens in each stuck state?).
- H7. One real production incident involving this system (retrieval, ingestion, plan compile, executor) — reconstruct timestamps, root-cause layer, fix, and the eval case added. Which parts were mine?

**After each session write down** (same as the existing file): OWN / PATTERN / THIN per topic; three specifics you'll
say out loud (a config value, a number with its method, an incident with timestamps); one honest boundary sentence;
anything that contradicts a resume line.

---

## 10. Five-day plan (Oct 4 → Oct 8; Oct 9 is the interview)

| Day | Do |
|---|---|
| Oct 4 (today) | Read §0–§2. Run **G1–G3** with office Claude. Settle your role sentence. |
| Oct 5 | Run office-Claude **A–C** (AWS, CI/CD, K8s) and **H1–H3**. Fill OWN/PATTERN/THIN. |
| Oct 6 | Run **D, E, F** (Splunk + incident, Data Cloud for your systems, 40%/on-call) and **H4–H7**. Draft stories 1–3 with the §6 template. |
| Oct 7 | Say §1 + §4.2 (draw the 11-hop chain on paper) + each story out loud, timed. Rehearse §7. |
| Oct 8 | Mock Q&A (ask me to interview you — I'll play Karan). Finalise 2–3 honest-boundary sentences. Light review only. |

Don't leave office-Claude work for Oct 8 — that's how CrowdStrike went wrong.
