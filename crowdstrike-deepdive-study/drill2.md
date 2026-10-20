# Agentforce for Setup V2 — end-to-end walkthrough

Status of every claim: **VERIFIED** (path or digest) or **NOT FOUND**. Nothing below is filled in from a typical architecture.

Repos opened: this Core checkout (`core-public/core`), `chatbots/service-api`, `chatbots/service-engine`, `chatbots/service-agentic-reasoner`, `chatbots/agent-dsl`, `chatbots/terraform-monitoring` (README only), `gate-definitions`, `Agentic-Setup/setup-agent-harness`, and the q3-second-brain digest of `#setup-with-agentforce-v2`.

The q3-second-brain concept page `agentic-setup/wiki/concepts/agent-graph.md` (synthesized 2026-09-22) still describes an older ConversationManager / Reasoner / `compilePlan` design. The file the reasoner loads is the YAML below. The YAML wins.

---

## Session 1 — “Create a public group Sales Ops and add users X and Y”

No live trace of this sentence was run. The path below is what the graph and the two NLDs specify.

### What the utterance splits into

Two skills, not one action.

| Step | Skill | Tool | What it writes |
|---|---|---|---|
| Create the group | `setup-copilot-impl/java/resources/ai/knowledge/AdminCopilot/Sharing/CreatePublicGroup.md` | `AdminCopilot__CreateGroup` with `groupType="PublicGroup"` | A `Group` row. No members. |
| Add users X and Y | `.../Sharing/ManageUserAssignmentsSharing.md` | `AdminCopilot__ManageUserAssignments` | `GroupMember` rows, after a draft. |

`ManageGroupInformation.md` says a user list assigned to a public group is not that document. It sends user-only membership to `ManageUserAssignmentsSharing.md`. **VERIFIED** that file’s description, lines 1–12.

### Hop by hop

**1. Setup chat — VERIFIED selection, protocol NOT FOUND**

On a Setup page, `SetupConfig.getAgentName()` returns `AdminCopilot__AgentforceForSetupV2` when enhanced agentic setup and V2 are on and no higher-priority playground or stable gate matches. Channel target is `LightningSetupChat`.

- `ui-agentforce-conversation-client-components/modules/runtime_copilot/setupConfig/setupConfig.js` lines 17–26, 83–120, 142–146
- Graph file: `setup-copilot-impl/java/resources/ai/agent/AdminCopilot/AgentforceForSetupV2.yaml`
- `orgAccess: SetupCopilot.orgHasAgentforceSetupV2`, `userAccess: SetupCopilot.userCanAccessEnhancedAgenticSetup`, `plannerType: Atlas__ConcurrentMultiAgentOrchestration`, `initialNode: AdminCopilot__Knowledge` (YAML lines 1–30, 582–586)

The Lightning component that POSTs the utterance, the protocol, and the timeout on that hop were **NOT FOUND**.

**2. Agent API (`bot-svc-api`) — VERIFIED store**

`V6Session` is stored in Redis by `V6SessionCacheService`, backed by `ApiCache` / `Store`. Redis is described as the only external data dependency of that service.

- `chatbots/service-api` `src/main/java/com/salesforce/chatbot/api/util/V6SessionCacheService.java`
- `chatbots/service-api` `ARCHITECTURE.md`

A numeric session TTL was **not reconfirmed**. A search of chatbot `config.py` for `DEFAULT_TTL` returned no hits. Hop timeout and retry count were **NOT FOUND**.

**3. Worker (`bot-svc-worker`) — VERIFIED role**

The worker is the Agent API v1 translator between `bot-svc-api` and `bot-svc-llmagent`. It lives in `chatbots/service-engine` (`worker/`), built with Maven. Falcon config is `./falcon-resources/armada`. A reasoner comment lists the worker on port **7444**.

- `chatbots/service-engine` `README.md`
- `chatbots/service-agentic-reasoner` `atlas_v2/api/internal/grpc/README.md`

Sync vs async on the Setup path, and any timeout, were **NOT FOUND** in the files opened. An older chatbots runtime guide (cited in an earlier pass, Last Updated 2026-03-12) calls the worker an async worker and says the worker does not call the reasoner itself. That guide was not re-opened for this writeup.

**4. Planner (`bot-svc-llmagent`) — VERIFIED URL**

Harness doc: production `JAVA_PROXY_URL` is `http://bot-svc-llmagent.chatbot-runtime.svc.mesh.sfdc.net:7442`. C2C fetch is `GET /planner/c2ctoken` with a 90-second httpx timeout.

- `Agentic-Setup/setup-agent-harness` `docs/agent-runtime-stack.md`
- `chatbots/service-agentic-reasoner` `atlas_v2/clients/force_clients.py` `_get_c2c_token` (timeout=90, path `/planner/c2ctoken`)

See “Reviewer question 1” for which credential production actually sends to Core.

**5. Reasoner — VERIFIED graph**

Nodes in the YAML:

| Node | `developerName` | Line |
|---|---|---|
| Knowledge | `AdminCopilot__Knowledge` | 586 |
| Assistant | `AdminCopilot__Assistant` | 964 |
| Executor | `AdminCopilot__Executor` | 1618 |
| Discovery | `AdminCopilot__Discovery` | 11875 |

The harness doc says the reasoner streams SSE (token deltas, tool calls, progress). **VERIFIED as that doc**, not as a captured stream.

**6. Approval pause — VERIFIED in the YAML**

| Flag | Default | Becomes true | Becomes false |
|---|---|---|---|
| `current_plan_shown` | `False` (line 572) | Assistant `onInit` when a pending unapproved plan exists (1360–1362) | Every `upsert_todo_item` (1387); `state_clear` (1460) |
| `todo_approved` | `False` (line 267) | `approve_todo_list` only if `current_plan_shown` (1414–1421). Auto-approve only when `pending_todo_count == 1` and the other gates pass (1464–1469) | `state_clear` (1444) |

Handoff to `AdminCopilot__Executor` when `todo_approved` and `todo_execution_status == 'pending'` (1472–1474).

Create plus add-users is two operations, so `pending_todo_count` is not 1. The auto-approve predicate does not match. The plan waits until it has been shown and `approve_todo_list` runs. These writes are `__state_update_action__` updates inside the graph. A separate Redis key for the two flags was **NOT FOUND**.

**7. Create the group — VERIFIED, with a confirmation-flag split (question 2)**

Executor may call `AdminCopilot__CreateGroup` only while `todo_execution_status == 'running'` and the tool is in `enabled_tools` (YAML 3326–3329).

`CreateGroupInvocableAction` (`InvocableActionType.CREATE_GROUP`) delegates to `CreateGroupInvocableActionAdapter`. Public groups go to `PublicGroupRetriever.createPublicGroup`, which saves a `GroupObject` with `GroupTypeEnum.REGULAR`, Name, Description, and DoesIncludeBosses.

- `admin-access-assistant-impl/java/src/cloudy/standardactions/CreateGroupInvocableAction.java`
- `access-control-impl/java/src/core/acs/group/PublicGroupRetriever.java` lines 115–123

User access is `HasCurrentUserAccessCheck` / `currentUserHasAccess`. NLD permissions: `SetupCopilot.orgHasEnhancedAgenticSetup` and `UserPermissions.ViewSetup`.

**8. Add the users — VERIFIED NLD**

`ManageUserAssignmentsSharing.md` steps 4 and 6: call `AdminCopilot__ManageUserAssignments` with `commitChanges=false` (draft), then `commitChanges=true`. The Executor tool text says the same (YAML 3287–3294). Copy-membership SOQL in that NLD reads `GroupMember` where `Group.Type = 'Regular'`.

No transaction spanning the group insert and the member insert was found. Duplicate group name behavior on `groupObject.save()` was **NOT FOUND**. Re-check of permissions at execution time, beyond the invocable action’s own access check, was **NOT FOUND**.

---

## Reviewer question 1 — C2C or mTLS in production?

**Production Core action calls use mTLS. The C2C token hook does not run outside local, development, and dev.**

`CoreActionExecutor` picks the client (`atlas_v2/plugins/tools/core_action_executor.py`, the selector just above `_create_action_request`):

- Host on the workspace port (6101): the non-mTLS client.
- Otherwise, if an mTLS client was constructed: that client.
- Otherwise: the non-mTLS client.

`tool_engine.py` builds the mTLS client only when `is_mtls_core_client_available()` is true (around lines 253–254) and passes both clients into `CoreActionExecutor`.

`MTLSCoreClientHooks.before_request` rewrites the Core URL to port **9443** unless the host is already the workspace port. The SSL context comes from `mtls_cert_provider` and is refreshed in place (`force_clients.py` `_instantiate_mtls_core_client`).

`_LegacyC2CHttpClientHooks.before_request` returns immediately when `is_local_environment()` is false. That function is true only for environment names `local`, `development`, and `dev`. The hook’s own note says production requests should already carry their own authentication. `GET /planner/c2ctoken` (90s timeout, headers `X-Org-Id`, `forceEndpoint`, `tenantKey`, user id) is what that local hook calls.

`atlas/egress/core_connector.py` `_resolve_use_mtls` and `atlas_v2/egress/egress_context.py` say the same thing in stronger language: non-local environments require mTLS, and if the cert client is missing they raise `RuntimeError` rather than falling through to C2C. The comment in `core_connector.py` says a production misconfig must fail fast, not silently degrade to C2C.

Workspace DN headers (`SSL_CLIENT_S_DN` / `SSL_CLIENT_I_DN`) are hardcoded to service `bot-svc-llmagent` and are injected only for port 6101, and only when the request does not already have `Authorization`. The comment says those values are for Workspace because the real mTLS proxy is not running there.

**Still open:** the exact header on a Setup `surfaceInvocations` call that carries the Salesforce user id was not read out of `_create_action_request`. The mTLS certificate is the service identity. User attribution is a separate header, not the certificate.

---

## Reviewer question 2 — which confirmation flag fires, and does it stack on `todo_approved`?

They are three different mechanisms. They do not share one flag.

**Plan approval** is `todo_approved` / `current_plan_shown` in the graph. For this two-step utterance the auto-approve rule does not match, so Executor does not start until `approve_todo_list`. **VERIFIED** YAML lines cited above.

**Platform tool confirmation** is `requireUserConfirmation` on the action definition the reasoner compiles.

- The graph sets `requireUserConfirmation: true` on `AdminCopilot__CreateGroup` (YAML 9745).
- The action asset sets `isConfirmationRequired: false` (`admin-access-assistant-impl/java/resources/ai/action/AdminCopilot/CreateGroup/CreateGroup.yaml`).
- `PlannerBuilder.getActionConfigsFromFile` copies `action.getIsConfirmationRequired()` onto `InvocableFunction.requireUserConfirmation` (`generative-ai-agent-impl/java/src/planners/runtime/PlannerBuilder.java` line 796). That is the action-YAML value.
- The reasoner’s DSL compiler copies whatever is on the `ActionConfiguration` it was given. `_resolve_require_user_confirmation` returns that field unchanged: `True` always confirms, `False` is an explicit opt-out, `None` lets voice entity detection decide (`atlas_v2/factories/_dsl_conversion.py` around line 1365; behavior wired at lines 1447 and 1602). The consumer named in that docstring is `atlas_v2/plugins/pre_orchestration/confirmation.py` `_mark_actions_requiring_confirmation`.
- A different parser, `config_parsing._extract_action_definitions`, treats graph `actionDefinitions` as name-only stubs and replaces them with planner-config functions. The integration step `action {name} requires user confirmation` says setting the flag on a graph fixture has no effect; the effective place is `plannerConfig.plugins[].functions[]` (`tests/integration/atlas_v2/behave/steps/common_behave_steps.py` around line 2184).

So: if the session compiles the file-based graph through `_dsl_conversion`, the YAML `true` is what the reasoner sees. If the session goes through `config_parsing`’s stub replacement, the action YAML `false` replaces it. The behave comment describes the CMS stub path. The harness runtime doc says Setup’s reasoner compiles the fetched agent DSL (`AgentDSLAuthoring` → unified spec), which is the `_dsl_conversion` path. **A live Setup trace showing which object was compiled was NOT captured.**

**Skill-level draft** is independent of both. `ManageUserAssignmentsSharing.md` always drafts with `commitChanges=false` and commits with `commitChanges=true`. That is NLD text, not `requireUserConfirmation`.

Stacking, if the DSL path is the one Setup uses: plan approval (`todo_approved`) happens first; then Executor may still pause on `CreateGroup` because the graph says `requireUserConfirmation: true`; then the membership skill does its own draft and commit. If the planner-config path wins, the `CreateGroup` platform pause does not fire, and only plan approval plus the membership draft remain.

`__user_input__` is a separate built-in with `require_user_confirmation=True` (`_dsl_conversion.py` `_create_user_input_action`). CreatePublicGroup says the action’s input form collects label, description, and hierarchy. That form is this built-in, not the `requireUserConfirmation` flag.

---

## Reviewer question 3 — Tuesday promotion, and what the Stable gate can revert

**The gate, in source, only changes which graph name the Setup client loads. It is closed for every org except one test org. A Tuesday runbook was not found in git.**

`orgHasAgentForSetupStableVersion` is `SetupCopilot.orgHasAgentforceSetupV2 && Gater.com.salesforce.agentforsetup.switchagentforsetupstableversion` (`setup-copilot-udd/.../SetupCopilot.accessChecks.xml`). When that check is true, `getAgentName()` returns `AdminCopilot__AgentforceForSetupStable` (`setupConfig.js` lines 113–116). The comment names W-24156884.

The gate definition (`gate-definitions` `teams/platform_actions/gates/com.salesforce.agentforsetup.switchagentforsetupstableversion.json`):

- Description: when open, serve `AgentforceForSetupStable.yaml`; when closed, serve `AgentforceForSetupV2.yaml`.
- `defaultResponseValue: false` on the test activation strategy.
- The only include rule is org id `00DVW00000DtIG9` (comment: SDB39 `stableagent`).
- `lastModifiedBy`: `meena.chinnaiah@salesforce.com`.

The Tuesday cadence, branch `p/agentforce-setup-v2/264-develop`, A4S owning the merge, a rotating Trust Hero, and “the gate reverts only the graph” are in a processed digest of Slack channel `C092LC2CD9T` (`#setup-with-agentforce-v2`), window 2026-09-15 to 2026-09-22, message TS `1789505820.340179`, attributed to Meena Chinnaiah. **VERIFIED as that digest** (`q3-second-brain` `agentic-setup/raw/processed/slack-setup-with-agentforce-v2-digest-2026-09-15-to-2026-09-22.md`). The raw Slack message and the Google doc id in that digest were not opened.

The digest says action schemas, invocable actions, templates, and NLDs deploy on their own and are not reverted by the Stable gate. That matches the code: the client swaps the agent developer name. It does not roll back `CreateGroupInvocableAction` or `CreatePublicGroup.md`.

Pipeline stages, approvers, freeze windows, canary percentages, and the command that opens the gate in production were **NOT FOUND**.

---

## Slack agent

MCP server metadata: `apiDomainName` `platform`, `serverName` `setup-agent`, `teamName` `Setup In Slack`, one tool `ChatWithSetupAgent` backed by `AdminCopilot__AgentforceForSetupV2`. **VERIFIED** `setup-copilot-impl/docs/specs/2026-07-07-setup-agent-mcp-server.md`.

Current delivery spec: near-core proxy `agentic-api-access` speaks MCP outward and the Agent API inward. Session cache key is `(orgId, mcpSessionId, botId)`. Response is text. No UI resource. **VERIFIED** `setup-copilot-impl/docs/architecture/mcp-delivery.md`.

Proxy timing in that spec: `AgentClientImpl` hardcodes **60s** with `RETRY_COUNT=2`. Practical ceiling described as a **3-minute** servlet/mesh async timeout. A local sample there is p50 about 35s, p95 about 98s, p99 about 117s, max 122.5s, labeled directional, not an SLO.

The 3-second Slack ack, the Slack-user to Salesforce-user map, and execution under the requester’s permissions were **NOT FOUND** for this agent. Unrelated repos mention Slack’s generic 3-second ack (`Industries-Q3Q4/wit-vaani-mentor` `slack_bot.py`). The June 2026 brain page still describes UEM hydration (`wiki/concepts/slack-integration.md`, synthesized 2026-06-11). The current Core spec says that UI path was removed.

One Slack thread (C06GAS5C2SW, `p1742320668192189`) says a Slack admin maps Slack profiles to the same Salesforce users before Agentforce in Slack. That is a person’s description, not this agent’s code.

---

## Headless 360 / MCP identity

The proxy “plumbs caller context into the agent” (`mcp-delivery.md`). The session key includes `orgId`. The header or token field that carries tenant and user into `ChatWithSetupAgent`, beyond that sentence, was **NOT FOUND**.

A reasoner test route string `platform/headless-360/discover` exists in `tests/unit/atlas_v2/factories/test_dsl_conversion.py`. That is a unit-test fixture for internal MCP route selection, not a count of onboarded capabilities.

“8 capabilities, 10+ teams” was **NOT FOUND**.

DX gateway headers `x-mcp-gw-cert-cn`, `x-mcp-gw-user-id`, `x-mcp-gw-xfcc` showed up in Slack channel `C090J83ECBA` in an earlier search. Those threads were not re-read for this writeup and were not tied to `agentic-api-access`.

---

## Change loop by artifact

| Change | What was found | What was not found |
|---|---|---|
| Agent graph YAML | Classpath resource in `java_resources_resourcejar.jar` (`setup-copilot-impl/docs/learnings/parallel-discovery-fan-out.md`). Client selects V2 vs Stable as above. | CI stages, canary, bake time. |
| NLD | Markdown under `setup-copilot-impl/java/resources/ai/knowledge/`. Ships with the Core module. | Index refresh cadence, a gate that can revert one NLD. |
| Core action | Java plus action YAML in `admin-access-assistant-impl` / `setup-copilot-impl`. Core release. | Whether action code and the graph are required to ship in the same patch. |
| Reasoner / planner / gateway code | Separate repos. Worker README points at the chatbot-runtime deployment wiki and says Falcon config was not applied by CI. | Stage list, secret injection, promotion criteria. |
| Prompt or model | Playground agent name `AdminCopilot__Sonnet5PlaygroundAgent` is one client-side switch (`setupConfig.js`). Brain digest of an Aug 12 SoS says the agent used GPT-4.1. | The production model pin and its change process. |

---

## Improvement loop

A written path from production failure to an eval case to a release gate was **NOT FOUND**.

One incident is in the same Slack digest: 2026-09-16/17, `AdminCopilot__QueryDataSource` returned 500s and the user-facing text “I apologize, but I encountered an unexpected error.” Digest’s cause: egress-mesh calls to `ms-api-protection` failed with “can not create request context,” three retries, then 500. Self-resolved within hours (thread root TS `1789578338.494949`). **VERIFIED as that digest.**

GES timeouts, a false 4.5–5 minute error, and a confirmation-loop sev1 were **NOT FOUND**.

The harness repo has `docs/kappa-audit-2026-08-18` through `docs/kappa-audit-2026-08-28-heldout`. The numbers inside those directories were not opened. Whether evals run in CI or block release was **NOT FOUND**.

---

## Sessions 2–5 — CI, images, Kubernetes, AWS

### What is verified

Worker: Maven (`mvn clean test`). Deploy doc linked from `chatbots/service-engine` `README.md` as `https://git.soma.salesforce.com/chatbots/chatbot-runtime/wiki/Deployment`. Falcon files under `./falcon-resources/armada`. README says there was no process to apply those config changes in CI/CD, and asks people to commit Armada changes via `./bin/armadactl_update`.

Reasoner image (`chatbots/service-agentic-reasoner` `Dockerfile`):

- Single `FROM docker.repo.local.sfdc.net/sfci/docker-images/sfdc_rhel9_python3/sfdc_rhel9_python3.12_minimal:1.0.9100`
- `uv` is mounted from the matching build image `sfdc_rhel9_python3.12_build:1.0.9100`, not a classic multi-stage `COPY --from`
- User `appuser` uid/gid 1001
- `EXPOSE 8128`
- Image size, scan severity that blocks release, signing, and whether staging promotes the same digest: **NOT FOUND**

Reasoner process (`gunicorn_config.py`):

| Setting | Value |
|---|---|
| `bind` | `0.0.0.0:8128` |
| `workers` | env `WORKER_COUNT`, default **6** |
| `worker_class` | `atlas_v2.server.worker.DrainingUvicornWorker` |
| `preload_app` | `False` (comment: copy-on-write breaks `AsyncClient`) |
| `max_requests` | **5000**, jitter **100** |
| Shutdown comment | `TURN_DRAIN_DEADLINE` 320 + post-end-of-connection 300 = 620; gunicorn graceful 640; timeout 700; Kubernetes grace asserted under 902 |

That shutdown comment describes voice WebSocket drain. What happens to a Setup SSE stream on SIGTERM was **NOT FOUND**. The Helm value for `terminationGracePeriodSeconds` was not opened; 902 is a comment, not a chart.

Monitoring README (`chatbots/terraform-monitoring` `README.md`): Argus alerts and Grafana panels from HCL for `bot-svc-api`, `bot-svc-llmagent`, `bot-svc-worker`, `agent-svc-reasoner`, and others. Worker board `https://moncloud-grafana.internal.salesforce.com/d/bot-svc-worker-alerts`. Thresholds were not opened. An older chatbot deployment runbook (CCE docs, exported 2026-08-18 from a 2022 Quip) says FIT tests gate deploys, Kaiju does not page, and alerts include request rate, error rate, availability, latency (Slack only), memory, CPU, and thread count. That runbook is for chatbot runtime generally, not proven to be the Setup agent’s on-call.

### What was not found, for every service in the loop

Pipeline definition file, ordered stages, duration, failure behavior, how CI injects secrets, environment promotion criteria, approvers, freeze windows, canary steps and percentages, bake time, analysis metrics, auto-rollback command, who can run it, and how long it takes.

Cluster, Falcon functional domain, namespace, Helm chart, values layering, replicas, CPU/memory, QoS, HPA, PDB, topology spread, probes, ConfigMap/Secret/Vault rotation, the path `api.salesforce.com` → ingress → Envoy → pod, and OOM or CPU-throttle history.

AWS account and region, Terraform, IRSA role scope, VPC, PrivateLink, Bedrock, S3 bucket policy, RPO/RTO, last DR test, monthly cost, and cost per request.

Named service “bootstrap”: **NOT FOUND**.

`einstein-ai-gateway`: no file opened. **NOT FOUND**.

`bot-svc-llm`: no repo opened. A brain page cites an Aug 12 platform SoS: the agent used GPT-4.1 and saw LLM-gateway 500s; one action regressed up to 700ms; parallel tool calling should be opt-in per action. **VERIFIED as that synthesis** (`agentic-setup/wiki/performance-improvements-q3-2026.md`), not as gateway config.

---

## Session 6 — application internals

| Topic | Verified | Not found |
|---|---|---|
| Reasoner runtime | Python, gunicorn, `DrainingUvicornWorker`, default 6 workers, port 8128. Harness calls the service FastAPI. | Worker/thread/async pool sizes. Connection pool sizes. |
| Graph execution | Four nodes above. Execution contract in `docs/architecture/agent-graph.md`: `StartTodo` → skill actions → `UpdateTodoStatus`, one todo at a time. | A trace of one turn with timings. |
| Planner vs reasoner | Worker README: planner is `bot-svc-llmagent`. Graph execution is the Python reasoner. The harness says the Java service does not interpret the YAML. | — |
| Action retrieval | `ToolRetrievalService`: `SYSTEM_PRIMITIVES_SIMILARITY_THRESHOLD = 0.7`. System-primitive search requests 50 hits, keeps `similarity >= 0.7`, then `limit(2)`. Separate constant `CANDIDATE_TOOLS_PER_GOAL = 5` is the global vector-fallback limit. `setup-copilot-impl/.../v2/ToolRetrievalService.java` lines 58–59, 334–342, 385–386. | Where the embedding vectors are generated and how often they refresh. This is not one “top-5 at 0.7” search. |
| Timeouts that were read | C2C client 90s. MCP proxy spec 60s × `RETRY_COUNT=2`, 3-minute ceiling. Gunicorn voice-drain comment 620/640/700. | A single chain that lines these up. 200 req/s per tenant. Circuit breakers. Bulkheads. |
| Idempotency | — | Dedupe key for double approve, Slack retry, or retry after timeout. |
| Partial failure | Group save and member commit are separate actions. | Compensation. Duplicate-name handling. |
| Two admins / Setup edit during approval | — | Lock or re-validation at execution. |
| Kill switches in this checkout | `com.salesforce.agentforceforsetup.agentMcp`, `com.salesforce.agentforceforsetup.setupagentmcpserver`, `com.salesforce.agentforsetup.switchagentforsetupstableversion`, `com.salesforce.agenticforsetupenablement.august_2026_release_features_enabled` (Data Cloud prerequisite bypass, spec W-23389050). | Behavior when the LLM gateway or retrieval is down, beyond the QDS 500 incident. |
| Kafka | — | Topic `PlannerActionOutput`, delivery semantics, DLQ, consumers. |

---

## Session 7 — Redis, Core DB, Data Cloud

**Redis.** Session objects for Agent API v6 are in Redis (`service-api` `ARCHITECTURE.md`). Graph flags are state variables the reasoner updates. Whether that state is the same Redis, the key schema, TTLs, cluster mode, node size, persistence, and eviction policy were **NOT FOUND** in this pass. What an in-approval turn does on failover or TTL expiry was **NOT FOUND**. Redis was not shown to be the source of truth for the `Group` row. The group row is a Core `GroupObject.save()`.

**Core DB.** Engine, isolation, `ALL_OR_NOTHING` vs `STANDARD`, `UNABLE_TO_LOCK_ROW`, and governor limits on this path were **NOT FOUND**. Tables this utterance touches in code: `Group` (create) and `GroupMember` (the second action, and the copy-membership SOQL). Org id on the member read comes from `UserContext.get().getOrganizationId()` (`PublicGroupRetriever`). `AiAgentSession`, `AiAgentInteraction`, and setup-audit retention were **NOT FOUND** on this path.

**Audit of “who approved what”.** **NOT FOUND** as a table or retention period. `enableEnhancedEventLogs: true` is set on the agent (YAML line 13). Where those events land was **NOT FOUND**.

**Data Cloud.** Spec W-23389050 removes Data Cloud as a Setup Agent UI prerequisite when `august_2026_release_features_enabled` is on. Ingestion stages, embedding model, chunk size, fusion weights, top-k, a shared index tenant, single-region risk, and GES timeouts were **NOT FOUND**.

---

## Session 8 — observability

| Item | Result |
|---|---|
| Splunk strings named by the harness | `AgentDSLAuthoring` + `ValidationError`; `payload.variables.too_many` with limit 50; `Error getting C2C token`. Doc: `setup-agent-harness` `docs/agent-runtime-stack.md`. Not run as queries. |
| One correlation id across every hop | **NOT FOUND** |
| Zipkin in Core, OTel at 1% | **NOT FOUND** |
| Where a trace would break (approval pause, SSE, Kafka, Slack) | **NOT FOUND** |
| Golden signals, dashboards to open first, alert thresholds, why retriever paging is off | **NOT FOUND** beyond the monitoring README’s service list |
| SLOs | **NOT FOUND**. No proposed numbers are invented here. |
| On-call, paging tool, runbooks | Chatbot runtime runbook names Slack `#copilot-runtime-platform-public` and a PagerDuty escalation. Not proven to be the Setup agent rotation. |
| Incidents reconstructed from a primary source | The QDS 500 in the 2026-09-16 digest, above. The other two named incidents were **NOT FOUND**. |

---

## Session 9 — why the shape is what the spec says

From `setup-copilot-impl/docs/architecture/agent-graph.md` and `docs/specs/2026-05-08-agent-graph-architecture-design.md` (same invariants):

- Planning is incremental because the spec says V1’s upfront plan took 8–12 seconds, and silence past three seconds was treated as a dead agent.
- Execution stays `StartTodo` → actions → `UpdateTodoStatus` so a failure stays attributable.
- Discovery is its own node so org-data lookup is not folded into Assistant.
- One NLD per todo, `sourceType=nld`.
- Authorization on the group actions is `HasCurrentUserAccessCheck` plus NLD permission frontmatter, not a sentence in the prompt.

Redis-for-graph-state, one shared knowledge index, and “ship the YAML in the Core jar” as rejected alternatives were **NOT FOUND** as decision records. The jar packaging itself is verified. The Stable fallback is verified as a client-side agent-name switch, and the digest says it does not roll back actions or NLDs.

### Numbers that were requested, and what exists instead

| Asked | Result |
|---|---|
| ~60 days → ~5 days (~92%) | **NOT FOUND** |
| Slack ~20 min → under 3 min | **NOT FOUND** |
| 150+ users, 8 teams | **NOT FOUND** |
| ~40% throughput | **NOT FOUND**. Brain cites “50% faster” on specific 264 utterances versus a 262 org, from an Aug 5 SoS. Not a throughput study, and not opened as a primary dashboard. |
| 8 Headless 360 capabilities, 10+ teams | **NOT FOUND** |
| 0.7 and top-5 | 0.7 then limit 2 on system primitives; 5 is a different fallback limit. See Session 6. |
| 200 req/s per tenant | **NOT FOUND** |
| OTel 1% | **NOT FOUND** |
| Eval pass rate, kappa, CI gate | Directories exist. Numbers and a blocking threshold were **NOT FOUND**. |

---

## Follow-ups a reviewer should still ask

These are the questions the code does not close.

1. **Which compiler runs for a production Setup session?** `_dsl_conversion` will honor the graph’s `requireUserConfirmation: true` on `CreateGroup`. `config_parsing._extract_action_definitions` will throw that boolean away and use the action YAML’s `false`. One captured session start (the object passed into `_resolve_require_user_confirmation` for `AdminCopilot__CreateGroup`) settles it. Until then, do not tell an admin that Create Group always shows a platform confirm card.

2. **Whose user id is on the mTLS action call?** The certificate is the service. The selector prefers mTLS off the workspace port. The header that Core uses for `UserContext` on `CreateGroupInvocableAction.currentUserHasAccess` was not read. If that header is the agent integration user rather than the admin who typed the sentence, the NLD’s `UserPermissions.ViewSetup` check is not the requester’s permission.

3. **Who opens the Stable gate outside org `00DVW00000DtIG9`?** The JSON in git opens it for that one test org only. The Tuesday procedure, the person who flips production orgs, and the proof that a bad NLD can be reverted without a Core rollback are not in the gate file. The digest says they cannot.

4. **Where does an in-approval turn live, and for how long?** `todo_approved` is a graph state variable. The Agent API session is Redis. The key, the TTL, and the behavior when that key is evicted while the admin is staring at the plan were not found. If the TTL is shorter than a slow approval, the second message starts a new plan and the first approval cannot be applied.

5. **What rolls back the group row?** `GroupObject.save()` and the later `ManageUserAssignments` commit are separate. No compensation was found. A reviewer should ask whether a failed member step leaves “Sales Ops” in the org, and whether a retry on the same name hits a duplicate-name error or creates a second group.

6. **Is there one id across the SSE pause?** Approval is a later HTTP turn. SSE, the worker, and the Slack/MCP proxy are separate processes. No correlation id was found that is guaranteed to survive the pause. An incident query that keys only on the first request’s trace will miss the execution turn.

7. **Do evals gate the Tuesday graph promotion?** Kappa-audit folders exist. No CI config was opened that fails a release on a pass-rate or kappa threshold. If the promotion is a human merge to `p/agentforce-setup-v2/264-develop`, the eval harness is advisory unless someone shows the check that blocks that merge.