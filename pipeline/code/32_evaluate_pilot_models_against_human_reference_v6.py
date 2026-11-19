#!/usr/bin/env python3
"""Evaluate Pilot model outputs against the frozen v6 human reference set.

The primary metrics use only human-reference records marked metric_eligible.
Uncertain human records remain visible in coverage counts but are never silently
treated as negative examples. No model API calls are made.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_ROOT.parent
REPORT_SCHEMA_VERSION = "af-pilot-human-model-evaluation-v1"

DEFAULTS = {
    "human_reference": "fulltext/pilot/human_annotation_v6/final/pilot_150_human_reference_v6.jsonl",
    "human_report": "fulltext/pilot/human_annotation_v6/final/pilot_150_human_reference_report_v6.json",
    "model_a": "fulltext/pilot/adjudication_v6/model_a_canonical_150_v6.jsonl",
    "model_b": "fulltext/pilot/adjudication_v6/model_b_canonical_150_v6.jsonl",
    "model_c": "fulltext/pilot/ensemble_v6/model_c_canonical_68_v6.jsonl",
    "ensemble": "fulltext/pilot/ensemble_v6/pilot_150_machine_consensus_v6.jsonl",
    "output_dir": "fulltext/pilot/human_annotation_v6/evaluation",
}

CORE_FIELDS = [
    "primary_label",
    "relevance_level",
    "evidence_level",
    "af_related_label",
    "af_use_label",
    "adoption_eligible",
    "future_or_hypothetical_only",
]
ALL_FIELDS = [*CORE_FIELDS, "observed_actions"]


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_finalizer_module() -> Any:
    path = CODE_ROOT / "31_finalize_pilot_human_reference_v6.py"
    spec = importlib.util.spec_from_file_location("pilot_human_reference_v6", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load finalizer module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            rows.append(value)
    return rows


def unique(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        review_id = str(row.get("review_id") or "").strip()
        if not review_id:
            raise ValueError(f"{label}: record without review_id")
        if review_id in result:
            raise ValueError(f"{label}: duplicate review_id {review_id}")
        result[review_id] = row
    return result


def normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).strip()


def normalize_actions(value: Any, support: Any) -> str:
    if isinstance(value, list):
        value = "|".join(str(item) for item in value)
    return "|".join(support.split_actions(value))


def normalize_response(response: dict[str, Any], support: Any) -> dict[str, str]:
    result = {field: normalize_scalar(response.get(field)) for field in CORE_FIELDS}
    result["observed_actions"] = normalize_actions(response.get("observed_actions"), support)
    return result


def model_predictions(path: Path, support: Any) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    rows = read_jsonl(path)
    by_id = unique(rows, path.name)
    predictions: dict[str, dict[str, str]] = {}
    providers: Counter[str] = Counter()
    models: Counter[str] = Counter()
    for review_id, row in by_id.items():
        response = row.get("response")
        if not isinstance(response, dict):
            raise ValueError(f"{path.name}: missing response for {review_id}")
        predictions[review_id] = normalize_response(response, support)
        providers[normalize_scalar(row.get("provider"))] += 1
        models[normalize_scalar(row.get("model"))] += 1
    metadata = {
        "records": len(rows),
        "providers": dict(providers),
        "models": dict(models),
    }
    return predictions, metadata


def ensemble_predictions(path: Path, support: Any) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    rows = read_jsonl(path)
    by_id = unique(rows, path.name)
    predictions: dict[str, dict[str, str]] = {}
    status_counts: Counter[str] = Counter()
    for review_id, row in by_id.items():
        core_vote = row.get("core_vote") or {}
        action_vote = row.get("action_vote") or {}
        core = core_vote.get("value") or {}
        prediction = {field: normalize_scalar(core.get(field)) for field in CORE_FIELDS}
        prediction["observed_actions"] = normalize_actions(action_vote.get("value") or [], support)
        predictions[review_id] = prediction
        status_counts[normalize_scalar(row.get("machine_status"))] += 1
    return predictions, {"records": len(rows), "machine_status_counts": dict(status_counts)}


def human_values(record: dict[str, Any], support: Any) -> dict[str, str]:
    result = {
        field: normalize_scalar(record.get(f"reference_{field}")) for field in CORE_FIELDS
    }
    result["observed_actions"] = normalize_actions(
        record.get("reference_observed_actions"), support
    )
    return result


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    observed = sum(human == predicted for human, predicted in pairs) / len(pairs)
    human_counts = Counter(human for human, _ in pairs)
    predicted_counts = Counter(predicted for _, predicted in pairs)
    categories = set(human_counts) | set(predicted_counts)
    expected = sum(
        human_counts[value] / len(pairs) * predicted_counts[value] / len(pairs)
        for value in categories
    )
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1.0 - expected)


def categorical_metrics(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    if not pairs:
        return {"n": 0, "exact_matches": 0, "accuracy": None, "cohen_kappa": None, "macro_f1": None, "confusion": {}}
    categories = sorted({value for pair in pairs for value in pair})
    confusion: dict[str, dict[str, int]] = {
        human: {predicted: 0 for predicted in categories} for human in categories
    }
    for human, predicted in pairs:
        confusion[human][predicted] += 1
    f1_values: list[float] = []
    for category in categories:
        tp = confusion[category][category]
        fp = sum(confusion[other][category] for other in categories if other != category)
        fn = sum(confusion[category][other] for other in categories if other != category)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1_values.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    matches = sum(human == predicted for human, predicted in pairs)
    return {
        "n": len(pairs),
        "exact_matches": matches,
        "accuracy": matches / len(pairs),
        "cohen_kappa": cohen_kappa(pairs),
        "macro_f1": sum(f1_values) / len(f1_values),
        "confusion": confusion,
    }


def positive_class_metrics(pairs: list[tuple[str, str]], positive: str = "yes") -> dict[str, Any]:
    if not pairs:
        return {"n": 0, "positive": positive, "tp": 0, "fp": 0, "fn": 0, "strict_tn": 0, "precision": None, "recall": None, "f1": None, "strict_specificity": None, "exact_accuracy": None}
    tp = sum(h == positive and p == positive for h, p in pairs)
    fp = sum(h != positive and p == positive for h, p in pairs)
    fn = sum(h == positive and p != positive for h, p in pairs)
    strict_tn = sum(h == "no" and p == "no" for h, p in pairs)
    human_negative = sum(h == "no" for h, _ in pairs)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "n": len(pairs),
        "positive": positive,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "strict_tn": strict_tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "strict_specificity": strict_tn / human_negative if human_negative else None,
        "exact_accuracy": sum(h == p for h, p in pairs) / len(pairs),
    }


def action_jaccard(human: str, predicted: str) -> float:
    human_set = set(item for item in human.split("|") if item)
    predicted_set = set(item for item in predicted.split("|") if item)
    union = human_set | predicted_set
    return len(human_set & predicted_set) / len(union) if union else 1.0


def simple_metrics(
    records: list[dict[str, Any]], predictions: dict[str, dict[str, str]], support: Any
) -> dict[str, Any]:
    pairs: list[tuple[dict[str, str], dict[str, str]]] = []
    for record in records:
        prediction = predictions.get(record["review_id"])
        if prediction is not None:
            pairs.append((human_values(record, support), prediction))
    if not pairs:
        return {"n": 0, "core_exact_accuracy": None, "primary_label_accuracy": None, "af_use_accuracy": None, "adoption_accuracy": None, "actions_exact_accuracy": None}
    return {
        "n": len(pairs),
        "core_exact_accuracy": sum(all(h[f] == p[f] for f in CORE_FIELDS) for h, p in pairs) / len(pairs),
        "primary_label_accuracy": sum(h["primary_label"] == p["primary_label"] for h, p in pairs) / len(pairs),
        "af_use_accuracy": sum(h["af_use_label"] == p["af_use_label"] for h, p in pairs) / len(pairs),
        "adoption_accuracy": sum(h["adoption_eligible"] == p["adoption_eligible"] for h, p in pairs) / len(pairs),
        "actions_exact_accuracy": sum(h["observed_actions"] == p["observed_actions"] for h, p in pairs) / len(pairs),
    }


def system_metrics(
    human_records: list[dict[str, Any]],
    predictions: dict[str, dict[str, str]],
    support: Any,
) -> dict[str, Any]:
    eligible = [record for record in human_records if record.get("metric_eligible") is True]
    evaluated = [record for record in eligible if record["review_id"] in predictions]
    fields: dict[str, Any] = {}
    for field in CORE_FIELDS:
        pairs = [
            (human_values(record, support)[field], predictions[record["review_id"]][field])
            for record in evaluated
        ]
        fields[field] = categorical_metrics(pairs)

    core_exact = [
        all(
            human_values(record, support)[field] == predictions[record["review_id"]][field]
            for field in CORE_FIELDS
        )
        for record in evaluated
    ]
    action_pairs = [
        (
            human_values(record, support)["observed_actions"],
            predictions[record["review_id"]]["observed_actions"],
        )
        for record in evaluated
    ]
    stratified: dict[str, Any] = {}
    stratum_functions = {
        "reference_route": lambda record: record["reference_route"],
        "reference_evidence_level": lambda record: record["reference_evidence_level"],
        "retrieval_sampling_stratum": lambda record: record["sampling"]["retrieval_sampling_stratum"],
    }
    for stratum_name, getter in stratum_functions.items():
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in evaluated:
            groups[str(getter(record))].append(record)
        stratified[stratum_name] = {
            key: simple_metrics(rows, predictions, support) for key, rows in sorted(groups.items())
        }
    return {
        "human_metric_eligible": len(eligible),
        "prediction_records": len(predictions),
        "evaluated_records": len(evaluated),
        "missing_predictions_for_eligible": len(eligible) - len(evaluated),
        "core_tuple_exact_matches": sum(core_exact),
        "core_tuple_exact_accuracy": sum(core_exact) / len(core_exact) if core_exact else None,
        "field_metrics": fields,
        "af_use_positive_metrics": positive_class_metrics(
            [
                (human_values(record, support)["af_use_label"], predictions[record["review_id"]]["af_use_label"])
                for record in evaluated
            ]
        ),
        "adoption_positive_metrics": positive_class_metrics(
            [
                (human_values(record, support)["adoption_eligible"], predictions[record["review_id"]]["adoption_eligible"])
                for record in evaluated
            ]
        ),
        "observed_actions": {
            "n": len(action_pairs),
            "exact_matches": sum(human == predicted for human, predicted in action_pairs),
            "exact_accuracy": sum(human == predicted for human, predicted in action_pairs) / len(action_pairs) if action_pairs else None,
            "mean_jaccard": sum(action_jaccard(human, predicted) for human, predicted in action_pairs) / len(action_pairs) if action_pairs else None,
        },
        "stratified": stratified,
    }


def flatten_comparisons(
    human_records: list[dict[str, Any]],
    systems: dict[str, dict[str, dict[str, str]]],
    support: Any,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for human in human_records:
        truth = human_values(human, support)
        row: dict[str, Any] = {
            "pilot_order": human["pilot_order"],
            "review_id": human["review_id"],
            "work_id": human["work_id"],
            "reference_route": human["reference_route"],
            "reference_status": human["reference_status"],
            "metric_eligible": human["metric_eligible"],
            "human_evidence_valid": human["human_evidence_valid"],
            **{f"human_{field}": truth[field] for field in ALL_FIELDS},
        }
        for system_name, predictions in systems.items():
            prediction = predictions.get(human["review_id"])
            prefix = system_name.lower()
            row[f"{prefix}_available"] = prediction is not None
            for field in ALL_FIELDS:
                row[f"{prefix}_{field}"] = prediction[field] if prediction else ""
            row[f"{prefix}_core_exact"] = (
                all(truth[field] == prediction[field] for field in CORE_FIELDS)
                if prediction and human["metric_eligible"]
                else ""
            )
            row[f"{prefix}_actions_exact"] = (
                truth["observed_actions"] == prediction["observed_actions"]
                if prediction and human["metric_eligible"]
                else ""
            )
        rows.append(row)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), type=Path, default=Path(default))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = {name: resolve(getattr(args, name)) for name in DEFAULTS if name != "output_dir"}
    output_dir = resolve(args.output_dir)
    for name, path in paths.items():
        if not path.is_file():
            raise ValueError(f"Missing {name}: {path}")

    support = load_finalizer_module()
    human_records = read_jsonl(paths["human_reference"])
    if len(human_records) != 150:
        raise ValueError(f"Expected 150 human-reference records, found {len(human_records)}")
    unique(human_records, "human reference")
    human_report = json.loads(paths["human_report"].read_text(encoding="utf-8"))
    expected_human_sha = human_report.get("outputs", {}).get("reference_jsonl", {}).get("sha256")
    actual_human_sha = sha256_file(paths["human_reference"])
    if expected_human_sha != actual_human_sha:
        raise ValueError("Human-reference JSONL hash does not match its audit report")

    predictions_a, metadata_a = model_predictions(paths["model_a"], support)
    predictions_b, metadata_b = model_predictions(paths["model_b"], support)
    predictions_c, metadata_c = model_predictions(paths["model_c"], support)
    predictions_ensemble, metadata_ensemble = ensemble_predictions(paths["ensemble"], support)
    systems = {
        "A": predictions_a,
        "B": predictions_b,
        "C": predictions_c,
        "ensemble": predictions_ensemble,
    }
    metrics = {
        name: system_metrics(human_records, predictions, support)
        for name, predictions in systems.items()
    }
    eligible_count = sum(record.get("metric_eligible") is True for record in human_records)
    print(f"Human reference records: {len(human_records)}")
    print(f"Primary metric records:  {eligible_count}")
    for name in ("A", "B", "C", "ensemble"):
        result = metrics[name]
        print(
            f"{name:8s} evaluated={result['evaluated_records']:3d} "
            f"core_exact={result['core_tuple_exact_accuracy']:.3f} "
            f"adoption={result['field_metrics']['adoption_eligible']['accuracy']:.3f} "
            f"actions={result['observed_actions']['exact_accuracy']:.3f}"
        )
    if args.dry_run:
        print("Dry run: no evaluation outputs were written.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "pilot_150_models_vs_human_report_v6.json"
    comparison_path = output_dir / "pilot_150_models_vs_human_records_v6.csv"
    if not args.force and (report_path.exists() or comparison_path.exists()):
        raise FileExistsError("Evaluation output exists; pass --force to replace it")

    comparison_rows = flatten_comparisons(human_records, systems, support)
    comparison_sha = support.write_csv(
        comparison_path, comparison_rows, list(comparison_rows[0])
    )
    evaluator_path = Path(__file__).resolve()
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": (
            "Primary performance metrics exclude human references that remain uncertain or lack "
            "valid supporting evidence. Model C metrics use only its prespecified 68-record scope."
        ),
        "human_reference": {
            "records": len(human_records),
            "metric_eligible": eligible_count,
            "status_counts": dict(Counter(record["reference_status"] for record in human_records)),
        },
        "systems": {
            "A": metadata_a,
            "B": metadata_b,
            "C": metadata_c,
            "ensemble": metadata_ensemble,
        },
        "metrics": metrics,
        "inputs": {
            name: {"path": relative(path), "sha256": sha256_file(path)}
            for name, path in paths.items()
        },
        "implementation": {
            "evaluator": {"path": relative(evaluator_path), "sha256": sha256_file(evaluator_path)},
            "human_reference_finalizer": {
                "path": relative(CODE_ROOT / "31_finalize_pilot_human_reference_v6.py"),
                "sha256": sha256_file(CODE_ROOT / "31_finalize_pilot_human_reference_v6.py"),
            },
        },
        "outputs": {
            "per_record_comparison": {
                "path": relative(comparison_path),
                "sha256": comparison_sha,
                "records": len(comparison_rows),
            }
        },
    }
    report_sha = support.write_json(report_path, report)
    print(f"Per-record comparison:  {comparison_path}")
    print(f"Evaluation report:      {report_path}")
    print(f"Report SHA-256:         {report_sha}")
    print("No model requests were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
