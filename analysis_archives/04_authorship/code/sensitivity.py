"""Predeclared same-sample sensitivity and disjoint-period direct contrasts."""
from common import *
from bootstrap import fit,group_only,ratios,pair_shares,bounds
from scipy import sparse
def weighted(m,minimum=5,cell=KEY):
    s=support(m,cell);s['supported']=(s.AF>=1)&(s.reference>=minimum);s['w_AF']=s.supported.astype(float);s['w_reference']=np.where(s.supported,s.AF/s.reference.replace(0,np.nan),0.)
    drop=[x for x in ['supported','w_AF','w_reference','weight'] if x in m];return add_weights(m.drop(columns=drop),s,cell)
def main():
    m=norm('analysis_members.parquet');meta=json.loads((ROOT/'inputs/normalized/feature_metadata.json').read_text());X,gm=group_only(sparse.load_npz(ROOT/'inputs/normalized/feature_matrix.npz'),meta)
    st=norm('study_structure.parquet').set_index('study_id').loc[m.study_id].reset_index();plans=[]
    for minimum in [1,10,20]:plans.append(('support_ref_'+str(minimum),np.ones(len(m),bool),minimum,None))
    plans.extend([('strict_international',m.strict_international.to_numpy(),5,None),('full_institution',st.unresolved_cells.eq(0).to_numpy(),5,None)])
    # Unique-role sensitivity: expected endpoints must come from the unique-country
    # author pool; it is not legitimate to retain the unrestricted team expectation.
    c=connect();d=ROOT/'inputs/normalized';c.register('m',m[['study_id','row_index']]);
    c.execute(f'CREATE VIEW ac AS SELECT x.* FROM read_parquet({q(d/"authors_countries.parquet")}) x SEMI JOIN m USING(study_id)')
    bg=norm('country_groups.parquet');c.register('bg',bg)
    c.execute('''CREATE TABLE ua AS SELECT a.study_id,a.author_id,any_value(a.country_code) AS country_code FROM ac a GROUP BY 1,2 HAVING count(*)=1''')
    c.execute('''CREATE TABLE ucounts AS SELECT u.study_id,coalesce(b.baseline_group,'outside') AS g,count(*)::DOUBLE AS n FROM ua u LEFT JOIN bg b USING(country_code) GROUP BY 1,2''')
    u=c.execute('''SELECT m.row_index,a.g AS fg,b.g AS lg,(a.n*b.n-CASE WHEN a.g=b.g THEN a.n ELSE 0 END)/(t.A*(t.A-1)) AS e
       FROM ucounts a JOIN ucounts b USING(study_id) JOIN (SELECT study_id,sum(n) AS A FROM ucounts GROUP BY 1 HAVING sum(n)>=2) t USING(study_id) JOIN m USING(study_id)''').df()
    ue=np.zeros((len(m),16));ue[u.row_index.to_numpy(),u.fg.map(GROUPS.index).to_numpy()*4+u.lg.map(GROUPS.index).to_numpy()]=u.e
    usc=c.execute('''SELECT m.row_index,sum(n*(n-1))/(sum(n)*(sum(n)-1)) AS e FROM (SELECT study_id,country_code,count(*)::DOUBLE n FROM ua GROUP BY 1,2) z JOIN m USING(study_id) GROUP BY 1 HAVING sum(n)>=2''').df()
    us=np.zeros(len(m));us[usc.row_index]=usc.e
    mask=(st.first_countries.eq(1)&st.last_countries.eq(1)).to_numpy()&np.isclose(ue.sum(axis=1),1)
    Y=X.tolil();off=gm['offsets']['expected_group'];Y[:,off:off+16]=ue;Y[:,gm['offsets']['same_country_expected']]=us[:,None];Y=Y.tocsr();Y.eliminate_zeros()
    plans.append(('unique_role_country_candidate_pool',mask,5,Y));c.close();del ue,Y
    status=[]
    for k,(name,mask,minimum,override) in enumerate(plans):
        mm=weighted(m.loc[mask].reset_index(drop=True),minimum);xx=(X if override is None else override)[mask].tocsr();fit(name,mm,xx,gm,10+k)
        for cp in CORPORA:
            z=mm[mm.corpus.eq(cp)];w=z.weight.to_numpy();status.append(dict(analysis_id=name,corpus=cp,n_raw=len(z),n_supported=int(z.supported.sum()),retention=z.supported.mean(),sum_weights=w.sum(),ESS=div(w.sum()**2,(w*w).sum()).item(),minimum_reference=minimum,replicates=B,status='executed',conditional=True))
    # Periods share pooled AF field/type target, not each period's separate target.
    dates=pd.to_datetime(m.publication_date,errors='coerce');period=np.where(dates.between('2021-07-01','2024-04-30'),'AF2',np.where(dates.between('2024-05-01','2025-12-31'),'AF3','outside'))
    cell=['work_type','primary_subfield_id'];z=m.assign(period=period);z=z[z.period.ne('outside')].dropna(subset=cell)
    ss=z.groupby(cell+['period','corpus'],observed=True).size().unstack(['period','corpus'],fill_value=0)
    gate=np.ones(len(ss),bool)
    for per in ['AF2','AF3']:gate&=(ss[per,'AF']>=1)&(ss[per,'reference']>=5)
    ss=ss.loc[gate];target=ss['AF2','AF']+ss['AF3','AF'];target=target/target.sum()
    targettable=ss.copy();targettable.columns=['_'.join(col) for col in targettable.columns];targettable['target_mass']=target;save('period_shared_target',targettable.reset_index())
    periodmembers={}
    for k,per in enumerate(['AF2','AF3']):
        mask=period==per;mm=m[mask].reset_index(drop=True).drop(columns=['supported','weight','w_AF','w_reference']);s=target.reset_index(name='target_mass');mm=mm.merge(s,on=cell,how='left',validate='many_to_one');mm['supported']=mm.target_mass.notna();ns=mm.groupby(cell+['corpus'],observed=True).study_id.transform('size');mm['weight']=mm.target_mass.fillna(0)/ns;fit('period_'+per,mm,X[mask],gm,30+k);periodmembers[per]=mm
        # Gate uses group-specific AF study support and ESS, never effects.
        for cp in CORPORA:
            for g in range(4):
                gx=X[mask,:4].toarray()[:,g]>0;v=mm[mm.corpus.eq(cp)&gx];w=v.weight.to_numpy();status.append(dict(analysis_id='period_'+per,corpus=cp,group=GROUPS[g],n_raw=len(v),n_supported=int(v.supported.sum()),retention=v.supported.mean(),sum_weights=w.sum(),ESS=div(w.sum()**2,(w*w).sum()).item(),minimum_reference=5,replicates=B,status='executed'))
    rows=[];pdra={};rds={};rp={};pp={}
    for per in ['AF2','AF3']:
        pools=np.load(ROOT/'draws'/f'period_{per}_joint_pools.npz');points=json.loads((ROOT/'draws'/f'period_{per}_points.json').read_text())
        for cp in CORPORA:
            p=np.array(points['standardized__'+cp]);rp[per,cp]=ratios(p[None,:],gm)[0];rds[per,cp]=ratios(pools['standardized__'+cp],gm);pp[per,cp]=pair_shares(p[None,:],gm);pdra[per,cp]=pair_shares(pools['standardized__'+cp],gm)
    for j,role in enumerate(['first','last']):
      for i,g in enumerate(GROUPS):
       gates=[]
       for per in ['AF2','AF3']:
        v=next(r for r in status if r['analysis_id']=='period_'+per and r['corpus']=='AF' and r['group']==g);gates.append(v['n_supported']>=20 and v['retention']>=.8 and v['ESS']>=20)
       for b,bench in enumerate(['country','author']):
        point=(rp['AF3','AF']-rp['AF3','reference'])[b,j,i]-(rp['AF2','AF']-rp['AF2','reference'])[b,j,i];dd=(rds['AF3','AF']-rds['AF3','reference'])[:,b,j,i]-(rds['AF2','AF']-rds['AF2','reference'])[:,b,j,i]
        rows.append(dict(outcome='R_difference_change',benchmark=bench,role=role,group=g,estimate=point,**bounds(dd),display_supported=all(gates),unsupported_reason='' if all(gates) else 'AF_group_n_retention_or_ESS_gate',unit='dimensionless'))
    for i,fg in enumerate(GROUPS):
      for j,lg in enumerate(GROUPS):
        k=i*4+j;ps=lambda per,cp:100*(pp[per,cp]['observed_group'][0,k]-pp[per,cp]['expected_group'][0,k]);ds=lambda per,cp:100*(pdra[per,cp]['observed_group'][:,k]-pdra[per,cp]['expected_group'][:,k]);point=(ps('AF3','AF')-ps('AF3','reference'))-(ps('AF2','AF')-ps('AF2','reference'));draw=(ds('AF3','AF')-ds('AF3','reference'))-(ds('AF2','AF')-ds('AF2','reference'));rows.append(dict(outcome='pair_deviation_direct_corpus_change',first_group=fg,last_group=lg,estimate=point,**bounds(draw),unit='percentage_points'))
    save('period_direct_changes',pd.DataFrame(rows));save('sensitivity_coverage_and_status',pd.DataFrame(status))
    dump(ROOT/'provenance/N06_complete.json',dict(status='PASS',analyses=[p[0] for p in plans]+['period_AF2','period_AF3'],replicates=B,period_target='shared_field_type_pooled_AF',direct_period_contrasts=True,unique_country_expected_pool='only observed authors with exactly one country; at least two',notes='Unavailable cofirst/colast, consortium completeness and alphabetical ordering remain unavailable. Conditional intervals do not address cross-study author/institution dependence.'))
if __name__=='__main__':main()
