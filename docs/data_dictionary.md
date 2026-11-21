# ProcureGuard data dictionary (MVP)

All data under `data/synthetic/` is **fabricated for the portfolio**. No data from real organizations, clients, government extracts, or the user's private repositories is stored here.

ProcureGuard models one procurement process with zero or more awards; each award references one supplier; a contract references one award. The four CSV files form a **raw landing zone**. They intentionally contain invalid records to exercise quality checks; a production trusted layer would enforce separate constraints only after remediation.

| Dataset | Column | Meaning | Required |
|---|---|---|---|
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
| issue_id | Deterministic hash of rule, dataset, CSV line number and affected field |
| rule_id | Data-quality rule identifier |
| dataset | Source table |
| record_id | Source primary identifier; `<missing>` when absent |
| row_number | Physical CSV row number, starting at 2 (header at 1) |
| field | Affected field |
| severity | Relative investigation priority, not a claim of legal risk |
| classification | `validation_error` or `review_flag` |
| owner_role | **Suggested** accountable role, not an actual assigned employee |
| status | Initially `Open`; full status transitions/audit history are a later milestone |
| detail | Human-readable explanation for investigation |

Stable issue IDs depend on input file ordering and field identity. They are **not** permanent business identifiers if the CSV is reordered; future versions can use durable source row keys.

A summary JSON file reports rows scanned, counts by rule/severity, distinct affected source rows, and a simple row-level pass rate. This pass rate is solely for the fictional fixture and is not representative of a real procurement environment.
