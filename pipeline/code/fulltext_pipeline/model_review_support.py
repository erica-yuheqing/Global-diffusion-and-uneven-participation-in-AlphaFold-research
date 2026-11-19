"""Local input-quality and conservative consistency checks for model review.

These checks are not a scientific gold standard. In particular, no AF keyword
match is ever converted into a negative adoption label.
"""

from __future__ import annotations

import copy
import hashlib
import html
import json
import math
import re
from typing import Any


QUALITY_VERSION = "af-review-input-quality-v1"
AF_TERM = re.compile(
    r"(?<![A-Za-z0-9])(?:alpha\s*fold(?:\s*[- ]?\d)?|colabfold|afdb|af[23])(?![A-Za-z0-9])",
    re.I,
)
AUTHOR_NAVIGATION = re.compile(r"search for other works by this author", re.I)
KNOWN_LABELS = {
    "FP": ("R0", "false", "no", "no"),
    "background_only": ("R1", "background", "no", "no"),
    "review_discussion": ("R2", "related", "no", "no"),
    "database_consumption": ("R3", "related", "yes", "yes"),
    "model_application": ("R3", "related", "yes", "yes"),
    "method_development": ("R4", "related", "yes", "yes"),
    "original_platform": ("R4", "related", "yes", "no"),
}
USE_ACTIONS = {
    "retrieved_precomputed_structure", "ran_alphafold", "ran_colabfold",
    "integrated_empirical_workflow", "docking_or_screening",
    "benchmarked_or_evaluated", "modified_or_extended", "developed_downstream_tool",
}
AF_EVALUATION = re.compile(
    r"\b(?:pLDDT|PAE|predicted aligned error|prediction (?:accuracy|quality|confidence)|"
    r"model (?:accuracy|quality|confidence)|low[- ]confidence|unreliable region|"
    r"failed? to predict|prediction failures?|incorrect(?:ly)? predict|"
    r"too low to|did not support)\b",
    re.I,
)
MOLECULAR_DOCKING_OR_SCREENING = re.compile(
    r"\b(?:molecular docking|virtual screening|ligand docking|protein[-– ]protein docking|"
    r"in[- ]silico\s+docks?\s+of\s+(?:compounds?|ligands?|drugs?|peptides?)\s+(?:to|into|against)|"
    r"(?:structure|model|complex)\s+(?:is|was)\s+subjected\s+to\s+(?:molecular\s+)?docking|"
    r"dock(?:ed|ing)?\s+(?:a\s+)?(?:ligand|compound|drug|peptide|protein)|"
    r"dock(?:ed|ing)?\s+(?:with|against|to)\s+(?:(?:a|an|the)\s+)?(?:[A-Za-z0-9-]+\s+){0,3}"
    r"(?:ligand|compound|drug|peptide|protein|receptor|vaccine|molecule|atp|dna|rna|mhc|tlr[- ]?\d?)|"
    r"dock(?:ed|ing)?\s+.{1,60}\s+into\s+(?:the\s+)?(?:[A-Za-z0-9-]+[- ]?)?"
    r"(?:binding|active|allosteric|catalytic)[- ](?:site|pocket)|"
    r"screen(?:ed|ing)?\s+(?:a\s+)?(?:compound|drug|ligand|library))\b",
    re.I,
)


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def comparison_text(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(value)).casefold().split())


def abstract_status(value: Any, title: str = "") -> str:
    if not isinstance(value, str) or not value.strip():
        return "missing"
    if len(AUTHOR_NAVIGATION.findall(value)) >= 2:
        return "invalid_author_navigation"
    # A single access-control phrase in an otherwise scientific abstract is not
    # enough to reject it. This second signature needs multiple page controls.
    controls = sum(bool(re.search(pattern, value, re.I)) for pattern in (
        r"get access", r"search for other works", r"corresponding author:",
        r"sign in", r"purchase access",
    ))
    if controls >= 3 and len(re.findall(r"google scholar", value, re.I)) >= 2:
        return "invalid_page_controls"
    normalized = comparison_text(value)
    if title and normalized == comparison_text(title):
        return "invalid_title_only"
    return "usable"


def body_block(block: dict[str, Any]) -> bool:
    return (
        bool(str(block.get("text") or "").strip())
        and str(block.get("block_type") or "").casefold() not in {"title", "abstract"}
        and str(block.get("section") or "").strip().casefold() not in {"title", "abstract"}
    )


def prepare_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Idempotently sanitize a packet, retaining its identity and sampling slot."""
    result = copy.deepcopy(packet)
    production_oversize = (
        bool(result.get("production_protocol"))
        and result.get("evidence_tier") == "oversize_context_human_review"
        and isinstance(result.get("forced_decision"), dict)
    )
    production_forced_decision = copy.deepcopy(result.get("forced_decision"))
    material = result.setdefault("input_material", {})
    previous = result.get("input_quality", {})
    previous = previous if previous.get("version") == QUALITY_VERSION else {}
    flags = set(previous.get("flags", []))
    status = abstract_status(material.get("abstract"), material.get("title") or "")
    removed_hash = previous.get("removed_abstract_sha256")
    if status.startswith("invalid_"):
        removed_hash = fingerprint(material["abstract"])
        flags.add(status)
        material["abstract"] = None
    elif status == "missing":
        material["abstract"] = None
        if str(previous.get("abstract_status", "")).startswith("invalid_"):
            status = previous["abstract_status"]

    blocks = []
    for block in material.get("evidence_blocks", []):
        if abstract_status(block.get("text")).startswith("invalid_"):
            flags.add("removed_navigation_block")
            continue
        blocks.append(block)
    has_body = any(body_block(block) for block in blocks)
    if "evidence_blocks" in material:
        material["evidence_blocks"] = blocks if has_body else []
    if not has_body and result.get("evidence_tier") == "fulltext_evidence":
        flags.add("no_usable_fulltext_blocks")

    if has_body:
        tier = "fulltext_evidence"
    elif material.get("abstract"):
        tier = "abstract_only"
    else:
        tier = "insufficient_evidence"
    result.update({
        "schema_version": "af-model-review-input-v2",
        "evidence_tier": tier,
        "model_eligible": tier != "insufficient_evidence",
        "forced_decision": None,
        "input_quality": {
            "version": QUALITY_VERSION,
            "abstract_status": status,
            "fulltext_body_available": has_body,
            "flags": sorted(flags),
            "removed_abstract_sha256": removed_hash,
        },
    })
    if tier == "insufficient_evidence":
        result["forced_decision"] = {
            "label": "U",
            "primary_label": "uncertain",
            "relevance_level": "RU",
            "evidence_level": "E0",
            "af_related_label": "uncertain",
            "af_use_label": "uncertain",
            "adoption_eligible": "uncertain",
            "needs_human_review": True,
            "reason": "No usable full-text blocks or substantive abstract; missing evidence is not non-use.",
        }
    if production_oversize:
        # The production packet builder intentionally routes exceptional
        # oversized evidence packets to human review. Re-sanitizing a packet
        # in the runner must not silently turn it back into an abstract-only
        # API request.
        result["evidence_tier"] = "oversize_context_human_review"
        result["model_eligible"] = False
        result["forced_decision"] = production_forced_decision
        result["input_quality"]["flags"] = sorted(
            {*result["input_quality"].get("flags", []), "oversize_context_requires_human_review"}
        )
    serialized = json.dumps(material, ensure_ascii=False, separators=(",", ":"))
    result["estimated_input_tokens"] = math.ceil(len(serialized) / 4)
    return result


def source_texts(packet: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    material = packet.get("input_material", {})
    source = evidence.get("source_kind")
    if source in {"title", "abstract"}:
        return [material.get(source) or ""]
    if source == "fulltext_block":
        return [block.get("text") or "" for block in material.get("evidence_blocks", [])
                if block.get("index") == evidence.get("block_index")]
    if source == "matched_reference":
        return [item.get("reference_text") or "" for item in material.get("matched_seed_references", [])]
    return []


def explicit_run_quote(text: str, *, colabfold_only: bool = False) -> bool:
    """Conservative English/Chinese proof gate; failure means unknown, not no run.

    An adjectival 'AF-predicted structure' or 'derived from AF' alone does not
    establish that these authors ran a prediction. Non-covered phrasing should
    be flagged for review, not converted to a negative use label.
    """
    text = " ".join(text.split())
    # A comparison WITH ColabFold after running a different predictor does not
    # establish that ColabFold was run. Conservatively require a procedure
    # quote that precedes (or is separate from) the comparison clause.
    text = re.split(r"\b(?:compared|comparing|comparison)\b", text, maxsplit=1, flags=re.I)[0]
    if not AF_TERM.search(text):
        return False
    if re.search(r"\b(?:did not|was not|were not|never|could|might|may|plan to|will)\b", text, re.I):
        return False
    model = (
        r"colabfold(?:_batch)?"
        if colabfold_only else
        r"(?:alpha\s*fold(?:\s*(?:[- ]?\d|v(?:ersion)?\.?\s*\d))?|"
        r"alpha\s*fold(?:\s*(?:[- ]?\d|v(?:ersion)?\.?\s*\d))?[- ]?multimer(?:[- ]?v?\.?\d+)?|"
        r"colabfold(?:_batch)?|af[23](?:[-‐‑–— ]?multimer)?(?:[-‐‑–— ]?server)?)"
    )
    patterns = (
        rf"\b(?:we|authors|study)\b.{{0,60}}\b(?:predicted|generated|created|constructed|calculated|computed|performed|modeled|modelled|folded)\b.{{0,100}}\b(?:using|with|via)\b.{{0,30}}{model}",
        rf"\b(?:we|authors|study)\b.{{0,60}}\b(?:ran|run|executed|running)\s+(?:the\s+)?{model}",
        rf"\b(?:is|are|was|were)\b.{{0,45}}\b(?:predicted|generated|created|constructed|calculated|computed|obtained|modeled|modelled|folded|run|performed)\b.{{0,100}}\b(?:by|on|using|with|via)\b.{{0,80}}{model}",
        # Common passive Methods wording uses the prediction/model as the
        # grammatical subject: "Structural predictions were done with
        # ColabFold" or "the models were made using AlphaFold2".  These are
        # explicit procedures, not merely adjectival "AF-predicted" origins.
        rf"\b(?:predictions?|structures?|models?|complexes?)\b.{{0,45}}\b(?:is|are|was|were)\s+(?:done|made|performed|generated|created|constructed|calculated|computed|modeled|modelled|predicted)\b.{{0,60}}\b(?:by|on|using|with|via)\b.{{0,50}}{model}",
        rf"{model}.{{0,70}}\b(?:is|are|was|were)\s+(?:accessed|run|used)\b.{{0,45}}\bto\s+(?:predict|generate|create|construct|calculate|compute|model|fold)",
        rf"{model}.{{0,55}}\b(?:generated|produced|calculated)\s+(?:the\s+)?(?:predictions?|structures?|models?|complexes?)\b",
        rf"\b(?:we|authors|study)\b.{{0,35}}\b(?:use|used|utilize|utilized|employed|applied)\s+(?:the\s+)?(?:accessible\s+|online\s+|official\s+|public\s+)?{model}.{{0,55}}\b(?:to\s+(?:predict|generate|model|compute|fold)|for\s+(?:all\s+)?predictions?)\b",
        # A named implementation plus explicit parameter configuration is a
        # reproducible execution statement even when the clipped evidence
        # quote omits a later "to predict" clause.
        rf"\b(?:we|authors|study)\b.{{0,35}}\b(?:used|utilized|employed|applied)\s+(?:the\s+)?{model}.{{0,70}}\b(?:parameters?|settings?)\b.{{0,35}}\b(?:configured|specified|set)\b",
        # Coordinated tools are common in Methods ("we applied X and AF2 to
        # design ...").  Requiring an attributable subject, an application
        # verb, the AF model, and a concrete downstream verb keeps this narrow.
        rf"\b(?:we|authors|study)\b.{{0,35}}\b(?:used|utilized|employed|applied|apply)\b.{{0,75}}{model}.{{0,55}}\bto\s+(?:predict|generate|create|construct|model|compute|fold|design)\b",
        # Some authors name the executable as a method rather than as a model:
        # "We apply this AlphaFold2 multimer based method ...".
        rf"\b(?:we|authors|study)\b.{{0,35}}\b(?:used|employed|applied|apply)\s+(?:this|the|our)\s+{model}.{{0,45}}\b(?:method|pipeline|server|implementation|environment)\b",
        rf"\b(?:we|our|authors|study)\b.{{0,80}}\busing\s+(?:the\s+)?{model}.{{0,45}}\bto\s+(?:predict|generate|model|compute|fold)\b",
        rf"\b(?:using|with|via)\s+(?:the\s+)?{model}.{{0,70}}\b(?:we|authors)\b.{{0,35}}\b(?:predicted|generated|created|constructed|calculated|computed|modeled|modelled|folded)\b",
        rf"\b(?:we|authors|study)\b.{{0,35}}\b(?:give|gave|input|provided|submit|submitted)\b.{{0,100}}\b(?:as\s+input\s+)?(?:to|into|on)\s+(?:the\s+)?{model}",
        rf"\b(?:sequences?|proteins?|structures?|models?)\b.{{0,70}}\b(?:is|are|was|were)\s+(?:submitted|input|provided)\s+(?:to|into|on)\s+(?:the\s+)?{model}",
        # Passive Methods wording such as "sequences are subjected to
        # structural modeling using AlphaFold2" also establishes execution.
        rf"\b(?:sequences?|proteins?|targets?|entries?)\b.{{0,70}}\b(?:is|are|was|were)\s+subjected\s+to\s+(?:structural\s+)?(?:modeling|modelling|prediction).{{0,40}}\b(?:using|with|via)\b.{{0,30}}{model}",
        rf"\bto\s+(?:predict|generate|model|fold)\b.{{0,100}}\b(?:we|authors)\b.{{0,50}}\b(?:use|used|employed|applied)\b.{{0,100}}\bbased\s+on\s+{model}",
        rf"\b(?:simulations?|predictions?|models?|structures?)\b.{{0,55}}\b(?:was|were)\s+run\s+using\s+(?:the\s+)?command.{{0,100}}{model}",
        # A complete structure-prediction procedure that gives the actual
        # ColabFold executable is stronger evidence than a clipped "modeled
        # using ColabFold" fragment, even when the prose omits "was run".
        rf"\b(?:structure\s+)?prediction\b.{{0,100}}\b(?:using|with)\b.{{0,120}}{model}",
        rf"(?:使用|运行|利用).{{0,20}}{model}.{{0,35}}(?:预测|生成|建模)",
    )
    if any(re.search(pattern, text, re.I) for pattern in patterns):
        return True
    # Some Methods sections identify the product and implementation together,
    # e.g. "input into AlphaFold2 (ColabFold v1.5.2)".  Count that as a
    # ColabFold run only when a complete AlphaFold procedure is present and the
    # parenthetical explicitly aliases AlphaFold2 to ColabFold.  A later
    # comparison with ColabFold was removed above and therefore cannot pass.
    if colabfold_only and re.search(
        r"alpha\s*fold\s*[- ]?2\s*\(\s*colabfold\b", text, re.I
    ):
        return explicit_run_quote(text, colabfold_only=False)
    return False


def substantive_docking_or_screening_quote(text: str) -> bool:
    """Separate molecular/interaction docking from cryo-EM density fitting."""
    normalized = " ".join(text.split())
    return bool(AF_TERM.search(normalized) and MOLECULAR_DOCKING_OR_SCREENING.search(normalized))


def af_evaluation_signal(text: str) -> bool:
    """Recognize explicit evaluation of AF predictions used by the study."""
    normalized = " ".join(text.split())
    if not AF_TERM.search(normalized):
        return False
    if AF_EVALUATION.search(normalized):
        return True
    return bool(re.search(r"\bwe compared our\b", normalized, re.I))


def semantic_errors(review: dict[str, Any], packet: dict[str, Any]) -> list[str]:
    """Check explicit contradictions/proof links, not unobservable ground truth."""
    errors: list[str] = []
    primary = review["primary_label"]
    if primary in KNOWN_LABELS:
        actual = tuple(review[key] for key in (
            "relevance_level", "af_related_label", "af_use_label", "adoption_eligible"
        ))
        if actual != KNOWN_LABELS[primary]:
            errors.append(f"semantic: {primary} requires R/relation/use/adoption={KNOWN_LABELS[primary]}")
    if primary == "uncertain" and review["relevance_level"] != "RU":
        errors.append("semantic: uncertain primary label requires RU, not a guessed R0-R4")
    if review["relevance_level"] == "RU" and primary != "uncertain":
        errors.append("semantic: RU requires primary_label=uncertain")
    if review["af_related_label"] == "uncertain" and review["relevance_level"] != "RU":
        errors.append("semantic: unknown AF relationship requires RU")
    if review["af_use_label"] == "yes" and review["af_related_label"] != "related":
        errors.append("semantic: actual AF use requires an established AF relationship")
    if review["adoption_eligible"] == "yes" and review["af_use_label"] != "yes":
        errors.append("semantic: adoption=yes requires use=yes")
    if review["future_or_hypothetical_only"] and review["af_use_label"] == "yes":
        errors.append("semantic: future/hypothetical-only evidence cannot establish actual use")
    if bool(review["human_review_reasons"]) != review["needs_human_review"]:
        errors.append("semantic: human review flag and nonempty reasons must agree")
    must_review = primary == "uncertain" or review["evidence_level"] in {"E0", "E1"}
    must_review |= packet["evidence_tier"] == "abstract_only" and review["af_use_label"] == "yes"
    if must_review and not review["needs_human_review"]:
        errors.append("semantic: uncertainty, E0/E1, and abstract-only use require human review")

    evidence = review["evidence"]
    material = packet["input_material"]
    texts = [material.get("title") or "", material.get("abstract") or ""]
    texts.extend(block.get("text") or "" for block in material.get("evidence_blocks", []))
    af_signal = any(AF_TERM.search(text) for text in texts) or bool(material.get("matched_seed_references"))
    if not af_signal and review["af_related_label"] in {"related", "background"}:
        errors.append("semantic: supplied material has no explicit AF signal or matched AF reference; do not invent a positive relationship")
    if review["evidence_level"] == "E3":
        body_indices = {b["index"] for b in material.get("evidence_blocks", []) if body_block(b)}
        if not any(e["source_kind"] == "fulltext_block" and e["block_index"] in body_indices for e in evidence):
            errors.append("semantic: E3 requires a quoted full-text body block, not a title/abstract/bibliography alone")
    if review["af_use_label"] == "yes":
        if review["evidence_level"] in {"E0", "E1"}:
            errors.append("semantic: E0/E1 cannot establish actual use")
        if not any(e["source_kind"] != "matched_reference" and
                   set(e["supports"]) & {"use", "engagement"} for e in evidence):
            errors.append("semantic: actual use requires non-bibliographic use evidence")

    actions = set(review["observed_actions"])
    if "none" in actions and len(actions) > 1:
        errors.append("semantic: none cannot coexist with observed actions")
    if "discussion_only" in actions and actions & USE_ACTIONS:
        errors.append("semantic: discussion_only cannot coexist with actual-use actions")
    if actions & USE_ACTIONS and review["af_use_label"] != "yes":
        errors.append("semantic: actual-use actions require use=yes")
    if review["adoption_eligible"] == "yes" and not actions & USE_ACTIONS:
        errors.append("semantic: downstream adoption requires at least one evidenced actual-use action")
    if actions & {"modified_or_extended", "developed_downstream_tool"} and primary != "method_development":
        errors.append(
            "semantic: modified_or_extended or developed_downstream_tool requires "
            "primary_label=method_development and relevance_level=R4"
        )
    if primary == "method_development" and not actions & {
        "benchmarked_or_evaluated", "modified_or_extended", "developed_downstream_tool"
    }:
        errors.append(
            "semantic: method_development/R4 requires evidenced systematic evaluation, "
            "modification/extension, or downstream method/tool development"
        )
    if primary == "model_application" and not actions & {"ran_alphafold", "ran_colabfold", "retrieved_precomputed_structure"}:
        if "prediction_origin_unclear" not in review["human_review_reasons"]:
            errors.append("semantic: model application with unestablished prediction origin must flag prediction_origin_unclear; retain supported use without inventing execution")
    action_links = review["action_evidence"]
    linked_actions = [item["action"] for item in action_links]
    if len(linked_actions) != len(set(linked_actions)) or set(linked_actions) != actions - {"none"}:
        errors.append("semantic: action_evidence must link each non-none observed action exactly once")
    for item in action_links:
        indices = item["evidence_indices"]
        if any(index >= len(evidence) for index in indices):
            errors.append(f"semantic: {item['action']} refers to a nonexistent evidence index")
            continue
        quotes = [evidence[index] for index in indices]
        if item["action"] in USE_ACTIONS and not any(
            e["source_kind"] != "matched_reference" and set(e["supports"]) & {"use", "engagement"}
            for e in quotes
        ):
            errors.append(f"semantic: {item['action']} needs non-bibliographic use evidence")
        if item["action"] in {"ran_alphafold", "ran_colabfold"}:
            eligible_quotes = [e["quote"] for e in quotes if e["source_kind"] != "matched_reference"]
            if item["action"] == "ran_colabfold":
                eligible_quotes = [q for q in eligible_quotes if re.search(r"colabfold", q, re.I)]
            else:
                # ColabFold is an AF-technology use route, but the same procedure
                # must not be counted again as a separate native AlphaFold run.
                # A distinct AlphaFold run needs its own non-ColabFold excerpt.
                eligible_quotes = [q for q in eligible_quotes if not re.search(r"colabfold", q, re.I)]
            if not any(explicit_run_quote(q, colabfold_only=item["action"] == "ran_colabfold") for q in eligible_quotes):
                errors.append(f"semantic: {item['action']} lacks an explicit prediction/run procedure quote; using an AF-predicted structure is insufficient. Cite the procedure or omit the unproven run action and flag prediction_origin_unclear")
        if item["action"] == "docking_or_screening":
            eligible_quotes = [e["quote"] for e in quotes if e["source_kind"] != "matched_reference"]
            if not substantive_docking_or_screening_quote(" ".join(eligible_quotes)):
                errors.append(
                    "semantic: docking_or_screening requires molecular/ligand/protein-interaction "
                    "docking or virtual screening with an AF prediction; fitting or manually docking "
                    "a model into cryo-EM/electron density belongs only to integrated_empirical_workflow"
                )

    # Narrow omission warning: explicitly comparing OUR experimental structure
    # with AF and discussing failed/incorrect predictions is an evaluation.
    evaluation_present = any(af_evaluation_signal(text) for text in texts)
    if evaluation_present and review["af_use_label"] == "yes" and "benchmarked_or_evaluated" not in actions:
        errors.append(
            "semantic: explicit evaluation of this study's AF predictions is present "
            "(accuracy/quality/confidence/limitation); record benchmarked_or_evaluated with evidence "
            "(target-specific evaluation does not automatically require R4)"
        )
    return errors
