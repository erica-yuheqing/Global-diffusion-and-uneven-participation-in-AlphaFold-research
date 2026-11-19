"""Archive explicit user acceptance in a new layer; never modify proposals or the original final database."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import fetch_public_evidence as e
from local_recall import MODULE,require,sha,write_json,write_csv,destination


def accept(record,message):
    require(record.get('approval_status')=='pending_user_acceptance','Expected pending proposals')
    require(bool(message.strip()),'Explicit user acceptance message required')
    result=json.loads(json.dumps(record))
    result.update(approval_status='accepted_by_user',approval_user_message=message,
        approval_recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        acceptance_scope='765 candidate routes and the 12 specifically proposed version groups; not a new independent human gold standard')
    require(len(result['decisions'])==765,'Candidate coverage differs')
    require(len(result['accepted_version_links'])==12,'Specific accepted version scope differs')
    for row in result['decisions']:
        row['review_status']='accepted_by_user_as_assisted_decision_or_unknown_route'
        row['original_proposal_status']=row['decision_status']
        row['decision_status']='user_accepted_retained_unknown' if row['af_use_label']=='uncertain' else 'user_accepted_assisted_decision'
        row['independent_human_gold']=False
    for link in result['accepted_version_links']:link['approval_status']='accepted_by_user'
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package-dir',type=Path,default=MODULE/'semantic_acceptance_package_v2')
    p.add_argument('--output-dir',type=Path,default=MODULE/'accepted_candidate_layer_v1')
    p.add_argument('--user-message',required=True)
    a=p.parse_args(argv);out=destination(a.output_dir)
    manifest=json.loads((a.package_dir/'run_manifest.json').read_text())
    require(e.inventory(a.package_dir)==manifest['outputs'],'Proposal package changed')
    for item in manifest['inputs']:require(sha(item['path'])==item['sha256'],'Proposal source changed')
    proposal=a.package_dir/'proposed_layer_private.json'
    layer=accept(json.loads(proposal.read_text()),a.user_message)
    layer['source_review_pins'] += [{'path':str(proposal.resolve()),'sha256':sha(proposal)},
        {'path':str((a.package_dir/'run_manifest.json').resolve()),'sha256':sha(a.package_dir/'run_manifest.json')}]
    stage=Path(tempfile.mkdtemp(prefix='.accepted-candidates-',dir=MODULE));stage.chmod(0o700)
    write_json(stage/'accepted_layer_private.json',layer)
    counts=Counter('yes_yes' if r['af_use_label']=='yes' and r['adoption_eligible']=='yes'
        else 'original_platform_not_downstream' if r['af_use_label']=='yes' else r['af_use_label'] for r in layer['decisions'])
    write_json(stage/'acceptance_record.json',{'user_message':a.user_message,
        'recorded_at_utc':layer['approval_recorded_at_utc'],'candidate_counts':dict(counts),
        'accepted_version_groups':12,'source_proposal_sha256':sha(proposal),
        'independent_human_gold':False,'original_final_changed':False,'api_calls':0})
    fields=['review_id','work_id','publication_year','af_use_label','adoption_eligible','relevance_level',
        'evidence_level','source_review','decision_status']
    write_csv(stage/'accepted_routes.csv',[{k:r[k] for k in fields} for r in layer['decisions']],fields)
    (stage/'README_zh.md').write_text('''# Figure1 独立接受层

用户接受信息与范围见[接受记录](acceptance_record.json)。此层接受765篇候选分流及12组特定版本归并建议；仍保留586篇未知，不把它们当作未使用。辅助评审不冒充独立人工金标准。

- [接受层与逐篇来源](accepted_layer_private.json)
- [候选分流表](accepted_routes.csv)

原最终库、候选建议、历史评审及旧图形不修改。年度/时期使用一个明确代表；首次国家参与只保留成员自己的独立已确认证据和日期，不回填预印本。
''',encoding='utf-8')
    write_json(stage/'run_manifest.json',{'schema':'figure1-specific-user-acceptance-v1',
        'inputs':layer['source_review_pins'],'outputs':e.inventory(stage),'approval_status':'accepted_by_user'})
    stage.rename(out);print('Accepted derived-only layer:',out,'; candidates:',dict(counts),'; version groups: 12')


if __name__=='__main__':main()
