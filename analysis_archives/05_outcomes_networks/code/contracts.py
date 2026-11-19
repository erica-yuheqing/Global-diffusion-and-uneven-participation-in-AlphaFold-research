"""Portable, queryable logical contracts and complementary support tables."""
from common import *
import os
def main():
 os.chdir(P);c=con();out=D/'logical';out.mkdir(exist_ok=True)
 for n,path in [('i',I/'institutions.parquet'),('p',I/'paper_base.parquet'),('a',D/'matched_comparisons.parquet'),('m',D/'paper_metrics.parquet'),('r',D/'control_links.parquet'),('s',D/'study_institutions_all.parquet'),('q',D/'study_roster_quality.parquet'),('j',I/'journal_year_positions.parquet'),('cat',I/'journal_category_positions.parquet'),('e',I/'citation_edges.parquet'),('quality',D/'citation_quality.parquet')]:view(c,n,path)
 c.execute('CREATE VIEW field AS SELECT * FROM read_parquet('+lit(I/'parent_fields.parquet')+')')
 definitions={
 'institutions':'''SELECT institution_id,country,"group" baseline_group,V_i baseline_output,baseline_eligible B2_eligible,'Finding2_v7_B2_fixed' grouping_version FROM i''',
 'studies':'''SELECT p.study_id,p.publication_date,p.date_status date_precision,p.subfield primary_subfield,f.parent_field,p.work_type document_type,CASE WHEN confirmed_af THEN 'confirmed_AF' WHEN screen_negative THEN 'screen_negative' ELSE 'unresolved_source_label' END af_status,p.source_id,'approved_crosswalk.parquet; coherent representative' version_bridge FROM p LEFT JOIN field f ON p.subfield=f.subfield''',
 'study_institutions':'''SELECT s.study_id,s.institution_id,'observed_provider_affiliation' affiliation_status,s.observed_country country,s.B2_eligible,'publisher_completeness_not_collected; observed coverage in study_roster_quality' institution_list_completeness_status FROM s''',
 'network_nodes':"SELECT * FROM read_parquet('source_data/networks/*/nodes.parquet')",
 'network_edges':"SELECT * EXCLUDE(filename),regexp_extract(filename,'networks/([^/]+)/edges',1) network_id FROM read_parquet('source_data/networks/*/edges.parquet',union_by_name=true,filename=true)",
 'journal_year_positions':'''SELECT j.source_id,j.metric_year AS "year",cat.category,cat.sjr SJR,cat.sjr_category_percentile percentile,'SCImago_annual_2015_2025_exact_ISSN_frozen' mapping_version,j.position_status status FROM j JOIN cat USING(scimago_source_id,metric_year)''',
 'citation_edges':'''SELECT citing_study_id,study_id cited_study_id,citing_publication_date,'deduplicated_approved_study_pair; quality isolated in citation_quality' edge_status,'approved_crosswalk frozen; original citing_work_id retained in inputs' bridge_version FROM e''',
 'citation_quality':'SELECT * EXCLUDE(year) FROM quality'
 }
 partner=[];points=[]
 for outcome in ['journal','citation']:
  for kind in ['own','partner']:
   sample='degree_'+kind;view(c,'f',D/f'network_records_{outcome}_{sample}.parquet');view(c,'pt',D/f'network_points_{outcome}_{sample}.parquet');metric='journal_position' if outcome=='journal' else 'percentile_12m'
   z=c.execute('SELECT f.institution_id,count(DISTINCT r.study_id) n_control_unique FROM f JOIN r USING(institution_id,year,subfield,work_type) WHERE r.'+metric+' IS NOT NULL GROUP BY 1').df();b=c.execute('SELECT * FROM pt').df().merge(z,on='institution_id',validate='one_to_one');b['sample_id']=sample;b['outcome']=outcome;b['log_degree']=b.institution_id.map(c.execute('SELECT institution_id,avg(x_log) x FROM f GROUP BY 1').df().set_index('institution_id').x);b['partner_mean_percentile']=b.institution_id.map(c.execute('SELECT institution_id,avg(partner_mean_percentile) x FROM f GROUP BY 1').df().set_index('institution_id').x);b['partner_sample_status']='valid_observed_roster_all_partners_scored' if kind=='partner' else 'own_baseline_valid';points.append(b)
  ps=pd.read_parquet(D/'partners_degree.parquet');support=pd.read_parquet(D/f'AF_records_{"journal_full2025" if outcome=="journal" else "citation_max"}.parquet')[['study_id','institution_id']];ps=ps.merge(support,on=['study_id','institution_id'],validate='one_to_one');ps['sample_id']='outcome_specific_maximum';ps['outcome']=outcome;partner.append(ps)
 pd.concat(partner,ignore_index=True).to_parquet(out/'partner_scores.parquet',index=False);pd.concat(points,ignore_index=True).to_parquet(out/'network_institution_outcomes.parquet',index=False)
 definitions['partner_scores']="SELECT * FROM read_parquet('source_data/logical/partner_scores.parquet')"
 definitions['network_institution_outcomes']="SELECT * FROM read_parquet('source_data/logical/network_institution_outcomes.parquet')"
 definitions['comparison_links']="SELECT * FROM read_parquet('source_data/comparison_links/*/*.parquet')"
 models=read_models();models['model_id_original']=models.model_id;models['model_id']=models.model_id.fillna('descriptive')+'::'+models.group.fillna('all')+'::'+models.metric.fillna('not_applicable');models['formula']=models.formula.fillna('M0: equal-institution D_i ~ continuous x; exact scale in unit; adjusted formulas/designs in qa/design_*.json');models['scale']=models.scale.fillna(models.unit);models.to_parquet(out/'network_model_results.parquet',index=False);definitions['network_model_results']="SELECT * FROM read_parquet('source_data/logical/network_model_results.parquet')"
 # Freeze query definitions, making large immutable tables queryable without duplicating them.
 prelude=[]
 for name,path in [('i','inputs/institutions.parquet'),('p','inputs/paper_base.parquet'),('s','source_data/study_institutions_all.parquet'),('j','inputs/journal_year_positions.parquet'),('cat','inputs/journal_category_positions.parquet'),('e','inputs/citation_edges.parquet'),('quality','source_data/citation_quality.parquet'),('field','inputs/parent_fields.parquet')]:prelude.append('CREATE OR REPLACE VIEW '+name+" AS SELECT * FROM read_parquet('"+path+"');")
 sql=prelude+['CREATE OR REPLACE VIEW contract_'+name+' AS '+query+';' for name,query in definitions.items()];(out/'views.sql').write_text('\n'.join(sql)+'\n')
 contract=json.loads((P/'specification/config/input_data_contract.json').read_text());audit=[]
 for item in contract['tables']:
  name=item['name'];query=definitions[name];columns=c.execute('SELECT * FROM ('+query+') LIMIT 0').df().columns;require(set(item['required_columns'])<=set(columns),'Contract columns: '+name)
  count=c.execute('SELECT count(*) FROM ('+query+')').fetchone()[0];key=','.join(item['primary_key']);duplicate=c.execute('SELECT count(*) FROM (SELECT '+key+',count(*) n FROM ('+query+') GROUP BY '+key+' HAVING n>1)').fetchone()[0];require(duplicate==0,'Contract key duplicates: '+name);audit.append(dict(table=name,rows=count,required_columns_present=True,key_duplicate_groups=duplicate,representation='portable_SQL_view; physical data referenced in same package'))
 dump(Q/'logical_contract_schema_audit.json',audit)
 # Source coverage, author/affiliation/activities, split by full dimensions.
 view(c,'st',D/'stratified_AF_links.parquet');view(c,'act',D/'activities.parquet')
 table('T_SI2_source_coverage',c.execute('''SELECT i.country,i."group",m.year,m.subfield,m.work_type,m.language_status,count(*) eligible_study_institution_links,
 count(DISTINCT m.study_id) eligible_studies,sum(m.confirmed_af::INT) confirmed_AF_links,count(m.journal_position) journal_known_links,count(m.percentile_12m) citation_known_links,
 sum(q.observed_author_roster_covered::INT) observed_author_roster_covered_links,sum((q.n_countries>0)::INT) observed_country_known_links,
 sum((m.confirmed_af AND ac.study_id IS NOT NULL)::INT) AF_activity_layer_present_links FROM m JOIN read_parquet('inputs/work_institutions.parquet') l USING(study_id,work_id,year)
 JOIN i USING(institution_id) JOIN q USING(study_id) LEFT JOIN (SELECT DISTINCT study_id FROM act) ac USING(study_id) WHERE i.baseline_eligible GROUP BY 1,2,3,4,5,6''').df())
 table('T_SI2_role_cooperation_coverage',c.execute('SELECT "group",year,role_class,collaboration,count(*) AF_links,count(DISTINCT study_id) AF_studies,count(DISTINCT institution_id) institutions FROM st GROUP BY 1,2,3,4').df())
 context=[];correlations=[]
 for outcome in ['journal','citation']:
  view(c,'n',D/f'network_records_{outcome}_degree_partner.parquet')
  z=c.execute('''SELECT n.institution_id,n."group",first(V_i) V_i,first(x_log) log_degree,avg(m_all) mean_team_size,avg((n_countries>=2)::INT) international_share,
  avg(partner_mean_percentile) partner_mean,count(*) AF_links FROM n JOIN q USING(study_id) GROUP BY 1,2''').df();z['outcome']=outcome;context.append(z)
  for group in ['L','M','H']:
   b=z[z.group.eq(group)].copy();b['log_baseline_output']=np.log1p(b.V_i)
   for method in ['pearson','spearman']:
    corr=b[['log_baseline_output','log_degree','mean_team_size','international_share','partner_mean']].corr(method=method)
    for x in corr.columns:
     for y in corr.columns:correlations.append(dict(outcome=outcome,group=group,method=method,x=x,y=y,correlation=corr.loc[x,y],institutions=len(b)))
 table('T_SI8_context',pd.concat(context,ignore_index=True));table('T_SI8_context_correlations',pd.DataFrame(correlations))
 table('T_SI6_absolute_primary',pd.read_csv(T/'primary_estimates.csv'))
 # Table entry points preserve complete detailed files, not compressed narrative substitutes.
 table('T_SI3',pd.read_csv(T/'T_SI3_estimates.csv'));table('T_SI6',pd.read_csv(T/'T_SI6_coverage.csv'));table('T_SI8',pd.read_csv(T/'T_SI8_network_registry.csv'));table('T_SI9',models)
 # Restore inherited case evidence annotations; candidate screen never grants main-case approval.
 candidates=pd.read_csv(P/'cases/candidates.csv');chosen=pd.read_csv(P/'cases/pathways.csv');keys=set(zip(chosen.work_id,chosen.focal_institution_id));selected=pd.Series([(w,i) in keys for w,i in zip(candidates.work_id,candidates.institution_id)],index=candidates.index);candidates['selected_for_case_review']=selected;candidates['selected_for_main_case']=False;candidates.loc[selected,'fulltext_review_status']='direct_component_evidence_assisted_review';candidates.loc[selected,'exclusion_from_main_case_reason']='focal affiliation not publisher-verified; supplementary evidence review only';candidates.to_csv(P/'cases/candidates.csv',index=False);table('T_SI7',candidates)
 print('TWELVE LOGICAL CONTRACTS AND COMPLETE SUPPORT TABLES VERIFIED',flush=True)
def read_models():return pd.read_csv(T/'T_SI9_network_models.csv')
if __name__=='__main__':main()
