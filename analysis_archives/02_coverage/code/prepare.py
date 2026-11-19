"""New weighting/model and N20 diagnostic tables; frozen simulations unchanged."""
from common import *
from model import continuous
import duckdb

def weighting(out):
    x=read(out,'country_group_year_primary.csv');x=x.loc[truth(x.eligible_20)&x.year.between(2020,2025)].copy()
    require(x.country.nunique()==68 and len(x)==1224,'Country/year grid')
    require(not x.duplicated(['country','group','year']).any(),'Duplicated country/year cell')
    require((x.groupby(['country','group']).fixed_N.nunique()==1).all(),'Changing fixed denominators')
    annual=[]
    for (yr,g),b in x.groupby(['year','group']):
        require(np.allclose(b.A,b.active_N/b.fixed_N),'Annual rate count mismatch')
        for weight in ['equal_country','pooled_institution']:
            a=b.A.mean() if weight=='equal_country' else b.active_N.sum()/b.fixed_N.sum()
            annual.append({'weighting':weight,'year':yr,'group':g,'countries':68,'fixed_institutions':b.fixed_N.sum(),'active_institutions':b.active_N.sum(),'A':a,'coverage_pct':100*a,'population_id':'B2','source_hash':sha(out/'inputs/frozen/country_group_year_primary.csv')})
    a=pd.DataFrame(annual);save(out,'new_weighting_annual.csv',a);dis=[]
    for (w,y),b in a.groupby(['weighting','year']):
        v=b.set_index('group').A;dis.append({'weighting':w,'year':y,'R':v.L/v.H if v.H>0 else np.nan,'R_defined':v.H>0,'G_pp':100*(v.H-v.L),'population_id':'B2','source_hash':b.source_hash.iloc[0]})
    d=pd.DataFrame(dis);save(out,'new_weighting_disparities.csv',d)
    ep=[]
    for w,b in d.groupby('weighting'):
        b=b.set_index('year');ep.append({'weighting':w,'R2021':b.loc[2021,'R'],'R2025':b.loc[2025,'R'],'G2021_pp':b.loc[2021,'G_pp'],'G2025_pp':b.loc[2025,'G_pp'],'delta_G_pp':b.loc[2025,'G_pp']-b.loc[2021,'G_pp'],'status':'new_observed_calculation_no_benchmark_transferred'})
    save(out,'new_weighting_endpoints.csv',pd.DataFrame(ep))
    print('Weighting sensitivity computed',flush=True)

def cohorts(out,base):
    states=read(out,'ED3_all_baseline_status.csv').rename(columns={'status':'date_state','eligible_20':'state_eligible_20','first_confirmed_year':'state_first_confirmed_year','first_date_identifiable_AF_publication':'state_first_date'})
    b=base.merge(states,on='institution_id',validate='one_to_one');require(len(b)==52098,'Cohort join changed B0')
    b['population_id']=np.where(truth(b.eligible_20),'B2','B0_outside_B2')
    b['country_group']=b.context.replace('','UNASSIGNED');b['institution_group']=b.group.replace('','UNASSIGNED')
    b['date_resolved']=b.state_first_date.ne('');b['confirmed_year_known']=number(b.first_confirmed_year).notna();b['pool_year_known']=number(b.first_pool_AF_year).notna()
    b['author_unobserved']=number(b.known_linked_author_ids).fillna(0).eq(0)
    cols=['population_id','country_group','institution_group','date_state','date_resolved','confirmed_year_known','pool_year_known','pre2020_confirmed','legacy_date_entry_in_main']
    partition=b.groupby(cols,dropna=False).agg(institutions=('institution_id','size'),author_unobserved=('author_unobserved','sum')).reset_index();partition['row_semantics']='mutually_exclusive_partition';save(out,'Table_SX_c_cohort_partition.csv',partition)
    summary=[]
    for pop,mask in [('B0',np.ones(len(b),bool)),('B2',truth(b.eligible_20))]:
        q=b.loc[mask]
        for label,count in [('all_institutions',len(q)),('legacy_date_entry',truth(q.legacy_date_entry_in_main).sum()),('ever_AF_pool_year_le2025',number(q.first_pool_AF_year).le(2025).sum()),('pre2020_confirmed',truth(q.pre2020_confirmed).sum()),('date_field_present',q.date_resolved.sum()),('confirmed_year_present',q.confirmed_year_known.sum()),('pool_year_present',q.pool_year_known.sum())]:summary.append({'population_id':pop,'condition':label,'institutions':count,'row_semantics':'overlapping_condition_summary_do_not_add'})
    save(out,'Table_SX_c_cohort_summary.csv',pd.DataFrame(summary));save(out,'Table_SX_c_status_totals.csv',b.groupby(['population_id','date_state']).size().rename('institutions').reset_index())
    author=b.groupby(['population_id','country_group','institution_group']).agg(institutions=('institution_id','size'),author_unobserved=('author_unobserved','sum')).reset_index();save(out,'Table_SX_d_author_missingness.csv',author)
    save(out,'Table_SX_c_institution_audit.csv',b[['institution_id','country','country_group','institution_group','population_id','date_state','first_pool_AF_year','confirmed_year_known','date_resolved','pool_year_known','pre2020_confirmed','legacy_date_entry_in_main','author_unobserved']])
    iy=pd.read_parquet(out/'inputs/raw/institution_year_observed.parquet',columns=['institution_id','year','unknown_label_studies'])
    iy=iy[iy.year.between(2020,2025)].merge(b[['institution_id','population_id','country_group','institution_group']],on='institution_id',validate='many_to_one')
    unknown=iy.groupby(['population_id','country_group','institution_group','year']).agg(observed_institution_years=('institution_id','nunique'),unknown_label_study_institution_relations=('unknown_label_studies','sum'),institutions_with_unknown=('unknown_label_studies',lambda x:int(x.gt(0).sum()))).reset_index()
    unknown['unit_note']='unknown study–institution incidences, not unique studies; do not sum to global unknown work count'
    save(out,'Table_SX_c_unknown_label_coverage.csv',unknown)
    print('Cohort cross-tabulations and author missingness prepared',flush=True)

def exchangeability(out,base):
    scratch=out/'scratch';scratch.mkdir(exist_ok=True)
    c=duckdb.connect();c.execute("SET threads=2");c.execute("SET memory_limit='4GiB'");c.execute("SET preserve_insertion_order=false")
    c.execute("SET temp_directory='"+str(scratch).replace("'","''")+"'");c.execute("SET max_temp_directory_size='4GiB'")
    studies=str(out/'inputs/raw/opportunity_studies.parquet').replace("'","''");members=str(out/'inputs/raw/opportunity_memberships.parquet').replace("'","''")
    c.execute(f"CREATE TEMP TABLE studies AS SELECT study_id,year,field,country_set,document_type,team_bin,z FROM read_parquet('{studies}')")
    n=c.execute('SELECT count(*),count(DISTINCT study_id),sum(z),min(z),max(z) FROM studies').fetchone();require(n==(2200061,2200061,15961,0,1),'Frozen opportunity study count or labels')
    b=base.loc[truth(base.eligible_20),['institution_id','country','group']].copy();c.register('registry',b)
    dup=c.execute(f"SELECT 1 FROM read_parquet('{members}') GROUP BY study_id,institution_id HAVING count(*)>1 LIMIT 1").fetchall();require(not dup,'Duplicate study–institution memberships')
    orphan=c.execute(f"SELECT count(*) FROM read_parquet('{members}') m LEFT JOIN studies s USING(study_id) WHERE s.study_id IS NULL").fetchone()[0];require(orphan==0,'Orphan study memberships')
    c.execute(f'''CREATE TEMP TABLE main_members AS SELECT m.study_id,m.institution_id,r.country,r."group",s.year,s.field,s.country_set,s.document_type,s.team_bin,s.z FROM read_parquet('{members}') m JOIN registry r USING(institution_id) JOIN studies s USING(study_id)''')
    diagnostics=[];relations=[];strata_tables=[]
    for variant,extra in [('main',''),('document_type',',document_type'),('team_size',',team_bin')]:
        fields='year,field,country_set'+extra
        c.execute(f'CREATE OR REPLACE TEMP TABLE strata AS SELECT {fields},count(*)::BIGINT n_h,sum(z)::BIGINT K_h FROM studies GROUP BY {fields}')
        totals=c.execute('''SELECT count(*),count(*) FILTER(WHERE K_h>0 AND K_h<n_h),sum(n_h),sum(n_h) FILTER(WHERE K_h>0 AND K_h<n_h),sum(K_h),sum(K_h) FILTER(WHERE K_h>0 AND K_h<n_h) FROM strata''').fetchone()
        d=dict(zip(['strata','mutable_strata','studies','mutable_studies','AF_studies','mutable_AF_studies'],totals));d.update(variant=variant,seed=20261024,result_status='new_count_diagnostic_no_simulation')
        if variant=='main':require(totals==(194625,3620,2200061,1224425,15961,14524),'Main strata historical anchors')
        diagnostics.append(d)
        group=c.execute(f'''SELECT '{variant}' AS variant,m.country,m."group",count(*) AS opportunity_relations,sum(CASE WHEN K_h>0 AND K_h<n_h THEN 1 ELSE 0 END)::BIGINT mutable_relations,sum(z)::BIGINT AF_relations,sum(CASE WHEN K_h>0 AND K_h<n_h THEN z ELSE 0 END)::BIGINT mutable_AF_relations FROM main_members m JOIN strata USING({fields}) GROUP BY m.country,m."group" ORDER BY m.country,m."group"''').fetchdf()
        # Include all 204 fixed country/group cells, even if the observed opportunity count is zero.
        cells=b.groupby(['country','group']).size().reset_index(name='fixed_N')
        group=cells.merge(group,on=['country','group'],how='left');group['variant']=variant
        for col in ['opportunity_relations','mutable_relations','AF_relations','mutable_AF_relations']:group[col]=group[col].fillna(0).astype('int64')
        group['mutable_relation_fraction']=group.mutable_relations/group.opportunity_relations.replace(0,np.nan);group['mutable_AF_relation_fraction']=group.mutable_AF_relations/group.AF_relations.replace(0,np.nan)
        group['denominator_scope']='N20_fixed_institutions';group['source_hash']=sha(out/'inputs/raw/opportunity_memberships.parquet');relations.append(group)
        strata=c.execute(f"SELECT '{variant}' AS variant,row_number() OVER(ORDER BY {fields}) AS stratum_id,*,K_h>0 AND K_h<n_h AS exchangeable FROM strata ORDER BY {fields}").fetchdf();strata['extra_condition']=extra.lstrip(',') or 'none'
        if extra:strata=strata.rename(columns={extra.lstrip(','):'extra_value'})
        else:strata['extra_value']=''
        # CSV preserves n/K and full exact conditioning keys; no new random draws.
        strata_tables.append(strata)
        print('N20 diagnostic',variant,':',int(group.opportunity_relations.sum()),'relations',flush=True)
    save(out,'new_N20_exchangeability.csv',pd.concat(relations,ignore_index=True));save(out,'new_strata_diagnostic_summary.csv',pd.DataFrame(diagnostics))
    save(out,'new_strata_diagnostics.csv',pd.concat(strata_tables,ignore_index=True))
    # Rebuild annual AF and general opportunity counts from the same frozen memberships.
    iy=c.execute('''SELECT institution_id,year,count(*) AS pool_opportunities,sum(z)::BIGINT AS pool_AF FROM main_members GROUP BY institution_id,year ORDER BY institution_id,year''').fetchdf()
    save(out,'new_institution_year_pool_counts.csv',iy)
    cell=c.execute('''SELECT country,"group",year,count(DISTINCT institution_id) AS opportunity_active_N,count(DISTINCT institution_id) FILTER(WHERE z=1) AS AF_active_N FROM main_members GROUP BY country,"group",year''').fetchdf()
    frozen=read(out,'country_group_year_primary.csv');frozen=frozen.loc[truth(frozen.eligible_20)&frozen.year.between(2020,2025)].copy();joined=frozen.merge(cell,on=['country','group','year'],how='left',validate='one_to_one')
    joined[['opportunity_active_N','AF_active_N']]=joined[['opportunity_active_N','AF_active_N']].fillna(0).astype(int)
    require(np.array_equal(joined.AF_active_N,joined.active_N),'Raw memberships annual AF coverage differs from frozen table')
    joined['B']=joined.opportunity_active_N/joined.fixed_N;joined['Q']=joined.AF_active_N/joined.opportunity_active_N.replace(0,np.nan)
    joined['identity_error']=np.where(joined.opportunity_active_N>0,joined.A-joined.B*joined.Q,np.nan);joined['Q_status']=np.where(joined.opportunity_active_N>0,'defined','undefined_no_pool_opportunity')
    require(joined.identity_error.abs().max()<1e-12,'Country cell A=BQ identity')
    save(out,'optional_activity_opportunity_decomposition.csv',joined)
    mean=joined.groupby(['context','year','group']).agg(A=('A','mean'),B=('B','mean'),Q_available=('Q','mean'),countries=('country','nunique'),Q_defined_countries=('Q','count')).reset_index();mean['warning']='mean(A)=mean(B*Q) where defined; not mean(B)*mean(Q); Q target excludes empty opportunity cells';save(out,'optional_activity_opportunity_means.csv',mean)
    dump(out/'quality/raw_relation_audit.json',{'full_memberships':6585658,'N20_memberships':c.execute('SELECT count(*) FROM main_members').fetchone()[0],'duplicates':0,'orphans':orphan,'studies':2200061,'AF_studies':15961,'raw_annual_counts_match':True,'A_equals_BQ_max_abs_error':joined.identity_error.abs().max(),'historical_N10_memberships_not_reused':6404572})
    c.close()

def alternatives(out):
    registry=read(out,'S8_institution_group_registry.csv');common=read(out,'S8_common_fixed_ID_registry.csv')
    valid=registry.loc[truth(registry.alternative_country_eligible)&truth(registry.alternative_institution_eligible)].copy()
    ids={m:set(common.loc[common.metric.eq(m),'institution_id']) for m in ['authors','partners']}
    require(ids['authors']==ids['partners'] and len(ids['authors'])==47910,'S8 common IDs differ')
    rows=[]
    for sample,frame in [('metric_valid',valid),('common_valid',common)]:
        for (metric,country),block in frame.groupby(['metric','country']):
            values=registry.loc[(registry.metric==metric)&registry.institution_id.isin(block.institution_id)].set_index('institution_id').baseline_metric
            v=number(values).dropna().to_numpy();q=np.quantile(v,[1/3,2/3],method='linear')
            expected=pd.Series(np.where(number(values)<=q[0],'L',np.where(number(values)<=q[1],'M','H')),index=values.index)
            actual=block.set_index('institution_id').alternative_group
            require((expected.reindex(actual.index)==actual).all(),'S8 domestic tie rule differs')
            rows.append({'metric':metric,'sample':sample,'country':country,'fixed_IDs':len(block),'N_L':sum(block.alternative_group=='L'),'N_M':sum(block.alternative_group=='M'),'N_H':sum(block.alternative_group=='H'),'cut_LM':q[0],'cut_MH':q[1],'eligible':True,'population_id':'alternative' if sample=='metric_valid' else 'common','weighting':'equal_country','tie_policy':'type7_lower_boundary_ties'})
    save(out,'Table_SX_d_alternative_sample_groups.csv',pd.DataFrame(rows))
    save(out,'Table_SX_d_common_fixed_IDs.csv',common)
    print('S8 fixed common IDs and grouping cutpoints independently checked',flush=True)

def prepare(out):
    base=read(out,'institution_baseline_and_first_participation.csv')
    require(len(base)==52098 and base.institution_id.nunique()==52098,'Unique B0 IDs')
    weighting(out);cohorts(out,base);alternatives(out);continuous(out,base);exchangeability(out,base)
