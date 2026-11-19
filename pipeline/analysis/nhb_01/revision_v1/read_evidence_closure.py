"""Print exact bounded local evidence for actual assisted reading, without decisions."""
import argparse
import json
from pathlib import Path
import re

from local_recall import MODULE, require, sha

TERMS = re.compile(r'alpha[\s‐‑–—-]*fold|aplha.?fold|colab.?fold|afdb|deepmind|a7d|senior|jumper', re.I)


def render(row, body=False):
    print('\nCASE', row['review_id'], row['work_id'], row['publication_year'], row['title'])
    print('DOI', row['doi'], 'DATE', row['publication_date'])
    seen = set()
    for a in row['abstract_variants']:
        print('ABSTRACT_SOURCE', a['source_kind'], a['quality']['structural_status'])
        if a['text'] in seen:
            print('[exact duplicate of previously printed abstract]')
        else:
            print(a['text'] or '[no text]'); seen.add(a['text'])
    print('LOOKUP', json.dumps(row['public_lookup'], ensure_ascii=False))
    if not body or not row['body_document_path']:
        return
    path = Path(row['body_document_path'])
    require(sha(path) == row['body_document_sha256'], 'Body changed')
    d = json.loads(path.read_text())
    print('BODY_PATH', path)
    print('SECTION_INVENTORY', [(i, s.get('title', ''), len(s['text']))
                                for i, s in enumerate(d['sections'])])
    for i, s in enumerate(d['sections']):
        hits = list(TERMS.finditer(s['text']))
        if not hits:
            print('SECTION_OPENING_ONLY', i, s.get('title', ''), s['text'][:600]); continue
        windows = []
        for h in hits:
            lo = max(0, h.start()-1300); hi = min(len(s['text']), h.end()+1700)
            if windows and lo <= windows[-1][1]:
                windows[-1][1] = max(hi, windows[-1][1])
            else:
                windows.append([lo, hi])
        for lo, hi in windows:
            print('SECTION_CONTEXT', i, s.get('title', ''), 'OFFSETS', lo, hi)
            print(s['text'][lo:hi])
    for i, context in enumerate(d.get('af1_citation_contexts', [])):
        print('AF1_CITATION', i, context['text'])
    print('READING_LIMIT: section inventory/openings and ALL detected AF contexts; NOT full body reading.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start', type=int, required=True)
    p.add_argument('--stop', type=int, required=True)
    p.add_argument('--route', choices=['all', 'not_individually_reviewed', 'reviewed_unknown_followup'], default='all')
    p.add_argument('--body', action='store_true')
    a = p.parse_args()
    rows = json.loads((MODULE / 'evidence_closure_preparation_v1/packets_private.json').read_text())
    if a.route != 'all': rows = [r for r in rows if r['prior_route'] == a.route]
    require(0 <= a.start < a.stop <= len(rows) and a.stop-a.start <= 30, 'Invalid bounded reading range')
    for row in rows[a.start:a.stop]: render(row, a.body)


if __name__ == '__main__': main()
