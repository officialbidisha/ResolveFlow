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
