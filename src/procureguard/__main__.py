"""CLI: scan raw CSVs and manage synthetic ProcureGuard issues in SQLite."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import ROOT, run
from .cases import (
    GovernanceError, assign, connect, export_cases, get_case, history,
    investigate, list_cases, propose, sync_scan, verify,
)


def _dump(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def cases_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="python -m procureguard cases")
    commands = parser.add_subparsers(dest="command", required=True)

    def common(name: str, help_text: str, input_file: bool = False):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--db", type=Path, default=ROOT / "build" / "governance.sqlite",
                         help="Private local SQLite case database")
        if input_file:
            sub.add_argument("--input", type=Path, default=ROOT / "data" / "synthetic")
            sub.add_argument("--rules", type=Path, default=ROOT / "config" / "quality_rules.csv")
        return sub

    common("sync", "Rescan sources and open or reopen cases", input_file=True)
    cmd = common("list", "List cases and their statuses")
    cmd.add_argument("--status", choices=[
        "Open", "Investigating", "Pending Verification", "Resolved", "Reopened",
    ])
    cmd = common("show", "Inspect one case")
    cmd.add_argument("issue_id")
    cmd = common("history", "View the append-only audit events for a case")
    cmd.add_argument("issue_id")
    cmd = common("assign", "Assign an owner to an open case")
    cmd.add_argument("issue_id")
    cmd.add_argument("--owner", required=True)
    cmd.add_argument("--actor", required=True)
    cmd = common("investigate", "Record an investigation root cause")
    cmd.add_argument("issue_id")
    cmd.add_argument("--cause", required=True)
    cmd.add_argument("--actor", required=True)
    cmd = common("propose", "Submit a corrective action for verification")
    cmd.add_argument("issue_id")
    cmd.add_argument("--action", required=True)
    cmd.add_argument("--actor", required=True)
    cmd = common("verify", "Re-evaluate the source data before resolving")
    cmd.add_argument("issue_id")
    cmd.add_argument("--actor", required=True)
    cmd.add_argument("--input", type=Path, default=ROOT / "data" / "synthetic")
    cmd.add_argument("--rules", type=Path, default=ROOT / "config" / "quality_rules.csv")
    cmd = common("export", "Export case register, audit events, status summary")
    cmd.add_argument("--output", type=Path, default=ROOT / "build" / "governance")

    args = parser.parse_args(argv)
    try:
        with connect(args.db) as db:
            if args.command == "sync":
                result = sync_scan(db, args.input, args.rules)
            elif args.command == "list":
                result = list_cases(db, args.status)
            elif args.command == "show":
                result = get_case(db, args.issue_id)
            elif args.command == "history":
                result = history(db, args.issue_id)
            elif args.command == "assign":
                result = assign(db, args.issue_id, args.owner, args.actor)
            elif args.command == "investigate":
                result = investigate(db, args.issue_id, args.actor, args.cause)
            elif args.command == "propose":
                result = propose(db, args.issue_id, args.actor, args.action)
            elif args.command == "verify":
                result = verify(db, args.issue_id, args.actor, args.input, args.rules)
            elif args.command == "export":
                result = export_cases(db, args.output)
            else:
                raise GovernanceError(f"Unsupported command: {args.command}")
        _dump(result)
        if args.command == "verify" and not result["verified"]:
            raise SystemExit(2)
    except (GovernanceError, ValueError) as exc:
        parser.exit(2, f"Governance validation error: {exc}\n")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "cases":
        cases_main(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(
        description="ProcureGuard — synthetic procurement data-quality validation"
    )
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "synthetic",
                        help="Directory containing the four procurement CSV files")
    parser.add_argument("--rules", type=Path, default=ROOT / "config" / "quality_rules.csv",
                        help="Rule catalogue CSV")
    parser.add_argument("--output", type=Path, default=ROOT / "build",
                        help="Directory for issues.csv and summary.json")
    args = parser.parse_args()
    report = run(args.input, args.rules, args.output)
    _dump(report)
    print(f"\nWritten: {args.output / 'issues.csv'}")
    print(f"Written: {args.output / 'summary.json'}")


if __name__ == "__main__":
    main()
