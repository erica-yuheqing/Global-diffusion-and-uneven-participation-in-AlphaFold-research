"""Bounded evidence reading aid, not automatic semantic approval."""
import argparse
import json
import re
from evidence_closure_api_v1 import read_jsonl
from finish_closure_execution_v3 import INPUT, REPORT

AF = re.compile(r'alpha[\s-]*fold|colab[\s-]*fold|alpha[\s-]*missense|\bA7D\b', re.I)


def passage(text, span, radius=260):
    return text[max(0, span[0] - radius):min(len(text), span[1] + radius)]


def card(row, packet):
    response = row.get('candidate_response') or {}
    body = []
    for block in packet['input_material'].get('evidence_blocks', []):
        matches = list(AF.finditer(block['text']))
        if matches:
            body.append({'index': block['index'], 'section': block['section'],
                         'mentions': len(matches),
                         'passages': [passage(block['text'], match.span()) for match in matches[:10]]})
    return {'work_id': row['work_id'], 'title': packet['input_material']['title'],
        'year': packet['input_material'].get('publication_year'),
        'tier': packet['evidence_tier'], 'source': row.get('candidate_source'),
        'core': {k: response.get(k) for k in ('af_use_label', 'adoption_eligible',
            'relevance_level', 'evidence_level', 'primary_label')},
        'model_evidence': response.get('evidence'), 'reason': response.get('reasoning_summary'),
        'flags': response.get('human_review_reasons'), 'body_AF_passages': body,
        'reading_limit': 'Only displayed passages have been read here; absence in this aid is not whole-document non-use evidence.'}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--scope', choices=('body_negative', 'body_uncertain', 'body_unresolved', 'all', 'uncertain'), default='body_negative')
    p.add_argument('--start', type=int, default=0); p.add_argument('--count', type=int, default=12)
    p.add_argument('--work-id', action='append', default=[])
    p.add_argument('--compact', action='store_true')
    p.add_argument('--full', action='store_true')
    args = p.parse_args()
    packets = {r['work_id']: r for r in read_jsonl(INPUT)}
    rows = json.loads((REPORT / 'candidate_proposals_private.json').read_text())
    if args.work_id:
        rows = [r for r in rows if r['work_id'] in args.work_id]
    elif args.scope == 'body_negative':
        rows = [r for r in rows if r['evidence_tier'] == 'fulltext_evidence' and
                (r.get('candidate_response') or {}).get('af_use_label') == 'no']
    elif args.scope == 'uncertain':
        rows = [r for r in rows if (r.get('candidate_response') or {}).get('af_use_label') == 'uncertain']
    elif args.scope == 'body_uncertain':
        rows = [r for r in rows if r['evidence_tier'] == 'fulltext_evidence' and
                (r.get('candidate_response') or {}).get('af_use_label') == 'uncertain']
    elif args.scope == 'body_unresolved':
        rows = [r for r in rows if r['evidence_tier'] == 'fulltext_evidence' and
                not r.get('candidate_response')]
    print(json.dumps({'scope_count': len(rows), 'start': args.start}, ensure_ascii=False))
    for row in rows[args.start:args.start + args.count]:
        value = card(row, packets[row['work_id']])
        if args.full:
            value['input_material'] = packets[row['work_id']]['input_material']
        if args.compact:
            value.pop('reason', None); value.pop('model_evidence', None)
            value.pop('reading_limit', None)
        print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
