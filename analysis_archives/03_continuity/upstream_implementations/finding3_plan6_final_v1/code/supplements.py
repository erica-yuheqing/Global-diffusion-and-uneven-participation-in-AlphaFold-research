"""Execute the seven specified robustness groups; retain unsupported cells."""
from common import *
from analyze import entry_rates,repeats,transitions

def author_counts(q):
    x=q[q.pair_author_available]
    return [dict(author_group=g,n=int(x.author_group.eq(g).sum()),N=len(x),fraction=ratio(int(x.author_group.eq(g).sum()),len(x))) for g in AUTH]

def dependency(e,cohort):
    z=e.merge(cohort[['institution_id','entry_date','window_end']],on='institution_id',how='inner')
    years=z.earliest_version_evidence_year
    overlap=z.event_date.ge(z.entry_date)&z.event_date.le(z.window_end)
    undated=z.event_date.isna()&years.ge(z.entry_date.dt.year)&years.le(z.window_end.dt.year)
    z=z[(z.confirmed_af|z.possible_af_only)&(overlap|undated)]
    ids=cohort.institution_id.tolist();parent={i:i for i in ids}
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for _,q in z.groupby('study_id'):
        a=q.institution_id.unique()
        for b in a[1:]:parent[root(b)]=root(a[0])
    df=pd.DataFrame(dict(institution_id=ids,component=[root(i) for i in ids]))
    sizes=df.component.value_counts()
    return df,z,dict(N=len(ids),components=len(sizes),largest_component=int(sizes.max()),largest_fraction=sizes.max()/len(ids),effective_components=len(ids)**2/(sizes**2).sum(),CI_executed=False,bootstrap_draws_executed=0,reason='descriptive finite observed cohort; no validated shared-study inferential procedure; old engineering thresholds not treated as statistical theorem')

def run():
    p=load('institution_pairs');x=load('entry_cohort');e=load('complete_cohort');r=load('repeat_cohort');base=load('baseline_groups');acts=load('work_activity_evidence');meta=load('work_metadata');partners=load('entry_partner_context')
    flow=[];missing=[];comparison=[]
    for co,g,q in scopes(x):
        c=q[q.eligible];t=c[c.repeat_flag.fillna(False)]
        for stage,n in [('entry',len(q)),('complete12',len(c)),('confirmed_repeat',len(t)),('repeat_unknown',int(c.repeat_flag.isna().sum())),('author_available',int(t.pair_author_available.sum())),('four_uses_available',int(t.pair_use_available.sum()))]:flow.append(dict(cohort=co,size_group=g,stage=stage,n=n))
        for m in MODES:
            n=int(t['pair_available_'+m].sum());flow.append(dict(cohort=co,size_group=g,stage='paired_'+m,n=n))
            for branch,part,col in [('entry',q,'entry_'+m),('paired_entry',t,'entry_'+m),('paired_followup',t,'followup_'+m)]:
                missing.append(dict(cohort=co,size_group=g,branch=branch,activity=m,N=len(part),supported=int(part[col].eq(1).sum()),not_established=int(part[col].eq(0).sum()),unknown=int(part[col].isna().sum())))
    save('S1_flow',pd.DataFrame(flow));save('S1_state_missingness',pd.DataFrame(missing))
    for branch,flag in [('authors','pair_author_available'),*[(m,'pair_available_'+m) for m in MODES]]:
        for included in [False,True]:
            q=r[r[flag].eq(included)]
            for variable in ['entry_cohort','size_group','entry_work_type','entry_action_source']:
                for value,n in q[variable].fillna('Unknown').value_counts().items():comparison.append(dict(branch=branch,included=included,variable=variable,value=value,n=int(n),N=len(q),fraction=ratio(int(n),len(q))))
            for variable in ['V_i','entry_authors','gap_days']:comparison.append(dict(branch=branch,included=included,variable=variable,value='median',n=np.nan,N=len(q),fraction=q[variable].median()))
    save('S1_selection_comparison',pd.DataFrame(comparison))
    dictionary=[]
    for m,terms in TERMS.items():
        for term in terms:dictionary.append(dict(activity=m,atomic_action=term,one_rule='any supported, except quarantine',zero_rule='all constituent actions assessed not_established',NA_rule='uncertain/not_assessed/not_listed_legacy/quarantined',institution_attribution='activity of coauthored study; local execution not established'))
    save('S2_dictionary',pd.DataFrame(dictionary))
    source=x[['institution_id','size_group','entry_cohort','entry_work_id']].merge(acts,left_on='entry_work_id',right_on='work_id',how='left')
    evidence=source.groupby(['size_group','entry_cohort','activity','action_source','state'],dropna=False).size().rename('n').reset_index();save('S2_evidence_coverage',evidence)
    atom=load('atomic_evidence');atom=atom[atom.work_id.isin(x.entry_work_id)];save('S2_atomic_subtypes',atom.groupby(['action','source','state'],dropna=False).size().rename('n').reset_index())
    # No model/database-reference field exists in selected frozen metadata.
    if not (OUT/'provenance/reference_proxy_audit.json').exists():save('S2_proxy_field_audit',pd.DataFrame([dict(field='reference_work_ids / model_or_database_reference',available=False,status='not available in frozen selected-work schema; no proxy inference from title or action')]))
    single=x.merge(partners[['institution_id','partner_class']],on='institution_id');single=single[single.partner_class.eq('single_institution')]
    save('S2_single_institution_entry',entry_rates(single))
    wi=load('all_event_work_institutions').groupby('work_id').institution_id.nunique()
    good=load('work_quality').set_index('work_id').observed_partner_mapping_complete
    singleworks=set(wi[wi.eq(1)&good.reindex(wi.index).fillna(False)].index)
    sr=r[r.entry_work_id.isin(singleworks)&r.followup_work_id.isin(singleworks)];save('S2_single_institution_transitions',transitions(sr))
    # First-event co-occurrence uses category-specific common-assessable populations.
    co=[]
    for a in MODES:
        for b in MODES:
            q=x[x['entry_'+a].notna()&x['entry_'+b].notna()];n=int((q['entry_'+a].eq(1)&q['entry_'+b].eq(1)).sum())
            co.append(dict(activity_a=a,activity_b=b,n=n,N=len(q),fraction=ratio(n,len(q))))
    save('S3_cooccurrence',pd.DataFrame(co));q=x[x[['entry_'+m for m in MODES]].notna().all(axis=1)].copy()
    q['combination']=q.apply(lambda s:'+'.join(str(i+1) for i,m in enumerate(MODES) if s['entry_'+m]==1) or 'None established',axis=1)
    save('S3_complete_combinations',q.groupby('combination').size().rename('n').reset_index().assign(N=len(q)))
    windows=[]
    for months in [3,6,12]:
        q=p[p.analysis_id.eq('main_calendar')&p.window_months.eq(months)&p.institution_id.isin(e.institution_id)]
        require(len(q)==4955 and q.eligible.all(),'Window comparison mixes risk sets')
        t=repeats(q);t['months']=months;windows.append(t)
    save('S4_common_windows',pd.concat(windows,ignore_index=True))
    s6=p[p.analysis_id.eq('main_calendar')&p.window_months.eq(6)].set_index('institution_id').reindex(e.institution_id)
    s12=e.set_index('institution_id');s6=s6.reindex(s12.index)
    delayed=[]
    for g in GROUPS:
        z=s12 if g=='All' else s12[s12.size_group.eq(g)];z6=s6.reindex(z.index)
        delayed.append(dict(size_group=g,N=len(z),known_no6_confirmed12=int((z6.repeat_flag.eq(False).fillna(False)&z.repeat_flag.fillna(False)).sum()),unknown6_confirmed12=int((z6.repeat_flag.isna()&z.repeat_flag.fillna(False)).sum())))
    save('S4_delayed',pd.DataFrame(delayed));phase=[]
    for setting in ['phase_shift_-1','main_calendar','phase_shift_1']:
        z=p[p.analysis_id.eq(setting)&p.window_months.eq(12)];t=repeats(z[z.eligible]);t['setting']=setting;phase.append(t)
    save('S4_period_sensitivity',pd.concat(phase,ignore_index=True))
    # Pure-date sensitivity rebuilds qualification and both selected event works.
    specs=[('primary',r),('no_same_day_ties',r[r.n_initial_same_day.eq(1)&r.n_first_followup_same_day.eq(1)]),('four_categories_complete',r[r.pair_use_available]),
      ('both_explicit_overlay',r[r.entry_action_source.eq('accepted_action_overlay')&r.followup_action_source.eq('accepted_action_overlay')]),
      ('month_end',p[p.analysis_id.eq('month_end')&p.eligible&p.repeat_flag.fillna(False)])]
    sens=[];au=[]
    for name,q in specs:
        t=transitions(q);t['setting']=name;sens.append(t)
        for row in author_counts(q):au.append(dict(setting=name,**row))
    # Same-day initial union is a distinct initial-study-set estimand.
    ev=load('institution_events');act=acts.pivot(index='work_id',columns='activity',values='value')
    members=load('work_author_institutions');qual=load('work_quality').set_index('work_id').observed_mapping_complete.to_dict()
    aset={(w,i):set(q.author_id.dropna()) for (w,i),q in members.groupby(['work_id','institution_id']) if pd.notna(i)}
    initial=ev.merge(x[['institution_id','entry_date']],on='institution_id');initial=initial[initial.confirmed_af&initial.event_date.eq(initial.entry_date)]
    iw=initial.groupby('institution_id').event_source_work_id.apply(list).to_dict();union=r.copy()
    for idx,row in union.iterrows():
        ws=iw.get(row.institution_id,[])
        for m in MODES:
            values=act.reindex(ws)[m];value=1. if values.eq(1).any() else 0. if len(values) and values.eq(0).all() else np.nan
            # Quarantine cannot be promoted by a different initial work.
            if acts[acts.work_id.isin(ws)&acts.activity.eq(m)].state.eq('quarantined').any():value=np.nan
            union.loc[idx,'entry_'+m]=value
        reliable=bool(ws) and all(qual.get(w,False) and aset.get((w,row.institution_id)) for w in ws)
        s0=set().union(*(aset.get((w,row.institution_id),set()) for w in ws));s1=aset.get((row.followup_work_id,row.institution_id),set())
        ok=reliable and qual.get(row.followup_work_id,False) and bool(s1) and not row.pair_order_uncertain
        union.loc[idx,'pair_author_available']=bool(ok)
        union.loc[idx,'author_group']=('initial_only' if not s1-s0 else 'mixed') if ok and s0&s1 else 'no_initial_overlap' if ok else None
    t=transitions(union);t['setting']='co_initial_union_distinct_estimand';sens.append(t)
    for row in author_counts(union):au.append(dict(setting='co_initial_union_distinct_estimand',**row))
    save('S5_use_sensitivity',pd.concat(sens,ignore_index=True));save('S5_author_sensitivity',pd.DataFrame(au));save('S5_extreme_missing_bounds',load('Fig3a_entry_uses'))
    authorq=load('work_quality');save('S6_author_mapping_quality',authorq)
    comparisons=[]
    for k in AUTH:
        q=r[r.pair_author_available&r.author_group.eq(k)]
        comparisons.append(dict(author_group=k,N=len(q),median_initial_authors=q.entry_authors.median(),median_gap_days=q.gap_days.median(),AF3_fraction=q.entry_cohort.eq('AF3').mean(),H_fraction=q.size_group.eq('H').mean()))
    save('S6_author_opportunity',pd.DataFrame(comparisons))
    # Source-type restriction changes target population; never substitutes for overall primary.
    meta_ids=meta[meta.work_type.isin(['article','review'])].work_id
    restricted=r[r.entry_work_id.isin(meta_ids)&r.followup_work_id.isin(meta_ids)]
    save('S6_article_review_use',transitions(restricted));save('S6_article_review_authors',pd.DataFrame(author_counts(restricted)))
    components,relations,diag=dependency(ev,e);save('S7_dependency_components',components);save('S7_dependency_relations',relations);dump(OUT/'provenance/dependency12.json',diag)
    degree=relations.groupby('study_id').institution_id.nunique();save('S7_study_influence',degree.rename('institutions').reset_index().sort_values('institutions',ascending=False))
    big=set(degree[degree.ge(20)].index);large_ids=set(relations[relations.study_id.isin(big)].institution_id)
    repeated=r[~r.institution_id.isin(large_ids)];t=transitions(repeated);t['setting']='exclude_any_window_study_ge20_cohort_institutions';save('S7_large_collaboration_sensitivity',t)
    x['baseline_percentile']=x.institution_id.map(base.assign(pct=base.groupby('country').V_i.rank(pct=True,method='average')).set_index('institution_id').pct)
    x['scale_bin']=np.minimum(5,np.maximum(1,np.ceil(x.baseline_percentile*5)))
    continuous=[]
    for k,q in x.groupby('scale_bin'):
        a=entry_rates(q).query('cohort=="All" and size_group=="All"');a['scale_bin']=k;continuous.append(a)
    save('S7_continuous_scale',pd.concat(continuous,ignore_index=True));save('S7_continuous_institution_data',x[['institution_id','country','V_i','baseline_percentile','scale_bin',*['entry_'+m for m in MODES]]])
    cut=[]
    for threshold in [10,20,30]:
        z=x.copy();b=base.set_index('institution_id');z['size_group']=z.institution_id.map(b['group']).where(z.institution_id.map(b['eligible_'+str(threshold)]),'Unclassified')
        a=entry_rates(z);a['setting']='minimum_group_N'+str(threshold);cut.append(a)
    z=x.copy();b=base.copy();c=b.groupby('country').V_i.quantile([.25,.75]).unstack();b=b.merge(c.rename(columns={.25:'q25',.75:'q75'}),on='country',how='left')
    b['alt_group']=np.select([b.V_i.le(b.q25),b.V_i.le(b.q75)],['L','M'],default='H')
    n=b.groupby(['country','alt_group']).size().unstack(fill_value=0).reindex(columns=['L','M','H'],fill_value=0);countries=set(n[n.ge(20).all(axis=1)].index)
    b['alt_group']=b.alt_group.where(b.country.isin(countries),'Unclassified');z['size_group']=z.institution_id.map(b.set_index('institution_id').alt_group)
    a=entry_rates(z);a['setting']='domestic_25_75_cutpoints_all_groups_N20';cut.append(a)
    save('S7_cutpoint_eligibility',pd.concat(cut,ignore_index=True))
    # Separate estimand: each initial study receives total institutional weight one.
    z=r.copy();weighted=[];weight_records=[]
    for m in MODES:
        q=z[z['pair_available_'+m]].copy();q['weight']=1/q.groupby('entry_study_id').institution_id.transform('size');v=q['entry_'+m].ne(q['followup_'+m]).astype(float)
        record=q[['institution_id','entry_study_id','weight']].copy();record['activity']=m;record['change']=v;weight_records.append(record)
        weighted.append(dict(activity=m,N=len(q),change_rate=float(np.average(v,weights=q.weight)) if len(q) else np.nan,weighting='initial-study normalized institution weights; distinct estimand'))
    save('S7_repeat_initial_weighting',pd.DataFrame(weighted))
    save('S7_repeat_initial_weight_records',pd.concat(weight_records,ignore_index=True))
    print('S1–S7 robustness and twelve-month full-window dependence diagnostics completed',flush=True)
if __name__=='__main__':run()
