"""Freeze the user's specific closure acceptance, without changing historical layers."""
import copy
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from prepare_closure_confirmation_v1 import OUT as CONFIRMATION, PRIOR, verify as verify_proposal
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, pin, require, sha, write_csv, write_json

OUT = MODULE / 'accepted_candidate_layer_v2'
USER_MESSAGE = '采用建议, 继续实施'


def accepted(proposal, prior, message):
    require(message == USER_MESSAGE, 'This release records the actual specific user message')
    require(proposal['approval_status'] == 'pending_one_user_confirmation', 'Unexpected proposal state')
    old = {r['work_id']: r for r in prior['decisions']}
    revised = {r['work_id']: r for r in proposal['decisions']}
    require(len(old) == 765 and len(revised) == 586, 'Frozen queue coverage differs')
    require(all(old[w]['af_use_label'] == 'uncertain' for w in revised), 'Cannot replace old accepted nonunknowns')
    layer = copy.deepcopy(prior)
    layer.update(schema='figure1-specific-closure-acceptance-v2', approval_status='accepted_by_user',
        approval_user_message=message, approval_recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        acceptance_scope='586 remaining routes and three specific same-study links; prior 179 decisions and 12 links preserved',
        independent_human_gold=False, core_database_changed=False,
        reviewed_source_scope=proposal['summary']['methods_limitation'],
        unknown_policy=proposal['unknown_policy'], version_policy=proposal['version_policy'],
        temporal_guards=copy.deepcopy(proposal['temporal_guards']))
    decisions = []
    for row in proposal['proposed_all765_decisions']:
        row = copy.deepcopy(row)
        if row['work_id'] in revised:
            row.update(source_review=str((CONFIRMATION / 'proposal_private.json').resolve()),
                original_proposal_status=row['decision_status'],
                decision_status='user_accepted_retained_unknown' if row['af_use_label'] == 'uncertain' else 'user_accepted_assisted_decision',
                review_status='accepted_by_user_as_assisted_decision_or_unknown_route', independent_human_gold=False)
        else:
            require(row == old[row['work_id']], 'Protected earlier decision changed')
        decisions.append(row)
    require(len(decisions) == 765 and len({r['work_id'] for r in decisions}) == 765, 'Duplicate or missing work')
    require(dict(Counter(r['af_use_label']+'/'+r['adoption_eligible'] for r in decisions)) ==
            {'yes/yes': 74, 'no/no': 159, 'yes/no': 1, 'uncertain/uncertain': 531}, 'Accepted counts differ')
    links = copy.deepcopy(proposal['preserved_old_version_links'])
    require(links == prior['accepted_version_links'], 'Protected links changed')
    for link in proposal['proposed_version_links']:
        link = copy.deepcopy(link)
        require(not link['labels_propagated'] and not link['early_preprint_use_backfilled'], 'Version label propagation forbidden')
        link['approval_status'] = 'accepted_by_user'
        links.append(link)
    require(len(links) == 15, 'Version group scope differs')
    members = [w for g in links for w in g['member_work_ids']]
    require(len(members) == len(set(members)), 'Overlapping version groups')
    layer['decisions'] = decisions
    layer['accepted_version_links'] = links
    layer['source_review_pins'] += [pin(PRIOR), pin(CONFIRMATION / 'run_manifest.json'),
        pin(CONFIRMATION / 'proposal_private.json'), pin(Path(__file__))]
    return layer


def verify(directory=OUT):
    manifest = json.loads((directory/'run_manifest.json').read_text())
    require(inventory(directory) == manifest['outputs'], 'Acceptance inventory differs')
    for item in manifest['inputs']:
        require(sha(Path(item['path'])) == item['sha256'], 'Acceptance source differs')
    verify_proposal(CONFIRMATION)
    layer = json.loads((directory/'accepted_layer_private.json').read_text())
    prior = json.loads(PRIOR.read_text()); proposal = json.loads((CONFIRMATION/'proposal_private.json').read_text())
    rebuilt = accepted(proposal, prior, USER_MESSAGE)
    rebuilt['approval_recorded_at_utc'] = layer['approval_recorded_at_utc']
    require(rebuilt == layer, 'Accepted layer reconstruction differs')
    print('Specific closure acceptance: PASS; 765 routes; 74 adopted / 159 nonuse / 1 platform / 531 unknown; 15 version groups')
    return layer


def main():
    import argparse
    p = argparse.ArgumentParser(); p.add_argument('--verify-only', action='store_true'); a=p.parse_args()
    if a.verify_only:
        verify(); return
    verify_proposal(CONFIRMATION)
    proposal=json.loads((CONFIRMATION/'proposal_private.json').read_text())
    layer=accepted(proposal,json.loads(PRIOR.read_text()),USER_MESSAGE)
    out=destination(OUT); stage=Path(tempfile.mkdtemp(prefix='.closure-accepted-',dir=MODULE)); stage.chmod(0o700)
    write_json(stage/'accepted_layer_private.json',layer)
    write_json(stage/'acceptance_record.json',{'user_message':USER_MESSAGE,
        'recorded_at_utc':layer['approval_recorded_at_utc'], 'new_decisions':{'yes_yes':3,'no_no':52,'retained_unknown':531},
        'all765':{'yes_yes':74,'no_no':159,'platform_excluded':1,'retained_unknown':531},
        'version_groups':15,'new_version_groups':3,'old_nonunknown_decisions_preserved':179,
        'labels_propagated':False,'early_preprint_use_backfilled':False,'API_valid_unchanged':{'a':525,'b':468,'c':482},
        'new_provider_requests':0,'original_final_changed':False,'independent_human_gold':False})
    fields=['review_id','work_id','publication_year','af_use_label','adoption_eligible','relevance_level','evidence_level','source_review','decision_status']
    write_csv(stage/'accepted_routes.csv',[{k:r[k] for k in fields} for r in layer['decisions']],fields)
    (stage/'README_zh.md').write_text('''# Figure 1补查接受层 v2

用户已确认586项剩余处置与3组同研究关系；保留先前179项非未知决定和12组关系。765项候选合计74项采用、159项非采用、1项原始平台排除、531项未知。15组特定版本关系不传播使用标签、不倒填预印本日期。

[接受记录](acceptance_record.json) · [逐项分流](accepted_routes.csv) · [证据溯源](accepted_layer_private.json)

这是辅助审阅后用户接受的独立派生层，不是独立人工双标金标准。全流程处置收尾不等于全球召回或版本去重完备；未知不当作非使用。旧数据库、旧结果、API成功数均不变。
''',encoding='utf-8')
    write_json(stage/'run_manifest.json',{'schema':'figure1-specific-closure-acceptance-v2',
        'inputs':layer['source_review_pins'],'outputs':inventory(stage),'approval_status':'accepted_by_user'})
    verify(stage); stage.rename(out); print('Accepted version saved:',out)


if __name__=='__main__':main()
