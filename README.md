# ProcureGuard

**Procurement data quality & governance — Python, SQL, Power BI (roadmap)**

ProcureGuard is an applied portfolio project demonstrating how a procurement team could **detect, explain and eventually manage data-quality exceptions** across procurement processes, suppliers, awards and contracts.

The first milestone is implemented: an offline, reproducible Python rules engine that processes fictional procurement records and exports a structured exceptions register. The project is being expanded toward issue ownership, corrective action, SQL reporting and Power BI monitoring.

> **Portfolio demonstration, not a deployed business system.** All records, buyer/supplier names and reported amounts in this repository are invented. No source data, people or contact details from the earlier pharmaceutical procurement project are copied here.

## Business case

A procurement reporting team needs to trust process identifiers and award relationships before calculating supplier participation or management KPIs. Some apparently incorrect reported contract values may actually reflect legitimate reporting conventions, so the system must distinguish **validation failures** from **issues requiring human review**.

The goal is to move from a one-time dashboard into an auditable, repeatable data-quality process.

## Architecture — milestone 1

```text
data/synthetic/*.csv             config/quality_rules.csv
   procurements | suppliers           severity | owner role
   awards | contracts                     |
             \                            /
              \                          /
               -> src/procureguard/engine.py
                   six deterministic checks
                            |
                            v
                  build/issues.csv
                  build/summary.json
                     (generated)
                            |
                     tests/ + CI
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

## Run the first milestone

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
├── src/procureguard/
│   ├── __init__.py
│   ├── __main__.py                 # CLI entry point
│   └── engine.py                   # Pure rule evaluation and exports
├── tests/test_engine.py            # Deterministic offline tests
├── .github/workflows/ci.yml       # Automatic checks and synthetic sample
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
- Stable issue IDs are based on the CSV line number; reorder the file and these IDs may change. An immutable source-row key is planned before adding issue resolution history.
- The initial `status=Open` is a placeholder. Real ownership, investigation, audit trail, root causes, and validated closure **are not yet implemented**.
- CI verifies the synthetic project, not any claimed production deployment.

## Project roadmap

| Milestone | Outcome | State |
|---|---|---|
| 1 — Detect | Synthetic relational data, rule catalogue, issue export, unit tests, GitHub Actions | **Implemented** |
| 2 — Govern | Durable issue IDs, issue history, owner workflow, root cause and corrective actions | Planned |
| 3 — Analyze | SQL data-quality mart, recurring snapshots and Power BI quality dashboard | Planned |
| 4 — Communicate | Data-quality SOP, accountability model, root-cause case study and portfolio walkthrough | Planned |

The quality-focused engineering work is intended as portfolio evidence for **Data Quality Analyst, Data Steward, Master Data, Quality Operations, and BI/Reporting Analyst** roles.

**Author:** Kyle Haustein · Public learning project · 2026.
