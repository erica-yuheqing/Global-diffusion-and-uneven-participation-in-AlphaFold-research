#!/usr/bin/env python3
"""Build deterministic, blinded model-review packets for the full corpus.

This production builder deliberately leaves the Pilot builder and all frozen
Pilot artifacts unchanged. It performs no provider or model API requests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fulltext_pipeline.common import DEFAULT_DB_PATH, PROJECT_ROOT


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fulltext" / "production" / "model_inputs_v1"
DEFAULT_PROTOCOL = PROJECT_ROOT / "config" / "af_production_protocol_v1.json"
PILOT_BUILDER = PROJECT_ROOT / "code" / "07_build_model_packets.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--work-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-packet-tokens", type=int, default=30_000)
    parser.add_argument(
        "--audit-over-cap",
        action="store_true",
        help="With --dry-run, report packets above the formal cap instead of stopping at the first one",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_lines(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_pilot_builder() -> Any:
    spec = importlib.util.spec_from_file_location("af_frozen_pilot_packet_builder", PILOT_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load packet builder: {PILOT_BUILDER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rows(db_path: Path, work_ids: list[str], limit: int | None) -> list[dict[str, Any]]:
    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM works WHERE in_current_corpus=1"
        params: list[Any] = []
        if work_ids:
            placeholders = ",".join("?" for _ in work_ids)
            sql += f" AND work_id IN ({placeholders})"  # noqa: S608
            params.extend(work_ids)
        sql += " ORDER BY work_id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = [dict(row) for row in connection.execute(sql, params)]
    finally:
        connection.close()
    if work_ids:
        found = {row["work_id"] for row in rows}
        missing = sorted(set(work_ids) - found)
        if missing:
            raise ValueError(f"Requested work IDs missing from current corpus: {missing[:10]}")
    return rows


def write_outputs(
    output_dir: Path,
    packets: list[dict[str, Any]],
    keys: list[dict[str, Any]],
    protocol: Path,
    max_packet_tokens: int,
    overwrite: bool,
) -> None:
    inputs_path = output_dir / "full_model_inputs.jsonl"
    key_path = output_dir / "full_model_key.csv"
    metadata_path = output_dir / "full_model_inputs.meta.json"
    targets = (inputs_path, key_path, metadata_path)
    if not overwrite and any(path.exists() for path in targets):
        raise FileExistsError("Production inputs already exist; use a new directory or --overwrite")
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
        "schema_version": "af-full-model-input-manifest-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(packets),
        "model_eligible_count": sum(bool(p["model_eligible"]) for p in packets),
        "forced_u_count": sum(not p["model_eligible"] for p in packets),
        "evidence_tiers": dict(Counter(p["evidence_tier"] for p in packets)),
        "estimated_input_tokens_one_model": sum(
            p["estimated_input_tokens"] for p in packets if p["model_eligible"]
        ),
        "largest_packet_tokens": max(
            (p["estimated_input_tokens"] for p in packets if p["model_eligible"]), default=0
        ),
        "max_packet_tokens": max_packet_tokens,
        "ordered_work_id_sha256": sha256_lines([p["work_id"] for p in packets]),
        "input_file_sha256": sha256_file(inputs_path),
        "protocol_path": str(protocol.resolve()),
        "protocol_sha256": sha256_file(protocol),
        "packet_builder_dependency": str(PILOT_BUILDER.resolve()),
        "packet_builder_dependency_sha256": sha256_file(PILOT_BUILDER),
        "review_id_policy": "stable work_id",
        "blinding": "af_usage_level and sampling fields are excluded from model inputs and retained only in the separate key CSV",
    }
    metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".part")
    metadata_tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata_tmp.replace(metadata_path)
    print(f"Inputs written to {inputs_path}")
    print(f"Blinded scoring key written to {key_path}")
    print(f"Metadata written to {metadata_path}")


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be positive")
    if args.max_packet_tokens < 1:
        raise ValueError("--max-packet-tokens must be positive")
    if args.audit_over_cap and not args.dry_run:
        raise ValueError("--audit-over-cap is read-only and requires --dry-run")
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if protocol.get("schema_version") != "af-production-protocol-v1":
        raise ValueError(f"Unexpected production protocol: {protocol.get('schema_version')!r}")
    rows = load_rows(args.db, args.work_id, args.limit)
    if not rows:
        raise ValueError("No current-corpus rows selected")
    builder = load_pilot_builder()
    packets: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    tier_counts: Counter[str] = Counter()
    eligible_count = 0
    token_total = 0
    largest_packet = 0
    over_cap: list[tuple[str, int]] = []
    for order, manifest in enumerate(rows, 1):
        pseudo_record = {
            "pilot_order": str(order),
            "af_usage_level": manifest.get("af_usage_level") or "",
        }
        packet, key = builder.build_packet(
            pseudo_record,
            manifest,
            # Production handles exceptional oversized packets explicitly
            # below instead of allowing the frozen Pilot builder to truncate.
            max_packet_tokens=1_000_000,
        )
        packet["review_id"] = manifest["work_id"]
        packet["production_protocol"] = protocol["schema_version"]
        key["review_id"] = manifest["work_id"]
        key.pop("pilot_order", None)
        key.pop("sampling_seed", None)
        key.pop("inclusion_probability", None)
        key.pop("sampling_weight", None)
        key["oversize_context_tokens"] = ""
        key["mandatory_human_review_reason"] = ""
        key["human_review_source_path"] = ""
        if packet["model_eligible"] and packet["estimated_input_tokens"] > args.max_packet_tokens:
            original_tokens = packet["estimated_input_tokens"]
            over_cap.append((manifest["work_id"], original_tokens))
            material = packet["input_material"]
            material["evidence_blocks"] = []
            material["matched_seed_references"] = []
            material["oversize_context_not_embedded"] = {
                "original_estimated_input_tokens": original_tokens,
                "formal_packet_token_cap": args.max_packet_tokens,
                "reason": "Source document is retained locally for mandatory human review; no evidence was silently truncated or sent to a model.",
            }
            packet["evidence_tier"] = "oversize_context_human_review"
            packet["model_eligible"] = False
            packet["forced_decision"] = {
                "label": "U",
                "primary_label": "uncertain",
                "relevance_level": "RU",
                "evidence_level": "E0",
                "af_related_label": "uncertain",
                "af_use_label": "uncertain",
                "adoption_eligible": "uncertain",
                "needs_human_review": True,
                "reason": "Deterministic evidence packet exceeds the production token cap; mandatory human review is required.",
            }
            quality = packet.setdefault("input_quality", {})
            quality["flags"] = sorted(
                {*quality.get("flags", []), "oversize_context_requires_human_review"}
            )
            packet["estimated_input_tokens"] = builder.estimate_tokens(material)
            key["oversize_context_tokens"] = original_tokens
            key["mandatory_human_review_reason"] = "oversize_context"
            key["human_review_source_path"] = manifest.get("parsed_document_path") or ""
        tier_counts[packet["evidence_tier"]] += 1
        if packet["model_eligible"]:
            eligible_count += 1
            token_total += packet["estimated_input_tokens"]
            largest_packet = max(largest_packet, packet["estimated_input_tokens"])
        # A full dry run is deliberately streaming so that readiness/cost
        # estimation does not retain hundreds of MB of packet objects in RAM.
        if not args.dry_run:
            packets.append(packet)
            keys.append(key)
    print(f"Full-corpus records:  {len(rows):,}")
    print(f"Model-eligible:       {eligible_count:,}")
    print(f"Forced U, no API:     {len(rows) - eligible_count:,}")
    print(f"Evidence tiers:       {dict(tier_counts)}")
    print(f"Estimated tokens/model:{token_total:,}")
    print(f"Estimated tokens A+B: {token_total * 2:,}")
    print(f"Largest packet:       {largest_packet:,}")
    print(f"Oversize -> human:    {len(over_cap):,}")
    if args.audit_over_cap:
        print(f"Original packets over:{len(over_cap):,} / {args.max_packet_tokens:,} tokens")
        for work_id, tokens in sorted(over_cap, key=lambda item: item[1], reverse=True)[:20]:
            print(f"  {work_id}: {tokens:,}")
    print(f"Protocol:             {protocol['schema_version']}")
    if args.dry_run:
        print("Dry run: no files written")
        return
    write_outputs(
        args.output_dir,
        packets,
        keys,
        args.protocol,
        args.max_packet_tokens,
        args.overwrite,
    )


if __name__ == "__main__":
    main()
