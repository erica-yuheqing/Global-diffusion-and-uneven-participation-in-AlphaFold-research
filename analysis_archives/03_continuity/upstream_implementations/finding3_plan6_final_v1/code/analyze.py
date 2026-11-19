"""One shared twelve-month table; explicit populations and conditional denominators."""
from common import *

def entry_rates(x):
    rows=[]
    for co,g,q in scopes(x):
        for m in MODES:
            N=len(q);D=int(q['entry_'+m].notna().sum());Y=int(q['entry_'+m].eq(1).sum())
            rows.append(dict(cohort=co,size_group=g,activity=m,N=N,D=D,Y=Y,not_established=D-Y,unknown=N-D,
                fraction=ratio(Y,D),coverage=ratio(D,N),lower=ratio(Y,N),upper=ratio(Y+N-D,N)))
    return pd.DataFrame(rows)

def repeats(x):
    rows=[]
    for co,g,q in scopes(x):
        N=len(q);C=int(q.repeat_flag.fillna(False).sum());U=int(q.repeat_flag.isna().sum())
        rows.append(dict(cohort=co,size_group=g,N=N,C=C,U=U,known_no_event=N-C-U,fraction=ratio(C,N),upper=ratio(C+U,N)))
    return pd.DataFrame(rows)

def transitions(x):
    return pd.DataFrame([dict(cohort=co,size_group=g,activity=m,**transition(q,m)) for co,g,q in scopes(x) for m in MODES])

def standardize(df,group,outcome,strata,groups,analysis,mode,context='All'):
    """Direct standardization: pooled eligible common strata, outcome-blind N>=10."""
    q=df[df[group].isin(groups)].dropna(subset=[group,outcome,*strata]).copy()
    counts=q.groupby([*strata,group],observed=True).size().unstack(group,fill_value=0).reindex(columns=groups,fill_value=0)
    supported=counts.ge(10).all(axis=1)
    support=counts.reset_index().copy();support['supported']=supported.to_numpy()
    support['analysis']=analysis;support['activity']=mode;support['context']=context
    if supported.any():
        eligible=counts[supported].reset_index()[strata]
        kept=q.merge(eligible,on=strata,validate='many_to_one')
        w=kept.groupby(strata,observed=True).size().rename('target_n').reset_index();w['weight']=w.target_n/w.target_n.sum()
    else:kept=q.iloc[:0];w=pd.DataFrame(columns=[*strata,'target_n','weight'])
    rows=[]
    for g in groups:
        original=q[q[group].eq(g)];k=kept[kept[group].eq(g)]
        cells=k.groupby(strata,observed=True)[outcome].mean().rename('rate').reset_index().merge(w,on=strata)
        rows.append(dict(analysis=analysis,activity=mode,context=context,compared_group=g,
            original_N=len(original),retained_N=len(k),excluded_N=len(original)-len(k),
            support_fraction=ratio(len(k),len(original)),fraction=(cells.rate*cells.weight).sum() if len(cells) else np.nan,
            supported_strata=int(supported.sum()),status='supported_descriptive' if len(cells) else 'insufficient_common_support',
            strata='+'.join(strata),target_population='pooled category-specific assessable institutions in shared supported strata',
            weighting='equal institutions for pooled target; same direct-standardization weights across compared groups'))
    w['analysis']=analysis;w['activity']=mode;w['context']=context
    return pd.DataFrame(rows),support,w

def run():
    p=load('institution_pairs');x=p[p.analysis_id.eq('main_calendar')&p.window_months.eq(12)].copy();e=x[x.eligible].copy();r=e[e.repeat_flag.fillna(False)].copy()
    require((len(x),len(e),len(r))==(6328,4955,2137),'Unexpected main counts')
    save('entry_cohort',x);save('complete_cohort',e);save('repeat_cohort',r)
    save('Fig3a_entry_uses',entry_rates(x));save('Fig3b_repeat12',repeats(e));save('Fig3c_use_transitions',transitions(r))
    authors=[]
    for co,g,q in scopes(r):
        a=q[q.pair_author_available]
        for k in AUTH:
            n=int(a.author_group.eq(k).sum());authors.append(dict(cohort=co,size_group=g,author_group=k,n=n,N=len(a),fraction=ratio(n,len(a)),repeat_N=len(q),coverage=ratio(len(a),len(q))))
    save('Fig3d_author_groups',pd.DataFrame(authors))
    joint=[]
    for k in AUTH:
        a=r[r.pair_author_available&r.author_group.eq(k)]
        for m in MODES:joint.append(dict(author_group=k,activity=m,**transition(a,m)))
    save('Fig3e_author_use',pd.DataFrame(joint));save('ED7_conditionals',pd.DataFrame(joint))
    # ED6a shares the exact first-use table; ED6b retains NA use/event counts.
    save('ED6a_era_entry_uses',entry_rates(x).query('cohort != "All"'))
    yr=[]
    for co,g,q in scopes(e):
        for m in MODES:
            for state in ['0','1','Unknown']:
                a=q[q['entry_'+m].isna()] if state=='Unknown' else q[q['entry_'+m].eq(int(state))]
                N=len(a);C=int(a.repeat_flag.fillna(False).sum());U=int(a.repeat_flag.isna().sum())
                yr.append(dict(cohort=co,size_group=g,activity=m,entry_state=state,N=N,C=C,U=U,fraction=ratio(C,N),upper=ratio(C+U,N)))
    save('ED6b_entry_use_repeat',pd.DataFrame(yr))
    context=load('entry_partner_context');x=x.merge(context[['institution_id','partner_class','observed_complete']],on='institution_id',validate='one_to_one')
    rows=[]
    for co,g,q in scopes(x):
        for m in MODES:
            for state in ['All','1','0','Unknown']:
                a=q if state=='All' else q[q['entry_'+m].isna()] if state=='Unknown' else q[q['entry_'+m].eq(int(state))]
                for k in ['single_institution','confirmed_H_partner','complete_no_H_partner','partner_unknown']:
                    z=a[a.partner_class.eq(k)];n=len(z);rows.append(dict(cohort=co,size_group=g,activity=m,entry_state=state,partner_class=k,n=n,N=len(a),fraction=ratio(n,len(a)),work_N=z.entry_work_id.nunique(),max_single_work_institutions=int(z.entry_work_id.value_counts().max()) if len(z) else 0))
    save('ED6c_partner_context',pd.DataFrame(rows))
    std=[];support=[];weights=[]
    for m in MODES:
        q=x[x['entry_'+m].notna()&x.size_group.isin(['L','M','H'])].copy();q['outcome']=q['entry_'+m]
        a,b,c=standardize(q,'size_group','outcome',['entry_cohort'],['L','M','H'],'ED6a_era_std',m);std.append(a);support.append(b);weights.append(c)
        q=e[e['entry_'+m].notna()&e.size_group.isin(['L','M','H'])].copy();q['use_state']=q['entry_'+m].astype(int).astype(str)
        for g in ['All','L','M','H']:
            z=q if g=='All' else q[q.size_group.eq(g)]
            for bound in ['lower','upper']:
                z=z.copy();z['outcome']=z.repeat_flag.fillna(bound=='upper').astype(float)
                a,b,c=standardize(z,'use_state','outcome',['entry_cohort'],['0','1'],'ED6b_era_std_'+bound,m,g);std.append(a);support.append(b);weights.append(c)
        # Category-wise same-country comparison; not a replacement for institution weighting.
        q=x[x['entry_'+m].notna()&x.size_group.isin(['L','M','H'])].copy();q['outcome']=q['entry_'+m]
        a,b,c=standardize(q,'size_group','outcome',['country'],['L','M','H'],'S7_country_pooled',m);std.append(a);support.append(b);weights.append(c)
        if len(c):
            q=q.merge(c[['country']],on='country');means=q.groupby(['country','size_group'],observed=True).outcome.mean().unstack('size_group')
            for g in ['L','M','H']:
                std.append(pd.DataFrame([dict(analysis='S7_equal_country',activity=m,context='All',compared_group=g,original_N=int(x.size_group.eq(g).sum()),retained_N=int(q.size_group.eq(g).sum()),fraction=means[g].mean(),supported_strata=len(means),status='supported_descriptive',strata='country',weighting='equal common-support countries; different estimand')]))
        z=r[r.pair_author_available & r['pair_available_'+m]].copy()
        z['author_bin']=pd.cut(z.entry_authors,[0,1,4,np.inf],labels=['1','2-4','5+']).astype(str)
        z['gap_bin']=pd.cut(z.gap_days,[0,92,183,366],labels=['1-92d','93-183d','184-366d']).astype(str)
        for initial in [0,1]:
            q=z[z['entry_'+m].eq(initial)].copy();q['outcome']=q['followup_'+m]
            for strata in [['entry_cohort'],['author_bin'],['gap_bin'],['size_group'],['entry_cohort','author_bin','gap_bin','size_group']]:
                a,b,c=standardize(q,'author_group','outcome',strata,AUTH,'ED7c_'+str(initial)+'_'+'_'.join(strata),m,str(initial));std.append(a);support.append(b);weights.append(c)
    save('standardized_estimates',pd.concat(std,ignore_index=True));save('common_support_cells',pd.concat(support,ignore_index=True));save('standardization_weights',pd.concat(weights,ignore_index=True))
    # Fine stratum details and exact fractions remain available even if standardization fails.
    rows=[]
    for m in MODES:
        z=r[r.pair_author_available&r['pair_available_'+m]].copy()
        z['author_bin']=pd.cut(z.entry_authors,[0,1,4,np.inf],labels=['1','2-4','5+']).astype(str)
        z['gap_bin']=pd.cut(z.gap_days,[0,92,183,366],labels=['1-92d','93-183d','184-366d']).astype(str)
        for keys,q in z.groupby(['author_group','entry_cohort','size_group','author_bin','gap_bin'],observed=True):rows.append(dict(zip(['author_group','entry_cohort','size_group','author_bin','gap_bin'],keys),activity=m,**transition(q,m)))
    save('ED7c_stratified_counts',pd.DataFrame(rows))
    print('Main a–e, ED6/7 and category-specific common-support standardization completed',flush=True)
if __name__=='__main__':run()
