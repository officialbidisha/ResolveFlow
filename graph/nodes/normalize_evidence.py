"""Day 1. Reads: raw evidence from fetch_evidence's output.
Writes: evidence (IssueEvidence).

Turn raw GitHub API JSON into a validated IssueEvidence. This is the one
place allowed to know the shape of GitHub's API responses — everything
after this node only ever sees the normalized schema.
"""

from __future__ import annotations

from graph.state import GraphState


def normalize_evidence(state: GraphState) -> dict:
    raise NotImplementedError
