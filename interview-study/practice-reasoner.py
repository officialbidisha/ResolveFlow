from operator import add
from typing import Annotated, Literal, TypedDict

from langgraph.graph import StateGraph, START, EBD
from langgraph.types import Command, Send, Interrupt

def merge_dicts(left: dict | None, right: dict | None ) -> dict:
    return {** (left or {}), ** (right or {})}

#messages, user context, modality -> action or information seeking, skills, enabled tools, plans, stage index, step outputs, status, error
class AgentState(TypedDict, total = False):
      messages : Annotated[list, add]
      user_ctx: dict
      modality: Literal["information_seeking", "action_seeking"]
      skills : list[dict]
      enabled_tools: list[str]
      plan: dict
      stage_idx: int
      step_outputs: Annotated[dict, merge_dicts]
      errors: Annotated[list, add]
      status: str

# Supervisor is a pure router over status.
# It is a deterministic code with no LLM decideing what is next

Route = Literal["triage", "knowledge", "reasoner", "approval", "executor", "respond"]

def supervisor(state: AgentState) -> Command[Route]:
    s = state.get("status")
    if s is None:                  return Command(goto="triage")
    if s == "triaged":             return Command(goto="knowledge")
    if s == "knowledge_done":
        return Command(goto="reasoner" if state["modality"] == "action" else "respond")
    if s == "planned":
        return Command(goto="approval" if plan_has_writes(state["plan"]) else "executor")
    if s == "approved":            return Command(goto="executor")
    if s == "stage_done":
        more = state["stage_idx"] < len(state["plan"]["stages"])
        return Command(goto="executor" if more else "respond")
    # declined, needs_clarification, failed, done
    return Command(goto="respond")

#Specialist: each of them does one job and writes one slice of state
def triage(state: AgentState) -> dict:
    modality = classify_intent(state["messages"][-1]["content"])
    return {"modality": "modality", "status": "triaged"}

# knowledge returns skills, enabled tools, errors, status
def knowledge(state: AgentState) -> dict:
    result = retrieve(
        query=state["messages"][-1]["content"],
        user=state["user_ctx"],
    )
    skills = select_documents(state["messages"], result.chunks)   # LLM picks; code validates the ids
    enabled = sorted({t for s in skills for t in s["tools"]})     # retrieval narrows the tool menu
    note = [] if not result.degraded else [f"retrieval degraded: {result.degraded}"]
    return {"skills": skills, "enabled_tools": enabled, "errors": note, "status": "knowledge_done"}

def reasoner(state:AgentState) -> dict:
    missing = find_missing_requirements(state["messages"], state["skills"])
    if missing:                                   # consultative loop: ask, do not guess
        return {"messages": [ask_user(missing)], "status": "needs_clarification"}
    plan = compile_plan(state["skills"], state["enabled_tools"])
    validate_plan(plan, state["enabled_tools"])
    return {"plan": plan, stage_idx:0, "status":planned }

def approval(state: AgentState) -> Command[Literal['supervisor']]:
    decision = Interrupt({"type": "plan_approval", "plan": render_plan(state["plan"])})
    if decision.get("approved"):
        return Command(update={"status": "approved"}, goto="supervisor")
    return Command(update={"status": "declined"}, goto="supervisor")