"""Read-only source reconciliation and blinded action calibration preparation.

Never imports the old API runner, calls a provider, or updates core labels.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from common import MODULE, ROOT, assert_unchanged, output_dir, read_json, sha256
from baseline_features import fingerprint

CONFIG = MODULE / "action_review_config_v1.json"
PROMPT = MODULE / "action_review_prompt_v1.txt"
GUIDE = MODULE / "ACTION_REVIEW_v1.md"
CODE = ("common.py", "baseline_features.py", "action_review.py", "prepare_action_review.py",
        "validate_action_review.py", "test_action_review.py")
ACTIONS = ("retrieved_precomputed_structure", "ran_alphafold", "ran_colabfold",
           "integrated_empirical_workflow", "docking_or_screening", "benchmarked_or_evaluated",
           "modified_or_extended", "developed_downstream_tool", "discussion_only")
CORE = ("primary_label", "relevance_level", "evidence_level", "af_related_label", "af_use_label",
        "adoption_eligible", "exclusion_reason", "future_or_hypothetical_only")
STATES = ("supported", "not_established", "uncertain")
EXPORTS = ("action_review_inputs_blinded_v1.jsonl", "action_review_comparison_v1.jsonl",
           "action_calibration_100_inputs_blinded_v1.jsonl", "action_calibration_selection_v1.json",
           "action_calibration_human_template_v1.jsonl", "action_calibration_blinded_v1.md",
           "action_calibration_comparison_v1.md", "action_only_output_schema_v1.json",
           "preparation_summary.json")


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def configuration():
    c = read_json(CONFIG)
    expected = {"schema_version": "nhb-action-review-preparation-config-v1", "seed": 20261004,
        "calibration_size": 100, "scope": "frozen_main_confirmed_AF_work_queue",
        "unit": "original_work_not_merged_study", "core_labels": "preserve_no_reclassification",
        "reuse_policy": "same_packet_hash_candidate_only_no_automatic_acceptance",
        "sample_policy": "balanced_round_robin_difference_family_x_evidence_tier_hash_order",
        "action_states": list(STATES), "provider_requests": 0}
    if any(c.get(k) != v for k, v in expected.items()):
        raise ValueError("Changed action policy needs a separately reviewed version")
    return c


def safe_source(path):
    p = Path(path)
    if not p.is_absolute():
        p = ROOT/p
    if not p.resolve().is_relative_to(ROOT) or p.is_symlink() or not p.is_file():
        raise ValueError(f"Expected regular in-project input: {p}")
    return p


def load_inputs(foundation):
    """Full selected-source hashes, no aggregation; safe for --dry-run."""
    import pyarrow.parquet as pq
    foundation = output_dir(foundation, existing=True)
    c = configuration()
    mp = foundation/"prepare_manifest.json"
    m = read_json(mp)
    vp = foundation/"validation_report.json"
    v = read_json(vp)
    checks = v.get("checks")
    if (m.get("schema_version") != "nhb-foundations-run-v2" or
        v.get("prepare_manifest_sha256") != sha256(mp) or v.get("blockers") != [] or
        v.get("work_level_foundations_ready") is not True or not isinstance(checks, list) or
        not checks or any(r.get("passed") is not True or r.get("violations") != 0 for r in checks)):
        raise ValueError("Matching validated foundation v2 is required")
    pinned = {r["role"]: r for r in m["inputs"] if r["role"] in {"final_lock", "final_csv"}}
    v2p = safe_source(pinned["final_lock"]["path"])
    v2 = read_json(v2p)
    if v2.get("schema_version") != "af-production-final-database-lock-v2":
        raise ValueError("Expected frozen final-v2 lock")
    v1p = safe_source(v2["sources"]["v1_lock"]["path"])
    v1 = read_json(v1p)
    files = {"foundation_manifest": mp, "foundation_validation": vp,
             "queue": foundation/"action_review_queue.parquet", "final_lock": v2p,
             "previous_lock": v1p,
             "final": safe_source(v2["outputs"]["af_research_database_final_v2.jsonl"]["path"])}
    expected = {"queue": m["outputs"]["action_review_queue.parquet"]["sha256"],
        "final_lock": pinned["final_lock"]["sha256"],
        "previous_lock": v2["sources"]["v1_lock"]["sha256"],
        "final": v2["outputs"]["af_research_database_final_v2.jsonl"]["sha256"]}
    for role in ("input", "model_a", "model_b", "model_c", "direct_human"):
        files[role] = safe_source(v1["sources"][role]["path"])
        expected[role] = v1["sources"][role]["sha256"]
    files["final_csv"] = safe_source(pinned["final_csv"]["path"])
    expected["final_csv"] = pinned["final_csv"]["sha256"]
    for name in CODE:
        files["code:"+name] = MODULE/name
    files.update(config=CONFIG, prompt=PROMPT, guide=GUIDE)
    inv = []
    for role, path in files.items():
        rec = fingerprint(safe_source(path))
        if role in expected and rec["sha256"] != expected[role]:
            raise ValueError(f"Frozen source changed: {role}")
        if path.suffix == ".jsonl" and rec["size_bytes"] > c["maximum_file_bytes"]:
            raise ValueError(f"Input byte cap exceeded: {role}")
        inv.append(dict(rec, role=role))
    pf = pq.ParquetFile(files["queue"])
    expected_rows = m["outputs"]["action_review_queue.parquet"]["rows"]
    if (pf.metadata.num_rows != expected_rows or expected_rows > c["maximum_jsonl_rows"] or
        not {"work_id", "publication_year", "observed_actions_status"}.issubset(pf.schema_arrow.names)):
        raise ValueError("Queue metadata differs from frozen foundation")
    assert_unchanged(inv)
    return c, files, inv, expected_rows


def selected_records(path, ids, c):
    """Bounded streaming parser. Check IDs throughout file, retain only selected rows."""
    result, seen = {}, set()
    with path.open("rb") as handle:
        for number in range(1, c["maximum_jsonl_rows"]+2):
            line = handle.readline(c["maximum_line_bytes"]+1)
            if not line:
                break
            if number > c["maximum_jsonl_rows"] or len(line) > c["maximum_line_bytes"]:
                raise ValueError(f"JSONL row/line cap exceeded: {path.name}")
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("work_id"), str):
                raise ValueError(f"Malformed JSONL row: {path.name}:{number}")
            wid = row["work_id"]
            if wid in seen:
                raise ValueError(f"Duplicate work_id: {path.name}:{wid}")
            seen.add(wid)
            if wid in ids:
                result[wid] = row
    return result


def actions(value):
    if not isinstance(value, list) or any(not isinstance(a, str) for a in value):
        raise ValueError("Expected canonical action array")
    if len(value) != len(set(value)) or set(value)-set(ACTIONS)-{"none"}:
        raise ValueError("Invalid/duplicate action vocabulary")
    if "none" in value and len(value) != 1:
        raise ValueError("none cannot coexist with other actions")
    return sorted(value)


def scalar(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return " ".join(str(value).split()).casefold()


def source_role(value):
    """Explicit archived aliases only; never infer a role from model/provider."""
    aliases = {"A": "model_a", "model_a": "model_a", "B": "model_b", "model_b": "model_b"}
    if not isinstance(value, str) or value not in aliases:
        raise ValueError(f"Unknown A/B source_model marker: {value!r}")
    return aliases[value]


def check_link(wid, packet, final, a, b):
    digest = canonical(packet)
    f = final["final_decision"]
    if (final["work_id"] != wid or packet["work_id"] != wid or
        f.get("af_use_label") != "yes" or f.get("adoption_eligible") != "yes" or
        f.get("observed_actions_status") != "disagreement_unadjudicated" or
        f.get("observed_actions") is not None or final.get("source_route") != "ab_core_agreement" or
        final["input_evidence"]["input_packet_sha256"] != digest):
        raise ValueError(f"Queue/core/input mismatch: {wid}")
    refs = {}
    for ref in final["provenance"]["selected_sources"]:
        role = source_role(ref.get("source_model"))
        if role in refs:
            raise ValueError(f"Duplicate canonical source role: {wid}:{role}")
        refs[role] = ref
    if set(refs) != {"model_a", "model_b"}:
        raise ValueError(f"Exactly one A and one B selected source required: {wid}")
    for name, record in (("model_a", a), ("model_b", b)):
        r = record["response"]
        if (source_role(record.get("source_model")) != name or
            record.get("work_id") != wid or r.get("work_id") != wid or
            record.get("review_id") != packet["review_id"] or r.get("review_id") != packet["review_id"] or
            record["provenance"].get("input_packet_sha256") != digest or
            refs[name]["canonical_record_sha256"] != canonical(record) or
            any(scalar(r.get(k)) != scalar(f.get(k)) for k in CORE)):
            raise ValueError(f"Canonical source/core provenance mismatch: {wid}:{name}")
    aa, bb = actions(a["response"]["observed_actions"]), actions(b["response"]["observed_actions"])
    if aa == bb or final["support"].get("model_a_observed_actions") != aa or final["support"].get("model_b_observed_actions") != bb:
        raise ValueError(f"Action difference/source mismatch: {wid}")
    return digest, aa, bb


def evidence_location(packet, e):
    material = packet["input_material"]
    kind = e.get("source_kind")
    if kind in {"title", "abstract"}:
        texts = [material.get(kind) or ""] if e.get("block_index") is None else []
    elif kind == "fulltext_block":
        texts = [b.get("text") or "" for b in material.get("evidence_blocks", [])
                 if type(e.get("block_index")) is int and b.get("index") == e["block_index"] and
                 b.get("section") == e.get("section")]
    elif kind == "matched_reference" and e.get("block_index") is None:
        texts = [r.get("reference_text") or "" for r in material.get("matched_seed_references", [])]
    else:
        texts = []
    quote = e.get("quote")
    return isinstance(quote, str) and bool(quote.strip()) and len(quote.split()) <= 25 and any(quote in t for t in texts)


def source_diagnostics(packet, record):
    response = record["response"]
    evidence = response.get("evidence") or []
    supported = [a for a in actions(response["observed_actions"]) if a != "none"]
    links = response.get("action_evidence") or []
    bad_links = []
    for action in supported:
        matches = [r for r in links if r.get("action") == action]
        if len(matches) != 1 or not matches[0].get("evidence_indices") or any(
            type(i) is not int or i < 0 or i >= len(evidence) for i in matches[0].get("evidence_indices", [])):
            bad_links.append(action)
    return {"invalid_quote_indices": [i for i,e in enumerate(evidence) if not evidence_location(packet,e)],
            "invalid_action_links": bad_links,
            "semantic_actions_not_automatically_verified": True}


def difference_family(aa, bb):
    diff = set(aa)^set(bb)
    families = [("execution", {"ran_alphafold", "ran_colabfold"}),
        ("retrieval", {"retrieved_precomputed_structure"}),
        ("tool_or_extension", {"modified_or_extended", "developed_downstream_tool"}),
        ("benchmark", {"benchmarked_or_evaluated"}), ("docking", {"docking_or_screening"}),
        ("integration", {"integrated_empirical_workflow"})]
    all_families = [name for name, vocabulary in families if diff & vocabulary]
    return (all_families[0] if all_families else "other"), all_families or ["other"]


def blind_packet(packet, original_digest):
    m = packet["input_material"]
    allowed = ("title", "abstract", "doi", "publication_year", "work_type", "evidence_blocks", "matched_seed_references")
    material = {k: copy.deepcopy(m[k]) for k in allowed if k in m}
    body = any((b.get("text") or "").strip() for b in material.get("evidence_blocks", []))
    abstract = bool((material.get("abstract") or "").strip()) and packet.get("input_quality", {}).get("abstract_status") == "usable"
    eligible = packet.get("model_eligible") is True and (body or abstract)
    return {"schema_version": "nhb-action-review-input-v1", "work_id": packet["work_id"],
        "review_id": packet["review_id"], "original_input_packet_sha256": original_digest,
        "evidence_tier": packet["evidence_tier"], "context_policy": copy.deepcopy(packet.get("context_policy")),
        "action_review_eligible": eligible, "input_material": material}


def select_calibration(reviews, n, seed):
    groups = defaultdict(list)
    for row in reviews:
        if row["action_review_eligible"]:
            groups[row["sampling_stratum"]].append(row["work_id"])
    for key in groups:
        groups[key].sort(key=lambda wid: (hashlib.sha256(f"{seed}:{wid}".encode()).hexdigest(), wid))
    selected, offsets = [], Counter()
    while len(selected) < n:
        progress = False
        for key in sorted(groups):
            if offsets[key] < len(groups[key]) and len(selected) < n:
                selected.append(groups[key][offsets[key]])
                offsets[key] += 1
                progress = True
        if not progress:
            break
    return selected


def assemble(files, c, expected_rows):
    import pyarrow.parquet as pq
    queue = pq.read_table(files["queue"]).to_pylist()
    ids = {q["work_id"] for q in queue}
    if len(ids) != len(queue) or len(queue) != expected_rows or any(
        q["observed_actions_status"] != "disagreement_unadjudicated" or not 2020 <= q["publication_year"] <= 2025 for q in queue):
        raise ValueError("Invalid queue content or duplicates")
    records = {role: selected_records(files[role], ids, c) for role in
               ("input", "final", "model_a", "model_b", "model_c", "direct_human")}
    for role in ("input", "final", "model_a", "model_b"):
        if set(records[role]) != ids:
            raise ValueError(f"Missing queue evidence/source rows: {role}")
    blind, review = [], []
    for q in sorted(queue, key=lambda r:r["work_id"]):
        wid = q["work_id"]
        packet, final, a, b = [records[r][wid] for r in ("input", "final", "model_a", "model_b")]
        if packet["input_material"].get("publication_year") != q["publication_year"]:
            raise ValueError(f"Queue publication year mismatch: {wid}")
        digest, aa, bb = check_link(wid, packet, final, a, b)
        bp = blind_packet(packet, digest)
        blind.append(bp)
        family, families = difference_family(aa, bb)
        reuse = []
        for role in ("model_c", "direct_human"):
            r = records[role].get(wid)
            if r:
                matching = r.get("provenance", {}).get("input_packet_sha256") == digest
                reuse.append({"source_role": role, "same_input_hash": matching,
                    "status": "candidate_pending_manual_acceptance" if matching else "different_input_not_reusable",
                    "record_sha256": canonical(r), "record": r,
                    "evidence_diagnostics": source_diagnostics(packet, r)})
        review.append({"schema_version": "nhb-action-review-comparison-v1", "work_id": wid,
            "review_id": bp["review_id"], "publication_year": q["publication_year"],
            "original_input_packet_sha256": digest, "blinded_packet_sha256": canonical(bp),
            "evidence_tier": bp["evidence_tier"], "action_review_eligible": bp["action_review_eligible"],
            "manual_queue_reason": None if bp["action_review_eligible"] else "no_usable_abstract_or_body",
            "difference_family": family, "all_difference_families": families,
            "sampling_stratum": family+"|"+bp["evidence_tier"],
            "symmetric_action_difference": sorted(set(aa)^set(bb)),
            "frozen_core_decision": {k: final["final_decision"].get(k) for k in CORE},
            "model_a": {"actions": aa, "record": a, "evidence_diagnostics": source_diagnostics(packet,a)},
            "model_b": {"actions": bb, "record": b, "evidence_diagnostics": source_diagnostics(packet,b)},
            "existing_adjudication_candidates": reuse,
            "final_action_review_status": "pending_not_adjudicated"})
    selected = select_calibration(review, c["calibration_size"], c["seed"])
    if len(selected) != c["calibration_size"]:
        raise ValueError("Fewer than 100 eligible calibration rows; review evidence before sampling")
    index = {r["work_id"]:r for r in review}
    summary = {"schema_version": "nhb-action-review-preparation-summary-v1", "queue_work_records": len(ids),
        "action_review_eligible": sum(r["action_review_eligible"] for r in review),
        "manual_evidence_only": sum(not r["action_review_eligible"] for r in review),
        "calibration_records": len(selected), "seed": c["seed"],
        "difference_family_counts": dict(sorted(Counter(r["difference_family"] for r in review).items())),
        "population_stratum_counts": dict(sorted(Counter(r["sampling_stratum"] for r in review).items())),
        "calibration_stratum_counts": dict(sorted(Counter(index[w]["sampling_stratum"] for w in selected).items())),
        "existing_same_packet_candidate_records": sum(any(x["same_input_hash"] for x in r["existing_adjudication_candidates"]) for r in review),
        "existing_different_packet_candidate_records": sum(any(not x["same_input_hash"] for x in r["existing_adjudication_candidates"]) for r in review),
        "source_diagnostic_warning_records": sum(any(r[k]["evidence_diagnostics"][field] for k in ("model_a","model_b") for field in ("invalid_quote_indices","invalid_action_links")) for r in review),
        "core_labels_changed": 0, "action_decisions_completed": 0, "provider_requests": 0,
        "ready_for_manual_calibration": True, "ready_for_api_run": False,
        "existing_08_runner_compatible": False,
        "sample_is_population_error_rate_estimator": False}
    return blind, review, selected, summary


def action_schema():
    ev = {"type":"object", "additionalProperties":False,
        "required":["source_kind","block_index","section","quote"], "properties":{
            "source_kind":{"enum":["title","abstract","fulltext_block","matched_reference"]},
            "block_index":{"type":["integer","null"],"minimum":0},
            "section":{"type":["string","null"]},"quote":{"type":"string","minLength":1,"maxLength":500}}}
    decision = {"type":"object", "additionalProperties":False,
        "required":["action","state","evidence_indices","note"], "properties":{
            "action":{"enum":list(ACTIONS)},"state":{"enum":list(STATES)},
            "evidence_indices":{"type":"array","uniqueItems":True,"items":{"type":"integer","minimum":0,"maximum":11}},
            "note":{"type":"string","maxLength":600}}}
    return {"$schema":"https://json-schema.org/draft/2020-12/schema", "type":"object",
        "additionalProperties":False, "required":["schema_version","work_id","review_id","action_decisions","supported_actions","evidence","review_flags","reasoning_summary"],
        "properties":{"schema_version":{"const":"nhb-action-review-output-v1"},
            "work_id":{"type":"string"},"review_id":{"type":"string"},
            "action_decisions":{"type":"array","minItems":9,"maxItems":9,"items":decision},
            "supported_actions":{"type":"array","uniqueItems":True,"items":{"enum":list(ACTIONS)}},
            "evidence":{"type":"array","maxItems":12,"items":ev},
            "review_flags":{"type":"array","uniqueItems":True,"items":{"enum":["prediction_origin_unclear","conflicting_evidence","core_label_conflict","evidence_insufficient"]}},
            "reasoning_summary":{"type":"string","maxLength":1200}}}


def response_errors(result, packet):
    """Local action-only checks for later integration; never converts errors to labels."""
    from jsonschema import Draft202012Validator
    errors = [e.message for e in Draft202012Validator(action_schema()).iter_errors(result)]
    if errors:
        return errors
    if result["work_id"] != packet["work_id"] or result["review_id"] != packet["review_id"]:
        errors.append("Identity mismatch")
    ds, evidence = result["action_decisions"], result["evidence"]
    if sorted(d["action"] for d in ds) != sorted(ACTIONS):
        errors.append("Each action must occur exactly once")
    supported = sorted(d["action"] for d in ds if d["state"] == "supported")
    if supported != sorted(result["supported_actions"]):
        errors.append("supported_actions differs from decisions")
    if not supported and "evidence_insufficient" not in result["review_flags"]:
        errors.append("No supported action requires evidence_insufficient/manual review")
    for i,e in enumerate(evidence):
        if not evidence_location(packet,e):
            errors.append(f"Invalid exact source quote/location: {i}")
    for d in ds:
        links = d["evidence_indices"]
        if d["state"] == "supported":
            if not links or any(i >= len(evidence) for i in links):
                errors.append(f"Missing/out-of-range evidence links: {d['action']}")
            elif any(evidence[i]["source_kind"] == "matched_reference" for i in links):
                errors.append("Bibliography does not prove an action")
        elif links or not d["note"].strip():
            errors.append("Unresolved/not-established actions require note and no affirmative links")
    if "discussion_only" in supported:
        if len(supported) > 1 or "core_label_conflict" not in result["review_flags"]:
            errors.append("discussion_only conflicts with actual use/core; manual review required")
    if any(d["state"] == "uncertain" for d in ds) and not result["review_flags"]:
        errors.append("Uncertain actions need a review flag")
    return errors


def human_template(packet):
    return {"schema_version":"nhb-action-human-calibration-template-v1", "work_id":packet["work_id"],
        "review_id":packet["review_id"], "blinded_packet_sha256":canonical(packet),
        "reviewer_id":"", "reviewed_at":"", "review_status":"pending",
        "action_decisions":[{"action":a,"state":None,"evidence":[],"note":""} for a in ACTIONS],
        "core_label_conflict":None, "notes":""}


def cards(packets, comparisons=None):
    rows = ["# 动作校准材料 v1", "", "原始work为单位；仅记录动作，不修改核心标签。", ""]
    index = {r["work_id"]:r for r in comparisons or []}
    for n,p in enumerate(packets,1):
        wid, m = p["work_id"], p["input_material"]
        rows += [f"## C{n:03d} / {wid}", "", f"标题：{m.get('title','')}", "",
                 f"证据层级：{p['evidence_tier']}；原输入哈希：{p['original_input_packet_sha256']}", ""]
        if wid in index:
            r = index[wid]
            rows += ["### 非盲核对信息（完成独立判断后才查看）", "",
                "A："+" | ".join(r["model_a"]["actions"]), "",
                "B："+" | ".join(r["model_b"]["actions"]), "",
                f"分歧：{r['sampling_stratum']}；旧C／人工候选数：{len(r['existing_adjudication_candidates'])}", ""]
        rows += ["### 原始科学证据", "", "````text", "[Title] "+(m.get("title") or ""),
                 "[Abstract] "+(m.get("abstract") or ""), "````", ""]
        for b in m.get("evidence_blocks",[]):
            rows += [f"Block {b.get('index')} / Section {b.get('section')}", "", "````text", b.get("text") or "", "````", ""]
        for ref in m.get("matched_seed_references",[]):
            rows += ["[Reference; not action proof]", "", "````text", ref.get("reference_text") or "", "````", ""]
    return "\n".join(rows)+"\n"


def export_content(blind, review, selected, summary):
    byid = {p["work_id"]:p for p in blind}
    sample = [byid[w] for w in selected]
    selection = {"schema_version":"nhb-action-calibration-selection-v1", "seed":summary["seed"],
        "work_ids":selected, "ordered_work_id_sha256":canonical(selected),
        "sample_policy":"balanced_round_robin_difference_family_x_evidence_tier_hash_order",
        "input_record_sha256":{w:canonical(byid[w]) for w in selected},
        "population_stratum_counts":summary["population_stratum_counts"],
        "calibration_stratum_counts":summary["calibration_stratum_counts"],
        "population_error_rate_estimation":False}
    return {EXPORTS[0]:blind, EXPORTS[1]:review, EXPORTS[2]:sample, EXPORTS[3]:selection,
        EXPORTS[4]:[human_template(p) for p in sample], EXPORTS[5]:cards(sample),
        EXPORTS[6]:cards(sample,review), EXPORTS[7]:action_schema(), EXPORTS[8]:summary}
