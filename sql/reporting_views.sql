-- ProcureGuard | SQLite reporting mart | Milestone 3 (foundation)
--
-- Source tables: cases, scan_runs, scan_findings, case_events.
-- These are populated by "python -m procureguard cases sync" and later
-- issue-management commands. All bundled examples are synthetic.
--
-- Execute against a ProcureGuard SQLite governance database, NOT MySQL.
-- CREATE VIEW statements do not change the underlying case records.
-- Re-runnable: replacing views changes only the reporting definitions.
--
-- Reporting conventions:
-- * "Unresolved" means status != 'Resolved' (including Pending Verification).
-- * "Seen in latest scan" is independent of current case status.
-- * Scan-trend metrics describe OBSERVED findings, not historical backlog.
-- * Days open is calculated as of query time; status is current, not a
--   reconstructed historical snapshot. Times can be zero for a fast demo.
-- * No reported monetary values are considered verified actual spending.

DROP VIEW IF EXISTS v_case_kpis;
DROP VIEW IF EXISTS v_rule_metrics;
DROP VIEW IF EXISTS v_owner_workload;
DROP VIEW IF EXISTS v_scan_quality_trend;
DROP VIEW IF EXISTS v_case_activity_daily;
DROP VIEW IF EXISTS v_verification_metrics;
DROP VIEW IF EXISTS v_case_details;

-- DETAIL FACT: one row per distinct rule violation/case; stable issue_id.
CREATE VIEW v_case_details AS
SELECT
    c.issue_id,
    c.rule_id,
    c.dataset,
    c.source_row_id,
    c.record_id,
    c.row_number,
    c.field,
    c.severity,
    c.classification,
    c.owner_role,
    c.owner,
    COALESCE(NULLIF(TRIM(c.owner), ''), 'Unassigned') AS owner_display,
    c.status,
    CASE WHEN c.status = 'Resolved' THEN 0 ELSE 1 END AS is_unresolved,
    CASE WHEN c.status = 'Resolved' THEN 1 ELSE 0 END AS is_resolved,
    CASE WHEN c.status <> 'Resolved' AND c.severity = 'High'
         THEN 1 ELSE 0 END AS is_high_priority_unresolved,
    CASE WHEN EXISTS (
        SELECT 1
        FROM scan_findings sf
        WHERE sf.issue_id = c.issue_id
          AND sf.run_id = (SELECT MAX(run_id) FROM scan_runs)
    ) THEN 1 ELSE 0 END AS seen_in_latest_scan,
    c.detail,
    c.root_cause,
    c.corrective_action,
    c.first_seen,
    date(c.first_seen) AS first_seen_date,
    c.last_seen,
    c.updated_at,
    c.resolved_at,
    date(c.resolved_at) AS resolved_date,
    c.last_scan_run_id,
    CASE WHEN c.status = 'Resolved' AND c.resolved_at IS NOT NULL
         THEN ROUND(MAX(0, julianday(c.resolved_at) - julianday(c.first_seen)), 3)
         ELSE NULL END AS resolution_days,
    CASE WHEN c.status <> 'Resolved'
         THEN ROUND(MAX(0, julianday('now') - julianday(c.first_seen)), 3)
         ELSE NULL END AS open_age_days
FROM cases c;

-- SINGLE-ROW KPI: current governance state, independent of scan counts.
CREATE VIEW v_case_kpis AS
SELECT
    COUNT(*) AS total_cases,
    COALESCE(SUM(is_unresolved), 0) AS unresolved_cases,
    COALESCE(SUM(is_resolved), 0) AS resolved_cases,
    COALESCE(SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END), 0) AS open_cases,
    COALESCE(SUM(CASE WHEN status = 'Investigating' THEN 1 ELSE 0 END), 0)
        AS investigating_cases,
    COALESCE(SUM(CASE WHEN status = 'Pending Verification' THEN 1 ELSE 0 END), 0)
        AS pending_verification_cases,
    COALESCE(SUM(CASE WHEN status = 'Reopened' THEN 1 ELSE 0 END), 0) AS reopened_cases,
    COALESCE(SUM(is_high_priority_unresolved), 0) AS high_priority_unresolved,
    COALESCE(SUM(CASE WHEN is_unresolved = 1 AND owner IS NULL THEN 1 ELSE 0 END), 0)
        AS unassigned_unresolved_cases,
    COALESCE(SUM(seen_in_latest_scan), 0) AS cases_seen_in_latest_scan,
    ROUND(AVG(resolution_days), 3) AS mean_resolution_days_resolved_only
FROM v_case_details;

-- RULE-LEVEL METRICS: one row per rule with at least one case.
CREATE VIEW v_rule_metrics AS
SELECT
    rule_id,
    severity,
    classification,
    owner_role,
    COUNT(*) AS total_cases,
    SUM(is_unresolved) AS unresolved_cases,
    SUM(is_resolved) AS resolved_cases,
    SUM(seen_in_latest_scan) AS cases_seen_in_latest_scan,
    COUNT(DISTINCT dataset || CHAR(31) || source_row_id) AS distinct_source_rows
FROM v_case_details
GROUP BY rule_id, severity, classification, owner_role;

-- TEAM CAPACITY/BACKLOG: current unresolved cases grouped by owner and severity.
-- The owner string is not a verified directory user or authenticated account.
CREATE VIEW v_owner_workload AS
SELECT
    owner_display,
    owner_role,
    severity,
    COUNT(*) AS unresolved_cases,
    SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) AS open_cases,
    SUM(CASE WHEN status = 'Investigating' THEN 1 ELSE 0 END)
        AS investigating_cases,
    SUM(CASE WHEN status = 'Pending Verification' THEN 1 ELSE 0 END)
        AS pending_verification_cases,
    SUM(CASE WHEN status = 'Reopened' THEN 1 ELSE 0 END) AS reopened_cases,
    SUM(seen_in_latest_scan) AS cases_seen_in_latest_scan,
    ROUND(MAX(open_age_days), 3) AS oldest_open_case_age_days
FROM v_case_details
WHERE is_unresolved = 1
GROUP BY owner_display, owner_role, severity;

-- SCAN OBSERVATIONS: exact values persisted at scan time.
-- A sequence of quick demonstration scans is NOT a longitudinal history of
-- production performance. In particular, this does not describe backlog
-- as it was at the time of a past scan.
CREATE VIEW v_scan_quality_trend AS
SELECT
    run_id,
    scanned_at,
    date(scanned_at) AS scan_date,
    input_sha256,
    rows_scanned,
    issues_found,
    affected_rows,
    CASE WHEN rows_scanned > 0 THEN rows_scanned - affected_rows
         ELSE 0 END AS rows_without_findings,
    CASE WHEN rows_scanned > 0
         THEN ROUND(100.0 * (rows_scanned - affected_rows) / rows_scanned, 2)
         ELSE NULL END AS row_pass_rate_pct
FROM scan_runs;

-- EVENT HISTORY: preserves event-time status changes and verification attempts.
-- event_id is a technical sequence number; timestamps can tie within one second.
CREATE VIEW v_case_activity_daily AS
SELECT
    date(occurred_at) AS event_date,
    action,
    COUNT(*) AS event_count,
    COUNT(DISTINCT issue_id) AS distinct_cases_with_event
FROM case_events
GROUP BY date(occurred_at), action;

-- VERIFICATION TRACKER: attempts remain visible after closure or reopening.
CREATE VIEW v_verification_metrics AS
SELECT
    c.issue_id,
    c.rule_id,
    c.dataset,
    c.source_row_id,
    c.status AS current_status,
    c.owner,
    COALESCE(SUM(CASE WHEN e.action IN ('verification_failed', 'verified_resolved')
             THEN 1 ELSE 0 END), 0) AS verification_attempts,
    COALESCE(SUM(CASE WHEN e.action = 'verification_failed'
             THEN 1 ELSE 0 END), 0) AS failed_attempts,
    COALESCE(SUM(CASE WHEN e.action = 'verified_resolved'
             THEN 1 ELSE 0 END), 0) AS successful_attempts,
    MAX(CASE WHEN e.action IN ('verification_failed','verified_resolved')
        THEN e.occurred_at ELSE NULL END) AS last_verification_at
FROM cases c
LEFT JOIN case_events e ON e.issue_id = c.issue_id
GROUP BY c.issue_id, c.rule_id, c.dataset, c.source_row_id,
         c.status, c.owner;
