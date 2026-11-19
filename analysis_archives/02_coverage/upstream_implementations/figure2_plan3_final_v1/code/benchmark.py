"""Global fixed-K, whole-study permutation with exact hypergeometric means."""
import time
import itertools
import numpy as np
import pandas as pd
from scipy.special import gammaln
from scipy.sparse import csr_matrix
from support import *

def log_none(n, k, m):
    """log[C(n-m,k)/C(n,k)] with impossible/empty edge cases explicit."""
    n,k,m=np.broadcast_arrays(np.asarray(n,dtype=float),np.asarray(k,dtype=float),np.asarray(m,dtype=float))
    require(((n>=0)&(k>=0)&(k<=n)&(m>=0)&(m<=n)).all(),'Invalid hypergeometric counts')
    result=np.zeros(n.shape,dtype=float)
    impossible=n-m<k
    result[impossible]=-np.inf
    use=(~impossible)&(k>0)&(m>0)
    nn,kk,mm=n[use],k[use],m[use]
    result[use]=(gammaln(nn-mm+1)-gammaln(nn-mm-kk+1)-gammaln(nn+1)+gammaln(nn-kk+1))
    return np.minimum(result,0)

class Sampler:
    def __init__(self, codes, z):
        self.codes=np.asarray(codes,dtype=np.int64);self.z=np.asarray(z,dtype=np.int8)
        require(set(np.unique(self.z))<=set([0,1]),'Only known binary labels can be permuted')
        self.n=np.bincount(self.codes)
        self.k=np.bincount(self.codes,weights=self.z,minlength=len(self.n)).astype(int)
        order=np.argsort(self.codes,kind='stable');starts=np.r_[0,np.cumsum(self.n)]
        self.mutable=np.flatnonzero((self.k>0)&(self.k<self.n))
        self.fixed=np.flatnonzero(self.z & (self.k[self.codes]==self.n[self.codes]))
        self.blocks=[order[starts[h]:starts[h+1]] for h in self.mutable]
        self.draw_k=self.k[self.mutable]
    def draw(self,rng):
        return np.concatenate([self.fixed]+[rng.choice(block,int(k),replace=False) for block,k in zip(self.blocks,self.draw_k)])

def expanded_rows(indptr,indices,selected):
    counts=np.diff(indptr)[selected];total=int(counts.sum())
    if total==0:return np.array([],dtype=int)
    starts=indptr[selected]
    offsets=np.repeat(starts,counts)+np.arange(total)-np.repeat(np.cumsum(counts)-counts,counts)
    return indices[offsets]

def active_cells(indptr,indices,selected,cell_by_inst,ncells):
    active=np.unique(expanded_rows(indptr,indices,selected))
    cell_year=cell_by_inst[active//6]*6+active%6
    return np.bincount(cell_year,minlength=ncells*6).reshape(ncells,6)

def ratio(low,high):
    low,high=np.broadcast_arrays(np.asarray(low,dtype=float),np.asarray(high,dtype=float))
    return np.divide(low,high,out=np.full(low.shape,np.nan),where=high>0)

def summarize_coverage(coverage,weights):
    """coverage[country,scale,year], weights[context,country]."""
    A=np.einsum('sc,cgy->sgy',weights,coverage)
    R=ratio(A[:,0,:],A[:,2,:]);G=100*(A[:,2,:]-A[:,0,:])
    return A,R,G,G[:,5]-G[:,1]

def make_weights(country,minimum=20,fractional=False):
    eligible=country[f'eligible_{minimum}'].to_numpy(bool)
    names=country.fractional_context if fractional else country.context
    w=np.zeros((4,len(country)))
    for j,context in enumerate(CONTEXTS):
        select=eligible if context=='All' else eligible&names.eq(context).to_numpy()
        if select.any():w[j,select]=1/select.sum()
    return w

def holm(p):
    p=np.asarray(p,float);order=np.argsort(p);adjusted=np.empty(len(p));running=0.
    for rank,i in enumerate(order):
        running=max(running,(len(p)-rank)*p[i]);adjusted[i]=min(1.,running)
    return adjusted

def setup(out,variant='main'):
    p=pd.read_parquet(out/'tables/opportunity_studies.parquet',columns=['study_id','year','field','country_set','document_type','team_bin','z'])
    p['paper_index']=np.arange(len(p),dtype=np.int32)
    keys=['field','year','country_set']
    if variant=='document_type':keys.append('document_type')
    elif variant=='team_size':keys.append('team_bin')
    elif variant!='main':raise ValueError('Unknown benchmark variant')
    codes,levels=pd.factorize(pd.MultiIndex.from_frame(p[keys]),sort=True)
    sampler=Sampler(codes,p.z.to_numpy())
    audit=levels.to_frame(index=False);audit['stratum_id']=np.arange(len(audit))
    audit['n_h']=sampler.n;audit['K_h']=sampler.k
    audit['AF_fraction']=audit.K_h/audit.n_h
    audit['exchangeable']=(audit.K_h>0)&(audit.K_h<audit.n_h)
    audit['variant']=variant
    save(out,'strata_audit' if variant=='main' else 'strata_audit_'+variant,audit)
    country=load(out,'country_context').query('eligible_10').sort_values('country').reset_index(drop=True)
    base=load(out,'baseline_groups');base=base[base.eligible_10].sort_values('institution_id').reset_index(drop=True)
    base['inst_index']=np.arange(len(base),dtype=np.int32)
    cc=country.country.tolist();base['country_index']=pd.Categorical(base.country,categories=cc).codes.astype(np.int64)
    cell=base.country_index.to_numpy(dtype=np.int64)*3+pd.Categorical(base.group,categories=GROUPS).codes.astype(np.int64)
    require((cell>=0).all(),'Institution has no fixed cell')
    denominator=np.bincount(cell,minlength=3*len(country)).reshape(len(country),3)
    require((denominator>=10).all(),'A retained domestic group violates N10')
    with connect(out) as c:
        c.register('paper_ids',p[['study_id','paper_index','year']]);c.register('inst_ids',base[['institution_id','inst_index']])
        links=c.execute(f'''SELECT p.paper_index,i.inst_index,p.year FROM read_parquet({lit(out/'tables/opportunity_memberships.parquet')}) m
          JOIN paper_ids p USING(study_id) JOIN inst_ids i USING(institution_id)''').df()
    require(not links.duplicated(['paper_index','inst_index']).any(),'Duplicate paper-institution connection')
    matrix=csr_matrix((np.ones(len(links),dtype=np.int8),(links.paper_index.to_numpy(),links.inst_index.to_numpy()*6+links.year.to_numpy()-2020)),shape=(len(p),len(base)*6))
    matrix.sort_indices()
    # Hypergeometric probability uses counts of *unique studies*, not fractional credit.
    hs=codes[links.paper_index.to_numpy()]
    exp=pd.DataFrame(dict(inst=links.inst_index.to_numpy(),year=links.year.to_numpy()-2020,h=hs)).groupby(['inst','year','h']).size().rename('m').reset_index()
    exp['log_none']=log_none(sampler.n[exp.h],sampler.k[exp.h],exp.m.to_numpy())
    iy=exp.inst.to_numpy()*6+exp.year.to_numpy()
    sums=np.zeros(len(base)*6)
    np.add.at(sums,iy,exp.log_none.to_numpy())
    q=-np.expm1(sums).reshape(len(base),6)
    expect=np.zeros((len(country)*3,6));non_deterministic=np.zeros_like(expect)
    for y in range(6):np.add.at(expect[:,y],cell,q[:,y])
    for y in range(6):np.add.at(non_deterministic[:,y],cell,((q[:,y]>1e-9)&(q[:,y]<1-1e-9)).astype(int))
    expect=expect.reshape(len(country),3,6)/denominator[:,:,None]
    observed_n=active_cells(matrix.indptr,matrix.indices,np.flatnonzero(p.z.to_numpy()),cell,len(country)*3)
    observed=observed_n.reshape(len(country),3,6)/denominator[:,:,None]
    # Share of opportunities/AF relations exposed to exchangeable strata, by country/scale.
    links['cell']=cell[links.inst_index.to_numpy()]
    links['mutable']=audit.exchangeable.to_numpy()[hs]
    links['AF']=p.z.to_numpy()[links.paper_index.to_numpy()]
    links['mutable_AF']=links.mutable&links.AF.eq(1)
    ex=links.groupby('cell').agg(opportunity_relations=('cell','size'),mutable_relations=('mutable','sum'),AF_relations=('AF','sum'),mutable_AF_relations=('mutable_AF','sum')).reset_index()
    ex['country']=[cc[v//3] for v in ex.cell];ex['group']=[GROUPS[v%3] for v in ex.cell]
    ex['mutable_relation_fraction']=ex.mutable_relations/ex.opportunity_relations
    ex['mutable_AF_relation_fraction']=ratio(ex.mutable_AF_relations,ex.AF_relations)
    save(out,'exchangeability_coverage_'+variant,ex)
    exchange=dict(variant=variant,strata=len(audit),mutable_strata=int(audit.exchangeable.sum()),
      papers=len(p),AF_papers=int(p.z.sum()),mutable_papers=int(audit.loc[audit.exchangeable,'n_h'].sum()),
      mutable_AF_papers=int(audit.loc[audit.exchangeable,'K_h'].sum()),institution_relations=len(links))
    dump(out/'provenance'/('exchangeability_'+variant+'.json'),exchange)
    print(f'{variant}: {len(p):,} opportunities; {exchange["mutable_strata"]:,} mutable strata; {exchange["mutable_AF_papers"]}/{exchange["AF_papers"]} AF exchangeable',flush=True)
    return dict(p=p,codes=codes,sampler=sampler,country=country,base=base,cell=cell,denominator=denominator,
                matrix=matrix,observed=observed,expected=expect,audit=audit,exchange=exchange,
                analytically_deterministic=(non_deterministic==0).reshape(len(country),3,6))

def verify_draw(s, selected):
    require(len(selected)==len(np.unique(selected)),'A study was drawn twice')
    require(np.array_equal(np.bincount(s['codes'][selected],minlength=len(s['sampler'].n)),s['sampler'].k),'Stratum K not preserved')
    # Stronger named invariants: complete known country set fixes integer/fractional country AF participation.
    p=s['p'];cols=['year','country_set']
    before=p[p.z.eq(1)].groupby(cols).size().sort_index()
    after=p.iloc[selected].groupby(cols).size().sort_index()
    require(before.equals(after),'Country-set/year AF counts changed')
    return True

def observed_tables(out,s):
    country=s['country'];base=s['base'];den=s['denominator']
    # Cumulative confirmed observation (not necessarily identifiable true first adoption).
    states=load(out,'institution_year_observed');states=states[states.institution_id.isin(base.institution_id)]
    hist=load(out,'entry_year_audit').set_index('institution_id').reindex(base.institution_id)
    earliest=states[states.pool_AF_studies.gt(0)].groupby('institution_id').year.min().reindex(base.institution_id).to_numpy()
    rows=[]
    for y in np.arange(2019,2026):
        cumulative=np.bincount(s['cell'],weights=(earliest<=y).astype(int),minlength=len(country)*3).reshape(len(country),3)
        for ci,c in country.iterrows():
            for gi,g in enumerate(GROUPS):
                active_n=int(round(s['observed'][ci,gi,y-2020]*den[ci,gi])) if y>=2020 else int(states[(states.year==y)&states.AF_studies.gt(0)&states.institution_id.isin(base[(base.country==c.country)&(base.group==g)].institution_id)].institution_id.nunique())
                rows.append(dict(country=c.country,context=c.context,group=g,year=y,fixed_N=int(den[ci,gi]),
                  active_N=active_n,cumulative_N=int(cumulative[ci,gi]),A=active_n/den[ci,gi],C=cumulative[ci,gi]/den[ci,gi],
                  eligible_10=c.eligible_10,eligible_20=c.eligible_20,eligible_30=c.eligible_30))
    cells=pd.DataFrame(rows);save(out,'country_group_year',cells)
    contexts=[]
    for minimum in [10,20,30]:
        for context in CONTEXTS:
            eligible=country[f'eligible_{minimum}'];select=country[eligible&(True if context=='All' else country.context.eq(context))]
            if not len(select):continue
            a=cells[cells.country.isin(select.country)].groupby(['group','year'])[['A','C']].mean().reset_index()
            ah=a.pivot(index='year',columns='group',values='A')
            for row in a.itertuples():
                contexts.append(dict(analysis=f'N{minimum}',context=context,group=row.group,year=row.year,
                  countries=len(select),country_weight=1/len(select),A=row.A,C=row.C,
                  R=float(ratio(ah.loc[row.year,'L'],ah.loc[row.year,'H'])),G=100*(ah.loc[row.year,'H']-ah.loc[row.year,'L']),weighting='equal country'))
    ctx=pd.DataFrame(contexts);save(out,'context_group_year',ctx)
    save(out,'panel_a_source',ctx[(ctx.analysis=='N20')&(ctx.context=='All')])
    save(out,'panel_b_source',ctx[(ctx.analysis=='N20')&(ctx.context!='All')&ctx.year.isin([2021,2025])].drop_duplicates(['context','year']))
    save(out,'entry_identification_summary',hist.assign(first_year_unknown_before_confirmed=hist.earliest_unknown_label_year.lt(hist.first_confirmed_year)).groupby(['eligible_20','pre2020_confirmed','first_year_unknown_before_confirmed'],dropna=False).size().rename('institutions').reset_index())
    # Explicitly descriptive denominator/weighting sensitivities; not new primary estimates.
    active=states[states.year.between(2020,2025)].merge(base[['institution_id','country','group']],on='institution_id',validate='many_to_one')
    active=active[active.general_studies.gt(0)].groupby(['country','group','year']).agg(generally_active_N=('institution_id','size')).reset_index()
    ds=cells.merge(active,on=['country','group','year'],how='left',validate='one_to_one')
    ds['generally_active_N']=ds.generally_active_N.fillna(0)
    ds['conditional_active_coverage']=ratio(ds.active_N,ds.generally_active_N)
    save(out,'generally_active_denominator_sensitivity',ds)
    iw=cells[cells.eligible_20].groupby(['context','group','year'])[['fixed_N','active_N','cumulative_N']].sum().reset_index()
    iw['A']=iw.active_N/iw.fixed_N;iw['C']=iw.cumulative_N/iw.fixed_N
    iw['weighting']='institution count, not equal countries'
    save(out,'institution_weighted_descriptives',iw)

def run_simulation(out,s,variant,B,seed,prefix):
    rng=np.random.default_rng(seed);matrix=s['matrix'];nc=len(s['country']);den=s['denominator']
    configs={'main':make_weights(s['country'])}
    if variant=='main':
        configs.update(N10=make_weights(s['country'],10),N30=make_weights(s['country'],30),fractional_context=make_weights(s['country'],20,True))
    values={k:np.zeros((B,4,3,6)) for k in configs}
    sumc=np.zeros((nc,3,6));sumsqc=np.zeros_like(sumc);t=time.monotonic()
    for b in range(B):
        chosen=s['sampler'].draw(rng)
        require(np.array_equal(np.bincount(s['codes'][chosen],minlength=len(s['sampler'].n)),s['sampler'].k),'Per-replicate stratum K changed')
        if b<3 or b==B-1:verify_draw(s,chosen)
        counts=active_cells(matrix.indptr,matrix.indices,chosen,s['cell'],nc*3)
        coverage=counts.reshape(nc,3,6)/den[:,:,None]
        sumc+=coverage;sumsqc+=coverage*coverage
        for key,w in configs.items():values[key][b]=np.einsum('sc,cgy->sgy',w,coverage)
        if (b+1)%200==0 or b==B-1:print(f'{prefix}/{variant}: {b+1}/{B}; {time.monotonic()-t:.1f}s',flush=True)
    mean=sumc/B;mcse=np.sqrt(np.maximum((sumsqc-B*mean*mean)/(B-1),0)/B)
    check=[]
    for ci,c in s['country'].iterrows():
        for gi,g in enumerate(GROUPS):
            for yi,y in enumerate(YEARS):
                diff=mean[ci,gi,yi]-s['expected'][ci,gi,yi]
                check.append(dict(country=c.country,group=g,year=y,analytic_A=s['expected'][ci,gi,yi],simulated_A=mean[ci,gi,yi],
                    difference=diff,MCSE=mcse[ci,gi,yi],standardized_error=diff/mcse[ci,gi,yi] if mcse[ci,gi,yi]>1e-12 else np.nan,
                    deterministic_match=abs(diff)<1e-8 if s['analytically_deterministic'][ci,gi,yi] else True,
                    analytically_deterministic=bool(s['analytically_deterministic'][ci,gi,yi]),
                    zero_sample_variance_not_proof_of_determinism=mcse[ci,gi,yi]<=1e-12 and not s['analytically_deterministic'][ci,gi,yi],
                    variant=variant,draws=B))
    checks=pd.DataFrame(check);save(out,f'{prefix}_analytic_check_{variant}',checks)
    require(checks.deterministic_match.all(),'Deterministic hypergeometric expectation differs from simulation')
    # Across many dependent cells an isolated 4-sigma fluctuation is diagnostic, not a direction-based stop.
    # Primary aggregate means are checked before release using independent pilot and full run.
    summary=[];replicates=[];contrasts=[];residuals=[]
    for setting,w in configs.items():
        actualA,actualR,actualG,actualD=summarize_coverage(s['observed'],w)
        exactA,_,exactG,exactD=summarize_coverage(s['expected'],w)
        draws=values[setting];G=100*(draws[:,:,2,:]-draws[:,:,0,:]);D=G[:,:,5]-G[:,:,1]
        R=ratio(draws[:,:,0,:],draws[:,:,2,:]);U=D-exactD[None,:];E=actualD-exactD
        pvalues=[]
        for j,context in enumerate(CONTEXTS):
            q=np.quantile(D[:,j],[.025,.975]);u=np.quantile(U[:,j],[.025,.975]);se=D[:,j].std(ddof=1)/np.sqrt(B)
            count=int((w[j]>0).sum())
            pv=(1+int((np.abs(U[:,j])>=abs(E[j])).sum()))/(B+1);pvalues.append(pv)
            summary.append(dict(variant=variant,setting=setting,context=context,countries=count,draws=B,
                actual_delta_G=actualD[j],expected_delta_G=exactD[j],simulated_mean_delta_G=D[:,j].mean(),
                excess=E[j],reference_low=q[0],reference_high=q[1],centered_low=u[0],centered_high=u[1],
                MCSE_mean_pp=se,mean_check_error_pp=D[:,j].mean()-exactD[j],
                mean_within_5MCSE=abs(D[:,j].mean()-exactD[j])<=5*se+1e-6,
                randomization_p=pv,R2021_undefined_draws=int(np.isnan(R[:,j,1]).sum()),R2025_undefined_draws=int(np.isnan(R[:,j,5]).sum()),
                interval_type='conditional benchmark reference range, not confidence interval'))
            for b in range(B):
                replicates.append(dict(variant=variant,setting=setting,replicate=b+1,context=context,delta_G=D[b,j],
                    G2021=G[b,j,1],G2025=G[b,j,5],R2021=R[b,j,1],R2025=R[b,j,5]))
            for gi,g in enumerate(GROUPS):
                residuals.append(dict(variant=variant,setting=setting,context=context,group=g,
                    observed_change_pp=100*(actualA[j,gi,5]-actualA[j,gi,1]),
                    expected_change_pp=100*(exactA[j,gi,5]-exactA[j,gi,1]),
                    residual_change_pp=100*((actualA[j,gi,5]-actualA[j,gi,1])-(exactA[j,gi,5]-exactA[j,gi,1]))))
        for low,high,primary in [(1,3,True),(1,2,False),(2,3,False)]:
            h=E[low]-E[high];draw=U[:,low]-U[:,high];q=np.quantile(draw,[.025,.975])
            pv=(1+int((np.abs(draw)>=abs(h)).sum()))/(B+1);pvalues.append(pv)
            contrasts.append(dict(variant=variant,setting=setting,context=CONTEXTS[low],reference_context=CONTEXTS[high],primary=primary,
                observed_excess_difference=h,centered_low=q[0],centered_high=q[1],MCSE_mean_pp=draw.std(ddof=1)/np.sqrt(B),
                randomization_p=pv,draws=B,interval_type='paired centered conditional reference range'))
        adjusted=holm(pvalues)
        for row,pv in zip(summary[-4:],adjusted[:4]):row['holm_p_7_tests']=pv
        for row,pv in zip(contrasts[-3:],adjusted[4:]):row['holm_p_7_tests']=pv
    save(out,prefix+'_benchmark_summary_'+variant,pd.DataFrame(summary))
    save(out,prefix+'_benchmark_replicates_'+variant,pd.DataFrame(replicates))
    save(out,prefix+'_context_contrasts_'+variant,pd.DataFrame(contrasts))
    save(out,prefix+'_residual_heatmap_'+variant,pd.DataFrame(residuals))
    timing=dict(variant=variant,stage=prefix,draws=B,seed=seed,seconds=time.monotonic()-t,
      mutable_AF=s['exchange']['mutable_AF_papers'],full_country_set_invariants_checked=[1,2,3,B],
      stratum_K_checked_every_replicate=True,all_global_labels_unique=True)
    dump(out/'provenance'/f'{prefix}_runtime_{variant}.json',timing)
    return pd.DataFrame(summary),pd.DataFrame(contrasts)

def run(out):
    summaries=[];contrasts=[];reps=[];residuals=[]
    for index,variant in enumerate(['main','document_type','team_size']):
        s=setup(out,variant)
        if variant=='main':
            observed_tables(out,s)
            pilot,_=run_simulation(out,s,variant,200,SEED+1,'pilot')
            require(pilot.mean_within_5MCSE.all(),'Pilot aggregate analytic mean mismatch')
        result,contrast=run_simulation(out,s,variant,5000,SEED+100*index,'main')
        if result.MCSE_mean_pp.max()>.05 or contrast.MCSE_mean_pp.max()>.05:
            # Fixed rule, not selected by observed effect/p value. Distinct deterministic 10k rerun.
            result,contrast=run_simulation(out,s,variant,10000,SEED+100*index,'extended')
            prefix='extended'
        else:prefix='main'
        require(result.mean_within_5MCSE.all(),'Primary aggregate simulation differs from analytic expectation')
        summaries.append(result);contrasts.append(contrast)
        reps.append(load(out,prefix+'_benchmark_replicates_'+variant))
        residuals.append(load(out,prefix+'_residual_heatmap_'+variant))
        if variant=='main':
            save(out,'analytic_expectation_check',load(out,prefix+'_analytic_check_'+variant))
        del s
    save(out,'benchmark_summary',pd.concat(summaries,ignore_index=True))
    save(out,'context_contrasts',pd.concat(contrasts,ignore_index=True))
    save(out,'benchmark_replicates',pd.concat(reps,ignore_index=True))
    save(out,'residual_heatmap',pd.concat(residuals,ignore_index=True))
    main=pd.concat(summaries).query('variant=="main" and setting=="main"')
    save(out,'panel_c_source',main[main.context.eq('All')])
    save(out,'panel_d_source',main[~main.context.eq('All')])
    cs=pd.concat(contrasts);primary=cs[cs.primary&cs.setting.eq('main')]
    signs=np.sign(primary.observed_excess_difference)
    mainh=primary[primary.variant.eq('main')].iloc[0]
    stable=bool((mainh.observed_excess_difference<mainh.centered_low or mainh.observed_excess_difference>mainh.centered_high)
                and (signs==signs.iloc[0]).all())
    dump(out/'provenance/panel_d_decision.json',dict(main_panel=stable,
        reason='Primary paired low-high contrast outside main centered reference range and sign consistent in two benchmark refinements' if stable else 'No prespecified stable heterogeneity support; d retained in Extended Data',
        no_independent_replication_claim=True))

if __name__=='__main__':run(OUT)
