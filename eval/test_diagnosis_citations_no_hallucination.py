"""Capability eval: Ensure citations don't hallucinate.

Every citation ID in diagnosis.citations must exist in the retrieved_ids list.
If the LLM cites a non-existent ID, it's hallucinating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from schemas.evidence import IssueEvidence
from graph.nodes.generate_diagnosis import generate_diagnosis


@dataclass
class DiagnosisCitationsNoHallucinationTest:
    """Ensure all citations match retrieved snippet IDs (no hallucinations)."""
    name: str = "diagnosis_citations_no_hallucination"
    evidence: Optional[IssueEvidence] = None

    def run(self) -> Dict:
        """
        Check: Are all diagnosis.citations in retrieved_ids?

        Returns dict with:
        - passed: bool (True if no hallucinated citations)
        - diagnosis_citations: list of cited IDs
        - retrieved_ids: list of available IDs
        - invalid_citations: list of IDs that don't exist (hallucinations)
        """
        # Step 1: Call generate_diagnosis
        state = {"evidence": self.evidence}
        res = generate_diagnosis(state)

        # Step 2: Extract what we need
        diagnosis = res["diagnosis"]
        retrieved_ids = res["retrieved_ids"]

        # Step 3: Check - are all citations in retrieved_ids?
        invalid_citations = [
            cid for cid in diagnosis.citations
            if cid not in retrieved_ids
        ]

        # Step 4: Return result
        return {
            "test": self.name,
            "passed": len(invalid_citations) == 0,
            "diagnosis_citations": diagnosis.citations,
            "retrieved_ids": retrieved_ids,
            "invalid_citations": invalid_citations,
        }


if __name__ == "__main__":
    test = DiagnosisCitationsNoHallucinationTest(
        evidence=IssueEvidence(
            repo="test/repo",
            issue_number=1,
            title="Build broken",
            body="Failing on main"
        )
    )
    result = test.run()
    print(result)
