# ProcureGuard data dictionary (MVP)

All data under `data/synthetic/` is **fabricated for the portfolio**. No data from real organizations, clients, government extracts, or the user's private repositories is stored here.

ProcureGuard models one procurement process with zero or more awards; each award references one supplier; a contract references one award. The four CSV files form a **raw landing zone**. They intentionally contain invalid records to exercise quality checks; a production trusted layer would enforce separate constraints only after remediation.

| Dataset | Column | Meaning | Required |
|---|---|---|---|
| all four | source_row_id | Immutable landing-row identity (unique per source table), used for persistent governance cases | Yes for case management |
| procurements | procurement_id | Business identifier of the procurement process (expected unique) | Yes |
| procurements | buyer_id | Identifier of the purchasing organization (not a separate table in MVP) | Yes for business use; not yet validated |
| procurements | method | Recorded procurement method | No |
| procurements | published_date | Publication date, ISO `YYYY-MM-DD` | Required for DQ-06 format check |
| awards | award_id | Award identifier (expected unique) | Yes |
| awards | procurement_id | Foreign key to `procurements.procurement_id` | Yes |
| awards | supplier_id | Foreign key to `suppliers.supplier_id` | Yes |
| suppliers | supplier_id | Supplier master identifier (expected unique) | Yes |
| suppliers | name | Supplier organization name | Used for DQ-04 |
| suppliers | country_code | Fictional supplier country, ISO alpha-2-style code | No; not yet validated |
| contracts | contract_id | Contract identifier (expected unique) | Yes |
| contracts | award_id | Foreign key to `awards.award_id` | Yes |
| contracts | reported_value | Published reported amount as raw text; **not validated actual spend** | Quality flag in DQ-05 |
| contracts | currency | Three uppercase-letter code (format check only; not an ISO membership lookup) | Checked by DQ-06 |
| contracts | start_date | Contract start, ISO `YYYY-MM-DD` | Checked by DQ-06 |
| contracts | end_date | Contract end, ISO `YYYY-MM-DD` | Checked by DQ-06 |

## Exceptions output

Each violated rule emits one row in `issues.csv`. Multiple issues may refer to the same source row.

| Field | Semantics |
|---|---|
| issue_id | Deterministic hash of rule, dataset, immutable source-row ID and affected field. For one-off scan inputs without source IDs, the legacy line-based fallback applies and case management is disabled |
| rule_id | Data-quality rule identifier |
| dataset | Source table |
| record_id | Source primary identifier; `<missing>` when absent |
| source_row_id | Immutable source-row identity, separate from business identifiers |
| row_number | Physical CSV row number, starting at 2 (header at 1) |
| field | Affected field |
| severity | Relative investigation priority, not a claim of legal risk |
| classification | `validation_error` or `review_flag` |
| owner_role | **Suggested** accountable role, not an actual assigned employee |
| status | Initially `Open`; full status transitions/audit history are a later milestone |
| detail | Human-readable explanation for investigation |

In governance mode, issue IDs use the source-row ID and remain stable across row ordering and corrections to business fields. Source-row IDs must be nonblank and unique within each table. Scan-only CSVs without source-row IDs retain line-based issue IDs for backwards compatibility, but cannot be synchronized into the case database.

A summary JSON file reports rows scanned, counts by rule/severity, distinct affected source rows, and a simple row-level pass rate. This pass rate is solely for the fictional fixture and is not representative of a real procurement environment.

## Milestone 2 case-management records

`build/governance.sqlite` contains three record families:

- `scan_runs`: scan timestamp, SHA-256 input fingerprint, record and finding counts
- `cases`: exception ID, stable source-row ID, status, owner, root cause, proposed corrective action, detection and resolution timestamps
- `case_events`: sequential event history (assigned/investigated/submitted for verification/verification failed/verified resolved/reopened), actor, status change, note and source-evidence JSON

`scan_findings` joins scans and observed issues. The `cases export` command writes `cases.csv`, `audit_events.csv`, and `case_summary.json`. The database and generated reports are excluded from Git by `.gitignore`.

All actors and ownership in the demonstration are fictional; see [issue-management SOP](issue_management_sop.md).
