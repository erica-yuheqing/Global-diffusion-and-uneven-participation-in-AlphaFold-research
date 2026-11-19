"""Frozen input verification, event reconstruction, complete observed partner mapping."""
import shutil
from common import *
from events import history,pairs

def tri_metadata(works):
    overlay={r['work_id']:r for r in map(json.loads,(LAYER/'action_layer3755.jsonl').read_text().splitlines())}
    new={r['work_id'] for r in json.loads(ACCEPT.read_text())['decisions']}
    atoms=[];rows=[]
    for r in works.itertuples():
        if r.work_id in new:states={a:'not_assessed' for terms in TERMS.values() for a in terms};source='new_candidate_core_only_acceptance'
        elif r.work_id in overlay:
            o=overlay[r.work_id];source='accepted_action_overlay'
            states={v['action']:('quarantined' if o['input_attribution_quarantined'] else v['state']) for v in o['action_decisions']}
            if o['assessment_status']=='not_assessed_no_parsed_response':states={a:'not_assessed' for terms in TERMS.values() for a in terms}
        elif r.observed_actions_status in ['ab_exact_consensus','adjudicated']:
            present=set(str(r.final_observed_actions).split('|')) if pd.notna(r.final_observed_actions) else set()
            states={a:'supported' if a in present else 'not_listed_legacy' for terms in TERMS.values() for a in terms};source='legacy_'+r.observed_actions_status
        else:states={a:'not_assessed' for terms in TERMS.values() for a in terms};source='unassessed_event_version'
        for mode,terms in TERMS.items():
            state=combine([states.get(a,'not_assessed') for a in terms])
            rows.append(dict(work_id=r.work_id,activity=mode,state=state,value={'supported':1.,'not_established':0.}.get(state,np.nan),action_source=source))
        for a,state in states.items():atoms.append(dict(work_id=r.work_id,action=a,state=state,source=source))
    return pd.DataFrame(rows),pd.DataFrame(atoms)

def enrich(p,base,works,activities,authors,members,quality):
    p=p.merge(base[['institution_id','V_i','group','eligible_20','country','size_group','cut_LM','cut_MH']],on='institution_id',how='left',validate='many_to_one')
    sets={(w,i):set(q.author_id.dropna()) for (w,i),q in members.groupby(['work_id','institution_id']) if pd.notna(i)}
    complete=quality.set_index('work_id').observed_mapping_complete.to_dict()
    raw=works.set_index('work_id');act=activities.pivot(index='work_id',columns='activity',values='value')
    src=activities.groupby('work_id').action_source.first().to_dict();rows=[]
    for r in p.itertuples():
        a,b=r.entry_work_id,r.followup_work_id;s0=sets.get((a,r.institution_id),set());s1=sets.get((b,r.institution_id),set())
        reliable=bool(b is not None and complete.get(a,False) and complete.get(b,False) and s0 and s1 and not r.pair_order_uncertain)
        row=dict(institution_id=r.institution_id,entry_authors=len(s0),followup_authors=len(s1),overlap_authors=len(s0&s1),additional_authors=len(s1-s0),pair_author_available=reliable,
            author_group=('initial_only' if not s1-s0 else 'mixed') if reliable and s0&s1 else 'no_initial_overlap' if reliable else None,
            author_missing_reason='available' if reliable else 'no_followup' if b is None else 'pair_order_uncertain' if r.pair_order_uncertain else 'incomplete_author_identity_or_local_affiliation')
        for prefix,w in [('entry',a),('followup',b)]:
            for mode in MODES:row[prefix+'_'+mode]=act.loc[w,mode] if w in act.index else np.nan
            for key in ['work_type','publication_year','primary_subfield_id','primary_subfield_display_name']:
                row[prefix+'_'+key]=raw.loc[w,key] if w in raw.index else None
            row[prefix+'_action_source']=src.get(w)
        for mode in MODES:row['pair_available_'+mode]=bool(b is not None and not r.pair_order_uncertain and pd.notna(row['entry_'+mode]) and pd.notna(row['followup_'+mode]))
        row['pair_use_available']=all(row['pair_available_'+m] for m in MODES)
        row['gap_days']=(pd.Timestamp(r.followup_date)-pd.Timestamp(r.entry_date)).days if pd.notna(r.followup_date) else np.nan
        rows.append(row)
    return p.merge(pd.DataFrame(rows),on='institution_id',validate='one_to_one')

def run():
    require(not OUT.exists() or ('--resume-unpublished' in sys.argv and not (OUT/'run_manifest.json').exists() and not (OUT/'provenance/preparation.json').exists()),'New release directory already exists; refusing overwrite')
    pins=pin_inputs()
    for sub in ['tables','figures','source_data','provenance','code','instructions','validation_materials']:(OUT/sub).mkdir(parents=True,exist_ok=True)
    dump(OUT/'analysis_config.json',configuration());dump(OUT/'provenance/input_pins.json',pins)
    for p in PLAN.glob('*.md'):shutil.copy2(p,OUT/'instructions'/p.name)
    base=pd.read_parquet(F2/'tables/baseline_groups.parquet');base['size_group']=base['group'].where(base.eligible_20.fillna(False),'Unclassified')
    save('baseline_groups',base)
    e=pd.read_parquet(OLD/'tables/original_institution_events.parquet');e.event_date=pd.to_datetime(e.event_date)
    h=history(e,base);save('event_history',h);save('institution_events',e)
    ids=pd.DataFrame(dict(work_id=e.event_source_work_id.unique()))
    with con() as c:
        c.register('needed',ids)
        works=c.execute('SELECT w.* FROM read_parquet(?) w JOIN needed n USING(work_id)',[str(UP/'works_eligible.parquet')]).df()
        authors=c.execute('SELECT DISTINCT a.work_id,a.author_id,a.author_position,a.is_corresponding FROM read_parquet(?) a JOIN needed n USING(work_id)',[str(UP/'authorships.parquet')]).df()
        members=c.execute('SELECT DISTINCT a.work_id,a.author_id,a.institution_id FROM read_parquet(?) a JOIN needed n USING(work_id)',[str(UP/'author_institution_membership.parquet')]).df()
    require(works.work_id.is_unique and set(works.work_id)==set(ids.work_id),'Event work metadata incomplete')
    quality=[];raw_sets={w:set(x.author_id.dropna()) for w,x in authors.groupby('work_id')}
    mapped_sets={w:set(x.author_id.dropna()) for w,x in members.groupby('work_id')}
    missing=authors.groupby('work_id').author_id.apply(lambda s:s.isna().any()|s.fillna('').eq('').any()).to_dict()
    nullinst=members.groupby('work_id').institution_id.apply(lambda s:s.isna().any()|s.fillna('').eq('').any()).to_dict()
    for w in works.work_id:
        # Main author rule exactly preserves the approved legacy observed mapping test.
        author_ok=bool(raw_sets.get(w)) and not missing.get(w,True) and raw_sets.get(w)==mapped_sets.get(w,set())
        partner_ok=author_ok and not nullinst.get(w,True)
        quality.append(dict(work_id=w,observed_authors=len(raw_sets.get(w,set())),mapped_authors=len(mapped_sets.get(w,set())),missing_author_id=missing.get(w,True),observed_mapping_complete=author_ok,observed_partner_mapping_complete=partner_ok))
    quality=pd.DataFrame(quality);activities,atoms=tri_metadata(works)
    for n,q in [('work_metadata',works),('work_authors',authors),('work_author_institutions',members),('work_quality',quality),('work_activity_evidence',activities),('atomic_evidence',atoms)]:save(n,q,csv=False)
    allpairs=[];rels=[];frozen=pd.read_parquet(OLD/'tables/institution_pairs.parquet')
    for months in [3,6,12]:
        p,r=pairs(e,h,months);p=enrich(p,base,works,activities,authors,members,quality);p['analysis_id']='main_calendar'
        old=frozen[frozen.analysis_id.eq('main_calendar')&frozen.window_months.eq(months)].set_index('institution_id').sort_index();new=p.set_index('institution_id').sort_index()
        require(new.index.equals(old.index),'Entry membership changed')
        for col in ['eligible','entry_work_id','followup_work_id','entry_cohort','repeat_flag','pair_order_uncertain','pair_author_available','author_group',*[f'{prefix}_{m}' for prefix in ['entry','followup'] for m in MODES]]:
            left=new[col].astype(object).where(new[col].notna(),'__NA__').astype(str)
            right=old[col].astype(object).where(old[col].notna(),'__NA__').astype(str)
            require(left.eq(right).all(),'Reconstruction differs '+str(months)+' '+col)
        allpairs.append(p);rels.append(r);print(f'Rebuilt {months}m: entries {len(p)}, complete {int(p.eligible.sum())}, repeats {int(p.loc[p.eligible].repeat_flag.fillna(False).sum())}',flush=True)
    for shift in [-1,1]:
        p,_=pairs(e,h,12,shift);p=enrich(p,base,works,activities,authors,members,quality);p['analysis_id']='phase_shift_'+str(shift);allpairs.append(p)
    em=e.copy();em.event_date=em.event_date.dt.to_period('M').dt.to_timestamp('M');hm=history(em,base)
    p,_=pairs(em,hm,12);p=enrich(p,base,works,activities,authors,members,quality);p['analysis_id']='month_end';allpairs.append(p)
    save('institution_pairs',pd.concat(allpairs,ignore_index=True));save('followup_relations',pd.concat(rels,ignore_index=True))
    # Complete observed institution lists use ALL linked institutions, not only eligible countries/entrants.
    inst=members[['work_id','institution_id']].drop_duplicates();inst=inst[inst.institution_id.notna()&inst.institution_id.ne('')]
    inst=inst.merge(base[['institution_id','size_group']],on='institution_id',how='left',validate='many_to_one');inst.size_group=inst.size_group.fillna('Unclassified')
    save('all_event_work_institutions',inst)
    quality_map=quality.set_index('work_id').observed_partner_mapping_complete.to_dict()
    mapped={w:q.set_index('institution_id').size_group.to_dict() for w,q in inst.groupby('work_id')}
    primary=allpairs[2];partner=[]
    for r in primary.itertuples():
        known=mapped.get(r.entry_work_id,{});others={i:g for i,g in known.items() if i!=r.institution_id}
        complete=quality_map.get(r.entry_work_id,False) and r.institution_id in known
        if any(g=='H' for g in others.values()):kind='confirmed_H_partner'
        elif complete and not others:kind='single_institution'
        elif complete and others and all(g in ['L','M','H'] for g in others.values()):kind='complete_no_H_partner'
        else:kind='partner_unknown'
        partner.append(dict(institution_id=r.institution_id,work_id=r.entry_work_id,partner_class=kind,observed_institutions=len(known),observed_partners=len(others),known_H_partners=sum(g=='H' for g in others.values()),observed_complete=bool(complete)))
    save('entry_partner_context',pd.DataFrame(partner))
    for n in ['ED5_annual_cohort_output','ED5_growth_contributions','ED5_institution_studies']:save(n,pd.read_parquet(OLD/'tables'/f'{n}.parquet'))
    dump(OUT/'provenance/preparation.json',dict(status='PASS',entry=6328,complete12=4955,repeat12=2137,author12=1312,baseline_groups=len(base),event_works=len(works),API_calls=0,independent_human_validation=False,observed_partner_completeness='observed authors and institution links; upstream truncation/ID correctness cannot be certified'))
if __name__=='__main__':run()
