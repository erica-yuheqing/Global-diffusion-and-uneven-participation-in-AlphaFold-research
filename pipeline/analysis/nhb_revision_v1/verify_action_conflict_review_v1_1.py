"""Versioned fix: rows:null is absent count metadata, NOT a JSONL instruction.

Preserves the pinned v1 verifier, proposals, source files and manifests unchanged.
Replaces only its row-count metadata check; all v1 scientific checks still run.
No API/key access, publication, merge, semantic approval, or data writeback.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import verify_action_conflict_review_v1 as original

FIX = original.MODULE / "action_conflict_verifier_fix_v1"


def check_pin(path, pin):
    path = original.safe(path)
    original.require(path.stat().st_size == pin["size_bytes"] and
                     original.digest(path) == pin["sha256"],
                     "Source/output changed: " + str(path))
    count = pin.get("rows")
    if count is None:
        return
    original.require(type(count) is int and count >= 0 and path.suffix == ".jsonl",
                     "Integer rows metadata requires a JSONL file: " + str(path))
    original.require(len(original.read_rows(path)) == count,
                     "JSONL row count differs: " + str(path))


def verify_fix_archive():
    manifest_path = FIX / "fix_manifest.json"
    manifest = original.read_json(manifest_path)
    with original.safe(FIX / "fix_manifest.json.sha256").open(encoding="utf-8") as stream:
        checksum = stream.read().strip().split()
    original.require(checksum == [original.digest(manifest_path), "fix_manifest.json"],
                     "Fix manifest checksum differs")
    original.require(manifest["schema_version"] == "nhb-action-conflict-verifier-fix-v1" and
                     manifest["provider_requests"] == 0 and
                     manifest["scientific_records_changed"] is False and
                     manifest["original_manifests_changed"] is False and
                     manifest["automatic_merge"] is False and
                     manifest["semantic_approval"] is False,
                     "Verifier fix scope differs")
    required = {str(original.MODULE / "verify_action_conflict_review_v1_1.py"),
                str(original.MODULE / "verify_action_conflict_review_v1.py"),
                str(original.MODULE / "test_action_conflict_verifier_fix_v1.py"),
                str(original.BUNDLE / "review_manifest.json"),
                str(original.BUNDLE / "review_manifest.sha256"),
                str(original.UPSTREAM / "acceptance_manifest.json")}
    original.require(required <= set(manifest["source_pins"]), "Incomplete fix source/code pins")
    for path, pin in manifest["source_pins"].items():
        check_pin(path, pin)
    for name, pin in manifest["outputs"].items():
        check_pin(FIX / name, pin)


def main():
    verify_fix_archive()
    # The original module's __file__ still points to its unchanged, pinned v1 code.
    # Its main runs unchanged; only rows=None handling is replaced by this fix.
    original.check_pin = check_pin
    print("Verifier fix v1.1: null row metadata handled; original v1 archives unchanged")
    return original.main()


if __name__ == "__main__":
    raise SystemExit(main())
