# ProcureGuard issue investigation & closure SOP (synthetic demonstration)

**Document type:** Portfolio simulation / operating procedure draft
**Scope:** Fictional procurement CSV landing files, local case register, automated rule checks.
**Not a real organizational policy:** Names, assigned roles, root causes, corrective actions, and verifications shown in this project are all illustrative.

## Why this exists

A row can be flagged by several quality rules. A flagged row does not establish financial loss, fraud, a reporting error, or that the same company appears twice. An operational process needs: source-row traceability, accountable review, investigation notes, corrective actions, independent re-verification, and an event history.

## Roles

| Role | Responsibility in the demonstration |
|---|---|
| Data steward | Review exception, assign/refer ownership, document cause |
| Source owner | Investigate upstream mapping or correct fictional source feed |
| Reporting owner | Decide whether nominal/missing contract values can support KPIs |
| Independent verifier | Re-run the original quality check against the corrected synthetic source |
| System scanner | Detect new exceptions and record recurrence; never auto-close |

A real organization would define named owners, segregation of duties, SLAs, escalation and signoff authorization. **The MVP records an actor name, but it does not authenticate actors or enforce role segregation**; verification evidence demonstrates the rule outcome, not that an independent person was authorized.

## Status flow

\`\`\`text
                  assignment
Open ───────────────────────────┐
                                ▼
                           Investigating
                                |
                   root cause and corrective action
                                ▼
                       Pending Verification
                        |                 |
               check still fails      source row present,
                        |             original rule now passes
                        |                 |
                        └── stay pending  ▼
                                     Resolved
                                        |
                        if later scan sees same violation
                                        ▼
                                     Reopened
                                        |
                                investigate again
                                        ▼
                                  Investigating
\`\`\`

**Critical:** A proposed correction is not evidence that source data changed. A case is resolved only after a fresh evaluation confirms its particular rule violation is gone **and the original source row still exists**. If a source row simply disappears, verification fails pending a separately approved decommission process (not yet implemented).

## Procedure

1. **Ingest/synchronize:** Run \`python -m procureguard cases sync\`. This scans the original fictional files and imports each finding into \`build/governance.sqlite\` with its original rule details. It adds \`detected\` events for new cases. A recurring issue after verified closure becomes \`Reopened\`, with a new audit event.
2. **Triage:** \`python -m procureguard cases list\`. Inspect rule, affected field, source-row ID, severity and classification before deciding the appropriate subject-matter owner. The initial severity is an illustrative priority, not a proven legal/materiality ranking.
3. **Assign:** \`python -m procureguard cases assign ISSUE_ID --owner "Demo Steward" --actor "Demo Lead"\`.
4. **Investigate:** \`python -m procureguard cases investigate ISSUE_ID --cause "Fictional upstream source mapping omitted the field" --actor "Demo Steward"\`. Record a source-specific *hypothesis* or fictional diagnosis. For DQ-04, a name match is not proof of identity; for DQ-05, nominal values may be valid.
5. **Document corrective action:** \`python -m procureguard cases propose ISSUE_ID --action "Reconcile the fictional source field" --actor "Demo Steward"\`. The case enters \`Pending Verification\`.
6. **Verify:** Update an **authorized local synthetic input** and run \`python -m procureguard cases verify ISSUE_ID --actor "Demo Reviewer" --input path/to/data\`. The check writes an audit event whether it passes or fails. A failure is an explicit nonzero CLI exit status and the case remains pending.
7. **Review audit trail:** \`python -m procureguard cases history ISSUE_ID\`. Export all cases and events using \`python -m procureguard cases export\`.

## Provenance and traceability

- Each fictional raw CSV has a unique, immutable \`source_row_id\`; **it is a landing-record identifier, not a procurement business key**.
- Case IDs derive from the rule ID, source dataset, source-row ID and affected field, so row order and business-field correction do not break their identity.
- Every scan records a SHA-256 fingerprint of the four input CSV files and rule catalogue; verification events store a similar fingerprint and pass/fail outcome.
- Case events are **append-only in the application workflow**, and the SQLite database provides persistent local storage. It is *not* tamper-evident or cryptographically signed, and anyone with database file access can modify it.
- A scan does not close previously known issues simply because the finding is absent. Closure requires explicit verification and an existing source row.
- A resolved case reappearing in a later scan is reopened, clearing its obsolete root-cause and corrective-action statements while retaining the audit trail.

## Evidence example

\`python scripts/demo_lifecycle.py --output build/lifecycle_demo\`

The script copies all fictional inputs, selects the intentionally missing reported value for \`CON-0003\`, assigns a fictional steward, logs an illustrative cause, submits a planned action, records a **failed verification** (because the source still violates the rule), edits only the copied synthetic fixture, then records a **successful verification**. It exports the cases, audit events, and a JSON walkthrough. No private or operational source data is touched.

## Human controls not yet implemented

- Account authentication, authorization, immutable signed audit logs or approval segregation.
- A separately reviewed exception waiver when nominal \`1\` represents a legitimate reporting convention.
- Multi-user concurrency safeguards, ticket notifications or real-world incident SLAs.
- Verification of downstream KPIs, regulatory impact, or validated financial savings.
- Referential cleanup for a deliberately deleted source row.
- Production monitoring, repeat scheduling, BI warehouse snapshots or Power BI dashboards.

**Conclusion:** This milestone demonstrates auditable **workflows and validation gates**, not real organizational governance certification.
