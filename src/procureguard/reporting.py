"""Power BI-ready CSV exports backed by SQLite reporting views.

All included example records are fictional. View definitions are stored in
sql/reporting_views.sql and run against the current local governance database.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .engine import ROOT

SQL_PATH = ROOT / "sql" / "reporting_views.sql"
REPORT_VIEWS = (
    "v_case_details",
    "v_case_kpis",
    "v_rule_metrics",
    "v_owner_workload",
    "v_scan_quality_trend",
    "v_case_activity_daily",
    "v_verification_metrics",
)


def prepare_views(db: sqlite3.Connection, sql_path: Path = SQL_PATH) -> None:
    """Install only reporting views. Require a scan so exports have provenance."""
    if not sql_path.is_file():
        raise FileNotFoundError(f"SQL view definitions not found: {sql_path}")
    try:
        count = db.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise ValueError(
            "This is not an initialized ProcureGuard governance database; "
            "run 'python -m procureguard cases sync' first"
        ) from exc
    if count == 0:
        raise ValueError(
            "No historical scans found. Run 'python -m procureguard cases sync' first"
        )
    db.executescript(sql_path.read_text(encoding="utf-8"))


def export_reporting(
    db: sqlite3.Connection, output_dir: Path, sql_path: Path = SQL_PATH,
) -> dict:
    """Materialize dashboard CSVs; reconcile counts against scan and case tables."""
    prepare_views(db, sql_path)
    latest = db.execute(
        "SELECT run_id,rows_scanned,issues_found,affected_rows "
        "FROM scan_runs ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    kpi = db.execute("SELECT * FROM v_case_kpis").fetchone()
    # Check every observed latest-scan issue is represented exactly once.
    actual_findings = db.execute(
        "SELECT COUNT(*) FROM scan_findings WHERE run_id = ?", (latest["run_id"],)
    ).fetchone()[0]
    actual_cases = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    if (
        latest["issues_found"] != actual_findings
        or kpi["cases_seen_in_latest_scan"] != actual_findings
        or kpi["total_cases"] != actual_cases
        or kpi["unresolved_cases"] + kpi["resolved_cases"] != actual_cases
    ):
        raise ValueError(
            "Reporting reconciliation failed: cases, latest scan, "
            "and scan findings must agree"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    row_counts = {}
    for view in REPORT_VIEWS:
        cursor = db.execute(f"SELECT * FROM {view}")
        headers = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        with (output_dir / f"{view}.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)
        row_counts[view] = len(rows)

    report = {
        "source": "Fictional ProcureGuard case-register demonstration only",
        "latest_scan_run_id": latest["run_id"],
        "latest_scan_rows_scanned": latest["rows_scanned"],
        "latest_scan_issues_found": latest["issues_found"],
        "latest_scan_affected_rows": latest["affected_rows"],
        "current_total_cases": kpi["total_cases"],
        "current_unresolved_cases": kpi["unresolved_cases"],
        "current_resolved_cases": kpi["resolved_cases"],
        "current_cases_seen_in_latest_scan": kpi["cases_seen_in_latest_scan"],
        "exported_rows_per_view": row_counts,
        "reconciliation": "passed",
        "interpretation": (
            "Current case states are not point-in-time historical backlog. "
            "Scan trends show observed data quality per run, not business-period "
            "trends; case times are generated during the synthetic workflow."
        ),
    }
    (output_dir / "reporting_manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report
