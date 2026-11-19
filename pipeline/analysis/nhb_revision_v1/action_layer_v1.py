"""Independent, user-approved work-level action overlay; no API or core writes."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import contextlib
import io
from collections import Counter
from pathlib import Path

import verify_action_conflict_review_v1_1 as upstream
from action_review import ACTIONS, canonical, evidence_location, response_errors

base = upstream.original
MODULE, ROOT, INPUT = base.MODULE, base.ROOT, base.INPUT
ACCEPTANCE = MODULE / "action_layer_acceptance_v1"
OUTPUT = MODULE / "action_layer_v1"
QUARANTINE = {"W4411273906"}
EXPORTS = {"action_layer3755.jsonl", "accepted_delta_refs185.jsonl", "missing_response9.jsonl",
           "quarantine1.jsonl", "layer_summary.json", "validation_report.json", "README_zh.md"}
CODE = ("action_layer_v1.py", "prepare_action_layer_v1.py", "verify_action_layer_v1.py",
        "test_action_layer_v1.py")
SCHEMA = "nhb-independent-action-overlay-v1"


def fingerprint(path):
    path = base.safe(path)
    return {"sha256": base.digest(path), "size_bytes": path.stat().st_size}


def approval_archive():
    manifest_path = ACCEPTANCE / "acceptance_manifest.json"
    manifest = base.read_json(manifest_path)
    with base.safe(ACCEPTANCE / "acceptance_manifest.json.sha256").open(encoding="utf-8") as stream:
        checksum = stream.read().strip().split()
    base.require(checksum == [base.digest(manifest_path), "acceptance_manifest.json"], "Approval checksum changed")
    base.require(manifest["schema_version"] == "nhb-action-layer-acceptance-manifest-v1" and
                 manifest["provider_requests"] == 0 and manifest["core_labels_changed"] is False,
                 "Approval manifest scope differs")
    required = {str(MODULE / name) for name in CODE} | {
        str(base.BUNDLE / "review_manifest.json"), str(base.BUNDLE / "finalization_policy_proposal.json"),
        str(base.UPSTREAM / "work_routing3755.json"), str(INPUT),
        str(MODULE / "action_calibration_freeze_v6/user_confirmation_v6.json"),
        str(MODULE / "action_policy20_acceptance_v1/user_confirmation.json"),
        str(base.UPSTREAM / "user_confirmation.json")}
    base.require(required <= set(manifest["source_pins"]), "Approval source/code pins incomplete")
    for path, pin in manifest["source_pins"].items():
        upstream.check_pin(path, pin)
    for name, pin in manifest["outputs"].items():
        upstream.check_pin(ACCEPTANCE / name, pin)
    approval = base.read_json(ACCEPTANCE / "user_confirmation.json")
    base.require(approval["schema_version"] == "nhb-action-layer-user-acceptance-v1" and
                 approval["user_message_verbatim"] == "确认" and
                 approval["approval_source"] == "direct_human_message_in_current_thread" and
                 approval["accepted_named_action_delta_count"] == 185 and
                 approval["accepted_changed_work_count"] == 99 and
                 approval["previous_protected_action_keys_preserved"] == 83,
                 "Named direct-user acceptance differs")
    for key in ("model_assisted_layer_use_approved", "uncertain_retention_policy_approved",
                "missing_response_disposition_approved", "historical_flags_retention_approved",
                "independent_layer_generation_approved", "validation_execution_required"):
        base.require(approval[key] is True, "Required user-approved policy missing: " + key)
    for key in ("apply_to_original_final_database", "core_labels_changed", "original_outputs_modified",
                "whole_work_human_gold_approval", "independent_blinded_annotation",
                "new_paid_calls_approved", "formal_models_approved", "analysis_freeze_completed"):
        base.require(approval[key] is False, "Authority broadened: " + key)
    base.require(approval["provider_requests"] == 0 and
                 set(approval["input_attribution_quarantine_work_ids"]) == QUARANTINE,
                 "Requests/quarantine policy differs")
    return approval, manifest


def protected_sources():
    """Retain 83 action-level approvals, including evidence a later model rejected."""
    refs, support = {}, {}
    sources = [
        (MODULE / "action_calibration_freeze_v6/user_confirmation_v6.json",
         (("accepted_action_changes", "accepted_state"), ("accepted_retained_uncertainties", "reviewed_state"))),
        (MODULE / "action_policy20_acceptance_v1/user_confirmation.json", (("accepted_decisions", "accepted_state"),)),
        (base.UPSTREAM / "user_confirmation.json",
         (("accepted_action_changes", "accepted_state"), ("accepted_state_retention", "accepted_state"))),
    ]
    for path, collections in sources:
        approval = base.read_json(path)
        for collection, state_field in collections:
            for index, row in enumerate(approval[collection]):
                key = row["work_id"], row["action"]
                state = row[state_field]
                if key in refs:
                    base.require(refs[key]["accepted_state"] == state, "Conflicting protected approvals")
                ref = {"file": str(path), "collection": collection, "row_index_zero_based": index,
                       "canonical_row_sha256": canonical(row), "accepted_state": state}
                refs[key] = ref
                if state == "supported" and row.get("evidence"):
                    support[key] = {"evidence": row["evidence"], "input_packet_sha256": row["input_packet_sha256"],
                                    "reference": ref, "note": row.get("rationale_zh", "Earlier accepted evidence retained")}
    base.require(len(refs) == 83, "Protected approval keys differ")
    return refs, support


def accepted_proposals(approval):
    files = [base.BUNDLE / "discussion_conflict_proposals96.jsonl", base.BUNDLE / "priority_source_reviews15.jsonl"]
    base.require(approval["accepted_proposal_files"] == [str(path) for path in files], "Accepted proposal files differ")
    updates, delta_refs, work_refs = {}, [], {}
    for path in files:
        for line, proposal in enumerate(base.read_rows(path), 1):
            wid = proposal["work_id"]
            ref = {"file": str(path), "line": line, "canonical_record_sha256": canonical(proposal),
                   "input_packet_sha256": proposal["input_packet_sha256"]}
            work_refs[wid] = ref
            for delta in proposal["changes"]:
                key = wid, delta["action"]
                base.require(key not in updates, "Duplicate accepted delta")
                proof = [proposal["evidence"][i] for i in delta["evidence_indices"]]
                updates[key] = {"before": delta["before"], "state": delta["proposed_state"],
                                "evidence": proof, "note": proposal["rationale_zh"], "reference": ref}
                delta_refs.append({"work_id": wid, "action": delta["action"], "before": delta["before"],
                    "accepted_state": delta["proposed_state"], "proposal_reference": ref,
                    "approval_file": str(ACCEPTANCE / "user_confirmation.json")})
    base.require(len(updates) == 185 and len({k[0] for k in updates}) == 99, "Accepted delta scope differs")
    return updates, delta_refs, work_refs


def compose_row(packet, record, source, prior_keys, updates, prior_refs, prior_support):
    wid = packet["work_id"]
    response = record.get("response")
    row = {"schema_version": SCHEMA, "work_id": wid, "review_id": packet.get("review_id"),
           "title": packet["input_material"].get("title"), "input_packet_sha256": canonical(packet),
           "source_reference": source, "source_flags_historical": response["review_flags"] if response else [],
           "input_attribution_quarantined": wid in QUARANTINE, "action_decisions": [],
           "supported_actions": [], "positive_actions_for_analysis": [], "uncertain_actions": [],
           "not_established_actions": [], "original_api_success_credit": source["original_api_success_credit"],
           "independent_human_gold_standard": False, "whole_work_semantic_approval": False,
           "core_labels_changed": False, "scope": "original_work_action_overlay_not_merged_study"}
    if response is None:
        base.require(not prior_keys and not any(k[0] == wid for k in updates), "No-response action invented")
        row["assessment_status"] = "not_assessed_no_parsed_response"
        return row
    base.require(not response_errors(response, packet), "Source response invalid: " + wid)
    prior = {d["action"]: d["accepted_state"] for d in prior_keys}
    source_decisions = {d["action"]: d for d in response["action_decisions"]}
    row["assessment_status"] = "quarantined_input_attribution" if wid in QUARANTINE else "assessed_model_assisted"
    for action in ACTIONS:
        key = wid, action
        original = source_decisions[action]
        state = prior.get(action, original["state"])
        context = [response["evidence"][i] for i in original["evidence_indices"]]
        provenance = "model_assisted_candidate_policy_accepted"
        ref, note = source, original["note"]
        if action in prior:
            base.require(key in prior_refs and prior_refs[key]["accepted_state"] == state, "Protected source mismatch")
            provenance, ref = "prior_specific_user_acceptance", prior_refs[key]
            note = "Earlier specifically accepted state preserved; original model note remains historical at source."
            if state == "supported" and key in prior_support:
                accepted = prior_support[key]
                base.require(accepted["input_packet_sha256"] == canonical(packet), "Prior accepted evidence packet differs")
                context, note = accepted["evidence"], accepted["note"]
            elif state == "supported":
                base.require(original["state"] == "supported" and context, "Protected positive proof missing")
        if key in updates:
            base.require(action not in prior, "Protected decision overwritten")
            update = updates[key]
            base.require(update["before"] == state and update["reference"]["input_packet_sha256"] == canonical(packet),
                         "Accepted delta before/packet differs")
            state, context, note = update["state"], update["evidence"], update["note"]
            provenance, ref = "scoped_assisted_review_user_accepted", update["reference"]
        base.require(all(evidence_location(packet, e) for e in context), "Nonliteral retained evidence: " + wid)
        affirmative = context if state == "supported" else []
        base.require(state != "supported" or affirmative, "Positive action without literal proof")
        eligible = state == "supported" and wid not in QUARANTINE
        row["action_decisions"].append({"action": action, "state": state, "decision_provenance": provenance,
            "decision_reference": ref, "note": note, "affirmative_evidence": affirmative,
            "evidence_context": context, "positive_action_count_eligible": eligible})
        if state == "supported":
            row["supported_actions"].append(action)
            if eligible:
                row["positive_actions_for_analysis"].append(action)
        elif state == "uncertain":
            row["uncertain_actions"].append(action)
        else:
            row["not_established_actions"].append(action)
    base.require(not ("discussion_only" in row["supported_actions"] and len(row["supported_actions"]) > 1),
                 "Exclusive discussion-only action contradicts positive use")
    return row


def summarize(rows, delta_refs):
    by_action = {a: dict(Counter(d["state"] for r in rows for d in r["action_decisions"] if d["action"] == a)) for a in ACTIONS}
    return {"schema_version": "nhb-action-layer-summary-v1", "queue_size": len(rows),
        "assessment_status_counts": dict(Counter(r["assessment_status"] for r in rows)),
        "action_decision_rows": sum(len(r["action_decisions"]) for r in rows),
        "original_api_valid_unchanged": sum(r["original_api_success_credit"] for r in rows),
        "prior_protected_action_keys": sum(d["decision_provenance"] == "prior_specific_user_acceptance" for r in rows for d in r["action_decisions"]),
        "new_accepted_action_deltas": len(delta_refs), "new_changed_work_records": len({d["work_id"] for d in delta_refs}),
        "uncertain_work_records": sum(bool(r["uncertain_actions"]) for r in rows),
        "missing_response_work_records": sum(r["assessment_status"] == "not_assessed_no_parsed_response" for r in rows),
        "quarantined_work_records": sum(r["input_attribution_quarantined"] for r in rows),
        "supported_action_counts_for_analysis": dict(Counter(a for r in rows for a in r["positive_actions_for_analysis"])),
        "states_by_action_including_quarantine": by_action,
        "decision_provenance_counts": dict(Counter(d["decision_provenance"] for r in rows for d in r["action_decisions"])),
        "historical_flag_counts_overlapping": dict(Counter(f for r in rows for f in r["source_flags_historical"])),
        "provider_requests": 0, "core_labels_changed": False, "original_final_database_modified": False,
        "independent_human_gold_standard": False, "formal_models_ready": False,
        "layer_status": "frozen_export_requires_validation_pass_for_downstream_use"}


def reconstruct(verify_history=True):
    if verify_history:
        # Old archives deliberately still contain their original pending labels.
        with contextlib.redirect_stdout(io.StringIO()):
            upstream.main()
    approval, manifest = approval_archive()
    updates, delta_refs, work_refs = accepted_proposals(approval)
    prior_refs, prior_support = protected_sources()
    base.require(not set(updates) & set(prior_refs), "Accepted current changes overlap protected keys")
    packets = base.read_rows(INPUT, 3755)
    routing = base.read_json(base.UPSTREAM / "work_routing3755.json")
    base.require([p["work_id"] for p in packets] == [r[0] for r in routing["rows"]], "Queue order changed")
    cache, rows = {}, []
    for packet, route in zip(packets, routing["rows"]):
        path = routing["source_files"][route[1]]
        if path not in cache:
            cache[path] = base.read_rows(path)
        record = cache[path][route[2] - 1]
        response = record.get("response")
        base.require(record["work_id"] == packet["work_id"] and canonical(record) == route[3] and
                     (canonical(response) if response else None) == route[4], "Selected source pointer changed")
        source = {"file": path, "line": route[2], "canonical_record_sha256": route[3],
                  "response_sha256": route[4], "historical_stage": routing["stages"][route[5]],
                  "historical_route": routing["routes"][route[6]], "original_api_success_credit": route[7]}
        row = compose_row(packet, record, source, route[9], updates, prior_refs, prior_support)
        row["work_review_reference"] = work_refs.get(packet["work_id"])
        rows.append(row)
    summary = summarize(rows, delta_refs)
    base.require(len(rows) == 3755 and summary["action_decision_rows"] == 33714 and
                 summary["original_api_valid_unchanged"] == 3198 and summary["prior_protected_action_keys"] == 83 and
                 summary["new_accepted_action_deltas"] == 185 and summary["new_changed_work_records"] == 99 and
                 summary["uncertain_work_records"] == 1408 and summary["missing_response_work_records"] == 9 and
                 summary["quarantined_work_records"] == 1, "Reconstructed frozen counts differ")
    base.require(not any("discussion_only" in r["supported_actions"] for r in rows), "Active discussion/core conflict")
    missing = [r for r in rows if r["assessment_status"] == "not_assessed_no_parsed_response"]
    quarantined = [r for r in rows if r["input_attribution_quarantined"]]
    policy = base.read_json(base.BUNDLE / "finalization_policy_proposal.json")
    base.require([r["work_id"] for r in missing] == policy["missing_response_work_ids"], "Missing membership differs")
    return rows, delta_refs, missing, quarantined, summary, manifest


def validation_document():
    return {"schema_version": "nhb-action-layer-validation-v1", "blockers": 0,
            "work_records": 3755, "action_decision_rows": 33714, "protected_action_keys": 83,
            "accepted_action_deltas": 185, "uncertain_work_records": 1408,
            "missing_response_work_records": 9, "quarantined_work_records": 1,
            "source_and_export_reconstruction_passed": True, "action_overlay_ready": True,
            "formal_models_ready": False, "core_labels_changed": False,
            "provider_requests": 0, "independent_human_gold_standard": False}


def verify_export(directory, reconstructed=None):
    directory = Path(directory)
    rows, deltas, missing, quarantined, summary, _ = reconstruct() if reconstructed is None else reconstructed
    manifest = base.read_json(directory / "layer_manifest.json")
    with base.safe(directory / "layer_manifest.json.sha256").open(encoding="utf-8") as stream:
        checksum = stream.read().strip().split()
    base.require(checksum == [base.digest(directory / "layer_manifest.json"), "layer_manifest.json"], "Layer manifest checksum differs")
    base.require(manifest["schema_version"] == "nhb-action-layer-manifest-v1" and
                 manifest["user_approval_recorded"] is True and manifest["provider_requests"] == 0 and
                 manifest["core_labels_changed"] is False and manifest["original_final_database_modified"] is False and
                 manifest["independent_human_gold_standard"] is False and set(manifest["outputs"]) == EXPORTS,
                 "Frozen layer authority/inventory differs")
    for path, pin in manifest["source_pins"].items():
        upstream.check_pin(path, pin)
    base.require({str(MODULE / name) for name in CODE} | {str(ACCEPTANCE / "acceptance_manifest.json"),
                 str(ACCEPTANCE / "user_confirmation.json")} <= set(manifest["source_pins"]), "Layer pins incomplete")
    for name, pin in manifest["outputs"].items():
        upstream.check_pin(directory / name, pin)
    expected_rows = {"action_layer3755.jsonl": rows, "accepted_delta_refs185.jsonl": deltas,
                     "missing_response9.jsonl": missing, "quarantine1.jsonl": quarantined}
    for name, expected in expected_rows.items():
        base.require(base.read_rows(directory / name) == expected, "Export reconstruction differs: " + name)
    base.require(base.read_json(directory / "layer_summary.json") == summary, "Frozen summary differs")
    base.require((directory / "README_zh.md").read_bytes() == (ACCEPTANCE / "README_zh.md").read_bytes(), "Usage instructions differ")
    report = validation_document()
    base.require(base.read_json(directory / "validation_report.json") == report, "Validation report differs")
    return report
