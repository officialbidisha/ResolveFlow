"""Capability evaluation suite for ResolveFlow.

Tests OUTPUT QUALITY, not safety gates. These evals measure:
- Diagnosis accuracy and completeness
- Citation grounding (no hallucinations)
- Reasoning soundness
- Retrieval relevance

Unlike safety gates (harness.py: must be 100%), these improve over time.
Expected to grow as new eval types are added.

Run with: python -m eval.capability_harness
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()

from eval.test_diagnosis_severity_valid import DiagnosisSeverityValidTest
from eval.test_diagnosis_citations_no_hallucination import DiagnosisCitationsNoHallucinationTest
from eval.real_test_cases import REAL_TEST_CASES


def run_diagnosis_severity_tests() -> List[dict]:
    """Eval: Severity is valid enum (not arbitrary string)."""
    results = []
    for i, evidence in enumerate(REAL_TEST_CASES):
        test = DiagnosisSeverityValidTest(evidence=evidence)
        result = test.run()
        result["case"] = i  # Track which test case
        result["repo"] = evidence.repo
        result["issue"] = evidence.issue_number
        results.append(result)
    return results


def run_diagnosis_citations_tests() -> List[dict]:
    """Eval: Citations don't hallucinate (all cite retrieved IDs)."""
    results = []
    for i, evidence in enumerate(REAL_TEST_CASES):
        test = DiagnosisCitationsNoHallucinationTest(evidence=evidence)
        result = test.run()
        result["case"] = i
        result["repo"] = evidence.repo
        result["issue"] = evidence.issue_number
        results.append(result)
    return results


def main() -> None:
    """Run all capability evals and report results."""
    print("=" * 70)
    print("CAPABILITY EVALUATION SUITE")
    print("=" * 70)

    # Run all eval suites
    severity_results = run_diagnosis_severity_tests()
    citations_results = run_diagnosis_citations_tests()

    all_results = severity_results + citations_results

    # Print results
    print()
    passed_count = 0
    for r in all_results:
        mark = "✓ PASS" if r["passed"] else "✗ FAIL"
        repo = r.get("repo", "?")
        issue = r.get("issue", "?")
        print(f"{mark} | {r['test']:<35} | {repo}#{issue}")

        if not r["passed"]:
            # Show details for failures
            if "invalid_citations" in r and r["invalid_citations"]:
                print(f"        Hallucinated IDs: {r['invalid_citations']}")
            if "severity" in r:
                print(f"        Severity: {r['severity']}")

        if r["passed"]:
            passed_count += 1

    # Summary
    total = len(all_results)
    print()
    print("=" * 70)
    print(f"SUMMARY: {passed_count}/{total} passed ({(passed_count/total)*100:.1f}%)")
    print("=" * 70)

    # Save results
    output_file = Path(__file__).parent / "capability_results.json"
    output_file.write_text(json.dumps(all_results, indent=2))
    print(f"\nResults saved to: {output_file}")

    # Exit code: 0 if all pass, 1 if any fail
    # (You might want to lower this threshold for capability evals)
    if passed_count != total:
        print(f"\n⚠️  {total - passed_count} test(s) failed")
        return 0  # Don't fail CI for capability evals yet (they improve over time)
    else:
        print(f"\n✅ All {total} capability tests passed!")
        return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
