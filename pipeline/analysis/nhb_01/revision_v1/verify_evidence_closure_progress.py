"""Validate literal review notes and exact coverage, never approve semantic choices."""
from collections import Counter
import argparse
import json
from pathlib import Path

from local_recall import MODULE, require, sha, write_json
from prepare_evidence_closure import OUT, verify


def validate_row(row, packet):
    require(row['review_id'] == packet['review_id'] and row['work_id'] == packet['work_id'], 'Review identity differs')
    require(row['publication_year'] == packet['publication_year'], 'Review year differs')
    require(row['review_status'] == 'pending_user_acceptance' and row['independent_human_gold'] is False,
            'A proposal cannot certify acceptance/gold')
    require(row['af_use_label'] in ('yes','no','uncertain') and
            row['adoption_eligible'] in ('yes','no','uncertain'), 'Invalid label')
    require(row['reviewer_id'] == 'root_assisted_evidence_closure', 'Only current assistant authorized')
    require(bool(row['reasoning_zh']) and bool(row['reading_scope']), 'Missing substantive notes/scope')
    if row['af_use_label'] == 'uncertain':
        require(row['relevance_level'] == 'RU' and bool(row['unknown_reason']), 'Unknown reason missing')
    if row['af_use_label'] == 'yes':
        require(row['evidence_level'] in ('E2','E3') and bool(row['evidence']), 'Use requires explicit evidence')
    scope = row['reading_scope']
    require(set(scope['abstract_variants_actually_read']) == {'local_abstract','public_abstract'},
            'Both available abstract variants must be accounted for')
    if scope['body_actually_read']:
        require(packet['body_document_path'] and row['source_body_sha256'] == packet['body_document_sha256'],
                'Body reading source differs')
    d = None
    for ev in row['evidence']:
        q = ev['quote']; require(bool(q) and len(q.split()) <= 25, 'Quote word bound differs')
        if ev['source_kind'] in ('local_abstract','public_abstract'):
            text = next(a['text'] for a in packet['abstract_variants'] if a['source_kind'] == ev['source_kind'])
        elif ev['source_kind'] == 'fulltext_body_section':
            require(scope['body_actually_read'], 'Body evidence without declared body reading')
            if d is None:
                require(sha(packet['body_document_path']) == packet['body_document_sha256'], 'Body changed')
                d = json.loads(Path(packet['body_document_path']).read_text())
            i = ev['section_index']; require(type(i) is int and 0 <= i < len(d['sections']), 'Bad body section')
            text = d['sections'][i]['text']
        else:
            raise ValueError('Unknown evidence source')
        require(q in text, 'Nonliteral quote: ' + row['work_id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save-report', action='store_true')
    args = parser.parse_args()
    verify(OUT)
    packets = {p['work_id']: p for p in json.loads((OUT / 'packets_private.json').read_text())}
    seen = {}; sources = []
    for path in sorted(MODULE.glob('evidence_closure_reviews_[0-9][0-9][0-9]_v1.json')):
        sources.append({'path': str(path), 'sha256': sha(path)})
        for row in json.loads(path.read_text()):
            require(row['work_id'] not in seen, 'Duplicate active review; use a supersession layer')
            validate_row(row, packets[row['work_id']]); seen[row['work_id']] = row
    changed = [wid for wid, row in seen.items() if any(
        row[k] != packets[wid]['prior_accepted_decision'][k]
        for k in ('af_use_label','adoption_eligible','primary_label','relevance_level'))]
    report = {'scope': 586, 'individual_checks_done': len(seen), 'remaining_actual_checks': 586-len(seen),
              'closure_status_counts': dict(Counter(r['closure_status'] for r in seen.values())),
              'new_semantic_proposals_pending_acceptance': len(changed),
              'all_candidate_review_complete': len(seen) == 586,
              'accepted_new_layer': False, 'final_figure_updated': False,
              'independent_human_gold': False, 'sources': sources}
    if args.save_report:
        write_json(MODULE / 'evidence_closure_progress_001_v1.json', report)
    print('Review progress/literal links: PASS;', json.dumps(report, ensure_ascii=False))


if __name__ == '__main__': main()
