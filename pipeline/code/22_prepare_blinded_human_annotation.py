#!/usr/bin/env python3
"""Prepare immutable blinded human-review packets and deterministic assignments.

This script deliberately removes fields that reveal retrieval labels, sampling
information, machine eligibility/forced decisions, or machine-review outcomes.
It does not call any external service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "af-human-annotation-packet-v1"
MANIFEST_VERSION = "af-human-annotation-manifest-v1"
ASSIGNMENT_VERSION = "af-human-annotation-assignment-v1"
DEFAULT_SEED_A = 202609051
DEFAULT_SEED_B = 202609052

PROHIBITED_KEYS = {
    "af_usage_level",
    "sampling_weight",
    "inclusion_probability",
    "sampling_seed",
    "selection_hash",
    "usage_population_n",
    "usage_selected_n",
    "year_band_population_n",
    "year_band_selected_n",
    "evidence_tier",
    "model_eligible",
    "forced_decision",
    "estimated_input_tokens",
    "primary_label",
    "relevance_level",
    "evidence_level",
    "af_related_label",
    "af_use_label",
    "adoption_eligible",
    "observed_actions",
    "machine_consensus",
    "model_a",
    "model_b",
    "model_c",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256_sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(f"{sha256_file(path)}  {path.name}\n", encoding="utf-8")


def walk_keys(value: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            yield path
            yield from walk_keys(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_keys(child, f"{prefix}[{index}]")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def build_blinded_record(row: dict[str, Any]) -> dict[str, Any]:
    required = {"review_id", "work_id", "context_policy", "input_material", "input_quality"}
    missing = sorted(required - row.keys())
    if missing:
        raise ValueError(f"{row.get('work_id', '<unknown>')}: missing required keys {missing}")

    blinded = {
        "schema_version": SCHEMA_VERSION,
        "review_id": row["review_id"],
        "work_id": row["work_id"],
        "context_policy": row["context_policy"],
        "input_material": row["input_material"],
        "input_quality": row["input_quality"],
    }
    blinded["packet_sha256"] = sha256_bytes(canonical_json(blinded).encode("utf-8"))
    return blinded


def build_assignment(
    records: list[dict[str, Any]], annotator_id: str, seed: int
) -> dict[str, Any]:
    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    entries = []
    for order, record in enumerate(shuffled, 1):
        entries.append(
            {
                "assignment_order": order,
                "reviewer_record_id": f"{annotator_id}{order:03d}",
                "review_id": record["review_id"],
                "work_id": record["work_id"],
                "packet_sha256": record["packet_sha256"],
            }
        )
    order_payload = [entry["review_id"] for entry in entries]
    return {
        "schema_version": ASSIGNMENT_VERSION,
        "annotator_id": annotator_id,
        "seed": seed,
        "record_count": len(entries),
        "ordered_review_id_sha256": sha256_bytes(canonical_json(order_payload).encode("utf-8")),
        "records": entries,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_sha256_sidecar(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("fulltext/pilot/model_inputs_v5/pilot_model_inputs.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("fulltext/pilot/human_annotation_v4_3"),
    )
    parser.add_argument(
        "--version-tag",
        default="v4_3",
        help="Filename tag for packets, assignments, and manifests (for example: v6).",
    )
    parser.add_argument(
        "--protocol-version",
        default="af-review-v2",
        help="Human-readable protocol identifier stored in reproducibility metadata.",
    )
    parser.add_argument(
        "--codebook-file",
        type=Path,
        default=Path("config/af_review_prompt_v2.txt"),
    )
    parser.add_argument(
        "--schema-file",
        type=Path,
        default=Path("config/af_review_output_schema_v2.json"),
    )
    parser.add_argument("--expected-records", type=int, default=150)
    parser.add_argument("--seed-a", type=int, default=DEFAULT_SEED_A)
    parser.add_argument("--seed-b", type=int, default=DEFAULT_SEED_B)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    version_tag = args.version_tag.strip()
    if not version_tag or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in version_tag):
        raise ValueError("--version-tag must contain only letters, digits, underscore, or hyphen")
    output_dir.mkdir(parents=True, exist_ok=True)

    source_rows = read_jsonl(source_path)
    if len(source_rows) != args.expected_records:
        raise ValueError(
            f"Expected {args.expected_records} source records, found {len(source_rows)}"
        )

    records = [build_blinded_record(row) for row in source_rows]
    review_ids = [row["review_id"] for row in records]
    work_ids = [row["work_id"] for row in records]
    if len(set(review_ids)) != len(review_ids):
        raise ValueError("Duplicate review_id in blinded records")
    if len(set(work_ids)) != len(work_ids):
        raise ValueError("Duplicate work_id in blinded records")

    prohibited_paths = sorted(
        path
        for record in records
        for path in walk_keys(record)
        if path.rsplit(".", 1)[-1].split("[", 1)[0] in PROHIBITED_KEYS
    )
    if prohibited_paths:
        raise ValueError(f"Blinding audit failed; prohibited keys found: {prohibited_paths[:20]}")

    packet_path = output_dir / f"pilot_150_human_packets_blinded_{version_tag}.jsonl"
    packet_text = "".join(canonical_json(record) + "\n" for record in records)
    packet_path.write_text(packet_text, encoding="utf-8")
    write_sha256_sidecar(packet_path)

    assignment_a = build_assignment(records, "A", args.seed_a)
    assignment_b = build_assignment(records, "B", args.seed_b)
    assignment_a_path = output_dir / f"pilot_150_annotator_a_assignment_{version_tag}.json"
    assignment_b_path = output_dir / f"pilot_150_annotator_b_assignment_{version_tag}.json"
    write_json(assignment_a_path, assignment_a)
    write_json(assignment_b_path, assignment_b)

    codebook_path = args.codebook_file.resolve()
    schema_path = args.schema_file.resolve()
    if not codebook_path.is_file():
        raise FileNotFoundError(codebook_path)
    if not schema_path.is_file():
        raise FileNotFoundError(schema_path)
    context_policy_versions = sorted(
        {
            str(record.get("context_policy", {}).get("version") or "unknown")
            for record in records
        }
    )
    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "created_at_utc": created_at,
        "version_tag": version_tag,
        "protocol_version": args.protocol_version,
        "source_file": source_path.name,
        "source_file_sha256": sha256_file(source_path),
        "packet_file": packet_path.name,
        "packet_file_sha256": sha256_file(packet_path),
        "record_count": len(records),
        "context_policy_versions": context_policy_versions,
        "assignment_files": {
            "A": {
                "file": assignment_a_path.name,
                "sha256": sha256_file(assignment_a_path),
                "seed": args.seed_a,
                "ordered_review_id_sha256": assignment_a["ordered_review_id_sha256"],
            },
            "B": {
                "file": assignment_b_path.name,
                "sha256": sha256_file(assignment_b_path),
                "seed": args.seed_b,
                "ordered_review_id_sha256": assignment_b["ordered_review_id_sha256"],
            },
        },
        "codebook_source": {
            "file": codebook_path.name,
            "sha256": sha256_file(codebook_path),
        },
        "output_schema_source": {
            "file": schema_path.name,
            "sha256": sha256_file(schema_path),
        },
        "blinding": {
            "prohibited_keys": sorted(PROHIBITED_KEYS),
            "prohibited_key_occurrences": 0,
            "machine_outputs_included": False,
            "old_retrieval_labels_included": False,
            "sampling_fields_included": False,
            "assignment_orders_are_independently_shuffled": True,
        },
    }
    manifest_path = output_dir / f"pilot_150_human_annotation_manifest_{version_tag}.json"
    write_json(manifest_path, manifest)

    print(f"Source records:            {len(source_rows)}")
    print(f"Blinded packets:           {len(records)}")
    print("Prohibited-key occurrences:0")
    print(f"Packet file:               {packet_path}")
    print(f"Assignment A:              {assignment_a_path}")
    print(f"Assignment B:              {assignment_b_path}")
    print(f"Manifest:                  {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
