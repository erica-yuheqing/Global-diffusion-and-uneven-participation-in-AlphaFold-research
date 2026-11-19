"""Local-author overlap, conservative negative evidence and fixed-count checks."""
from math import comb
import numpy as np
import pandas as pd
from support import *

CATEGORIES=['Linked-only','Mixed','Unlinked-only','Unresolved']

def paper_state(initial_ids,later_ids,initial_complete,later_complete,strict_positive=False):
    if initial_ids & later_ids:
        return 'linked' if not strict_positive or (initial_complete and later_complete) else 'unresolved'
    if initial_ids and later_ids and initial_complete and later_complete:return 'unlinked'
    return 'unresolved'

def institution_state(states):
    require(len(states)>0,'No later paper is not an author-continuity sample')
    s=set(states)
    if 'linked' in s and 'unlinked' in s:return 'Mixed'
    if s=={'linked'}:return 'Linked-only'
    if s=={'unlinked'}:return 'Unlinked-only'
    return 'Unresolved'

def fixed_probabilities(states,k):
    n=len(states);l=states.count('linked');u=states.count('unlinked')
    require(n>=k,'Fixed-count sample exceeds observed follow-up papers')
    denom=comb(n,k)
    c=lambda a:comb(a,k) if a>=k else 0
    linked=c(l)/denom;unlinked=c(u)/denom
    mixed=1-c(n-l)/denom-c(n-u)/denom+c(n-l-u)/denom
    return np.array([linked,mixed,unlinked,max(0,1-linked-unlinked-mixed)])

def run(out):
    r=load(out,'af_initial_followup_relations');base=load(out,'institution_analysis_base')
    needed=pd.DataFrame({'work_id':r.event_source_work_id.unique()})
    with connect(out) as c:
        c.register('needed',needed)
        authors=c.execute(f'''SELECT DISTINCT a.work_id,a.author_id FROM read_parquet({lit(UP/'out_v2/authorships.parquet')}) a JOIN needed n USING(work_id)''').df()
        memberships=c.execute(f'''SELECT DISTINCT a.work_id,a.author_id,a.institution_id FROM read_parquet({lit(UP/'out_v2/author_institution_membership.parquet')}) a JOIN needed n USING(work_id)''').df()
    observed={w:set(x.author_id.dropna()) for w,x in authors.groupby('work_id')}
    missing=authors.groupby('work_id').author_id.apply(lambda s:s.isna().any()).to_dict()
    mapped={w:set(x.author_id.dropna()) for w,x in memberships.groupby('work_id')}
    local={(w,i):set(x.author_id.dropna()) for (w,i),x in memberships.groupby(['work_id','institution_id'])}
    work_complete={w:bool(observed.get(w)) and not missing.get(w,True) and observed[w]==mapped.get(w,set()) for w in needed.work_id}
    qa=[]
    for w in needed.work_id:qa.append(dict(source_work_id=w,observed_author_ids=len(observed.get(w,set())),
      mapped_author_ids=len(mapped.get(w,set())),any_missing_author_id=missing.get(w,True),observed_mapping_complete=work_complete[w]))
    save(out,'author_work_completeness',pd.DataFrame(qa))
    initial={};complete={}
    for inst,x in r[r.interval.eq(0)].groupby('institution_id'):
        sets=[local.get((w,inst),set()) for w in x.event_source_work_id]
        initial[inst]=set().union(*sets)
        complete[inst]=all(work_complete.get(w,False) and bool(local.get((w,inst))) for w in x.event_source_work_id)
    later=[]
    for row in r[r.interval.gt(0)].itertuples():
        inst=row.institution_id;ids=local.get((row.event_source_work_id,inst),set())
        ok=bool(work_complete.get(row.event_source_work_id,False) and ids)
        state=paper_state(initial.get(inst,set()),ids,complete.get(inst,False),ok)
        strict=paper_state(initial.get(inst,set()),ids,complete.get(inst,False),ok,True)
        later.append(dict(institution_id=inst,study_id=row.study_id,source_work_id=row.event_source_work_id,
          interval=row.interval,initial_local_author_ids=len(initial.get(inst,set())),later_local_author_ids=len(ids),
          overlapping_author_ids=len(initial.get(inst,set()) & ids),initial_observed_metadata_complete=complete.get(inst,False),
          later_observed_metadata_complete=ok,link_state=state,strict_complete_state=strict))
    papers=pd.DataFrame(later);save(out,'author_continuity_papers',papers)
    rows=[]
    for inst,x in papers.groupby('institution_id'):
        states=x.link_state.tolist()
        rows.append(dict(institution_id=inst,category=institution_state(states),strict_complete_category=institution_state(x.strict_complete_state.tolist()),
           later_studies=len(x),linked_studies=states.count('linked'),unlinked_studies=states.count('unlinked'),
           unresolved_studies=states.count('unresolved'),initial_observed_metadata_complete=complete[inst],
           assessable=institution_state(states)!='Unresolved'))
    inst=pd.DataFrame(rows).merge(base[['institution_id','quintile','baseline_papers']],on='institution_id',validate='one_to_one')
    require(len(inst)==int(base.repeat.sum()),'Repeat institution sample differs')
    save(out,'panel_d_author_continuity',inst)
    group=[]
    for variant,col in [('primary','category'),('require_complete_for_positive_overlap','strict_complete_category')]:
        for q in ['All',1,2,3,4,5]:
            x=inst if q=='All' else inst[inst.quintile.eq(q)]
            for cat in CATEGORIES:group.append(dict(variant=variant,quintile=str(q),category=cat,N=int(x[col].eq(cat).sum()),denominator=len(x),percentage=100*x[col].eq(cat).mean()))
    save(out,'panel_d_group_shares',pd.DataFrame(group))
    rng=np.random.default_rng(SEED);checks=[]
    byinst={i:x.link_state.tolist() for i,x in papers.groupby('institution_id')}
    for k in [2,3,5]:
        eligible=inst[inst.later_studies.ge(k)]
        exact={};sim={};denoms={}
        for row in eligible.itertuples():
            states=byinst[row.institution_id];n=len(states);values=np.array(states,dtype=object)
            indices=np.argpartition(rng.random((500,n)),k-1,axis=1)[:,:k]
            sample=values[indices];l=(sample=='linked').sum(axis=1);u=(sample=='unlinked').sum(axis=1)
            cat=np.full(500,3);cat[(l>0)&(u>0)]=1;cat[l==k]=0;cat[u==k]=2
            probs=fixed_probabilities(states,k)
            scopes=['eligible_at_each_k']+(['common_at_least5'] if n>=5 else [])
            for scope in scopes:
                for q in ['All',str(row.quintile)]:
                    key=(scope,q)
                    if key not in sim:sim[key]=np.zeros((500,4));exact[key]=np.zeros(4);denoms[key]=0
                    sim[key][np.arange(500),cat]+=1;exact[key]+=probs;denoms[key]+=1
        for key in sim:
            scope,q=key
            for j,category in enumerate(CATEGORIES):
                distribution=100*sim[key][:,j]/denoms[key]
                checks.append(dict(scope=scope,later_papers_sampled=k,quintile=q,category=category,N_eligible=denoms[key],
                   exact_expected_percentage=100*exact[key][j]/denoms[key],sample_mean_percentage=distribution.mean(),
                   sampling_p025=np.quantile(distribution,.025),sampling_p975=np.quantile(distribution,.975),
                   interval_type='fixed_count_sampling_spread_NOT_population_CI',draws=500,seed=SEED))
    save(out,'author_fixed_count_sensitivity',pd.DataFrame(checks))
    print(f'Author continuity: {len(inst)} repeat institutions; {int(inst.assessable.sum())} classified; remaining explicitly unresolved',flush=True)

if __name__=='__main__':run(OUT)
