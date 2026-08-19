"""Assembles the StateGraph: wires nodes + conditional edges together.

Not implemented yet — needs langgraph installed first (see README "Setup").
Shape to build toward:

    START -> fetch_evidence -> normalize_evidence -> classify
                                                        |
                        (conditional on state["classification"])
                    /                 |                    \\
          deterministic       ai_investigation          human_review
                |                     |                       |
            execute*          generate_diagnosis            END
                |                     |
               END          independent_review
                                      |
                    (conditional on review_result.outcome)
                    /                |                  \\
               approve        escalate_to_human   reject_retrieve_more
                  |                   |                    |
              [interrupt]           END          generate_diagnosis (loop)
                  |
               execute*
                  |
                 END

* execute is the only node with side effects, and only runs after either
  the deterministic-path skips review entirely (still requires `approved`,
  see graph/nodes/execute.py) or the interrupt() resumes with approved=True.
"""

from dotenv import load_dotenv
load_dotenv()
from graph.nodes.fetch_evidence import fetch_evidence
from graph.nodes.normalize_evidence import normalize_evidence
from graph.nodes.classify import classify
from langgraph.graph import StateGraph, END
from graph.state import GraphState
from graph.nodes.execute import execute


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
       "deterministic": "execute", "ai_investigation": END, "human_review": END
})

graph.add_node("execute", execute)
graph.add_edge("execute",END)
compiled_graph = graph.compile()

