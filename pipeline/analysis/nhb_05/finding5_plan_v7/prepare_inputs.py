"""Versioned Finding 5 v7 foundations. Does not certify citation completeness."""
from pathlib import Path
import hashlib,json,shutil,datetime
import duckdb,pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SPEC=Path('/historical-workspace/projects/IGN/revision/finding5-revision-plan-v7')
J=ROOT/'analysis/nhb_05/historical_journals_v1/figure5_historical_positions_v1'
F=ROOT/'analysis/nhb_revision_v1/out_v2'
S=ROOT/'analysis/nhb_01/revision_v1/figure1_revision_final_v2'
B=ROOT/'analysis/nhb_02/finding2_plan_v7/finding2_v7_final_v1/tables/institution_baseline_and_first_participation.csv'
OUT=HERE/'foundations_v2'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for x in iter(lambda:f.read(1048576),b''):h.update(x)
 return h.hexdigest()
def q(p):return "'"+str(p).replace("'","''")+"'"
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def require(x,m):
 if not x:raise ValueError(m)
def main():
 require(not OUT.exists(),'Output exists; verify instead of overwrite')
 stage=HERE/'.foundations-incomplete-v2';stage.mkdir(exist_ok=True)
 for name in ['inputs','data','tables','specification','code']: (stage/name).mkdir(exist_ok=True)
 pins={}
 def pin(p):pins[str(p)]=sha(p)
 for item in json.loads((SPEC/'manifest.json').read_text())['files']:
  p=SPEC/item['path'];require(sha(p)==item['sha256'],'Specification differs');pin(p);shutil.copy2(p,stage/'specification'/p.name)
 baseline=pd.read_csv(B,keep_default_na=False,low_memory=False);pin(B)
 require(len(baseline)==52098 and baseline.institution_id.is_unique,'Baseline differs')
 baseline['baseline_eligible']=baseline.group_eligible & baseline.eligible_20
 require(baseline.baseline_eligible.sum()==48010,'B2 differs')
 baseline.to_parquet(stage/'inputs/institutions.parquet',index=False)
 c=duckdb.connect(config={'threads':1,'memory_limit':'2GiB','max_temp_directory_size':'1GiB','temp_directory':str(stage/'scratch'),'preserve_insertion_order':False})
 for name,p in [('s',S/'derived_study_records.parquet'),('w',F/'works_eligible.parquet'),('j',J/'data/journal_year_position.parquet')]:
  pin(p);c.execute(f'CREATE VIEW {name} AS SELECT * FROM read_parquet({q(p)})')
 c.execute(f'CREATE VIEW inst AS SELECT * FROM read_parquet({q(stage/"inputs/institutions.parquet")})')
 # Every metadata field uses the same explicitly selected annual work.
 c.execute('''CREATE TEMP TABLE papers AS SELECT s.study_id,w.work_id,w.title,w.doi,
 w.publication_year AS year,try_cast(w.publication_date AS DATE) AS publication_date,
 w.date_status,w.work_type,w.primary_subfield_id AS subfield,w.primary_topic_id,
 s.confirmed_af,s.screen_negative,s.possible_af,s.af_use_label,s.adoption_eligible,
 regexp_replace(w.journal_or_source_id,'^https://openalex.org/','') AS source_id,
 NULL::VARCHAR AS language,'not_collected' AS language_status,
 j.journal_position,j.official_best_Q1,j.position_status,
 'not_collected' AS citation_status,NULL::BIGINT AS citations_12m,NULL::BIGINT AS citations_24m,
 w.publication_date IS NOT NULL AND try_cast(w.publication_date AS DATE)+INTERVAL 12 MONTH<=DATE '2025-12-31' AS mature12,
 w.publication_date IS NOT NULL AND try_cast(w.publication_date AS DATE)+INTERVAL 24 MONTH<=DATE '2025-12-31' AS mature24
 FROM s JOIN w ON s.annual_representative_work_id=w.work_id LEFT JOIN j
 ON regexp_replace(w.journal_or_source_id,'^https://openalex.org/','')=j.source_id AND w.publication_year=j.metric_year''')
 require(c.execute('SELECT count(*)=count(DISTINCT study_id) AND count(*)=4686879 FROM papers').fetchone()[0],'Study/source expansion')
 require(c.execute('SELECT sum(confirmed_af::INT) FROM papers WHERE year BETWEEN 2020 AND 2025').fetchone()[0]==16414,'Core AF differs')
 c.execute(f'COPY papers TO {q(stage/"data/paper_metrics.parquet")} (FORMAT PARQUET,COMPRESSION ZSTD)')
 targets=c.execute("SELECT work_id,study_id,publication_date,year,work_type,subfield,confirmed_af,mature12,mature24 FROM papers WHERE year BETWEEN 2020 AND 2024 ORDER BY work_id").df()
 targets.to_parquet(stage/'data/citation_target_universe.parquet',index=False)
 c.execute('CREATE TEMP TABLE links(study_id VARCHAR,work_id VARCHAR,institution_id VARCHAR,year INTEGER)')
 for year in range(2015,2026):
  rel=J/f'data/study_institution/year_{year}.parquet';pin(rel)
  old=json.loads((J/'run_manifest.json').read_text())['outputs'][str(rel.relative_to(J))]['sha256']
  require(pins[str(rel)]==old,'Frozen membership differs')
  mismatch=c.execute(f'SELECT count(*) FROM read_parquet({q(rel)}) r JOIN papers p USING(study_id) WHERE r.selected_work_id<>p.work_id').fetchone()[0]
  require(mismatch==0,'Representative membership mismatch')
  c.execute(f'''INSERT INTO links SELECT DISTINCT p.study_id,p.work_id,r.institution_id,p.year
   FROM read_parquet({q(rel)}) r JOIN papers p USING(study_id) JOIN inst i USING(institution_id)
   WHERE i.baseline_eligible AND p.year={year}''')
  print('Validated coherent institution links:',year,flush=True)
 require(c.execute('SELECT count(*)=count(DISTINCT(study_id,institution_id)) FROM links').fetchone()[0],'Duplicate links')
 c.execute(f'COPY links TO {q(stage/"inputs/work_institutions.parquet")} (FORMAT PARQUET,COMPRESSION ZSTD)')
 # All usable controls; no role, repeat-AF, credit or minimum-five gate.
 c.execute('''CREATE TEMP TABLE observations AS SELECT l.*,p.* EXCLUDE(study_id,work_id,year),i.country,i."group"
 FROM links l JOIN papers p USING(study_id,work_id,year) JOIN inst i USING(institution_id)''')
 c.execute('''CREATE TEMP TABLE controls AS SELECT institution_id,year,subfield,work_type,
 count(*) AS control_n,avg(journal_position) AS ref_position,
 avg((journal_position>=75)::INT) AS ref_high75,avg((journal_position>=90)::INT) AS ref_high90
 FROM observations WHERE screen_negative AND journal_position IS NOT NULL AND subfield IS NOT NULL
 AND publication_date BETWEEN DATE '2020-01-01' AND DATE '2025-12-31' GROUP BY ALL''')
 c.execute('''CREATE TEMP TABLE pairs AS SELECT o.*,r.control_n,r.ref_position,r.ref_high75,r.ref_high90,
 o.journal_position-r.ref_position AS journal_difference,
 (o.journal_position>=75)::INT-r.ref_high75 AS high75_difference
 FROM observations o LEFT JOIN controls r USING(institution_id,year,subfield,work_type)
 WHERE confirmed_af AND year BETWEEN 2020 AND 2025''')
 c.execute(f'COPY pairs TO {q(stage/"data/matched_comparisons.parquet")} (FORMAT PARQUET,COMPRESSION ZSTD)')
 c.execute(f'''COPY (SELECT o.study_id,o.work_id,o.institution_id,o.year,o.publication_date,o.subfield,o.work_type,o.journal_position
 FROM observations o WHERE screen_negative AND journal_position IS NOT NULL AND subfield IS NOT NULL
 AND publication_date BETWEEN DATE '2020-01-01' AND DATE '2025-12-31') TO {q(stage/'data/usable_control_links.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)''')
 c.execute('''CREATE TEMP TABLE institution_metrics AS SELECT institution_id,country,"group",count(*) af_links,
 avg(journal_position) af_position,avg(ref_position) ref_position,avg(journal_difference) difference,
 avg(high75_difference)*100 high75_difference_pp
 FROM pairs WHERE year<=2024 AND publication_date BETWEEN DATE '2020-01-01' AND DATE '2024-12-31'
 AND journal_position IS NOT NULL AND control_n>=1 GROUP BY ALL''')
 c.execute(f'COPY institution_metrics TO {q(stage/"data/institution_metrics.parquet")} (FORMAT PARQUET)')
 c.execute('''CREATE TEMP TABLE events AS SELECT i.institution_id,i.country,i."group",
 coalesce(bool_or(o.confirmed_af),false) af_confirmed,
 coalesce(bool_or(o.confirmed_af OR o.possible_af OR o.af_use_label='uncertain' OR (o.af_use_label='yes' AND o.adoption_eligible='uncertain')),false) af_possible,
 coalesce(bool_or(o.confirmed_af AND o.journal_position>=75),false) venue_confirmed,
 coalesce(bool_or((o.confirmed_af AND (o.journal_position>=75 OR o.journal_position IS NULL))
 OR ((o.possible_af OR o.af_use_label='uncertain' OR (o.af_use_label='yes' AND o.adoption_eligible='uncertain')) AND (o.journal_position>=75 OR o.journal_position IS NULL))),false) venue_possible
 FROM inst i LEFT JOIN observations o ON i.institution_id=o.institution_id AND o.year BETWEEN 2020 AND 2024
 WHERE i.baseline_eligible GROUP BY ALL''')
 c.execute(f'COPY events TO {q(stage/"data/coverage_events.parquet")} (FORMAT PARQUET)')
 country=c.execute('''SELECT country,"group",count(*) denominator,sum(af_confirmed::INT) af_confirmed_n,sum(af_possible::INT) af_possible_n,
 sum(venue_confirmed::INT) venue_confirmed_n,sum(venue_possible::INT) venue_possible_n,
 avg(af_confirmed::INT)*100 af_lower,avg(af_possible::INT)*100 af_upper,
 avg(venue_confirmed::INT)*100 venue_lower,avg(venue_possible::INT)*100 venue_upper FROM events GROUP BY ALL ORDER BY 1,2''').df()
 require(len(country)==204 and country.denominator.sum()==48010,'Coverage denominator lost')
 require((country.af_lower<=country.af_upper).all() and (country.venue_lower<=country.venue_upper).all(),'Bounds invalid')
 country.to_csv(stage/'tables/country_coverage.csv',index=False)
 country.groupby('group')[['af_lower','af_upper','venue_lower','venue_upper']].mean().to_csv(stage/'tables/country_equal_coverage.csv')
 c.execute('''SELECT "group",count(*) institutions,sum(af_links) links,avg(af_position) AF,avg(ref_position) reference,
 avg(difference) difference,avg(high75_difference_pp) high75_difference_pp FROM institution_metrics GROUP BY 1 ORDER BY 1''').df().to_csv(stage/'tables/journal_maximum_assessable_point_estimates.csv',index=False)
 c.execute('SELECT year,work_type,count(*) studies,sum(confirmed_af::INT) af,count(journal_position) metric_known,count(*) FILTER(WHERE publication_date IS NULL) date_missing FROM papers GROUP BY ALL ORDER BY 1,2').df().to_csv(stage/'tables/paper_coverage.csv',index=False)
 c.execute('SELECT "group",year,count(*) af_links,count(journal_position) journal_known,count(*) FILTER(WHERE journal_position IS NOT NULL AND control_n>=1) matched_links,count(*) FILTER(WHERE journal_position IS NOT NULL AND control_n>=5) matched_ge5 FROM pairs GROUP BY ALL ORDER BY 1,2').df().to_csv(stage/'tables/matching_support.csv',index=False)
 cfg=json.loads((SPEC/'analysis_config.template.json').read_text());cfg.update(document_status='branch_specific_foundations',analysis_can_run=False)
 cfg['journal'].update(source='SCImago full annual lists; category-mean SJR percentile',version='2015–2025 frozen annual grid')
 cfg['comparisons']['minimum_controls']=1;cfg['citations']['min_reference_cell_size']=100
 cfg['baseline'].update(framework_path='inputs/institutions.parquet',grouping_version='Finding2 v7 B2: 48010 institutions,68 countries')
 cfg['readiness']={'journal_maximum_assessable_point_estimates':True,'common_main_a_b':False,'fixed_window_citations':False,'bootstrap':False,'case_evidence':False}
 dump(stage/'analysis_config.json',cfg)
 report={'status':'foundations_prepared_not_final_analysis','targets_2020_2024':len(targets),'AF_targets_2020_2024':int(targets.confirmed_af.sum()),'citation_edges_complete':False,'fixed_B2':48010,'countries':68,'main_a_b_common_sample_ready':False,'no_paid_calls':True,'old_sources_modified':False,'prepared_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'input_pins':pins}
 dump(stage/'preparation_report.json',report)
 shutil.copy2(__file__,stage/'code'/Path(__file__).name)
 c.close()
 dump(stage/'manifest.json',{str(p.relative_to(stage)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in stage.rglob('*') if p.is_file() and 'scratch' not in p.parts and p.name!='manifest.json'})
 stage.rename(OUT);print(json.dumps(report|{'input_pins':'saved in report'},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
