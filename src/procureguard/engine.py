"""Deterministic data-quality checks for fictional procurement CSVs.

MVP: validation and exception export only. No real assignments, incident
closures, financial savings, or external-data connections are claimed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCHEMAS = {
    "procurements": ("procurement_id", "buyer_id", "method", "published_date"),
    "suppliers": ("supplier_id", "name", "country_code"),
    "awards": ("award_id", "procurement_id", "supplier_id"),
    "contracts": (
        "contract_id", "award_id", "reported_value", "currency",
        "start_date", "end_date",
    ),
}
PRIMARY_KEYS = {
    "procurements": "procurement_id",
    "suppliers": "supplier_id",
    "awards": "award_id",
    "contracts": "contract_id",
}
REQUIRED_IDENTIFIERS = {
    "procurements": ("procurement_id",),
    "suppliers": ("supplier_id",),
    "awards": ("award_id", "procurement_id", "supplier_id"),
    "contracts": ("contract_id", "award_id"),
}
RELATIONSHIPS = (
    ("awards", "procurement_id", "procurements", "procurement_id"),
    ("awards", "supplier_id", "suppliers", "supplier_id"),
    ("contracts", "award_id", "awards", "award_id"),
)
ISSUE_FIELDS = (
    "issue_id", "rule_id", "dataset", "record_id", "source_row_id", "row_number", "field",
    "severity", "classification", "owner_role", "status", "detail",
)


def read_tables(input_dir: Path) -> dict[str, list[dict]]:
    """Read a strict set of CSV landing tables; preserve physical line numbers."""
    tables = {}
    for table, columns in SCHEMAS.items():
        source = input_dir / f"{table}.csv"
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            if not headers:
                raise ValueError(f"{source}: missing header")
            if len(headers) != len(set(headers)):
                raise ValueError(f"{source}: duplicate CSV headers")
            missing_columns = set(columns) - set(headers)
            if missing_columns:
                raise ValueError(f"{source}: missing columns {sorted(missing_columns)}")
            rows = []
            has_source_row_id = "source_row_id" in headers
            seen_source_ids: set[str] = set()
            for line_number, raw in enumerate(reader, start=2):
                if None in raw or any(v is None for v in raw.values()):
                    raise ValueError(f"{source}: malformed row at line {line_number}")
                row = {name: (raw[name] or "").strip() for name in columns}
                row["_line"] = line_number
                row["_source_row_id"] = (raw.get("source_row_id") or "").strip()
                if has_source_row_id:
                    source_id = row["_source_row_id"]
                    if not source_id:
                        raise ValueError(f"{source}: blank source_row_id at line {line_number}")
                    if source_id in seen_source_ids:
                        raise ValueError(f"{source}: duplicate source_row_id {source_id!r}")
                    seen_source_ids.add(source_id)
                rows.append(row)
            tables[table] = rows
    return tables


def read_rules(path: Path) -> dict[str, dict]:
    """Read rule ownership and priority from an explicit, reviewable catalogue."""
    expected = {
        "rule_id", "title", "severity", "classification", "owner_role",
        "description",
    }
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not expected.issubset(reader.fieldnames):
            raise ValueError("Invalid rule catalogue header")
        rules = {}
        for row in reader:
            key = row["rule_id"].strip()
            if key in rules:
                raise ValueError(f"Duplicate rule: {key}")
            rules[key] = {k: (v or "").strip() for k, v in row.items()}
    required = {f"DQ-{n:02d}" for n in range(1, 7)}
    if set(rules) != required:
        raise ValueError(f"Rule catalogue must contain exactly {sorted(required)}")
    return rules


def _normal_name(name: str) -> str:
    """Very simple candidate-duplicate key; never sufficient for merging."""
    return re.sub(r"[\W_]+", "", name.casefold())


def _date(value: str) -> date | None:
    """Date-only ISO input; reject anything outside valid YYYY-MM-DD."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _issue(
    issues: list[dict], rules: dict[str, dict], code: str, table: str,
    row: dict, field: str, detail: str,
) -> None:
    rule = rules[code]
    # source_row_id preserves identity when a source CSV is reordered or
    # the content of a business field is corrected. Scan-only inputs without
    # source_row_id retain legacy line-based IDs; case tracking rejects those.
    identity = row.get("_source_row_id") or str(row["_line"])
    identifier = f"{code}|{table}|{identity}|{field}"
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12].upper()
    issues.append({
        "issue_id": f"PG-{digest}",
        "rule_id": code,
        "dataset": table,
        "record_id": row[PRIMARY_KEYS[table]] or "<missing>",
        "source_row_id": row.get("_source_row_id", ""),
        "row_number": row["_line"],
        "field": field,
        "severity": rule["severity"],
        "classification": rule["classification"],
        "owner_role": rule["owner_role"],
        "status": "Open",
        "detail": detail,
    })


def evaluate(tables: dict[str, list[dict]], rules: dict[str, dict]) -> list[dict]:
    """Apply six independent, explainable rules; never mutate source rows."""
    issues: list[dict] = []

    # DQ-01: required primary and foreign identifiers.
    for table, rows in tables.items():
        for row in rows:
            for field in REQUIRED_IDENTIFIERS[table]:
                if not row[field]:
                    _issue(issues, rules, "DQ-01", table, row, field,
                           f"Required identifier '{field}' is blank")

    # DQ-02: all records sharing a duplicate primary identifier are flagged.
    for table, rows in tables.items():
        pk = PRIMARY_KEYS[table]
        grouped = defaultdict(list)
        for row in rows:
            if row[pk]:
                grouped[row[pk]].append(row)
        for key, matched in grouped.items():
            if len(matched) > 1:
                for row in matched:
                    _issue(issues, rules, "DQ-02", table, row, pk,
                           f"Identifier '{key}' appears {len(matched)} times in {table}")

    # DQ-03: a populated relationship key must resolve in the parent set.
    for child, fk, parent, pk in RELATIONSHIPS:
        valid = {row[pk] for row in tables[parent] if row[pk]}
        for row in tables[child]:
            if row[fk] and row[fk] not in valid:
                _issue(issues, rules, "DQ-03", child, row, fk,
                       f"'{row[fk]}' does not resolve to {parent}.{pk}")

    # DQ-04: only possible supplier duplicates; distinct IDs are essential.
    name_groups = defaultdict(list)
    for row in tables["suppliers"]:
        name_key = _normal_name(row["name"])
        if name_key and row["supplier_id"]:
            name_groups[name_key].append(row)
    for matched in name_groups.values():
        ids = {row["supplier_id"] for row in matched}
        if len(ids) > 1:
            for row in matched:
                _issue(issues, rules, "DQ-04", "suppliers", row, "name",
                       f"Potential duplicate organization name across supplier IDs "
                       f"{', '.join(sorted(ids))}; human review required")

    # DQ-05: unusable reported amount, without asserting source-data errors.
    for row in tables["contracts"]:
        raw = row["reported_value"]
        reason = None
        if not raw:
            reason = "No amount reported; expenditure cannot be inferred"
        else:
            try:
                amount = Decimal(raw)
                if not amount.is_finite():
                    reason = "Non-finite amount is unusable for reporting"
                elif amount == Decimal("1"):
                    reason = "Nominal amount 1; investigate reporting convention before treating as spend"
            except InvalidOperation:
                reason = "Unparseable amount; expenditure cannot be inferred"
        if reason is not None:
            _issue(issues, rules, "DQ-05", "contracts", row, "reported_value", reason)

    # DQ-06: valid ISO dates, realistic date order and currency code format.
    for row in tables["procurements"]:
        if _date(row["published_date"]) is None:
            _issue(issues, rules, "DQ-06", "procurements", row, "published_date",
                   "Date is missing or is not a valid YYYY-MM-DD calendar date")
    for row in tables["contracts"]:
        dates = {}
        for field in ("start_date", "end_date"):
            parsed = _date(row[field])
            dates[field] = parsed
            if parsed is None:
                _issue(issues, rules, "DQ-06", "contracts", row, field,
                       "Date is missing or is not a valid YYYY-MM-DD calendar date")
        if dates["start_date"] and dates["end_date"]:
            if dates["start_date"] > dates["end_date"]:
                _issue(issues, rules, "DQ-06", "contracts", row, "end_date",
                       "Contract end date precedes start date")
        if not re.fullmatch(r"[A-Z]{3}", row["currency"]):
            _issue(issues, rules, "DQ-06", "contracts", row, "currency",
                   "Currency must use a three-uppercase-letter format (ISO membership not verified)")

    index = {name: position for position, name in enumerate(SCHEMAS)}
    issues.sort(key=lambda x: (
        index[x["dataset"]], x["row_number"], x["rule_id"], x["field"]
    ))
    return issues


def summarize(tables: dict[str, list[dict]], issues: list[dict]) -> dict:
    total_rows = sum(len(rows) for rows in tables.values())
    affected = {(x["dataset"], x["row_number"]) for x in issues}
    count_by_rule = Counter(x["rule_id"] for x in issues)
    count_by_severity = Counter(x["severity"] for x in issues)
    passing = total_rows - len(affected)
    return {
        "source": "synthetic demonstration only",
        "dataset_rows": {table: len(rows) for table, rows in tables.items()},
        "rows_scanned": total_rows,
        "issues_found": len(issues),
        "distinct_rows_with_issues": len(affected),
        "rows_passing_all_rules": passing,
        "row_pass_rate_pct": round(100 * passing / total_rows, 2) if total_rows else None,
        "issues_by_rule": {f"DQ-{n:02d}": count_by_rule[f"DQ-{n:02d}"]
                           for n in range(1, 7)},
        "issues_by_severity": dict(sorted(count_by_severity.items())),
        "status_note": "All issues are newly Open; no resolution workflow implemented yet",
    }


def run(input_dir: Path, rules_path: Path, output_dir: Path) -> dict:
    """Validate, write a machine-readable issue register, and return summary."""
    tables = read_tables(input_dir)
    rules = read_rules(rules_path)
    issues = evaluate(tables, rules)
    summary = summarize(tables, issues)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "issues.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ISSUE_FIELDS)
        writer.writeheader()
        writer.writerows(issues)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary
