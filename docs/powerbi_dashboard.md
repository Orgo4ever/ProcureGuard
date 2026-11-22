# Power BI dashboard — ProcureGuard

## Purpose

The three-page Power BI report communicates a fictional procurement data-quality process built with Python, SQLite case management, seven SQL reporting views, and exportable CSVs. It shows both current issue-management responsibilities and one controlled data-correction/verification example.

**Open the report:** [ProcureGuard_Dashboard.pbix](../Dashboards/ProcureGuard_Dashboard.pbix) (Power BI Desktop required).

## Report pages

| Page | Decision supported | Main visuals |
| --- | --- | --- |
| **1. Quality Overview** | Where are the current data-quality exceptions? | Four KPI cards, issues by rule, status donut, dataset/severity/status slicers |
| **2. Issue Management** | Which exceptions remain unresolved, who owns them, and what failed? | Unresolved/unassigned/high-priority KPIs, unresolved workload by owner, detailed case register and slicers |
| **3. Quality Trends & Performance** | What changed between the two demonstration scans and how did verification behave? | Initial/latest row pass-rate KPIs, verified resolutions, scan comparison, verification outcomes, written findings |

### Screenshots

[Quality Overview](../Dashboards/Screenshots/01_quality_overview.png) · [Issue Management](../Dashboards/Screenshots/02_issue_management.png) · [Quality Trends & Performance](../Dashboards/Screenshots/03_quality_trends.png)

## Metrics and interpretation

These are **synthetic demonstration values**, not production or historical business measurements.

| Metric | Demonstration value | Interpretation |
| --- | ---: | --- |
| Initial detected issues | 22 | Rule failures found during the initial scan |
| Current unresolved cases | 21 | Open cases remaining after the scripted correction |
| Resolved cases | 1 | Case resolved only after fresh-data verification |
| High-priority unresolved | 14 | Current unresolved backlog at High severity |
| Initial row-level pass rate | 42.11% | Proportion of source rows without any triggered issue in initial scan |
| Corrected row-level pass rate | 44.74% | Same metric after the fictional correction |
| Scan-to-scan improvement | +2.63 percentage points | Difference between the two pass rates, not a percent relative increase |
| Corrected-scan findings | 21 | One fewer finding than the initial scan |
| Failed / successful verifications | 1 / 1 | A verification failed against unchanged data, then succeeded after correction |

**Important boundaries:**
- **Issue count** is not the same as **affected row count**. A source row can trigger multiple rules.
- **Scan findings** are not identical to **open case backlog**. One refers to the selected scan; the other to current case state.
- **Two synthetic scan observations** do not establish a historical quality trend, sustained improvement, or real-world business effect.
- The assigned actors and users are illustrative, not authenticated identities. This is a local portfolio workflow, not enterprise production governance.
- Values flagged by DQ-04 and DQ-05 may require human interpretation; the demo does not prove supplier duplication, fraud, or incorrect financial reporting.

## Reproduce the reporting exports

Requires Python 3.11+ and the repository source:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/demo_lifecycle.py --output build/lifecycle_demo
python -m procureguard report --db build/lifecycle_demo/governance.sqlite --output build/powerbi
```

The report command creates seven `v_*.csv` files and `reporting_manifest.json` with reconciliation checks. Open the `.pbix` in Power BI Desktop. If Power BI cannot locate the CSVs after downloading the repository, update their local file paths through Power Query's data source settings to point to your generated `build/powerbi` directory. Then refresh.

**Implementation references:** [reporting definitions and data contract](reporting_layer.md) · [SQL view source](../sql/reporting_views.sql) · [case-management SOP](issue_management_sop.md).

## Scope

This report is a reproducible, offline demonstration of data-quality and governance design, reporting logic, and analyst communication. It does not connect to any real procurement systems, store personal data, or claim production monitoring, compliance certification, or operational financial impact.
