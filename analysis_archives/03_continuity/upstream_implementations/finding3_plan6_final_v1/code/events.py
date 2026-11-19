"""Reconstruct the frozen event rules, with configurable windows/phase boundaries."""
from common import *

def history(events,baseline):
    e=events.copy();e.event_date=pd.to_datetime(e.event_date);p=e[e.confirmed_af]
    h=baseline[['institution_id','V_i']].rename(columns={'V_i':'baseline_papers'})
    h=h.merge(p.groupby('institution_id').agg(first_date=('event_date','min'),first_confirmed_evidence_year=('confirmed_evidence_year','min')),on='institution_id',how='left',validate='one_to_one')
    z=e.merge(h[['institution_id','first_date']],on='institution_id',how='left')
    yr=z.first_date.dt.year
    risk=(z.confirmed_af&z.event_date.isna()&z.confirmed_evidence_year.le(yr)) | (z.confirmed_af&z.within_study_first_date_unresolved&z.earliest_undated_confirmed_year.le(yr)) | (z.possible_af_only&(z.event_date.lt(z.first_date)|(z.event_date.isna()&z.earliest_version_evidence_year.le(yr))))
    r=risk.groupby(z.institution_id).sum();h['first_entry_uncertainty']=h.institution_id.map(r).fillna(0).astype(int)
    h['entry_resolved']=h.first_date.notna()&h.first_entry_uncertainty.eq(0)
    h['pre_main']=h.first_confirmed_evidence_year.lt(2020)
    return h

def pairs(events,h,months=12,shift=0):
    e=events.copy();e.event_date=pd.to_datetime(e.event_date);rows=[];relations=[]
    grouped={i:x for i,x in e.groupby('institution_id',sort=False)}
    for r in h.itertuples():
        first=r.first_date;end=first+pd.DateOffset(months=months) if pd.notna(first) else pd.NaT
        co=phase(pd.Series([first]),shift).iloc[0]
        ok=bool(r.entry_resolved and not r.pre_main and co in ['AF2','AF3']);eligible=bool(ok and end<=CUTOFF)
        if not ok:continue
        d=grouped.get(r.institution_id,e.iloc[:0]);positive=d[d.confirmed_af]
        initial=positive[positive.event_date.eq(first)].sort_values('study_id')
        later=positive[positive.event_date.gt(first)&positive.event_date.le(end)].sort_values(['event_date','study_id']) if eligible else positive.iloc[:0]
        unknown=d.iloc[:0]
        if eligible:
            year=d.earliest_version_evidence_year.astype('Int64').astype(str)
            lo=pd.to_datetime(year+'-01-01',errors='coerce');hi=pd.to_datetime(year+'-12-31',errors='coerce')
            unknown=d[(d.possible_af_only&((d.event_date.gt(first)&d.event_date.le(end))|(d.event_date.isna()&hi.gt(first)&lo.le(end)))) |
                (d.confirmed_af&d.event_date.isna()&hi.gt(first)&lo.le(end)) |
                (d.confirmed_af&d.within_study_first_date_unresolved&d.earliest_undated_confirmed_year.le(end.year)&d.earliest_undated_confirmed_year.ge(first.year))]
        repeat=True if len(later) else (pd.NA if len(unknown) or not eligible else False)
        follow=later.iloc[0] if len(later) else None;origin=initial.iloc[0]
        u=unknown[~unknown.study_id.eq(follow.study_id)] if follow is not None else unknown
        uncertain=bool(follow is not None and ((u.event_date.isna()|u.event_date.le(follow.event_date)).any() or follow.within_study_first_date_unresolved))
        rows.append(dict(institution_id=r.institution_id,entry_date=first,window_end=end,window_months=months,entry_cohort=co,entry_resolved=True,eligible=eligible,
            entry_study_id=origin.study_id,entry_work_id=origin.event_source_work_id,
            followup_study_id=follow.study_id if follow is not None else None,followup_work_id=follow.event_source_work_id if follow is not None else None,
            followup_date=follow.event_date if follow is not None else pd.NaT,repeat_flag=repeat,pair_order_uncertain=uncertain,
            n_initial_same_day=len(initial),n_first_followup_same_day=int(later.event_date.eq(follow.event_date).sum()) if follow is not None else 0,
            n_followup_af_papers=len(later) if eligible else None,n_uncertain_window_studies=len(unknown)))
        if eligible:
            selected=d[d.confirmed_af&(d.event_date.eq(first)|(d.event_date.gt(first)&d.event_date.le(end)))]
            for q in selected.itertuples():relations.append(dict(institution_id=r.institution_id,study_id=q.study_id,event_source_work_id=q.event_source_work_id,event_date=q.event_date,window_months=months))
    result=pd.DataFrame(rows);result.repeat_flag=result.repeat_flag.astype('boolean')
    return result,pd.DataFrame(relations)
