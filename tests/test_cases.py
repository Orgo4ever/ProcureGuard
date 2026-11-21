"""Governance lifecycle regression tests, entirely on synthetic records."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from procureguard.cases import (
    GovernanceError, assign, connect, export_cases, get_case, history,
    investigate, list_cases, propose, sync_scan, verify,
)
from procureguard.engine import ROOT, evaluate, read_rules, read_tables

SOURCE = ROOT / "data" / "synthetic"
RULES = ROOT / "config" / "quality_rules.csv"


class CaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input_dir = self.root / "input"
        shutil.copytree(SOURCE, self.input_dir)
        self.database = self.root / "governance.sqlite"
        self.db = connect(self.database)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def scan(self):
        return sync_scan(self.db, self.input_dir, RULES)

    def find_case(self, rule="DQ-05", source_id="CON-0003"):
        return next(
            x for x in list_cases(self.db)
            if x["rule_id"] == rule and x["source_row_id"] == source_id
        )

    def change_contract_amount(self, source_id, new_amount):
        path = self.input_dir / "contracts.csv"
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fields = list(reader.fieldnames)
        for row in rows:
            if row["source_row_id"] == source_id:
                row["reported_value"] = new_amount
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def prepare_case(self):
        self.scan()
        issue = self.find_case()
        case_id = issue["issue_id"]
        assign(self.db, case_id, "Fictional Steward", "Fictional Supervisor")
        investigate(self.db, case_id, "Fictional Steward",
                    "Demonstration source feed omitted an amount")
        propose(self.db, case_id, "Fictional Steward",
                "Reconcile and correct the synthetic contract amount")
        return case_id

    def test_initial_import_creates_22_cases_and_22_events(self):
        outcome = self.scan()
        self.assertEqual(outcome["rows_scanned"], 38)
        self.assertEqual(outcome["issues_found"], 22)
        self.assertEqual(outcome["cases_created"], 22)
        cases = list_cases(self.db)
        self.assertEqual(len(cases), 22)
        self.assertTrue(all(case["status"] == "Open" for case in cases))
        total_events = self.db.execute("SELECT COUNT(*) FROM case_events").fetchone()[0]
        self.assertEqual(total_events, 22)

    def test_rescan_is_idempotent_for_open_case_count(self):
        first = self.scan()
        second = self.scan()
        self.assertEqual(second["cases_created"], 0)
        self.assertEqual(second["cases_reopened"], 0)
        self.assertEqual(second["existing_cases_observed"], 22)
        self.assertEqual(len(list_cases(self.db)), 22)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM scan_findings").fetchone()[0], 44)
        self.assertEqual(first["input_sha256"], second["input_sha256"])

    def test_assign_investigate_propose_require_valid_order(self):
        self.scan()
        issue = self.find_case()
        issue_id = issue["issue_id"]
        with self.assertRaises(GovernanceError):
            investigate(self.db, issue_id, "Reviewer", "Unverified upstream error")
        with self.assertRaises(GovernanceError):
            propose(self.db, issue_id, "Reviewer", "Check source")
        with self.assertRaises(GovernanceError):
            assign(self.db, issue_id, " ", "Reviewer")
        assign(self.db, issue_id, "Demo Owner", "Reviewer")
        value = investigate(self.db, issue_id, "Reviewer", "Simulated missing feed field")
        self.assertEqual(value["status"], "Investigating")
        value = propose(self.db, issue_id, "Reviewer", "Fix data in synthetic input")
        self.assertEqual(value["status"], "Pending Verification")

    def test_failed_verification_is_retained_and_audited(self):
        issue_id = self.prepare_case()
        outcome = verify(self.db, issue_id, "Demo Auditor", self.input_dir, RULES)
        self.assertFalse(outcome["verified"])
        self.assertEqual(get_case(self.db, issue_id)["status"], "Pending Verification")
        self.assertEqual(history(self.db, issue_id)[-1]["action"], "verification_failed")

    def test_successful_verification_and_export(self):
        issue_id = self.prepare_case()
        self.change_contract_amount("CON-0003", "6500")
        outcome = verify(self.db, issue_id, "Demo Independent Checker", self.input_dir, RULES)
        self.assertTrue(outcome["verified"])
        self.assertEqual(outcome["status"], "Resolved")
        case = get_case(self.db, issue_id)
        self.assertTrue(case["resolved_at"])
        log = history(self.db, issue_id)
        self.assertEqual(
            [e["action"] for e in log],
            ["detected", "assigned", "investigated",
             "submitted_for_verification", "verified_resolved"],
        )
        evidence = json.loads(log[-1]["evidence_json"])
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["source_row_id"], "CON-0003")
        status = export_cases(self.db, self.root / "export")
        self.assertEqual(status["cases_by_status"]["Resolved"], 1)
        self.assertEqual(status["total_cases"], 22)
        self.assertTrue((self.root / "export" / "cases.csv").exists())
        self.assertTrue((self.root / "export" / "audit_events.csv").exists())
        self.assertEqual(json.loads(
            (self.root / "export" / "case_summary.json").read_text()
        )["total_cases"], 22)

    def test_new_scan_does_not_auto_close_absent_issues(self):
        self.scan()
        issue_id = self.find_case()["issue_id"]
        self.change_contract_amount("CON-0003", "6500")
        self.scan()
        self.assertEqual(get_case(self.db, issue_id)["status"], "Open")
        self.assertEqual(len(list_cases(self.db)), 22)

    def test_missing_source_record_prevents_verification(self):
        issue_id = self.prepare_case()
        path = self.input_dir / "contracts.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = [r for r in reader if r["source_row_id"] != "CON-0003"]
            headers = reader.fieldnames
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        outcome = verify(self.db, issue_id, "Demo Reviewer", self.input_dir, RULES)
        self.assertFalse(outcome["verified"])
        self.assertIn("missing", outcome["reason"])
        self.assertEqual(get_case(self.db, issue_id)["status"], "Pending Verification")

    def test_violations_reappear_as_reopened_and_clear_old_action(self):
        issue_id = self.prepare_case()
        self.change_contract_amount("CON-0003", "6500")
        self.assertTrue(verify(self.db, issue_id, "Demo Auditor", self.input_dir, RULES)["verified"])
        corrected_scan = self.scan()
        self.assertEqual(corrected_scan["cases_reopened"], 0)
        self.change_contract_amount("CON-0003", "")
        reintroduced = self.scan()
        self.assertEqual(reintroduced["cases_reopened"], 1)
        issue = get_case(self.db, issue_id)
        self.assertEqual(issue["status"], "Reopened")
        self.assertIsNone(issue["root_cause"])
        self.assertIsNone(issue["corrective_action"])
        self.assertIsNone(issue["resolved_at"])
        self.assertEqual(history(self.db, issue_id)[-1]["action"], "reopened")

    def test_row_order_change_does_not_change_case_ids(self):
        self.scan()
        before = {x["issue_id"] for x in list_cases(self.db)}
        path = self.input_dir / "suppliers.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(list(reversed(rows)))
        self.scan()
        after = {x["issue_id"] for x in list_cases(self.db)}
        self.assertEqual(before, after)

    def test_missing_source_row_id_is_rejected_by_governance(self):
        path = self.input_dir / "suppliers.csv"
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fields = [s for s in reader.fieldnames if s != "source_row_id"]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaisesRegex(GovernanceError, "source_row_id"):
            self.scan()

    def test_duplicate_source_row_id_is_rejected(self):
        path = self.input_dir / "contracts.csv"
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fields = reader.fieldnames
        rows[1]["source_row_id"] = rows[0]["source_row_id"]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaisesRegex(ValueError, "duplicate source_row_id"):
            self.scan()

    def test_resolved_case_cannot_be_manually_mutated(self):
        issue_id = self.prepare_case()
        self.change_contract_amount("CON-0003", "6500")
        verify(self.db, issue_id, "Demo Auditor", self.input_dir, RULES)
        with self.assertRaises(GovernanceError):
            assign(self.db, issue_id, "Someone Else", "Demo Auditor")
        with self.assertRaises(GovernanceError):
            investigate(self.db, issue_id, "Demo Auditor", "New cause")
        with self.assertRaises(GovernanceError):
            propose(self.db, issue_id, "Demo Auditor", "New action")

    def test_nonexistent_case_is_rejected(self):
        self.scan()
        with self.assertRaisesRegex(GovernanceError, "Unknown case"):
            get_case(self.db, "PG-DOES-NOT-EXIST")


if __name__ == "__main__":
    unittest.main()
