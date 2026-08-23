from dataclasses import dataclass
from typing import Dict, Optional
from schemas.evidence import IssueEvidence
from graph.nodes.generate_diagnosis import generate_diagnosis

@dataclass
class DiagnosisSeverityValidTest:
    """Verify diagnosis.severity is one of the valid options"""
    name: str = "severity_is_valid_enum"
    evidence: Optional[IssueEvidence] = None
    def run(self) -> Dict:
        # Inside run(), you access the object's fields with self.FIELDNAME
        state = {"evidence": self.evidence}
        res = generate_diagnosis(state)
        valid_severities = ["low", "medium", "high"]
        is_valid = res["diagnosis"].severity in valid_severities
        return {
            "test": self.name,
            "passed": is_valid,
            "severity": res["diagnosis"].severity,
            "valid_options": valid_severities
        }
if __name__ == "__main__":
    test = DiagnosisSeverityValidTest(
        evidence=IssueEvidence(
            repo="test/repo",
            issue_number=1,
            title="Build broken",
            body="Test"
        )
    )
    result = test.run()
    print(result)

