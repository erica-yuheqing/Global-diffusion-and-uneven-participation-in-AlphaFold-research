"""Conditional distinct-author Monte Carlo and analytic institution zero events."""
from common import *
import os, sys, shutil
import ctypes,subprocess,time
from scipy import sparse
def main():
    marker=ROOT/'provenance/conditional_reference_complete.json'
    if marker.exists():print('Retain committed conditional reference');return
    c=connect();d=ROOT/'inputs/normalized'
    for n in ['studies','authors','authors_countries','authors_institutions','analysis_members']:
        c.execute(f'CREATE VIEW {n} AS SELECT * FROM read_parquet({q(d/(n+".parquet"))})')
    c.execute(f'CREATE VIEW im AS SELECT * FROM read_parquet({q(ROOT/"inputs/local/institution_members.parquet")})')
    # Institution opportunity reference uses the observed usable institution cohort,
    # restricted to verified author IDs and different explicit role authors.
    c.execute('''CREATE TABLE eligible AS SELECT s.*,
      EXISTS(SELECT 1 FROM im WHERE im.study_id=s.study_id) AND s.observed_IDs_consistent
      AND s.first_id<>s.last_id AND s.observed_author_count>=2 AS inst_eligible
      FROM studies s''')
    p=c.execute('''SELECT e.study_id,e.corpus,e.first_id,e.last_id,e.inst_eligible,
      coalesce(m.weight,0) AS main_weight,m.study_id IS NOT NULL AS main_member
      FROM eligible e LEFT JOIN analysis_members m USING(study_id)
      WHERE e.inst_eligible OR m.study_id IS NOT NULL ORDER BY e.study_id''').df()
    p['sidx']=np.arange(len(p));c.register('p',p)
    a=c.execute('''SELECT a.study_id,a.author_id,a.author_index FROM authors a SEMI JOIN p USING(study_id)
      ORDER BY a.study_id,a.author_index''').df();a['aidx']=np.arange(len(a));c.register('a',a)
    poolptr=np.r_[0,np.cumsum(a.groupby('study_id',sort=True).size().to_numpy())].astype('int64')
    require(len(poolptr)==len(p)+1 and np.all(np.diff(poolptr)>=2),'Every simulated team has >=2 observed authors')
    ac=c.execute('''SELECT a.aidx,x.country_code,x.country_weight FROM authors_countries x
      JOIN a USING(study_id,author_id) ORDER BY a.aidx,x.country_code''').df()
    codes=sorted(ac.country_code.unique());ci={v:i for i,v in enumerate(codes)}
    countryptr=np.r_[0,np.cumsum(np.bincount(ac.aidx,minlength=len(a)))].astype('int64')
    countryidx=ac.country_code.map(ci).to_numpy('int32');countryweight=ac.country_weight.to_numpy(float)
    bg=norm('country_groups.parquet');gm=dict(zip(bg.country_code,bg.baseline_group));gw=np.zeros((len(a),4))
    np.add.at(gw,(ac.aidx.to_numpy(),ac.country_code.map(lambda z:GROUPS.index(gm.get(z,'outside'))).to_numpy()),countryweight)
    # Aligned affiliation pairs only; institutional unknowns are not redistributed.
    ai=c.execute('''SELECT DISTINCT a.aidx,a.study_id,a.author_id,x.institution_country AS country_code,x.institution_id,p.corpus
      FROM authors_institutions x JOIN a USING(study_id,author_id) JOIN p USING(study_id) WHERE p.inst_eligible''').df()
    er=ai[['corpus','country_code','institution_id']].drop_duplicates().sort_values(['corpus','country_code','institution_id']).reset_index(drop=True);er['eidx']=np.arange(len(er))
    ai=ai.merge(er,validate='many_to_one').sort_values(['aidx','eidx']).reset_index(drop=True);c.register('ai',ai)
    members=ai[['study_id','eidx','aidx']].drop_duplicates().merge(p[['study_id','first_id','last_id']],validate='many_to_one').merge(a[['aidx','author_id']],validate='many_to_one')
    counts=members.groupby(['study_id','eidx']).agg(n_authors=('aidx','nunique'),first_hit=('author_id',lambda x:False)).reset_index().drop(columns='first_hit')
    counts=counts.merge(p[['study_id','sidx']],validate='many_to_one');counts['A']=np.diff(poolptr)[counts.sidx];counts['pi']=counts.n_authors/counts.A
    require(counts.pi.between(0,1).all(),'Institution endpoint probability')
    counts['log_nohit']=np.where(counts.pi.eq(1),-np.inf,np.log1p(-counts.pi.clip(upper=1-1e-16)))
    z=counts.groupby('eidx').agg(n_papers=('study_id','nunique'),log_P0=('log_nohit','sum'),pi_sum=('pi','sum'),pi_max=('pi','max')).reset_index();z['analytic_P0']=np.exp(z.log_P0)
    hits=members.assign(first_hit=members.author_id.eq(members.first_id),last_hit=members.author_id.eq(members.last_id)).groupby('eidx')[['first_hit','last_hit']].sum().reset_index()
    er=er.merge(z,validate='one_to_one').merge(hits,validate='one_to_one');ib=norm('institution_groups.parquet');ib=ib.rename(columns={'country':'baseline_country','group':'institution_group'})
    er=er.merge(ib[['institution_id','baseline_country','institution_group','V_i','group_eligible']],how='left',validate='many_to_one')
    ok=er.group_eligible.fillna(False)&er.country_code.eq(er.baseline_country);er['institution_group']=np.where(ok,er.institution_group,'unclassified')
    er['paper_bin']=pd.cut(er.n_papers,[0,1,4,9,np.inf],labels=['1','2–4','5–9','10+']).astype(str)
    vc=['corpus','country_code','institution_group','paper_bin'];views=er[vc].drop_duplicates().sort_values(vc).reset_index(drop=True);views['view_index']=np.arange(len(views));er=er.merge(views,validate='many_to_one').sort_values('eidx').reset_index(drop=True)
    totals=er.groupby(['corpus','country_code'])[['first_hit','last_hit']].transform('sum');rolevalid=(totals.to_numpy()>0).astype('int8')
    er['first_R_defined']=rolevalid[:,0].astype(bool);er['last_R_defined']=rolevalid[:,1].astype(bool)
    # CSR institutional entity incidence. A multiple institution author can hit >1 entity.
    instptr=np.r_[0,np.cumsum(np.bincount(ai.aidx,minlength=len(a)))].astype('int64');instidx=ai.eidx.to_numpy('int32')
    mainweight=np.column_stack([p.main_member.to_numpy(float),p.main_weight.to_numpy(float)])
    arrays=dict(pool_ptr=poolptr,pool_authors=np.arange(len(a),dtype='int64'),group_weights=gw,country_ptr=countryptr,country_idx=countryidx,country_weight=countryweight,
      inst_ptr=instptr,inst_entity=instidx,entity_view=er.view_index.to_numpy('int32'),entity_role_valid=rolevalid,inst_eligible=p.inst_eligible.to_numpy('int8'),corpus=p.corpus.map(CORPORA.index).to_numpy('int8'),weights=mainweight)
    np.savez_compressed(d/'conditional_reference_inputs.npz',**arrays);er.to_parquet(d/'institution_zero_entities.parquet',index=False);p.to_parquet(d/'conditional_reference_studies.parquet',index=False)
    c.close();del ai,members,counts,ac,a
    src=ROOT/'code/endpoint_reference.cpp';lib=ROOT/'code'/('endpoint_reference.dylib' if sys.platform=='darwin' else 'endpoint_reference.so');compiler=os.environ.get('CXX') or shutil.which('c++') or 'c++';cmd=[compiler,'-std=c++17','-O3','-fPIC','-dynamiclib' if sys.platform=='darwin' else '-shared',str(src),'-o',str(lib)];subprocess.run(cmd,check=True,capture_output=True)
    fn=ctypes.CDLL(str(lib)).endpoints;P=ctypes.c_void_p;I=ctypes.c_int64;fn.argtypes=[I,ctypes.c_uint64,I]+[P]*10+[I,P,P,I,P,P,P,P,P,P];fn.restype=ctypes.c_int
    # C ABI arguments are kept explicit to make pointer/data-type auditing possible.
    fn.argtypes=[I,ctypes.c_uint64,I,P,P,P,P,P,P,P,P,I,P,P,I,P,P,P,P,P,P]
    g=np.zeros((B,2,2,18));zz=np.zeros((B,len(views),2),dtype='int32');ez=np.zeros((len(er),2),dtype='int32')
    arrays={k:np.ascontiguousarray(v) for k,v in arrays.items()};ptr=lambda name:arrays[name].ctypes.data_as(P)
    print('Conditional reference teams / institutions:',len(p),len(er),flush=True);start=time.time()
    ret=fn(B,SEED+4004,len(p),ptr('pool_ptr'),ptr('pool_authors'),ptr('group_weights'),ptr('country_ptr'),ptr('country_idx'),ptr('country_weight'),ptr('inst_ptr'),ptr('inst_entity'),len(er),ptr('entity_view'),ptr('entity_role_valid'),len(views),ptr('inst_eligible'),ptr('corpus'),ptr('weights'),g.ctypes.data_as(P),zz.ctypes.data_as(P),ez.ctypes.data_as(P));require(ret==0,'Native endpoint return '+str(ret))
    np.savez_compressed(ROOT/'draws/conditional_reference.npz',group=g,zero_counts=zz,entity_zero=ez)
    rows=[]
    for k,corpus in enumerate(CORPORA):
      for j,setting in enumerate(['raw_full','standardized']):
        x=g[:,k,j,:17]/g[:,k,j,17,None]
        for i in range(17):
          lo,hi=np.quantile(x[:,i],[.025,.975]);rows.append(dict(corpus=corpus,setting=setting,first_group=GROUPS[i//4] if i<16 else 'same_country',last_group=GROUPS[i%4] if i<16 else 'same_country',conditional_mean=x[:,i].mean(),reference_low=lo,reference_high=hi,MC_standard_error=x[:,i].std(ddof=1)/np.sqrt(B),replicates=B,seed=SEED+4004,range_type='conditional_random_distinct_author_endpoint_range_NOT_bootstrap_CI'))
    save('conditional_pair_reference',pd.DataFrame(rows))
    zr=[]
    for v in views.itertuples():
      e=er[er.view_index.eq(v.view_index)]
      for j,role in enumerate(['first','last']):
        ee=e[e[role+'_R_defined']];draw=zz[:,v.view_index,j];lo,hi=np.quantile(draw,[.025,.975]);expected=ee.analytic_P0.sum();n=len(ee)
        zr.append(dict(**{k:getattr(v,k) for k in vc},role=role,n_entities=n,n_R_undefined=len(e)-n,observed_zero=int(ee[role+'_hit'].eq(0).sum()),expected_zero=expected,simulated_mean=draw.mean(),reference_low=lo,reference_high=hi,MC_standard_error=draw.std(ddof=1)/np.sqrt(B),observed_zero_pct=100*ee[role+'_hit'].eq(0).mean() if n else np.nan,expected_zero_pct=100*expected/n if n else np.nan,range_type='conditional_endpoint_reference_count_range_NOT_estimate_CI',replicates=B))
    save('institution_zero_reference',pd.DataFrame(zr));er['MC_P0_first']=ez[:,0]/B;er['MC_P0_last']=ez[:,1]/B;save('institution_zero_entities',er)
    check=np.abs(ez/B-er.analytic_P0.to_numpy()[:,None]);require(np.all(check<=.08),'Analytic/Monte Carlo zero discrepancy')
    views.to_csv(ROOT/'tables/institution_zero_view_registry.csv',index=False)
    dump(marker,dict(status='PASS',replicates=B,seed=SEED+4004,elapsed_seconds=time.time()-start,n_teams=len(p),institution_eligible_teams=p[p.inst_eligible].groupby('corpus').size().to_dict(),main_raw_teams=p[p.main_member].groupby('corpus').size().to_dict(),institutions=len(er),views=len(views),exact_P0='product_over_participating_papers(1 - affiliated_observed_authors / observed_team_authors)',distinct_endpoint_sampling=True,role_undefined_separate=True,source_sha256=sha(src),compiler=subprocess.run([compiler,'--version'],capture_output=True,text=True).stdout,command=cmd,max_entity_MC_P0_error=float(check.max())))
    print('Conditional reference / analytic institutional zero audit PASS',flush=True)
if __name__=='__main__':main()
