"""Bounded read-only evidence cards for the current assistant, not adjudication."""
import argparse
import json
import re
from evidence_closure_api_v1 import read_jsonl
from local_recall import MODULE
from finish_closure_execution_v3 import INPUT
from closure_execution_v3 import OUT

AF = re.compile(r'alpha\s*fold|alphfold|colabfold|alphamissense|DeepMind|Senior.{0,35}2020|Jumper.{0,35}2021', re.I)


def card(packet, response):
    material = packet['input_material']
    body = []
    for block in material.get('evidence_blocks', []):
        text = block.get('text') or ''
        chunks = []
        for match in list(AF.finditer(text))[:12]:
            left = max(0, match.start() - 260); right = min(len(text), match.end() + 420)
            chunks.append(text[left:right])
        if chunks:
            body.append({'index': block['index'], 'section': block.get('section'),
                         'AF_contexts': chunks, 'full_source_characters': len(text)})
    return {'work_id': packet['work_id'], 'title': material.get('title'),
            'abstract': material.get('abstract'), 'evidence_tier': packet['evidence_tier'],
            'response': response, 'body_AF_contexts': body,
            'references': material.get('matched_seed_references'),
            'limitation': 'Bounded context is a reading aid, not proof of whole-paper absence; full frozen packet remains the source.'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--model', choices=('a','b','c'), default='c')
    parser.add_argument('--selector', choices=('positive','negative','uncertain','all'), default='positive')
    parser.add_argument('--start', type=int, default=0); parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--work-id', action='append', default=[])
    args = parser.parse_args()
    packets = {r['work_id']: r for r in read_jsonl(INPUT)}
    path = OUT / f'model_{args.model}_closure_v3.jsonl'
    rows = read_jsonl(path) if path.is_file() else []
    selected = []
    for row in rows:
        response = row['response']; label = response['af_use_label']
        if args.work_id and row['work_id'] not in args.work_id:
            continue
        if not args.work_id and args.selector != 'all' and label != {
                'positive':'yes', 'negative':'no', 'uncertain':'uncertain'}[args.selector]:
            continue
        selected.append(row)
    print(json.dumps({'selected_total':len(selected), 'start':args.start,
        'cards':[card(packets[r['work_id']], r['response']) for r in
                 selected[args.start:args.start + args.count]]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
