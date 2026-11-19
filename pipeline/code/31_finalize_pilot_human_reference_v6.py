#!/usr/bin/env python3
"""Validate Pilot adjudication and freeze a 150-record human reference set.

This program is local-only. It revalidates the two locked human annotation
workbooks, checks the completed adjudication workbook against the frozen
disagreement list, and merges exact A/B agreements with adjudicated records.
Records that remain uncertain are retained but excluded from the primary model
performance denominator.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
SCHEMA_VERSION = "af-pilot-human-reference-v1"
REPORT_SCHEMA_VERSION = "af-pilot-human-reference-report-v1"

DEFAULTS = {
    "annotator_a": "fulltext/pilot/human_annotation_v6/repaired/pilot_150_annotator_A_repaired_v6.xlsx",
    "annotator_b": "fulltext/pilot/human_annotation_v6/repaired/pilot_150_annotator_B_repaired_v6.xlsx",
    "assignment_a": "fulltext/pilot/human_annotation_v6/pilot_150_annotator_a_assignment_v6.json",
    "assignment_b": "fulltext/pilot/human_annotation_v6/pilot_150_annotator_b_assignment_v6.json",
    "packets": "fulltext/pilot/human_annotation_v6/pilot_150_human_packets_blinded_v6.jsonl",
    "pilot": "fulltext/pilot/pilot_150.csv",
    "validation_report": "fulltext/pilot/human_annotation_v6/results_repaired/pilot_150_human_validation_report_repaired_v6.json",
    "disagreements": "fulltext/pilot/human_annotation_v6/results_repaired/pilot_150_human_disagreements_repaired_v6.csv",
    "adjudication": "fulltext/pilot/human_annotation_v6/adjudication/pilot_150_human_adjudication_109_v6_adjudicated_completed.xlsx",
    "output_dir": "fulltext/pilot/human_annotation_v6/final",
}

ADJUDICATION_HEADERS = [
    "adjudication_order",
    "review_id",
    "work_id",
    "title",
    "disagreement_fields",
    "annotator_a_primary_label",
    "annotator_a_relevance_level",
    "annotator_a_evidence_level",
    "annotator_a_af_related_label",
    "annotator_a_af_use_label",
    "annotator_a_adoption_eligible",
    "annotator_a_future_or_hypothetical_only",
    "annotator_a_observed_actions",
    "annotator_b_primary_label",
    "annotator_b_relevance_level",
    "annotator_b_evidence_level",
    "annotator_b_af_related_label",
    "annotator_b_af_use_label",
    "annotator_b_adoption_eligible",
    "annotator_b_future_or_hypothetical_only",
    "annotator_b_observed_actions",
    "adjudicated_primary_label",
    "adjudicated_relevance_level",
    "adjudicated_evidence_level",
    "adjudicated_af_related_label",
    "adjudicated_af_use_label",
    "adjudicated_adoption_eligible",
    "adjudicated_future_or_hypothetical_only",
    "adjudicated_observed_actions",
    "adjudication_evidence_valid",
    "adjudicator_id",
    "adjudication_date",
    "adjudication_notes",
    "adjudication_status",
]

REFERENCE_FIELDS = [
    "primary_label",
    "relevance_level",
    "evidence_level",
    "af_related_label",
    "af_use_label",
    "adoption_eligible",
    "future_or_hypothetical_only",
    "observed_actions",
]

ACTION_ORDER = [
    "retrieved_precomputed_structure",
    "ran_alphafold",
    "ran_colabfold",
    "integrated_empirical_workflow",
    "docking_or_screening",
    "benchmarked_or_evaluated",
    "modified_or_extended",
    "developed_downstream_tool",
    "discussion_only",
    "none",
]
ACTION_SET = set(ACTION_ORDER)
ACTUAL_USE_ACTIONS = ACTION_SET - {"discussion_only", "none"}

PRIMARY_LABELS = {
    "FP",
    "background_only",
    "review_discussion",
    "database_consumption",
    "model_application",
    "method_development",
    "original_platform",
    "uncertain",
}
RELEVANCE_LEVELS = {"R0", "R1", "R2", "R3", "R4", "RU"}
EVIDENCE_LEVELS = {"E0", "E1", "E2", "E3"}
RELATED_LABELS = {"false", "background", "related", "uncertain"}
TERNARY_LABELS = {"no", "yes", "uncertain"}
BOOLEAN_LABELS = {"no", "yes"}

EXPECTED_BY_PRIMARY = {
    "FP": ("R0", "false", "no", "no"),
    "background_only": ("R1", "background", "no", "no"),
    "review_discussion": ("R2", "related", "no", "no"),
    "database_consumption": ("R3", "related", "yes", "yes"),
    "model_application": ("R3", "related", "yes", "yes"),
    "method_development": ("R4", "related", "yes", "yes"),
    "original_platform": ("R4", "related", "yes", "no"),
}


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def split_actions(value: Any) -> tuple[str, ...]:
    text = norm(value)
    for separator in ("；", "，", ",", ";"):
        text = text.replace(separator, "|")
    found = {item.strip() for item in text.split("|") if item.strip()}
    return tuple(action for action in ACTION_ORDER if action in found)


def normalized_field(row: dict[str, Any], field: str) -> str:
    if field.endswith("observed_actions"):
        return "|".join(split_actions(row.get(field)))
    return norm(row.get(field))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    digest = sha256_bytes(data)
    checksum = path.with_name(path.name + ".sha256")
    checksum_tmp = checksum.with_suffix(checksum.suffix + ".part")
    checksum_tmp.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    checksum_tmp.replace(checksum)
    return digest


def write_json(path: Path, value: Any) -> str:
    return atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> str:
    data = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    ).encode("utf-8")
    return atomic_write(path, data)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    import io

    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return atomic_write(path, handle.getvalue().encode("utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            records.append(value)
    return records


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def unique(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        review_id = norm(row.get("review_id"))
        if not review_id:
            raise ValueError(f"{label}: missing review_id")
        if review_id in result:
            raise ValueError(f"{label}: duplicate review_id {review_id}")
        result[review_id] = row
    return result


def load_validation_module() -> Any:
    path = CODE_ROOT / "23_validate_pilot_human_annotations.py"
    spec = importlib.util.spec_from_file_location("pilot_human_validation_v6", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load validation module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workbook_key_values(workbook: Any, sheet_name: str) -> dict[str, str]:
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Workbook is missing {sheet_name} sheet")
    result: dict[str, str] = {}
    for row in workbook[sheet_name].iter_rows(max_col=2, values_only=True):
        key = norm(row[0])
        if key and key not in {"field", "Reproducibility metadata"}:
            result[key] = norm(row[1])
    return result


def read_adjudication(path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    required = {
        "Instructions",
        "Adjudication",
        "A-B Evidence",
        "Paper Text",
        "Evidence Blocks",
        "Codebook",
        "Metadata",
    }
    missing = sorted(required - set(workbook.sheetnames))
    if missing:
        raise ValueError(f"Adjudication workbook is missing sheets: {missing}")
    sheet = workbook["Adjudication"]
    values = list(sheet.iter_rows(values_only=True))
    if not values:
        raise ValueError("Adjudication sheet is empty")
    headers = [norm(value) for value in values[0]]
    if headers != ADJUDICATION_HEADERS:
        raise ValueError("Adjudication header does not match the locked workbook schema")
    rows = [
        dict(zip(headers, row, strict=True))
        for row in values[1:]
        if any(norm(value) for value in row)
    ]
    return rows, workbook_key_values(workbook, "Metadata")


def valid_iso_date(value: Any) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    try:
        date.fromisoformat(norm(value))
    except ValueError:
        return False
    return True


def validate_adjudicated_values(row: dict[str, Any], row_number: int) -> list[str]:
    errors: list[str] = []
    values = {
        field: normalized_field(row, f"adjudicated_{field}") for field in REFERENCE_FIELDS
    }
    for field, allowed in (
        ("primary_label", PRIMARY_LABELS),
        ("relevance_level", RELEVANCE_LEVELS),
        ("evidence_level", EVIDENCE_LEVELS),
        ("af_related_label", RELATED_LABELS),
        ("af_use_label", TERNARY_LABELS),
        ("adoption_eligible", TERNARY_LABELS),
        ("future_or_hypothetical_only", BOOLEAN_LABELS),
    ):
        if values[field] not in allowed:
            errors.append(f"row {row_number} adjudicated_{field}: invalid {values[field]!r}")

    actions = set(split_actions(row.get("adjudicated_observed_actions")))
    raw_actions = {
        item.strip()
        for item in norm(row.get("adjudicated_observed_actions"))
        .replace("；", "|")
        .replace("，", "|")
        .replace(",", "|")
        .replace(";", "|")
        .split("|")
        if item.strip()
    }
    unknown = raw_actions - ACTION_SET
    if not actions:
        errors.append(f"row {row_number} adjudicated_observed_actions: required")
    if unknown:
        errors.append(f"row {row_number} adjudicated_observed_actions: unknown {sorted(unknown)}")
    if "none" in actions and len(actions) > 1:
        errors.append(f"row {row_number}: none cannot coexist with another action")
    if "discussion_only" in actions and actions & ACTUAL_USE_ACTIONS:
        errors.append(f"row {row_number}: discussion_only cannot coexist with actual use")

    primary = values["primary_label"]
    if primary in EXPECTED_BY_PRIMARY:
        observed = (
            values["relevance_level"],
            values["af_related_label"],
            values["af_use_label"],
            values["adoption_eligible"],
        )
        if observed != EXPECTED_BY_PRIMARY[primary]:
            errors.append(
                f"row {row_number} primary consistency: expected "
                f"{EXPECTED_BY_PRIMARY[primary]}, found {observed}"
            )
    elif primary == "uncertain" and values["relevance_level"] != "RU":
        errors.append(f"row {row_number}: primary uncertain requires relevance_level=RU")

    if values["evidence_level"] in {"E0", "E1"} and (
        values["af_use_label"] == "yes" or values["adoption_eligible"] == "yes"
    ):
        errors.append(f"row {row_number}: E0/E1 cannot establish actual use or adoption")
    if actions & ACTUAL_USE_ACTIONS and values["af_use_label"] != "yes":
        errors.append(f"row {row_number}: actual-use action requires af_use_label=yes")
    if values["future_or_hypothetical_only"] == "yes" and (
        values["af_use_label"] == "yes"
        or values["adoption_eligible"] == "yes"
        or actions & ACTUAL_USE_ACTIONS
    ):
        errors.append(f"row {row_number}: future-only conflicts with actual use")

    evidence_valid = norm(row.get("adjudication_evidence_valid"))
    if evidence_valid not in BOOLEAN_LABELS:
        errors.append(f"row {row_number} adjudication_evidence_valid: invalid {evidence_valid!r}")
    if evidence_valid == "no" and primary != "uncertain":
        errors.append(
            f"row {row_number}: evidence_valid=no must remain primary_label=uncertain"
        )
    if norm(row.get("adjudication_status")) != "complete":
        errors.append(f"row {row_number} adjudication_status: expected complete")
    for field in ("adjudicator_id", "adjudication_date", "adjudication_notes"):
        if not norm(row.get(field)):
            errors.append(f"row {row_number} {field}: required")
    if not valid_iso_date(row.get("adjudication_date")):
        errors.append(f"row {row_number} adjudication_date: expected ISO date")
    return errors


def validate_adjudication(
    rows: list[dict[str, Any]],
    disagreements: list[dict[str, Any]],
    metadata: dict[str, str],
    input_paths: dict[str, Path],
) -> list[str]:
    errors: list[str] = []
    expected_metadata = {
        "workbook_schema_version": "af-human-adjudication-workbook-v1",
        "records_requiring_adjudication": str(len(disagreements)),
        "disagreements_sha256": sha256_file(input_paths["disagreements"]),
        "annotator_a_sha256": sha256_file(input_paths["annotator_a"]),
        "annotator_b_sha256": sha256_file(input_paths["annotator_b"]),
        "packet_file_sha256": sha256_file(input_paths["packets"]),
        "validation_report_sha256": sha256_file(input_paths["validation_report"]),
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            errors.append(
                f"metadata {key}: expected {expected!r}, found {metadata.get(key)!r}"
            )

    if len(rows) != len(disagreements):
        errors.append(
            f"adjudication record_count: expected {len(disagreements)}, found {len(rows)}"
        )
        return errors

    for row_number, (row, expected) in enumerate(zip(rows, disagreements, strict=True), 2):
        for field in ("review_id", "work_id", "title", "disagreement_fields"):
            if norm(row.get(field)) != norm(expected.get(field)):
                errors.append(
                    f"row {row_number} {field}: expected {expected.get(field)!r}, "
                    f"found {row.get(field)!r}"
                )
        if norm(row.get("adjudication_order")) != str(row_number - 1):
            errors.append(f"row {row_number} adjudication_order: sequence mismatch")
        for annotator in ("a", "b"):
            for field in REFERENCE_FIELDS:
                actual = normalized_field(row, f"annotator_{annotator}_{field}")
                wanted = normalized_field(expected, f"annotator_{annotator}_{field}")
                if actual != wanted:
                    errors.append(
                        f"row {row_number} annotator_{annotator}_{field}: locked value changed"
                    )
        errors.extend(validate_adjudicated_values(row, row_number))
    return errors


def source_values(row: dict[str, Any], prefix: str = "") -> dict[str, str]:
    return {
        field: normalized_field(row, f"{prefix}{field}") for field in REFERENCE_FIELDS
    }


def reference_status(route: str, evidence_valid: str, primary_label: str) -> str:
    if evidence_valid == "no":
        return "unresolved_evidence"
    if primary_label == "uncertain":
        return "uncertain_consensus" if route == "ab_exact_agreement" else "uncertain_adjudicated"
    return "resolved"


def build_reference_records(
    packets: list[dict[str, Any]],
    pilot_rows: list[dict[str, Any]],
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    adjudication_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pilot_by_work = {norm(row["work_id"]): row for row in pilot_rows}
    by_a = unique(rows_a, "annotator A")
    by_b = unique(rows_b, "annotator B")
    by_adj = unique(adjudication_rows, "adjudication")
    records: list[dict[str, Any]] = []

    for packet_order, packet in enumerate(packets, 1):
        review_id = norm(packet.get("review_id"))
        work_id = norm(packet.get("work_id"))
        row_a = by_a[review_id]
        row_b = by_b[review_id]
        values_a = source_values(row_a)
        values_b = source_values(row_b)
        differing = [
            field for field in REFERENCE_FIELDS if values_a[field] != values_b[field]
        ]
        if differing:
            adjudicated = by_adj.get(review_id)
            if adjudicated is None:
                raise ValueError(f"Missing adjudication for {review_id}")
            final_values = source_values(adjudicated, "adjudicated_")
            route = "human_adjudication"
            evidence_valid = norm(adjudicated["adjudication_evidence_valid"])
            adjudication = {
                "adjudicator_id": norm(adjudicated["adjudicator_id"]),
                "adjudication_date": norm(adjudicated["adjudication_date"]),
                "adjudication_notes": norm(adjudicated["adjudication_notes"]),
            }
        else:
            final_values = values_a
            route = "ab_exact_agreement"
            evidence_valid = "yes"
            adjudication = {
                "adjudicator_id": "",
                "adjudication_date": "",
                "adjudication_notes": "",
            }

        status = reference_status(route, evidence_valid, final_values["primary_label"])
        pilot = pilot_by_work.get(work_id)
        if pilot is None:
            raise ValueError(f"Pilot row not found for {work_id}")
        material = packet.get("input_material") or {}
        record = {
            "schema_version": SCHEMA_VERSION,
            "pilot_order": int(pilot.get("pilot_order") or packet_order),
            "review_id": review_id,
            "work_id": work_id,
            "title": norm(material.get("title") or pilot.get("title")),
            "publication_year": int(pilot["publication_year"]) if norm(pilot.get("publication_year")) else None,
            "work_type": norm(pilot.get("work_type")),
            "doi": norm(pilot.get("doi")),
            "domain_labels": norm(pilot.get("domain_labels")),
            "reference_route": route,
            "reference_status": status,
            "metric_eligible": status == "resolved",
            "human_evidence_valid": evidence_valid,
            "disagreement_fields": "|".join(differing),
            **{f"reference_{field}": value for field, value in final_values.items()},
            "annotator_a": values_a,
            "annotator_b": values_b,
            "adjudication": adjudication,
            "sampling": {
                "retrieval_sampling_stratum": norm(pilot.get("af_usage_level")),
                "year_band": norm(pilot.get("year_band")),
                "inclusion_probability": float(pilot["inclusion_probability"]),
                "sampling_weight": float(pilot["sampling_weight"]),
                "selection_hash": norm(pilot.get("selection_hash")),
                "sampling_seed": int(pilot["sampling_seed"]),
            },
        }
        records.append(record)

    extra = sorted(set(by_adj) - {record["review_id"] for record in records})
    if extra:
        raise ValueError(f"Adjudication contains unexpected review IDs: {extra}")
    records.sort(key=lambda row: row["pilot_order"])
    return records


def flatten_reference(record: dict[str, Any]) -> dict[str, Any]:
    flat = {
        key: record[key]
        for key in (
            "pilot_order",
            "review_id",
            "work_id",
            "title",
            "publication_year",
            "work_type",
            "doi",
            "domain_labels",
            "reference_route",
            "reference_status",
            "metric_eligible",
            "human_evidence_valid",
            "disagreement_fields",
        )
    }
    for field in REFERENCE_FIELDS:
        flat[f"reference_{field}"] = record[f"reference_{field}"]
    flat.update(record["adjudication"])
    flat.update(record["sampling"])
    return flat


def count_field(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(norm(record.get(field)) for record in records))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in (
        "annotator_a",
        "annotator_b",
        "assignment_a",
        "assignment_b",
        "packets",
        "pilot",
        "validation_report",
        "disagreements",
        "adjudication",
        "output_dir",
    ):
        parser.add_argument(
            "--" + argument.replace("_", "-"),
            type=Path,
            default=Path(DEFAULTS[argument]),
        )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = {
        key: resolve(getattr(args, key))
        for key in DEFAULTS
        if key != "output_dir"
    }
    output_dir = resolve(args.output_dir)
    for label, path in paths.items():
        if not path.is_file():
            raise ValueError(f"Missing {label}: {path}")

    validation = load_validation_module()
    packets = read_jsonl(paths["packets"])
    packet_by_id = unique(packets, "packets")
    pilot_rows = read_csv(paths["pilot"])
    assignment_a = json.loads(paths["assignment_a"].read_text(encoding="utf-8"))
    assignment_b = json.loads(paths["assignment_b"].read_text(encoding="utf-8"))
    workbook_a = load_workbook(paths["annotator_a"], read_only=True, data_only=False)
    workbook_b = load_workbook(paths["annotator_b"], read_only=True, data_only=False)
    rows_a = validation.annotation_rows(workbook_a)
    rows_b = validation.annotation_rows(workbook_b)
    metadata_a = validation.workbook_metadata(workbook_a)
    metadata_b = validation.workbook_metadata(workbook_b)

    errors = [
        *(f"A identity: {message}" for message in validation.validate_identity(rows_a, assignment_a, metadata_a)),
        *(f"B identity: {message}" for message in validation.validate_identity(rows_b, assignment_b, metadata_b)),
    ]
    for annotator, rows in (("A", rows_a), ("B", rows_b)):
        for row_number, row in enumerate(rows, 2):
            review_id = norm(row["review_id"])
            if norm(row["status"]) != "complete":
                errors.append(f"{annotator}: row {row_number} is not complete")
                continue
            packet = packet_by_id.get(review_id)
            if packet is None:
                errors.append(f"{annotator}: row {row_number} missing packet")
                continue
            errors.extend(
                f"{annotator}: {message}"
                for message in validation.validate_completed_row(row, packet, row_number)
            )

    agreement, expected_disagreements = validation.build_agreement(rows_a, rows_b)
    disagreements = read_csv(paths["disagreements"])
    if expected_disagreements != disagreements:
        errors.append("Frozen disagreement CSV no longer matches the revalidated A/B workbooks")
    saved_validation = json.loads(paths["validation_report"].read_text(encoding="utf-8"))
    if not saved_validation.get("ready_for_adjudication"):
        errors.append("Saved A/B validation report is not ready_for_adjudication")
    if saved_validation.get("agreement", {}).get("records_requiring_adjudication") != len(disagreements):
        errors.append("Saved validation report disagreement count does not match the CSV")

    adjudication_rows, adjudication_metadata = read_adjudication(paths["adjudication"])
    errors.extend(
        validate_adjudication(adjudication_rows, disagreements, adjudication_metadata, paths)
    )
    if errors:
        preview = "\n".join(f"- {message}" for message in errors[:50])
        raise ValueError(f"Human reference validation failed ({len(errors)} errors):\n{preview}")

    records = build_reference_records(
        packets, pilot_rows, rows_a, rows_b, adjudication_rows
    )
    if len(records) != 150:
        raise ValueError(f"Expected 150 reference records, found {len(records)}")
    status_counts = Counter(record["reference_status"] for record in records)
    route_counts = Counter(record["reference_route"] for record in records)
    eligible = [record for record in records if record["metric_eligible"]]
    unresolved = [record for record in records if not record["metric_eligible"]]
    print(f"Human reference records: {len(records)}")
    print(f"Reference routes:        {dict(route_counts)}")
    print(f"Reference status:        {dict(status_counts)}")
    print(f"Metric-eligible:         {len(eligible)}")
    print(f"Excluded as uncertain:  {len(unresolved)}")
    print(f"Validation errors:       {len(errors)}")
    if args.dry_run:
        print("Dry run: no human-reference outputs were written.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "pilot_150_human_reference_v6.jsonl"
    csv_path = output_dir / "pilot_150_human_reference_v6.csv"
    unresolved_path = output_dir / "pilot_150_human_reference_unresolved_v6.csv"
    report_path = output_dir / "pilot_150_human_reference_report_v6.json"
    targets = (jsonl_path, csv_path, unresolved_path, report_path)
    if not args.force and any(path.exists() for path in targets):
        raise FileExistsError("Human-reference output exists; pass --force to replace it")

    jsonl_sha = write_jsonl(jsonl_path, records)
    flat_records = [flatten_reference(record) for record in records]
    csv_sha = write_csv(csv_path, flat_records, list(flat_records[0]))
    unresolved_flat = [flatten_reference(record) for record in unresolved]
    unresolved_sha = write_csv(
        unresolved_path,
        unresolved_flat,
        list(flat_records[0]),
    )
    finalizer_path = Path(__file__).resolve()
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": (
            "The primary evaluation denominator contains only records with a non-uncertain "
            "human reference and valid supporting evidence. Uncertain records remain in the "
            "150-record reference set for transparent coverage accounting."
        ),
        "policy": {
            "ab_exact_agreement": "Use the common A/B value after both workbooks pass local validation.",
            "adjudication": "Use completed adjudicated values for every A/B disagreement.",
            "metric_eligible": "reference_status=resolved only.",
            "uncertain_consensus": "A and B agree on primary_label=uncertain; excluded from primary metrics.",
            "unresolved_evidence": "Adjudicator set adjudication_evidence_valid=no; excluded from primary metrics.",
        },
        "cohort": {
            "records": len(records),
            "reference_route_counts": dict(route_counts),
            "reference_status_counts": dict(status_counts),
            "metric_eligible": len(eligible),
            "metric_ineligible": len(unresolved),
            "adjudication_evidence_valid": dict(
                Counter(record["human_evidence_valid"] for record in records if record["reference_route"] == "human_adjudication")
            ),
            "primary_label_counts_all": count_field(records, "reference_primary_label"),
            "primary_label_counts_metric_eligible": count_field(eligible, "reference_primary_label"),
            "af_use_label_counts_metric_eligible": count_field(eligible, "reference_af_use_label"),
            "adoption_eligible_counts_metric_eligible": count_field(eligible, "reference_adoption_eligible"),
        },
        "double_annotation_agreement": agreement,
        "inputs": {
            label: {"path": relative(path), "sha256": sha256_file(path)}
            for label, path in paths.items()
        },
        "implementation": {
            "finalizer": {"path": relative(finalizer_path), "sha256": sha256_file(finalizer_path)},
            "a_b_validator": {
                "path": relative(CODE_ROOT / "23_validate_pilot_human_annotations.py"),
                "sha256": sha256_file(CODE_ROOT / "23_validate_pilot_human_annotations.py"),
            },
        },
        "outputs": {
            "reference_jsonl": {"path": relative(jsonl_path), "sha256": jsonl_sha, "records": len(records)},
            "reference_csv": {"path": relative(csv_path), "sha256": csv_sha, "records": len(records)},
            "unresolved_csv": {"path": relative(unresolved_path), "sha256": unresolved_sha, "records": len(unresolved)},
        },
    }
    report_sha = write_json(report_path, report)
    print(f"Reference JSONL:         {jsonl_path}")
    print(f"Reference CSV:           {csv_path}")
    print(f"Unresolved worklist:     {unresolved_path}")
    print(f"Audit report SHA-256:    {report_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
