#!/usr/bin/env python3
"""Build blinded model-review packets for the stratified AlphaFold pilot.

The model JSONL deliberately excludes the existing af_usage_level label and
sampling metadata. Those fields are written to a separate key CSV for scoring
after model outputs have been frozen.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fulltext_pipeline.common import DEFAULT_DB_PATH, PROJECT_ROOT
from fulltext_pipeline.model_review_support import prepare_packet


DEFAULT_PILOT_FILE = PROJECT_ROOT / "fulltext" / "pilot" / "pilot_150.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fulltext" / "pilot" / "model_inputs_v5"
DEFAULT_MAX_PACKET_TOKENS = 30_000
CONTEXT_POLICY = {
    "version": "af-context-window-v2",
    "base_radius": 1,
    "direct_mention_radius": 2,
    "expanded_neighbors_same_section": True,
    "citation_only_radius": 1,
    "full_document_included": False,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--pilot-file", type=Path, default=DEFAULT_PILOT_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--max-packet-tokens",
        type=int,
        default=DEFAULT_MAX_PACKET_TOKENS,
        help="Fail safely if an eligible packet exceeds this estimated input-token cap",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def read_pilot(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        records = list(csv.DictReader(handle))
    if not records or "work_id" not in records[0]:
        raise ValueError(f"Pilot CSV must contain work_id: {path}")
    work_ids = [record["work_id"].strip() for record in records]
    if any(not work_id for work_id in work_ids):
        raise ValueError("Pilot CSV contains an empty work_id")
    if len(work_ids) != len(set(work_ids)):
        raise ValueError("Pilot CSV contains duplicate work_id values")
    return records


def load_manifest_rows(db_path: Path, work_ids: list[str]) -> dict[str, dict[str, Any]]:
    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in work_ids)
        rows = connection.execute(
            f"SELECT * FROM works WHERE in_current_corpus=1 AND work_id IN ({placeholders})",  # noqa: S608
            work_ids,
        ).fetchall()
        result = {row["work_id"]: dict(row) for row in rows}
    finally:
        connection.close()
    missing = sorted(set(work_ids) - set(result))
    if missing:
        raise ValueError(f"Pilot work IDs missing from current manifest: {missing[:10]}")
    return result


def sha256_lines(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def load_document(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        raise ValueError("Parsed document path is missing")
    path = Path(path_value)
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "af-fulltext-context-v2":
        raise ValueError(
            f"Expected af-fulltext-context-v2 for {document.get('work_id')}, "
            f"got {document.get('schema_version')!r}"
        )
    return document


def unique_evidence_blocks(document: dict[str, Any]) -> list[dict[str, Any]]:
    paragraphs = {item["index"]: item for item in document.get("paragraphs", [])}
    evidence_by_index = {
        item["paragraph_index"]: item for item in document.get("evidence_contexts", [])
    }
    selected_indices: set[int] = set()
    for index, evidence in evidence_by_index.items():
        # Preserve the v4 baseline for every trigger, including citation-only
        # evidence. This may cross a section boundary because it is the existing
        # auditable ±1 window and avoids silently dropping previously supplied text.
        selected_indices.update(value for value in (index - 1, index, index + 1) if value in paragraphs)
        # Only direct AF mentions receive the modest v5 expansion. The additional
        # outer neighbors must remain in the same section as the anchor so that an
        # AF mention near a heading does not pull in an unrelated section.
        if "direct_mention" in evidence.get("trigger_types", []):
            anchor_section = str(paragraphs[index].get("section") or "").strip().casefold()
            selected_indices.update(
                value
                for value in (index - 2, index + 2)
                if value in paragraphs
                and str(paragraphs[value].get("section") or "").strip().casefold()
                == anchor_section
            )

    blocks: list[dict[str, Any]] = []
    for index in sorted(selected_indices):
        paragraph = paragraphs[index]
        evidence = evidence_by_index.get(index)
        block = {
            "index": index,
            "role": "evidence" if evidence else "neighbor",
            "section": paragraph.get("section"),
            "block_type": paragraph.get("block_type"),
            "text": paragraph.get("text"),
        }
        if evidence:
            block["trigger_types"] = evidence.get("trigger_types", [])
            block["matched_values"] = evidence.get("matched_values", {})
        blocks.append(block)
    return blocks


def estimate_tokens(value: Any) -> int:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return math.ceil(len(serialized) / 4)


def build_packet(
    pilot_record: dict[str, str],
    manifest: dict[str, Any],
    *,
    max_packet_tokens: int = DEFAULT_MAX_PACKET_TOKENS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    work_id = manifest["work_id"]
    review_id = f"P{int(pilot_record.get('pilot_order') or 0):03d}"
    common_material = {
        "title": manifest.get("title"),
        "abstract": manifest.get("abstract"),
        "publication_year": manifest.get("publication_year"),
        "work_type": manifest.get("work_type"),
        "doi": manifest.get("doi"),
        "domain_labels": manifest.get("domain_labels"),
    }

    if manifest.get("parse_status") == "success":
        document = load_document(manifest.get("parsed_document_path"))
        if document.get("work_id") != work_id:
            raise ValueError(f"Parsed document work_id mismatch for {work_id}")
        tier = "fulltext_evidence"
        model_eligible = True
        input_material = {
            **common_material,
            "fulltext_source": manifest.get("fetched_source"),
            "matched_seed_references": document.get("matched_seed_references", []),
            "evidence_blocks": unique_evidence_blocks(document),
            "extraction_quality": document.get("quality", {}),
        }
        forced_decision = None
    elif manifest.get("abstract"):
        tier = "abstract_only"
        model_eligible = True
        input_material = common_material
        forced_decision = None
    else:
        tier = "insufficient_evidence"
        model_eligible = False
        input_material = {**common_material, "abstract": None}
        forced_decision = {
            "label": "U",
            "reason": "No retrievable full text or abstract; do not infer non-use from missing evidence.",
        }

    packet = {
        "schema_version": "af-model-review-input-v2",
        "review_id": review_id,
        "work_id": work_id,
        "evidence_tier": tier,
        "model_eligible": model_eligible,
        "forced_decision": forced_decision,
        "context_policy": CONTEXT_POLICY,
        "input_material": input_material,
    }
    packet = prepare_packet(packet)
    if packet["model_eligible"] and packet["estimated_input_tokens"] > max_packet_tokens:
        raise ValueError(
            f"Packet {work_id} exceeds --max-packet-tokens: "
            f"{packet['estimated_input_tokens']:,} > {max_packet_tokens:,}; "
            "review the deterministic context policy instead of silently truncating evidence"
        )
    key_record = {
        "review_id": review_id,
        "work_id": work_id,
        "af_usage_level": pilot_record.get("af_usage_level"),
        "pilot_order": pilot_record.get("pilot_order"),
        "sampling_seed": pilot_record.get("sampling_seed"),
        "inclusion_probability": pilot_record.get("inclusion_probability"),
        "sampling_weight": pilot_record.get("sampling_weight"),
        "evidence_tier": packet["evidence_tier"],
        "model_eligible": packet["model_eligible"],
        "abstract_quality": packet["input_quality"]["abstract_status"],
    }
    return packet, key_record


def print_summary(packets: list[dict[str, Any]], max_packet_tokens: int) -> None:
    tier_counts = Counter(packet["evidence_tier"] for packet in packets)
    eligible = [packet for packet in packets if packet["model_eligible"]]
    token_counts = [packet["estimated_input_tokens"] for packet in eligible]
    print(f"Pilot records:       {len(packets):,}")
    print(f"Model-eligible:      {len(eligible):,}")
    print(f"Forced U:            {len(packets) - len(eligible):,}")
    print(f"Evidence tiers:      {dict(tier_counts)}")
    print(f"Estimated tokens A:  {sum(token_counts):,}")
    print(f"Estimated tokens A+B:{2 * sum(token_counts):,}")
    print(f"Largest packet:      {max(token_counts, default=0):,}")
    print(f"Packet token cap:    {max_packet_tokens:,}")
    print(f"Context policy:      {CONTEXT_POLICY['version']} (direct mention ±2 same-section; citation ±1)")
    print(f"Abstract quality:    {dict(Counter(p['input_quality']['abstract_status'] for p in packets))}")


def write_outputs(
    output_dir: Path,
    packets: list[dict[str, Any]],
    keys: list[dict[str, Any]],
    overwrite: bool,
    max_packet_tokens: int,
) -> None:
    inputs_path = output_dir / "pilot_model_inputs.jsonl"
    key_path = output_dir / "pilot_model_key.csv"
    metadata_path = output_dir / "pilot_model_inputs.meta.json"
    if not overwrite:
        existing = [path for path in (inputs_path, key_path, metadata_path) if path.exists()]
        if existing:
            raise FileExistsError(
                "Refusing to replace existing model inputs; use --overwrite: "
                + ", ".join(str(path) for path in existing)
            )
    output_dir.mkdir(parents=True, exist_ok=True)

    inputs_tmp = inputs_path.with_suffix(inputs_path.suffix + ".part")
    with inputs_tmp.open("w", encoding="utf-8") as handle:
        for packet in packets:
            handle.write(json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n")
    inputs_tmp.replace(inputs_path)

    key_tmp = key_path.with_suffix(key_path.suffix + ".part")
    with key_tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(keys[0]))
        writer.writeheader()
        writer.writerows(keys)
    key_tmp.replace(key_path)

    metadata = {
        "schema_version": "af-model-review-input-manifest-v3",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(packets),
        "model_eligible_count": sum(packet["model_eligible"] for packet in packets),
        "forced_u_count": sum(not packet["model_eligible"] for packet in packets),
        "evidence_tiers": dict(Counter(packet["evidence_tier"] for packet in packets)),
        "estimated_input_tokens_one_model": sum(
            packet["estimated_input_tokens"]
            for packet in packets
            if packet["model_eligible"]
        ),
        "ordered_work_id_sha256": sha256_lines([packet["work_id"] for packet in packets]),
        "input_file_sha256": hashlib.sha256(inputs_path.read_bytes()).hexdigest(),
        "abstract_quality": dict(Counter(p["input_quality"]["abstract_status"] for p in packets)),
        "quality_flag_counts": dict(Counter(flag for p in packets for flag in p["input_quality"]["flags"])),
        "context_policy": CONTEXT_POLICY,
        "max_estimated_input_tokens_per_packet": max_packet_tokens,
        "blinding": "Old labels and sampling fields are excluded; detected author-navigation contamination is removed. This is not a complete geographic-blinding certification.",
    }
    metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".part")
    metadata_tmp.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata_tmp.replace(metadata_path)
    print(f"Inputs written to {inputs_path}")
    print(f"Blinded scoring key written to {key_path}")
    print(f"Metadata written to {metadata_path}")


def main() -> None:
    args = parse_args()
    if args.max_packet_tokens < 1:
        raise ValueError("--max-packet-tokens must be positive")
    pilot_records = read_pilot(args.pilot_file)
    manifest_rows = load_manifest_rows(
        args.db, [record["work_id"].strip() for record in pilot_records]
    )
    packets: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    for pilot_record in pilot_records:
        work_id = pilot_record["work_id"].strip()
        packet, key = build_packet(
            pilot_record,
            manifest_rows[work_id],
            max_packet_tokens=args.max_packet_tokens,
        )
        packets.append(packet)
        keys.append(key)
    print_summary(packets, args.max_packet_tokens)
    if args.dry_run:
        print("Dry run: no files written")
        return
    write_outputs(
        args.output_dir,
        packets,
        keys,
        args.overwrite,
        args.max_packet_tokens,
    )


if __name__ == "__main__":
    main()
