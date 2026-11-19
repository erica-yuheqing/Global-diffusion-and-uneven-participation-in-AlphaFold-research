"""N01 actual observed author/role/affiliation reconstruction from pinned local data."""
from common import *
def main():
    require(not (ROOT/'provenance/N01_complete.json').exists(),'N01 already committed')
    cat=json.loads((ROOT/'provenance/input_catalog.json').read_text());out=ROOT/'inputs/normalized';c=connect()
    c.execute(f'CREATE TABLE f AS SELECT *,CASE WHEN study_group=\'AF\' THEN \'AF\' ELSE \'reference\' END AS corpus FROM read_parquet({q(ROOT/"inputs/local/flags.parquet")})')
    require(c.execute('SELECT count(*)=count(DISTINCT study_id) AND count(*)=count(DISTINCT work_id) FROM f').fetchone()[0],'Study/work mapping not unique')
    normid=lambda name,p:f"CASE WHEN regexp_matches(CAST({name} AS VARCHAR),'{p}[0-9]+$') THEN regexp_extract(CAST({name} AS VARCHAR),'({p}[0-9]+)$',1) ELSE NULL END"
    files='['+','.join(q(p) for p in cat['country_shards'])+']'
    print('N01: scanning 72 pinned author-country shards...',flush=True)
    c.execute(f'''CREATE TABLE raw AS SELECT DISTINCT {normid('r.work_id','W')} AS work_id,{normid('r.author_id','A')} AS author_id,
       nullif(upper(trim(r.country_code)),'') AS country_code,r.country_source,lower(trim(r.author_position)) AS author_position
       FROM read_parquet({files}) r SEMI JOIN f ON {normid('r.work_id','W')}=f.work_id''')
    c.execute('''CREATE TABLE ac AS WITH direct AS (SELECT DISTINCT work_id,author_id FROM raw WHERE regexp_full_match(country_code,'[A-Z]{2}') AND country_source='authorship_countries_field')
      SELECT DISTINCT r.work_id,r.author_id,r.country_code,CASE WHEN d.work_id IS NOT NULL THEN 'authorship_countries_field' ELSE 'institution_country_code' END AS country_source
      FROM raw r LEFT JOIN direct d USING(work_id,author_id) WHERE r.author_id IS NOT NULL AND regexp_full_match(r.country_code,'[A-Z]{2}') AND
      (r.country_source='authorship_countries_field' OR d.work_id IS NULL AND r.country_source='institution_country_code')''')
    c.execute(f'''CREATE TABLE au AS SELECT f.study_id,f.work_id,a.author_id,row_number() OVER(PARTITION BY f.study_id ORDER BY a.author_id)-1 AS author_index
      FROM (SELECT DISTINCT work_id,author_id FROM read_parquet({q(cat['authorships'])}) WHERE author_id IS NOT NULL) a JOIN f USING(work_id)''')
    c.execute('''CREATE TABLE astats AS SELECT study_id,count(*) AS observed_author_count FROM au GROUP BY 1''')
    c.execute('''CREATE TABLE countries AS SELECT a.study_id,a.work_id,a.author_id,a.author_index,x.country_code,x.country_source,1.0/count(*) OVER(PARTITION BY a.study_id,a.author_id) AS country_weight
       FROM au a JOIN ac x USING(work_id,author_id)''')
    c.execute('''CREATE TABLE cov AS SELECT study_id,count(DISTINCT author_id) AS authors_with_country FROM countries GROUP BY 1''')
    c.execute(f'''CREATE TABLE dates AS SELECT study_id,publication_date FROM read_parquet({q(cat['study_records'])})''')
    c.execute('''CREATE TABLE studies AS SELECT f.*,a.observed_author_count,coalesce(v.authors_with_country,0) AS authors_with_country,d.publication_date,
       f.common_country_candidate AND f.author_fraction_eligible AND f.observed_country_assignment_complete AS primary_eligible,
       f.observed_author_IDs_complete AND a.observed_author_count=f.known_author_ids AND a.observed_author_count>=1 AS observed_IDs_consistent
       FROM f LEFT JOIN astats a USING(study_id) LEFT JOIN cov v USING(study_id) LEFT JOIN dates d USING(study_id)''')
    bad=c.execute('''SELECT study_id,work_id,known_author_ids,observed_author_count,authors_with_country,observed_IDs_consistent,first_id,last_id FROM studies WHERE primary_eligible AND (NOT observed_IDs_consistent OR authors_with_country<>observed_author_count OR first_id IS NULL OR last_id IS NULL)''').df()
    bad.to_csv(ROOT/'tables/N01_reconstruction_differences.csv',index=False)
    require(len(bad)==0,'Primary eligible IDs/countries/roles do not reconstruct; see N01_reconstruction_differences.csv: '+str(len(bad)))
    c.execute('ALTER TABLE studies ADD COLUMN strict_pairing_eligible BOOLEAN')
    c.execute('UPDATE studies SET strict_pairing_eligible=primary_eligible AND observed_author_count>=2 AND first_id<>last_id')
    conflicts=c.execute('SELECT study_id,work_id,corpus,publication_year,known_author_ids,first_id,last_id,position_status FROM studies WHERE primary_eligible AND NOT strict_pairing_eligible ORDER BY study_id').df()
    conflicts.to_csv(ROOT/'tables/legacy_same_author_role_exclusions.csv',index=False)
    require(len(conflicts)==6 and conflicts.corpus.eq('reference').all(),'Unexpected additional legacy role conflicts')
    c.execute('''CREATE TABLE roles AS SELECT study_id,work_id,first_id AS first_author_id,last_id AS last_author_id,
       CASE WHEN first_pairs=1 AND first_id IS NOT NULL AND unknown_position_pairs=0 AND conflicting_known_ids=0 THEN 'explicit_unique' ELSE 'not_explicit_unique' END AS first_position_status,
       CASE WHEN last_pairs=1 AND last_id IS NOT NULL AND unknown_position_pairs=0 AND conflicting_known_ids=0 THEN 'explicit_unique' ELSE 'not_explicit_unique' END AS last_position_status,
       'unavailable' AS shared_contribution_status FROM studies''')
    c.execute('''CREATE TABLE role_countries AS SELECT s.study_id,x.country_code,'first' AS role,x.country_weight AS credit FROM studies s JOIN countries x ON s.study_id=x.study_id AND s.first_id=x.author_id
       UNION ALL SELECT s.study_id,x.country_code,'last',x.country_weight FROM studies s JOIN countries x ON s.study_id=x.study_id AND s.last_id=x.author_id''')
    c.execute(f'''CREATE TABLE credit AS SELECT f.study_id,w.country_code,'country_output' AS channel,cast(w.country_weight AS DOUBLE) AS credit FROM f JOIN read_parquet({q(cat['work_countries'])}) w USING(work_id)
       UNION ALL SELECT x.study_id,x.country_code,'author_output',sum(x.country_weight/s.observed_author_count) FROM countries x JOIN studies s USING(study_id) GROUP BY 1,2
       UNION ALL SELECT study_id,country_code,role,credit FROM role_countries''')
    # Reconstructed author and position credits must match frozen estimates study by study.
    c.execute(f'''CREATE TABLE oldcredit AS SELECT study_id,country_code,CASE WHEN role='output' THEN 'country_output' ELSE role END AS channel,credit FROM read_parquet({q(ROOT/'inputs/local/country_credit.parquet')})
       UNION ALL SELECT study_id,country_code,'author_output',credit FROM read_parquet({q(ROOT/'inputs/local/author_fraction_credit.parquet')})''')
    difference=c.execute('''WITH n AS (SELECT z.* FROM credit z JOIN studies s USING(study_id) WHERE s.primary_eligible),o AS (SELECT z.* FROM oldcredit z JOIN studies s USING(study_id) WHERE s.primary_eligible)
       SELECT coalesce(n.study_id,o.study_id) AS study_id,coalesce(n.country_code,o.country_code) AS country_code,coalesce(n.channel,o.channel) AS channel,
          n.credit AS new_credit,o.credit AS legacy_credit FROM n FULL OUTER JOIN o USING(study_id,country_code,channel) WHERE abs(coalesce(n.credit,0)-coalesce(o.credit,0))>1e-11''').df()
    difference.to_csv(ROOT/'tables/N01_credit_differences.csv',index=False)
    require(difference.empty or difference.channel.isin(['first','last']).all(),'Country/author participation credit failed to reconstruct')
    require(difference.empty or difference.study_id.isin(conflicts.study_id).all(),'New role credit differs outside explicitly excluded legacy records')
    diff=(len(difference),float((difference.new_credit.fillna(0)-difference.legacy_credit.fillna(0)).abs().max()) if len(difference) else 0.)
    c.execute(f'''CREATE TABLE ai AS SELECT DISTINCT a.study_id,a.work_id,a.author_id,a.author_index,i.institution_id,i.country_code AS institution_country
       FROM au a JOIN read_parquet({q(cat['author_institutions'])}) i USING(work_id,author_id)
       WHERE i.institution_id IS NOT NULL AND regexp_full_match(i.country_code,'[A-Z]{{2}}')''')
    for name,table in [('studies','studies'),('authors','au'),('authors_countries','countries'),('roles','roles'),('authors_institutions','ai'),('credit','credit')]:
        c.execute(f'COPY {table} TO {q(out/(name+".parquet"))} (FORMAT PARQUET,COMPRESSION ZSTD)')
    group=read('country_baseline.csv');g=group[['country','baseline_country_studies','eligible_20','context']].copy();eligible=g.eligible_20.astype(str).str.lower().eq('true')
    g['baseline_group']=np.where(eligible,g.context.map({'High':'higher','Middle':'middle','Low':'lower'}),'outside');g=g.rename(columns={'country':'country_code'});g.to_parquet(out/'country_groups.parquet',index=False)
    read('institution_baseline.csv').to_parquet(out/'institution_groups.parquet',index=False)
    primary=c.execute('SELECT * FROM studies WHERE primary_eligible ORDER BY study_id').df();primary=add_weights(primary,support(primary));primary.to_parquet(out/'primary_studies.parquet',index=False)
    require(primary.groupby('corpus').size().to_dict()=={'AF':5087,'reference':438479},'Primary full counts')
    require(primary[primary.supported].groupby('corpus').size().to_dict()=={'AF':5087,'reference':332764},'Primary support counts')
    require(int(support(primary).supported.sum())==173,'Common cells not173')
    support(primary).to_csv(ROOT/'tables/primary_support.csv',index=False)
    primary[['study_id','work_id','corpus']+KEY+['publication_date','supported','weight']].to_csv(ROOT/'tables/study_ids_and_weights.csv',index=False)
    strict=primary[primary.strict_pairing_eligible].drop(columns=['supported','w_AF','w_reference','weight']);strict=add_weights(strict,support(strict));strict.to_parquet(out/'pairing_studies.parquet',index=False)
    strict[['study_id','work_id','corpus']+KEY+['publication_date','supported','weight']].to_csv(ROOT/'tables/pairing_study_ids_and_weights.csv',index=False)
    # Explicit qualification/exclusions for all binary records, not a manufactured author table for missing members.
    c.execute(f'''COPY (SELECT a.study_id,a.work_id,a.study_group AS original_corpus,a.publication_year,a.work_type,a.primary_subfield_id,
        a.output_countries,a.common_country_candidate,s.primary_eligible,s.observed_author_count,s.authors_with_country,s.observed_IDs_consistent,
        CASE WHEN a.output_countries<2 THEN 'not_observed_international' WHEN NOT a.common_country_candidate THEN 'common_roles_ineligible'
          WHEN NOT coalesce(s.primary_eligible,false) THEN 'author_completeness_ineligible' ELSE 'primary_full_eligible' END AS reason
        FROM read_parquet({q(ROOT/'inputs/local/all_audits.parquet')}) a LEFT JOIN studies s USING(study_id))
        TO {q(ROOT/'tables/study_eligibility.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)''')
    annual=c.execute('''SELECT corpus,publication_year,count(*) AS international,count(*) FILTER(WHERE common_country_candidate) AS common_roles,count(*) FILTER(WHERE primary_eligible) AS author_complete FROM studies GROUP BY 1,2 ORDER BY 1,2''').df();save('annual_author_coverage',annual)
    counts=c.execute('SELECT corpus,count(*) AS international,count(*) FILTER(WHERE common_country_candidate) AS common_roles,count(*) FILTER(WHERE primary_eligible) AS author_complete FROM studies GROUP BY 1').df()
    audits={name:int(c.execute('SELECT count(*) FROM '+name).fetchone()[0]) for name in ['studies','au','countries','ai','credit']}
    dump(ROOT/'provenance/N01_complete.json',dict(status='PASS_WITH_EXPLICIT_LEGACY_ROLE_DIFFERENCE',counts=counts.to_dict('records'),normalized_rows=audits,primary_credit_difference_count=diff[0],legacy_common_cells=173,legacy_study_weight_hash=sha(ROOT/'tables/study_ids_and_weights.csv'),strict_pairing_counts=strict.groupby('corpus').size().to_dict(),strict_supported_counts=strict[strict.supported].groupby('corpus').size().to_dict(),strict_common_cells=int(support(strict).supported.sum()),strict_study_weight_hash=sha(ROOT/'tables/pairing_study_ids_and_weights.csv'),legacy_same_author_exclusions=conflicts.to_dict('records'),scope='Observed frozen records; six legacy reference single-author/multi-country studies excluded from strict new pairing, Figure4 scope awaiting user choice; no relabeling',API_calls=0,LLM_calls=0))
    c.close()
    # Read the committed normalized author snapshot in an independent connection for this large join.
    verify_affiliations(cat,out,audits)
    report=json.loads((ROOT/'provenance/N01_complete.json').read_text());report['normalized_rows']=audits;report['strict_credit_difference_count']=0;report['scope']='Strict distinct-author Figure4/Figure5 reestimate approved 2026-10-30; legacy snapshots retained; all credit differences confined to six excluded legacy records';dump(ROOT/'provenance/N01_complete.json',report)
    print('N01 PASS:',audits,flush=True)
def verify_affiliations(cat,out,audits):
    d=connect();d.execute(f'''CREATE TABLE links AS SELECT DISTINCT a.study_id,a.work_id,a.author_id,a.author_index,i.institution_id,i.country_code AS institution_country
       FROM read_parquet({q(out/'authors.parquet')}) a JOIN read_parquet({q(cat['author_institutions'])}) i ON a.work_id=i.work_id AND a.author_id=i.author_id
       WHERE i.institution_id IS NOT NULL AND regexp_full_match(i.country_code,'[A-Z]{{2}}')''')
    n=d.execute('SELECT count(*) FROM links').fetchone()[0];require(n>0,'Observed author-institution linkage unexpectedly empty')
    d.execute(f'COPY links TO {q(out/"authors_institutions.parquet")} (FORMAT PARQUET,COMPRESSION ZSTD)');audits['ai']=n;d.close()
if __name__=='__main__':main()
