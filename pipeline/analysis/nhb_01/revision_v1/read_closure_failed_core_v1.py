"""Read failed positive suggestions; does not validate or accept them."""
import importlib.util
import json
from closure_execution_v3 import OUT
from evidence_closure_api_v1 import RUNNER, read_jsonl
from finish_closure_execution_v3 import INPUT


def main():
    spec = importlib.util.spec_from_file_location('failed_core_reader', RUNNER)
    engine = importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
    packets = {r['work_id']: r for r in read_jsonl(INPUT)}
    for model in ('a', 'b', 'c'):
        valid = {r['work_id'] for r in read_jsonl(OUT / f'model_{model}_closure_v3.jsonl')}
        for row in read_jsonl(OUT / f'model_{model}_closure_v3.attempts.jsonl'):
            if row.get('event') != 'request_finished' or row['work_id'] in valid:
                continue
            try:
                response = engine.parse_json_object(row.get('visible_response_text') or '')
            except (ValueError, TypeError):
                continue
            if response.get('af_use_label') != 'yes':
                continue
            print(json.dumps({'model': model, 'work_id': row['work_id'],
                'title': packets[row['work_id']]['input_material']['title'],
                'core': {k: response.get(k) for k in ('af_use_label', 'adoption_eligible',
                    'relevance_level', 'evidence_level', 'primary_label')},
                'evidence': response.get('evidence'), 'reason': response.get('reasoning_summary')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
