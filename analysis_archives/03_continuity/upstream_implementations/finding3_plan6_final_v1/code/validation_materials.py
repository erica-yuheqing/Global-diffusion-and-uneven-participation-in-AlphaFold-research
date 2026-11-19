"""Blind work-level sample design, provenance screen, and author/atomic record audit."""
from common import *

def run():
    x=load('entry_cohort');r=load('repeat_cohort');acts=load('work_activity_evidence');meta=load('work_metadata').set_index('work_id');atoms=load('atomic_evidence')
    historical=ROOT/'analysis/nhb_revision_v1/action_calibration_human_results_v2'
    hm=json.loads((historical/'results_manifest.json').read_text())
    files=[historical/'human_action_rows.jsonl',historical/'human_model_state_comparisons.jsonl',LAYER/'accepted_delta_refs185.jsonl']
    for path in files[:2]:require(sha(path)==hm['outputs'][path.name]['sha256'],'Historical human archive changed')
    lm=json.loads((LAYER/'layer_manifest.json').read_text());require(sha(files[2])==lm['outputs'][files[2].name]['sha256'],'Accepted delta archive changed')
    humans=pd.DataFrame([json.loads(v) for v in files[0].read_text().splitlines()]);comparisons=pd.DataFrame([json.loads(v) for v in files[1].read_text().splitlines()])
    explicit=[json.loads(v) for v in files[2].read_text().splitlines()]
    historical_ids=set(humans.work_id);accepted_ids={v['work_id'] for v in explicit if 'work_id' in v}
    existing_review=dict(historical_human_work_N=humans.work_id.nunique(),historical_action_rows=len(humans),
        self_reported_blind_rows=int(humans.review_mode.eq('blinded').sum()),main_original_comparison_rows=int(comparisons.main_blinded_calibration.sum()),
        policy_tuning_reused_cases=True,interpretation='Existing human calibration retained and audited; policy was subsequently tuned on these cases, so not a new independent validation of current labels',
        current_first_work_overlap=len(set(x.entry_work_id)&historical_ids),independence_not_inferred_from_self_report=True)
    dump(OUT/'provenance/existing_human_validation_inventory.json',existing_review)
    pins=json.loads((OUT/'provenance/input_pins.json').read_text());known={v['path'] for v in pins}
    for path in files+[historical/'results_manifest.json']:
        if str(path) not in known:pins.append(dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size))
    dump(OUT/'provenance/input_pins.json',pins)
    # Unique first-event works; prioritize any L association without duplicating a work.
    records=[]
    for wid,q in x.groupby('entry_work_id'):
        gs=set(q.size_group);g=next((v for v in ['L','M','H'] if v in gs),'Unclassified')
        a=acts[acts.work_id.eq(wid)];has_zero=a.value.eq(0).any();develop=a[a.activity.eq(MODES[2])].value.eq(1).any()
        raw=meta.loc[wid];co=q.entry_cohort.iloc[0]
        records.append(dict(work_id=wid,validation_group=g,entry_cohort=co,evidence_source=q.entry_action_source.iloc[0],work_type=raw.work_type,
            priority_label='assessed_zero_or_development' if has_zero or develop else 'other',title=raw.title,doi=raw.doi))
    frame=pd.DataFrame(records);total_first_works=len(frame)
    frame=frame[~frame.work_id.isin(historical_ids|accepted_ids)].copy();excluded_prior=total_first_works-len(frame)
    fields=['validation_group','entry_cohort','evidence_source','work_type','priority_label']
    frame['stratum']=frame[fields].astype(str).agg('|'.join,axis=1)
    rng=np.random.default_rng(20261026);strata={k:q.copy() for k,q in frame.groupby('stratum')};alloc={k:1 for k in strata}
    target=min(len(frame),max(240,len(strata)))
    # Stratified SRS without replacement; top-ups emphasize rare assessed-zero/development strata.
    while sum(alloc.values())<target:
        available=[k for k,q in strata.items() if alloc[k]<len(q)]
        scores=[(2 if 'assessed_zero_or_development' in k else 1)*len(strata[k])/(alloc[k]+1) for k in available]
        k=available[int(np.argmax(scores))];alloc[k]+=1
    samples=[];registry=[]
    for k,q in strata.items():
        n=alloc[k];N=len(q);part=q.iloc[rng.choice(len(q),n,replace=False)].copy();part['selection_probability']=n/N;part['validation_weight']=N/n;samples.append(part)
        registry.append(dict(stratum=k,population_N=N,sample_n=n,selection_probability=n/N,validation_weight=N/n))
    sample=pd.concat(samples,ignore_index=True).sort_values('work_id');sample['openalex_url']='https://openalex.org/'+sample.work_id
    cards=[]
    for row in sample.itertuples():
        for m in MODES:cards.append(dict(work_id=row.work_id,title=row.title,doi=row.doi,openalex_url=row.openalex_url,activity=m,human_state='',original_evidence_quote='',evidence_locator='',reviewer='',review_date='',prior_model_answer_seen='',adjudication=''))
    pd.DataFrame(cards).to_csv(OUT/'validation_materials/blind_human_template.csv',index=False)
    sample.to_csv(OUT/'validation_materials/sampling_registry.csv',index=False);pd.DataFrame(registry).to_csv(OUT/'validation_materials/stratum_probabilities.csv',index=False)
    answer=sample[['work_id','selection_probability','validation_weight']].merge(acts,on='work_id');answer.to_csv(OUT/'validation_materials/model_answers_OPEN_AFTER_REVIEW.csv',index=False)
    (OUT/'validation_materials/README_zh.md').write_text(f'''# 四用途独立验证材料（尚未标注）

主验证总体为本轮首篇事件的唯一work中，未用于既往100篇人工校准及185项命名修订的子总体，不是机构关系。总首篇work {total_first_works:,}项，排除既往相关{excluded_prior}项，剩{len(frame):,}项；按规模暴露组、进入期、证据来源、文献类型与稀少0/开发优先标志分层，抽取{len(sample)}项，每项四类，共{4*len(sample)}行。还权结果仅代表该抽样总体，不能自动外推到排除的旧校准/修订记录。
同一work涉及L时优先归L抽样层，否则M、H、未分类；该抽样归层不改变机构主分析分组。固定种子20261026，层内无放回随机抽样。分层、样本量和概率已在新人工判读前保存。
请先填写[盲评表](blind_human_template.csv)，阅读原始研究全文/方法并留下原文与定位；不要先打开[模型答案](model_answers_OPEN_AFTER_REVIEW.csv)。仅看模型选择的摘录不构成独立验证。三个状态填写supported、not_established、uncertain；缺乏证据不强迫判0。
抽样概率及还权见[登记](sampling_registry.csv)和[分层表](stratum_probabilities.csv)。准确性评估按work和用途进行，使用逆概率权重；0/1/NA及各组覆盖单列。需保留审阅者、看模型前后状态及分歧裁定。
现有100篇/900动作人工材料已盘点，记录见[既往材料审计](../provenance/existing_human_validation_inventory.json)。900行review_mode为填表者自报；既往95篇主比较855动作，但这些材料后来用于政策调校与接受修订，不能重新称为当前分类器的独立测试集。既往核心AF采用标签的独立人工核验也不等于这四类活动验证。此包未收到新独立人工标签，因此不报告准确率。
需要复核的是论文活动证据，并不能从共同署名推断哪个机构实际执行。缺少可访问原文的work保留无法判定，不静默替换样本。
''')
    # Development explanation: verify author sets and subtype links per paired institution.
    members=load('work_author_institutions');sets={(w,i):set(q.author_id.dropna()) for (w,i),q in members.groupby(['work_id','institution_id']) if pd.notna(i)}
    atomsets={(w,a):s for w,a,s in atoms[['work_id','action','state']].itertuples(index=False,name=None)}
    q=r[r.pair_author_available&r['pair_available_'+MODES[2]]];audit=[]
    for row in q.itertuples():
        a=sets.get((row.entry_work_id,row.institution_id),set());b=sets.get((row.followup_work_id,row.institution_id),set())
        actual=('initial_only' if not b-a else 'mixed') if a&b else 'no_initial_overlap'
        require(actual==row.author_group,'Author-set classification failed')
        rec=dict(institution_id=row.institution_id,entry_work_id=row.entry_work_id,followup_work_id=row.followup_work_id,author_group=actual,
            entry_value=getattr(row,'entry_'+MODES[2]),followup_value=getattr(row,'followup_'+MODES[2]),initial_authors=len(a),later_authors=len(b),overlap=len(a&b),other_authors=len(b-a),ID_set_check='PASS',semantic_independent_human_review='not completed')
        for prefix,w in [('entry',row.entry_work_id),('followup',row.followup_work_id)]:
            for action in TERMS[MODES[2]]:rec[prefix+'_'+action]=atomsets.get((w,action),'not_assessed')
            rec[prefix+'_title']=meta.loc[w,'title']
        audit.append(rec)
    save('ED7_development_record_audit',pd.DataFrame(audit))
    examples=[];first_ids=set(x.entry_work_id);layer={v['work_id']:v for v in map(json.loads,(LAYER/'action_layer3755.jsonl').read_text().splitlines())}
    for mode in MODES:
        for state in ['supported','not_established']:
            candidates=acts[acts.work_id.isin(first_ids)&acts.activity.eq(mode)&acts.state.eq(state)].work_id
            for wid in candidates:
                if wid not in layer:continue
                decisions=[v for v in layer[wid]['action_decisions'] if v['action'] in TERMS[mode]]
                contexts=[v for decision in decisions for v in decision.get('evidence_context',[])][:2]
                if not contexts and not any(v.get('note') for v in decisions):continue
                excerpts=[' '.join(str(v.get('quote','')).split()[:20]) for v in contexts]
                examples.append(dict(work_id=wid,activity=mode,state=state,title=meta.loc[wid,'title'],
                    archived_context_excerpt=' | '.join(excerpts),locator=' | '.join(str(v.get('source_kind'))+':'+str(v.get('block_index')) for v in contexts),
                    archived_decision_note=' | '.join(v.get('note','') for v in decisions),
                    provenance='accepted model-assisted action layer; illustrative record, not independent gold',
                    negative_meaning='not_established is not proof of actual non-use'))
                break
    save('S2_actual_evidence_examples',pd.DataFrame(examples))
    dump(OUT/'provenance/independent_validation_status.json',dict(status='designed_not_independently_annotated',sample_work_N=len(sample),action_rows=4*len(sample),accuracy_estimated=False,core_label_validation_not_activity_validation=True,author_development_record_ID_checks=len(audit)))
    print(f'Validation design: {len(sample)} unique works / {4*len(sample)} blank human rows; development ID checks {len(audit)}',flush=True)
if __name__=='__main__':run()
