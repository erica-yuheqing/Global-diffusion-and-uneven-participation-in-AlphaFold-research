"""Traceable country matrices, strict domestic institutions and full flow audits."""
from common import *
def main():
    if (ROOT/'provenance/ancillary_complete.json').exists():return
    c=connect();d=ROOT/'inputs/normalized'
    for n in ['analysis_members','studies','authors','authors_countries','roles','country_groups','institution_groups','role_country_institution_credit','country_pair_credit','country_pair_expected']:
        c.execute(f'CREATE VIEW {n} AS SELECT * FROM read_parquet({q(d/(n+".parquet"))})')
    for n in ['all_audits','institution_credit','institution_members']:
        c.execute(f'CREATE VIEW {n} AS SELECT * FROM read_parquet({q(ROOT/"inputs/local"/(n+".parquet"))})')
    # Full country grid includes absent observations; expected 0 is not missing.
    codes=read('country_registry.csv')[['country_code']].drop_duplicates();c.register('codes',codes)
    for n in ['country_pair_credit','country_pair_expected']:
        c.execute(f'''CREATE TABLE agg_{n} AS SELECT p.corpus,z.first_country,z.last_country,
          sum(z.credit) AS raw_credit,sum(z.credit*p.weight) AS standardized_credit,
          count(*) FILTER(WHERE z.credit>0) AS n_positive_raw,count(*) FILTER(WHERE z.credit>0 AND p.supported) AS n_positive_supported
          FROM {n} z JOIN analysis_members p USING(study_id) GROUP BY 1,2,3''')
    p=norm('analysis_members.parquet');rows=[]
    for setting in ['raw_full','standardized']:
      vs=[]
      for cp in CORPORA:
        w=p.loc[p.corpus.eq(cp),'weight'].to_numpy() if setting=='standardized' else np.ones(p.corpus.eq(cp).sum());den=w.sum();ess=div(den**2,(w*w).sum()).item();field='standardized_credit' if setting=='standardized' else 'raw_credit'
        z=c.execute(f'''SELECT a.country_code AS first_country,b.country_code AS last_country,
          coalesce(o.{field},0)/{den} AS observed_share,coalesce(e.{field},0)/{den} AS expected_share,
          coalesce(o.n_positive_raw,0) AS n_positive_raw,coalesce(o.n_positive_supported,0) AS n_positive_supported
          FROM codes a CROSS JOIN codes b LEFT JOIN agg_country_pair_credit o ON o.corpus={q(cp)} AND a.country_code=o.first_country AND b.country_code=o.last_country
          LEFT JOIN agg_country_pair_expected e ON e.corpus={q(cp)} AND a.country_code=e.first_country AND b.country_code=e.last_country''').df()
        z['corpus']=cp;z['setting']=setting;z['O_minus_E_pp']=100*(z.observed_share-z.expected_share);z['sum_weights']=den;z['ESS']=ess;z['n_studies']=int((w>0).sum());z['expected_zero']=z.expected_share.eq(0);z['cell_interval_status']='not_estimated_country_cell; group intervals separately';vs.append(z)
      out=pd.concat(vs,ignore_index=True);x=vs[0].merge(vs[1],on=['first_country','last_country'],suffixes=('_AF','_reference'));delta=x[['first_country','last_country']].copy();delta['corpus']='AF_minus_reference';delta['setting']=setting;delta['O_minus_E_pp']=x.O_minus_E_pp_AF-x.O_minus_E_pp_reference;delta['cell_interval_status']='not_estimated_country_cell; group direct intervals separately';rows.extend([out,delta])
    mat=pd.concat(rows,ignore_index=True);mat.to_parquet(ROOT/'tables/full_country_pair_matrices.parquet',index=False);mat.to_csv(ROOT/'tables/full_country_pair_matrices.csv.gz',index=False,compression='gzip')
    # New domestic R excludes explicit identical first/last IDs throughout.
    c.execute('''CREATE TABLE im AS SELECT * FROM institution_members WHERE first_id<>last_id''')
    z=c.execute('''SELECT i.country_code,i.institution_id,CASE WHEN m.study_group='AF' THEN 'AF' ELSE 'reference' END AS corpus,i.role,sum(i.credit) AS credit,count(DISTINCT i.study_id) AS n_papers
      FROM institution_credit i JOIN im m USING(study_id) GROUP BY 1,2,3,4''').df()
    v=z.pivot(index=['country_code','institution_id','corpus'],columns='role',values='credit').fillna(0).reset_index();nn=z[z.role.eq('output')][['country_code','institution_id','corpus','n_papers']];v=v.merge(nn,validate='one_to_one');out=[]
    for role in ['first','last']:
      t=v[['country_code','institution_id','corpus','n_papers','output',role]].rename(columns={'output':'output_credit',role:'role_credit'}).copy();t['role']=role
      for kind in ['output','role']:t[kind+'_total']=t.groupby(['country_code','corpus'])[kind+'_credit'].transform('sum');t[kind+'_share']=div(t[kind+'_credit'],t[kind+'_total'])
      t['R_inst']=div(t.role_share,t.output_share);t['defined_flag']=np.isfinite(t.R_inst);t['undefined_reason']=np.where(t.output_credit.le(0),'zero_output',np.where(t.role_total.le(0),'zero_country_role_total',''));out.append(t)
    v=pd.concat(out,ignore_index=True);ib=norm('institution_groups.parquet');ib=ib[ib.group_eligible][['institution_id','country','group','V_i']].rename(columns={'country':'country_code','group':'institution_group'});v=v.merge(ib,how='left',validate='many_to_one');v['institution_group']=v.institution_group.fillna('unclassified').replace({'H':'high','M':'middle','L':'low'});save('strict_domestic_institution_R',v)
    keys=['country_code','institution_id','role','institution_group'];pp=v[v.corpus.eq('AF')].merge(v[v.corpus.eq('reference')],on=keys,how='outer',suffixes=('_AF','_reference'),validate='one_to_one');pp['common_defined']=pp.defined_flag_AF.fillna(False)&pp.defined_flag_reference.fillna(False);pp['delta']=pp.R_inst_AF-pp.R_inst_reference;save('strict_domestic_institution_paired',pp)
    ss=[];ps=[]
    for n in [1,2,5,10]:
      for key,t in v[v.n_papers.ge(n)&v.defined_flag].groupby(['country_code','institution_group','corpus','role']):
        ss.append(dict(zip(['country_code','institution_group','corpus','role'],key),minimum_studies=n,n=len(t),median=t.R_inst.median(),q25=t.R_inst.quantile(.25),q75=t.R_inst.quantile(.75),zero_n=int(t.role_credit.eq(0).sum()),zero_pct=100*t.role_credit.eq(0).mean()))
      for key,t in pp[pp.common_defined&pp.n_papers_AF.ge(n)&pp.n_papers_reference.ge(n)].groupby(['country_code','institution_group','role']):
        ps.append(dict(zip(['country_code','institution_group','role'],key),minimum_studies=n,n=len(t),median=t.delta.median(),q25=t.delta.quantile(.25),q75=t.delta.quantile(.75)))
    save('strict_institution_distribution',pd.DataFrame(ss));save('strict_institution_paired_summary',pd.DataFrame(ps))
    # Fixed baseline zero-output is genuinely undefined R, never set to zero.
    ib['institution_group']=ib.institution_group.replace({'H':'high','M':'middle','L':'low'})
    fixed=[]
    for cp in CORPORA:
      for role in ['first','last']:
        t=ib.merge(v[v.corpus.eq(cp)&v.role.eq(role)][['country_code','institution_id','output_credit','R_inst']],on=['country_code','institution_id'],how='left',validate='one_to_one');t['corpus']=cp;t['role']=role;t['output_credit']=t.output_credit.fillna(0);t['zero_output']=t.output_credit.eq(0);t['undefined_reason']=np.where(t.zero_output,'zero_output',np.where(t.R_inst.isna(),'zero_country_role_total',''));fixed.append(t)
    save('strict_institution_fixed_baseline',pd.concat(fixed,ignore_index=True))
    # Domestic group pairs only within an actual same-country institution pair.
    c.register('ib',ib);c.execute('''CREATE TABLE zz AS SELECT z.*,coalesce(b.institution_group,'unclassified') AS g FROM role_country_institution_credit z LEFT JOIN ib b ON z.institution_id=b.institution_id AND z.country_code=b.country_code''')
    ig=c.execute('''SELECT p.corpus,f.country_code,f.g AS first_institution_group,l.g AS last_institution_group,sum(f.credit*l.credit) AS raw_credit,sum(f.credit*l.credit*p.weight) AS standardized_credit
      FROM zz f JOIN zz l ON f.study_id=l.study_id AND f.country_code=l.country_code JOIN analysis_members p ON p.study_id=f.study_id WHERE f.role='first' AND l.role='last' AND f.institution_id IS NOT NULL AND l.institution_id IS NOT NULL GROUP BY 1,2,3,4''').df();save('domestic_institution_group_pairings',ig)
    # Annual and country-group retention reconstructed from actual study membership.
    flow=c.execute('''SELECT s.publication_year AS year,s.corpus,count(*) AS international,
      count(*) FILTER(WHERE s.common_country_candidate) AS common_roles_legacy,
      count(*) FILTER(WHERE s.primary_eligible) AS author_complete_legacy,
      count(*) FILTER(WHERE s.strict_pairing_eligible) AS strict_complete,
      count(*) FILTER(WHERE m.supported) AS strict_supported
      FROM studies s LEFT JOIN analysis_members m USING(study_id) GROUP BY 1,2''').df();annual=read('Table_S1_annual.csv').rename(columns={'role_eligible':'role_eligible_historical'});annual['corpus']=annual.corpus.replace({'non-AF':'reference'});save('strict_annual_flow',annual.merge(flow,on=['year','corpus'],suffixes=('_historical','_reconstructed'),validate='one_to_one'))
    cc=ROOT/'inputs/local/country_credit.parquet';c.execute(f'CREATE VIEW cc AS SELECT * FROM read_parquet({q(cc)})')
    # Input country_credit uses role=output.
    gr=c.execute('''WITH g AS (SELECT DISTINCT s.study_id,s.publication_year,s.corpus,s.common_country_candidate,s.strict_pairing_eligible,coalesce(b.baseline_group,'outside') AS national_group
      FROM studies s JOIN cc ON s.study_id=cc.study_id LEFT JOIN country_groups b ON b.country_code=cc.country_code WHERE cc.role='output')
      SELECT publication_year AS year,corpus,national_group,count(*) AS international_group_n,count(*) FILTER(WHERE common_country_candidate) AS common_role_n,count(*) FILTER(WHERE strict_pairing_eligible) AS strict_complete_n FROM g GROUP BY 1,2,3''').df();gr['common_retention']=div(gr.common_role_n,gr.international_group_n);gr['strict_complete_retention']=div(gr.strict_complete_n,gr.international_group_n);save('strict_group_annual_retention',gr)
    elig=pd.read_parquet(ROOT/'tables/study_eligibility.parquet');strict=norm('studies.parquet')[['study_id','strict_pairing_eligible']];elig=elig.merge(strict,on='study_id',how='left',validate='one_to_one');elig['strict_pairing_eligible']=elig.strict_pairing_eligible.fillna(False);elig['new_main_eligible']=elig.strict_pairing_eligible;elig['new_exclusion_reason']=np.where(elig.new_main_eligible,'included',np.where(elig.study_id.isin(norm('studies.parquet').query('first_id == last_id').study_id),'identical_first_last_author','international_ID_country_position_or_support_audit'));elig.to_parquet(ROOT/'source_data/study_eligibility.parquet',index=False)
    # Canonical data contract has CSV views plus Parquet for large relational inputs.
    for n in ['studies','roles','country_groups']:
      norm(n+'.parquet').to_csv(ROOT/'source_data'/(n+'.csv'),index=False)
    p.to_csv(ROOT/'source_data/study_weights.csv',index=False)
    c.execute(f'''COPY (SELECT r.study_id,r.country_code,r.channel AS role,r.credit,s.first_id,s.last_id FROM read_parquet({q(d/'credit.parquet')}) r JOIN studies s USING(study_id) WHERE r.channel IN ('first','last')) TO {q(ROOT/'source_data/role_country_credit.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)''')
    c.close();dump(ROOT/'provenance/ancillary_complete.json',dict(status='PASS',country_pair_grid_rows=len(mat),country_registry=len(codes),institution_estimates=len(v),institution_studies_exclusion='explicit first_id == last_id removed; historical estimates retained separately',unknown_institution_baseline='unclassified',zero_output_R='undefined',country_cell_interval='not estimated; all group cells have conditional joint bootstrap',canonical_large_inputs='Parquet is lossless typed long-table format; full country CSV gzip also supplied'))
if __name__=='__main__':main()
