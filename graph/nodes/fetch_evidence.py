"""Day 1. Reads: issue_url. Writes: raw_evidence — hands raw API
responses to normalize_evidence rather than building IssueEvidence itself,
so a GitHub API shape change only touches one function.

Parse `issue_url` -> (repo, issue_number), call tools.github_client.get_issue
+ get_comments + get_codeowners. Return the raw dicts under raw_evidence;
do not construct IssueEvidence here.

PR-linked CI check-run detection is intentionally out of scope for this
pass (see README limitations) — check_runs is always []. The deterministic
classification branch is still exercised via synthetic fixtures in
tests/test_classify.py rather than requiring a live linked-PR lookup.
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

    raw_evidence = {
        "repo": repo,
        "issue_number": issue_number,
        "issue": github_client.get_issue(repo, issue_number),
        "comments": github_client.get_comments(repo, issue_number),
        "codeowners": github_client.get_codeowners(repo),
        "check_runs": [],
    }

    return {"raw_evidence": raw_evidence}
