#!/usr/bin/env python3
"""Recover paid Model C responses locally without making provider requests.

The append-only attempt journal contains the full visible response returned by
the provider for every HTTP 200 request.  This command replays those responses
against the current schema and semantic validator, applies only narrow,
auditable repairs, and writes recovered and unresolved records separately.  It
never modifies the original model output or attempt journal.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import re
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from fulltext_pipeline.model_review_support import (  # noqa: E402
    AF_TERM,
    af_evaluation_signal,
    explicit_run_quote,
    fingerprint,
    source_texts,
    substantive_docking_or_screening_quote,
)


DEFAULT_INPUT = (
    PROJECT_ROOT
    / "fulltext/production/adjudication_v1/production_model_c_inputs_v1.jsonl"
)
DEFAULT_SCHEMA = PROJECT_ROOT / "config/af_review_output_schema_v2.json"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "fulltext/production/model_outputs_v1/model_c_gpt_5_6_luna_xhigh_v1.jsonl"
)
DEFAULT_ATTEMPTS = DEFAULT_OUTPUT.with_name(DEFAULT_OUTPUT.stem + ".attempts.jsonl")
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fulltext/production/model_c_local_recovery_v2"
RECOVERY_VERSION = "af-model-c-local-recovery-v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--existing-output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--attempts", type=Path, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--max-responses-per-work",
        type=int,
        default=12,
        help="Keep this many most-recent paid responses per unresolved work.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolved(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


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


def load_runner() -> Any:
    path = CODE_ROOT / "08_run_model_review.py"
    spec = importlib.util.spec_from_file_location("model_c_recovery_runner", path)
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
    checksum_temp = checksum.with_suffix(checksum.suffix + ".part")
    checksum_temp.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    checksum_temp.replace(checksum)
    return digest


def write_json(path: Path, value: Any) -> str:
    return atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> str:
    data = b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode()
        for record in records
    )
    return atomic_write(path, data)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    fields = list(rows[0]) if rows else ["review_id", "work_id", "categories"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return atomic_write(path, buffer.getvalue().encode())


def load_packets(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    order: list[str] = []
    packets: dict[str, dict[str, Any]] = {}
    for line_number, packet in iter_jsonl(path):
        work_id = packet.get("work_id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError(f"Missing work_id at {path}:{line_number}")
        if packet.get("review_id") != work_id:
            raise ValueError(f"review_id/work_id mismatch at {path}:{line_number}")
        if work_id in packets:
            raise ValueError(f"Duplicate packet: {work_id}")
        order.append(work_id)
        packets[work_id] = packet
    return order, packets


def load_completed_ids(path: Path) -> set[str]:
    completed: set[str] = set()
    for line_number, record in iter_jsonl(path):
        work_id = record.get("work_id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError(f"Missing work_id at {path}:{line_number}")
        if work_id in completed:
            raise ValueError(f"Duplicate completed output: {work_id}")
        completed.add(work_id)
    return completed


HYPHENS = frozenset("-‐‑‒–—−")
SINGLE_QUOTES = frozenset("'‘’‚‛")
DOUBLE_QUOTES = frozenset('"“”„‟')


def normalized_with_map(value: str) -> tuple[str, list[int]]:
    """Return a conservative comparison string and source-character mapping."""
    normalized: list[str] = []
    mapping: list[int] = []
    whitespace = False
    for index, character in enumerate(value):
        if character.isspace():
            if normalized and not whitespace:
                normalized.append(" ")
                mapping.append(index)
            whitespace = True
            continue
        whitespace = False
        if character in HYPHENS:
            character = "-"
        elif character in SINGLE_QUOTES:
            character = "'"
        elif character in DOUBLE_QUOTES:
            character = '"'
        # Avoid multi-codepoint case folding so source offsets remain exact.
        lowered = character.lower()
        if len(lowered) != 1:
            lowered = character
        normalized.append(lowered)
        mapping.append(index)
    if normalized and normalized[-1] == " ":
        normalized.pop()
        mapping.pop()
    return "".join(normalized), mapping


def exact_quote_replacement(quote: str, candidates: list[str]) -> str | None:
    """Repair only whitespace, hyphen, quote-style, or case differences."""
    needle, _ = normalized_with_map(quote.strip())
    if not needle:
        return None
    matches: list[str] = []
    for source in candidates:
        haystack, mapping = normalized_with_map(source)
        start = 0
        while True:
            position = haystack.find(needle, start)
            if position < 0:
                break
            source_start = mapping[position]
            source_end = mapping[position + len(needle) - 1] + 1
            matches.append(source[source_start:source_end])
            start = position + 1
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def repair_exact_quotes(review: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for index, evidence in enumerate(review.get("evidence", [])):
        quote = evidence.get("quote")
        if not isinstance(quote, str) or not quote:
            continue
        candidates = source_texts(packet, evidence)
        if not candidates or any(quote in source for source in candidates):
            continue
        replacement = exact_quote_replacement(quote, candidates)
        if replacement is None or len(replacement.split()) > 25:
            continue
        evidence["quote"] = replacement
        changes.append({
            "type": "exact_quote_normalization",
            "evidence_index": index,
            "before": quote,
            "after": replacement,
        })
    return changes


def repair_sections(review: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Replace a mismatched section only when the block index has one section."""
    changes: list[dict[str, Any]] = []
    blocks = packet.get("input_material", {}).get("evidence_blocks", [])
    for index, evidence in enumerate(review.get("evidence", [])):
        if evidence.get("source_kind") != "fulltext_block":
            continue
        sections = {
            block.get("section")
            for block in blocks
            if block.get("index") == evidence.get("block_index")
        }
        if len(sections) != 1:
            continue
        section = next(iter(sections))
        if evidence.get("section") == section:
            continue
        before = evidence.get("section")
        evidence["section"] = section
        changes.append({
            "type": "section_from_unique_block_index",
            "evidence_index": index,
            "before": before,
            "after": section,
        })
    return changes


def explicit_retrieval_quote(text: str) -> bool:
    normalized = " ".join(text.split())
    if not AF_TERM.search(normalized):
        return False
    database = r"(?:alphafold\s+(?:protein\s+structure\s+)?database|alphafold\s*db|afdb|precomputed)"
    retrieval = r"(?:downloaded|retrieved|accessed|obtained|sourced|taken)"
    return bool(
        re.search(rf"\b{retrieval}\b.{{0,100}}\b(?:from|via)\b.{{0,50}}{database}", normalized, re.I)
        or re.search(rf"\b{database}\b.{{0,80}}\b{retrieval}\b", normalized, re.I)
    )


def linked_quotes(
    review: dict[str, Any], action_link: dict[str, Any]
) -> list[tuple[int, dict[str, Any]]]:
    evidence = review.get("evidence", [])
    result: list[tuple[int, dict[str, Any]]] = []
    for index in action_link.get("evidence_indices", []):
        if isinstance(index, int) and 0 <= index < len(evidence):
            result.append((index, evidence[index]))
    return result


def supported_run_action(action: str, quotes: list[tuple[int, dict[str, Any]]]) -> bool:
    eligible = [
        item.get("quote", "")
        for _, item in quotes
        if item.get("source_kind") != "matched_reference"
    ]
    if action == "ran_colabfold":
        eligible = [quote for quote in eligible if re.search(r"colabfold", quote, re.I)]
    else:
        eligible = [quote for quote in eligible if not re.search(r"colabfold", quote, re.I)]
    return any(
        explicit_run_quote(quote, colabfold_only=action == "ran_colabfold")
        for quote in eligible
    )


def repair_unsupported_run_actions(
    review: dict[str, Any], packet: dict[str, Any]
) -> list[dict[str, Any]]:
    del packet  # The response's exact evidence links are sufficient here.
    actions = list(review.get("observed_actions", []))
    links = list(review.get("action_evidence", []))
    changes: list[dict[str, Any]] = []
    retained_links: list[dict[str, Any]] = []
    retrieval_indices: list[int] = []

    for link in links:
        action = link.get("action")
        quotes = linked_quotes(review, link)
        if action not in {"ran_alphafold", "ran_colabfold"} or supported_run_action(action, quotes):
            retained_links.append(link)
            continue
        if action in actions:
            actions.remove(action)
        evidence_indices = [index for index, _ in quotes]
        quote_texts = [item.get("quote", "") for _, item in quotes]
        if any(explicit_retrieval_quote(quote) for quote in quote_texts):
            retrieval_indices.extend(evidence_indices)
            replacement = "retrieved_precomputed_structure"
        else:
            replacement = None
        changes.append({
            "type": "unsupported_run_action_removed",
            "action": action,
            "replacement": replacement,
            "evidence_indices": evidence_indices,
        })

    if retrieval_indices:
        retrieval_indices = sorted(set(retrieval_indices))
        if "retrieved_precomputed_structure" not in actions:
            actions.append("retrieved_precomputed_structure")
        existing = next(
            (item for item in retained_links if item.get("action") == "retrieved_precomputed_structure"),
            None,
        )
        if existing is None:
            retained_links.append({
                "action": "retrieved_precomputed_structure",
                "evidence_indices": retrieval_indices,
            })
        else:
            existing["evidence_indices"] = sorted(set(existing.get("evidence_indices", [])) | set(retrieval_indices))

    if not changes:
        return []
    review["observed_actions"] = actions
    review["action_evidence"] = retained_links
    review["needs_human_review"] = True
    reasons = list(review.get("human_review_reasons", []))
    if "prediction_origin_unclear" not in reasons:
        reasons.append("prediction_origin_unclear")
    review["human_review_reasons"] = reasons
    return changes


def mark_human_review(review: dict[str, Any], reason: str) -> None:
    review["needs_human_review"] = True
    reasons = list(review.get("human_review_reasons", []))
    if reason not in reasons:
        reasons.append(reason)
    review["human_review_reasons"] = reasons


def repair_unsupported_docking(review: dict[str, Any]) -> list[dict[str, Any]]:
    actions = list(review.get("observed_actions", []))
    if "docking_or_screening" not in actions:
        return []
    links = list(review.get("action_evidence", []))
    docking_link = next(
        (item for item in links if item.get("action") == "docking_or_screening"), None
    )
    if docking_link is None:
        return []
    quotes = [
        item.get("quote", "")
        for _, item in linked_quotes(review, docking_link)
        if item.get("source_kind") != "matched_reference"
    ]
    if substantive_docking_or_screening_quote(" ".join(quotes)):
        return []
    actions.remove("docking_or_screening")
    review["observed_actions"] = actions
    review["action_evidence"] = [
        item for item in links if item.get("action") != "docking_or_screening"
    ]
    mark_human_review(review, "other")
    return [{
        "type": "unsupported_docking_action_removed",
        "action": "docking_or_screening",
        "replacement": (
            "integrated_empirical_workflow"
            if "integrated_empirical_workflow" in actions else None
        ),
        "evidence_indices": list(docking_link.get("evidence_indices", [])),
    }]


def repair_missing_evaluation_action(review: dict[str, Any]) -> list[dict[str, Any]]:
    actions = list(review.get("observed_actions", []))
    if review.get("af_use_label") != "yes" or "benchmarked_or_evaluated" in actions:
        return []
    indices = [
        index
        for index, evidence in enumerate(review.get("evidence", []))
        if evidence.get("source_kind") != "matched_reference"
        and af_evaluation_signal(evidence.get("quote", ""))
    ]
    if not indices:
        return []
    indices = indices[:3]
    actions.append("benchmarked_or_evaluated")
    review["observed_actions"] = actions
    review.setdefault("action_evidence", []).append({
        "action": "benchmarked_or_evaluated",
        "evidence_indices": indices,
    })
    mark_human_review(review, "other")
    return [{
        "type": "explicit_evaluation_action_added",
        "action": "benchmarked_or_evaluated",
        "evidence_indices": indices,
    }]


def repair_missing_origin_flag(review: dict[str, Any]) -> list[dict[str, Any]]:
    if review.get("primary_label") != "model_application":
        return []
    actions = set(review.get("observed_actions", []))
    if actions & {"ran_alphafold", "ran_colabfold", "retrieved_precomputed_structure"}:
        return []
    if "prediction_origin_unclear" in review.get("human_review_reasons", []):
        return []
    mark_human_review(review, "prediction_origin_unclear")
    return [{
        "type": "prediction_origin_unclear_added",
        "core_labels_changed": False,
    }]


def classify_errors(errors: list[str]) -> list[str]:
    categories: set[str] = set()
    for error in errors:
        if "quote is not an exact substring" in error:
            categories.add("non_exact_quote")
        elif "ran_alphafold lacks" in error or "ran_colabfold lacks" in error:
            categories.add("unsupported_run_action")
        elif error.startswith("schema "):
            categories.add("schema")
        elif error.startswith("response parsing"):
            categories.add("response_parsing")
        else:
            categories.add("other_semantic")
    return sorted(categories or {"unknown"})


def attempt_candidate(event: dict[str, Any], line_number: int) -> dict[str, Any]:
    return {
        "attempt_line": line_number,
        "run_id": event.get("run_id"),
        "attempt_number": event.get("attempt_number"),
        "validation_round": event.get("validation_round"),
        "provider": event.get("provider"),
        "model": event.get("model"),
        "input_packet_sha256": event.get("input_packet_sha256"),
        "visible_response_text": event.get("visible_response_text"),
        "visible_response_sha256": event.get("visible_response_sha256"),
        "usage": event.get("usage") or {},
        "normalized_usage": event.get("normalized_usage") or {},
    }


def main() -> int:
    args = parse_args()
    paths = {
        "input": resolved(args.input),
        "schema": resolved(args.schema),
        "existing_output": resolved(args.existing_output),
        "attempts": resolved(args.attempts),
        "output_dir": resolved(args.output_dir),
    }
    if args.max_responses_per_work < 1:
        raise ValueError("--max-responses-per-work must be positive")
    for label in ("input", "schema", "existing_output", "attempts"):
        if not paths[label].is_file():
            raise FileNotFoundError(paths[label])

    order, packets = load_packets(paths["input"])
    completed = load_completed_ids(paths["existing_output"])
    unresolved_ids = set(packets) - completed
    runner = load_runner()
    schema = json.loads(paths["schema"].read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    candidates: dict[str, deque[dict[str, Any]]] = defaultdict(
        lambda: deque(maxlen=args.max_responses_per_work)
    )
    paid_response_events = 0
    for line_number, event in iter_jsonl(paths["attempts"]):
        work_id = event.get("work_id")
        if (
            event.get("event") == "request_finished"
            and event.get("http_status") == 200
            and work_id in unresolved_ids
            and isinstance(event.get("visible_response_text"), str)
            and event["visible_response_text"].strip()
        ):
            paid_response_events += 1
            candidates[work_id].append(attempt_candidate(event, line_number))

    recovered: dict[str, dict[str, Any]] = {}
    audits: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []
    recovery_statuses: Counter[str] = Counter()
    unresolved_categories: Counter[str] = Counter()

    for work_id in order:
        if work_id not in unresolved_ids:
            continue
        packet = packets[work_id]
        packet_hash = fingerprint(packet)
        final_errors: list[str] = ["no paid HTTP 200 response retained"]
        final_candidate: dict[str, Any] | None = None
        parse_failures = 0

        for candidate in reversed(candidates.get(work_id, ())):
            if candidate.get("input_packet_sha256") != packet_hash:
                continue
            final_candidate = candidate
            try:
                original = runner.parse_json_object(candidate["visible_response_text"])
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                parse_failures += 1
                final_errors = [f"response parsing: {exc}"]
                continue

            direct_errors = runner.validate_review(copy.deepcopy(original), packet, validator)
            if not direct_errors:
                response = original
                status = "validator_revalidated"
                changes: list[dict[str, Any]] = []
            else:
                response = copy.deepcopy(original)
                changes = repair_exact_quotes(response, packet)
                changes.extend(repair_sections(response, packet))
                after_quote_errors = runner.validate_review(copy.deepcopy(response), packet, validator)
                if not after_quote_errors:
                    status = "mechanical_evidence_repaired"
                else:
                    changes.extend(repair_unsupported_run_actions(response, packet))
                    changes.extend(repair_unsupported_docking(response))
                    changes.extend(repair_missing_evaluation_action(response))
                    changes.extend(repair_missing_origin_flag(response))
                    repaired_errors = runner.validate_review(copy.deepcopy(response), packet, validator)
                    if repaired_errors:
                        final_errors = repaired_errors
                        continue
                    status = (
                        "retrieval_reclassified"
                        if any(change.get("replacement") == "retrieved_precomputed_structure" for change in changes)
                        else "deterministic_semantic_repair"
                    )

            record = {
                "schema_version": RECOVERY_VERSION,
                "review_id": work_id,
                "work_id": work_id,
                "recovery_status": status,
                "validation_status": "valid",
                "provider": candidate.get("provider"),
                "model": candidate.get("model"),
                "input_packet_sha256": packet_hash,
                "source_attempt": {
                    "attempts_path": str(paths["attempts"]),
                    "attempts_file_sha256": None,
                    "line_number": candidate.get("attempt_line"),
                    "run_id": candidate.get("run_id"),
                    "attempt_number": candidate.get("attempt_number"),
                    "validation_round": candidate.get("validation_round"),
                    "visible_response_sha256": candidate.get("visible_response_sha256"),
                    "usage": candidate.get("usage"),
                    "normalized_usage": candidate.get("normalized_usage"),
                },
                "local_transformations": changes,
                "response": response,
            }
            recovered[work_id] = record
            recovery_statuses[status] += 1
            audits.append({
                "schema_version": RECOVERY_VERSION,
                "review_id": work_id,
                "work_id": work_id,
                "recovery_status": status,
                "source_run_id": candidate.get("run_id"),
                "source_attempt_number": candidate.get("attempt_number"),
                "source_visible_response_sha256": candidate.get("visible_response_sha256"),
                "original_validation_errors": direct_errors,
                "transformations": changes,
                "final_validation_errors": [],
            })
            break

        if work_id in recovered:
            continue
        categories = classify_errors(final_errors)
        for category in categories:
            unresolved_categories[category] += 1
        unresolved_rows.append({
            "review_id": work_id,
            "work_id": work_id,
            "candidate_responses_retained": len(candidates.get(work_id, ())),
            "parse_failures": parse_failures,
            "latest_run_id": final_candidate.get("run_id") if final_candidate else "",
            "latest_attempt_number": final_candidate.get("attempt_number") if final_candidate else "",
            "categories": "|".join(categories),
            "validation_errors": json.dumps(final_errors[:20], ensure_ascii=False),
        })

    attempts_hash = sha256_file(paths["attempts"])
    for record in recovered.values():
        record["source_attempt"]["attempts_file_sha256"] = attempts_hash

    recovered_in_order = [recovered[work_id] for work_id in order if work_id in recovered]
    api_retry_ids = {
        row["work_id"]
        for row in unresolved_rows
        if row["candidate_responses_retained"] == 0
    }
    human_review_ids = {row["work_id"] for row in unresolved_rows} - api_retry_ids
    api_retry_packets = [packets[work_id] for work_id in order if work_id in api_retry_ids]
    human_review_packets = [
        packets[work_id] for work_id in order if work_id in human_review_ids
    ]
    human_review_rows = [
        row for row in unresolved_rows if row["work_id"] in human_review_ids
    ]
    summary = {
        "schema_version": RECOVERY_VERSION,
        "created_at_utc": utc_now(),
        "local_only": True,
        "provider_requests_made": 0,
        "sources": {
            "input": {"path": str(paths["input"]), "sha256": sha256_file(paths["input"])},
            "schema": {"path": str(paths["schema"]), "sha256": sha256_file(paths["schema"])},
            "existing_output": {
                "path": str(paths["existing_output"]),
                "sha256": sha256_file(paths["existing_output"]),
            },
            "attempts": {"path": str(paths["attempts"]), "sha256": attempts_hash},
        },
        "counts": {
            "model_c_packets": len(packets),
            "already_valid": len(completed & set(packets)),
            "unresolved_before": len(unresolved_ids),
            "paid_response_events_considered": paid_response_events,
            "works_with_retained_responses": len(candidates),
            "recovered_locally": len(recovered),
            "unresolved_after": len(unresolved_rows),
            "api_retry_no_paid_response": len(api_retry_packets),
            "human_review_after_paid_response": len(human_review_packets),
        },
        "recovery_statuses": dict(sorted(recovery_statuses.items())),
        "unresolved_categories": dict(sorted(unresolved_categories.items())),
        "policy": {
            "explicit_run_gate": "current fulltext_pipeline.model_review_support.explicit_run_quote",
            "exact_quote_repair": "whitespace/hyphen/quote-style/case normalization only; unique match required",
            "unsupported_run_action": (
                "remove only unsupported ran_alphafold/ran_colabfold; reclassify as retrieval only "
                "with explicit AFDB/precomputed retrieval evidence; otherwise flag prediction_origin_unclear"
            ),
            "core_labels_changed": False,
        },
    }

    print(f"Model C packets:         {len(packets):,}")
    print(f"Already valid:           {len(completed & set(packets)):,}")
    print(f"Unresolved before:       {len(unresolved_ids):,}")
    print(f"Paid responses retained: {paid_response_events:,}")
    print(f"Recovered locally:       {len(recovered):,}")
    print(f"Recovery statuses:       {dict(recovery_statuses)}")
    print(f"Unresolved after:        {len(unresolved_rows):,}")
    print(f"API retry, no response:  {len(api_retry_packets):,}")
    print(f"Human review, responded: {len(human_review_packets):,}")
    print(f"Unresolved categories:   {dict(unresolved_categories)}")
    print("Provider requests made:  0")
    if args.dry_run:
        print("Dry run: no recovery files written")
        return 0

    output_dir = paths["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    recovered_path = output_dir / "model_c_local_recovered_v2.jsonl"
    audit_path = output_dir / "model_c_local_recovery_audit_v2.jsonl"
    unresolved_path = output_dir / "model_c_unresolved_after_local_recovery_v2.csv"
    api_retry_path = output_dir / "model_c_api_retry_inputs_v2.jsonl"
    human_packets_path = output_dir / "model_c_human_review_inputs_v2.jsonl"
    human_worklist_path = output_dir / "model_c_human_review_worklist_v2.csv"
    summary_path = output_dir / "model_c_local_recovery_summary_v2.json"
    write_jsonl(recovered_path, recovered_in_order)
    write_jsonl(audit_path, audits)
    write_csv(unresolved_path, unresolved_rows)
    write_jsonl(api_retry_path, api_retry_packets)
    write_jsonl(human_packets_path, human_review_packets)
    write_csv(human_worklist_path, human_review_rows)
    summary["outputs"] = {
        "recovered": str(recovered_path),
        "audit": str(audit_path),
        "unresolved": str(unresolved_path),
        "api_retry_inputs": str(api_retry_path),
        "human_review_inputs": str(human_packets_path),
        "human_review_worklist": str(human_worklist_path),
        "summary": str(summary_path),
    }
    write_json(summary_path, summary)
    print(f"Recovered output:        {recovered_path}")
    print(f"Recovery audit:          {audit_path}")
    print(f"Unresolved worklist:     {unresolved_path}")
    print(f"API retry inputs:        {api_retry_path}")
    print(f"Human review inputs:     {human_packets_path}")
    print(f"Human review worklist:   {human_worklist_path}")
    print(f"Summary:                 {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
