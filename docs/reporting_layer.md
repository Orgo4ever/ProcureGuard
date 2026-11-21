# ProcureGuard reporting layer — SQLite views and Power BI CSV exports

**Milestone 3, stage 1: implemented.** This is a reproducible reporting foundation, **not yet a Power BI dashboard**. The project includes only synthetic procurement records and simulated case activity.

## Reproduce the demo

Requires Python 3.11+ and the standard library, plus editable installation of the local package.

\`\`\`bash
git clone https://github.com/Orgo4ever/ProcureGuard.git
cd ProcureGuard
python -m pip install -e .
python -m unittest discover -s tests -v

# Creates a separate local SQLite database and fictional resolution history.
python scripts/demo_lifecycle.py --output build/lifecycle_demo

# Installs/replaces SQLite views in that database and exports reporting CSVs.
python -m procureguard report \
  --db build/lifecycle_demo/governance.sqlite \
  --output build/powerbi
\`\`\`

On Windows PowerShell, run the final report command on one line or use PowerShell backticks instead of the shell backslash. The files live under \`build/powerbi/\` and are ignored by Git.

Alternatively, for your own local case register:

\`\`\`bash
python -m procureguard cases sync
python -m procureguard report
\`\`\`

The second workflow includes only the issues detected in the present fictional source. It does not show the simulated closed case until you run \`scripts/demo_lifecycle.py\`.

## SQL views

Source of truth: [sql/reporting_views.sql](../sql/reporting_views.sql). The view DDL is **SQLite** syntax for the existing \`governance.sqlite\` database, not MySQL. It is idempotent and creates views rather than modifying the underlying case records.

| View / output CSV | Row grain | Dashboard purpose |
|---|---|---|
| \`v_case_details\` | One row per unique issue/case | Detailed case register: priority, status, owner, identifiers, date, review flag |
| \`v_case_kpis\` | One aggregate row | Current total, unresolved, resolved, owner gaps, pending verification, cases in latest scan |
| \`v_rule_metrics\` | One row per rule/severity/classification/owner role with a case | Rule-level exception counts and closure comparison |
| \`v_owner_workload\` | One row per current owner display, owner role and severity | Current unresolved backlog by person/role and priority |
| \`v_scan_quality_trend\` | One row per recorded scan | Source-row pass rate and issue observations for each scan |
| \`v_case_activity_daily\` | One row per event calendar date and event action | How many assignments, investigations, failed checks, and verified resolutions were recorded |
| \`v_verification_metrics\` | One row per case | Verification attempts, failures, successes and latest verification date |

There is also a \`reporting_manifest.json\` containing reconciliation results and export record counts.

### Definitions and caveats

**Case vs finding:** The engine reports quality *findings* for a given input scan. The case register retains a stable issue ID across rescans. A historical case can remain \`Resolved\` when not seen in the latest scan; it is only \`Reopened\` if the same violation is found again.

**Current backlog:** \`unresolved_cases\` counts cases in \`Open\`, \`Investigating\`, \`Pending Verification\`, or \`Reopened\`. It includes cases that were *not seen in the latest scan* but have not been formally verified and resolved. These cases might require investigation rather than an automatic closure. Use \`seen_in_latest_scan\` to distinguish them.

**Current case status is not historical status:** No view reconstructs month-end backlog as of a previous date. \`v_scan_quality_trend\` uses the actual \`scan_runs\` observations—number of scanned rows, findings and distinct affected rows—not today's case statuses. Do not plot historical backlog from today's \`v_case_details\`.

**Row pass rate:** \`100 × (rows_scanned − affected_rows) / rows_scanned\`. An affected row is counted once even if it violates several rules. Scans with no rows have \`NULL\` pass rate.

**Open age:** \`julianday('now') - julianday(first_seen)\` for unresolved cases; it changes as time passes. **Resolution time** is the elapsed time from initial detection to verified closure for cases currently marked \`Resolved\`. Quick demo activity can have a zero-day duration, and it is *not* a production SLA metric.

**Rule metrics:** Rule counts describe recorded **cases**, not necessarily the current scan's findings. The rule catalogue is independently available in \`config/quality_rules.csv\`; a rule with zero cases will not appear in \`v_rule_metrics\`. Severity and ownership are illustrative, not regulatory classifications or authenticated assignments.

**Verification:** Failure and success counts are *audit events* from a fictional validation process. They do not prove independent organizational approval, fraud detection, regulatory compliance, or financial impact.

## Reconciliation controls

The export refuses to run unless at least one scan exists. Before writing CSV files it cross-checks:

- Current case count equals the persisted \`cases\` table count.
- Resolved plus unresolved equals all current cases.
- The latest scan's stored findings count equals the \`scan_findings\` detail count.
- The count of cases flagged \`seen_in_latest_scan\` equals that same finding count.

The synthetic fixture initially has **38 records and 22 findings** (42.11% row pass rate). After running the standalone demo, one fictitious contract value has been corrected in a *copied* input folder, so the second scan reports **21 findings**, **one resolved case** and **21 unresolved cases**. The second pass rate is **44.74%**, not a claim about real procurement operations.

Regression tests in \`tests/test_reporting.py\` verify the SQL results, export rows, and reconciliation against both stages.

## Power BI Desktop: practical import plan

1. Run the commands above; open Power BI Desktop → **Get data → Text/CSV**, and import the seven generated \`v_*.csv\` files.
2. For a simple first report, use \`v_case_kpis\` for KPI cards, \`v_rule_metrics\` for a rule bar chart, \`v_owner_workload\` for a backlog matrix, and \`v_case_details\` for a detailed case table.
3. Use \`v_scan_quality_trend\` for scan number vs. row pass rate, **labeling the chart “synthetic scan observations.”** Do not imply that multiple same-day scans are a months-long operational trend.
4. Use \`v_verification_metrics\` to show successful vs. failed checks, and \`v_case_activity_daily\` for a breakdown of documented events.
5. **Treat pre-aggregated tables as separate reporting outputs.** Do not arbitrarily create relationships between \`v_case_kpis\`, \`v_rule_metrics\`, \`v_scan_quality_trend\` and \`v_case_details\`: their different grains can cause double counting. When interactive filtering by rule, owner or status is needed, build measures from the row-level \`v_case_details\` table (e.g., distinct count of \`issue_id\`) instead.
6. Cross-check the displayed totals against \`reporting_manifest.json\` and \`v_case_kpis.csv\` before publishing screenshots.

The project's original table model and rules are described in [data_dictionary.md](data_dictionary.md); the investigation and closure process is in [issue_management_sop.md](issue_management_sop.md).

## What remains to build

The next stage is the **native Power BI dashboard**: layout, DAX measures for dynamic filtering, report interactions, reconciliation screenshots and an honest portfolio case study. A long-running historical dataset and point-in-time case-status snapshots are *not currently implemented*; the current synthetic demo only proves the initial and corrected scans.
