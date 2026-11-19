"""Read all abstract-only packets with explicit AF-family names, not approvals."""
import json
from evidence_closure_api_v1 import read_jsonl
from finish_closure_execution_v3 import INPUT
from read_closure_semantic_cases_v1 import AF


def main():
    rows = [r for r in read_jsonl(INPUT) if r['evidence_tier'] == 'abstract_only']
    hits = []
    for row in rows:
        material = row['input_material']
        if AF.search(material['title'] + ' ' + (material.get('abstract') or '')):
            hits.append({'work_id': row['work_id'], 'input_material': material})
    print(json.dumps({'abstract_packets': len(rows), 'explicit_name_hits': len(hits),
        'no_name_not_nonuse': True}))
    for row in hits:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == '__main__':
    main()
