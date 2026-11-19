"""Read-only integrity/source checks for scoped proposals; NEVER semantic approval.

No provider, API key, file publication, state writeback, merge, or analysis freeze.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import hashlib
import json
from collections import Counter
from pathlib import Path

MODULE = Path(__file__).resolve().parent
ROOT = MODULE.parents[1]
BUNDLE = MODULE / "action_conflict_review_v1"
UPSTREAM = MODULE / "action_assisted_acceptance_v1"
INPUT = MODULE / "action_review_preparation_v1/action_review_inputs_blinded_v1.jsonl"
PROMPT = MODULE / "action_review_prompt_full_v1.txt"
OUTPUTS = {"discussion_conflict_proposals96.jsonl", "priority_source_reviews15.jsonl",
           "source_flag_triage244.jsonl", "review_summary.json",
           "finalization_policy_proposal.json", "README_zh.md", "scoped_changes_review_zh.md"}
ACTIONS = {"retrieved_precomputed_structure", "ran_alphafold", "ran_colabfold",
           "integrated_empirical_workflow", "docking_or_screening", "benchmarked_or_evaluated",
           "modified_or_extended", "developed_downstream_tool", "discussion_only"}
STATES = {"supported", "not_established", "uncertain"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            path.resolve().is_relative_to(ROOT), "Not a regular project file: " + str(path))
    return path


def digest(path):
    h = hashlib.sha256()
    with safe(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    with safe(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def read_rows(path, maximum=8000):
    result = []
    with safe(path).open(encoding="utf-8") as stream:
        for line in stream:
            require(bool(line.strip()), "Blank JSONL line: " + str(path))
            result.append(json.loads(line))
            require(len(result) <= maximum, "Exceeded bounded row count: " + str(path))
    return result


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def check_pin(path, pin):
    path = safe(path)
    require(path.stat().st_size == pin["size_bytes"] and digest(path) == pin["sha256"],
            "Source/output changed: " + str(path))
    if "rows" in pin:
        require(len(read_rows(path)) == pin["rows"], "JSONL row count differs: " + str(path))


def main():
    manifest = read_json(BUNDLE / "review_manifest.json")
    with safe(BUNDLE / "review_manifest.sha256").open(encoding="utf-8") as stream:
        checksum = stream.read().strip().split()
    require(checksum == [digest(BUNDLE / "review_manifest.json"), "review_manifest.json"],
            "Review manifest checksum differs")
    require(manifest["schema_version"] == "nhb-action-conflict-review-manifest-v1" and
            manifest["confirmation_status"] == "pending_user_confirmation" and
            manifest["provider_requests"] == 0, "Manifest scope differs")
    for key in ("core_labels_changed", "automatic_merge", "analysis_freeze_ready",
                "whole_work_semantic_approval", "independent_human_gold_standard"):
        require(manifest[key] is False, "Authority must not be broadened: " + key)
    require(set(manifest["outputs"]) == OUTPUTS, "Output inventory differs")
    required_sources = {str(INPUT), str(PROMPT), str(Path(__file__).resolve()),
                        str(UPSTREAM / "acceptance_manifest.json"),
                        str(UPSTREAM / "work_routing3755.json"),
                        str(UPSTREAM / "discussion_core_conflicts96.jsonl")}
    require(required_sources <= set(manifest["source_pins"]), "Incomplete source/code inventory")
    for path, pin in manifest["source_pins"].items():
        check_pin(path, pin)
    for name, pin in manifest["outputs"].items():
        check_pin(BUNDLE / name, pin)

    # Retain the previous acceptance scope, and check all its source/output pins.
    old_manifest = read_json(UPSTREAM / "acceptance_manifest.json")
    for path, pin in old_manifest["source_pins"].items():
        check_pin(path, pin)
    for name, pin in old_manifest["outputs"].items():
        check_pin(UPSTREAM / name, pin)
    approval = read_json(UPSTREAM / "user_confirmation.json")
    require(approval["user_message_verbatim"] == "确认" and
            approval["global_model_semantic_acceptance"] is False and
            approval["core_labels_changed"] is False, "Previous authority differs")

    packets = read_rows(INPUT, 3755)
    packet_map = {p["work_id"]: (line, p) for line, p in enumerate(packets, 1)}
    routing = read_json(UPSTREAM / "work_routing3755.json")
    require(len(packets) == len(packet_map) == len(routing["rows"]) == 3755,
            "Queue size/uniqueness differs")
    require([p["work_id"] for p in packets] == [r[0] for r in routing["rows"]],
            "Queue order differs")
    records_cache, source_refs, prior_states, protected, flags = {}, {}, {}, {}, {}
    for r in routing["rows"]:
        wid, file = r[0], routing["source_files"][r[1]]
        require(file in manifest["source_pins"], "Unpinned routed source")
        if file not in records_cache:
            records_cache[file] = read_rows(file)
        record = records_cache[file][r[2] - 1]
        response = record.get("response")
        require(record["work_id"] == wid and canonical(record) == r[3] and
                (canonical(response) if response else None) == r[4], "Routed source differs: " + wid)
        state = {d["action"]: d["state"] for d in response["action_decisions"]} if response else None
        if state is not None:
            require(set(state) == ACTIONS and set(state.values()) <= STATES, "Invalid action states")
            state.update({d["action"]: d["accepted_state"] for d in r[9]})
        source_refs[wid] = (file, r[2], r[3], r[4])
        prior_states[wid], protected[wid] = state, r[9]
        flags[wid] = response["review_flags"] if response else []
    require(sum(r[7] for r in routing["rows"]) == 3198 and
            sum(len(x) for x in protected.values()) == 83, "API credit/protected keys differ")
    missing = [wid for wid, state in prior_states.items() if state is None]
    require(len(missing) == 9, "Missing-response membership differs")
    conflict_cards = read_rows(UPSTREAM / "discussion_core_conflicts96.jsonl", 96)
    conflicts = read_rows(BUNDLE / "discussion_conflict_proposals96.jsonl", 96)
    priority = read_rows(BUNDLE / "priority_source_reviews15.jsonl", 15)
    triage = read_rows(BUNDLE / "source_flag_triage244.jsonl", 244)
    require(len(conflicts) == 96 and len(priority) == 15 and len(triage) == 244,
            "Proposal/worklist counts differ")
    require([p["work_id"] for p in conflicts] == [p["work_id"] for p in conflict_cards],
            "96-work membership/order differs")
    proposal_ids = [p["work_id"] for p in conflicts + priority]
    require(len(set(proposal_ids)) == 111, "Duplicate/overlapping proposal work")
    proposed_states = {wid: (dict(state) if state else None) for wid, state in prior_states.items()}
    for p in conflicts + priority:
        wid = p["work_id"]
        packet_line, packet = packet_map[wid]
        require((p["source_file"], p["source_line"], p["source_record_sha256"],
                 p["source_response_sha256"]) == source_refs[wid], "Proposal source differs: " + wid)
        require(p["schema_version"] == "nhb-action-conflict-scoped-proposal-v1" and
                p["packet_file"] == str(INPUT) and p["packet_line"] == packet_line and
                p["input_packet_sha256"] == canonical(packet) and
                p["title"] == packet["input_material"].get("title"), "Proposal packet differs: " + wid)
        require(p["protected_action_keys"] == protected[wid] and
                p["original_review_flags"] == flags[wid], "Protected keys/flags differ")
        require(p["confirmation_status"] == "pending_user_confirmation", "Unapproved proposal")
        for key in ("whole_work_semantic_approval", "independent_human_gold_standard",
                    "core_labels_changed", "automatic_merge", "api_success_credit", "resume_credit"):
            require(p[key] is False, "Proposal scope broadened: " + key)
        blocks = {b["index"]: b for b in packet["input_material"].get("evidence_blocks", [])}
        indices = p["reviewed_block_indices"]
        require(len(indices) == len(set(indices)) and all(type(i) is int and i in blocks for i in indices),
                "Reviewed-block scope differs")
        for e in p["evidence"]:
            block = blocks.get(e["block_index"])
            require(block and e["block_index"] in indices and e["source_kind"] == "fulltext_block" and
                    e["section"] == block["section"] and isinstance(e["quote"], str) and
                    bool(e["quote"].strip()) and len(e["quote"].split()) <= 25 and
                    e["quote"] in block["text"], "Invalid literal quote/location: " + wid)
        action_names = [d["action"] for d in p["changes"]]
        require(len(action_names) == len(set(action_names)), "Duplicate action delta")
        for d in p["changes"]:
            action, after = d["action"], d["proposed_state"]
            require(action in ACTIONS and after in STATES and
                    d["before"] == prior_states[wid][action] and d["before"] != after,
                    "Delta before/after differs: " + wid)
            require(action not in {x["action"] for x in protected[wid]}, "Protected action changed")
            refs = d["evidence_indices"]
            require(bool(refs) and len(refs) == len(set(refs)) and all(
                    type(i) is int and 0 <= i < len(p["evidence"]) for i in refs), "Invalid delta evidence")
            require(not (action in {"ran_alphafold", "ran_colabfold"} and after == "supported"),
                    "Unapproved new execution claim")
            proposed_states[wid][action] = after
    for p in conflicts:
        require(prior_states[p["work_id"]]["discussion_only"] == "supported" and
                proposed_states[p["work_id"]]["discussion_only"] != "supported", "Conflict proposal incomplete")

    flagged_ids = [r[0] for r in routing["rows"] if
                   routing["routes"][r[6]] == "P3_source_flags_triage_pending"]
    require([p["work_id"] for p in triage] == flagged_ids, "244-work warning routing differs")
    priority_ids = {p["work_id"] for p in priority}
    require(priority_ids == {wid for wid in flagged_ids if
            {"core_label_conflict", "conflicting_evidence"} & set(flags[wid])}, "Priority routing differs")
    priority_map = {p["work_id"]: p for p in priority}
    carry_scopes = {"protected_decision_carry_only", "protected_supersession_metadata"}
    for row in triage:
        wid = row["work_id"]
        require(row["states"] == prior_states[wid] and row["flags"] == flags[wid] and
                row["protected"] == protected[wid] and
                (row["source_file"], row["source_line"], row["source_record_sha256"],
                 row["source_response_sha256"]) == source_refs[wid], "Warning source/state differs")
        require(row["flags_removed"] is False and row["whole_work_semantic_approval"] is False and
                row["confirmation_status"] == "pending_user_confirmation", "Warning scope broadened")
        evidence_review = wid in priority_ids and priority_map[wid]["review_scope"] not in carry_scopes
        require(row["semantic_review_completed"] == evidence_review and row["triage_kind"] ==
                ("attribution_priority_review" if wid in priority_ids else
                 "historical_flag_retention_metadata_only"), "Warning review scope differs")

    expected = dict(schema_version="nhb-action-conflict-review-summary-v1", queue_size=3755,
        original_api_valid_unchanged=3198, structurally_valid_candidate_coverage_unchanged=3746,
        no_parsed_response=9, protected_action_keys_preserved=83, conflict_proposal_works=96,
        conflict_disposition_counts=dict(Counter(p["disposition"] for p in conflicts)),
        conflict_action_delta_count=sum(len(p["changes"]) for p in conflicts), source_flag_triage_works=244,
        priority_changed_works=sum(bool(p["changes"]) for p in priority),
        priority_action_delta_count=sum(len(p["changes"]) for p in priority),
        input_attribution_quarantine_works=[p["work_id"] for p in priority if p["input_attribution_quarantine"]],
        unknown_works_before_proposals=sum("uncertain" in (s or {}).values() for s in prior_states.values()),
        unknown_works_if_scoped_proposals_accepted=sum("uncertain" in (s or {}).values() for s in proposed_states.values()),
        active_discussion_core_conflicts_before=96,
        active_discussion_core_conflicts_if_scoped_proposals_accepted=sum(
            s is not None and s["discussion_only"] == "supported" for s in proposed_states.values()),
        historical_source_flags_removed=0, new_supported_AF_or_ColabFold_execution_claims=0,
        confirmation_status="pending_user_confirmation", provider_requests=0, core_labels_changed=False,
        automatic_merge=False, analysis_freeze_ready=False, independent_human_gold_standard=False,
        whole_work_semantic_approval=False, priority_flagged_works=15, priority_evidence_reviews=10,
        priority_protected_or_metadata_carries=5)
    require(read_json(BUNDLE / "review_summary.json") == expected, "Summary reconstruction differs")
    require(expected["conflict_disposition_counts"] ==
            {"specific_use_supported": 48, "boundary_unknown": 46, "protected_unknown": 2} and
            expected["conflict_action_delta_count"] == 179 and expected["priority_action_delta_count"] == 6,
            "Named review scope differs")
    policy = read_json(BUNDLE / "finalization_policy_proposal.json")
    require(policy["schema_version"] == "nhb-action-finalization-policy-proposal-v1" and
            policy["confirmation_status"] == "pending_user_confirmation" and
            policy["accepted"] is False and policy["provider_requests"] == 0 and
            policy["request_new_paid_calls"] is False and
            policy["protected_action_keys"] == 83 and policy["missing_response_work_ids"] == missing and
            policy["input_attribution_quarantine_work_ids"] == ["W4411273906"] and
            expected["input_attribution_quarantine_works"] == ["W4411273906"], "Policy/disposition differs")
    for key in ("whole_work_semantic_approval", "independent_human_gold_standard", "automatic_merge",
                "analysis_freeze_ready", "core_labels_changed"):
        require(policy[key] is False, "Policy scope broadened")
    require(policy["uncertain_policy"] == "retain_uncertain_per_action_never_convert_to_not_established_or_supported_by_core_labels" and
            policy["missing_response_policy"] == "retain_not_assessed_no_parsed_response_do_not_generate_nine_negative_decisions",
            "Unknown/missing cannot become negative decisions")
    print("Scoped review archive: PASS; conflict proposals: 96; warnings retained: 244")
    print("Named pending deltas: 185 / 99 works; protected action keys: 83 unchanged")
    print("Proposed: 48 specific-use cases + 48 boundary unknowns; attribution quarantine: 1")
    print("API-valid unchanged: 3198; no parsed response: 9; unknown works IF accepted: 1408")
    print("Integrity/literal links only; semantic/policy acceptance pending. No API, writes, merge or freeze.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
