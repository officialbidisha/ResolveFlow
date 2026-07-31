from pydantic import BaseModel


class IssueEvidence(BaseModel):
    issue_title: str
    issue_body: str