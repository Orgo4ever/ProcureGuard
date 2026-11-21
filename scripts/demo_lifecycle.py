"""Reproducible fictional case: failed verification -> corrective edit -> resolution.

Does not alter tracked inputs. Creates a local, synthetic SQLite case database
and an auditable report in the provided output directory.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from procureguard.cases import (
    assign, connect, export_cases, history, investigate,
    list_cases, propose, sync_scan, verify,
)
from procureguard.engine import ROOT

DEFAULT_DATA = ROOT / "data" / "synthetic"
RULES = ROOT / "config" / "quality_rules.csv"


def update_amount(path: Path, source_row_id: str, value: str) -> None:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = reader.fieldnames
    matched = 0
    for row in rows:
        if row["source_row_id"] == source_row_id:
            row["reported_value"] = value
            matched += 1
    if matched != 1:
        raise ValueError(f"Expected exactly one synthetic source row: {source_row_id}")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run_demo(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    input_dir = output / "corrected_synthetic_input"
    if input_dir.exists():
        shutil.rmtree(input_dir)
    shutil.copytree(DEFAULT_DATA, input_dir)
    db_path = output / "governance.sqlite"
    if db_path.exists():
        db_path.unlink()

    with connect(db_path) as db:
        original = sync_scan(db, input_dir, RULES)
        case = next(
            x for x in list_cases(db)
            if x["rule_id"] == "DQ-05" and x["source_row_id"] == "CON-0003"
        )
        case_id = case["issue_id"]
        assign(db, case_id, "Fictional Data Steward", "Demo Team Lead")
        investigate(
            db, case_id, "Fictional Data Steward",
            "Simulated upstream feed omitted a reportable contract amount",
        )
        propose(
            db, case_id, "Fictional Data Steward",
            "Reconcile the fictional contract record and replace the missing value",
        )

        # A documented action alone does not close an issue.
        failed = verify(db, case_id, "Fictional Independent Reviewer", input_dir, RULES)
        if failed["verified"]:
            raise AssertionError("An unchanged source must not pass verification")

        # Correct only the copied synthetic fixture, not version-controlled input.
        update_amount(input_dir / "contracts.csv", "CON-0003", "6500")
        passed = verify(db, case_id, "Fictional Independent Reviewer", input_dir, RULES)
        if not passed["verified"]:
            raise AssertionError(f"Corrected synthetic input should verify: {passed}")

        after = sync_scan(db, input_dir, RULES)
        totals = export_cases(db, output)
        events = history(db, case_id)

    result = {
        "disclaimer": "Fictional case study; all owners, records and findings are synthetic",
        "case_id": case_id,
        "before_scan": original,
        "initial_verification": failed,
        "post_correction_verification": passed,
        "after_scan": after,
        "case_register": totals,
        "audit_event_actions": [x["action"] for x in events],
        "note": "The data is repaired in an isolated copy; no real-world corrective action occurred",
    }
    (output / "demo_lifecycle.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic ProcureGuard issue lifecycle")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "lifecycle_demo")
    args = parser.parse_args()
    result = run_demo(args.output)
    print(json.dumps(result, indent=2))
    print(f"\nDemo outputs: {args.output.resolve()}")


if __name__ == "__main__":
    main()
