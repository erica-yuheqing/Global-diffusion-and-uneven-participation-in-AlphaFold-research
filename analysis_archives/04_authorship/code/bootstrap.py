"""Joint full-study-vector stratified multinomial bootstrap, fixed support/weights."""
from common import *
from scipy import sparse
import hashlib
def bounds(x):
    x=np.asarray(x,float);v=x[np.isfinite(x)];deg=len(v)>0 and np.ptp(v)<1e-14
    if len(v)>=.95*B and not deg:lo,hi=np.quantile(v,[.025,.975]);reason=''
    else:lo=hi=np.nan;reason='degenerate_conditional_draws' if deg else 'fewer_than_95pct_defined_replicates'
    return dict(ci_low=lo,ci_high=hi,valid_replicates=len(v),invalid_replicates=B-len(v),degenerate=deg,undefined_reason=reason)
def compression(m,X,name):
    signatures=[]
    for i in range(len(m)):
        l,r=X.indptr[i:i+2];signatures.append(hashlib.sha256(X.indices[l:r].tobytes()+X.data[l:r].tobytes()).hexdigest())
    d=m[['corpus']+KEY+['supported','weight']].copy();d['signature']=signatures;d['rep']=np.arange(len(m))
    for k in KEY:d[k]=d[k].astype('string').fillna('__MISSING__')
    g=d.groupby(['corpus']+KEY+['signature'],sort=True,dropna=False).agg(n=('rep','size'),rep=('rep','first'),supported=('supported','first'),weight=('weight','first')).reset_index()
    require(g.n.sum()==len(m),'Compression lost studies')
    # Cryptographic grouping never rounds the feature vector; exact representatives are retained.
    Z=X[g.rep.to_numpy(np.int64)].tocsr();g.to_parquet(ROOT/'draws'/f'{name}_bootstrap_patterns.parquet',index=False)
    dump(ROOT/'provenance'/f'{name}_compression.json',dict(full_studies=len(m),patterns=len(g),rule='Exact binary full-study feature vector and corpus/year/type/subfield; no rounding; joint multiplicities',sum_counts=int(g.n.sum())))
    return g,Z
def ratios(pool,meta):
    E=meta['n_entities'];nc=meta['n_countries'];a=pool.reshape((-1,pool.shape[-1]))
    totals=np.stack([a[:,i*E:i*E+nc].sum(axis=1) for i in range(4)],axis=1)
    z=np.stack([div(a[:,i*E:(i+1)*E],totals[:,i,None]) for i in range(4)],axis=1)
    return np.stack([div(z[:,2:4],z[:,i,None,:]) for i in [0,1]],axis=1)
def pair_shares(pool,meta):
    out={}
    for key,n in [('observed_group',16),('expected_group',16),('structure',4)]:
        a=pool[...,meta['offsets'][key]:meta['offsets'][key]+n];out[key]=div(a,a.sum(axis=-1,keepdims=True))
    total=pool[...,meta['offsets']['observed_group']:meta['offsets']['observed_group']+16].sum(axis=-1)
    for key in ['same_country_observed','same_country_expected']:out[key]=div(pool[...,meta['offsets'][key]],total)
    return out
def fit(name,m,X,meta,seed_id=1):
    marker=ROOT/'provenance'/f'{name}_bootstrap_complete.json'
    if marker.exists():print('Retain committed',name,flush=True);return
    require(len(m)==X.shape[0] and m.study_id.is_unique,'Members/vector mapping')
    g,Z=compression(m,X,name);points={};draws={};seed=SEED+1009*seed_id
    for corpus in CORPORA:
        gi=np.flatnonzero(g.corpus.eq(corpus));h=g.iloc[gi].reset_index(drop=True);A=Z[gi].tocsr();counts=h.n.to_numpy(np.int64)
        strata=list(h.groupby(KEY,sort=True,dropna=False).indices.values());rng=np.random.default_rng(np.random.SeedSequence([seed,CORPORA.index(corpus)]))
        factors={'raw_full':np.ones(len(h)),'common_raw':h.supported.to_numpy(float),'standardized':h.weight.to_numpy(float)}
        for setting,f in factors.items():points[setting,corpus]=np.asarray(A.T@(counts*f)).ravel();draws[setting,corpus]=np.empty((B,X.shape[1]))
        for start in range(0,B,25):
            size=min(25,B-start);w=np.empty((len(h),size))
            for idx in strata:
                ns=int(counts[idx].sum());w[idx]=rng.multinomial(ns,counts[idx]/ns,size=size).T
            cached={}
            for setting,f in factors.items():
                signature=hashlib.sha256(f.tobytes()).digest()
                if signature not in cached:cached[signature]=np.asarray(A.T@(w*f[:,None])).T
                draws[setting,corpus][start:start+size]=cached[signature]
            if (start+size)%250==0:print(name,corpus,'joint whole-study bootstrap',start+size,'/',B,'patterns',len(h),flush=True)
    np.savez_compressed(ROOT/'draws'/f'{name}_joint_pools.npz',**{setting+'__'+corpus:x for (setting,corpus),x in draws.items()})
    dump(ROOT/'draws'/f'{name}_points.json',{s+'__'+c:v for (s,c),v in points.items()})
    summarize(name,m,X,meta,points,draws,seed)
    dump(marker,dict(status='PASS',seed=seed,seed_sequence='[seed, corpus_index]',replicates=B,strata='corpus/year/type/subfield within actual analysis cohort',study_n=len(m),patterns=len(g),joint_channels=True,fixed_weights=True,fixed_support=True,interval_type='conditional_stratified_whole_study_bootstrap_not_network_robust',meta=meta))
def summarize(name,m,X,meta,points,draws,seed):
    E=meta['n_entities'];nc=meta['n_countries'];rpoints={k:ratios(v[None,:],meta)[0] for k,v in points.items()};rdraw={k:ratios(v,meta) for k,v in draws.items()};rs=[];ds=[];cs=[];pair=[];structure=[];same=[];direction=[]
    presence=X[:,:E].copy();presence.data[:]=1
    countinfo={}
    for corpus in CORPORA:
        mask=m.corpus.eq(corpus).to_numpy()
        for setting in ['raw_full','common_raw','standardized']:
            w=mask.astype(float)
            if setting!='raw_full':w*=m.supported.to_numpy(float)
            if setting=='standardized':w*=m.weight.to_numpy(float)
            nn=np.asarray(presence.T@(w>0)).ravel();sw=np.asarray(presence.T@w).ravel();sw2=np.asarray(presence.T@(w*w)).ravel()
            countinfo[setting,corpus]=(nn,sw,sw2,int((w>0).sum()),w.sum(),div(w.sum()**2,np.sum(w*w)).item())
    for (setting,corpus),pool in points.items():
        nn,sw,sw2,N,total,ess=countinfo[setting,corpus]
        for b,benchmark in enumerate(['country','author']):
            for j,role in enumerate(['first','last']):
                for i,entity in enumerate(meta['entities']):
                    base=dict(analysis_id=name,setting=setting,corpus=corpus,benchmark=benchmark,role=role,entity_id=entity,level='group' if entity.startswith('group:') else 'country',n_studies=N,n_papers=int(nn[i]),sum_weights=total,global_ESS=ess,ESS=div(sw[i]**2,sw2[i]).item(),participation_credit=pool[b*E+i],role_credit=pool[(2+j)*E+i],participation_total=pool[b*E:b*E+nc].sum(),role_total=pool[(2+j)*E:(2+j)*E+nc].sum(),R=rpoints[setting,corpus][b,j,i],unit='dimensionless',interval_type='conditional_whole_study_bootstrap',seed=seed)
                    base.update(bounds(rdraw[setting,corpus][:,b,j,i]));rs.append(base)
    for setting in ['raw_full','common_raw','standardized']:
        a=rpoints[setting,'AF'];r=rpoints[setting,'reference'];d=a-r;dd=rdraw[setting,'AF']-rdraw[setting,'reference']
        for j,role in enumerate(['first','last']):
            for i,entity in enumerate(meta['entities']):
                for b,benchmark in enumerate(['country','author']):ds.append(dict(analysis_id=name,setting=setting,benchmark=benchmark,role=role,entity_id=entity,level='group' if entity.startswith('group:') else 'country',R_AF=a[b,j,i],R_reference=r[b,j,i],delta=d[b,j,i],unit='dimensionless',**bounds(dd[:,b,j,i])))
                direct=dd[:,1,j,i]-dd[:,0,j,i];absolute=np.abs(dd[:,0,j,i])-np.abs(dd[:,1,j,i]);bb=bounds(absolute)
                cs.append(dict(analysis_id=name,setting=setting,role=role,entity_id=entity,level='group' if entity.startswith('group:') else 'country',country_delta=d[0,j,i],author_delta=d[1,j,i],C=d[1,j,i]-d[0,j,i],B=abs(d[0,j,i])-abs(d[1,j,i]),unit='dimensionless',**bounds(direct),B_ci_low=bb['ci_low'],B_ci_high=bb['ci_high'],B_valid_replicates=bb['valid_replicates'],B_degenerate=bb['degenerate']))
        ps={c:pair_shares(points[setting,c][None,:],meta) for c in CORPORA};pdra={c:pair_shares(draws[setting,c],meta) for c in CORPORA}
        for c in CORPORA:
            N,total,ess=countinfo[setting,c][3:]
            for i,fg in enumerate(GROUPS):
                for j,lg in enumerate(GROUPS):
                    k=i*4+j;o=ps[c]['observed_group'][0,k];e=ps[c]['expected_group'][0,k];bdr=100*(pdra[c]['observed_group'][:,k]-pdra[c]['expected_group'][:,k]);ob=bounds(pdra[c]['observed_group'][:,k]);eb=bounds(pdra[c]['expected_group'][:,k]);cb=bounds(bdr)
                    pair.append(dict(analysis_id=name,setting=setting,corpus=c,first_group=fg,last_group=lg,observed_share=o,expected_share=e,observed_minus_expected_pp=100*(o-e),observed_ci_low=ob['ci_low'],observed_ci_high=ob['ci_high'],expected_bootstrap_low=eb['ci_low'],expected_bootstrap_high=eb['ci_high'],deviation_ci_low=cb['ci_low'],deviation_ci_high=cb['ci_high'],valid_replicates=cb['valid_replicates'],degenerate=cb['degenerate'],n_studies=N,sum_weights=total,ESS=ess,expected_zero=abs(e)<1e-15,interval_type='conditional_whole_study_bootstrap',unit='shares_0_1; deviation_percentage_points'))
            for k,category in enumerate(meta['structure_categories']):structure.append(dict(analysis_id=name,setting=setting,corpus=c,category=category,share=ps[c]['structure'][0,k],weighted_credit=ps[c]['structure'][0,k]*total,n_studies=N,total_credit=total,ESS=ess,**bounds(pdra[c]['structure'][:,k]),interval_type='conditional_whole_study_bootstrap'))
            for key in ['same_country_observed','same_country_expected']:same.append(dict(analysis_id=name,setting=setting,corpus=c,kind=key,share=ps[c][key][0],n_studies=N,sum_weights=total,ESS=ess,**bounds(pdra[c][key]),interval_type='conditional_whole_study_bootstrap'))
        for i,fg in enumerate(GROUPS):
            for j,lg in enumerate(GROUPS):
                k=i*4+j;af=100*(ps['AF']['observed_group'][0,k]-ps['AF']['expected_group'][0,k]);ref=100*(ps['reference']['observed_group'][0,k]-ps['reference']['expected_group'][0,k]);diff=100*((pdra['AF']['observed_group'][:,k]-pdra['AF']['expected_group'][:,k])-(pdra['reference']['observed_group'][:,k]-pdra['reference']['expected_group'][:,k]));row=dict(analysis_id=name,setting=setting,corpus='AF_minus_reference',first_group=fg,last_group=lg,observed_minus_expected_pp=af-ref,unit='percentage_points',**bounds(diff),interval_type='conditional_whole_study_bootstrap');pair.append(row)
                if i!=j:
                    rev=j*4+i;ad=100*((ps['AF']['observed_group'][0,k]-ps['AF']['expected_group'][0,k])-(ps['AF']['observed_group'][0,rev]-ps['AF']['expected_group'][0,rev]));rd=100*((ps['reference']['observed_group'][0,k]-ps['reference']['expected_group'][0,k])-(ps['reference']['observed_group'][0,rev]-ps['reference']['expected_group'][0,rev]));bd=diff-100*((pdra['AF']['observed_group'][:,rev]-pdra['AF']['expected_group'][:,rev])-(pdra['reference']['observed_group'][:,rev]-pdra['reference']['expected_group'][:,rev]));direction.append(dict(analysis_id=name,setting=setting,first_group=fg,last_group=lg,AF_direction_pp=ad,reference_direction_pp=rd,AF_minus_reference_direction_pp=ad-rd,unit='percentage_points',**bounds(bd)))
        for k,category in enumerate(meta['structure_categories']):structure.append(dict(analysis_id=name,setting=setting,corpus='AF_minus_reference',category=category,share=ps['AF']['structure'][0,k]-ps['reference']['structure'][0,k],**bounds(pdra['AF']['structure'][:,k]-pdra['reference']['structure'][:,k]),interval_type='conditional_whole_study_bootstrap'))
    for suffix,data in [('R',rs),('delta',ds),('benchmark_change',cs),('pairings',pair),('structure',structure),('same_country',same),('direction_contrasts',direction)]:save(name+'_'+suffix,pd.DataFrame(data))
def group_only(X,meta):
    E=meta['n_entities'];nc=meta['n_countries'];cols=[]
    for i in range(4):cols+=list(range(i*E+nc,(i+1)*E))
    cols+=list(range(4*E,X.shape[1]));m=dict(meta);m['entities']=['group:'+g for g in GROUPS];m['n_entities']=4;m['n_countries']=4;m['offsets']={k:v-4*E+16 for k,v in meta['offsets'].items()};return X[:,cols].tocsr(),m
def main():
    m=norm('analysis_members.parquet');meta=json.loads((ROOT/'inputs/normalized/feature_metadata.json').read_text());X=sparse.load_npz(ROOT/'inputs/normalized/feature_matrix.npz');fit('strict_main',m,X,meta,1)
if __name__=='__main__':main()
