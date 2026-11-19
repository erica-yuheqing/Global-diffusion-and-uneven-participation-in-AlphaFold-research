"""Read-only verification of the new offline recall bundle; no semantic certification."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from local_recall import MODULE, ROOT, regular, require, sha


def verify(directory, recheck_sources=True):
    directory=Path(directory).absolute()
    require(not directory.is_symlink() and directory.resolve().is_relative_to(MODULE), 'Unapproved bundle')
    m=json.loads(regular(directory/'run_manifest.json',MODULE).read_text())
    expected=m['outputs']
    actual={p.name for p in directory.iterdir() if p.is_file() and p.name!='run_manifest.json' and p.name!='.DS_Store'}
    require(actual==set(expected),'Bundle inventory differs')
    for name,pin in expected.items():
        f=regular(directory/name,MODULE)
        require(sha(f)==pin['sha256'] and f.stat().st_size==pin['size_bytes'],'Output bytes differ')
    if recheck_sources:
        for pin in m['inputs']:
            p=Path(pin['path']);root=ROOT if p.is_relative_to(ROOT) else p.parent
            require(sha(regular(p,root))==pin['sha256'],'Source bytes differ since recall audit')
    with (directory/'candidate_review_private.csv').open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    require(len(rows)<=100000,'Queue cap exceeded')
    require(len({r['work_id'] for r in rows})==len(rows),'Duplicate queue works')
    require(all(r['candidate_reviewed']=='False' and not r['af_use_label'] and
                not r['adoption_eligible'] and r['review_status']=='pending_evidence_review' for r in rows),
            'New candidate states must remain unreviewed, with blank decisions')
    eligible=[r for r in rows if r['document_eligible']=='True']
    s=json.loads((directory/'summary.json').read_text())
    require(s==m['summary'],'Summary/manifest mismatch')
    require(s['new_candidates_all_types']==len(rows) and s['new_candidates_eligible']==len(eligible), 'Queue counts differ')
    require(s['by_year_eligible']==dict(sorted(Counter(r['publication_year'] for r in eligible).items())), 'Annual counts differ')
    require(s['evidence_routes_eligible']==dict(Counter(r['evidence_route'] for r in eligible)), 'Evidence counts differ')
    require(s['year2020_eligible']==sum(r['publication_year']=='2020' for r in eligible), '2020 count differs')
    require(s['api_calls']==0 and s['llm_calls']==0 and s['af_labels_changed']==0 and
            s['ready_for_final_revised_figure'] is False,'Invalid readiness or mutation claim')
    for key,n in s['overlapping_signals_eligible'].items():
        require(n==sum(r[key]=='True' for r in eligible),'Signal counts differ')
    return s


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',type=Path,default=MODULE/'recall_audit_v1')
    a=p.parse_args(argv);s=verify(a.input_dir)
    print(f"Recall archive/reconstruction PASS; eligible candidates: {s['new_candidates_eligible']}; 2020: {s['year2020_eligible']}")
    print('Candidate identity/evidence presence only; no use-label or semantic approval; final revised figure not ready')
    return 0


if __name__=='__main__':raise SystemExit(main())
