"""Exact public version relations and temporal leads; never auto-merge labels."""
from collections import Counter
import json
import duckdb
from fetch_closure_public_v4 import title_sim
from fetch_public_evidence import inventory, norm_doi
from local_recall import MODULE, MASTER, destination, pin, require, sql_path, write_json

PUBLIC = MODULE / 'evidence_closure_public_v4'
OUT = MODULE / 'evidence_closure_version_audit_v1'
VERSION_RELATIONS = {'has-preprint', 'is-preprint-of', 'is-version-of', 'has-version'}


def relations(record):
    result = []
    if record.get('published_version_doi'):
        result.append((norm_doi(record['published_version_doi']), 'biorxiv_published_doi'))
    for kind, entries in (record.get('relations') or {}).items():
        if kind not in VERSION_RELATIONS:
            continue
        for entry in entries:
            if entry.get('id-type') == 'doi' and norm_doi(entry.get('id')):
                result.append((norm_doi(entry['id']), 'crossref_' + kind))
    for entry in (record.get('parsed_atom') or {}).get('entries', []):
        if norm_doi(entry.get('doi')):
            result.append((norm_doi(entry['doi']), 'arxiv_journal_doi'))
    return sorted(set(result))


def temporal(record, original):
    flags = []
    for entry in (record.get('parsed_atom') or {}).get('entries', []):
        published = (entry.get('published') or '')[:10]
        updated = (entry.get('updated') or '')[:10]
        if updated and published and updated != published:
            flags.append({'reason': 'latest_arxiv_abstract_not_initial_version',
                          'published': published, 'updated': updated,
                          'version': entry.get('version')})
    selected = (record.get('source_date') or '')[:10]
    original_date = str(original.get('publication_date') or '')[:10]
    if selected and original_date and selected != original_date:
        flags.append({'reason': 'source_version_date_differs_from_master_date',
                      'master_date': original_date, 'source_date': selected})
    return flags


def main():
    manifest = json.loads((PUBLIC / 'run_manifest.json').read_text())
    require(inventory(PUBLIC) == manifest['outputs'], 'Public evidence archive changed')
    records = json.loads((PUBLIC / 'results_private.json').read_text())
    originals = {r['work_id']: r for r in json.loads(
        (MODULE / 'evidence_closure_preparation_v1/packets_private.json').read_text())}
    accepted = json.loads((MODULE / 'accepted_candidate_layer_v1/accepted_layer_private.json').read_text())
    accepted_pairs = {frozenset(link['member_work_ids']) for link in accepted['accepted_version_links']}
    targets = sorted({doi for record in records for doi, _ in relations(record)})
    con = duckdb.connect()
    con.execute("SET threads=2; SET memory_limit='2GB'; SET preserve_insertion_order=false")
    con.execute('CREATE TEMP TABLE targets(doi VARCHAR)')
    con.executemany('INSERT INTO targets VALUES (?)', [(doi,) for doi in targets])
    rows = con.execute(f'''SELECT m.work_id,m.title,m.publication_year,
            CAST(m.publication_date AS VARCHAR) AS publication_date,m.work_type,
            m.af_use_label,m.adoption_eligible,t.doi
        FROM read_parquet({sql_path(MASTER)}) m JOIN targets t
        ON lower(regexp_replace(m.doi,'^https?://(dx\\.)?doi.org/',''))=t.doi
        ORDER BY t.doi,m.work_id''').fetchall()
    fields = ['work_id', 'title', 'publication_year', 'publication_date', 'work_type',
              'af_use_label', 'adoption_eligible', 'doi']
    matches = {}
    for values in rows:
        row = dict(zip(fields, values)); matches.setdefault(row['doi'], []).append(row)
    leads = []; timing = []
    for record in records:
        wid = record['work_id']; original = originals[wid]
        flags = temporal(record, original)
        if flags:
            timing.append({'work_id': wid, 'title': original['title'], 'flags': flags,
                           'decision': 'pending_version_specific_evidence_review_not_date_replacement'})
        for doi, basis in relations(record):
            candidates = [r for r in matches.get(doi, []) if r['work_id'] != wid]
            for other in candidates or [None]:
                already = bool(other and any({wid, other['work_id']} <= pair for pair in accepted_pairs))
                leads.append({'work_id': wid, 'title': original['title'],
                    'source_date': original['publication_date'], 'linked_doi': doi, 'basis': basis,
                    'target': other, 'title_similarity': title_sim(original['title'], other['title']) if other else None,
                    'already_accepted_version_group': already,
                    'status': 'already_accepted_same_study_link_labels_not_propagated' if already else
                              'pending_same_study_and_representative_date_review',
                    'automatic_merge': False})
    con.close()
    out = destination(OUT); out.mkdir(mode=0o700)
    write_json(out / 'version_leads_private.json', leads)
    write_json(out / 'temporal_leads_private.json', timing)
    summary = {'exact_public_relation_leads': len(leads), 'lead_works': len({r['work_id'] for r in leads}),
        'already_accepted_leads': sum(r['already_accepted_version_group'] for r in leads),
        'relations_without_local_target': sum(r['target'] is None for r in leads),
        'temporal_review_works': len(timing), 'relation_sources': dict(Counter(r['basis'] for r in leads)),
        'new_version_approvals': 0, 'automatic_merges': 0, 'labels_propagated': 0}
    write_json(out / 'summary.json', summary)
    write_json(out / 'run_manifest.json', {'schema': 'closure-version-temporal-leads-v1',
        'inputs': [pin(MASTER), pin(PUBLIC / 'run_manifest.json'), pin(Path(__file__)),
                   pin(MODULE / 'accepted_candidate_layer_v1/accepted_layer_private.json')],
        'summary': summary, 'outputs': inventory(out)})
    print('Exact version and temporal audit saved:', summary, flush=True)


from pathlib import Path
if __name__ == '__main__':
    main()
