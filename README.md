# ProcureGuard

**Procurement data quality & governance — Python · SQLite · SQL/Power BI planned**

ProcureGuard is an applied portfolio project demonstrating how a procurement team could **detect, investigate, document and verify data-quality exceptions** across procurement processes, suppliers, awards and contracts.

**Milestones 1 and 2 are implemented:** an offline Python quality-rule engine, durable source-row IDs, persistent SQLite case management, assignment and investigation, corrective-action documentation, a fresh-data verification gate, and an exportable event audit trail. SQL reporting and Power BI monitoring are future milestones.

> **Portfolio demonstration, not a deployed business system.** All records, buyer/supplier names and reported amounts in this repository are invented. No source data, people or contact details from the earlier pharmaceutical procurement project are copied here.

## Business case

A procurement reporting team needs to trust process identifiers and award relationships before calculating supplier participation or management KPIs. Some apparently incorrect reported contract values may actually reflect legitimate reporting conventions, so the system must distinguish **validation failures** from **issues requiring human review**.

The goal is to move from a one-time dashboard into an auditable, repeatable data-quality process.

## Architecture — milestones 1–2

```text
data/synthetic/*.csv            config/quality_rules.csv
procurements, awards,            rule ID, severity, owner role
suppliers, contracts                    |
               \                       /
                \                     /
                 -> Python quality engine (six rules)
                            |
               +------------+-------------+
               |                          |
          build/issues.csv         SQLite case register
          build/summary.json       source-row IDs, status
                                          |
                               Assign -> Investigate ->
                               Correct -> Verify (rescan)
                                          |
                                cases.csv, audit_events.csv
                                     case_summary.json
                                          |
                                    26 tests + CI
```

### Quality rules

| Rule | Detection | Interpretation |
|---|---|---|
| DQ-01 | Blank required primary/foreign identifier | Validation error |
| DQ-02 | Duplicate primary identifier | Validation error |
| DQ-03 | Foreign key references missing parent record | Validation error |
| DQ-04 | Different supplier IDs with punctuation-insensitive matching names | **Possible duplicate; review** |
| DQ-05 | Missing, nominal `1`, or nonnumeric reported contract value | **Reporting usability flag; review** |
| DQ-06 | Invalid ISO date, contract end preceding start, or wrong currency-code format | Validation error |

Priorities, classifications and suggested responsible **roles** come from a visible rule catalogue. They are not real incident assignments or regulatory severity assessments.

## Run the project

Requirements: **Python 3.11+**. No database, credentials, cloud account, network call or external datasets required.

```bash
git clone https://github.com/Orgo4ever/ProcureGuard.git
cd ProcureGuard
python -m pip install -e .
python -m unittest discover -s tests -v
python -m procureguard --input data/synthetic --output build
```

The command writes:

- `build/issues.csv` — deterministic issue IDs, affected dataset/record/CSV row, failing field, rule, severity, classification, suggested owner, and initial `Open` status.
- `build/summary.json` — source counts, issue totals, rule/severity breakdown, distinct impacted rows, and the **fictional** row-level pass rate.

The bundled sample intentionally contains quality problems. It has **38 source records** and an expected **22 exceptions** across the six rules. These are synthetic fixture metrics, not real operational KPIs.

## Manage issues — Milestone 2

For a persistent local case register, run:

```bash
python -m procureguard cases sync
python -m procureguard cases list
python -m procureguard cases export
```

Then choose a case ID from `cases list` and use this workflow:

```bash
python -m procureguard cases show ISSUE_ID
python -m procureguard cases assign ISSUE_ID --owner "Demo Steward" --actor "Demo Lead"
python -m procureguard cases investigate ISSUE_ID --cause "Fictional upstream mapping failure" --actor "Demo Steward"
python -m procureguard cases propose ISSUE_ID --action "Correct the fictional source record" --actor "Demo Steward"
python -m procureguard cases verify ISSUE_ID --actor "Demo Reviewer"
python -m procureguard cases history ISSUE_ID
```

**Verification will fail if the problem is still present.** That is intentional: merely describing a corrective action is not a verified resolution. Verification must be run against updated, authorized input files containing the same original source row. See [the operating procedure](docs/issue_management_sop.md).

### See a complete, successful case lifecycle

```bash
python scripts/demo_lifecycle.py --output build/lifecycle_demo
```

This self-contained walkthrough copies the synthetic files, detects 22 issues, assigns a fictional owner, records an illustrative investigation and proposed correction, **fails verification before the data changes**, edits one copied fictional contract, then **passes verification** and exports the audit trail.

Generated outputs include `build/lifecycle_demo/cases.csv`, `audit_events.csv`, `case_summary.json`, `demo_lifecycle.json`, and a local `governance.sqlite` database. These generated files are excluded from Git; the example and its regression checks run in GitHub Actions.

The ordinary `cases sync` database is `build/governance.sqlite`; run `cases export` for a portable exception register and audit log. The scanner and case manager require no network access, credentials or external Python packages after installation.

To run against alternative CSVs with the **same column schema**:

```bash
python -m procureguard --input path/to/your/csv_folder --output build
```

Run this only on data you are authorized to use. Avoid committing private or personal information. The CSV reader validates required headers and rejects malformed rows.

## Repository layout

```text
ProcureGuard/
├── config/quality_rules.csv        # Rules, priority, classification, ownership
├── data/synthetic/                # Four fictional procurement source tables
├── docs/data_dictionary.md        # Columns, relationships and output contract
├── docs/rule_catalogue.md         # Business interpretation and safeguards
├── docs/issue_management_sop.md   # Case workflow and verification policy
├── src/procureguard/
│   ├── __init__.py
│   ├── __main__.py                 # Scan and case CLI entry point
│   ├── engine.py                   # Pure rule evaluation and exports
│   └── cases.py                    # SQLite issues, ownership, audit, verification
├── scripts/demo_lifecycle.py      # Fictional failed/pass verification example
├── tests/                         # Engine + lifecycle regression tests
├── .github/workflows/ci.yml       # Tests, reproducible demo, audit artifacts
└── pyproject.toml
```

## Data-model choices

The four CSV files are intentionally a **raw landing zone** and can contain duplicate IDs, missing keys and invalid dates. The validation happens **before** data would be accepted into a trusted relational warehouse. Loading these raw rows directly into SQL tables with enforced unique and foreign-key constraints would prevent the quality engine from inspecting the bad records.

`award_id` links awards to contracts; `procurement_id` links procurements to awards; `supplier_id` links suppliers to awards. A conceptual data dictionary is in [docs/data_dictionary.md](docs/data_dictionary.md).

## Quality and interpretation

- **DQ-05:** A nominal amount such as `1` may be a reporting convention. We flag it for interpretation, not call it fraudulent or erroneous.
- **DQ-04:** A normalized name match is a *candidate* duplicate, not proof of the same legal entity.
- **DQ-06:** Currency validation checks three-uppercase-letter **format only**, not the entire ISO currency registry.
- A record can trigger multiple rules. The dashboard-ready count of **affected rows** is deliberately distinct from total **issues**.
- Every landing record includes a unique immutable `source_row_id`; issue identities persist across CSV reorderings and changes to the record's business values. Scan-only CSVs lacking this ID can still be evaluated but cannot be persisted in the governance database.
- SQLite tracks `Open`, `Investigating`, `Pending Verification`, `Resolved` and `Reopened` cases. The application records actor-attributed events and SHA-256 input fingerprints. Cases do not auto-close merely because a subsequent scan omits a finding.
- Case actors and owners are **illustrative text labels, not authenticated users**; the local audit log is not tamper-evident or an enterprise-grade approval system. This project does not establish real corrective-action effectiveness, SLAs, or financial impact.
- CI verifies the synthetic project, not any claimed production deployment.

## Project roadmap

| Milestone | Outcome | State |
|---|---|---|
| 1 — Detect | Synthetic relational data, rule catalogue, issue export, unit tests, GitHub Actions | **Implemented** |
| 2 — Govern | Durable row IDs, SQLite issue history, owner workflow, root cause, corrective action and verification | **Implemented** |
| 3 — Analyze | SQL data-quality mart, recurring snapshots and Power BI quality dashboard | Planned |
| 4 — Communicate | Operating SOP and synthetic lifecycle walkthrough (added in Milestone 2); employer-facing portfolio case study | In progress |

The quality-focused engineering work is intended as portfolio evidence for **Data Quality Analyst, Data Steward, Master Data, Quality Operations, and BI/Reporting Analyst** roles.

**Author:** Kyle Haustein · Public learning project · 2026.
