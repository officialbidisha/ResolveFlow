# AgentPlatform for Setup V2: Agentic Access Management, End-to-End Architecture

**Example request:** "Create a public group *Sales Ops* and add users X and Y."
**Agent:** `AdminCopilot__AgentPlatformForSetupV2` (planner `Atlas__ConcurrentMultiAgentOrchestration`).
**Branch checked:** `p4/264-patch`. **Date:** 2026-10-04.

## Evidence legend

| Tag | Meaning |
|---|---|
| **[C]** | Verified in the Core repo (path:line given) |
| **[O]** | Verified in an off-core repo on git.soma (repo:path given) |
| **[S]** | Stated in Slack (channel and date given); not verified in code |
| **[I]** | Inference from verified facts; not directly confirmed |
| **[N]** | Searched for and **not found** |

## Component and repo map

| Component (term used in the questions) | Concrete implementation | Repo |
|---|---|---|
| Surface | Setup chat LWC `ui-setup-components/modules/setup/agenticSetupChat`, streaming client `ui-agentplatform-conversation-client-components/.../cwcLibrary` | Core |
| Agent runtime | `bot-svc-api` (Agent API) + `bot-svc-worker` (session engine) | `chatbots/service-api`, `chatbots/service-engine` |
| Conversation manager | No separate service by this name exists [N]. The role is split between `bot-svc-worker` (session state in Redis, `V6SessionCacheService`) and the reasoner's graph state in Redis | as above + `chatbots/service-agentic-reasoner` |
| Planner (the "agent runtime" that runs the graph) | `bot-svc-llmagent` | `chatbots/service-llmagent` |
| Reasoning | `agent-svc-reasoner` ("Atlas Daisy", Python FastAPI) | `chatbots/service-agentic-reasoner` |
| Knowledge / Executor / Assistant / Discovery nodes | Nodes in the agent graph defined in `AgentPlatformForSetupV2.yaml`, executed by the reasoner | Core `setup-copilot-impl` |
| Knowledge content | NLD markdown under `core/<module>/java/resources/ai/knowledge/` | Core + `communities/a4s-knowledge` |
| Retriever | Core `C360Retriever` calling the AI gateway retriever API | Core + `hawking/ai-gateway` |
| AI gateway | Two separate services: **LLM Gateway** `bot-svc-llm` (model calls, Trust Layer) and **AI Gateway** `einstein-ai-gateway` (retrievers, reranking) | `einsteingpt/service-llm-gateway`, `hawking/ai-gateway` |
| Data Cloud | `agentplatformnld` org's Data Cloud tenant: data stream, DLO/DMO, chunk, vector/hybrid index, Query Federator, Graph Execution Service (GES) | Data Cloud (not in code search) |
| Actions | `AdminCopilot__CreateGroup`, `AdminCopilot__ManageUserAssignments`, `AdminCopilot__QueryDataSource`, `FilterKnowledgeDocuments` | Core |
| Core APIs | `/services/data/vXX.X/support/functions/{name}` → `InvocableActionType` → UDD `GroupObject` / `GroupMemberObject` save | Core |

---

## 1. Request flow

### 1.0 Sequence summary

```
Browser (Setup chat LWC)
 │ ①  GET  /agentplatform/bootstrap                         → Core (OrgJWT)
 │ ②  POST api.company-w.com/einstein/ai-agent/v1/sessions/{id}/messages/stream (SSE)
 ▼
SFAP front door → bot-svc-api (Agent API)
 │ ③  mesh mTLS :7442
 ▼
bot-svc-worker (runtime / conversation session, Redis)
 │ ④  SSE :9443 /api/v1/planner/Atlas__ConcurrentMultiAgentOrchestration/...
 ▼
bot-svc-llmagent (planner)
 │ ⑤  mesh mTLS :8128
 ▼
agent-svc-reasoner (graph: Knowledge → Assistant → Executor → Discovery)
 │ ⑥  every LLM step ──────────────────────────────► bot-svc-llm (LLM Gateway) → OpenAI / Azure / Bedrock
 │ ⑦  Knowledge node: execute-action QueryDataSource ─► planner ─► Core /support/functions
 │        ⑧ Core C360Retriever ─► AI Gateway /retrievers/{name}/text-retrieval
 │        ⑨ AI Gateway ─► Data Cloud Query Federator ─► GES hybrid search on AgentPlatform_NLD_S3 index
 │ ⑩  Assistant node: plan (todo list) → turn ends → user approves → approve_todo_list
 │ ⑪  Executor node: execute-action createGroup ─► planner ─► Core /support/functions/createGroup
 ▼
Core: CreateGroupInvocableAction → PublicGroupRetriever.createPublicGroup → GroupObject.save()   ⑫
      ManageUserAssignments (draft → user confirms → commit) → GroupMemberObject bulk save
 ▲
 └─ ⑬ result card (groupSummaryComponent) flows back ⑪→⑤→④→③→② as SSE events
```

### 1.1 Hop-by-hop detail

Each hop answers the same five questions: **protocol, auth token, timeout, retry, and behaviour on failure.**

#### Hop ① Surface → Core bootstrap (token acquisition)
| Field | Answer |
|---|---|
| Components | Setup chat LWC → Core servlet `AgentPlatformMessagingAuthBootstrapServlet`, mapped to `/agentplatform/bootstrap` (`sfdc/conf/jetty/webapps/sfdc/web.xml:3005`) [C]. Internal service callers use `AgentPlatformMessagingAuthBootstrapMtlsServlet` at `/sfdcmtls/agentplatform/bootstrap` (`web.xml:3001`) [C]. A named-user variant is `NamedUserAuthBootstrapServlet` at `/agentplatform/bootstrap/nameduser` (`web.xml:3850`) [C] |
| Protocol | HTTPS GET to the org's Core instance [C] |
| Auth token used | Inbound: the user's Core UI session (browser) [I]. Exactly how the servlet validates it was **[N]** in code. Internal callers present a workload mTLS identity plus `x-sfdc-user-id` [S #tmp-agentplatform-obs-aip-chronos-collab 2026-09-16]. Outbound: a short-lived **OrgJWT** [S, same thread] |
| Timeout | None set in the client [C] |
| Retry | [N] |
| On failure | No token, so the chat cannot open a session. Internal callers that still use the old `/sfdc/agentplatform/bootstrap` path have received **404** since about 2026-09-16; the path now lives under `/sfdcmtls/` (W-24359622) [S #yellow-pubsec-hrc-my-dfd 2026-10-02; mapping confirmed in Core, `web.xml:3001`] |

#### Hop ② Surface → SFAP front door → Agent API (`bot-svc-api`)
| Field | Answer |
|---|---|
| Components | `streamConfig.js:2-3` → `https://api.company-w.com/einstein/ai-agent/v1/sessions` and `/messages/stream` [C], rewritten to `/v6.0.0/sessions` on `bot-svc-api` [O `chatbots/service-api`] |
| Protocol | HTTPS POST with a streamed SSE response [C/O] |
| Auth token used | `Authorization: Bearer <OrgJWT>` from hop ①. Port 443 requires an Org JWT; port 9443 is internal mTLS. The ingress strips and re-adds `x-sfdc-forwarded-port`, so it cannot be spoofed [O] |
| Timeout | No timeout in the client [C]. The stream is capped at **601 s** [O] |
| Retry | None in the client [C] |
| On failure | 401 on a bad or expired JWT; 429 when rate-limited. The chat shows an error. **Known defect:** turns of about 4.5–5 min show "Something went wrong" even though the backend succeeded [O `Agentic-Setup/cap` finding 53] |

#### Hop ③ Agent API → Agent runtime / conversation manager (`bot-svc-worker`)
| Field | Answer |
|---|---|
| Components | `bot-svc-worker` (`chatbots/service-engine/worker`). The session is kept in Redis (`V6SessionCacheService`) [O] |
| Protocol | HTTP inside the Falcon functional domain; the Envoy mesh upgrades it to mTLS. Port 7442 [O] |
| Auth token used | Mesh mTLS (workload identity) [O] |
| Timeout | [N] |
| Retry | [N] |
| On failure | Session create returns 500. A frequent root cause is `BOT_PLANNER_C2C` provisioning stuck in `ENQUEUED`: the planner returns 4xx and the caller sees 500 [S #agentplatform-local-dev-setup 2026-09-22; #copilot-planner-service 2026-08-05] |

#### Hop ④ Agent runtime → Planner (`bot-svc-llmagent`)
| Field | Answer |
|---|---|
| Components | `POST /api/v1/planner/Atlas__ConcurrentMultiAgentOrchestration/sessions/{id}/messages/stream` [O `chatbots/service-llmagent`]. The planner type comes from `AgentPlatformForSetupV2.yaml:30` [C]. The agent YAML is file-based and packaged in the Core jar [C] |
| Protocol | SSE through the internal front door, port 9443 [O] |
| Auth token used | mTLS (service identity) [O] |
| Timeout | [N] |
| Retry | [N] |
| On failure | "Initializing Copilot Session Failed"; 429 when rate-limited [O] |

#### Hop ⑤ Planner → Reasoning (`agent-svc-reasoner`)
| Field | Answer |
|---|---|
| Components | `agent-svc-reasoner` runs the graph: Knowledge, Assistant, Executor and Discovery nodes, with invariants I-1..I-6 (`setup-copilot-impl/docs/architecture/agent-graph.md`) [C]. Graph state is kept in Redis [O] |
| Protocol | HTTP over mesh mTLS, port 8128 [O] |
| Auth token used | Mesh mTLS. No auth header inside Falcon [O] |
| Timeout | Planner→reasoner timeout **[N]** |
| Retry | The reasoner retries on mesh 503s during rolling deploys [O] |
| On failure | Rate limit (GRLS) of **200 requests per org per minute** returns 429 [O]. Load is about 5 LLM calls per request at P95 and 12 at P99 [O]. Other failure handling [N] |

#### Hop ⑥ Reasoner → AI gateway: LLM Gateway (`bot-svc-llm`) → model providers
| Field | Answer |
|---|---|
| Components | Reasoner LLM client → `bot-svc-llm` [O `einsteingpt/service-llm-gateway`] → OpenAI, Azure OpenAI, Anthropic or Bedrock. Core's own LLM calls use `AIGatewayApiHandler` / `BaseHawkingApiHandler` [C] |
| Protocol | HTTPS (REST) [O] |
| Auth token used | Reasoner→gateway: mesh mTLS, with the tenant identified by `x-sfdc-core-tenant-id` (the GRLS rate-limit key) [O]. Core→gateway: Org JWT with scope `SFAP_API` [C] |
| Timeout | Reasoner side: connect **5 s**, read **90 s** (`atlas/core/config.py:186-187`) [O]. Gateway side, per provider: OpenAI, Azure and Anthropic **25 s**; Bedrock **90 s**. Trust Layer checks (PII, toxicity, prompt defense) **2 s each**. Mesh request timeout **300 s** [O]. Core side: no default timeout in the template; `LONG_TIMEOUT_SECONDS = 300` (`EinsteinHawkingClientInitializer.java:78`) [C] |
| Retry | Gateway retries up to **10** times at 50 ms. Trust Layer checks retry once [O]. Core side: 2 attempts in production and 1 elsewhere, with a fixed 3 s wait (`BaseHawkingApiHandler.java:54,106`) [C]. No circuit breaker on the Core side [C] |
| On failure | OpenAI circuit breaker fails over to Azure (`application.properties:905`, `circuitbreaker.openai.fallback-azure-enabled=true`) [O]. A kill switch routes to us-west-2 [O]. 429 above **200 req/s per tenant** [O]. Gatekeeper quota is enforced [O]. A 40% availability dip within 10 minutes has been seen [S #aicloud-perf-workgroup 2026-07-10] |

#### Hop ⑦ Knowledge node → Actions (`QueryDataSource`) → Core APIs
| Field | Answer |
|---|---|
| Components | The Knowledge node calls action `AdminCopilot__QueryDataSource`. It travels the same execute-action path as hop ⑪ (reasoner → planner → Core `/support/functions/`) [O/C]. In Core, `DocumentSourcesQueryService` (`help-documentation-copilot-impl`, :121-225) runs the **product docs, NLD and navigation** branches in parallel, each gated by C360 gates [C]. The LLM then picks documents, and `FilterKnowledgeDocumentsInvocableAction` keeps only those; their `tools:` lists populate `enabled_tools` [C] |
| Protocol / auth / timeout / retry | Same as hop ⑪: HTTPS; Bearer from token exchange; 60 s (90 s in aws-prod5-uswest2); **no retry** |
| On failure | A failed branch returns no documents. The Knowledge node continues with fewer documents or no tools [C] |

#### Hop ⑧ Core → Retriever → AI gateway (`einstein-ai-gateway`)
| Field | Answer |
|---|---|
| Components | `C360Retriever` → `POST /einstein/platform/v1/retrievers/{name}/text-retrieval` [C] → `hawking/ai-gateway` retriever provider [O]. Retriever names: `AgentPlatform_NLD_S3_Retriever_1Cx_fZl1aa6ecba` and `Help_Content_S3_DMO_Retriever_1Cx_fZl12284ee6` (`v2-dataHosting-properties.env`) [C] |
| Protocol | HTTPS through `api.company-w.com`. Production config: region header `us-west-2`, `aws-prod5-uswest2`, domain einstein (`mlplatform-config.yaml:151-166`) [C] |
| Auth token used | A **token exchange** for an access token in the Company W-owned `agentplatformnld` org (`agentplatformnld.my.company-w.com`) (`OrgCSAccessToken.java:48-100`) [C] |
| Timeout | Gateway retriever query **35 s**; reranker **12 s** [O]. No Core-side default [C] |
| Retry | **1** retry after a token refresh on 401/403 [C] |
| On failure | Reranker failure keeps the original order [O]. Retriever failure leaves that branch empty [C] |

#### Hop ⑨ AI gateway → Data Cloud (Query Federator → Graph Execution Service)
| Field | Answer |
|---|---|
| Components | AI gateway → Data Cloud Query Service / Query Federator → GES `hybrid_search` / `vector_search` on `AgentPlatform_NLD_S3_index__dlm` (also seen as `AgentPlatform_NLD_S3_DMO_index__dlm`) [O/S] |
| Protocol | SQL via `hybrid_search(...)` / `vector_search(...)` table functions (`CustomSqlQueryRequestBuilder.java:32,301`) [O]. Federator→GES uses Arrow Flight / gRPC on `:7443` [S #query-livesite 2026-05-03] |
| Auth token used | Tenant-scoped JWT for the `agentplatformnld` tenant (from hop ⑧) [C]. Data-space claims are enforced (`AIGatewayApiHandler.java:260-385`) [C] |
| Timeout | GES hybrid search about **11 s** deadline; Query Service **60 s** deadline [S #query-livesite, #hyper-agent 2026-04-16 / 05-05] |
| Retry | [N] |
| On failure | `DEADLINE_EXCEEDED` / `HYBRID_SEARCH_FAILURE`, so retrieval returns nothing. This happened repeatedly on the NLD index in cdp2 aws-prod1-us-east-1 (2026-04-15, 05-03, 05-05, 06-02) [S] |

#### Hop ⑩ Assistant node → human-approval pause (plan)
| Field | Answer |
|---|---|
| Components | `upsert_todo_item` builds the plan. The turn ends, showing the plan (`current_plan_shown`). When the user approves, `approve_todo_list` sets `todo_approved`. A single-task plan is **auto-approved** (`AgentPlatformForSetupV2.yaml` ~1102, ~1417; `todo_execution_status` :353) [C] |
| Protocol | The pause is an ended turn. The approval comes back as a new user message through hops ②–⑤ [C/O] |
| Auth token used | Same as hops ②–⑤ |
| Timeout | No expiry found in V2 **[N]**. The graph state lives in Redis, and its TTL is [N]. In the new CAP runtime, approvals **auto-decline after 5 min** and are lost on restart [O `Agentic-Setup/cap`] |
| Retry | Not applicable |
| On failure | If the user does not approve, no side effect happens |

#### Hop ⑪ Executor node → Actions → Core APIs (`createGroup`)
| Field | Answer |
|---|---|
| Components | Reasoner execute-action → planner (`falcon/bom/service.json:195`) → `ActionExecutionService.executeAction` → Core `POST /services/data/v60.0/support/functions/createGroup` [O] → `InvocableActionType.CREATE_GROUP` (`sfdc/java/src/common/invocation/InvocableActionType.java:2250`) [C]. In the agent YAML, the CreateGroup tool has `requireUserConfirmation: true`, `invocationTargetType: standardInvocableAction` and `invocationTargetName: createGroup` (`AgentPlatformForSetupV2.yaml:9741-9749`) [C] |
| Protocol | Reasoner→planner: HTTP over the mesh. Planner→Core: HTTPS REST [O] |
| Auth token used | Reasoner→planner: **no auth header**, relying on mesh mTLS [O]. Planner→Core: `Authorization: Bearer` from a token exchange; the exact grant is **[N]**. Requests carry `x-org-id`, `x-sfdc-user-id`, `x-sfdc-core-tenant-id` and `x-sfdc-app-context: sfdc.aiplanner` [S #agentplatform-api-integration-help 2026-09-12, A2A path to `/services/data/v65.0/support/functions/{name}`] |
| Timeout | Reasoner→planner: **60 s, connect 5 s** (`atlas/clients/proxy_client.py:32`); **90 s** (`atlas_v2/clients/force_clients.py:292`, `action_client.py:36`) [O]. Planner→Core: connect **5 s**; response **60 s** by default (`application.properties:222`, `CORE_FUNCTION_SOCKET_TIMEOUT:60000`); **90 s** in `falcon/config/helm/bot-svc-llmagent/falcon/fi/aws-prod5-uswest2/values.yaml:3` [O]. People in Slack also describe 60 s as "the AgentPlatform default action timeout" [S #help-oncall-agentplatform-mcp-group 2026-08-04] |
| Retry | **None** on either leg [O] |
| On failure | `ProxyResponseError` in the reasoner. Planner failures are published as a `PlannerActionOutput` event; a missing action returns `INVALID_TOPIC_OR_ACTION` [O]. A 403 from Core (permission or JWT) surfaces as "Invalid response from Core Action Execution" [S]. **Confirmation gate:** with `require_user_confirmation=true`, the planner emits a deterministic **mandatory action-confirmation message** before it executes. With it false or absent, it still emits an entity-confirmation message. LLM-generated confirmations can stack on top, so users may be asked twice [S #sev1-474516052 2026-09-14; a PR changing this merged around 2026-09-12] |

#### Hop ⑫ Core action → side effect
| Field | Answer |
|---|---|
| Components | `CreateGroupInvocableAction` → `CreateGroupInvocableActionAdapter` (requires **Manage Users** or delegated admin, `:313`) → `CreateGroupValidator` → `CreateGroupPermissionChecks` (403) → `access-control-impl/java/src/core/acs/group/PublicGroupRetriever.java:115-124`. That method creates a `GroupObject` (Type `REGULAR`, Name, Description, `DoesIncludeBosses`) and calls `save()` [C]. Members come next through `ManageUserAssignments`: a **draft** with `commitChanges=false`, user review, then a **commit** with `true`. Max 50 assignments; bulk save of `GroupMemberObject` [C] |
| Protocol | In-process Java within the Core API request [C] |
| Auth token used | Runs as the represented user (the user context from the JWT) [C] |
| Timeout | Core request and transaction limits [I] |
| Retry | None [C] |
| On failure | `CREATE_PUBLIC_GROUP_ERROR`, 401 or 403 [C]. Members can be saved ALL_OR_NOTHING or STANDARD, with per-assignment results [C]. If the member step fails after the group was created, the result is **partial** (group exists, members missing) [I] |

#### Hop ⑬ Return path
| Field | Answer |
|---|---|
| Components | Action output `groupSummaryComponent{groupId, isNewlyCreated}` → planner → reasoner (Discovery / response) → planner → worker → Agent API → SSE → LWC renders the card (`renderer.json`) [C/O] |
| Protocol | SSE in reverse over the same connections [O] |
| Auth token used | Same connections as the request |
| Timeout | Mesh 300 s; stream cap 601 s [O] |
| Retry | None |
| On failure | The false-error defect on 4.5–5 min turns (see hop ②). The side effect has still happened [O] |

---

## 2. Where each component runs

| Component | Platform | Region / cell model | Definition file |
|---|---|---|---|
| Setup chat LWC, streaming client | **Core monolith** (served from Core) | Per Core instance (Hyperforce cell). Host from `FALCON_INSTANCE`/`SUBSTRATE` (`config/settings/defaults/core.xml:457`) [C] | `ui-setup-components/BUILD.bazel`, `ui-agentplatform-conversation-client-components/` [C] |
| Bootstrap servlets | **Core monolith** | Per Core instance | `sfdc/conf/jetty/webapps/sfdc/web.xml:3001,3005,3850` [C] |
| Agent definition (graph, topics, NLD) | **Core monolith** (classpath resource in the Core jar) | Ships with the Core release to every instance. Gated per org/user (`SetupCopilot.accessChecks.xml`) [C] | `setup-copilot-impl/java/resources/ai/agent/AdminCopilot/AgentPlatformForSetupV2.yaml` and the `ai/topic`, `ai/knowledge` folders [C] |
| Actions (CreateGroup, ManageUserAssignments, QueryDataSource) | **Core monolith** | Per Core instance; data lives in the org's Core database | `admin-access-assistant-impl/java/resources/ai/action/AdminCopilot/CreateGroup/CreateGroup.yaml` and its `input`/`output` `schema.json`; Spring `AdminAccessAssistantImplSpringConfiguration.java` [C] |
| Agent API `bot-svc-api` | **Internal runtime on AWS** (Falcon/Hyperforce) | Bots / Unified Engagement functional domain, per Falcon instance [O] | `chatbots/service-api`: `falcon/addons/sfap-*.tf` (SFAP route), Helm values [O] |
| Runtime `bot-svc-worker` | **Internal runtime on AWS** (Falcon) | Bots functional domain [O] | `chatbots/service-engine`: `terraform/`, `manifests/`, `.strata.yml` [O] |
| Session / graph state (Redis) | **AWS service** (managed Redis) [O] | Co-located with the worker and reasoner [I] | [N] (definition file not located) |
| Planner `bot-svc-llmagent` | **AI Cloud** (Falcon, Einstein domain) | Einstein / einstein2 functional domains, per Falcon instance (e.g. `aws-prod5-uswest2`; gov `giaprod1`, `giastage1`) [O/S] | `chatbots/service-llmagent`: `falcon/config/helm/bot-svc-llmagent/` (layered base → env → FI → FD values), `releases_{blue,gold}.tf`, `vault.tf` [O] |
| Reasoner `agent-svc-reasoner` | **AI Cloud** (Falcon) | Einstein domain; staged rollout to about 21 instances [O] | `chatbots/service-agentic-reasoner`: `falcon/{helm,config,addons,bom,sfap}`, `gunicorn_config.py` [O] |
| LLM Gateway `bot-svc-llm` | **AI Cloud** (Falcon) | Einstein / einstein2, with per-instance overrides. In-region Bedrock is enforced (`RESTRICT_BEDROCK_REGION_ENABLED`); kill-switch fallback to us-west-2 [O] | `einsteingpt/service-llm-gateway`: `falcon/config/helm/bot-svc-llm/values.yaml` (HPA 3–9, 4 CPU / 12 Gi, Trust Layer sidecar), `application.properties` [O] |
| LLM providers | **External / AWS service** (OpenAI, Azure OpenAI, Anthropic, AWS Bedrock) | Bedrock in-region; OpenAI/Azure by provider region [O] | Provider routing in the LLM Gateway `application.properties` [O] |
| AI Gateway `einstein-ai-gateway` (retriever, reranker) | **AI Cloud** (Falcon) | Einstein domain; about 25 prod instances (prod0 … prod28 us-west-2, plus gov) [O] | `hawking/ai-gateway`: `falcon/config/helm/einstein-ai-gateway/values.yaml` (HPA 3–12) [O] |
| Knowledge index, Query Federator, GES | **Data Cloud** | **One global shared tenant**: the `agentplatformnld` org (backup `agentplatformnld-2`). The index sits in cdp2 / aws-prod1-us-east-1 [S]. Every org's Setup agent calls this one tenant [I] | Data stream, index and retriever are configured in Data Cloud setup; not in a repo [N]. Core points to them in `v2-dataHosting-properties.env` [C] |
| NLD source bucket | **AWS service** (S3) | us-east-2 (`agentplatform-nld-pd`, `knowledge-csv-bucket`) [O] | `communities/a4s-knowledge` scripts [O]; the bucket's Terraform [N] |
| Agent harness / evals | **Internal runtime** (developer machines / CLI; not deployed to production) | Points at preprod/dev orgs [O] | `Agentic-Setup/setup-agent-harness`, `Agentic-Setup/cap-tools` [O] |

**Traffic routing:**
- Within a functional domain: plain HTTP, upgraded to mTLS by the Envoy mesh [O].
- Between domains: through the `api.company-w.com` front door or the ingress/egress gateways [O].
- Region choice: each org's AI region comes from its provisioned instance (`mlplatform-config.yaml`) [C].

---

## 3. Data Cloud path

### 3.1 Pipeline stages
| Stage | Setup knowledge corpus (what create-group uses) |
|---|---|
| **Source** | NLD markdown files in Core, e.g. `setup-copilot-impl/java/resources/ai/knowledge/AdminCopilot/Sharing/CreatePublicGroup.md` and `ManageUserAssignmentsSharing.md` [C]. They are collected from about 15 team branches by `generate_nld_csv_from_branches.py`; document generation uses LiteLLM `gpt-4o-mini` [O `communities/a4s-knowledge`]. Help documentation is a second source [C] |
| **Landing** | S3 us-east-2: `agentplatform-nld-pd`, `knowledge-csv-bucket` [O] |
| **MDLO** | No "MDLO" object or concept exists in this path [N]. The corpus lands directly as a DLO from an S3 data stream |
| **DLO** | Data stream "AgentPlatform NLD S3" → `AgentPlatform_NLD_S3__dlm` [O]. Help content: `PIC_AgentPlatform_HelpDocs__dlm` [C] / `hdc_GenAIHelpContent__dlm` [O] |
| **DMO** | `AgentPlatform_NLD_S3_DMO` (its index appears as `AgentPlatform_NLD_S3_DMO_index__dlm`) [S]. Help retriever is `Help_Content_S3_DMO_Retriever_*` [C] |
| **Chunk** | `AgentPlatform_NLD_S3_chunk__dlm` [O]. The harness default is `passage_extraction`, max 512 tokens, HTML stripped [O]. Production chunk settings [N] |
| **Embedding** | Harness default `e5_large_v2`, 1024 dimensions, cosine [O]. Production embedding model [N]. Separately, **tool/action selection** uses ada-002 embeddings (1536 dimensions) bundled in the jar (`ActionEmbeddingService.java:46`) [C] |
| **Index** | `AgentPlatform_NLD_S3_index__dlm`: HYBRID (vector + keyword), HNSW M=64 / ef=2000 (harness), NEAR_REALTIME [O] |
| **Retriever** | `AgentPlatform_NLD_S3_Retriever_1Cx_fZl1aa6ecba`, `Help_Content_S3_DMO_Retriever_1Cx_fZl12284ee6`, plus premium variants [C/O] |

### 3.2 Ingestion cadence
- **Manual or skill-driven; no schedule exists** [O]. A run means "Refresh All The Files" on the S3 data stream, then a manual index rebuild on 4 orgs.
- A corpus change in Core also needs an `a4s-knowledge` jar version bump in Core, which takes about 12–24 h [O].
- Index mode is NEAR_REALTIME once data lands [O].

### 3.3 Tenant isolation
- **Setup corpus:** a single Company W-owned tenant (`agentplatformnld`) that holds **no customer data**. Every customer org reads the same index. The calling org is identified only through claims in the exchanged token (`OrgCSAccessToken.java`) [C].
- **Customer retrievers** (other agents): isolated per org and per data space through signed claims; a user without access gets `NO_DATASPACE_ACCESS` (`AIGatewayApiHandler.java:137,260-385,857`) [C]. Logs carry `cdpTenantId` [O].

### 3.4 Pre- vs post-filtering
- **Pre-filter:** the filter expression is passed as the third argument of `hybrid_search` / `vector_search` and runs inside the search engine (`CustomSqlQueryRequestBuilder.java:32,301`) [O].
- **Post-filter**, in this order:
  1. Reranker, up to 320 chunks, 12 s [O].
  2. Optional result post-processor, off by default [C].
  3. Core Setup filtering: permissions, client and de-duplication (`DocumentSourcesQueryService`) [C].
  4. The LLM selects documents, then `FilterKnowledgeDocumentsInvocableAction` keeps only those [C].

### 3.5 Retrieval parameters
| Parameter | Value |
|---|---|
| topK | Default **10**, max **2048** (`MlRetrieverConstant.java:17-18`) [C]; same in the gateway `RetrieverUtil` [O] |
| Mode | Basic retrieval; scores returned are vector, keyword and hybrid [O] |
| Reranker | Up to 320 chunks, 12 s timeout [O] |
| Query timeout | AI Gateway 35 s [O]; GES about 11 s; Query Service 60 s [S] |
| Hybrid fusion weights / score threshold | [N] (the Data Cloud search server is not in code search) |
| Tool retrieval (separate path) | Top **5** (`ActionEmbeddingService.java:46`); similarity threshold **0.7** (`ToolRetrievalService.java:59`) [C] |

---

## 4. Build and release pipeline (per deployable)

| Deployable | Build | Test gates | Release / promotion | Rollback |
|---|---|---|---|---|
| **Core modules**: `setup-copilot-impl` (agent YAML, NLD, topics), `admin-access-assistant-impl` (CreateGroup), `access-control-impl`, `help-documentation-copilot-impl`, `einstein-metadata-impl`, UI modules | Bazel `sfdc_core_module`, aggregated into `//core-app` via `core-app/members.bzl` (lines 1445, 2953, 2954, 3616, 4485) [C] | CIX precheckin `tools/build/cix-pipelines/pipelines/core-precheckin-pipeline-rhel9.yaml`, then postcommit unit tests, ftests and coverage [C]. Pre-push hook `.claude/hooks/finish-core-gate.sh` blocks changes to `AgentPlatformForSetupV2.yaml` until the graph invariants I-1..I-6 pass [O] | Core release train (`p4/264-patch`; feature minVersion 264, `features/platform-agent-for-setup.feature.yaml`) [C]. **Agent graph:** every **Tuesday** since 264.6, the validated graph becomes live V2 and the previous one becomes `AgentPlatformForSetupStable`. All graph changes go through `p/agentplatform-setup-v2/264-develop`, and a rotating "Trust Hero" owns the promotion [O] | Per-org gate `com.company-w.agentforsetup.switchagentforsetupstableversion` moves an org to Stable. This reverts **the graph only**, not actions, templates or NLDs [O] |
| **NLD corpus** (`a4s-knowledge` jar + Data Cloud index) | SFCI `minimal-java` → Nexus [O] | Harness/eval runs (not a gate; see 6.7) [O] | Bump the jar version in Core, then manual S3 upload and index rebuild on 4 orgs [O] | Re-upload the previous corpus and rebuild [I] |
| **bot-svc-api, bot-svc-worker** | Strata SFCI → Docker image [O] | Service CI [O]; details [N] | Falcon Helm + Terraform add-ons; promotion through FD stages with Argo canary [O] | Argo / Helm rollback [O] |
| **bot-svc-llmagent (planner)** | Strata SFCI [O] | Service CI [O] | einstein2 → soak → einstein; blue/gold releases (`releases_{blue,gold}.tf`); Argo canary [O]. Deployments are frozen around Dreamforce [S #agentplatform-bots-release-sync 2026-09-14] | Switch blue/gold; Argo rollback [O] |
| **agent-svc-reasoner** | Strata SFCI [O] | Service CI [O] | Mesh-staggered rollout (e.g. 1.0.949 to 21 instances) [O] | Argo rollback [O] |
| **LLM Gateway** | Strata; `falcon/staggers/{dev1stagger,developstagger,ebf}.yaml` [O] | Health-check analysis during rollout [O] | FedX deploy with a 1-minute pre-rollout pause [O] | Automated on failed analysis [O] |
| **AI Gateway** | Strata [O] | `falcon/config/pipeline/run-einstein-ai-gateway-fit-tests` [O] | Falcon Helm [O] | Helm rollback [O] |

---

## 5. Runtime operations and observability

### 5.1 Splunk
| Layer | Index / search | Source |
|---|---|---|
| Core | Core Splunk; log record `AgentForSetupLlmTiming` (`hk`/`llt`) and `AccessInvocableActionLogRecord` (`log_0aaia`) | [C] |
| Agent runtime | `index=bots` | [O] |
| Planner | `index=globaldefault` (non-core Splunk) | [O] |
| Retriever | `index=distapps mdc.clientFeatureId=EinsteinRAG k8s_container_name=einstein-ai-gateway` | [O] |
| Data Cloud | Query Federator / GES logs, surfaced through #query-livesite and Hyper Agent | [S] |
| Harness | `splunk-check.sh <session-id>` searches **preprod** `atlas*` logs only | [O] |

### 5.2 Structured log fields
- **`AgentForSetupLlmTiming`** (`monitoringlib/.../app-logging-format.xml:36157`): traceId, templateDevName, llmGenerationId, durations, token counts, errorMessage [C].
- **`AccessInvocableActionLogRecord`** (CreateGroup): action, status, input, output, timeMs, targetPublicGroupId [C].
- **Planner trace** (`setup-agent-harness` `trace-schema.md`): `PlanSuccessResponse{planId, sessionId, topic, plan[]}`, with these step types [O]:
  - UserInputStep
  - LLMStep (prompt, response, latency)
  - FunctionStep (name, input, output)
  - TransitionStep
  - PlannerResponseStep (Inform / Action / Clarify / Error, isContentSafe)
  - OutputEvaluationStep (GROUNDED / UNGROUNDED)
- **Planner→Core request tags:** `planner_type`, `bot_session_id`, `turnId`, `planId`, `user_context`, `agent_version_api_name` [S].
- **Enhanced event logs:** `enableEnhancedEventLogs: true` (`AgentPlatformForSetupV2.yaml:13`) [C]. Session tracing data goes to the `AiAgentSession` / `AiAgentInteraction` DMOs (`agentplatform-session-tracing-*`) [C].
- **Trace propagation:** Brave/Zipkin `traceId` in Core [C]; OpenTelemetry sampled at 1% in the LLM Gateway [O].

### 5.3 Async hops
| Hop | Mechanism |
|---|---|
| Core actions | Synchronous; no async hop on the create-group path [C] |
| Planner action failures | Published as `PlannerActionOutput` events [O] |
| LLM Gateway feedback / audit | Ajna Kafka; deferred audit to S3 [O] |
| Streaming | SSE end to end. Not a queue, but a long-lived connection (601 s cap) [O] |
| NLD ingestion | Offline, manual (see 3.2) [O] |

### 5.4 Human-approval pause
- **What it looks like at runtime:** the turn ends with an Action/Confirm response type, and the graph state holds `current_plan_shown` / `todo_approved` [C/O]. The planner's mandatory confirmation message for `require_user_confirmation` shows the same way [S].
- **Dedicated "awaiting approval" trace event or metric:** [N]. Pause length and abandonment are not measured.
- **Expiry:** none found in V2 [N]. CAP auto-declines after 5 min [O].

### 5.5 Dashboards
- Grafana "falcon-service-owner-dashboard" for the retriever provider [O].
- MonCloud Grafana for planner availability [S].
- Harness HTML reports (`setup-agent-harness-reports`) and `cap-board` [O].
- A Setup-agent business dashboard (success rate, approval rate, latency per action): [N].

### 5.6 Alerts
| Service | Alert | Routing | Source |
|---|---|---|---|
| AI Gateway retriever | Availability **Sev2 < 99.7%**, **Sev1 < 99.3%**; 60-min window, 10-min persistence (`terramon-alerts-provider-retriever`) | Slack `C082F0DTYBA`; **PagerDuty commented out** | [O] |
| Planner `bot-svc-llmagent` | `GiaAvailability-<instance>-<domain>`: "Planner Service is down… AgentPlatform will not work". Seen for gov `giaprod1` / `giastage1`, including NoData triggers. Thresholds [N] | MonCloud Notifications → Grafana | [S #govsre-umbrella-testing 2026-10-02] |
| Data Cloud Query Federator | Availability **Sev2 < 96%** | PagerDuty (#cdp-query-federator-alerts) | [S] |
| LLM Gateway, reasoner, worker, Setup agent | [N] | — | — |

### 5.7 SLOs
- **No SLO was found** for the Setup agent, reasoner, planner (commercial), LLM Gateway or Agent API [N].
- The only numeric targets found are the retriever alert thresholds (99.7 / 99.3%) and the Query Federator threshold (96%).

---

## 6. Permission checks, allowlists, schema validation, human approval, plan validation, confidence scoring, eval suites and AI harness

### 6.1 Permission checks
| Layer | Check | Source |
|---|---|---|
| Org | `orgHasAgentPlatformSetupV2 = Gater.com.company-w.agentplatform.setupV2 && !OrgPermissions.AgentPlatformSetupV1Override` | `setup-copilot-udd/.../SetupCopilot.accessChecks.xml` [C] |
| User | `UseSetupWithAgentPlatform` permission; `userCanAccessEnhancedAgenticSetup`; `userCanExecuteMetadataCrud` | same file [C] |
| Default agent | `AgentDefaultRegistryImpl.java:33` | [C] |
| Action | CreateGroup requires **Manage Users** or delegated admin (`CreateGroupInvocableActionAdapter.java:313`) and `CreateGroupPermissionChecks`, which returns 403 | [C] |
| Agent API edge | Org JWT on 443; mTLS on 9443 | [O] |
| Core function API | Runs with the represented user's normal feature and endpoint permissions | [S #tmp-agentplatform-obs-aip-chronos-collab 2026-09-16] |

Notes:
- `APIKeyAuthMechanism` grants InternalService **unconditionally**. It is meant for tests [O].
- Admins report "You don't have the required permissions to change agent availability" even with `UseSetupWithAgentPlatform` assigned [S #agentplatform-technical-support 2026-07-15].

### 6.2 Allowlists
| Allowlist | Entry | Source |
|---|---|---|
| Copilot action allowlist | `AdminCopilot__CreateGroup`, owner "Access Control Experience" | `generative-ai-agent-api/java/resources/module-config/copilot-action-allow-list.yaml:61` [C] |
| Surface blocklist | `CREATE_GROUP` is **blocked** from the public REST and Apex invocable surfaces | `AdminAccessAssistantImplSpringConfiguration.java:72,104` [C] |
| Metadata write map | `Group`: CREATE / READ / UPDATE | `mdapi-impl/.../FileBasedMetadataDaoAllowedOperationsImpl.java:85` [C] |
| Action registration | Action YAML: `isConfirmationRequired: false` (confirmation is enforced in the agent YAML instead) | `CreateGroup.yaml` [C] |

### 6.3 Schema validation
- `CreateGroup/input/schema.json` uses `unevaluatedProperties: false`; the output schema is `output/schema.json` [C].
- Server-side checks in `CreateGroupValidator`: name and inputs [C].

### 6.4 Human approval
Four layers:
1. **Plan approval** (`approve_todo_list`). Single-task plans auto-approve [C].
2. **Tool confirmation:** `requireUserConfirmation: true` on CreateGroup (`AgentPlatformForSetupV2.yaml:9745`), plus the prompt rule "NEVER call without confirmation" [C]. The planner emits a deterministic mandatory confirmation message [S].
3. **Draft-then-commit** for membership (`commitChanges=false` → `true`) [C].
4. **CAP runtime (future):** a pre-tool-use hook parks the run; it auto-declines after 5 min and is lost on restart [O].

Gaps:
- `CreateSObjectCollection` has `requireUserConfirmation: false` (`:4114`) [C].
- `ExecuteMetadataCreate` has no confirmation and can write `Group` (`:11623`) [C].
- Known planner defects: confirmation loops and double prompts [S #nga-template-migration 2026-06-18; #sev1-474516052 2026-09-14].

### 6.5 Plan validation
- Graph invariants I-1..I-6 are enforced by the pre-push hook [O/C].
- Plan state machine `todo_execution_status` (`:353`) [C].
- SME plan input checks [C].
- Runtime validation of a generated plan (other than the approval itself): [N].

### 6.6 Confidence scoring
- **Live in production:**
  - Tool retrieval threshold 0.7 (`ToolRetrievalService.java:59`); top-5 actions (`ActionEmbeddingService.java:46`) [C].
  - Per-response grounding check (`OutputEvaluationStep` GROUNDED / UNGROUNDED) [O].
  - Trust Layer toxicity score (`EinsteinSMToxicity`) and PII detection (`EinsteinSMPII`) [O].
  - Guardrails timeout 10 s (`TRUST_GUARDRAILS_TIMEOUT_SECONDS`, reasoner `config.py:72`) [O].
- **Defined but unused:** the thresholds in `ClassificationConstants` are dead code [C].
- **Not present:** a calibrated confidence score that gates execution of a side effect [N].

### 6.7 Eval suites
| Suite | Size / result | Source |
|---|---|---|
| Q3 utterance suite | 524 utterances; latest five-run report **81.7% pass**, 88.3% stable | [O] |
| Daily backend regression | 499 rows across 53 actions; partly judged by Haiku | [O] |
| UI runs | Browser service, vision-graded | [O] |
| Utterance corpus | 3,216 files in `eval-utterance-corpus`, tied to one dev org | [O] |
| Create-group cases | `tests/scenarios/uam-sharing/uam-sharing-suite.yaml` L728–770; `capability-eval/user-simulator/scenarios/gen-create-public-group.json`, where success is checked with `SELECT … FROM Group WHERE Type='Regular'` | [O] |
| Create-group utterances | Authored April 2026; signed off July 2026 | [S #srivatsakl-all-org, #acx-dev-connect] |
| Judge agreement | κ = 0.649 | [O] |
| Core tests | Structure and action behaviour only (`CreateGroupInvocableActionTest`, `CreateGroupInvocableActionAdapterTest`, `GroupActionsAgenticAppsRendererTest`) | [C] |
| CI gate on pass rate | **None** [N] | — |

### 6.8 AI harness
- `Agentic-Setup/setup-agent-harness`: a CLI built on `mcp-harness`, with results PASS / FAIL / SOFT_FAIL [O].
- `Agentic-Setup/cap-tools`: scoring engine [O].
- Gold suite `gold-full.sh`: 33 API cases and 15 UI fixtures; recommended, not required [O].
- `splunk-check.sh` for trace lookups [O].
- The CreateGroup action itself went through DRB approval in February 2026 [S #user-access-ux-pm-eng-collab].

---

## 7. Known limits and risks

| # | Risk | Evidence | Impact |
|---|---|---|---|
| 1 | **Plaintext credentials** in `Agentic-Setup/setup-agent-harness/docs/runbooks/api-regression-daily.md`, including a session ID | [O] | Credential exposure. **Rotate and purge from git history** (values deliberately not reproduced here) |
| 2 | **Open P24-class security finding on the agent bootstrap endpoint**, tracked in W-24123535, with a reopened fix bypass in W-24151809. The move to `/sfdcmtls/agentplatform/bootstrap` is probably part of the fix [I] | [S #p24-review-board 2026-09-08/10] | Hop ① is the root of trust for the whole flow. Confirm remediation status with ProdSec before relying on hop ① as designed |
| 3 | CAP `GET /v1/agents/:id` leaks `SF_ACCESS_TOKEN`; `APIKeyAuthMechanism` grants InternalService unconditionally | [O] | Token leak and over-privileged test auth |
| 4 | **Bootstrap path change breaks internal callers** (404 since about 2026-09-16; W-24359622) | [S], [C web.xml:3001] | GovCloud customer go-live is blocked; other internal callers may break silently |
| 5 | **No retries on action execution** (reasoner→planner 60/90 s; planner→Core 60 s, or 90 s in one instance) | [O] | A Core latency spike becomes a failed turn |
| 6 | **Partial side effects:** the group is created, then the member step fails or times out; there is no compensation | [C/I] | A group exists without its members; a user retry may hit a duplicate name |
| 7 | **Timeout chain does not line up:** no Core gateway default; planner 60 vs 90 s by region; mesh 300 s; stream 601 s | [C/O] | False "Something went wrong" on 4.5–5 min turns although the change happened |
| 8 | **Shared knowledge index in a single region:** one `agentplatformnld` tenant in cdp2 us-east-1, with repeated GES 11 s timeouts | [S] | A Data Cloud incident in one cell degrades Setup knowledge for every org worldwide; data-residency question for knowledge queries [I] |
| 9 | **Manual knowledge ingestion:** S3 upload plus 4-org index rebuild plus Core jar bump (12–24 h) | [O] | Stale or wrong instructions; NLD and tool drift |
| 10 | **Approval weaknesses:** single-task plans auto-approve; `ExecuteMetadataCreate` writes `Group` without confirmation; `CreateSObjectCollection` has no type allowlist and conflicting flags; confirmation loops and double prompts; CAP 5-min auto-decline | [C/O/S] | A side effect without explicit consent through an alternate tool, or poor UX |
| 11 | **No eval release gate:** 81.7% pass; no CI threshold; gold suite optional; judge κ 0.649 | [O] | Regressions can ship in the weekly Tuesday promotion |
| 12 | **Monitoring gaps:** retriever alerts go only to Slack (PagerDuty off); no LLM Gateway, reasoner or Setup-agent alerts found; no SLOs; harness Splunk check covers only preprod | [O/S/N] | Outages detected by customers first |
| 13 | **Rollback scope:** the Stable gate reverts only the graph | [O] | Breaking changes in actions, templates or NLDs cannot be rolled back that way |
| 14 | **Provisioning fragility:** `BOT_PLANNER_C2C` stuck in `ENQUEUED` produces misleading 500s | [S] | New orgs or sandboxes cannot start sessions |
| 15 | **Model and region:** a Sonnet 5 move may block 6 of 623 prod orgs and 9 of 438 sandboxes (in-region-only routing or Bedrock off); in-region Bedrock enforcement vs the us-west-2 kill switch | [O] | Outage or residency conflict for regulated orgs |
| 16 | **LLM Gateway is a single point of failure** (40% availability dip observed); no Core-side circuit breaker | [S/C] | Every turn fails during gateway incidents |
| 17 | **Zero data retention not confirmed for Setup:** customers have asked whether ZDR covers RAG context, plans and history; only a generic Trust Layer answer was given | [S #setup-with-agentplatform-help 2026-06-02] | Blocks security reviews and procurement |
| 18 | **Dead confidence constants** (`ClassificationConstants`) | [C] | False sense of a confidence gate |

### Still unverified [N]
- How the browser `/agentplatform/bootstrap` servlet validates the session.
- The exact token-exchange grant from the planner to Core.
- Timeouts on the Agent API→worker, worker→planner and planner→reasoner hops.
- Redis TTL for graph and approval state.
- Data Cloud production embedding model, chunk settings, fusion weights and thresholds.
- Production SLOs, plus alert thresholds for the planner (commercial) and LLM Gateway.
- Setup-specific ZDR confirmation.
- Whether the planner `require_user_confirmation` change (about 2026-09-12) is in effect for V2 CreateGroup.