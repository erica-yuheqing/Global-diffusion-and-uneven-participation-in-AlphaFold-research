"""Exact uniform study matching without replacement via country-set frequency cells."""
from scipy.sparse import csr_matrix
from common import *

def credit_matrix(signatures,registry):
    lookup={c:i for i,c in enumerate(registry)};row=[];col=[];values=[]
    for i,sig in enumerate(signatures):
        if not sig:continue
        codes=sig.split('|');require(len(codes)==len(set(codes)) and set(codes)<=set(registry),'Malformed full country set')
        for code in codes:row.append(i);col.append(lookup[code]);values.append(1/len(codes))
    return csr_matrix((values,(row,col)),shape=(len(signatures),len(registry)))

def stratify(patterns,year,spec):
    x=patterns[patterns.year.eq(year)&patterns.group.isin(['AF','C'])].copy()
    if spec.endswith('known_country'):x=x[x.signature.ne('')]
    keys=['work_type','subfield'] if spec!='count_only' else []
    if not keys:x['all_strata']='all';keys=['all_strata']
    targets=x[x.group.eq('AF')].groupby(keys,sort=True).n.sum();groups=[];support=[]
    for key,k in targets.items():
        key=key if isinstance(key,tuple) else (key,);mask=x.group.eq('C')
        for field,val in zip(keys,key):mask &= x[field].eq(val)
        pool=x[mask].groupby('signature',sort=True).n.sum()
        support.append(dict(year=year,spec=spec,stratum='|'.join(map(str,key)),AF_target=int(k),non_AF_available=int(pool.sum()),supported=pool.sum()>=k,AF_fixed=True))
        groups.append((int(k),pool))
    return x,groups,pd.DataFrame(support)

def run(out):
    require(not (out/'tables/matching_summary.parquet').exists(),'Do not overwrite archived matching')
    p=load(out,'study_country_patterns');registry=sorted(load(out,'annual_country_credits').country_code.unique());audit=[];plans=[]
    for si,spec in enumerate(SPECS):
        for year in range(2020,2026):
            x,groups,support=stratify(p,year,spec);audit.append(support);plans.append((si,spec,year,x,groups))
    support=pd.concat(audit,ignore_index=True);save(out,'matching_stratum_support',support)
    require(support.supported.all(),'Insufficient non-AF stratum; no draws sent and no fallback')
    draws=[];summaries=[]
    for si,spec,year,x,groups in plans:
        rng=np.random.default_rng(np.random.SeedSequence([SEED,si,year]));credit=np.zeros((REPS,len(registry)));selected=np.zeros(REPS,dtype=np.int64)
        af=x[x.group.eq('AF')].groupby('signature',sort=True).n.sum();AFcredit=np.asarray(credit_matrix(af.index.tolist(),registry).T@af.to_numpy()).ravel();afg=float(gini(AFcredit))
        for k,pool in groups:
            matrix=credit_matrix(pool.index.tolist(),registry)
            for start in range(0,REPS,128):
                stop=min(start+128,REPS);freq=rng.multivariate_hypergeometric(pool.to_numpy(dtype=np.int64),k,size=stop-start,method='marginals')
                require((freq<=pool.to_numpy()).all() and (freq.sum(axis=1)==k).all(),'Without-replacement draw contract broken')
                credit[start:stop]+=np.asarray(matrix.T@freq.T).T;selected[start:stop]+=k
        require(np.all(selected==af.sum()),'Matching study count differs from AF target')
        cg=gini(credit);gaps=afg-cg;require(np.isfinite(gaps).all(),'Undefined matched Gini draw')
        draws.extend(dict(spec=spec,year=year,replicate=i,AF_gini=afg,matched_non_AF_gini=float(cg[i]),gap=float(gaps[i]),matched_studies=int(selected[i]),known_credit=float(credit[i].sum())) for i in range(REPS))
        lo,hi=np.quantile(gaps,[.025,.975]);summaries.append(dict(spec=spec,year=year,n_AF=int(af.sum()),replicates=REPS,AF_gini=afg,matched_non_AF_mean=float(cg.mean()),point=float(gaps.mean()),lower=float(lo),upper=float(hi),interval_type='central95_conditional_matched_range_AF_fixed',seed=SEED))
        print(f'Matching {spec} {year}: n={int(af.sum())}; gap={gaps.mean():.6f};2000 draws',flush=True)
    d=pd.DataFrame(draws);save(out,'matching_draws',d);summary=pd.DataFrame(summaries);save(out,'matching_summary',summary)
    changes=[]
    for spec,x in d.groupby('spec',sort=False):
        v=x.pivot(index='replicate',columns='year',values='gap')
        for start in [2021,2022]:
            delta=v[2025]-v[start];lo,hi=np.quantile(delta,[.025,.975])
            changes.append(dict(spec=spec,start=start,end=2025,point=float(delta.mean()),lower=float(lo),upper=float(hi),replicates=REPS,interval_type='conditional_endpoint_matched_range_independent_year_streams'))
    save(out,'matching_endpoint_changes',pd.DataFrame(changes))
    dump(out/'provenance/matching_protocol.json',dict(seed=SEED,replicates=REPS,AF_fixed=True,replace=False,
      sampling='multivariate hypergeometric on integer study-country-set counts, equivalent to uniform study sampling without replacement',
      original_named_handoff_not_available=True,comparison_to_document='Monte Carlo reconstruction; do not force rounded prose example values',
      specs=SPECS,unknown_country='Included as empty country sets except known_country specification',all_support_passed=True))

if __name__=='__main__':run(OUT)
