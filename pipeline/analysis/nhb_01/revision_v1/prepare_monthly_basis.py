"""Prepare actual monthly/period diagnostics on OLD frozen labels, not revised final figures."""
from __future__ import annotations

import argparse
from datetime import date,datetime,timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile

import duckdb
import pandas as pd

from local_recall import MODULE, ROOT, destination, pin, require, sha, sql_path, write_json
from verify_recall import verify as verify_recall

# Reuse the read-only frozen-chain auditor. No old source code or output is edited.
sys.path.insert(0,str(MODULE.parent))
from io_utils import audit_inputs, STUDIES, FOUNDATION


def period_for(value, periods):
    if value is None:return None
    for p in periods:
        if p['start']<=value<p['end_exclusive']:return p['name']
    return None


def prepare(c,studies,countries,registry,protocol):
    c.execute(f'''CREATE VIEW studies AS SELECT study_id,annual_representative_work_id,
        publication_year,publication_date,confirmed_af,screen_negative,candidate_reviewed,
        work_type,primary_subfield_id FROM read_parquet({sql_path(studies)})''')
    c.execute(f'CREATE VIEW countries AS SELECT * FROM read_parquet({sql_path(countries)})')
    c.execute(f'CREATE VIEW registry AS SELECT country_code FROM read_parquet({sql_path(registry)})')
    require(c.execute('SELECT count(*)-count(DISTINCT country_code) FROM registry').fetchone()[0]==0,'Duplicate registry')
    require(c.execute('SELECT count(*)-count(DISTINCT study_id) FROM studies').fetchone()[0]==0,'Duplicate studies')
    require(c.execute('''SELECT count(*) FROM countries WHERE country_weight IS NULL OR n_countries<=0
        OR abs(country_weight-1.0/n_countries)>1e-10''').fetchone()[0]==0,'Invalid country weights')
    require(c.execute('''SELECT count(*) FROM countries c LEFT JOIN registry r USING(country_code)
        WHERE r.country_code IS NULL''').fetchone()[0]==0,'Unknown country code')
    case='CASE '+ ' '.join(f"WHEN dt>=DATE '{p['start']}' AND dt<DATE '{p['end_exclusive']}' THEN '{p['name']}'" for p in protocol['periods'])+' ELSE NULL END'
    c.execute(f'''CREATE TEMP TABLE scope AS SELECT *,date_trunc('month',dt)::DATE AS month,{case} AS period_name
        FROM (SELECT *,try_cast(publication_date AS DATE) AS dt FROM studies
              WHERE publication_year BETWEEN 2015 AND 2025 AND work_type IN ('article','review','preprint'))''')
    date_audit=c.execute('''SELECT publication_year,count(*) AS studies,
        count(*) FILTER(WHERE confirmed_af) AS confirmed_af,
        count(*) FILTER(WHERE dt IS NULL) AS date_unparseable,
        count(*) FILTER(WHERE dt IS NOT NULL AND year(dt)<>publication_year) AS year_date_mismatch,
        count(*) FILTER(WHERE confirmed_af AND dt IS NOT NULL AND month(dt)=1 AND day(dt)=1) AS af_january1_review_flag
        FROM scope GROUP BY 1 ORDER BY 1''').df()
    # Do not silently reassign date-mismatched studies to the other year.
    require(date_audit.year_date_mismatch.sum()==0,'Year/date mismatch: stop for source/date review')
    c.execute('''CREATE TEMP TABLE country_sets AS SELECT work_id,string_agg(country_code,'|' ORDER BY country_code) AS signature
        FROM countries GROUP BY work_id''')
    c.execute('''CREATE TEMP TABLE basis AS SELECT s.*,coalesce(w.signature,'') AS signature
        FROM scope s LEFT JOIN country_sets w ON s.annual_representative_work_id=w.work_id''')
    c.execute('''CREATE TEMP TABLE period_credits AS SELECT b.period_name,c.country_code,
          sum(c.country_weight) AS eligible_credit,
          sum(CASE WHEN b.confirmed_af THEN c.country_weight ELSE 0 END) AS af_credit,
          count(*) AS eligible_participation_studies,
          count(*) FILTER(WHERE b.confirmed_af) AS af_participation_studies
        FROM basis b JOIN countries c ON b.annual_representative_work_id=c.work_id
        WHERE b.period_name IS NOT NULL GROUP BY 1,2''')
    period_counts=c.execute('''SELECT period_name,count(*) AS eligible_studies,
        count(*) FILTER(WHERE confirmed_af) AS af_studies,
        count(*) FILTER(WHERE signature<>'') AS eligible_assigned,
        count(*) FILTER(WHERE confirmed_af AND signature<>'') AS af_assigned,
        count(*) FILTER(WHERE confirmed_af AND signature='') AS af_unknown
        FROM basis WHERE period_name IS NOT NULL GROUP BY 1''').df()
    order={p['name']:i for i,p in enumerate(protocol['periods'])}
    period_counts['order']=period_counts.period_name.map(order)
    period_counts=period_counts.sort_values('order').drop(columns='order').reset_index(drop=True)
    c.register('period_totals',period_counts)
    profiles=c.execute('''SELECT t.period_name,r.country_code,t.af_studies,t.af_assigned,t.af_unknown,
        coalesce(p.af_credit,0)::DOUBLE AS af_credit,coalesce(p.eligible_credit,0)::DOUBLE AS eligible_credit,
        coalesce(p.af_participation_studies,0)::BIGINT AS af_participation_studies,
        coalesce(p.eligible_participation_studies,0)::BIGINT AS eligible_participation_studies,
        100.0*coalesce(p.af_credit,0)/nullif(t.af_assigned,0) AS global_known_af_percent,
        100.0*coalesce(p.af_credit,0)/nullif(p.eligible_credit,0) AS domestic_local_af_percent,
        coalesce(p.eligible_credit,0)>0 AS denominator_available,
        coalesce(p.af_credit,0)>0 AND coalesce(p.eligible_credit,0)>0 AS scatter_included
        FROM period_totals t CROSS JOIN registry r LEFT JOIN period_credits p
        ON p.period_name=t.period_name AND p.country_code=r.country_code ORDER BY t.period_name,r.country_code''').df()
    for p in protocol['periods']:
        name=p['name'];part=profiles[profiles.period_name.eq(name)]
        n=period_counts[period_counts.period_name.eq(name)].iloc[0]
        require(abs(part.af_credit.sum()-int(n.af_assigned))<1e-6,'AF credit does not conserve known studies')
        require(abs(part.eligible_credit.sum()-int(n.eligible_assigned))<1e-6,'Eligible credit not conserved')
    require(not (profiles.af_credit>profiles.eligible_credit+1e-8).any(),'AF numerator exceeds denominator')
    first=c.execute('''SELECT c.country_code,min(b.month) AS first_observed_month
        FROM basis b JOIN countries c ON b.annual_representative_work_id=c.work_id
        WHERE b.confirmed_af AND b.month IS NOT NULL GROUP BY 1 ORDER BY 1''').df()
    monthly=[]
    for month in pd.date_range('2020-01-01','2025-12-01',freq='MS'):
        f=pd.to_datetime(first.first_observed_month)
        monthly.append({'month':month.date().isoformat(),
            'period_name':period_for(month.date().isoformat(),protocol['periods']),
            'new_countries':int(f.eq(month).sum()),'cumulative_countries':int(f.le(month).sum()),
            'pre2020_countries':int(f.lt(pd.Timestamp('2020-01-01')).sum())})
    monthly=pd.DataFrame(monthly)
    annual=c.execute('''SELECT publication_year,count(*) FILTER(WHERE confirmed_af) AS confirmed_af,
        count(*) FILTER(WHERE confirmed_af AND dt IS NULL) AS af_missing_date
        FROM basis GROUP BY 1 ORDER BY 1''').df()
    frozen_yearly=c.execute('''SELECT b.publication_year,count(DISTINCT c.country_code) AS active_countries
        FROM basis b JOIN countries c ON b.annual_representative_work_id=c.work_id
        WHERE b.confirmed_af GROUP BY 1 ORDER BY 1''').df()
    return {'date_audit':date_audit,'period_counts':period_counts,'country_period_profiles':profiles,
            'country_first_observed':first,'monthly_diffusion':monthly,'annual_counts':annual,
            'annual_country_coverage':frozen_yearly}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recall-dir',type=Path,default=MODULE/'recall_audit_v1')
    p.add_argument('--output-dir',type=Path,default=MODULE/'monthly_basis_v1')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args(argv);dest=destination(a.output_dir)
    print('Checking old frozen lineage and recall queue; final revised figure remains gated...',flush=True)
    recall=verify_recall(a.recall_dir);pins=audit_inputs()
    for f in [a.recall_dir/'run_manifest.json',a.recall_dir/'summary.json',MODULE/'protocol.json',Path(__file__)]:pins.append(pin(f))
    if a.dry_run:
        print('Source hashes/lineage passed; no monthly/period computation, writes or API calls');return 0
    stage=Path(tempfile.mkdtemp(prefix='.monthly-basis-incomplete-',dir=MODULE));stage.chmod(0o700)
    c=duckdb.connect(config={'threads':2,'memory_limit':'2GiB','temp_directory':str(stage/'spill'),
        'max_temp_directory_size':'2GiB','preserve_insertion_order':False,
        'autoinstall_known_extensions':False,'autoload_known_extensions':False})
    try:
        protocol=json.loads((MODULE/'protocol.json').read_text())
        tables=prepare(c,STUDIES/'study_records.parquet',FOUNDATION/'work_countries.parquet',
                       FOUNDATION/'country_registry.parquet',protocol)
        for name,df in tables.items():
            df.to_parquet(stage/(name+'.parquet'),index=False);df.to_csv(stage/(name+'.csv'),index=False)
        summary={'label_source':'OLD frozen study_events_v1; new candidates NOT merged',
                 'period_counts':tables['period_counts'].to_dict('records'),
                 'first_observed_country_count':len(tables['country_first_observed']),
                 'dates_unparseable':int(tables['date_audit'].date_unparseable.sum()),
                 'af_january1_review_flags':int(tables['date_audit'].af_january1_review_flag.sum()),
                 'new_eligible_candidates_pending':recall['new_candidates_eligible'],
                 'ready_for_monthly_design_diagnostics':True,'ready_for_final_revised_figure':False,'api_calls':0}
        write_json(stage/'summary.json',summary);write_json(stage/'protocol.json',protocol)
        (stage/'README_zh.md').write_text('''# 新版月度／时期底表：旧标签诊断版

**不是召回修复后的正式结果。** 本目录用于检查月份规则、分数信用守恒和新布局的数据可用性，新765候选未合并。不能替换论文Results或旧阅读包。

- [三个时期数量及已知／未知归属](period_counts.csv)
- [全部国家×时期散点底表](country_period_profiles.csv)
- [月度首次观察新增／累计](monthly_diffusion.csv)
- [逐年日期审计](date_audit.csv)
- [历史国家首次观察月份](country_first_observed.csv)
- [汇总／发布门槛](summary.json)

时期只按发表月份，不代表AF模型版本。日期可解析不认证月份精度；1月1日是审查线索，未据此剔除记录。全球份额分母为已知国家归属AF信用，国内分母为本地全部适格研究信用；未知归属不重新分摊。首次观察保留2015–2019已观察的国家。早期参与稀疏不作因果或版本效应解释。

下一步：新候选证据核查及标签批准；批准叠加层和比较组重建通过后，方可冻结正式新版a–d。固定十国期间仍待确认。无LLM／API调用。
''',encoding='utf-8')
        c.close();c=None
        for p in pins:require(sha(p['path'])==p['sha256'],'Input changed during monthly preparation')
        outputs={p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in stage.iterdir() if p.is_file()}
        write_json(stage/'run_manifest.json',{'schema_version':'nhb01-monthly-diagnostic-v1',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'inputs':pins,'outputs':outputs,'summary':summary,
            'frozen_source_labels_unchanged':True,'formal_revised_result':False})
        for f in stage.iterdir():
            if f.is_file():f.chmod(0o600)
        require(not dest.exists(),'Refusing replacement');stage.rename(dest)
        print('Monthly/period diagnostic preparation PASS; period AF counts: '+
              ', '.join(str(int(n)) for n in tables['period_counts'].af_studies))
        print('Old labels only; no final revised figure, semantic approval or API calls')
        return 0
    finally:
        if c is not None:c.close()


if __name__=='__main__':raise SystemExit(main())
