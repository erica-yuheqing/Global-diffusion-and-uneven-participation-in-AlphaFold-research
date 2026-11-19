"""All observed affiliations, before B2 projection; missingness is explicit."""
from common import *
def main():
 c=con()
 for n,f in [('p','paper_base.parquet'),('f','author_affiliations.parquet'),('u','authorships.parquet'),('i','institutions.parquet')]:view(c,n,I/f)
 c.execute('''CREATE TEMP TABLE imported_authors AS SELECT u.work_id,count(*) n_authorship_rows,
 count(DISTINCT u.author_id) known_author_IDs,count(*) FILTER(WHERE u.author_id IS NULL) missing_author_ID_rows
 FROM u SEMI JOIN p USING(work_id) GROUP BY 1''')
 c.execute('''CREATE TEMP TABLE observed AS SELECT f.work_id,count(DISTINCT f.author_id) assigned_author_IDs,
 count(DISTINCT f.institution_id) n_institutions,count(DISTINCT f.country_code) n_countries,
 count(*) FILTER(WHERE f.country_code IS NULL OR f.country_code='') missing_country_rows
 FROM f SEMI JOIN p USING(work_id) GROUP BY 1''')
 c.execute('''CREATE TEMP TABLE unassigned AS SELECT u.work_id,count(DISTINCT u.author_id) unassigned_author_IDs
 FROM (SELECT u.work_id,u.author_id FROM u SEMI JOIN p USING(work_id) WHERE u.author_id IS NOT NULL) u
 ANTI JOIN f ON u.work_id=f.work_id AND u.author_id=f.author_id GROUP BY 1''')
 parquet(c,'''SELECT p.study_id,p.work_id,p.year,coalesce(u.n_authorship_rows,0) n_authorship_rows,
 coalesce(u.known_author_IDs,0) known_author_IDs,coalesce(u.missing_author_ID_rows,0) missing_author_ID_rows,
 coalesce(o.assigned_author_IDs,0) assigned_author_IDs,coalesce(o.n_institutions,0) n_institutions,
 coalesce(o.n_countries,0) n_countries,coalesce(o.missing_country_rows,0) missing_country_rows,
 coalesce(unassigned.unassigned_author_IDs,0) unassigned_author_IDs,
 CASE WHEN u.known_author_IDs>0 THEN o.assigned_author_IDs::DOUBLE/u.known_author_IDs END observed_author_affiliation_coverage,
 coalesce(u.known_author_IDs>0 AND u.missing_author_ID_rows=0 AND coalesce(unassigned.unassigned_author_IDs,0)=0 AND o.assigned_author_IDs=u.known_author_IDs,false) observed_author_roster_covered,
 false AS publisher_roster_completeness_certified,'not_collected; observed roster is not global completeness' completeness_status
 FROM p LEFT JOIN imported_authors u USING(work_id) LEFT JOIN observed o USING(work_id) LEFT JOIN unassigned USING(work_id)''',D/'study_roster_quality.parquet')
 parquet(c,'''SELECT p.study_id,p.work_id,p.year,f.institution_id,
 min(f.country_code) FILTER(WHERE f.country_code IS NOT NULL) observed_country,
 count(DISTINCT f.country_code) observed_country_count,coalesce(bool_or(i.baseline_eligible),false) B2_eligible
 FROM f JOIN p USING(work_id) LEFT JOIN i ON f.institution_id=i.institution_id WHERE f.institution_id IS NOT NULL
 GROUP BY 1,2,3,4''',D/'study_institutions_all.parquet')
 view(c,'r',D/'study_roster_quality.parquet');view(c,'s',D/'study_institutions_all.parquet')
 distribution=c.execute('''SELECT year,n_institutions,count(*) studies,sum(n_institutions*(n_institutions-1)/2)::BIGINT potential_full_pair_studies FROM r GROUP BY 1,2''').df();table('network_team_size_distribution',distribution)
 b2=c.execute('''SELECT study_id,count(*) m_boundary FROM s WHERE B2_eligible GROUP BY 1''').df();c.register('b2',b2)
 table('network_pair_size_preflight',c.execute('''SELECT r.year,count(*) studies,max(r.n_institutions) largest_full_team,
 sum(r.n_institutions*(r.n_institutions-1)/2)::BIGINT full_pair_rows,sum(coalesce(b.m_boundary*(b.m_boundary-1)/2,0))::BIGINT B2_pair_rows,
 sum(r.observed_author_roster_covered::INT) observed_roster_covered_studies FROM r LEFT JOIN b2 b USING(study_id) GROUP BY 1 ORDER BY 1''').df())
 dump(Q/'roster_audit.json',{'study_count':c.execute('SELECT count(*) FROM r').fetchone()[0],'unique_observed_institutions':c.execute('SELECT count(DISTINCT institution_id) FROM s').fetchone()[0],
 'all_observed_IDs_before_B2_projection':True,'publisher_completeness_certified':False,'source_flag_absent_not_invented':True,
 'main_partner_quality':'requires all imported known author IDs assigned plus all observed partners scored; source truncation not certified',
 'strict_publisher_certified_branch':'not_computable: upstream completeness/truncation flags not collected'})
 print('FULL OBSERVED ROSTERS AND PAIR-SIZE AUDIT COMPLETE',flush=True)
if __name__=='__main__':main()
