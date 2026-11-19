"""One user-run command: reconstruct, export and verify the independent overlay."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import fcntl
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from action_layer_v1 import (ACCEPTANCE, MODULE, OUTPUT, base, fingerprint, reconstruct,
                             validation_document, verify_export)


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_rows(path, rows):
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")


def source_inventory(approval_manifest):
    result = dict(approval_manifest["source_pins"])
    for path in (ACCEPTANCE / "acceptance_manifest.json", ACCEPTANCE / "acceptance_manifest.json.sha256"):
        result[str(path)] = fingerprint(path)
    for name, pin in approval_manifest["outputs"].items():
        result[str(ACCEPTANCE / name)] = {k: v for k, v in pin.items() if k in ("sha256", "size_bytes")}
    return result


def publish():
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise FileExistsError("Action layer exists; use verify_action_layer_v1.py, never overwrite")
    reconstructed = reconstruct()
    rows, deltas, missing, quarantine, summary, approval_manifest = reconstructed
    sources = source_inventory(approval_manifest)
    stage = Path(tempfile.mkdtemp(prefix=".action-layer-v1-incomplete-", dir=MODULE))
    print("Staging (retained on failure): " + str(stage))
    for name, content in (("action_layer3755.jsonl", rows), ("accepted_delta_refs185.jsonl", deltas),
                          ("missing_response9.jsonl", missing), ("quarantine1.jsonl", quarantine)):
        write_rows(stage / name, content)
    write_json(stage / "layer_summary.json", summary)
    write_json(stage / "validation_report.json", validation_document())
    with (stage / "README_zh.md").open("xb") as stream:
        stream.write((ACCEPTANCE / "README_zh.md").read_bytes())
    outputs = {}
    for path in sorted(stage.iterdir()):
        pin = fingerprint(path)
        if path.suffix == ".jsonl":
            pin["rows"] = len(base.read_rows(path))
        outputs[path.name] = pin
    manifest = {"schema_version": "nhb-action-layer-manifest-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_pins": sources, "outputs": outputs,
        "user_approval_recorded": True, "provider_requests": 0, "core_labels_changed": False,
        "original_final_database_modified": False, "independent_human_gold_standard": False,
        "formal_models_ready": False, "freeze_basis": "explicit_user_policy_and_named_action_acceptance_then_export_reconstruction",
        "unit": "original_work_not_merged_study", "queue_size": 3755}
    write_json(stage / "layer_manifest.json", manifest)
    with (stage / "layer_manifest.json.sha256").open("x", encoding="ascii") as stream:
        stream.write(base.digest(stage / "layer_manifest.json") + "  layer_manifest.json\n")
    verify_export(stage, reconstructed)
    # mkdir is exclusive: no overwrite even if another process creates the target.
    OUTPUT.mkdir(exist_ok=False)
    for path in stage.iterdir():
        path.rename(OUTPUT / path.name)
    stage.rmdir()  # Only our now-empty staging directory; no recursive removal.
    print("Independent action layer exported + verified: PASS; works: 3755; decisions: 33714")
    print("Accepted deltas: 185 / 99 works; protected keys: 83; uncertain works: 1408")
    print("No-response works: 9 separate; attribution quarantine: 1; original API-valid: 3198 unchanged")
    print("Frozen overlay: " + str(OUTPUT))
    print("Original final/core unchanged; no API. Next: verify_action_layer_v1.py; then downstream activity preparation.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local-only independent action overlay; combined export + verification")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        _, _, _, _, summary, _ = reconstruct()
        print("Dry run: approved sources and all 3755 works reconstructed; no files or requests")
        print("Decisions: 33714; approved deltas: 185; protected keys: 83; unknown works: " + str(summary["uncertain_work_records"]))
        return 0
    lock_path = MODULE / ".action-layer-v1.writer.lock"
    with lock_path.open("a", encoding="ascii") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another action-layer writer is active; do not run duplicate writers") from exc
        try:
            return publish()
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    raise SystemExit(main())
