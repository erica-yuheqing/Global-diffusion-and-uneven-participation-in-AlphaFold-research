"""Produce a bounded public-source proposal only; no downloads or source approvals."""
from collections import Counter
import json
from pathlib import Path
import re
import tempfile

from fetch_public_evidence import inventory, norm_doi
from local_recall import MODULE, destination, pin, require, write_csv, write_json
from prepare_evidence_closure import OUT, verify


def main():
    verify(OUT)
    rows = json.loads((OUT / 'packets_private.json').read_text())
    lookup = []
    for p in rows:
        no_abstract = not any(a['quality']['structural_status'] == 'usable' for a in p['abstract_variants'])
        doi = norm_doi(p['doi'])
        is_biorxiv = doi.startswith('10.1101/')
        if no_abstract: rank, why = 0, 'no_usable_abstract_any_year'
        elif p['publication_year'] == 2019 and is_biorxiv: rank, why = 1, 'early_baseline_preprint_body_and_version_identity'
        elif not p['body_document_path'] and is_biorxiv and p['publication_year'] <= 2021:
            rank, why = 2, 'early_main_preprint_body_and_version_identity'
        else: continue
        # arXiv and DataCite prefixes are disclosed, not blindly submitted to
        # Crossref and silently considered absent. They need a separate fallback.
        service = 'biorxiv' if is_biorxiv else 'crossref'
        if doi.startswith(('10.48550/','10.5281/','10.31219/')):
            service = 'outside_initial_provider_scope_requires_specific_fallback'
        lookup.append({'work_id': p['work_id'], 'review_id': p['review_id'],
                       'doi': doi, 'publication_year': p['publication_year'], 'title': p['title'],
                       'priority': rank, 'reason': why, 'primary_service': service,
                       'request_status': 'not_sent_pending_user_confirmation'})
    lookup.sort(key=lambda r: (r['priority'], r['publication_year'], r['review_id']))
    # Candidate existence is different from requests: initial bounded tranche.
    initial = lookup[:100]
    summary = {'proposed_max_http_sends_including_redirects_retries':200,
               'initial_work_targets':len(initial), 'initial_priority_counts':dict(Counter(r['reason'] for r in initial)),
               'initial_service_counts':dict(Counter(r['primary_service'] for r in initial)),
               'remaining_targets_outside_initial_tranche':max(0,len(lookup)-len(initial)),
               'approval_status':'pending_user_confirmation', 'http_sends':0, 'paid_llm_calls':0,
               'old_database_changed':False,
               'other_sources':'CASP13/AF1 dataset identity checked separately before any yes decision',
               'access_rules':'Only public metadata and returned authorized public text; no paywall bypass; redirects/retries count toward cap'}
    out = destination(MODULE / 'evidence_closure_lookup_plan_v1')
    stage = Path(tempfile.mkdtemp(prefix='.evidence-closure-lookup-plan-',dir=MODULE)); stage.chmod(0o700)
    write_json(stage / 'initial_targets_private.json', initial)
    write_json(stage / 'all_priority_targets_private.json', lookup)
    write_json(stage / 'summary.json', summary)
    write_csv(stage / 'initial_targets_private.csv', initial, list(initial[0]))
    write_json(stage / 'run_manifest.json', {'schema':'figure1-evidence-closure-lookup-proposal-v1',
        'inputs':[pin(OUT / 'packets_private.json'),pin(OUT / 'run_manifest.json'),pin(Path(__file__))],
        'summary':summary,'outputs':inventory(stage)})
    stage.rename(out)
    print('Public lookup PLAN only:',json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__': main()
