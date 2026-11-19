"""Strict unified sample, actual country/institution pairs and exact team expectations."""
from common import *
from scipy import sparse
def main():
    require((ROOT/'provenance/N01_complete.json').exists(),'N01 not committed')
    require(not (ROOT/'provenance/features_complete.json').exists(),'Features already committed')
    p=norm('pairing_studies.parquet').sort_values('study_id').reset_index(drop=True);p['row_index']=np.arange(len(p),dtype=np.int64)
    p.to_parquet(ROOT/'inputs/normalized/analysis_members.parquet',index=False)
    c=connect();c.register('p',p)
    for table,file in [('ac','authors_countries'),('rc','credit'),('ai','authors_institutions')]:
        c.execute(f'CREATE VIEW {table} AS SELECT z.* FROM read_parquet({q(ROOT/"inputs/normalized"/(file+".parquet"))}) z SEMI JOIN p USING(study_id)')
    bg=norm('country_groups.parquet');c.register('bg',bg)
    c.execute('''CREATE TABLE author_groups AS SELECT x.study_id,x.author_id,x.author_index,coalesce(b.baseline_group,'outside') AS country_group,sum(x.country_weight) AS credit
       FROM ac x LEFT JOIN bg b ON x.country_code=b.country_code GROUP BY 1,2,3,4''')
    c.execute('''CREATE TABLE observed_country AS SELECT f.study_id,f.country_code AS first_country,l.country_code AS last_country,f.credit*l.credit AS credit
       FROM rc f JOIN rc l USING(study_id) WHERE f.channel='first' AND l.channel='last' ''')
    # Country expectation is built at country level, never by disaggregating group results.
    c.execute('''CREATE TABLE country_totals AS SELECT study_id,country_code,sum(country_weight) AS s FROM ac GROUP BY 1,2''')
    c.execute('''CREATE TABLE correction AS SELECT a.study_id,a.country_code AS first_country,b.country_code AS last_country,sum(a.country_weight*b.country_weight) AS d
       FROM ac a JOIN ac b USING(study_id,author_id) GROUP BY 1,2,3''')
    c.execute('''CREATE TABLE expected_country AS SELECT a.study_id,a.country_code AS first_country,b.country_code AS last_country,
       (a.s*b.s-coalesce(x.d,0))/(p.observed_author_count*(p.observed_author_count-1)) AS credit
       FROM country_totals a JOIN country_totals b USING(study_id) JOIN p USING(study_id)
       LEFT JOIN correction x ON a.study_id=x.study_id AND a.country_code=x.first_country AND b.country_code=x.last_country''')
    # Figure5 country-first institution allocation, explicitly distinct from old institutional R.
    c.execute('''CREATE TABLE z AS WITH rolebase AS (SELECT r.study_id,r.country_code,r.channel AS role,r.credit,
       CASE WHEN r.channel='first' THEN p.first_id ELSE p.last_id END AS author_id FROM rc r JOIN p USING(study_id) WHERE r.channel IN ('first','last')),
       linked AS (SELECT DISTINCT r.study_id,r.country_code,r.role,i.institution_id FROM rolebase r JOIN ai i ON r.study_id=i.study_id AND r.author_id=i.author_id AND r.country_code=i.institution_country),
       base AS (SELECT r.*,l.institution_id,count(l.institution_id) OVER(PARTITION BY r.study_id,r.role,r.country_code) AS k FROM rolebase r LEFT JOIN linked l USING(study_id,country_code,role))
       SELECT study_id,author_id,role,country_code,institution_id,credit/(CASE WHEN k=0 THEN 1 ELSE k END) AS credit,
         CASE WHEN k=0 THEN 'institution_unknown' ELSE 'observed_country_aligned_institution' END AS affiliation_status FROM base''')
    c.execute('''CREATE TABLE struct AS WITH sc AS (SELECT study_id,sum(credit) AS same_country FROM observed_country WHERE first_country=last_country GROUP BY 1),
       si AS (SELECT f.study_id,sum(f.credit*l.credit) AS same_inst FROM z f JOIN z l ON f.study_id=l.study_id AND f.country_code=l.country_code AND f.institution_id=l.institution_id
          WHERE f.role='first' AND l.role='last' AND f.institution_id IS NOT NULL GROUP BY 1),
       known AS (SELECT study_id,role,country_code,sum(credit) AS u FROM z WHERE institution_id IS NOT NULL GROUP BY 1,2,3),
       kk AS (SELECT f.study_id,sum(f.u*l.u) AS both_known_same_country FROM known f JOIN known l USING(study_id,country_code) WHERE f.role='first' AND l.role='last' GROUP BY 1),
       crossinst AS (SELECT f.study_id,sum(f.credit*l.credit) AS same_ID_cross_country FROM z f JOIN z l ON f.study_id=l.study_id AND f.institution_id=l.institution_id
         WHERE f.role='first' AND l.role='last' AND f.country_code<>l.country_code AND f.institution_id IS NOT NULL GROUP BY 1),
       cov AS (SELECT study_id,count(*) FILTER(WHERE institution_id IS NULL) AS unresolved_cells,
         count(DISTINCT institution_id) FILTER(WHERE role='first') AS first_institutions,count(DISTINCT institution_id) FILTER(WHERE role='last') AS last_institutions,
         count(DISTINCT country_code) FILTER(WHERE role='first') AS first_countries,count(DISTINCT country_code) FILTER(WHERE role='last') AS last_countries FROM z GROUP BY 1)
       SELECT p.study_id,coalesce(si.same_inst,0) AS same_country_same_institution,
         coalesce(kk.both_known_same_country,0)-coalesce(si.same_inst,0) AS same_country_different_institutions,
         coalesce(sc.same_country,0)-coalesce(kk.both_known_same_country,0) AS same_country_institutional_relation_unresolved,
         1-coalesce(sc.same_country,0) AS different_countries,coalesce(crossinst.same_ID_cross_country,0) AS same_ID_cross_country,
         cov.* EXCLUDE(study_id) FROM p LEFT JOIN sc USING(study_id) LEFT JOIN si USING(study_id) LEFT JOIN kk USING(study_id) LEFT JOIN crossinst USING(study_id) LEFT JOIN cov USING(study_id)''')
    for name,table in [('country_pair_credit','observed_country'),('country_pair_expected','expected_country'),('role_country_institution_credit','z'),('author_group_memberships','author_groups'),('study_structure','struct')]:
        c.execute(f'COPY {table} TO {q(ROOT/"inputs/normalized"/(name+".parquet"))} (FORMAT PARQUET,COMPRESSION ZSTD)')
    # Shared sparse whole-study vector includes both benchmarks, both roles and every Figure5 outcome.
    codes=sorted(set(read('country_registry.csv').country_code)|set(c.execute('SELECT DISTINCT country_code FROM rc').df().country_code))
    entities=codes+['group:'+g for g in GROUPS];lookup={v:i for i,v in enumerate(entities)};gmap=dict(zip(bg.country_code,bg.baseline_group));E=len(entities);nc=len(codes);N=len(p)
    values=c.execute('SELECT r.* FROM rc r JOIN p USING(study_id)').df().merge(p[['study_id','row_index']],on='study_id',validate='many_to_one')
    ch={'country_output':0,'author_output':1,'first':2,'last':3};row=values.row_index.to_numpy(np.int64);channel=values.channel.map(ch).to_numpy(np.int64)
    col=values.country_code.map(lookup).to_numpy(np.int64)+channel*E
    groupcol=values.country_code.map(lambda x:lookup['group:'+gmap.get(x,'outside')]).to_numpy(np.int64)+channel*E
    rr=[row,row];cc=[col,groupcol];vv=[values.credit.to_numpy(float),values.credit.to_numpy(float)]
    offsets={'observed_group':4*E,'expected_group':4*E+16,'same_country_observed':4*E+32,'same_country_expected':4*E+33,'structure':4*E+34}
    for table,start in [('observed_country',offsets['observed_group']),('expected_country',offsets['expected_group'])]:
        x=c.execute(f'''SELECT z.study_id,coalesce(f.baseline_group,'outside') AS fg,coalesce(l.baseline_group,'outside') AS lg,sum(z.credit) AS credit
           FROM {table} z LEFT JOIN bg f ON z.first_country=f.country_code LEFT JOIN bg l ON z.last_country=l.country_code GROUP BY 1,2,3''').df().merge(p[['study_id','row_index']],on='study_id',validate='many_to_one')
        rr.append(x.row_index.to_numpy(np.int64));cc.append(start+x.fg.map(GROUPS.index).to_numpy(np.int64)*4+x.lg.map(GROUPS.index).to_numpy(np.int64));vv.append(x.credit.to_numpy(float))
        s=c.execute(f'SELECT study_id,sum(credit) AS credit FROM {table} WHERE first_country=last_country GROUP BY 1').df().merge(p[['study_id','row_index']],on='study_id',validate='many_to_one')
        rr.append(s.row_index.to_numpy(np.int64));cc.append(np.full(len(s),offsets['same_country_observed' if table=='observed_country' else 'same_country_expected'],dtype=np.int64));vv.append(s.credit.to_numpy(float))
    st=norm('study_structure.parquet').merge(p[['study_id','row_index']],on='study_id',validate='one_to_one').sort_values('row_index').reset_index(drop=True)
    categories=['same_country_same_institution','same_country_different_institutions','same_country_institutional_relation_unresolved','different_countries']
    require(st[categories].min().min()>-1e-12 and np.allclose(st[categories].sum(axis=1),1,atol=1e-12),'Figure5a study structure not normalized')
    for i,name in enumerate(categories):rr.append(st.row_index.to_numpy(np.int64));cc.append(np.full(len(st),offsets['structure']+i,dtype=np.int64));vv.append(st[name].to_numpy(float))
    M=sparse.coo_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(N,4*E+38)).tocsr();M.sum_duplicates();M.eliminate_zeros();M.sort_indices()
    for i in range(4):require(np.allclose(np.asarray(M[:,i*E:i*E+nc].sum(axis=1)).ravel(),1,atol=1e-11),'Study credit mass channel '+str(i))
    og=M[:,offsets['observed_group']:offsets['observed_group']+16].toarray().reshape(N,4,4);eg=M[:,offsets['expected_group']:offsets['expected_group']+16].toarray().reshape(N,4,4)
    require(np.allclose(og.sum(axis=(1,2)),1) and np.allclose(eg.sum(axis=(1,2)),1),'Pair mass')
    require(np.allclose(og.sum(axis=2),M[:,2*E+nc:3*E].toarray(),atol=1e-11) and np.allclose(og.sum(axis=1),M[:,3*E+nc:4*E].toarray(),atol=1e-11),'Observed pairing role margins')
    require(np.allclose(eg,eg.transpose(0,2,1),atol=1e-11) and np.allclose(eg.sum(axis=2),M[:,E+nc:2*E].toarray(),atol=1e-11),'Expected symmetric distinct-author marginals')
    require(np.allclose(st[categories[:3]].sum(axis=1),M[:,offsets['same_country_observed']].toarray().ravel(),atol=1e-11),'Figure5a/b/c country margins disagree')
    sparse.save_npz(ROOT/'inputs/normalized/feature_matrix.npz',M)
    dump(ROOT/'inputs/normalized/feature_metadata.json',dict(entities=entities,countries=codes,n_countries=nc,n_entities=E,channels=ch,offsets=offsets,structure_categories=categories,n_studies=N,rows_order='analysis_members.parquet',shared_feature_vector='country/author participation, first/last, observed/expected pairs, institution structure'))
    cov=st.merge(p[['study_id','corpus']],on='study_id').groupby('corpus').agg(studies=('study_id','size'),any_unresolved=('unresolved_cells',lambda z:int((z>0).sum())),unique_role_countries=('first_countries',lambda z:0))
    cov=cov.drop(columns='unique_role_countries');cov.to_csv(ROOT/'tables/figure5_institution_coverage_audit.csv')
    dump(ROOT/'provenance/features_complete.json',dict(status='PASS',study_n=N,sparse_rows=M.shape[0],sparse_columns=M.shape[1],nonzero=M.nnz,strict_sample_hash=sha(ROOT/'tables/pairing_study_ids_and_weights.csv'),same_sample_Figure4_Figure5=True,primary_n=p[p.supported].groupby('corpus').size().to_dict(),country_margins_preserved=True,structure_unknown_retained=True,institution_credit_definition='country first, aligned observed institutions second; not historical domestic R role credit'))
    c.close();print('N01/N03 exact feature and country/institution pairing reconstruction PASS:',M.shape,M.nnz,flush=True)
if __name__=='__main__':main()
