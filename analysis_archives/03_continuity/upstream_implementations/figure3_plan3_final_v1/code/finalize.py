"""Audit numeric contracts, preserve historical evidence and validate a portable ZIP."""
import argparse
import json
import re
import os
from urllib.parse import unquote
import shutil
import subprocess
import sys
import tempfile
import zipfile
import importlib.metadata as metadata
from datetime import datetime,timezone
from PIL import Image
from support import *

def checks(out):
    a=load(out,'panel_a_participation');base=load(out,'institution_analysis_base');op=load(out,'publication_opportunities')
    ref=load(out,'benchmark_reference_unique_studies');inst=load(out,'benchmark_institution_probabilities')
    b=load(out,'panel_b_observed_expected');c=load(out,'panel_c_initial_use');d=load(out,'panel_d_author_continuity')
    dp=load(out,'author_continuity_papers');groups=load(out,'panel_d_group_shares');fixed=load(out,'author_fixed_count_sensitivity')
    activity=load(out,'initial_activity_institution');rates=load(out,'field_year_benchmark_rates')
    qa={
      'a_partition_2339':int(a.N.sum())==len(base)==2339,
      'a_percent_sum100':np.isclose(a.percentage.sum(),100),
      'a_repeat1255_both454':int(base.repeat.sum())==1255 and int(base.sustained.sum())==454,
      'base_unique_institutions':base.institution_id.is_unique,
      'opportunities_unique_integer_study_institution':not op.duplicated(['institution_id','study_id']).any(),
      'all_initial_dates_excluded':(pd.to_datetime(op.date)>pd.to_datetime(op.first_date)).all(),
      'no_post_window_records':(pd.to_datetime(op.date)<=pd.to_datetime(op.window_end)).all(),
      'reference_unique_across_institutions':ref.study_id.is_unique,
      'five_fixed_groups_complete':b.quintile.tolist()==[1,2,3,4,5] and int(b.N.sum())==2339,
      'no_missing_opportunities_to_zero':b.incomplete_expected.eq(0).all() and base.opportunity_timing_complete.all(),
      'probabilities_bounded':inst.expected.dropna().between(0,1).all() and rates.p.dropna().between(0,1).all(),
      'expected_q1_times_q2':np.allclose(inst.expected,inst.q1*inst.q2,equal_nan=True),
      'b_difference_identity':np.allclose(b.difference_pp,100*(b.observed-b.expected)),
      'initial_four_modes_per_institution':len(activity)==4*len(base) and not activity.duplicated(['institution_id','activity']).any(),
      'initial_unknown_not_negative':activity.initial_state.isin(['present','assessed_absent','unassessable']).all(),
      'no_fake_CI':c.loc[c.CI_status.ne('released_component_cluster_95CI'),['CI_low','CI_high','difference_CI_low','difference_CI_high']].isna().all().all(),
      'd_all_repeat_not_sustained_subset':len(d)==1255 and d.institution_id.is_unique,
      'd_all_followup_relations_retained':len(dp)==int((base.bin1+base.bin2).sum())==3244,
      'author_negative_requires_complete':dp.loc[dp.link_state.eq('unlinked'),['initial_observed_metadata_complete','later_observed_metadata_complete']].all().all(),
      'author_positive_requires_overlap':dp.loc[dp.link_state.eq('linked'),'overlapping_author_ids'].gt(0).all(),
      'category_partitions':groups.groupby(['variant','quintile']).percentage.sum().sub(100).abs().max()<1e-8,
      'fixed_count_exact_partition':fixed.groupby(['scope','later_papers_sampled','quintile']).exact_expected_percentage.sum().sub(100).abs().max()<1e-8,
      'fixed_count_same_institutions':fixed[fixed.scope.eq('common_at_least5')].groupby('quintile').N_eligible.nunique().eq(1).all(),
    }
    af=op[op.confirmed_af].groupby(['institution_id','interval']).size().unstack(fill_value=0).reindex(index=base.institution_id,columns=[1,2],fill_value=0)
    qa['AF_window_count_reconstruction']=np.array_equal(af,base.set_index('institution_id')[['bin1','bin2']])
    for q,g in base.groupby('quintile'):
        row=b[b.quintile.eq(q)].iloc[0]
        qa[f'quintile_{q}_observed']=np.isclose(row.observed,g.sustained.mean())
    require(all(qa.values()),'Numeric audit failed: '+str([k for k,v in qa.items() if not v]))
    return qa

def links(directory):
    count=0
    for p in directory.rglob('*.md'):
        for text in re.findall(r'\]\(([^)\n]+)\)',p.read_text()):
            if text.startswith(('https:','http:','#','mailto:')):continue
            target=(p.parent/unquote(text.split('#')[0].strip('<>'))).resolve()
            require(target.is_relative_to(directory.resolve()) and target.is_file(),'Invalid package link: '+str(p.relative_to(directory))+' '+text)
            count+=1
    return count

def protocol_history(out):
    original=json.loads((out/'provenance/input_pins.json').read_text())
    target=next(p for p in original if p['path']==str(MODULE/'README.md'))
    current=(MODULE/'README.md').read_text()
    already_current=hashlib.sha256(current.encode()).hexdigest()==target['sha256']
    old=current.replace('and at least 10 observed institutions in each initial-type/outcome cell.','and adequate supported/absent outcome cells.')
    amendment=' Before initial-type fitting, fix a computational fallback: if MLE separation/convergence/support prevents an estimate, fit standardized ridge-logistic (slope penalty lambda=1, unpenalized intercept) for an explicitly exploratory Extended Data point, with lambda=.1/10 sensitivity; never call its estimate unpenalized MLE or release a naive CI. No direction-based penalty selection.'
    old=old.replace(amendment,'')
    if already_current:old=current
    require(hashlib.sha256(old.encode()).hexdigest()==target['sha256'],'Cannot reconstruct the original recorded protocol bytes')
    (out/'provenance/protocol_at_preparation.md').write_text(old)
    (out/'provenance/protocol_before_initial_models.md').write_text(current)
    dump(out/'provenance/protocol_amendment.json',dict(original_sha256=target['sha256'],
      amended_sha256=sha(MODULE/'README.md'),scope='Current protocol used from preparation on clean replay' if already_current else 'Before first initial-mode model fit; preparation and benchmark definitions unchanged',
      change='Explicit min cell count10 and ridge computational fallback with fixed .1/1/10 penalties; CI remains withheld on failed gates',
      initial_snapshot_method='Reverse one documented amendment and verify byte-identical against the original preparation SHA256',
      human_independent_gold_approval=False))
    for p in original:
        if p['path']!=str(MODULE/'README.md'):require(sha(p['path'])==p['sha256'],'Original data/source changed: '+p['path'])

def historical(out):
    target=out/'previous_figure3_v6'
    m=json.loads((PREVIOUS/'run_manifest.json').read_text())
    for name,pin in m['outputs'].items():require(sha(PREVIOUS/name)==pin['sha256'],'Previous release differs: '+name)
    if not target.exists():shutil.copytree(PREVIOUS,target,ignore=shutil.ignore_patterns('.DS_Store','__pycache__'))
    logpath=out/'provenance/historical_link_relocations.json'
    log=json.loads(logpath.read_text()) if logpath.exists() else []
    changed={v['path']:v for v in log}
    for name,pin in m['outputs'].items():
        if sha(target/name)==pin['sha256']:continue
        require(name in changed and sha(out/changed[name]['original_snapshot'])==pin['sha256'] and sha(target/name)==changed[name]['portable_sha256'],'Historical source snapshot differs')
    shutil.copyfile(OLD/'run_manifest.json',out/'provenance/original_activity_analysis_manifest.json')
    shutil.copyfile(PLAN,out/'provenance/source_plan.md')

def portable_historical_links(out):
    """Rewrite navigation only in the portable copy; retain exact raw text bytes."""
    root=out/'previous_figure3_v6';logpath=out/'provenance/historical_link_relocations.json'
    log=json.loads(logpath.read_text()) if logpath.exists() else []
    pattern=re.compile(r'(!?)\[([^\]\n]*)\]\(([^)\n]+)\)')
    for p in list(root.rglob('*.md')):
        before=p.read_text();replacements=[]
        def replace(m):
            url=m.group(3)
            if url.startswith(('https:','http:','mailto:','#')):return m.group(0)
            resolved=(p.parent/unquote(url.split('#')[0].strip('<>'))).resolve()
            if resolved.is_relative_to(out.resolve()) and resolved.is_file():return m.group(0)
            token=hashlib.sha256((p.relative_to(root).as_posix()+'|'+url).encode()).hexdigest()[:16]
            notice=out/'provenance'/f'external_reference_{token}.md'
            notice.write_text('# 原始材料的外部参考路径\n\n该引用来自保留的历史材料，原地址是外部或临时文件，并非本包已有附件；未将其他图冒充原图。历史原文按原字节保存，当前仅修正便携副本导航。\n\n原引用地址：\n\n```text\n'+url+'\n```\n\n[返回新版入口](../README_zh.md)\n')
            replacements.append(dict(original_reference=url,notice=notice.relative_to(out).as_posix()))
            rel=Path(os.path.relpath(notice,p.parent)).as_posix()
            return f'[{m.group(2)}（原外部引用说明）]({rel})'
        after=pattern.sub(replace,before)
        if after!=before:
            token=hashlib.sha256(p.relative_to(root).as_posix().encode()).hexdigest()[:16]
            snapshots=out/'provenance/historical_originals';snapshots.mkdir(exist_ok=True)
            raw=snapshots/(token+'.source.txt');raw.write_bytes(p.read_bytes())
            original_sha=sha(p);p.write_text(after)
            log.append(dict(path=p.relative_to(root).as_posix(),original_sha256=original_sha,
              original_snapshot=raw.relative_to(out).as_posix(),portable_sha256=sha(p),replacements=replacements))
    dump(logpath,log)

def evidence_index(out):
    x=load(out,'initial_activity_evidence')
    q=x.groupby(['event_source_work_id','activity','state','action_source']).agg(institution_relations=('institution_id','size')).reset_index()
    q['source_export']='initial_activity_evidence.csv'
    q['upstream_evidence_locator']='original_activity_analysis_manifest.json inputs; join by event_source_work_id'
    q['new_independent_human_validation']=False
    save(out,'initial_action_evidence_index',q)
    sources=x.groupby(['activity','action_source','state']).agg(institution_relations=('institution_id','size'),unique_source_works=('event_source_work_id','nunique')).reset_index()
    save(out,'initial_classification_source_audit',sources)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true');parser.add_argument('--output-dir',type=Path,default=OUT);a=parser.parse_args()
    out=a.output_dir.resolve();archive=MODULE/'Figure3_plan3_reading_package_v1.zip' if out==OUT else out.with_suffix('.zip')
    if a.verify_only:
        manifest=json.loads((out/'run_manifest.json').read_text())
        for name,pin in manifest['outputs'].items():require(sha(out/name)==pin['sha256'],'Output changed: '+name)
        for p in manifest['inputs']:require(sha(p['path'])==p['sha256'],'Current source pin differs')
        print('Read-only verification PASS:',len(checks(out)),'numeric checks;',links(out),'links');return
    require(not (out/'run_manifest.json').exists() and not archive.exists(),'Completed release is immutable')
    test=subprocess.run([sys.executable,str(MODULE/'test_plan3.py')],cwd=ROOT,capture_output=True,text=True)
    require(test.returncode==0,'Unit tests failed: '+test.stdout+test.stderr)
    historical(out);protocol_history(out);evidence_index(out);portable_historical_links(out)
    code=out/'code';code.mkdir(exist_ok=True)
    for p in MODULE.glob('*.py'):shutil.copyfile(p,code/p.name)
    shutil.copyfile(MODULE/'README.md',code/'README.md')
    module('plan3_evidence_report',MODULE/'report.py').write(out)
    (code/'REPRODUCE.md').write_text('''# Reproduction in the original project environment

The ZIP is self-contained for reading figures, tables and Markdown navigation. Recomputing requires the original pinned project datasets, which are deliberately not duplicated in this reading archive.

Run from the original AlphaFoldResearch project using the existing .venv Python:

```sh
.venv/bin/python analysis/nhb_03/revision_v7/test_plan3.py
.venv/bin/python analysis/nhb_03/revision_v7/run_all.py --output-dir analysis/nhb_03/revision_v7/reproduced_v1
```

The output directory must not exist. This runs preparation, all nine benchmarks, author continuity, initial-mode models, figures, visual contact sheets, numeric/hash checks and portable packaging. Review generated contact sheets before using the new output; an unattended replay is not human scientific approval.

The initial release was built by the same saved stage functions: prepare.py; benchmark.py; authors.py; initial_models.py; figures.py; report.py; refresh_monthly_sensitivity.py (unpublished month-end implementation correction); visual_review.py; finalize.py. The corrected month-end implementation is integrated into prepare.py for clean replay, so the repair stage is not needed on a clean run. No temporary command-line analysis is required.
''')
    qa=checks(out)
    rasters=[]
    for p in (out/'figures').rglob('*'):
        if p.suffix in ['.png','.tiff'] and '_preview' not in p.stem:
            with Image.open(p) as im:
                dpi=[float(v) for v in im.info.get('dpi',(0,0))]
                require(im.mode=='RGB' and min(dpi)>599 and im.info.get('icc_profile'),'Raster technical check failed')
                rasters.append(dict(path=p.relative_to(out).as_posix(),pixels=im.size,dpi=dpi,RGB=True,sRGB=True))
    for p in (out/'figures').rglob('*.pdf'):
        raw=p.read_bytes();require(b'/FontFile2' in raw and b'/Subtype /Type3' not in raw,'PDF TrueType embedding failed')
    for p in (out/'figures').rglob('*.svg'):require('<text' in p.read_text(),'SVG editable text missing')
    dump(out/'provenance/unit_tests.json',dict(status='PASS',test_output=test.stderr+test.stdout,exit_code=test.returncode))
    dump(out/'validation_report.json',dict(status='PASS',checks=qa,check_count=len(qa),rasters=rasters,
      assistant_visual_review='core/read-layout/initial-use/author-continuity/Extended Data inspected',author_scientific_approval='pending',
      initial_type_reliable_95CI=False,initial_type_independent_new_human_validation=False,
      old_data_unchanged=True,paid_calls=0,new_LLMapi_calls=0,submission_ready=False))
    nlinks=links(out)
    currentpins=pins()
    output={p.relative_to(out).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='.DS_Store'}
    dump(out/'run_manifest.json',dict(schema='figure3-plan3-v1',created_utc=datetime.now(timezone.utc).isoformat(),
      inputs=currentpins,outputs=output,seed=SEED,api_calls=0,
      environment={p:metadata.version(p) for p in ['duckdb','pyarrow','numpy','pandas','scipy','matplotlib','pillow']},
      core_panels=['a','b'],c_status='exploratory_only_CI_gate_failed',d_status='descriptive_with_unresolved_retained',
      execution_protocol='code/README.md',protocol_history='provenance/protocol_amendment.json',
      author_review_pending=True,submission_certified=False))
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file() and p.name!='.DS_Store':z.write(p,out.name+'/'+p.relative_to(out).as_posix())
    with tempfile.TemporaryDirectory(prefix='figure3-plan3-unzip-') as tmp:
        with zipfile.ZipFile(archive) as z:require(z.testzip() is None,'ZIP CRC failed');z.extractall(tmp)
        unpacked=Path(tmp)/out.name;require(links(unpacked)==nlinks,'ZIP navigation differs')
        for p in out.rglob('*'):
            if p.is_file() and p.name!='.DS_Store':require(sha(p)==sha(unpacked/p.relative_to(out)),'ZIP extraction hash differs')
    require(currentpins==pins(),'Source input changed while packaging')
    testcount=int(re.search(r'Ran (\d+) tests',test.stderr+test.stdout).group(1))
    dump(MODULE/'package_check_v1.json',dict(status='PASS',archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),
      numeric_checks=len(qa),unit_tests=testcount,relative_links=nlinks,actual_zip_extraction_verified=True,paid_calls=0))
    print(f'Plan-3 release PASS: {len(qa)} numeric checks, {testcount} tests, {nlinks} package links')
    print('Core:',out/'figures/figure3_core_a_b.pdf');print('Reading:',out/'figures/figure3_a_d_reading_not_full_inference.pdf');print('ZIP:',archive)

if __name__=='__main__':main()
