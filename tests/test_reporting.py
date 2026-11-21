"""SQLite reporting mart: deterministic tests using only fictional data."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from procureguard.cases import (
    assign, connect, investigate, list_cases, propose, sync_scan, verify,
)
from procureguard.engine import ROOT
from procureguard.reporting import REPORT_VIEWS, export_reporting, prepare_views

DATA = ROOT / "data" / "synthetic"
RULES = ROOT / "config" / "quality_rules.csv"


class ReportingViewsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input = self.root / "synthetic"
        shutil.copytree(DATA, self.input)
        self.db = connect(self.root / "governance.sqlite")
        self.first_scan = sync_scan(self.db, self.input, RULES)
        prepare_views(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def fetchone(self, name):
        return dict(self.db.execute(f"SELECT * FROM {name}").fetchone())

    def repair_missing_value(self):
        path = self.input / "contracts.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        for row in rows:
            if row["source_row_id"] == "CON-0003":
                row["reported_value"] = "6500"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def resolve_example(self):
        issue = next(
            x for x in list_cases(self.db)
            if x["rule_id"] == "DQ-05" and x["source_row_id"] == "CON-0003"
        )
        case_id = issue["issue_id"]
        assign(self.db, case_id, "Demo Steward", "Demo Manager")
        investigate(self.db, case_id, "Demo Steward", "Synthetic feed omitted amount")
        propose(self.db, case_id, "Demo Steward", "Correct copied synthetic source")
        failed = verify(self.db, case_id, "Demo Reviewer", self.input, RULES)
        self.assertFalse(failed["verified"])
        self.repair_missing_value()
        completed = verify(self.db, case_id, "Demo Reviewer", self.input, RULES)
        self.assertTrue(completed["verified"])
        sync_scan(self.db, self.input, RULES)
        return case_id

    def test_all_expected_views_exist(self):
        names = {
            row["name"] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            )
        }
        self.assertEqual(set(REPORT_VIEWS), names)

    def test_current_case_kpis_reconcile_to_22(self):
        kpis = self.fetchone("v_case_kpis")
        self.assertEqual(kpis["total_cases"], 22)
        self.assertEqual(kpis["unresolved_cases"], 22)
        self.assertEqual(kpis["resolved_cases"], 0)
        self.assertEqual(kpis["high_priority_unresolved"], 14)
        self.assertEqual(kpis["unassigned_unresolved_cases"], 22)
        self.assertEqual(kpis["cases_seen_in_latest_scan"], 22)

    def test_rule_counts_match_original_engine(self):
        rule_counts = {
            row["rule_id"]: row["total_cases"]
            for row in self.db.execute("SELECT * FROM v_rule_metrics")
        }
        self.assertEqual(rule_counts, {
            "DQ-01": 3, "DQ-02": 8, "DQ-03": 3,
            "DQ-04": 2, "DQ-05": 2, "DQ-06": 4,
        })
        self.assertEqual(sum(rule_counts.values()), 22)

    def test_owner_workload_tracks_unresolved_not_all_cases(self):
        records = self.db.execute(
            "SELECT * FROM v_owner_workload"
        ).fetchall()
        self.assertEqual(sum(x["unresolved_cases"] for x in records), 22)
        self.assertTrue(all(x["owner_display"] == "Unassigned" for x in records))

    def test_scan_view_uses_observed_quality_not_backlog(self):
        trend = self.fetchone("v_scan_quality_trend")
        self.assertEqual(trend["run_id"], self.first_scan["scan_run_id"])
        self.assertEqual(trend["rows_scanned"], 38)
        self.assertEqual(trend["issues_found"], 22)
        self.assertEqual(trend["affected_rows"], 22)
        self.assertEqual(trend["row_pass_rate_pct"], 42.11)

    def test_one_verified_case_changes_current_kpis(self):
        case_id = self.resolve_example()
        detail = dict(self.db.execute(
            "SELECT * FROM v_case_details WHERE issue_id=?", (case_id,)
        ).fetchone())
        kpis = self.fetchone("v_case_kpis")
        self.assertEqual(detail["is_resolved"], 1)
        self.assertEqual(detail["is_unresolved"], 0)
        self.assertEqual(detail["seen_in_latest_scan"], 0)
        self.assertIsNotNone(detail["resolution_days"])
        self.assertEqual(kpis["total_cases"], 22)
        self.assertEqual(kpis["resolved_cases"], 1)
        self.assertEqual(kpis["unresolved_cases"], 21)
        self.assertEqual(kpis["high_priority_unresolved"], 14)
        self.assertEqual(kpis["unassigned_unresolved_cases"], 21)
        self.assertEqual(kpis["cases_seen_in_latest_scan"], 21)

    def test_scan_trend_distinguishes_two_source_observations(self):
        self.resolve_example()
        trends = [
            dict(r) for r in self.db.execute(
                "SELECT * FROM v_scan_quality_trend ORDER BY run_id"
            )
        ]
        self.assertEqual(len(trends), 2)
        self.assertEqual([x["issues_found"] for x in trends], [22, 21])
        self.assertEqual([x["row_pass_rate_pct"] for x in trends], [42.11, 44.74])

    def test_failed_and_passed_verifications_remain_visible(self):
        case_id = self.resolve_example()
        record = dict(self.db.execute(
            "SELECT * FROM v_verification_metrics WHERE issue_id=?", (case_id,)
        ).fetchone())
        self.assertEqual(record["verification_attempts"], 2)
        self.assertEqual(record["failed_attempts"], 1)
        self.assertEqual(record["successful_attempts"], 1)
        self.assertEqual(record["current_status"], "Resolved")
        daily = {
            r["action"]: r["event_count"]
            for r in self.db.execute("SELECT * FROM v_case_activity_daily")
        }
        self.assertEqual(daily["detected"], 22)
        self.assertEqual(daily["verification_failed"], 1)
        self.assertEqual(daily["verified_resolved"], 1)

    def test_export_has_all_csvs_and_reconciled_manifest(self):
        self.resolve_example()
        target = self.root / "powerbi"
        result = export_reporting(self.db, target)
        self.assertEqual(result["reconciliation"], "passed")
        self.assertEqual(result["current_total_cases"], 22)
        self.assertEqual(result["current_resolved_cases"], 1)
        self.assertEqual(result["latest_scan_issues_found"], 21)
        self.assertEqual(result["current_cases_seen_in_latest_scan"], 21)
        self.assertEqual(len(result["exported_rows_per_view"]), 7)
        for view in REPORT_VIEWS:
            with (target / f"{view}.csv").open(newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            self.assertEqual(len(rows) - 1, result["exported_rows_per_view"][view])
            self.assertGreater(len(rows[0]), 1)
        self.assertEqual(
            json.loads((target / "reporting_manifest.json").read_text()), result
        )

    def test_compatible_view_installation_is_idempotent(self):
        prepare_views(self.db)
        prepare_views(self.db)
        self.assertEqual(self.fetchone("v_case_kpis")["total_cases"], 22)

    def test_no_empty_scan_database_is_reported_as_valid(self):
        separate = connect(self.root / "empty.sqlite")
        try:
            with self.assertRaisesRegex(ValueError, "No historical scans"):
                prepare_views(separate)
        finally:
            separate.close()


if __name__ == "__main__":
    unittest.main()
