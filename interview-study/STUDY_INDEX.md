# Study Index

Start here. Order is by what to rehearse first; each line says what the note is for.

## ResolveFlow (own project, be able to defend every claim)
1. `RESOLVEFLOW_CONCURRENCY_EXPLAINED.md` - asyncio / ContextVar / Semaphore / GIL, with follow-up questions and an honesty table.
2. `resolveflow-docs/CONCURRENCY.md` - the short design record behind it.
3. `resolveflow-docs/EKS_DEPLOYMENT.md` + `ResolveFlow_EKS_Learning_Notes.pdf` - what was verified on EKS vs only designed. Say "designed" for ALB/WAF/Pod Identity/HPA.
4. `resolveflow-docs/exactly-once/` - run `demo.py`; 5 racing callers -> 1 comment.
5. `resolveflow-docs/CHECKPOINTING.md`, `CAP_THEOREM_AND_AGENTIC_SYSTEMS.md` - state, resume, consistency trade-offs.

## Known weaknesses to volunteer before being asked
- OAuth token persisted in `sessions` and in LangGraph checkpoints.
- Resume can double-post without the exactly-once fix (design only in app code).
- Schema setup runs per replica; Pinecone is called at import; `/api/health` skips Postgres.
- Per-process semaphore: real ceiling = limit x instances.

## Interview-specific
- Company X: `HM_ROUND_PREP.md`, `AGENTPLATFORM_SETUP_V2_HLD_INTERVIEW_PREP.md`, `A4S_V2_COMPLETE_GUIDE.pdf`, `pdf/INFRA_FROM_SCRATCH.pdf` (AWS/K8s/CI-CD gap).
- Company Y: `COMPANY_Y_ANSWERS.md`, `pdf/COMPANY_Y_COMBINED_STUDY_PLAN.pdf`, `pdf/COMPANY_Y_INTERVIEW_QUESTION_BANK.pdf`.
- Company Z backend: `pdf/COMPANY_Z_DATABASES_TRANSACTIONS_DEEP_DIVE.pdf`.
- Python / MCP / agents: `PYTHON_DEEP_DIVE.md`, `MCP_SERVER_ISSUES.md`, `mcp_server_reference.py`, `resume_examples/`.

## Habit
For every note: say the 60-second version aloud, then answer its follow-up list without looking.
