#!/usr/bin/env python3
"""Deterministically merge the frozen production review into one final database.

The command is local-only and never makes provider requests.  It joins records
by ``work_id`` and enforces the mutually exclusive production routes frozen by
``35_prepare_production_model_c.py``:

* A/B core agreement -> consensus core fields; actions only when A and B agree.
* Model C routes -> canonical Model C adjudication.
* Evidence-recovery forced U -> the frozen input's forced decision.
* Direct-human routes -> canonical direct-human adjudication.

``observed_actions`` is deliberately not synthesized for A/B records when the
two annotations differ.  Both source values remain in the final record and the
flat CSV, with an explicit ``disagreement_unadjudicated`` status.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent

from fulltext_pipeline.agreement_policy import (  # noqa: E402
    CORE_DECISION_FIELDS,
    POLICY_VERSION,
    action_disagreement,
    core_differences,
    normalize_actions,
)


DEFAULT_INPUT = PROJECT_ROOT / "fulltext/production/model_inputs_v1/full_model_inputs.jsonl"
DEFAULT_RECONCILIATION = (
    PROJECT_ROOT / "fulltext/production/adjudication_v1/production_ab_reconciliation_v1.csv"
)
DEFAULT_A = PROJECT_ROOT / "fulltext/production/adjudication_v1/model_a_canonical_valid_v1.jsonl"
DEFAULT_B = PROJECT_ROOT / "fulltext/production/adjudication_v1/model_b_canonical_valid_v1.jsonl"
DEFAULT_C = (
    PROJECT_ROOT / "fulltext/production/model_c_finalization_v1/model_c_canonical_complete_v1.jsonl"
)
DEFAULT_HUMAN = (
    PROJECT_ROOT
    / "fulltext/production/direct_human_finalization_v1/production_direct_human_canonical_valid_v1.jsonl"
)
DEFAULT_C_WARNINGS = (
    PROJECT_ROOT
    / "fulltext/production/model_c_finalization_v1/model_c_human_adjudication_semantic_warnings_v1.csv"
)
DEFAULT_HUMAN_WARNINGS = (
    PROJECT_ROOT
    / "fulltext/production/direct_human_finalization_v1/production_direct_human_semantic_warnings_v1.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fulltext/production/final_database_v1"

MODEL_C_ROUTES = {"model_c_core_disagreement", "model_c_single_model_only"}
DIRECT_HUMAN_ROUTES = {"direct_human_no_valid_ab", "forced_u_oversize_direct_human"}
FORCED_U_ROUTE = "forced_u_evidence_recovery"
AB_ROUTE = "ab_core_agreement"
KNOWN_ROUTES = MODEL_C_ROUTES | DIRECT_HUMAN_ROUTES | {FORCED_U_ROUTE, AB_ROUTE}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--reconciliation", type=Path, default=DEFAULT_RECONCILIATION)
    parser.add_argument("--model-a", type=Path, default=DEFAULT_A)
    parser.add_argument("--model-b", type=Path, default=DEFAULT_B)
    parser.add_argument("--model-c", type=Path, default=DEFAULT_C)
    parser.add_argument("--direct-human", type=Path, default=DEFAULT_HUMAN)
    parser.add_argument("--model-c-warnings", type=Path, default=DEFAULT_C_WARNINGS)
    parser.add_argument("--direct-human-warnings", type=Path, default=DEFAULT_HUMAN_WARNINGS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-records", type=int, default=29_127)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolved(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected an object at {path}:{line_number}")
            yield line_number, value


def unique_jsonl(path: Path, label: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    ordered: list[dict[str, Any]] = []
    mapped: dict[str, dict[str, Any]] = {}
    for line_number, record in iter_jsonl(path):
        work_id = record.get("work_id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError(f"{label}:{line_number}: missing work_id")
        if record.get("review_id") != work_id:
            raise ValueError(f"{label}:{line_number}: review_id/work_id mismatch")
        if work_id in mapped:
            raise ValueError(f"{label}: duplicate work_id {work_id}")
        ordered.append(record)
        mapped[work_id] = record
    return ordered, mapped


def read_reconciliation(path: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    mapped: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(rows, 2):
        work_id = row.get("work_id")
        if not work_id or row.get("review_id") != work_id:
            raise ValueError(f"reconciliation:{row_number}: invalid review_id/work_id")
        if work_id in mapped:
            raise ValueError(f"reconciliation: duplicate work_id {work_id}")
        route = row.get("route")
        if route not in KNOWN_ROUTES:
            raise ValueError(f"reconciliation:{work_id}: unknown route {route!r}")
        mapped[work_id] = row
    return rows, mapped


def warning_ids(path: Path) -> set[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = {str(row.get("work_id") or row.get("review_id") or "") for row in rows}
    ids.discard("")
    return ids


def response(record: dict[str, Any], label: str) -> dict[str, Any]:
    value = record.get("response")
    if not isinstance(value, dict):
        raise ValueError(f"{label}/{record.get('work_id')}: missing response")
    missing = [field for field in CORE_DECISION_FIELDS if field not in value]
    if missing:
        raise ValueError(f"{label}/{record.get('work_id')}: missing core fields {missing}")
    return value


def source_reference(record: dict[str, Any]) -> dict[str, Any]:
    provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    return {
        "source_model": record.get("source_model"),
        "provider": record.get("provider"),
        "model": record.get("model"),
        "canonical_record_sha256": fingerprint(record),
        "upstream_source_record_sha256": provenance.get("source_record_sha256"),
        "input_packet_sha256": provenance.get("input_packet_sha256"),
        "source_run_id": provenance.get("source_run_id"),
    }


def core_decision(value: dict[str, Any]) -> dict[str, Any]:
    return {field: value.get(field) for field in CORE_DECISION_FIELDS}


def adjudicated_support(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "confidence": value.get("confidence"),
        "needs_human_review": value.get("needs_human_review"),
        "human_review_reasons": value.get("human_review_reasons") or [],
        "evidence": value.get("evidence") or [],
        "reasoning_summary": value.get("reasoning_summary"),
        "action_evidence": value.get("action_evidence") or [],
    }


def ab_final(
    work_id: str,
    a_record: dict[str, Any],
    b_record: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    a = response(a_record, "model_a")
    b = response(b_record, "model_b")
    differences = core_differences(a, b)
    if differences:
        raise ValueError(f"{work_id}: routed as A/B agreement but differs in {differences}")
    action_diff = action_disagreement(a, b)
    a_actions = list(normalize_actions(a.get("observed_actions")))
    b_actions = list(normalize_actions(b.get("observed_actions")))
    final = core_decision(a)
    final.update(
        {
            "observed_actions": None if action_diff else a_actions,
            "observed_actions_status": (
                "disagreement_unadjudicated" if action_diff else "ab_exact_consensus"
            ),
            "needs_human_review": (
                a.get("needs_human_review")
                if a.get("needs_human_review") == b.get("needs_human_review")
                else None
            ),
            "confidence": None,
        }
    )
    secondary = {
        "model_a_observed_actions": a_actions,
        "model_b_observed_actions": b_actions,
        "model_a_needs_human_review": a.get("needs_human_review"),
        "model_b_needs_human_review": b.get("needs_human_review"),
        "model_a_confidence": a.get("confidence"),
        "model_b_confidence": b.get("confidence"),
        "action_judgment_is_final": not action_diff,
    }
    provenance = {
        "selected_sources": [source_reference(a_record), source_reference(b_record)],
        "selection_rule": "A/B normalized exact agreement on all core decision fields",
    }
    return final, secondary, provenance


def adjudicated_final(
    record: dict[str, Any], *, selection_rule: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    value = response(record, str(record.get("source_model") or "adjudicated"))
    final = core_decision(value)
    final.update(
        {
            "observed_actions": list(normalize_actions(value.get("observed_actions"))),
            "observed_actions_status": "adjudicated",
            "needs_human_review": value.get("needs_human_review"),
            "confidence": value.get("confidence"),
        }
    )
    return (
        final,
        adjudicated_support(value),
        {"selected_sources": [source_reference(record)], "selection_rule": selection_rule},
    )


def forced_final(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    forced = packet.get("forced_decision")
    if not isinstance(forced, dict):
        raise ValueError(f"{packet.get('work_id')}: forced-U route lacks forced_decision")
    final = {field: forced.get(field) for field in CORE_DECISION_FIELDS}
    if final["exclusion_reason"] is None:
        final["exclusion_reason"] = "insufficient_evidence"
    if final["future_or_hypothetical_only"] is None:
        final["future_or_hypothetical_only"] = False
    final.update(
        {
            "observed_actions": None,
            "observed_actions_status": "not_assessed_insufficient_evidence",
            "needs_human_review": bool(forced.get("needs_human_review", True)),
            "confidence": None,
        }
    )
    support = {
        "forced_decision": forced,
        "reason": forced.get("reason"),
        "evidence": [],
        "action_evidence": [],
    }
    provenance = {
        "selected_sources": [],
        "selection_rule": "Frozen packet was model-ineligible; retain forced uncertain decision",
        "input_packet_sha256": fingerprint(packet),
    }
    return final, support, provenance


def atomic_write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    digest = sha256_bytes(data)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar_tmp = sidecar.with_suffix(sidecar.suffix + ".part")
    sidecar_tmp.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    sidecar_tmp.replace(sidecar)
    return digest


def write_json(path: Path, value: Any) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    return atomic_write(path, data)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    data = b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode()
        for record in records
    )
    return atomic_write(path, data)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    fieldnames = list(rows[0]) if rows else ["review_id", "work_id"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return atomic_write(path, buffer.getvalue().encode())


def pipe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "|".join(str(item) for item in value)
    return str(value)


def main() -> int:
    args = parse_args()
    paths = {
        "input": resolved(args.input),
        "reconciliation": resolved(args.reconciliation),
        "model_a": resolved(args.model_a),
        "model_b": resolved(args.model_b),
        "model_c": resolved(args.model_c),
        "direct_human": resolved(args.direct_human),
        "model_c_warnings": resolved(args.model_c_warnings),
        "direct_human_warnings": resolved(args.direct_human_warnings),
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label}: {path}")
    source_hashes = {label: sha256_file(path) for label, path in paths.items()}

    packets_ordered, packets = unique_jsonl(paths["input"], "input")
    reconciliation_ordered, reconciliation = read_reconciliation(paths["reconciliation"])
    _, model_a = unique_jsonl(paths["model_a"], "model_a")
    _, model_b = unique_jsonl(paths["model_b"], "model_b")
    _, model_c = unique_jsonl(paths["model_c"], "model_c")
    _, direct_human = unique_jsonl(paths["direct_human"], "direct_human")
    c_warning_ids = warning_ids(paths["model_c_warnings"])
    human_warning_ids = warning_ids(paths["direct_human_warnings"])

    ordered_ids = [packet["work_id"] for packet in packets_ordered]
    reconciliation_ids = [row["work_id"] for row in reconciliation_ordered]
    if len(ordered_ids) != args.expected_records or len(set(ordered_ids)) != args.expected_records:
        raise ValueError(
            f"Expected {args.expected_records:,} unique frozen inputs, found {len(ordered_ids):,}"
        )
    if reconciliation_ids != ordered_ids:
        raise ValueError("Reconciliation membership/order differs from frozen input")

    route_ids = {
        route: {work_id for work_id, row in reconciliation.items() if row["route"] == route}
        for route in KNOWN_ROUTES
    }
    model_c_expected = set().union(*(route_ids[route] for route in MODEL_C_ROUTES))
    human_expected = set().union(*(route_ids[route] for route in DIRECT_HUMAN_ROUTES))
    if set(model_c) != model_c_expected:
        raise ValueError(
            "Model C canonical coverage mismatch: "
            f"missing={len(model_c_expected-set(model_c))}, extra={len(set(model_c)-model_c_expected)}"
        )
    if set(direct_human) != human_expected:
        raise ValueError(
            "Direct-human canonical coverage mismatch: "
            f"missing={len(human_expected-set(direct_human))}, "
            f"extra={len(set(direct_human)-human_expected)}"
        )
    if not c_warning_ids <= set(model_c):
        raise ValueError("Model C semantic-warning IDs are outside Model C canonical coverage")
    if not human_warning_ids <= set(direct_human):
        raise ValueError("Direct-human semantic-warning IDs are outside human canonical coverage")

    route_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    relevance_counts: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    af_use_counts: Counter[str] = Counter()
    adoption_counts: Counter[str] = Counter()
    action_status_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    final_records: list[dict[str, Any]] = []
    flat_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for packet in packets_ordered:
        work_id = packet["work_id"]
        route_row = reconciliation[work_id]
        route = route_row["route"]
        route_counts[route] += 1
        decision_route: str
        if route == AB_ROUTE:
            if work_id not in model_a or work_id not in model_b:
                raise ValueError(f"{work_id}: A/B agreement route lacks a canonical A or B response")
            final, support, provenance = ab_final(work_id, model_a[work_id], model_b[work_id])
            decision_route = "ab_core_consensus"
        elif route in MODEL_C_ROUTES:
            final, support, provenance = adjudicated_final(
                model_c[work_id], selection_rule="Canonical Model C adjudication"
            )
            decision_route = "model_c_adjudication"
        elif route in DIRECT_HUMAN_ROUTES:
            final, support, provenance = adjudicated_final(
                direct_human[work_id], selection_rule="Canonical direct-human adjudication"
            )
            decision_route = "direct_human_adjudication"
        elif route == FORCED_U_ROUTE:
            final, support, provenance = forced_final(packet)
            decision_route = "forced_u_insufficient_evidence"
        else:  # pragma: no cover - guarded during reconciliation load
            raise ValueError(f"{work_id}: unsupported route {route}")

        label_counts[str(final.get("primary_label"))] += 1
        relevance_counts[str(final.get("relevance_level"))] += 1
        evidence_counts[str(final.get("evidence_level"))] += 1
        af_use_counts[str(final.get("af_use_label"))] += 1
        adoption_counts[str(final.get("adoption_eligible"))] += 1
        action_status_counts[str(final.get("observed_actions_status"))] += 1
        semantic_warning_sources: list[str] = []
        if work_id in c_warning_ids:
            semantic_warning_sources.append("model_c_human_semantic_heuristic")
        if work_id in human_warning_ids:
            semantic_warning_sources.append("direct_human_semantic_heuristic")
        for warning in semantic_warning_sources:
            warning_counts[warning] += 1

        material = packet.get("input_material") or {}
        quality = packet.get("input_quality") or {}
        record = {
            "schema_version": "af-production-final-record-v1",
            "review_id": work_id,
            "work_id": work_id,
            "bibliographic_metadata": {
                "title": material.get("title"),
                "publication_year": material.get("publication_year"),
                "work_type": material.get("work_type"),
                "doi": material.get("doi"),
                "domain_labels": material.get("domain_labels"),
            },
            "input_evidence": {
                "evidence_tier": packet.get("evidence_tier"),
                "model_eligible": packet.get("model_eligible"),
                "input_quality": quality,
                "estimated_input_tokens": packet.get("estimated_input_tokens"),
                "input_packet_sha256": fingerprint(packet),
            },
            "decision_route": decision_route,
            "source_route": route,
            "agreement_policy": POLICY_VERSION,
            "final_decision": final,
            "support": support,
            "semantic_heuristic_warnings": semantic_warning_sources,
            "provenance": provenance,
        }
        final_records.append(record)

        selected = provenance.get("selected_sources") or []
        a_actions = support.get("model_a_observed_actions") if route == AB_ROUTE else None
        b_actions = support.get("model_b_observed_actions") if route == AB_ROUTE else None
        flat = {
            "review_id": work_id,
            "work_id": work_id,
            "title": material.get("title") or "",
            "publication_year": material.get("publication_year") or "",
            "doi": material.get("doi") or "",
            "work_type": material.get("work_type") or "",
            "domain_labels": pipe(material.get("domain_labels")),
            "evidence_tier": packet.get("evidence_tier") or "",
            "model_eligible": packet.get("model_eligible"),
            "decision_route": decision_route,
            "source_route": route,
            "primary_label": final.get("primary_label") or "",
            "relevance_level": final.get("relevance_level") or "",
            "evidence_level": final.get("evidence_level") or "",
            "af_related_label": final.get("af_related_label") or "",
            "af_use_label": final.get("af_use_label") or "",
            "adoption_eligible": final.get("adoption_eligible") or "",
            "exclusion_reason": final.get("exclusion_reason") or "",
            "future_or_hypothetical_only": final.get("future_or_hypothetical_only"),
            "observed_actions_status": final.get("observed_actions_status") or "",
            "final_observed_actions": pipe(final.get("observed_actions")),
            "model_a_observed_actions": pipe(a_actions),
            "model_b_observed_actions": pipe(b_actions),
            "needs_human_review": (
                "" if final.get("needs_human_review") is None else final.get("needs_human_review")
            ),
            "confidence": "" if final.get("confidence") is None else final.get("confidence"),
            "semantic_heuristic_warning": bool(semantic_warning_sources),
            "semantic_warning_sources": pipe(semantic_warning_sources),
            "selected_source_models": pipe(item.get("source_model") for item in selected),
            "selected_providers": pipe(item.get("provider") for item in selected),
            "input_packet_sha256": fingerprint(packet),
            "final_record_sha256": fingerprint(record),
        }
        flat_rows.append(flat)
        if (
            final.get("observed_actions_status") == "disagreement_unadjudicated"
            or semantic_warning_sources
        ):
            audit_rows.append(
                {
                    "review_id": work_id,
                    "work_id": work_id,
                    "decision_route": decision_route,
                    "source_route": route,
                    "audit_flags": pipe(
                        (["ab_observed_actions_disagreement"]
                         if final.get("observed_actions_status") == "disagreement_unadjudicated"
                         else [])
                        + semantic_warning_sources
                    ),
                    "model_a_observed_actions": pipe(a_actions),
                    "model_b_observed_actions": pipe(b_actions),
                    "final_observed_actions": pipe(final.get("observed_actions")),
                    "primary_label": final.get("primary_label"),
                    "af_use_label": final.get("af_use_label"),
                    "adoption_eligible": final.get("adoption_eligible"),
                }
            )

    final_ids = [record["work_id"] for record in final_records]
    if final_ids != ordered_ids or len(set(final_ids)) != args.expected_records:
        raise RuntimeError("Final record coverage/order invariant failed")
    if sum(route_counts.values()) != args.expected_records:
        raise RuntimeError("Final route counts do not sum to the frozen corpus")

    final_source_hashes = {label: sha256_file(path) for label, path in paths.items()}
    changed = [label for label in paths if final_source_hashes[label] != source_hashes[label]]
    if changed:
        raise RuntimeError(f"Source files changed while being read: {changed}")

    print(f"Frozen corpus:          {len(final_records):,}")
    print(f"Unique work IDs:        {len(set(final_ids)):,}")
    print(f"A/B core consensus:     {route_counts[AB_ROUTE]:,}")
    print(f"Model C adjudication:   {sum(route_counts[r] for r in MODEL_C_ROUTES):,}")
    print(f"Forced U:               {route_counts[FORCED_U_ROUTE]:,}")
    print(f"Direct human:           {sum(route_counts[r] for r in DIRECT_HUMAN_ROUTES):,}")
    print(
        "A/B action unresolved: "
        f"{action_status_counts['disagreement_unadjudicated']:,} "
        "(excluded from core agreement)"
    )
    print(f"Semantic warnings:      {sum(warning_counts.values()):,} source flags")
    print(f"Agreement policy:       {POLICY_VERSION}")
    if args.dry_run:
        print("Dry run: all invariants passed; no files written; no provider requests made")
        return 0

    output_dir = resolved(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "af_research_database_final_v1.jsonl"
    csv_path = output_dir / "af_research_database_final_v1.csv"
    audit_path = output_dir / "af_research_database_final_audit_v1.csv"
    summary_path = output_dir / "af_research_database_final_summary_v1.json"
    lock_path = output_dir / "af_research_database_final_v1.lock.json"

    outputs: dict[str, dict[str, Any]] = {}
    outputs[jsonl_path.name] = {
        "path": str(jsonl_path),
        "records": len(final_records),
        "sha256": write_jsonl(jsonl_path, final_records),
    }
    outputs[csv_path.name] = {
        "path": str(csv_path),
        "records": len(flat_rows),
        "sha256": write_csv(csv_path, flat_rows),
    }
    outputs[audit_path.name] = {
        "path": str(audit_path),
        "records": len(audit_rows),
        "sha256": write_csv(audit_path, audit_rows),
    }

    created_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema_version": "af-production-final-database-summary-v1",
        "created_at_utc": created_at,
        "records": len(final_records),
        "unique_work_ids": len(set(final_ids)),
        "coverage_complete": final_ids == ordered_ids,
        "agreement_policy": {
            "version": POLICY_VERSION,
            "core_fields": list(CORE_DECISION_FIELDS),
            "observed_actions_excluded_from_core_agreement": True,
            "unresolved_ab_action_policy": (
                "Retain both A/B values; final observed_actions is null; do not union or select one."
            ),
        },
        "route_counts": dict(sorted(route_counts.items())),
        "decision_route_counts": dict(Counter(r["decision_route"] for r in final_records)),
        "primary_label_counts": dict(sorted(label_counts.items())),
        "relevance_level_counts": dict(sorted(relevance_counts.items())),
        "evidence_level_counts": dict(sorted(evidence_counts.items())),
        "af_use_label_counts": dict(sorted(af_use_counts.items())),
        "adoption_eligible_counts": dict(sorted(adoption_counts.items())),
        "observed_actions_status_counts": dict(sorted(action_status_counts.items())),
        "semantic_warning_source_counts": dict(sorted(warning_counts.items())),
        "audit_records": len(audit_rows),
        "local_only": True,
        "provider_requests_made": 0,
        "outputs": outputs,
    }
    outputs[summary_path.name] = {
        "path": str(summary_path),
        "records": 1,
        "sha256": write_json(summary_path, summary),
    }

    lock = {
        "schema_version": "af-production-final-database-lock-v1",
        "created_at_utc": created_at,
        "expected_records": args.expected_records,
        "ordered_work_id_sha256": sha256_bytes("\n".join(ordered_ids).encode()),
        "sources": {
            label: {"path": str(paths[label]), "sha256": source_hashes[label]}
            for label in paths
        },
        "source_record_counts": {
            "frozen_input": len(packets),
            "reconciliation": len(reconciliation),
            "model_a_canonical": len(model_a),
            "model_b_canonical": len(model_b),
            "model_c_canonical_complete": len(model_c),
            "direct_human_canonical": len(direct_human),
        },
        "merge_policy": {
            "agreement_policy": POLICY_VERSION,
            "routes_are_mutually_exclusive": True,
            "join_key": "work_id",
            "output_order": "frozen_input_order",
            "observed_actions_disagreement": "retained_both_values_without_final_action",
        },
        "implementation": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "agreement_module": str((CODE_ROOT / "fulltext_pipeline/agreement_policy.py").resolve()),
            "agreement_module_sha256": sha256_file(CODE_ROOT / "fulltext_pipeline/agreement_policy.py"),
        },
        "outputs": outputs,
    }
    lock_sha = write_json(lock_path, lock)

    print(f"Output directory:       {output_dir}")
    print(f"Final JSONL SHA-256:     {outputs[jsonl_path.name]['sha256']}")
    print(f"Final CSV SHA-256:       {outputs[csv_path.name]['sha256']}")
    print(f"Lock SHA-256:            {lock_sha}")
    print("Merge complete; no provider requests were made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
