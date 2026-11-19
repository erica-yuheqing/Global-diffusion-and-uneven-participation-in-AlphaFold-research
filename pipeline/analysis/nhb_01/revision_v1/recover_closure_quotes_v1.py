"""Offline quotation-format candidates, separate from API validation/acceptance."""
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from evidence_closure_api_v1 import RUNNER, SCHEMA, read_jsonl, fingerprint
from closure_execution_v3 import OUT as EXECUTION
from finish_closure_execution_v3 import INPUT, load
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, pin, require, write_json

OUT = MODULE / 'evidence_closure_local_candidates_v1'
TRANSLATE = str.maketrans({'‐': '-', '‑': '-', '–': '-', '−': '-',
                          '’': "'", '‘': "'", '“': '"', '”': '"'})


def indexed_normalize(text):
    normalized = []; spans = []
    for index, char in enumerate(text):
        char = ' ' if char.isspace() else char.translate(TRANSLATE)
        if char == ' ' and normalized and normalized[-1] == ' ':
            spans[-1] = (spans[-1][0], index + 1)
        else:
            normalized.append(char); spans.append((index, index + 1))
    return ''.join(normalized), spans


def restored_quote(quote, sources):
    needle = indexed_normalize(quote)[0].strip()
    if not needle:
        return None
    matches = set()
    for source in sources:
        text, spans = indexed_normalize(source)
        start = 0
        while True:
            position = text.find(needle, start)
            if position < 0:
                break
            restored = source[spans[position][0]:spans[position + len(needle) - 1][1]]
            if len(restored.split()) <= 25:
                matches.add(restored)
            start = position + 1
    return matches.pop() if len(matches) == 1 else None


def repair(response, packet, engine, validator):
    candidate = copy.deepcopy(response); changes = []
    if 'action_evidence' not in candidate and candidate.get('observed_actions') == ['none']:
        candidate['action_evidence'] = []
        changes.append({'field': 'action_evidence', 'operation': 'empty_links_for_explicit_none_only'})
    for index, evidence in enumerate(candidate.get('evidence', [])):
        if not isinstance(evidence, dict) or not isinstance(evidence.get('quote'), str):
            continue
        sources = engine.exact_source_texts(packet, evidence)
        if any(evidence['quote'] in source for source in sources):
            continue
        quote = restored_quote(evidence['quote'], sources)
        if quote is not None:
            changes.append({'field': f'evidence[{index}].quote', 'old': evidence['quote'], 'new': quote,
                            'operation': 'same_declared_source_whitespace_or_typographic_restoration'})
            evidence['quote'] = quote
    # No clipped quotations, word substitutions, source-index changes, action
    # deletion, enum translation, or alteration of core adoption conclusions.
    errors = engine.validate_review(candidate, packet, validator)
    return candidate if changes and not errors else None, changes, errors


def main():
    packets = {p['work_id']: p for p in read_jsonl(INPUT)}
    spec = importlib.util.spec_from_file_location('closure_quote_original_engine', RUNNER)
    engine = importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
    validator = Draft202012Validator(json.loads(SCHEMA.read_text()))
    candidates = []; unresolved = []; pins = [pin(INPUT), pin(Path(__file__))]
    valid_counts = {}
    for model in ('a', 'b', 'c'):
        valid, source_pins = load(model, packets); pins += source_pins
        valid_counts[model] = len(valid)
        path = EXECUTION / f'model_{model}_closure_v3.attempts.jsonl'
        if not path.is_file():
            continue
        pins.append(pin(path))
        latest = {}
        for event in read_jsonl(path):
            if event.get('event') == 'request_finished' and event.get('http_status') == 200:
                latest[event['work_id']] = event
        for wid, event in latest.items():
            if wid in valid:
                continue
            packet = packets[wid]
            try:
                original = engine.parse_json_object(event.get('visible_response_text') or '')
                candidate, changes, errors = repair(original, packet, engine, validator)
            except (ValueError, TypeError, KeyError) as error:
                unresolved.append({'model': model, 'work_id': wid, 'reason': str(error)[:300]})
                continue
            if candidate is None:
                unresolved.append({'model': model, 'work_id': wid, 'remaining_errors': errors})
                continue
            require(all(original.get(k) == candidate.get(k) for k in
                ('primary_label', 'relevance_level', 'evidence_level', 'af_related_label',
                 'af_use_label', 'adoption_eligible', 'observed_actions')), 'Non-mechanical change')
            candidates.append({'model': model, 'work_id': wid, 'input_packet_sha256': fingerprint(packet),
                'original_response': original, 'candidate_response': candidate, 'changes': changes,
                'source_attempt_number': event['attempt_number'], 'source_run_id': event['run_id'],
                'source_visible_text_sha256': fingerprint(event['visible_response_text']),
                'semantic_status': 'pending_assistant_evidence_review_and_user_acceptance',
                'API_validation_credit': False, 'resume_credit': False})
    out = destination(OUT); out.mkdir(mode=0o700)
    write_json(out / 'candidates_private.json', candidates)
    write_json(out / 'unresolved_private.json', unresolved)
    summary = {'original_API_valid_unchanged': valid_counts, 'strict_local_format_candidates': len(candidates),
        'by_model': dict(Counter(r['model'] for r in candidates)), 'unrecovered_parsed_attempts': len(unresolved),
        'accepted_new_labels': 0, 'API_calls': 0, 'old_outputs_changed': False}
    write_json(out / 'summary.json', summary)
    write_json(out / 'run_manifest.json', {'schema': 'closure-local-format-candidates-v1',
        'inputs': pins, 'summary': summary, 'outputs': inventory(out)})
    print('Local format candidate archive:', summary, flush=True)


if __name__ == '__main__':
    main()
