"""Evaluation runner for the Triage endpoint."""
import json
from pathlib import Path
from fastapi.testclient import TestClient

import main

CASES_PATH = Path("evals/cases.json")


def run_eval():
    client = TestClient(main.app)
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    correct = 0
    total = len(cases)
    failures = []

    print(f"Running evaluation on {total} cases...\n")

    for case in cases:
        resp = client.post("/triage", json={"text": case["input"]})
        if resp.status_code != 200:
            failures.append({
                "id": case["id"],
                "input": case["input"],
                "expected": case["expected_category"],
                "actual": f"HTTP {resp.status_code}: {resp.text}"
            })
            continue

        result = resp.json()
        category = result.get("category")
        if category == case["expected_category"]:
            correct += 1
            print(f"✓ Case {case['id']}: '{case['input'][:40]}...' -> {category}")
        else:
            failures.append({
                "id": case["id"],
                "input": case["input"],
                "expected": case["expected_category"],
                "actual": category,
                "confidence": result.get("confidence"),
                "reason": result.get("reason")
            })
            print(f"✗ Case {case['id']}: expected {case['expected_category']}, got {category}")

    score_pct = (correct / total) * 100
    print("\n--- Evaluation Summary ---")
    print(f"Score: {correct}/{total} ({score_pct:.1f}%)")
    if failures:
        print("\nFailed cases:")
        for f in failures:
            print(f"- Case {f['id']}: {f}")

    return correct, total, failures


if __name__ == "__main__":
    run_eval()
