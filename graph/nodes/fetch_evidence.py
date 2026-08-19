"""Day 1. Reads: issue_url. Writes: nothing directly — hands raw API
responses to normalize_evidence rather than building IssueEvidence itself,
so a GitHub API shape change only touches one function.

Parse `issue_url` -> (repo, issue_number), call tools.github_client.get_issue
+ get_comments, and if the issue references a PR, get_check_runs for its
head SHA. Return the raw dicts; do not construct IssueEvidence here.
"""

from __future__ import annotations

from graph.state import GraphState


def fetch_evidence(state: GraphState) -> dict:
    raise NotImplementedError
