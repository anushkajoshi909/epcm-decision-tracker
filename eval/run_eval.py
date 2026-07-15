"""Minimal evaluation harness.

Not academic benchmarking - just enough to show the prototype was actually
tested, not only demonstrated. Hits the REAL running FastAPI service over
HTTP (this is also a good example of a plain REST client, as opposed to
n8n's HTTP Request node doing the same thing).

Usage:
    uvicorn app.main:app --reload &      # from the project root, in another shell
    python eval/run_eval.py
"""
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
TEST_CASES_PATH = Path(__file__).parent / "test_cases.json"


def norm(value):
    if value is None:
        return None
    return str(value).strip().lower()


def run_case(case: dict) -> dict:
    resp = requests.post(
        f"{BASE_URL}/analyse-protocol",
        json={"project_id": case["project_id"], "text": case["text"]},
        timeout=30,
    )
    resp.raise_for_status()
    actual = resp.json()

    expected = case["expected"]
    first_action = actual["actions"][0] if actual["actions"] else {}
    issue_types = {i["type"] for i in actual["issues"]}

    checks = {
        "decision_detected": (len(actual["decisions"]) > 0) == expected["decision_detected"],
        "action_detected": (len(actual["actions"]) > 0) == expected["action_detected"],
        "owner": norm(first_action.get("owner")) == norm(expected["owner"]),
        "deadline": norm(first_action.get("deadline")) == norm(expected["deadline"]),
        "affected_deliverable": norm(first_action.get("affected_deliverable"))
        == norm(expected["affected_deliverable"]),
        "missing_owner": ("missing_owner" in issue_types) == expected["missing_owner"],
        "unresolved_dependency": ("unresolved_dependency" in issue_types)
        == expected["unresolved_dependency"],
        "requires_attention": actual["requires_attention"] == expected["requires_attention"],
    }
    return {"id": case["id"], "checks": checks, "actual": actual}


def main():
    cases = json.loads(TEST_CASES_PATH.read_text())
    results = []
    for case in cases:
        try:
            results.append(run_case(case))
        except Exception as exc:  # noqa: BLE001 - eval script, want to keep going
            print(f"[{case['id']}] FAILED TO RUN: {exc}")
            continue

    print("\n=== Per-case results ===")
    field_totals = {}
    for r in results:
        passed = sum(r["checks"].values())
        total = len(r["checks"])
        print(f"\n{r['id']}: {passed}/{total} fields correct")
        for field, ok in r["checks"].items():
            field_totals.setdefault(field, []).append(ok)
            mark = "OK" if ok else "MISMATCH"
            print(f"  [{mark:8}] {field}")

    print("\n=== Aggregate accuracy per field ===")
    for field, oks in field_totals.items():
        accuracy = sum(oks) / len(oks)
        print(f"  {field:22} {accuracy:.0%}  ({sum(oks)}/{len(oks)})")

    # requires_attention treated as a binary classifier -> precision/recall
    tp = fp = fn = tn = 0
    cases_by_id = {c["id"]: c for c in cases}
    for r in results:
        expected_attention = cases_by_id[r["id"]]["expected"]["requires_attention"]
        actual_attention = r["actual"]["requires_attention"]
        if expected_attention and actual_attention:
            tp += 1
        elif not expected_attention and actual_attention:
            fp += 1
        elif expected_attention and not actual_attention:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    print("\n=== requires_attention as binary classifier ===")
    print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  precision={precision:.0%}  recall={recall:.0%}")


if __name__ == "__main__":
    main()
