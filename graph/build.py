"""Assembles the StateGraph: wires nodes + conditional edges together.

    START -> fetch_evidence -> normalize_evidence -> classify
                                                        |
                        (conditional on state["classification"])
                    /                 |                    \\
          deterministic       ai_investigation          human_review
                |                     |                       |
        await_approval        generate_diagnosis             END
                |                     |
               ...          independent_review
                                      |
                    (conditional on review_result.outcome)
                    /                |                  \\
               approve        escalate_to_human   reject_retrieve_more
                  |                   |                    |
          await_approval             END          generate_diagnosis (loop,
                  |                                     not built)
        (conditional on state["approved"])
              /        \\
          execute*      END
              |
             END

* execute is the only node with side effects, and only runs after
  await_approval's interrupt() resumes with approved=True — both paths
  (deterministic and ai_investigation-approved) go through the same gate,
  never straight to execute. See graph/nodes/await_approval.py and
  graph/nodes/execute.py.

Requires a checkpointer because interrupt() needs somewhere to persist
state across the pause — callers must invoke with a thread_id in config,
and resume with Command(resume=...) using that same thread_id.

`compiled_graph` below (MemorySaver, in-process only) is a convenience
export for local/ad-hoc use (a REPL, a quick script, tests) — nothing
resume-worthy across separate requests should rely on it. `graph`
(uncompiled) is exported too, so a caller needing a persistent
checkpointer across process restarts — app/main.py's FastAPI backend,
via AsyncPostgresSaver — can compile it themselves instead. The deployed app
(frontend on Vercel, backend on Render) is the only live surface; there
is no in-process UI anymore.
"""

from dotenv import load_dotenv
load_dotenv()
from graph.nodes.fetch_evidence import fetch_evidence
from graph.nodes.normalize_evidence import normalize_evidence
from graph.nodes.classify import classify
from graph.nodes.generate_diagnosis import generate_diagnosis
from graph.nodes.independent_review import independent_review
from graph.nodes.await_approval import await_approval
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from graph.state import GraphState
from graph.nodes.execute import execute
from graph.serde import get_serde


graph = StateGraph(GraphState)
graph.add_node("fetch_evidence",fetch_evidence)
graph.add_node("normalize_evidence",normalize_evidence)
graph.add_node("classify",classify)
graph.set_entry_point("fetch_evidence")
graph.add_edge("fetch_evidence", "normalize_evidence")
graph.add_edge("normalize_evidence", "classify")

def should_route_to(state: GraphState) -> str :
    if state["classification"] == "deterministic":
            return "deterministic"
    elif state["classification"]== "ai_investigation":
            return "ai_investigation"
    else:
           return "human_review"

## add conditional edges
graph.add_conditional_edges("classify", should_route_to, {
       "deterministic": "await_approval", "ai_investigation": "generate_diagnosis", "human_review": END
})

graph.add_node("await_approval", await_approval)
graph.add_node("execute", execute)
graph.add_edge("execute", END)


def should_execute(state: GraphState) -> str:
    return "execute" if state.get("approved") else "rejected"


graph.add_conditional_edges("await_approval", should_execute, {
    "execute": "execute",
    "rejected": END,
})

graph.add_node("generate_diagnosis", generate_diagnosis)
graph.add_node("independent_review", independent_review)
graph.add_edge("generate_diagnosis", "independent_review")


def should_route_review(state: GraphState) -> str:
    return state["review_result"].outcome


# "reject_retrieve_more" is the optional loop-back-to-generate_diagnosis
# stretch goal from independent_review.py's own docstring — not built;
# independent_review never actually returns that outcome today, only
# "approve" or "escalate_to_human".
graph.add_conditional_edges("independent_review", should_route_review, {
       "approve": "await_approval", "escalate_to_human": END, "reject_retrieve_more": END
})

compiled_graph = graph.compile(checkpointer=MemorySaver(serde=get_serde()))

