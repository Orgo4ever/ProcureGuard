"""Offline regression tests for ProcureGuard's synthetic validation MVP."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from procureguard.engine import (
    ROOT, evaluate, read_rules, read_tables, run, summarize,
)

DATA = ROOT / "data" / "synthetic"
RULES = ROOT / "config" / "quality_rules.csv"


class ProcureGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tables = read_tables(DATA)
        cls.rules = read_rules(RULES)
        cls.issues = evaluate(cls.tables, cls.rules)

    def test_synthetic_dataset_sizes(self):
        self.assertEqual(
            {name: len(rows) for name, rows in self.tables.items()},
            {"procurements": 9, "suppliers": 9, "awards": 10, "contracts": 10},
        )

    def test_expected_rule_distribution(self):
        observed = Counter(row["rule_id"] for row in self.issues)
        self.assertEqual(
            dict(observed),
            {"DQ-01": 3, "DQ-02": 8, "DQ-03": 3,
             "DQ-04": 2, "DQ-05": 2, "DQ-06": 4},
        )
        self.assertEqual(len(self.issues), 22)

    def test_ids_unique_and_deterministic(self):
        current = [item["issue_id"] for item in self.issues]
        future = [item["issue_id"] for item in evaluate(self.tables, self.rules)]
        self.assertEqual(current, future)
        self.assertEqual(len(current), len(set(current)))
        self.assertTrue(all(s.startswith("PG-") for s in current))

    def test_duplicate_identifier_flags_all_rows(self):
        dupes = [row for row in self.issues if row["rule_id"] == "DQ-02"]
        by_table = Counter(row["dataset"] for row in dupes)
        self.assertEqual(dict(by_table), {
            "procurements": 2, "suppliers": 2, "awards": 2, "contracts": 2,
        })

    def test_orphans_are_not_conflated_with_blank_identifiers(self):
        unresolved = [row for row in self.issues if row["rule_id"] == "DQ-03"]
        self.assertEqual(
            {(r["dataset"], r["field"], r["record_id"]) for r in unresolved},
            {("awards", "procurement_id", "A-204"),
             ("awards", "supplier_id", "A-205"),
             ("contracts", "award_id", "C-305")},
        )
        blanks = [row for row in self.issues if row["rule_id"] == "DQ-01"]
        self.assertEqual(len(blanks), 3)

    def test_possible_supplier_duplicates_are_not_auto_confirmed(self):
        flagged = [row for row in self.issues if row["rule_id"] == "DQ-04"]
        self.assertEqual({r["record_id"] for r in flagged}, {"S-01", "S-02"})
        self.assertTrue(all(r["classification"] == "review_flag" for r in flagged))
        self.assertTrue(all("human review" in r["detail"] for r in flagged))

    def test_contract_value_flags_not_misrepresented_as_errors(self):
        flagged = [row for row in self.issues if row["rule_id"] == "DQ-05"]
        self.assertEqual({r["record_id"] for r in flagged}, {"C-302", "C-303"})
        self.assertTrue(all(r["classification"] == "review_flag" for r in flagged))

    def test_format_and_date_logic(self):
        flagged = [r for r in self.issues if r["rule_id"] == "DQ-06"]
        self.assertEqual(
            {(r["dataset"], r["record_id"], r["field"]) for r in flagged},
            {("procurements", "P-105", "published_date"),
             ("contracts", "C-304", "end_date"),
             ("contracts", "C-306", "currency"),
             ("contracts", "C-307", "start_date")},
        )

    def test_summary_counts_rows_not_issues(self):
        report = summarize(self.tables, self.issues)
        self.assertEqual(report["rows_scanned"], 38)
        self.assertEqual(report["issues_found"], 22)
        self.assertEqual(report["distinct_rows_with_issues"], 22)
        self.assertEqual(report["rows_passing_all_rules"], 16)
        self.assertEqual(report["row_pass_rate_pct"], 42.11)
        self.assertEqual(report["issues_by_severity"], {"High": 14, "Medium": 8})

    def test_export_writes_valid_csv_and_json(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            summary = run(DATA, RULES, output)
            csv_path = output / "issues.csv"
            with csv_path.open("r", newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 22)
            self.assertEqual(set(rows[0]), {
                "issue_id", "rule_id", "dataset", "record_id", "source_row_id", "row_number",
                "field", "severity", "classification", "owner_role", "status",
                "detail",
            })
            self.assertTrue(all(row["status"] == "Open" for row in rows))
            self.assertEqual(json.loads((output / "summary.json").read_text()), summary)
            saved = csv_path.read_bytes()
            run(DATA, RULES, output)
            self.assertEqual(csv_path.read_bytes(), saved)

    def test_invalid_input_schema_fails_loudly(self):
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder)
            for path in DATA.glob("*.csv"):
                shutil.copy2(path, copy / path.name)
            source = copy / "awards.csv"
            source.write_text("award_id,procurement_id\nA-1,P-1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing columns"):
                read_tables(copy)

    def test_missing_rule_catalogue_entry_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "rules.csv"
            with RULES.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))
            with target.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerows([r for r in rows if not r or r[0] != "DQ-06"])
            with self.assertRaisesRegex(ValueError, "exactly"):
                read_rules(target)

    def test_clean_records_generate_no_issues(self):
        clean = {
            "procurements": [{
                "procurement_id": "P-X", "buyer_id": "B-X", "method": "open",
                "published_date": "2026-05-10", "_line": 2,
            }],
            "suppliers": [{
                "supplier_id": "S-X", "name": "Unique Demo Supplies",
                "country_code": "NL", "_line": 2,
            }],
            "awards": [{
                "award_id": "A-X", "procurement_id": "P-X",
                "supplier_id": "S-X", "_line": 2,
            }],
            "contracts": [{
                "contract_id": "C-X", "award_id": "A-X",
                "reported_value": "2500", "currency": "EUR",
                "start_date": "2026-05-10", "end_date": "2027-05-09",
                "_line": 2,
            }],
        }
        self.assertEqual(evaluate(clean, self.rules), [])
        self.assertEqual(summarize(clean, [])["row_pass_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
