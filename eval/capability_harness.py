"""Capability evaluation suite for ResolveFlow.

Tests OUTPUT QUALITY, not safety gates. These evals measure:
- Diagnosis accuracy and completeness
- Citation grounding (no hallucinations)
- Reasoning soundness
- Retrieval relevance

Unlike safety gates (harness.py: must be 100%), these improve over time,
so the bar is a pass-rate threshold rather than 100%: CAPABILITY_PASS_THRESHOLD
(default 0.8). Each case is graded by code (valid severity enum, citations
that exist in the retrieved set) against a real model's output.

Exit codes:
  0  evaluated, pass rate >= threshold
  1  evaluated, pass rate below threshold (or a case crashed)
  2  UNEVALUATED: provider credentials missing or no test cases. This is
     deliberately not 0, so a run that never called the model can't look
     like a pass.

Run with: uv run python -m eval.capability_harness
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable, List

from dotenv import load_dotenv

load_dotenv()

from eval.real_test_cases import REAL_TEST_CASES

PASS_THRESHOLD = float(os.environ.get("CAPABILITY_PASS_THRESHOLD", "0.8"))
REQUIRED_ENV = ("OPENAI_API_KEY", "PINECONE_API_KEY")
EXIT_OK, EXIT_BELOW_THRESHOLD, EXIT_UNEVALUATED = 0, 1, 2


def _run_case(name: str, run: Callable[[], dict]) -> dict:
    """A case that raises is a failed case, not a crashed suite."""
    try:
        return run()
    except Exception as exc:  # noqa: BLE001 -- recorded as a failure with its error
        return {"test": name, "passed": False, "error": f"{type(exc).__name__}: {exc}"}


def run_diagnosis_severity_tests() -> List[dict]:
    """Eval: Severity is valid enum (not arbitrary string)."""
    from eval.test_diagnosis_severity_valid import DiagnosisSeverityValidTest

    results = []
    for i, evidence in enumerate(REAL_TEST_CASES):
        test = DiagnosisSeverityValidTest(evidence=evidence)
        result = _run_case(test.name, test.run)
        result["case"] = i  # Track which test case
        result["repo"] = evidence.repo
        result["issue"] = evidence.issue_number
        results.append(result)
    return results


def run_diagnosis_citations_tests() -> List[dict]:
    """Eval: Citations don't hallucinate (all cite retrieved IDs)."""
    from eval.test_diagnosis_citations_no_hallucination import DiagnosisCitationsNoHallucinationTest

    results = []
    for i, evidence in enumerate(REAL_TEST_CASES):
        test = DiagnosisCitationsNoHallucinationTest(evidence=evidence)
        result = _run_case(test.name, test.run)
        result["case"] = i
        result["repo"] = evidence.repo
        result["issue"] = evidence.issue_number
        results.append(result)
    return results


def main() -> int:
    """Run all capability evals and report results. Returns the exit code."""
    print("=" * 70)
    print("CAPABILITY EVALUATION SUITE")
    print("=" * 70)

    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing or not REAL_TEST_CASES:
        reason = f"missing {', '.join(missing)}" if missing else "no test cases in eval/real_test_cases.py"
        print(f"\nUNEVALUATED: {reason}. No model was called; this is not a pass.")
        return EXIT_UNEVALUATED

    all_results = run_diagnosis_severity_tests() + run_diagnosis_citations_tests()

    print()
    passed_count = 0
    for r in all_results:
        mark = "✓ PASS" if r["passed"] else "✗ FAIL"
        print(f"{mark} | {r['test']:<35} | {r.get('repo', '?')}#{r.get('issue', '?')}")
        if not r["passed"]:
            if r.get("error"):
                print(f"        Error: {r['error']}")
            if r.get("invalid_citations"):
                print(f"        Hallucinated IDs: {r['invalid_citations']}")
            if "severity" in r:
                print(f"        Severity: {r['severity']}")
        passed_count += bool(r["passed"])

    total = len(all_results)
    rate = passed_count / total
    print()
    print("=" * 70)
    print(f"SUMMARY: {passed_count}/{total} passed ({rate:.1%}); threshold {PASS_THRESHOLD:.0%}")
    print("=" * 70)

    output_file = Path(__file__).parent / "capability_results.json"
    output_file.write_text(json.dumps(all_results, indent=2))
    print(f"\nResults saved to: {output_file}")

    if rate < PASS_THRESHOLD:
        print(f"\nBELOW THRESHOLD: {rate:.1%} < {PASS_THRESHOLD:.0%}")
        return EXIT_BELOW_THRESHOLD
    print(f"\nAt or above threshold ({rate:.1%} >= {PASS_THRESHOLD:.0%})")
    return EXIT_OK


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
