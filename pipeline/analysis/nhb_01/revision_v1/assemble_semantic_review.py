"""Validate literal evidence and consolidate auxiliary proposals, never approve them."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tempfile
from local_recall import MODULE,require,sha,write_json,write_csv
import fetch_public_evidence as e


def packet_index():
    base=json.loads((MODULE/'candidate_review_v1/review_packets_private.json').read_text())
    result={x['work_id']:x for x in base}
    # Stable copied bodies, restored unsectioned paragraphs and citation contexts.
    for file in sorted(MODULE.glob('body_assignments_round*_v1/part*_private.json')):
        for row in json.loads(file.read_text()):result[row['work_id']]=row
    return result


def validate_row(row,packet):
    require(row['work_id']==packet['work_id'] and row['review_id']==packet['review_id'],'Review identity differs')
    require(row.get('review_status')=='pending_user_acceptance','Suggestion unexpectedly approved')
    require(row['af_use_label'] in ['yes','no','uncertain'] and row['adoption_eligible'] in ['yes','no','uncertain'],'Invalid state')
    doc=None
    for item in row['evidence']:
        quote=item['quote'];require(quote and len(quote.split())<=25,'Evidence quote word bound differs')
        source=item['source_kind']
        if source in ['local_abstract','public_abstract']:
            text=next(x['text'] for x in packet['abstract_variants'] if x['source_kind']==source)
        else:
            if doc is None:
                path=Path(packet['body_document_path']);require(sha(path)==packet['body_document_sha256'],'Body hash changed')
                doc=json.loads(path.read_text())
            if source=='fulltext_body_section':
                index=item['section_index'];require(type(index)==int and 0<=index<len(doc['sections']),'Bad section')
                text=doc['sections'][index]['text']
                require(not re.search(r'^references?$|^bibliography$',doc['sections'][index]['title'],re.I) or row['af_use_label']!='yes',
                    'Reference section cannot establish use')
            elif source=='raw_body_af1_citation_paragraph':
                text=doc['af1_citation_contexts'][item['context_index']]['text']
            else:raise ValueError('Unexpected evidence source: '+source)
        require(quote in text,'Quote not a literal source substring: '+row['work_id'])
    require(row['af_use_label']!='yes' or bool(row['evidence']),'No source for use=yes')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--specific-amendment',type=Path,action='append',default=[],
        help='Additional explicit evidence-based proposals, applied after historical sources; approval still pending')
    a=p.parse_args(argv);require(not a.output_dir.exists(),'Output exists')
    packets=packet_index()
    files=[MODULE/'assisted_review_abstracts_v1.json',MODULE/'assisted_review_bodies_v1.json']
    files+=sorted(MODULE.glob('assisted_review_round*_part*_v1.json'))
    files+=a.specific_amendment
    files=[f for f in files if f.is_file()]
    suggestions={};history=[];comparisons=[];used_bodies=set()
    for f in files:
        seen=set()
        for row in json.loads(f.read_text()):
            wid=row['work_id'];require(wid not in seen,'Duplicate review in file');seen.add(wid)
            # First30 retain original extraction indices/hash; restored snapshots
            # preserve section order, but their hashes differ and are independent.
            packet=packets[wid]
            if f.name=='assisted_review_bodies_v1.json':
                packet=next(x for x in json.loads((MODULE/'candidate_review_v1/review_packets_private.json').read_text()) if x['work_id']==wid)
            validate_row(row,packet)
            if any(x['source_kind'] not in ['local_abstract','public_abstract'] for x in row['evidence']):
                used_bodies.add(Path(packet['body_document_path']))
            prior=suggestions.get(wid)
            if prior:
                comparisons.append({'work_id':wid,'earlier':prior['source_review'],'later':f.name,
                    'use_earlier':prior['af_use_label'],'use_later':row['af_use_label'],
                    'changed':prior['af_use_label']!=row['af_use_label'] or prior['adoption_eligible']!=row['adoption_eligible']})
            rec=dict(row);rec['source_review']=f.name
            history.append(rec);suggestions[wid]=rec
    rows=[]
    for wid,packet in sorted(packets.items(),key=lambda x:x[1]['review_id']):
        rec=suggestions.get(wid)
        if rec is None:
            rec={'work_id':wid,'review_id':packet['review_id'],'primary_label':'uncertain',
                'relevance_level':'RU','evidence_level':'E0' if not(packet['body_document_path'] or any(x['text'] for x in packet['abstract_variants'])) else 'E1',
                'af_related_label':'uncertain','af_use_label':'uncertain','adoption_eligible':'uncertain','evidence':[],
                'reasoning_zh':'尚未有足够的正面使用证据；未审阅或证据缺口保留unknown，不等于已评审为未使用。',
                'source_review':'explicit_pending_or_insufficient_evidence_route','review_status':'pending_user_acceptance',
                'decision_status':'not_semantically_resolved_retained_unknown','needs_human_review':True}
        else:rec['decision_status']='auxiliary_proposal_pending_acceptance'
        rec['publication_year']=packet['publication_year'];rec['title']=packet['title']
        rows.append(rec)
    counts=Counter('confirmed_AF_proposed' if r['af_use_label']=='yes' and r['adoption_eligible']=='yes'
        else 'original_platform_not_downstream' if r['af_use_label']=='yes' else r['af_use_label'] for r in rows)
    summary={'candidate_coverage':len(rows),'individually_reviewed_unique':len(suggestions),'review_source_files':len(files),
        'proposal_counts':dict(counts),'by_year':{str(y):dict(Counter('yes_yes' if r['af_use_label']=='yes' and r['adoption_eligible']=='yes'
            else r['af_use_label'] for r in rows if r['publication_year']==y)) for y in range(2019,2026)},
        'approval_status':'pending_user_acceptance','independent_human_gold':False,'old_changes':0,'api_calls':0}
    stage=Path(tempfile.mkdtemp(prefix='.semantic-proposals-',dir=MODULE))
    write_json(stage/'candidate_proposals_private.json',rows)
    write_json(stage/'review_history_private.json',history)
    write_json(stage/'abstract_body_comparisons.json',comparisons)
    write_json(stage/'summary.json',summary)
    write_csv(stage/'candidate_decision_summary_private.csv',[
        {k:r.get(k,'') for k in ['review_id','work_id','publication_year','title','af_use_label','adoption_eligible','relevance_level','evidence_level','source_review','decision_status','reasoning_zh']} for r in rows],
        ['review_id','work_id','publication_year','title','af_use_label','adoption_eligible','relevance_level','evidence_level','source_review','decision_status','reasoning_zh'])
    packet_sources=[MODULE/'candidate_review_v1/review_packets_private.json']+sorted(MODULE.glob('body_assignments_round*_v1/part*_private.json'))
    source_files=list(dict.fromkeys(files+packet_sources+sorted(used_bodies)))
    write_json(stage/'run_manifest.json',{'schema':'figure1-combined-semantic-proposals-v1',
        'inputs':[{'path':str(f.resolve()),'sha256':sha(f)} for f in source_files], 'summary':summary,'outputs':e.inventory(stage)})
    stage.rename(a.output_dir);print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':raise SystemExit(main())
