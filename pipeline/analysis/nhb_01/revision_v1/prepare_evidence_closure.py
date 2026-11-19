"""Freeze remaining candidates and current evidence; no semantic decisions or requests."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import tempfile

from assemble_semantic_review import packet_index
from fetch_public_evidence import inventory
from local_recall import MODULE, ROOT, destination, pin, require, sha, write_csv, write_json
from prepare_candidate_review import screen_abstract

ACCEPTED = MODULE / 'accepted_candidate_layer_v1'
PUBLIC = MODULE / 'public_evidence_v3'
OUT = MODULE / 'evidence_closure_preparation_v1'


def checked(directory):
    manifest = json.loads((directory / 'run_manifest.json').read_text())
    require(inventory(directory) == manifest['outputs'], 'Archive changed: ' + str(directory))
    return manifest


def assemble():
    checked(ACCEPTED)
    checked(PUBLIC)
    accepted_file = ACCEPTED / 'accepted_layer_private.json'
    layer = json.loads(accepted_file.read_text())
    require(layer['approval_status'] == 'accepted_by_user', 'No accepted upstream layer')
    unknown = [r for r in layer['decisions'] if r['af_use_label'] == 'uncertain']
    require(len(unknown) == 586 and len({r['work_id'] for r in unknown}) == 586,
            'Frozen remaining scope differs')
    csv.field_size_limit(2_000_000)
    with (PUBLIC / 'evidence_candidates_private.csv').open(newline='') as f:
        public = {r['work_id']: r for r in csv.DictReader(f)}
    packets = packet_index()
    sources = {accepted_file, ACCEPTED / 'run_manifest.json', PUBLIC / 'run_manifest.json',
               PUBLIC / 'evidence_candidates_private.csv',
               MODULE / 'candidate_review_v1/review_packets_private.json',
               ROOT / 'config/af_review_prompt_v4.txt', Path(__file__)}
    sources.update(MODULE.glob('body_assignments_round*_v1/part*_private.json'))
    results = []
    for prior in sorted(unknown, key=lambda r: (r['publication_year'], r['review_id'])):
        wid = prior['work_id']; row = public[wid]; original = packets[wid]
        require(int(row['publication_year']) == prior['publication_year'], 'Year identity changed')
        doc = original.get('body_document_path')
        if not doc and row['fulltext_status'] == 'verified_body':
            doc = str(PUBLIC / row['fulltext_document_path'])
        if doc:
            doc = Path(doc)
            require(doc.is_file() and doc.resolve().is_relative_to(MODULE), 'Invalid body source')
            if original.get('body_document_path'):
                require(sha(doc) == original['body_document_sha256'], 'Historical body changed')
            sources.add(doc)
        abstracts = []
        for kind, text, source in (
            ('local_abstract', row['abstract'], row['abstract_source']),
            ('public_abstract', row['public_abstract'], row['public_abstract_source'])):
            abstracts.append({'source_kind': kind, 'text': text, 'source': source,
                              'quality': screen_abstract(text, row['title'])})
        route = ('not_individually_reviewed' if prior['source_review'] ==
                 'explicit_pending_or_insufficient_evidence_route' else 'reviewed_unknown_followup')
        results.append({
            'schema': 'figure1-evidence-closure-packet-v1',
            'review_id': prior['review_id'], 'work_id': wid,
            'publication_year': prior['publication_year'], 'publication_date': row['publication_date'],
            'doi': row['doi'], 'title': row['title'], 'work_type': row['work_type'],
            'prior_route': route, 'prior_accepted_decision': prior,
            'abstract_variants': abstracts,
            'body_document_path': str(doc) if doc else None,
            'body_document_sha256': sha(doc) if doc else None,
            'public_lookup': {k: row[k] for k in (
                'metadata_status', 'metadata_title', 'metadata_year', 'metadata_date',
                'epmc_source', 'epmc_id', 'pmcid', 'fulltext_status', 'fulltext_source',
                'fulltext_access_class', 'fulltext_license')},
            'recall_signals': {k: row[k] == 'True' for k in
                               ('cites_af1', 'cites_existing_seed', 'keyword_hit', 'seed_self')},
            'existing_quality_flags': original.get('quality_flags', []),
            'semantic_review_status': 'pending_actual_reading',
            'independent_human_gold': False})
    summary = {
        'scope': 'all 586 previously accepted unknown candidates; AF, not AF-like',
        'queue_works': len(results),
        'prior_routes': dict(Counter(r['prior_route'] for r in results)),
        'by_year': dict(sorted(Counter(str(r['publication_year']) for r in results).items())),
        'body_available': sum(bool(r['body_document_path']) for r in results),
        'usable_abstract_available': sum(any(a['quality']['structural_status'] == 'usable'
                                            for a in r['abstract_variants']) for r in results),
        'actually_reviewed_this_stage': 0, 'requests': 0, 'paid_llm_calls': 0,
        'prior_routes_changed': False, 'final_figure_ready': False}
    require(summary['prior_routes'] == {'not_individually_reviewed': 430,
                                        'reviewed_unknown_followup': 156}, 'Prior routes differ')
    return results, summary, [pin(p) for p in sorted(sources)]


def verify(directory=OUT):
    manifest = checked(directory)
    for item in manifest['inputs']:
        require(sha(item['path']) == item['sha256'], 'Pinned source changed')
    packets = json.loads((directory / 'packets_private.json').read_text())
    require(len(packets) == 586, 'Queue coverage differs')
    ids = [r['work_id'] for r in packets]
    batches = [json.loads(p.read_text()) for p in sorted((directory / 'batches').glob('*.json'))]
    require([r['work_id'] for b in batches for r in b] == ids, 'Batch partition differs')
    require(all(r['semantic_review_status'] == 'pending_actual_reading' for r in packets),
            'Preparation must not certify semantic review')
    return manifest['summary']


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, default=OUT)
    p.add_argument('--verify-only', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args(argv)
    if a.verify_only:
        print('Closure queue integrity: PASS;', json.dumps(verify(a.output_dir), ensure_ascii=False))
        return
    rows, summary, pins = assemble()
    if a.dry_run:
        print('Read-only preparation:', json.dumps(summary, ensure_ascii=False)); return
    out = destination(a.output_dir)
    stage = Path(tempfile.mkdtemp(prefix='.evidence-closure-preparation-', dir=MODULE))
    stage.chmod(0o700); (stage / 'batches').mkdir()
    write_json(stage / 'packets_private.json', rows)
    write_json(stage / 'summary.json', summary)
    fields = ['review_id', 'work_id', 'publication_year', 'title', 'prior_route',
              'body_document_path', 'semantic_review_status']
    write_csv(stage / 'queue_private.csv', [{k: r[k] for k in fields} for r in rows], fields)
    for start in range(0, len(rows), 25):
        write_json(stage / 'batches' / f'batch_{start // 25 + 1:02d}_private.json', rows[start:start+25])
    write_json(stage / 'run_manifest.json', {
        'schema': 'figure1-evidence-closure-preparation-v1', 'inputs': pins,
        'summary': summary, 'outputs': inventory(stage)})
    verify(stage)
    stage.rename(out)
    print('Frozen closure queue + export verification: PASS;', json.dumps(summary, ensure_ascii=False))
    print('Queue:', out, '; semantic review NOT completed by preparation')


if __name__ == '__main__':
    main()
