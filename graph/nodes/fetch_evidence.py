"""Day 1. Reads: issue_url. Writes: raw_evidence — hands raw API
responses to normalize_evidence rather than building IssueEvidence itself,
so a GitHub API shape change only touches one function.

Parse `issue_url` -> (repo, issue_number), call tools.github_client.get_issue
+ get_comments + get_codeowners. Return the raw dicts under raw_evidence;
do not construct IssueEvidence here.

CI check runs require a commit SHA, which only exists on a linked PR, so
get_linked_pull_request is tried first; if the issue has no linked PR yet,
check_runs stays []. The deterministic classification branch is still
exercised via synthetic fixtures in tests/test_classify.py rather than
requiring a live linked-PR lookup.
"""

from __future__ import annotations

import re

from graph.state import GraphState
from tools import github_client

_ISSUE_URL_RE = re.compile(r"github\.com/([^/]+/[^/]+)/issues/(\d+)")


def fetch_evidence(state: GraphState) -> dict:
    match = _ISSUE_URL_RE.search(state["issue_url"])
    if not match:
        raise ValueError(f"could not parse issue URL: {state['issue_url']!r}")
    repo, issue_number = match.group(1), int(match.group(2))
    token = state.get("github_token")

    linked_pr = github_client.get_linked_pull_request(repo, issue_number, token=token)
    check_runs = (
        github_client.get_check_runs(repo, linked_pr["head"]["sha"], token=token) if linked_pr else []
    )

    raw_evidence = {
        "repo": repo,
        "issue_number": issue_number,
        "issue": github_client.get_issue(repo, issue_number, token=token),
        "comments": github_client.get_comments(repo, issue_number, token=token),
        "codeowners": github_client.get_codeowners(repo, token=token),
        "check_runs": check_runs,
    }

    return {"raw_evidence": raw_evidence}
