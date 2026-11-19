"""Read-only numeric, source, candidate, archive and portable-navigation checks."""
import json
from pathlib import Path
import pandas as pd
from local_recall import MODULE, require, sha
from build_closure_reading_package_v3 import SOURCE, OUT, check_inventory, checked_zip, links_ok
from accept_closure_layer_v2 import verify as verify_acceptance
from verify_revised_country_bundle import verify as verify_analysis


def main():
    layer=verify_acceptance();s=verify_analysis(SOURCE);check_inventory(OUT)
    manifest=json.loads((OUT/'run_manifest.json').read_text())
    for p in manifest['inputs']:require(sha(Path(p['path']))==p['sha256'],'Package source changed')
    old=pd.read_csv(MODULE/'figure1_revision_final_v1/annual_counts.csv').set_index('publication_year')
    new=pd.read_csv(OUT/'tables/annual_counts.csv').set_index('publication_year')
    delta=new.confirmed_af-old.confirmed_af
    require(delta.to_dict()=={y:(1 if y in [2023,2024,2025] else 0) for y in delta.index},'Unexpected adoption changes')
    routes=pd.read_csv(OUT/'tables/candidate_routes.csv')
    counts=routes.groupby(['af_use_label','adoption_eligible']).size().to_dict()
    require(counts=={('yes','yes'):74,('no','no'):159,('yes','no'):1,('uncertain','uncertain'):531},'Route totals differ')
    require(len(routes)==765 and routes.work_id.nunique()==765,'Route identities differ')
    require('source_review' not in routes and 'quote' not in routes,'Private source text must not be shared')
    checks=json.loads((OUT/'release_checks.json').read_text())
    require(links_ok(OUT)==checks['portable_local_links_checked'],'Portable links differ')
    require(checked_zip(OUT.with_suffix('.zip'),OUT)==54,'Release inventory differs')
    registry=json.loads((OUT/'claim_evidence_registry.json').read_text())
    require(registry['numeric_facts']['confirmed_AF_main']==s['confirmed_AF_main']==16414,'Main numerator differs')
    require(all((OUT/f).is_file() for files in registry['claims'].values() for f in files),'Missing claim evidence')
    require(not registry['submission_ready'] and not checks['independent_human_gold'] and
        not checks['other_NHB_sections_recomputed'] and not checks['old_database_changed'],'Release scope overclaim')
    require(len(layer['accepted_version_links'])==15,'Specific version scope differs')
    print('Closure release PASS: 765 accepted routes; main 16,414; exact +1 in 2023/2024/2025; 531 unknown retained.')
    print('ZIP 54 files / 86 local links / byte-identical; source locks and old accepted decisions preserved.')
    print('No new provider requests; original final/NHB02–05 unchanged; no global recall/gold/submission certification.')


if __name__=='__main__':main()
