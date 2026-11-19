#!/usr/bin/env python3
"""Freeze valid Model C results and prepare the residual human queue.

This command is local-only. It does not call any model or external API. Every
candidate response is revalidated against the frozen packet and current schema,
then written to a canonical append-free snapshot with source-level provenance.
The residual packet set is joined to Model A/B decisions for human adjudication.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

DEFAULTS = {
    "input": "fulltext/production/adjudication_v1/production_model_c_inputs_v1.jsonl",
    "model_a": "fulltext/production/adjudication_v1/model_a_canonical_valid_v1.jsonl",
    "model_b": "fulltext/production/adjudication_v1/model_b_canonical_valid_v1.jsonl",
    "original_valid": "fulltext/production/model_outputs_v1/model_c_gpt_5_6_luna_xhigh_v1.jsonl",
    "original_recovered": "fulltext/production/model_c_local_recovery_v2/model_c_local_recovered_v2.jsonl",
    "original_human": "fulltext/production/model_c_local_recovery_v2/model_c_human_review_inputs_v2.jsonl",
    "original_worklist": "fulltext/production/model_c_local_recovery_v2/model_c_human_review_worklist_v2.csv",
    "retry_valid": "fulltext/production/model_outputs_v1/model_c_retry551_luna_xhigh_v2.jsonl",
    "retry_recovered": "fulltext/production/model_c_retry551_local_recovery_v2/model_c_local_recovered_v2.jsonl",
    "retry_human": "fulltext/production/model_c_retry551_local_recovery_v2/model_c_human_review_inputs_v2.jsonl",
    "retry_worklist": "fulltext/production/model_c_retry551_local_recovery_v2/model_c_human_review_worklist_v2.csv",
    "schema": "config/af_review_output_schema_v2.json",
    "output_dir": "fulltext/production/model_c_finalization_v1",
}

ROUTES = (
    ("original_api_valid", "original_valid"),
    ("original_local_recovery", "original_recovered"),
    ("retry551_api_valid", "retry_valid"),
    ("retry551_local_recovery", "retry_recovered"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in DEFAULTS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=Path(default))
    parser.add_argument("--expected-inputs", type=int, default=9_677)
    parser.add_argument("--expected-valid", type=int, default=9_607)
    parser.add_argument("--expected-human", type=int, default=70)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            yield line_number, value


def unique_jsonl(path: Path, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line_number, row in iter_jsonl(path):
        review_id = row.get("review_id")
        if not isinstance(review_id, str) or not review_id:
            raise ValueError(f"{label}:{line_number}: missing review_id")
        if row.get("work_id") != review_id:
            raise ValueError(f"{label}:{line_number}: review_id/work_id mismatch")
        if review_id in result:
            raise ValueError(f"{label}: duplicate review_id {review_id}")
        result[review_id] = row
    return result


def read_csv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        review_id = row.get("review_id", "").strip()
        if not review_id or review_id in result:
            raise ValueError(f"Invalid or duplicate review_id in {path}: {review_id!r}")
        result[review_id] = row
    return result


def load_runner() -> Any:
    path = CODE_ROOT / "08_run_model_review.py"
    spec = importlib.util.spec_from_file_location("model_c_finalization_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic_write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    digest = sha256_bytes(data)
    checksum = path.with_suffix(path.suffix + ".sha256")
    checksum.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    return digest


def write_json(path: Path, value: Any) -> str:
    return atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    digest = hashlib.sha256()
    with temporary.open("wb") as handle:
        for record in records:
            data = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode()
            handle.write(data)
            digest.update(data)
    temporary.replace(path)
    value = digest.hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{value}  {path.name}\n", encoding="ascii"
    )
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    fields = list(rows[0]) if rows else ["review_id", "work_id"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return atomic_write(path, buffer.getvalue().encode())


def response_summary(response: dict[str, Any] | None, prefix: str) -> dict[str, Any]:
    response = response or {}
    return {
        f"{prefix}_primary_label": response.get("primary_label", ""),
        f"{prefix}_relevance_level": response.get("relevance_level", ""),
        f"{prefix}_evidence_level": response.get("evidence_level", ""),
        f"{prefix}_af_related_label": response.get("af_related_label", ""),
        f"{prefix}_af_use_label": response.get("af_use_label", ""),
        f"{prefix}_adoption_eligible": response.get("adoption_eligible", ""),
        f"{prefix}_future_or_hypothetical_only": response.get("future_or_hypothetical_only", ""),
        f"{prefix}_observed_actions": "|".join(response.get("observed_actions") or []),
        f"{prefix}_reasoning_summary": response.get("reasoning_summary", ""),
    }


def main() -> int:
    args = parse_args()
    paths = {name: resolve(getattr(args, name)) for name in DEFAULTS}
    for name, path in paths.items():
        if name != "output_dir" and not path.is_file():
            raise FileNotFoundError(path)

    packet_order: list[str] = []
    packets: dict[str, dict[str, Any]] = {}
    for line_number, packet in iter_jsonl(paths["input"]):
        review_id = packet.get("review_id")
        if not isinstance(review_id, str) or review_id != packet.get("work_id"):
            raise ValueError(f"input:{line_number}: invalid identity")
        if review_id in packets:
            raise ValueError(f"input: duplicate review_id {review_id}")
        packet_order.append(review_id)
        packets[review_id] = packet
    if len(packets) != args.expected_inputs:
        raise ValueError(f"Expected {args.expected_inputs} inputs, found {len(packets)}")

    runner = load_runner()
    schema = json.loads(paths["schema"].read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    sources: dict[str, dict[str, dict[str, Any]]] = {}
    accepted: dict[str, tuple[str, dict[str, Any]]] = {}
    source_hashes: dict[str, str] = {}
    route_counts: Counter[str] = Counter()

    for route, key in ROUTES:
        source_path = paths[key]
        source_hashes[key] = sha256_file(source_path)
        rows = unique_jsonl(source_path, route)
        sources[key] = rows
        for review_id, envelope in rows.items():
            packet = packets.get(review_id)
            if packet is None:
                raise ValueError(f"{route}/{review_id}: outside frozen Model C queue")
            if review_id in accepted:
                raise ValueError(f"Duplicate accepted Model C record: {review_id}")
            if envelope.get("input_packet_sha256") != fingerprint(packet):
                raise ValueError(f"{route}/{review_id}: packet fingerprint mismatch")
            if envelope.get("provider") != "openrouter" or envelope.get("model") != "openai/gpt-5.6-luna":
                raise ValueError(f"{route}/{review_id}: provider/model mismatch")
            response = envelope.get("response")
            if not isinstance(response, dict):
                raise ValueError(f"{route}/{review_id}: missing response")
            errors = runner.validate_review(copy.deepcopy(response), packet, validator)
            if errors:
                raise ValueError(f"{route}/{review_id}: response no longer valid: {errors}")
            accepted[review_id] = (route, envelope)
            route_counts[route] += 1

    if len(accepted) != args.expected_valid:
        raise ValueError(f"Expected {args.expected_valid} valid records, found {len(accepted)}")

    human_original = unique_jsonl(paths["original_human"], "original_human")
    human_retry = unique_jsonl(paths["retry_human"], "retry_human")
    overlap = set(human_original) & set(human_retry)
    if overlap:
        raise ValueError(f"Human queues overlap: {sorted(overlap)[:5]}")
    human_ids = set(human_original) | set(human_retry)
    if len(human_ids) != args.expected_human:
        raise ValueError(f"Expected {args.expected_human} human records, found {len(human_ids)}")
    if set(accepted) & human_ids:
        raise ValueError("Valid and human routes overlap")
    if set(accepted) | human_ids != set(packets):
        raise ValueError(
            f"Coverage mismatch: missing={len(set(packets)-set(accepted)-human_ids)}, "
            f"extra={len((set(accepted)|human_ids)-set(packets))}"
        )

    model_a = unique_jsonl(paths["model_a"], "model_a")
    model_b = unique_jsonl(paths["model_b"], "model_b")
    original_worklist = read_csv(paths["original_worklist"])
    retry_worklist = read_csv(paths["retry_worklist"])

    canonical: list[dict[str, Any]] = []
    for review_id in packet_order:
        if review_id not in accepted:
            continue
        route, envelope = accepted[review_id]
        source_key = dict(ROUTES)[route]
        source_path = paths[source_key]
        source_attempt = envelope.get("source_attempt") or {}
        canonical.append({
            "schema_version": "af-production-canonical-model-review-v1",
            "review_id": review_id,
            "work_id": review_id,
            "provider": "openrouter",
            "model": "openai/gpt-5.6-luna",
            "validation_status": "valid",
            "source_model": "model_c",
            "source_route": route,
            "provenance": {
                "source_path": rel(source_path),
                "source_file_sha256": source_hashes[source_key],
                "source_record_sha256": fingerprint(envelope),
                "source_run_id": envelope.get("run_id") or source_attempt.get("run_id"),
                "source_attempt_number": source_attempt.get("attempt_number"),
                "source_artifact": envelope.get("run_artifact"),
                "input_packet_sha256": envelope.get("input_packet_sha256"),
                "recovery_status": envelope.get("recovery_status"),
                "local_transformations": envelope.get("local_transformations") or [],
            },
            "response": envelope["response"],
        })

    human_packets: list[dict[str, Any]] = []
    human_worklist: list[dict[str, Any]] = []
    for review_id in packet_order:
        if review_id not in human_ids:
            continue
        packet = packets[review_id]
        batch = "original" if review_id in human_original else "retry551"
        worklist = original_worklist.get(review_id) if batch == "original" else retry_worklist.get(review_id)
        if not worklist:
            raise ValueError(f"Missing worklist metadata for {review_id}")
        a_envelope = model_a.get(review_id)
        b_envelope = model_b.get(review_id)
        a = (a_envelope or {}).get("response")
        b = (b_envelope or {}).get("response")
        if a is not None and not isinstance(a, dict):
            raise ValueError(f"Invalid Model A canonical response for {review_id}")
        if b is not None and not isinstance(b, dict):
            raise ValueError(f"Invalid Model B canonical response for {review_id}")
        if a is None and b is None:
            raise ValueError(f"Both A and B canonical responses are missing for {review_id}")
        human_packets.append({
            "schema_version": "af-model-c-human-adjudication-input-v1",
            "adjudication_order": len(human_packets) + 1,
            "review_id": review_id,
            "work_id": review_id,
            "source_batch": batch,
            "failure_categories": worklist.get("categories", ""),
            "validation_errors": worklist.get("validation_errors", ""),
            "input_packet_sha256": fingerprint(packet),
            "packet": packet,
            "model_a": a_envelope,
            "model_b": b_envelope,
        })
        material = packet.get("input_material") or {}
        quality = packet.get("input_quality") or {}
        row = {
            "adjudication_order": len(human_packets),
            "review_id": review_id,
            "work_id": review_id,
            "source_batch": batch,
            "failure_categories": worklist.get("categories", ""),
            "validation_errors": worklist.get("validation_errors", ""),
            "title": material.get("title", ""),
            "publication_year": material.get("publication_year", ""),
            "doi": material.get("doi", ""),
            "evidence_tier": packet.get("evidence_tier", ""),
            "abstract_status": quality.get("abstract_status", ""),
            "model_a_status": "valid" if a is not None else "missing",
            "model_b_status": "valid" if b is not None else "missing",
            **response_summary(a, "model_a"),
            **response_summary(b, "model_b"),
        }
        human_worklist.append(row)

    summary = {
        "schema_version": "af-model-c-finalization-summary-v1",
        "created_at_utc": utc_now(),
        "local_only": True,
        "provider_requests_made": 0,
        "frozen_model_c_inputs": len(packets),
        "canonical_valid_records": len(canonical),
        "human_adjudication_records": len(human_packets),
        "coverage_complete": len(canonical) + len(human_packets) == len(packets),
        "route_counts": dict(route_counts),
        "human_source_batches": dict(Counter(row["source_batch"] for row in human_packets)),
        "human_failure_categories": dict(Counter(row["failure_categories"] for row in human_packets)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    output_dir = paths["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "canonical": output_dir / "model_c_canonical_valid_v1.jsonl",
        "human_inputs": output_dir / "model_c_human_adjudication_inputs_v1.jsonl",
        "human_worklist": output_dir / "model_c_human_adjudication_worklist_v1.csv",
        "summary": output_dir / "model_c_finalization_summary_v1.json",
        "lock": output_dir / "model_c_finalization_v1.lock.json",
    }
    output_hashes = {
        "canonical": write_jsonl(outputs["canonical"], canonical),
        "human_inputs": write_jsonl(outputs["human_inputs"], human_packets),
        "human_worklist": write_csv(outputs["human_worklist"], human_worklist),
        "summary": write_json(outputs["summary"], summary),
    }
    lock = {
        "schema_version": "af-model-c-finalization-lock-v1",
        "created_at_utc": utc_now(),
        "summary": summary,
        "sources": {
            name: {"path": rel(path), "sha256": sha256_file(path)}
            for name, path in paths.items() if name != "output_dir"
        },
        "outputs": {
            key: {"path": rel(outputs[key]), "sha256": value}
            for key, value in output_hashes.items()
        },
        "ordered_input_ids_sha256": sha256_bytes(("\n".join(packet_order) + "\n").encode()),
        "ordered_canonical_ids_sha256": sha256_bytes(
            ("\n".join(row["review_id"] for row in canonical) + "\n").encode()
        ),
        "ordered_human_ids_sha256": sha256_bytes(
            ("\n".join(row["review_id"] for row in human_packets) + "\n").encode()
        ),
    }
    write_json(outputs["lock"], lock)
    print(f"Canonical Model C: {outputs['canonical']}")
    print(f"Human adjudication inputs: {outputs['human_inputs']}")
    print(f"Human worklist: {outputs['human_worklist']}")
    print(f"Lock: {outputs['lock']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
