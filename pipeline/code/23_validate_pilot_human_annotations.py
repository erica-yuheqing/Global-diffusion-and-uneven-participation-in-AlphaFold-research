#!/usr/bin/env python3
"""Validate two completed blinded annotation workbooks and build adjudication inputs.

The validator is local-only. It verifies the frozen assignment identity, controlled
vocabularies, label consistency, and verbatim evidence against the blinded packet.
It never reads machine-review outputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook


SCHEMA_VERSION = "af-human-double-annotation-validation-v1"
EXPECTED_HEADERS = [
    "assignment_order",
    "reviewer_record_id",
    "review_id",
    "work_id",
    "title",
    "publication_year",
    "doi",
    "material_available",
    "primary_label",
    "relevance_level",
    "evidence_level",
    "af_related_label",
    "af_use_label",
    "adoption_eligible",
    "future_or_hypothetical_only",
    "observed_actions",
    "action_evidence_map",
    "exclusion_reason",
    "evidence_1_source_kind",
    "evidence_1_block_index",
    "evidence_1_section",
    "evidence_1_quote",
    "evidence_1_supports",
    "evidence_2_source_kind",
    "evidence_2_block_index",
    "evidence_2_section",
    "evidence_2_quote",
    "evidence_2_supports",
    "evidence_3_source_kind",
    "evidence_3_block_index",
    "evidence_3_section",
    "evidence_3_quote",
    "evidence_3_supports",
    "uncertainty_reasons",
    "reasoning_summary",
    "annotator_id",
    "annotation_date",
    "status",
]

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
EXCLUSION_REASONS = {
    "none",
    "unrelated_or_abbreviation",
    "background_only",
    "review_no_use",
    "original_platform",
    "insufficient_evidence",
    "future_hypothetical_only",
    "other",
}
ACTIONS = {
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
}
ACTUAL_USE_ACTIONS = ACTIONS - {"discussion_only", "none"}
UNCERTAINTY_REASONS = {
    "abstract_only",
    "insufficient_evidence",
    "boundary_R2_R3",
    "boundary_R3_R4",
    "original_vs_downstream",
    "conflicting_evidence",
    "citation_link_uncertain",
    "prediction_origin_unclear",
    "input_quality",
    "other",
}
SUPPORT_VALUES = {"relation", "use", "engagement", "exclusion", "uncertainty"}
SOURCE_KINDS = {"title", "abstract", "fulltext_block", "matched_reference"}
AGREEMENT_FIELDS = [
    "primary_label",
    "relevance_level",
    "evidence_level",
    "af_related_label",
    "af_use_label",
    "adoption_eligible",
    "future_or_hypothetical_only",
    "observed_actions",
]


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


def split_pipe(value: Any) -> tuple[str, ...]:
    parts = [part.strip() for part in norm(value).split("|") if part.strip()]
    return tuple(dict.fromkeys(parts))


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256_sidecar(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def workbook_metadata(workbook: Any) -> dict[str, str]:
    if "Metadata" not in workbook.sheetnames:
        raise ValueError("Workbook is missing Metadata sheet")
    sheet = workbook["Metadata"]
    result: dict[str, str] = {}
    for row in sheet.iter_rows(min_row=6, max_col=2, values_only=True):
        key = norm(row[0])
        if key:
            result[key] = norm(row[1])
    return result


def annotation_rows(workbook: Any) -> list[dict[str, Any]]:
    if "Annotations" not in workbook.sheetnames:
        raise ValueError("Workbook is missing Annotations sheet")
    sheet = workbook["Annotations"]
    headers = [norm(cell.value) for cell in sheet[1]]
    if headers != EXPECTED_HEADERS:
        raise ValueError("Annotations header does not match the locked workbook schema")
    rows: list[dict[str, Any]] = []
    for values in sheet.iter_rows(min_row=2, max_col=len(headers), values_only=True):
        if not any(value is not None and norm(value) for value in values):
            continue
        rows.append(dict(zip(headers, values, strict=True)))
    return rows


def validate_identity(
    rows: list[dict[str, Any]], assignment: dict[str, Any], metadata: dict[str, str]
) -> list[str]:
    errors: list[str] = []
    expected = assignment["records"]
    if len(rows) != len(expected):
        errors.append(f"record_count: expected {len(expected)}, found {len(rows)}")
        return errors
    for index, (row, locked) in enumerate(zip(rows, expected, strict=True), 2):
        for key in ("assignment_order", "reviewer_record_id", "review_id", "work_id"):
            if norm(row[key]) != norm(locked[key]):
                errors.append(
                    f"row {index} {key}: expected {locked[key]!r}, found {row[key]!r}"
                )
    for key, expected_value in (
        ("assignment_id", assignment["annotator_id"]),
        ("record_count", assignment["record_count"]),
        ("assignment_seed", assignment["seed"]),
        ("ordered_review_id_sha256", assignment["ordered_review_id_sha256"]),
    ):
        if metadata.get(key) != norm(expected_value):
            errors.append(
                f"metadata {key}: expected {expected_value!r}, found {metadata.get(key)!r}"
            )
    return errors


def add_enum_error(
    errors: list[str], row_number: int, field: str, value: str, allowed: set[str]
) -> None:
    if value not in allowed:
        errors.append(f"row {row_number} {field}: invalid value {value!r}")


def parse_action_evidence(value: Any) -> tuple[dict[str, tuple[int, ...]], list[str]]:
    result: dict[str, tuple[int, ...]] = {}
    errors: list[str] = []
    for item in split_pipe(value):
        if ":" not in item:
            errors.append(f"invalid action_evidence_map item {item!r}")
            continue
        action, raw_indices = (part.strip() for part in item.split(":", 1))
        try:
            indices = tuple(dict.fromkeys(int(part.strip()) for part in raw_indices.split(",")))
        except ValueError:
            errors.append(f"invalid evidence index in {item!r}")
            continue
        result[action] = indices
    return result, errors


def evidence_source_texts(
    packet: dict[str, Any], source_kind: str, block_index: str, section: str
) -> list[str]:
    material = packet["input_material"]
    if source_kind == "title":
        return [material.get("title") or ""]
    if source_kind == "abstract":
        return [material.get("abstract") or ""]
    if source_kind == "fulltext_block":
        try:
            wanted = int(block_index)
        except (TypeError, ValueError):
            return []
        return [
            block.get("text") or ""
            for block in material.get("evidence_blocks") or []
            if block.get("index") == wanted and norm(block.get("section")) == section
        ]
    if source_kind == "matched_reference":
        return [
            reference.get("reference_text") or ""
            for reference in material.get("matched_seed_references") or []
        ]
    return []


def validate_consistency(row: dict[str, Any], row_number: int) -> list[str]:
    errors: list[str] = []
    primary = norm(row["primary_label"])
    relevance = norm(row["relevance_level"])
    evidence = norm(row["evidence_level"])
    related = norm(row["af_related_label"])
    use = norm(row["af_use_label"])
    adoption = norm(row["adoption_eligible"])
    future = norm(row["future_or_hypothetical_only"])
    exclusion = norm(row["exclusion_reason"])
    actions = set(split_pipe(row["observed_actions"]))
    uncertainty = set(split_pipe(row["uncertainty_reasons"]))

    for field, value, allowed in (
        ("primary_label", primary, PRIMARY_LABELS),
        ("relevance_level", relevance, RELEVANCE_LEVELS),
        ("evidence_level", evidence, EVIDENCE_LEVELS),
        ("af_related_label", related, RELATED_LABELS),
        ("af_use_label", use, TERNARY_LABELS),
        ("adoption_eligible", adoption, TERNARY_LABELS),
        ("future_or_hypothetical_only", future, BOOLEAN_LABELS),
        ("exclusion_reason", exclusion, EXCLUSION_REASONS),
    ):
        add_enum_error(errors, row_number, field, value, allowed)

    unknown_actions = actions - ACTIONS
    if not actions:
        errors.append(f"row {row_number} observed_actions: at least one action is required")
    if unknown_actions:
        errors.append(f"row {row_number} observed_actions: unknown {sorted(unknown_actions)}")
    if "none" in actions and len(actions) > 1:
        errors.append(f"row {row_number} observed_actions: none cannot coexist with another action")
    if "discussion_only" in actions and actions & ACTUAL_USE_ACTIONS:
        errors.append(
            f"row {row_number} observed_actions: discussion_only cannot coexist with actual use"
        )
    unknown_uncertainty = uncertainty - UNCERTAINTY_REASONS
    if unknown_uncertainty:
        errors.append(f"row {row_number} uncertainty_reasons: unknown {sorted(unknown_uncertainty)}")

    expected_by_primary = {
        "FP": ("R0", "false", "no", "no", "unrelated_or_abbreviation"),
        "background_only": ("R1", "background", "no", "no", "background_only"),
        "review_discussion": ("R2", "related", "no", "no", "review_no_use"),
        "database_consumption": ("R3", "related", "yes", "yes", "none"),
        "model_application": ("R3", "related", "yes", "yes", "none"),
        "method_development": ("R4", "related", "yes", "yes", "none"),
        "original_platform": ("R4", "related", "yes", "no", "original_platform"),
    }
    if primary in expected_by_primary:
        expected = expected_by_primary[primary]
        observed = (relevance, related, use, adoption, exclusion)
        if observed != expected:
            errors.append(
                f"row {row_number} primary consistency: expected {expected}, found {observed}"
            )
    elif primary == "uncertain":
        if relevance != "RU":
            errors.append(f"row {row_number}: primary uncertain requires relevance_level=RU")
        if not uncertainty:
            errors.append(f"row {row_number}: primary uncertain requires uncertainty_reasons")

    if evidence in {"E0", "E1"} and (use == "yes" or adoption == "yes"):
        errors.append(f"row {row_number}: E0/E1 cannot establish actual use or adoption")
    if use == "yes" and evidence == "E2" and "abstract_only" not in uncertainty:
        errors.append(f"row {row_number}: E2 actual use requires uncertainty reason abstract_only")
    if actions & ACTUAL_USE_ACTIONS and use != "yes":
        errors.append(f"row {row_number}: actual-use action requires af_use_label=yes")
    if use == "no" and actions & ACTUAL_USE_ACTIONS:
        errors.append(f"row {row_number}: af_use_label=no conflicts with actual-use action")
    if future == "yes" and (use == "yes" or adoption == "yes" or actions & ACTUAL_USE_ACTIONS):
        errors.append(f"row {row_number}: hypothetical-only evidence cannot establish actual use")
    return errors


def validate_evidence(
    row: dict[str, Any], packet: dict[str, Any], row_number: int
) -> tuple[list[str], tuple[int, ...]]:
    errors: list[str] = []
    populated: list[int] = []
    for slot in range(1, 4):
        source = norm(row[f"evidence_{slot}_source_kind"])
        block_index = norm(row[f"evidence_{slot}_block_index"])
        section = norm(row[f"evidence_{slot}_section"])
        quote = norm(row[f"evidence_{slot}_quote"])
        supports = set(split_pipe(row[f"evidence_{slot}_supports"]))
        any_value = any((source, block_index, section, quote, supports))
        if not any_value:
            continue
        populated.append(slot)
        if source not in SOURCE_KINDS:
            errors.append(f"row {row_number} evidence {slot}: invalid source_kind {source!r}")
        if not quote:
            errors.append(f"row {row_number} evidence {slot}: quote is required")
        elif word_count(quote) > 25:
            errors.append(
                f"row {row_number} evidence {slot}: quote has {word_count(quote)} words; maximum is 25"
            )
        if not supports or supports - SUPPORT_VALUES:
            errors.append(f"row {row_number} evidence {slot}: invalid or missing supports")
        if source == "fulltext_block" and (not block_index or not section):
            errors.append(
                f"row {row_number} evidence {slot}: fulltext_block requires block_index and exact section"
            )
        if source != "fulltext_block" and block_index:
            errors.append(
                f"row {row_number} evidence {slot}: block_index must be blank for {source}"
            )
        sources = evidence_source_texts(packet, source, block_index, section)
        if quote and not any(quote in text for text in sources):
            errors.append(
                f"row {row_number} evidence {slot}: quote is not an exact substring of the supplied source"
            )
    if not populated:
        errors.append(f"row {row_number}: at least one evidence excerpt is required")
    if norm(row["evidence_level"]) == "E3" and not any(
        norm(row[f"evidence_{slot}_source_kind"]) == "fulltext_block" for slot in populated
    ):
        errors.append(f"row {row_number}: E3 requires at least one fulltext_block excerpt")

    mapping, mapping_errors = parse_action_evidence(row["action_evidence_map"])
    errors.extend(f"row {row_number}: {message}" for message in mapping_errors)
    actions = set(split_pipe(row["observed_actions"]))
    evidence_actions = actions - {"none"}
    for action in evidence_actions:
        indices = mapping.get(action)
        if not indices:
            errors.append(f"row {row_number}: action {action} lacks action_evidence_map indices")
        elif any(index not in populated for index in indices):
            errors.append(
                f"row {row_number}: action {action} references an unpopulated evidence slot"
            )
    for action in mapping:
        if action not in evidence_actions:
            errors.append(f"row {row_number}: action_evidence_map contains unselected action {action}")
    return errors, tuple(populated)


def validate_completed_row(
    row: dict[str, Any], packet: dict[str, Any], row_number: int
) -> list[str]:
    errors = validate_consistency(row, row_number)
    evidence_errors, _ = validate_evidence(row, packet, row_number)
    errors.extend(evidence_errors)
    for field in ("reasoning_summary", "annotator_id", "annotation_date"):
        if not norm(row[field]):
            errors.append(f"row {row_number} {field}: required when status=complete")
    if len(norm(row["reasoning_summary"])) > 1200:
        errors.append(f"row {row_number} reasoning_summary: exceeds 1200 characters")
    return errors


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    observed = sum(a == b for a, b in pairs) / len(pairs)
    counts_a = Counter(a for a, _ in pairs)
    counts_b = Counter(b for _, b in pairs)
    categories = set(counts_a) | set(counts_b)
    expected = sum((counts_a[c] / len(pairs)) * (counts_b[c] / len(pairs)) for c in categories)
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1 - expected)


def normalized_for_agreement(row: dict[str, Any], field: str) -> str:
    if field == "observed_actions":
        return "|".join(sorted(split_pipe(row[field])))
    return norm(row[field])


def build_agreement(
    rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_id_a = {norm(row["review_id"]): row for row in rows_a if norm(row["status"]) == "complete"}
    by_id_b = {norm(row["review_id"]): row for row in rows_b if norm(row["status"]) == "complete"}
    paired_ids = sorted(set(by_id_a) & set(by_id_b))
    field_summary: dict[str, Any] = {}
    disagreements: list[dict[str, Any]] = []
    for field in AGREEMENT_FIELDS:
        pairs = [
            (normalized_for_agreement(by_id_a[key], field), normalized_for_agreement(by_id_b[key], field))
            for key in paired_ids
        ]
        matches = sum(a == b for a, b in pairs)
        field_summary[field] = {
            "n": len(pairs),
            "exact_matches": matches,
            "exact_agreement": matches / len(pairs) if pairs else None,
            "cohen_kappa": cohen_kappa(pairs) if field != "observed_actions" else None,
        }

    core_fields = AGREEMENT_FIELDS[:-1]
    core_matches = 0
    action_jaccards: list[float] = []
    for key in paired_ids:
        row_a = by_id_a[key]
        row_b = by_id_b[key]
        differing = [
            field
            for field in AGREEMENT_FIELDS
            if normalized_for_agreement(row_a, field) != normalized_for_agreement(row_b, field)
        ]
        if not any(field in differing for field in core_fields):
            core_matches += 1
        actions_a = set(split_pipe(row_a["observed_actions"]))
        actions_b = set(split_pipe(row_b["observed_actions"]))
        union = actions_a | actions_b
        action_jaccards.append(len(actions_a & actions_b) / len(union) if union else 1.0)
        if differing:
            disagreements.append(
                {
                    "review_id": key,
                    "work_id": norm(row_a["work_id"]),
                    "title": norm(row_a["title"]),
                    "disagreement_fields": "|".join(differing),
                    **{f"annotator_a_{field}": normalized_for_agreement(row_a, field) for field in AGREEMENT_FIELDS},
                    **{f"annotator_b_{field}": normalized_for_agreement(row_b, field) for field in AGREEMENT_FIELDS},
                    "adjudicated_primary_label": "",
                    "adjudicated_relevance_level": "",
                    "adjudicated_evidence_level": "",
                    "adjudicated_af_related_label": "",
                    "adjudicated_af_use_label": "",
                    "adjudicated_adoption_eligible": "",
                    "adjudicated_future_or_hypothetical_only": "",
                    "adjudicated_observed_actions": "",
                    "adjudication_evidence_valid": "",
                    "adjudicator_id": "",
                    "adjudication_date": "",
                    "adjudication_notes": "",
                    "adjudication_status": "pending",
                }
            )
    summary = {
        "paired_complete_records": len(paired_ids),
        "field_agreement": field_summary,
        "core_tuple_exact_matches": core_matches,
        "core_tuple_exact_agreement": core_matches / len(paired_ids) if paired_ids else None,
        "mean_action_jaccard": sum(action_jaccards) / len(action_jaccards) if action_jaccards else None,
        "records_requiring_adjudication": len(disagreements),
    }
    return summary, disagreements


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    write_sha256_sidecar(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotator-a", type=Path, required=True)
    parser.add_argument("--annotator-b", type=Path, required=True)
    parser.add_argument(
        "--packet-file",
        type=Path,
        default=Path("fulltext/pilot/human_annotation_v4_3/pilot_150_human_packets_blinded_v4_3.jsonl"),
    )
    parser.add_argument(
        "--assignment-a",
        type=Path,
        default=Path("fulltext/pilot/human_annotation_v4_3/pilot_150_annotator_a_assignment_v4_3.json"),
    )
    parser.add_argument(
        "--assignment-b",
        type=Path,
        default=Path("fulltext/pilot/human_annotation_v4_3/pilot_150_annotator_b_assignment_v4_3.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("fulltext/pilot/human_annotation_v4_3/results"),
    )
    parser.add_argument(
        "--result-tag",
        default="v4_3",
        help="Filename tag for the validation report and adjudication worklist.",
    )
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result_tag = args.result_tag.strip()
    if not result_tag or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in result_tag
    ):
        raise ValueError("--result-tag must contain only letters, digits, underscore, or hyphen")
    packet_path = args.packet_file.resolve()
    assignment_a_path = args.assignment_a.resolve()
    assignment_b_path = args.assignment_b.resolve()
    workbook_a_path = args.annotator_a.resolve()
    workbook_b_path = args.annotator_b.resolve()
    output_dir = args.output_dir.resolve()

    packets = read_jsonl(packet_path)
    packet_by_id = {packet["review_id"]: packet for packet in packets}
    assignment_a = json.loads(assignment_a_path.read_text(encoding="utf-8"))
    assignment_b = json.loads(assignment_b_path.read_text(encoding="utf-8"))
    workbook_a = load_workbook(workbook_a_path, read_only=True, data_only=False)
    workbook_b = load_workbook(workbook_b_path, read_only=True, data_only=False)
    rows_a = annotation_rows(workbook_a)
    rows_b = annotation_rows(workbook_b)
    metadata_a = workbook_metadata(workbook_a)
    metadata_b = workbook_metadata(workbook_b)

    identity_errors = [
        *(f"A: {message}" for message in validate_identity(rows_a, assignment_a, metadata_a)),
        *(f"B: {message}" for message in validate_identity(rows_b, assignment_b, metadata_b)),
    ]
    validation_errors: list[str] = []
    incomplete: dict[str, list[str]] = {"A": [], "B": []}
    completed_counts: dict[str, int] = {"A": 0, "B": 0}
    for annotator, rows in (("A", rows_a), ("B", rows_b)):
        for row_number, row in enumerate(rows, 2):
            status = norm(row["status"])
            review_id = norm(row["review_id"])
            if status not in {"pending", "complete"}:
                validation_errors.append(
                    f"{annotator}: row {row_number} status: expected pending or complete"
                )
                continue
            if status == "pending":
                incomplete[annotator].append(review_id)
                continue
            completed_counts[annotator] += 1
            packet = packet_by_id.get(review_id)
            if not packet:
                validation_errors.append(f"{annotator}: row {row_number}: missing blinded packet")
                continue
            validation_errors.extend(
                f"{annotator}: {message}"
                for message in validate_completed_row(row, packet, row_number)
            )

    agreement, disagreements = build_agreement(rows_a, rows_b)
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "annotator_a_file": workbook_a_path.name,
            "annotator_a_sha256": sha256_file(workbook_a_path),
            "annotator_b_file": workbook_b_path.name,
            "annotator_b_sha256": sha256_file(workbook_b_path),
            "packet_file": packet_path.name,
            "packet_file_sha256": sha256_file(packet_path),
            "assignment_a_file": assignment_a_path.name,
            "assignment_a_sha256": sha256_file(assignment_a_path),
            "assignment_b_file": assignment_b_path.name,
            "assignment_b_sha256": sha256_file(assignment_b_path),
        },
        "record_count": len(packets),
        "identity_errors": identity_errors,
        "validation_errors": validation_errors,
        "completed_counts": completed_counts,
        "incomplete_counts": {key: len(value) for key, value in incomplete.items()},
        "incomplete_review_ids": incomplete,
        "agreement": agreement,
        "ready_for_adjudication": (
            not identity_errors
            and not validation_errors
            and not incomplete["A"]
            and not incomplete["B"]
        ),
        "method_note": "Agreement is computed only for records marked complete by both annotators. No machine outputs or prior labels are read.",
    }

    print(f"Records:                 {len(packets)}")
    print(f"Completed A/B:           {completed_counts['A']} / {completed_counts['B']}")
    print(f"Incomplete A/B:          {len(incomplete['A'])} / {len(incomplete['B'])}")
    print(f"Identity errors:         {len(identity_errors)}")
    print(f"Annotation errors:       {len(validation_errors)}")
    print(f"Paired complete:         {agreement['paired_complete_records']}")
    print(f"Require adjudication:    {agreement['records_requiring_adjudication']}")
    print(f"Ready for adjudication:  {report['ready_for_adjudication']}")

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"pilot_150_human_validation_report_{result_tag}.json"
        disagreements_path = output_dir / f"pilot_150_human_disagreements_{result_tag}.csv"
        if not args.force and (report_path.exists() or disagreements_path.exists()):
            raise FileExistsError("Output exists; pass --force to replace validation results")
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_sha256_sidecar(report_path)
        disagreement_fields = list(disagreements[0]) if disagreements else [
            "review_id",
            "work_id",
            "title",
            "disagreement_fields",
            "adjudication_status",
        ]
        write_csv(disagreements_path, disagreements, disagreement_fields)
        print(f"Validation report:       {report_path}")
        print(f"Adjudication worklist:   {disagreements_path}")

    has_incomplete = bool(incomplete["A"] or incomplete["B"])
    if identity_errors or validation_errors:
        return 2
    if has_incomplete and not args.allow_incomplete:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
