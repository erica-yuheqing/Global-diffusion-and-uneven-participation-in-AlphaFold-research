"""New Figure1 bundle; formal use requires an explicit accepted candidate layer."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import shutil
import duckdb
import pandas as pd
import pyarrow as pa

from local_recall import MODULE, ROOT, destination, pin, require, sha, sql_path, write_json
from prepare_monthly_basis import prepare, audit_inputs, STUDIES, FOUNDATION
from revised_country_analysis import prepare_annual, annual_diffusion
from render_revised_figure import render
from write_revised_narrative import write as write_narrative
import fetch_public_evidence as e


def approved_rows(path):
    record=json.loads(path.read_text())
    require(record.get('approval_status')=='accepted_by_user','Semantic decisions have not been accepted')
    require(record.get('approval_user_message') and record.get('source_review_pins'),'Missing specific approval/source provenance')
    rows=record['decisions']
    expected={x['work_id'] for x in json.loads((MODULE/'candidate_review_v1/review_packets_private.json').read_text())}
    require(len(rows)==765 and {r['work_id'] for r in rows}==expected,'Approved layer must account for all 765, including unknowns')
    for r in rows:
        require(r['af_use_label'] in ['yes','no','uncertain'] and r['adoption_eligible'] in ['yes','no','uncertain'],'Invalid core state')
        require(r.get('source_review') and r.get('decision_status'),'Missing decision provenance')
    for item in record['source_review_pins']:
        require(sha(Path(item['path']))==item['sha256'],'Approved source changed')
    return rows,record


def derive(c,rows,record,stage):
    c.register('accepted_candidates',pa.Table.from_pylist([
        {k:r[k] for k in ['work_id','af_use_label','adoption_eligible']} for r in rows]))
    c.execute(f'''CREATE TEMP TABLE raw_derived AS SELECT s.* REPLACE(
        CASE WHEN a.work_id IS NOT NULL THEN true ELSE s.candidate_reviewed END AS candidate_reviewed,
        CASE WHEN a.work_id IS NOT NULL THEN false ELSE s.screen_negative END AS screen_negative,
        CASE WHEN a.work_id IS NOT NULL THEN a.af_use_label='yes' AND a.adoption_eligible='yes' ELSE s.confirmed_af END AS confirmed_af,
        coalesce(a.af_use_label,s.af_use_label) AS af_use_label,
        coalesce(a.adoption_eligible,s.adoption_eligible) AS adoption_eligible)
        FROM read_parquet({sql_path(STUDIES/'study_records.parquet')}) s
        LEFT JOIN accepted_candidates a ON s.annual_representative_work_id=a.work_id''')
    require(c.execute('SELECT count(*) FROM raw_derived JOIN accepted_candidates a ON annual_representative_work_id=a.work_id').fetchone()[0]==len(rows),'Candidate mapping incomplete; stop, no implicit inherited override')
    # Explicit representatives only. No title clustering, date edits or inferred
    # source-label propagation. The approved representative must itself be yes
    # when it is intended to enter the confirmed numerator.
    remove=set(); linked_members=set()
    for link in record.get('accepted_version_links',[]):
        require(link.get('approval_status')=='accepted_by_user' and link.get('basis'),'Unapproved version link')
        members=link['member_work_ids'];rep=link['representative_work_id']
        require(len(members)>=2 and rep in members and len(set(members))==len(members),'Invalid version group')
        require(not linked_members.intersection(members),'Overlapping approved groups must first be consolidated')
        linked_members.update(members)
        count=c.execute('SELECT count(*) FROM raw_derived WHERE annual_representative_work_id IN (SELECT unnest(?))',[members]).fetchone()[0]
        require(count==len(members),'Version members not independent representatives; explicit map review needed')
        positive=c.execute('SELECT count(*) FROM raw_derived WHERE confirmed_af AND annual_representative_work_id IN (SELECT unnest(?))',[members]).fetchone()[0]
        rep_positive=c.execute('SELECT confirmed_af FROM raw_derived WHERE annual_representative_work_id=?',[rep]).fetchone()[0]
        require(not positive or rep_positive,'Cannot silently drop confirmed evidence by choosing an unknown/nonuse representative')
        remove.update(set(members)-{rep})
    c.register('removed_versions',pa.Table.from_pylist([{'work_id':x} for x in sorted(remove)]) if remove else pa.table({'work_id':pa.array([],pa.string())}))
    c.execute(f'''COPY (SELECT * FROM raw_derived WHERE annual_representative_work_id NOT IN
        (SELECT work_id FROM removed_versions)) TO {sql_path(stage/'derived_study_records.parquet')} (FORMAT PARQUET)''')
    return stage/'derived_study_records.parquet'


def member_specific_first_observation(c,tables,protocol):
    # New approved merges retain independently confirmed member dates and their
    # OWN affiliation sets for diffusion; annual composition remains coherent.
    from prepare_monthly_basis import period_for
    first=c.execute('''SELECT x.country_code,min(date_trunc('month',try_cast(s.publication_date AS DATE)))::DATE AS first_observed_month
        FROM raw_derived s JOIN countries x ON s.annual_representative_work_id=x.work_id
        WHERE s.confirmed_af AND s.publication_year BETWEEN 2015 AND 2025
        AND s.work_type IN ('article','review','preprint')
        GROUP BY 1 ORDER BY 1''').df()
    f=pd.to_datetime(first.first_observed_month)
    monthly=pd.DataFrame([{'month':m.date().isoformat(),'period_name':period_for(m.date().isoformat(),protocol['periods']),
        'new_countries':int(f.eq(m).sum()),'cumulative_countries':int(f.le(m).sum()),
        'pre2020_countries':int(f.lt(pd.Timestamp('2020-01-01')).sum())}
        for m in pd.date_range('2020-01-01','2025-12-01',freq='MS')])
    tables['country_first_observed']=first;tables['monthly_diffusion']=monthly


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--accepted-layer',type=Path)
    ap.add_argument('--old-label-diagnostic',action='store_true')
    ap.add_argument('--output-dir',type=Path,required=True)
    a=ap.parse_args(argv)
    require(bool(a.accepted_layer) != a.old_label_diagnostic,'Choose accepted semantic layer OR explicitly old-label diagnostic')
    out=destination(a.output_dir);pins=audit_inputs()
    code_sources=[Path(__file__),MODULE/'revised_country_analysis.py',MODULE/'render_revised_figure.py',
        MODULE/'prepare_monthly_basis.py',MODULE/'write_revised_narrative.py',MODULE.parent/'data.py',MODULE.parent/'country_stats.py']
    code_start={str(f):sha(f) for f in code_sources}
    for f in [MODULE/'protocol.json',MODULE/'execution_policy_v2.json']:pins.append(pin(f))
    decisions,record=approved_rows(a.accepted_layer) if a.accepted_layer else (None,None)
    if a.accepted_layer:pins.append(pin(a.accepted_layer))
    stage=Path(tempfile.mkdtemp(prefix='.revised-country-',dir=MODULE));stage.chmod(0o700)
    (stage/'code_snapshot').mkdir()
    for file in code_sources:shutil.copy2(file,stage/'code_snapshot'/file.name)
    c=duckdb.connect(config={'threads':2,'memory_limit':'3GiB','temp_directory':str(stage/'spill'),
        'max_temp_directory_size':'2GiB','preserve_insertion_order':False,
        'autoinstall_known_extensions':False,'autoload_known_extensions':False})
    try:
        studies=derive(c,decisions,record,stage) if decisions else STUDIES/'study_records.parquet'
        protocol=json.loads((MODULE/'protocol.json').read_text())
        protocol['fixed_top10']={'years':[2020,2025],'approval_status':'accepted_whole_period_selection'}
        c.execute(f'CREATE VIEW label_metadata AS SELECT study_id,af_use_label FROM read_parquet({sql_path(studies)})')
        print('Preparing publication-month tables and whole-study bootstrap...',flush=True)
        tables=prepare(c,studies,FOUNDATION/'work_countries.parquet',FOUNDATION/'country_registry.parquet',protocol)
        if decisions:member_specific_first_observation(c,tables,protocol)
        registry=c.execute('SELECT country_code FROM registry ORDER BY 1').df().country_code.tolist()
        annual,leaders=prepare_annual(c,registry);tables.update(annual)
        tables['annual_diffusion_counts']=annual_diffusion(tables['monthly_diffusion'],tables['annual_country_coverage'])
        for name,df in tables.items():df.to_parquet(stage/f'{name}.parquet',index=False);df.to_csv(stage/f'{name}.csv',index=False)
        render(tables,leaders,protocol,stage/'figures',diagnostic=a.old_label_diagnostic)
        summary={'formal_revised_result':not a.old_label_diagnostic,'label_source':'old_frozen_diagnostic' if a.old_label_diagnostic else 'specifically_user_accepted_overlay',
            'confirmed_AF_main':int(tables['annual_counts'].query('publication_year>=2020').confirmed_af.sum()),
            'fixed_ten':leaders,'bootstrap_replicates':1000,'country_registry':len(registry),'api_calls':0,
            'date_mismatches':int(tables['date_audit'].year_date_mismatch.sum()),
            'all_version_deduplication_certified':False,
            'whole_study_bootstrap_is_conditional_not_coverage_error':True,
            'semantic_decisions_pending':765 if a.old_label_diagnostic else 0,
            'first_observation_uses_independently_confirmed_member_own_country_sets':bool(decisions)}
        if decisions:
            summary['candidate_decisions']={'total':len(decisions),
                'yes_yes':sum(r['af_use_label']=='yes' and r['adoption_eligible']=='yes' for r in decisions),
                'nonuse':sum(r['af_use_label']=='no' for r in decisions),
                'uncertain':sum(r['af_use_label']=='uncertain' for r in decisions),
                'use_yes_not_downstream':sum(r['af_use_label']=='yes' and r['adoption_eligible']!='yes' for r in decisions)}
            summary['specifically_accepted_version_groups']=len(record.get('accepted_version_links',[]))
            summary['removed_version_records']=c.execute('SELECT count(*) FROM raw_derived').fetchone()[0]-c.execute('SELECT count(*) FROM studies').fetchone()[0]
        write_json(stage/'summary.json',summary);write_json(stage/'protocol.json',protocol)
        write_narrative(stage,tables,summary,protocol)
        (stage/'README_zh.md').write_text('''# Figure 1 新版计算导出

此目录的发布状态以[summary.json](summary.json)为准；旧标签诊断不能替换正式Results。全文提取、辅助评审、用户接受与正式结果不是同一件事。

- [四面板图](figures/)
- [按月首次观察](monthly_diffusion.csv)
- [三时期国家份额与国内比例](country_period_profiles.csv)
- [全期固定10国及未知份额](fixed_ten_composition.csv)
- [年度集中度及相对差异](concentration.csv)
- [排除2020／2021早期年度的端点敏感性](concentration_endpoint_sensitivity.csv)
- [国内比例共同支持调整](paired_domestic_heatmaps.csv)
- [调整支持保留率](paired_domestic_heatmap_support.csv)
- [年度来源／未知归属覆盖](annual_source_coverage.csv)

背景比较组是旧筛查阴性扣除本轮全部765候选，不是完整无AF金标准；未知不会混入阴性。国内比例只涉及本地采集领域的适格论文，并非各国全部科学产出。时期按发表月份，不代表实际运行AF版本或模型发布的因果效应。

全期固定十国每年不更换；未知国家信用不重新分摊。Gini固定227个国家与地区含零，整篇研究随机重采样1000次；95%区间仅条件于观察数据，不包括遗漏、标签错误、数据库覆盖差异或跨年团队依赖。端点差异不是单调趋势或发布效应检验。

共同支持热图在同一年、同类型、同子领域上比较相同样本；右侧将ALL的构成匹配到AF混合分布，总量维持共同支持的ALL量，是描述性假想分母敏感性，不冒充原始国内AF比例。
''',encoding='utf-8')
        c.close();c=None
        for item in pins:require(sha(Path(item['path']))==item['sha256'],'Input changed during run')
        require(all(sha(Path(path))==digest for path,digest in code_start.items()),'Analysis code changed during run')
        write_json(stage/'run_manifest.json',{'schema':'figure1-revised-computation-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'inputs':pins,'outputs':e.inventory(stage),'summary':summary,'visual_review':'pending',
            'executed_code_source_hashes':code_start})
        stage.rename(out);print('New bundle exported:',out,'; formal:',summary['formal_revised_result'])
        return 0
    finally:
        if c is not None:c.close()

if __name__=='__main__':raise SystemExit(main())
