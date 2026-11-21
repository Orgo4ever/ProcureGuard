# Data quality rule catalogue — MVP

| Rule | Detection | Severity | Classification | Suggested owner |
|---|---|---|---|---|
| DQ-01 | Required primary/foreign key is blank | High | Validation error | Data steward |
| DQ-02 | Primary key appears more than once within its table | High | Validation error | Data steward |
| DQ-03 | Populated award/contract relationship cannot be resolved | High | Validation error | Data steward |
| DQ-04 | Two supplier IDs normalize to the same organization name | Medium | **Review flag** | Supplier master data owner |
| DQ-05 | Contract amount is blank, nominal £1 equivalent, or not numeric | Medium | **Review flag** | Reporting owner |
| DQ-06 | Invalid ISO date, end before start, or nonconforming three-letter currency format | Medium | Validation error | Procurement operations |

**Interpretation principles**

- A nominal amount of `1` is flagged as **unsuitable for unqualified spending analysis**, not automatically an error in the source.
- DQ-04 is a candidate duplicate based on a deliberately simple punctuation/whitespace-insensitive comparison. Names may be legitimately shared by distinct businesses; no automatic merge is performed.
- DQ-06 validates currency **format only**, not membership in the complete ISO 4217 code list or appropriate legal tender. It enforces `[A-Z]{3}` only.
- A missing foreign key is reported by DQ-01; a *populated but missing target* is reported by DQ-03.
- Row-level counts cannot be equated with financial risk, actual losses, or business savings.
- A `High` priority tells a data steward to investigate early. It does not represent a real SLA, regulatory classification, or validated operational impact.

## Demonstration and governance limits

All records and exception classifications are synthetic. These rules form a demonstration rule engine, not a certified data quality framework. **Milestone 2 now implements a local SQLite investigation and corrective-action workflow with required source-data revalidation and an event log.** See [issue-management SOP](issue_management_sop.md). Real user authentication, independent approval controls, enterprise audit protection, downstream KPI validation, recurring operational monitoring, reporting snapshots, and Power BI dashboards remain out of scope.
