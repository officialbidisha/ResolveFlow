"""Day 1. Reads: raw evidence from fetch_evidence's output.
Writes: evidence (IssueEvidence).

Turn raw GitHub API JSON into a validated IssueEvidence. This is the one
place allowed to know the shape of GitHub's API responses — everything
after this node only ever sees the normalized schema.
"""

from __future__ import annotations

from graph.state import GraphState
from schemas.evidence import CheckRun, IssueEvidence


def normalize_evidence(state: GraphState) -> dict:
    raw = state["raw_evidence"]
    issue = raw["issue"]

    evidence = IssueEvidence(
        repo=raw["repo"],
        issue_number=raw["issue_number"],
        title=issue["title"],
        body=issue["body"] or "",
        labels=[label["name"] for label in issue["labels"]],
        comments=[comment["body"] for comment in raw["comments"]],
        linked_prs=[],
        check_runs=[CheckRun(**check_run) for check_run in raw["check_runs"]],
        files_touched=[],
        owner_hint=_extract_owner_hint(raw["codeowners"]),
    )

    return {"evidence": evidence}


def _extract_owner_hint(codeowners_text:str|None) -> str|None:
    if codeowners_text == None or len(codeowners_text)==0 or codeowners_text== '':
        return None
    else:
        arr = codeowners_text.split("\n")
        for li in arr:
            if (li.strip().startswith("#") or li==""):
                continue
            else:
                return li.split()[-1]
        return None