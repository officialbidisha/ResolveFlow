"""Normalized shape of everything we know about a GitHub issue before diagnosis.

This is the contract between evidence-fetching (tools/github_client.py) and
every downstream graph node — nothing past `normalize_evidence` should ever
touch a raw GitHub API response again.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CheckRun(BaseModel):
    name: str
    conclusion: str | None  # "success" | "failure" | "neutral" | None (still running)


class LinkedPR(BaseModel):
    number: int
    title: str
    state: str
    merged: bool


class IssueEvidence(BaseModel):
    repo: str
    issue_number: int
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    linked_prs: list[LinkedPR] = Field(default_factory=list)
    check_runs: list[CheckRun] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    owner_hint: str | None = None

    @property
    def has_failing_ci(self) -> bool:
        return any(c.conclusion == "failure" for c in self.check_runs)

    @property
    def is_information_sparse(self) -> bool:
        return len(self.body.strip()) < 40 and not self.comments
