"""Independent SQL/count checks, source pins and portable ZIP verification."""
import argparse
from datetime import datetime,timezone
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote
import zipfile
from PIL import Image
from support import *
from benchmark import ratio

def numeric_checks(out):
    base=load(out,'baseline_groups');country=load(out,'country_context');cells=load(out,'country_group_year')
    ctx=load(out,'context_group_year');bm=load(out,'benchmark_summary');con=load(out,'context_contrasts')
    qa={
      'baseline_unique_52098':base.institution_id.is_unique and len(base)==52098,
      'baseline_V_positive_integer':base.V_i.ge(1).all() and np.equal(base.V_i,np.floor(base.V_i)).all(),
      'fixed_country_only_unique_baseline':base.loc[base.eligible_20,'baseline_country_count'].eq(1).all(),
      'main_N20_all_groups':country.loc[country.eligible_20,['N_L','N_M','N_H']].ge(20).all().all(),
      'main_countries_no_AF_selection':set(country.loc[country.eligible_20,'country'])==set(cells.loc[cells.eligible_20,'country']),
      'fixed_denominator_across_years':cells.groupby(['country','group']).fixed_N.nunique().eq(1).all(),
      'integer_annual_activity':cells.active_N.eq(np.floor(cells.active_N)).all(),
      'coverage_identity':np.allclose(cells.A,cells.active_N/cells.fixed_N),
      'cumulative_identity':np.allclose(cells.C,cells.cumulative_N/cells.fixed_N),
      'A_C_bounded':cells[['A','C']].ge(0).all().all() and cells[['A','C']].le(1).all().all(),
      'cumulative_monotone':cells.sort_values('year').groupby(['country','group']).C.diff().dropna().ge(-1e-12).all(),
      'G_identity':True,'R_ratio_of_means':True,'global_not_equal_context_weight':True,
      'analytic_MC_aggregate_all_pass':bm.mean_within_5MCSE.all(),
      'main_and_refinements_B5000':bm.draws.ge(5000).all(),
      'paired_contrast_not_independent':True,
    }
    for _,x in base[base.country.notna()&base.group_eligible].groupby(['country','V_i']):
        require(x.group.nunique()==1,'Equal integer baseline count split across groups')
    qa['baseline_ties_never_split']=True
    for minimum in [10,20,30]:
        eligible=country.loc[country[f'eligible_{minimum}'],'country']
        select=cells[cells.country.isin(eligible)]
        for context in CONTEXTS:
            q=ctx[(ctx.analysis==f'N{minimum}')&(ctx.context==context)]
            cs=eligible if context=='All' else country.loc[country[f'eligible_{minimum}']&country.context.eq(context),'country']
            expected=select[select.country.isin(cs)].groupby(['group','year'])[['A','C']].mean()
            actual=q.set_index(['group','year'])[['A','C']].sort_index()
            qa[f'equal_country_{minimum}_{context}']=np.allclose(actual,expected.reindex(actual.index))
            pivot=q.pivot(index='year',columns='group',values='A')
            require(np.allclose(q.G,100*(q.year.map(pivot.H)-q.year.map(pivot.L))),'Gap identity failed')
            require(np.allclose(q.R,ratio(q.year.map(pivot.L),q.year.map(pivot.H)),equal_nan=True),'R ratio of means failed')
    # Each country fixed weight must be shared across L/M/H and endpoints.
    for y in YEARS:
        q=ctx[(ctx.analysis=='N20')&(ctx.year==y)]
        for g in GROUPS:
            row=q[q.group.eq(g)].set_index('context')
            weighted=np.average(row.loc[['Low','Middle','High'],'A'],weights=row.loc[['Low','Middle','High'],'countries'])
            require(np.isclose(row.loc['All','A'],weighted),'Global aggregation accidentally weighted context equally')
    # Independent SQL from study identity and full institution membership; no sparse-matrix helper.
    with connect(out) as c:
        bpath=out/'tables/baseline_groups.parquet';ppath=out/'tables/opportunity_studies.parquet';mpath=out/'tables/opportunity_memberships.parquet'
        independent=c.execute(f'''SELECT b.country,b."group",p.year,count(DISTINCT b.institution_id) AS active_N
          FROM read_parquet({lit(ppath)}) p JOIN read_parquet({lit(mpath)}) m USING(study_id)
          JOIN read_parquet({lit(bpath)}) b USING(institution_id)
          WHERE p.z=1 AND b.eligible_10 GROUP BY ALL''').df()
        joined=cells[cells.year.ge(2020)].merge(independent,on=['country','group','year'],how='left',suffixes=('','_SQL'),validate='one_to_one')
        qa['independent_SQL_annual_counts']=np.array_equal(joined.active_N,joined.active_N_SQL.fillna(0))
        qa['full_study_institution_unique']=c.execute(f'''SELECT count(*)-count(DISTINCT (study_id,institution_id))
          FROM read_parquet({lit(out/'tables/study_institution.parquet')})''').fetchone()[0]==0
        qa['frozen_research_units_unique']=c.execute(f'''SELECT count(*)-count(DISTINCT study_id)
          FROM read_parquet({lit(out/'tables/studies.parquet')})''').fetchone()[0]==0
        af=c.execute(f'''SELECT count(*) FROM read_parquet({lit(out/'tables/studies.parquet')}) WHERE confirmed_af AND year BETWEEN 2020 AND 2025''').fetchone()[0]
        old=json.loads((OLD/'summary.json').read_text())
        qa['confirmed_AF_16414_unchanged']=af==old['global_af_studies']==16414
        qa['unknown_never_binary_zero']=c.execute(f'''SELECT count(*) FROM read_parquet({lit(out/'tables/opportunity_studies.parquet')}) WHERE possible_af OR z<0''').fetchone()[0]==0
        qa['baseline_outside_pool_present']=c.execute(f'''SELECT count(*) FROM read_parquet({lit(ppath)}) p WHERE NOT EXISTS
          (SELECT 1 FROM read_parquet({lit(mpath)}) m JOIN read_parquet({lit(bpath)}) b USING(institution_id)
          WHERE m.study_id=p.study_id AND b.eligible_20)''').fetchone()[0]>0
        qcount=c.execute(f'''SELECT count(*) FROM read_parquet({lit(out/'tables/studies.parquet')}) WHERE metadata_quality='institution_unattributed' AND n_institutions>0''').fetchone()[0]
        qa['no_fake_institution_attribution']=qcount==0
    r=load(out,'benchmark_replicates')
    qa['replicate_ids_shared_all_contexts']=r.groupby(['variant','setting','replicate']).context.nunique().eq(4).all()
    for row in con.itertuples():
        v=r[(r.variant==row.variant)&(r.setting==row.setting)].pivot(index='replicate',columns='context',values='delta_G')
        summary=bm[(bm.variant==row.variant)&(bm.setting==row.setting)].set_index('context')
        means=summary.expected_delta_G
        d=(v[row.context]-means[row.context])-(v[row.reference_context]-means[row.reference_context])
        np.testing.assert_allclose(np.quantile(d,[.025,.975]),[row.centered_low,row.centered_high],atol=1e-10)
        require(np.isclose(row.observed_excess_difference,summary.loc[row.context,'excess']-summary.loc[row.reference_context,'excess']),'Contrast point identity')
    qa['paired_contrast_quantiles_reconstructed']=True
    for row in bm.itertuples():
        draws=r[(r.variant==row.variant)&(r.setting==row.setting)&(r.context==row.context)].delta_G
        require(np.isclose(row.excess,row.actual_delta_G-row.expected_delta_G),'Excess identity')
        np.testing.assert_allclose(np.quantile(draws-row.expected_delta_G,[.025,.975]),[row.centered_low,row.centered_high],atol=1e-10)
    qa['centered_reference_not_E_centered_CI']=True
    residual=load(out,'residual_heatmap')
    for row in bm.itertuples():
        q=residual[(residual.variant==row.variant)&(residual.setting==row.setting)&(residual.context==row.context)].set_index('group')
        require(np.isclose(row.excess,q.loc['H','residual_change_pp']-q.loc['L','residual_change_pp']),'Heatmap H-L excess identity')
    qa['residual_heatmap_reconstructs_E']=True
    for variant in ['main','document_type','team_size']:
        info=json.loads((out/'provenance'/f'main_runtime_{variant}.json').read_text())
        qa['every_draw_K_invariant_'+variant]=info.get('stratum_K_checked_every_replicate',False)
    require(all(qa.values()),'Numeric validation failed: '+str([k for k,v in qa.items() if not v]))
    return qa

def check_links(directory):
    count=0
    for p in directory.rglob('*.md'):
        for raw in re.findall(r'\]\(([^)\n]+)\)',p.read_text()):
            if raw.startswith(('http:','https:','mailto:','#')):continue
            rel=unquote(raw.split('#')[0].strip('<>'))
            target=(p.parent/rel).resolve()
            require(target.is_relative_to(directory.resolve()) and target.is_file(),'Broken or external package link: '+str(p)+' '+raw)
            count+=1
    return count

def portable_plan(out):
    path=out/'provenance/figure2-revision-plan-3.md';raw=path.read_text()
    snapshot=out/'provenance/figure2-revision-plan-3.source.txt'
    if not snapshot.exists():shutil.copyfile(path,snapshot)
    # The user's source points at another Mac user's visualization, not an available data file.
    raw=re.sub(r'!\[Finding 2 benchmark流程\]\([^\n]+\)',
      '原方案此处引用另一台电脑上的流程示意图；本包没有该原图，未以其他图片冒充。算法文字和公式完整保留。',raw)
    path.write_text(raw)
    dump(out/'provenance/plan_link_relocation.json',dict(original_sha256=sha(snapshot),portable_sha256=sha(path),
      note='Only an unavailable external illustrative-image link replaced with explicit notice; original bytes preserved.'))

def raster_checks(out):
    checks=[]
    for p in sorted((out/'figures').rglob('*')):
        if p.suffix not in ['.png','.tiff'] or '_preview' in p.stem:continue
        with Image.open(p) as im:
            dpi=[float(v) for v in im.info.get('dpi',(0,0))];expected=300 if 'submission_300dpi' in p.parts else 600
            require(im.mode=='RGB' and min(dpi)>expected-.1 and max(dpi)<expected+.1 and im.info.get('icc_profile'),'Raster profile/DPI check failed: '+str(p))
            checks.append(dict(path=p.relative_to(out).as_posix(),pixels=list(im.size),dpi=list(dpi),RGB=True,sRGB=True))
    for p in (out/'figures').rglob('*.pdf'):
        content=p.read_bytes();require(b'/FontFile2' in content and b'/Subtype /Type3' not in content,'PDF font embedding failed')
    for p in (out/'figures').rglob('*.svg'):require('<text' in p.read_text(),'SVG text not editable')
    return checks

def precision_diagnostics(out):
    """Batch-quantile MC error diagnostics, not additional effect/significance selection."""
    reps=load(out,'benchmark_replicates');rows=[]
    for keys,x in reps.groupby(['variant','setting','context']):
        x=x.sort_values('replicate');values=x.delta_G.to_numpy()
        chunks=np.array_split(values,10)
        q=np.array([np.quantile(v,[.025,.975]) for v in chunks])
        se=q.std(axis=0,ddof=1)/np.sqrt(10)
        rows.append(dict(variant=keys[0],setting=keys[1],context=keys[2],draws=len(values),
          reference_low=np.quantile(values,.025),reference_high=np.quantile(values,.975),
          approximate_quantile_MCSE_low_pp=se[0],approximate_quantile_MCSE_high_pp=se[1],
          method='10 disjoint equal-sized replicate batches; diagnostic approximation, not effect CI'))
    save(out,'monte_carlo_precision_audit',pd.DataFrame(rows))

def finalize(out,verify_only=False):
    archive=out.parent/'Figure2_plan3_reading_package_v1.zip' if out.resolve()==OUT.resolve() else out.with_suffix('.zip')
    if verify_only:
        manifest=json.loads((out/'run_manifest.json').read_text())
        for name,pin in manifest['outputs'].items():require(sha(out/name)==pin['sha256'],'Output differs: '+name)
        for pin in manifest['inputs']:require(sha(pin['path'])==pin['sha256'],'Source differs: '+pin['path'])
        qa=numeric_checks(out);nlinks=check_links(out)
        print(f'Read-only final verification PASS: {len(qa)} numeric checks; {nlinks} portable links',flush=True)
        return
    require(not (out/'run_manifest.json').exists() and not archive.exists(),'Completed release cannot be overwritten')
    require(json.loads((out/'provenance/input_pins.json').read_text())==pins(),'Original frozen inputs differ')
    portable_plan(out)
    code=out/'code';code.mkdir(exist_ok=True)
    for p in MODULE.glob('*.py'):shutil.copy2(p,code/p.name)
    shutil.copy2(MODULE/'README.md',code/'README.md')
    (code/'REPRODUCE.md').write_text('''# Reproduction

The ZIP is self-contained for reading figures, all reported tables, minimal derived study/institution inputs and Markdown links. Rebuilding raw preparation requires the pinned original project exports identified in provenance/input_pins.json; raw full texts are not included.

From the original AlphaFoldResearch repository, with its existing environment:

```sh
.venv/bin/python analysis/nhb_02/revision_v4/test_revision.py
.venv/bin/python analysis/nhb_02/revision_v4/run.py --output-dir analysis/nhb_02/revision_v4/reproduced_v1
```

Choose an absent output directory. This executes preparation, independent 200-draw pilot, three 5,000-draw joint benchmarks, exact expectation checks, all figures and prose, numeric checks and ZIP navigation verification. No provider calls, credentials or original-data edits. Source scripts in this folder are snapshots of the original project-relative layout, not a relocated replacement for the project root. The reading archive naming can be customized with a different output directory; completed releases refuse overwrite.

This release was executed through the same saved stage functions. Figure-only layout repairs do not rerun or change analysis tables. Assistant visual inspection is not author approval or journal acceptance.

[Reading entry](../README_zh.md)
''')
    from report import write
    precision_diagnostics(out)
    write(out)
    tests=subprocess.run([sys.executable,str(MODULE/'test_revision.py')],cwd=ROOT,capture_output=True,text=True)
    require(tests.returncode==0,'Regression tests failed: '+tests.stdout+tests.stderr)
    dump(out/'provenance/unit_tests.json',dict(status='PASS',output=tests.stdout+tests.stderr))
    qa=numeric_checks(out);rasters=raster_checks(out);nlinks=check_links(out)
    visual=(out/'provenance/visual_review.md').read_text()
    dump(out/'validation_report.json',dict(status='PASS',numeric_check_count=len(qa),checks=qa,rasters=rasters,
        portable_links=nlinks,raw_and_old_outputs_unchanged=True,paid_calls=0,new_LLM_calls=0,
        author_scientific_approval='pending',submission_acceptance_certified=False,
        assistant_visual_review='pending' if 'pending' in visual.lower() else 'Main figure and Extended Data contact sheets inspected; notes in provenance/visual_review.md'))
    inventory={p.relative_to(out).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
      for p in sorted(out.rglob('*')) if p.is_file() and p.name!='.DS_Store' and 'scratch' not in p.parts}
    dump(out/'run_manifest.json',dict(schema='figure2-plan3-final-v1',created_utc=datetime.now(timezone.utc).isoformat(),
       inputs=pins(),outputs=inventory,config=configuration(),old_data_unchanged=True,paid_calls=0,
       d_main=json.loads((out/'provenance/panel_d_decision.json').read_text())['main_panel']))
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file() and p.name!='.DS_Store' and 'scratch' not in p.parts:z.write(p,out.name+'/'+p.relative_to(out).as_posix())
    with tempfile.TemporaryDirectory(prefix='figure2-plan3-zipcheck-') as tmp:
        with zipfile.ZipFile(archive) as z:require(z.testzip() is None,'ZIP CRC failed');z.extractall(tmp)
        unpack=Path(tmp)/out.name
        require(check_links(unpack)==nlinks,'Unzipped Markdown links differ')
        manifest=json.loads((unpack/'run_manifest.json').read_text())
        for name,pin in manifest['outputs'].items():require(sha(unpack/name)==pin['sha256'],'Unzipped bytes differ: '+name)
    dump(out.parent/'Figure2_plan3_package_check.json',dict(status='PASS',archive=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,
        zip_CRC=True,all_unzipped_output_hashes=True,portable_links=nlinks,numeric_checks=len(qa)))
    print(f'Figure2 plan3 final PASS: {len(qa)} numeric checks; {nlinks} links; ZIP {archive.stat().st_size/1024**2:.1f} MiB',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=OUT);p.add_argument('--verify-only',action='store_true');p.add_argument('--numeric-only',action='store_true');a=p.parse_args()
    if a.numeric_only:
        qa=numeric_checks(a.output_dir)
        dump(a.output_dir/'provenance/independent_numeric_checks.json',dict(status='PASS',checks=qa,check_count=len(qa)))
        print(f'Independent numeric checks PASS: {len(qa)}')
    else:finalize(a.output_dir,a.verify_only)
