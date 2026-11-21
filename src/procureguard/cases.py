"""SQLite-backed issue governance for synthetic ProcureGuard quality exceptions.

Lifecycle: Open -> Investigating -> Pending Verification -> Resolved.
A repeated violation after verified closure creates a Reopened case with an
append-only event. No automatic closure or production incident claims.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .engine import SCHEMAS, evaluate, read_rules, read_tables, summarize

CASE_FIELDS = (
    "issue_id", "rule_id", "dataset", "source_row_id", "record_id", "row_number",
    "field", "severity", "classification", "owner_role", "detail", "status",
    "owner", "root_cause", "corrective_action", "first_seen", "last_seen",
    "updated_at", "resolved_at", "last_scan_run_id",
)


class GovernanceError(ValueError):
    """Raised when an issue workflow action would violate governance rules."""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_digest(input_dir: Path, rules_path: Path) -> str:
    """A reproducible audit fingerprint for all four files and the rule set."""
    hasher = hashlib.sha256()
    for path in [*(input_dir / f"{t}.csv" for t in SCHEMAS), rules_path]:
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(path.read_bytes())
        hasher.update(b"\x00")
    return hasher.hexdigest()


def _load(input_dir: Path, rules_path: Path) -> tuple[dict, list[dict], dict]:
    tables = read_tables(input_dir)
    for table, rows in tables.items():
        for row in rows:
            if not row.get("_source_row_id"):
                raise GovernanceError(
                    f"{table} must include unique, nonblank source_row_id values "
                    "for persistent case management"
                )
    rules = read_rules(rules_path)
    issues = evaluate(tables, rules)
    return tables, issues, summarize(tables, issues)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS scan_runs (
          run_id INTEGER PRIMARY KEY AUTOINCREMENT,
          scanned_at TEXT NOT NULL,
          input_sha256 TEXT NOT NULL,
          rows_scanned INTEGER NOT NULL,
          issues_found INTEGER NOT NULL,
          affected_rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cases (
          issue_id TEXT PRIMARY KEY,
          rule_id TEXT NOT NULL,
          dataset TEXT NOT NULL,
          source_row_id TEXT NOT NULL,
          record_id TEXT NOT NULL,
          row_number INTEGER NOT NULL,
          field TEXT NOT NULL,
          severity TEXT NOT NULL,
          classification TEXT NOT NULL,
          owner_role TEXT NOT NULL,
          detail TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN
            ('Open','Investigating','Pending Verification','Resolved','Reopened')),
          owner TEXT,
          root_cause TEXT,
          corrective_action TEXT,
          first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          resolved_at TEXT,
          last_scan_run_id INTEGER,
          FOREIGN KEY(last_scan_run_id) REFERENCES scan_runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS case_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          issue_id TEXT NOT NULL,
          occurred_at TEXT NOT NULL,
          actor TEXT NOT NULL,
          action TEXT NOT NULL,
          from_status TEXT,
          to_status TEXT NOT NULL,
          note TEXT NOT NULL,
          evidence_json TEXT NOT NULL,
          FOREIGN KEY(issue_id) REFERENCES cases(issue_id)
        );
        CREATE TABLE IF NOT EXISTS scan_findings (
          run_id INTEGER NOT NULL,
          issue_id TEXT NOT NULL,
          PRIMARY KEY(run_id,issue_id),
          FOREIGN KEY(run_id) REFERENCES scan_runs(run_id),
          FOREIGN KEY(issue_id) REFERENCES cases(issue_id)
        );
        CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
        CREATE INDEX IF NOT EXISTS idx_cases_owner ON cases(owner);
        CREATE INDEX IF NOT EXISTS idx_events_issue ON case_events(issue_id,event_id);
    """)
    return db


def _required(value: str, label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise GovernanceError(f"{label} must be nonblank")
    return text


def _case(db: sqlite3.Connection, issue_id: str) -> sqlite3.Row:
    record = db.execute("SELECT * FROM cases WHERE issue_id = ?", (issue_id,)).fetchone()
    if record is None:
        raise GovernanceError(f"Unknown case: {issue_id}. Run 'cases sync' first")
    return record


def _event(
    db: sqlite3.Connection, issue_id: str, actor: str, action: str,
    from_status: str | None, to_status: str, note: str,
    evidence: dict | None = None,
) -> None:
    db.execute(
        """INSERT INTO case_events
           (issue_id,occurred_at,actor,action,from_status,to_status,note,evidence_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            issue_id, now_utc(), _required(actor, "Actor"), action,
            from_status, to_status, note,
            json.dumps(evidence or {}, sort_keys=True),
        ),
    )


def sync_scan(db: sqlite3.Connection, input_dir: Path, rules_path: Path) -> dict:
    """Record a new scan and findings; never silently close absent issues."""
    tables, issues, summary = _load(input_dir, rules_path)
    timestamp = now_utc()
    digest = source_digest(input_dir, rules_path)
    created, reopened, updated = 0, 0, 0
    with db:
        cursor = db.execute(
            """INSERT INTO scan_runs
            (scanned_at,input_sha256,rows_scanned,issues_found,affected_rows)
            VALUES (?,?,?,?,?)""",
            (
                timestamp, digest, summary["rows_scanned"],
                summary["issues_found"], summary["distinct_rows_with_issues"],
            ),
        )
        scan_id = cursor.lastrowid
        for issue in issues:
            existing = db.execute(
                "SELECT status FROM cases WHERE issue_id = ?", (issue["issue_id"],)
            ).fetchone()
            fields = (
                issue["rule_id"], issue["dataset"], issue["source_row_id"],
                issue["record_id"], issue["row_number"], issue["field"],
                issue["severity"], issue["classification"], issue["owner_role"],
                issue["detail"],
            )
            if existing is None:
                db.execute(
                    """INSERT INTO cases (
                        issue_id,rule_id,dataset,source_row_id,record_id,row_number,field,
                        severity,classification,owner_role,detail,status,
                        first_seen,last_seen,updated_at,last_scan_run_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'Open',?,?,?,?)""",
                    (issue["issue_id"], *fields, timestamp, timestamp, timestamp, scan_id),
                )
                _event(db, issue["issue_id"], "system", "detected", None, "Open",
                       "New synthetic validation exception", {"scan_run_id": scan_id})
                created += 1
            else:
                previous = existing["status"]
                status = "Reopened" if previous == "Resolved" else previous
                db.execute(
                    """UPDATE cases SET
                       rule_id=?,dataset=?,source_row_id=?,record_id=?,row_number=?,
                       field=?,severity=?,classification=?,owner_role=?,detail=?,
                       status=?,last_seen=?,updated_at=?,last_scan_run_id=?,
                       root_cause=CASE WHEN ?='Resolved' THEN NULL ELSE root_cause END,
                       corrective_action=CASE WHEN ?='Resolved' THEN NULL ELSE corrective_action END,
                       resolved_at=CASE WHEN ?='Resolved' THEN NULL ELSE resolved_at END
                       WHERE issue_id=?""",
                    (*fields, status, timestamp, timestamp, scan_id,
                     previous, previous, previous, issue["issue_id"]),
                )
                if status == "Reopened":
                    _event(db, issue["issue_id"], "system", "reopened", previous,
                           "Reopened", "Exception appeared again on subsequent scan",
                           {"scan_run_id": scan_id})
                    reopened += 1
                else:
                    updated += 1
            db.execute(
                "INSERT INTO scan_findings(run_id,issue_id) VALUES (?,?)",
                (scan_id, issue["issue_id"]),
            )
    return {
        "scan_run_id": scan_id,
        "input_sha256": digest,
        "rows_scanned": summary["rows_scanned"],
        "issues_found": summary["issues_found"],
        "cases_created": created,
        "cases_reopened": reopened,
        "existing_cases_observed": updated,
        "closure_policy": "Missing findings do not automatically resolve cases",
    }


def assign(db: sqlite3.Connection, issue_id: str, owner: str, actor: str) -> dict:
    owner, actor = _required(owner, "Owner"), _required(actor, "Actor")
    with db:
        record = _case(db, issue_id)
        if record["status"] == "Resolved":
            raise GovernanceError("Cannot assign a resolved case; a new scan must reopen it")
        db.execute(
            "UPDATE cases SET owner=?,updated_at=? WHERE issue_id=?",
            (owner, now_utc(), issue_id),
        )
        _event(db, issue_id, actor, "assigned", record["status"], record["status"],
               f"Assigned to {owner}", {"previous_owner": record["owner"], "owner": owner})
    return dict(_case(db, issue_id))


def investigate(
    db: sqlite3.Connection, issue_id: str, actor: str, root_cause: str,
) -> dict:
    actor, root_cause = _required(actor, "Actor"), _required(root_cause, "Root cause")
    with db:
        record = _case(db, issue_id)
        if record["status"] not in {"Open", "Reopened", "Investigating"}:
            raise GovernanceError("Investigation requires Open, Reopened or Investigating status")
        if not record["owner"]:
            raise GovernanceError("Assign an owner before investigating")
        db.execute(
            """UPDATE cases SET status='Investigating',root_cause=?,
               corrective_action=NULL,updated_at=? WHERE issue_id=?""",
            (root_cause, now_utc(), issue_id),
        )
        _event(db, issue_id, actor, "investigated", record["status"], "Investigating",
               "Root cause documented (synthetic investigation)",
               {"root_cause": root_cause})
    return dict(_case(db, issue_id))


def propose(
    db: sqlite3.Connection, issue_id: str, actor: str, corrective_action: str,
) -> dict:
    actor = _required(actor, "Actor")
    corrective_action = _required(corrective_action, "Corrective action")
    with db:
        record = _case(db, issue_id)
        if record["status"] != "Investigating":
            raise GovernanceError("Corrective action requires Investigating status")
        if not record["root_cause"] or not record["owner"]:
            raise GovernanceError("Owner and root cause must be recorded first")
        db.execute(
            """UPDATE cases SET status='Pending Verification',
               corrective_action=?,updated_at=? WHERE issue_id=?""",
            (corrective_action, now_utc(), issue_id),
        )
        _event(db, issue_id, actor, "submitted_for_verification",
               "Investigating", "Pending Verification",
               "Corrective action documented; source must be independently rechecked",
               {"corrective_action": corrective_action})
    return dict(_case(db, issue_id))


def verify(
    db: sqlite3.Connection, issue_id: str, actor: str,
    input_dir: Path, rules_path: Path,
) -> dict:
    """Require a fresh rule evaluation, the source row, and a missing finding."""
    actor = _required(actor, "Actor")
    record = _case(db, issue_id)
    if record["status"] != "Pending Verification":
        raise GovernanceError("Only cases Pending Verification may be verified")
    tables, current_issues, _ = _load(input_dir, rules_path)
    digest = source_digest(input_dir, rules_path)
    matching_rows = [
        row for row in tables[record["dataset"]]
        if row.get("_source_row_id") == record["source_row_id"]
    ]
    present = any(finding["issue_id"] == issue_id for finding in current_issues)
    if not matching_rows:
        reason = "Source row is missing; deletion alone does not verify corrective action"
    elif present:
        reason = "The original quality-rule violation is still present"
    else:
        reason = "Source row retained and the original rule violation is no longer detected"
    passed = bool(matching_rows) and not present
    evidence = {
        "passed": passed, "input_sha256": digest,
        "source_row_id": record["source_row_id"],
        "rule_id": record["rule_id"], "reason": reason,
    }
    # Persist both successes and failures in append-only case events.
    with db:
        if passed:
            db.execute(
                """UPDATE cases SET status='Resolved',updated_at=?,resolved_at=?
                   WHERE issue_id=?""",
                (now_utc(), now_utc(), issue_id),
            )
            _event(db, issue_id, actor, "verified_resolved",
                   "Pending Verification", "Resolved",
                   reason, evidence)
        else:
            _event(db, issue_id, actor, "verification_failed",
                   "Pending Verification", "Pending Verification",
                   reason, evidence)
    return {"issue_id": issue_id, "verified": passed, "reason": reason,
            "status": "Resolved" if passed else "Pending Verification",
            "input_sha256": digest}


def get_case(db: sqlite3.Connection, issue_id: str) -> dict:
    return dict(_case(db, issue_id))


def list_cases(db: sqlite3.Connection, status: str | None = None) -> list[dict]:
    if status:
        return [
            dict(row) for row in db.execute(
                "SELECT * FROM cases WHERE status=? ORDER BY severity,rule_id,issue_id",
                (status,),
            )
        ]
    return [
        dict(row) for row in db.execute(
            "SELECT * FROM cases ORDER BY severity,rule_id,issue_id"
        )
    ]


def history(db: sqlite3.Connection, issue_id: str) -> list[dict]:
    _case(db, issue_id)
    return [
        dict(row) for row in db.execute(
            "SELECT * FROM case_events WHERE issue_id=? ORDER BY event_id", (issue_id,)
        )
    ]


def export_cases(db: sqlite3.Connection, output_dir: Path) -> dict:
    """Export a readable case register, event audit log and status totals."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = list_cases(db)
    events = [dict(row) for row in db.execute(
        "SELECT * FROM case_events ORDER BY event_id"
    )]
    with (output_dir / "cases.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CASE_FIELDS)
        writer.writeheader()
        writer.writerows(cases)
    event_fields = (
        "event_id", "issue_id", "occurred_at", "actor", "action", "from_status",
        "to_status", "note", "evidence_json",
    )
    with (output_dir / "audit_events.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=event_fields)
        writer.writeheader()
        writer.writerows(events)
    statuses = {s: sum(x["status"] == s for x in cases) for s in
                ("Open", "Investigating", "Pending Verification", "Resolved", "Reopened")}
    summary = {
        "source": "synthetic demonstration only",
        "total_cases": len(cases),
        "audit_events": len(events),
        "cases_by_status": statuses,
        "note": "Resolution requires a repeat rules evaluation; no real cases are shown",
    }
    (output_dir / "case_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary
