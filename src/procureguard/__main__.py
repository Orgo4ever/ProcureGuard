"""CLI entry point: python -m procureguard."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import ROOT, run


def main() -> None:
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
    print(json.dumps(report, indent=2))
    print(f"\nWritten: {args.output / 'issues.csv'}")
    print(f"Written: {args.output / 'summary.json'}")


if __name__ == "__main__":
    main()
