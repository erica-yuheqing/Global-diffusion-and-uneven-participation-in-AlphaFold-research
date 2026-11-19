"""Offline, unaccepted semantic proposal; no API, labels or figure mutations."""
from collections import Counter
import copy
import json
from pathlib import Path

from evidence_closure_api_v1 import read_jsonl, fingerprint
from finish_closure_execution_v3 import INPUT, REPORT
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, pin, require, sha, write_csv, write_json
from read_closure_semantic_cases_v1 import AF

OUT = MODULE / 'evidence_closure_confirmation_v1'
POLICY = MODULE / 'closure_semantic_decisions_v1.json'
PRIOR = MODULE / 'accepted_candidate_layer_v1/accepted_layer_private.json'
VERSION = MODULE / 'evidence_closure_version_audit_v1'
BUDGET = MODULE / 'evidence_closure_final_budget_v1'


def checked_archive(directory):
    manifest = json.loads((directory / 'run_manifest.json').read_text())
    for name, expected in manifest['outputs'].items():
        path = directory / name
        require(path.is_file() and sha(path) == expected['sha256'], 'Frozen archive differs: ' + str(path))
        require(path.stat().st_size == expected['size_bytes'], 'Frozen size differs')
    return manifest


def quote(packet, index, text):
    blocks = [b for b in packet['input_material']['evidence_blocks'] if b['index'] == index]
    require(len(blocks) == 1 and text in blocks[0]['text'], 'Quote is not literal in declared block')
    require(0 < len(text.split()) <= 25, 'Quote exceeds old 25-word bound')
    return {'source_kind': 'fulltext_block', 'block_index': index,
            'section': blocks[0]['section'], 'quote': text}


def unknown(packet, row, policy):
    wid = packet['work_id']; tier = packet['evidence_tier']
    reason = policy['specific_unknown_reasons'].get(wid)
    if not reason:
        reason = {'abstract_only': '摘要或文献关系未建立本研究实际采用；摘要未出现AF不是非使用证据。',
                  'insufficient_evidence': '未取得可用的科学证据，保留未知而非误用R0。',
                  'oversize_context_human_review': '证据超过冻结包上限；本轮未完整实质阅读，不强判采用或非采用。',
                  'fulltext_evidence': '现有正文/引用语境未充分建立AF实际采用归属；仅有文献、独立工具或名称缺失不证明非使用。'}.get(tier, '证据不足，保留未知。')
    return {'work_id': wid, 'review_id': row['review_id'], 'primary_label': 'uncertain',
            'relevance_level': 'RU', 'evidence_level': 'E0' if tier == 'insufficient_evidence' else 'E1',
            'af_related_label': 'uncertain', 'af_use_label': 'uncertain', 'adoption_eligible': 'uncertain',
            'observed_actions': ['none'], 'action_evidence': [], 'evidence': [],
            'reasoning_zh': reason, 'action_scope': 'Unestablished, not an assertion that no action occurred.'}


def set_nonuse(decision, rlevel, elevel, evidence, reason):
    require(rlevel in ('R1', 'R2'), 'Nonuse proposals must not use R0 for missing evidence')
    decision.update(primary_label='background_only' if rlevel == 'R1' else 'review_discussion',
                    relevance_level=rlevel, evidence_level=elevel,
                    af_related_label='background' if rlevel == 'R1' else 'related',
                    af_use_label='no', adoption_eligible='no', evidence=[evidence], reasoning_zh=reason,
                    observed_actions=['none'] if rlevel == 'R1' else ['discussion_only'],
                    action_evidence=[] if rlevel == 'R1' else
                    [{'action': 'discussion_only', 'evidence_indices': [0]}])


def build():
    directories = [REPORT, MODULE / 'accepted_candidate_layer_v1', VERSION, BUDGET,
                   MODULE / 'evidence_closure_local_candidates_v1', MODULE / 'evidence_closure_tm_provenance_v1']
    manifests = [checked_archive(d) for d in directories]
    # Also check upstream content pins, rather than trusting a prior PASS string.
    for m in manifests:
        for entry in m.get('inputs', []):
            path = Path(entry['path'])
            require(path.is_file() and sha(path) == entry['sha256'], 'Selected upstream pin differs: ' + str(path))
    policy = json.loads(POLICY.read_text()); prior = json.loads(PRIOR.read_text())
    packets = {p['work_id']: p for p in read_jsonl(INPUT)}
    rows = json.loads((REPORT / 'candidate_proposals_private.json').read_text())
    require(len(rows) == len(packets) == 586, 'Expected frozen 586-work queue')
    require(len({r['work_id'] for r in rows}) == 586, 'Duplicate proposal work')
    old = {d['work_id']: d for d in prior['decisions']}
    require(len(old) == 765 and all(old[w]['af_use_label'] == 'uncertain' for w in packets),
            'Only previously accepted unknowns may be proposed for change')
    whitelist = policy['nonuse_body_work_ids']
    require(len(whitelist) == len(set(whitelist)), 'Duplicate explicit negative review')
    negatives = set(whitelist)
    additional = {x['work_id']: x for x in policy['additional_nonuse']}
    positives = {x['work_id']: x for x in policy['positive_proposals']}
    require(not (negatives & set(positives) or negatives & set(additional) or set(additional) & set(positives)),
            'Conflicting substantive decisions')
    require(negatives | set(additional) | set(positives) <= set(packets), 'Unknown reviewed work')
    decisions = []; comparisons = []
    for row in rows:
        wid = row['work_id']; packet = packets[wid]
        require(fingerprint(packet) == row['input_packet_sha256'], 'Mixed evidence packet')
        decision = unknown(packet, row, policy)
        if wid in negatives:
            response = row['candidate_response']
            require(packet['evidence_tier'] == 'fulltext_evidence' and response and response['af_use_label'] == 'no',
                    'Nonuse whitelist was not based on reviewed body suggestion')
            candidates = [e for e in response['evidence'] if e['source_kind'] == 'fulltext_block' and AF.search(e['quote'])]
            require(candidates, 'No attributable literal AF body evidence for reviewed nonuse')
            selected = next((e for e in candidates if 'method' in e['section'].lower()), candidates[0])
            evidence = quote(packet, selected['block_index'], selected['quote'])
            override = policy['nonuse_overrides'].get(wid, {})
            set_nonuse(decision, override.get('relevance_level', response['relevance_level']),
                       override.get('evidence_level', response['evidence_level']), evidence,
                       override.get('reasoning_zh', '已定位的AF正文语境为背景、综述、既往研究讨论或未来愿景；可见工作流程未建立本研究实际AF采用。该结论限于冻结证据包，不声称排除了不可见补充材料。'))
        elif wid in additional:
            spec = additional[wid]
            set_nonuse(decision, spec['relevance_level'], spec['evidence_level'],
                       quote(packet, spec['block_index'], spec['quote']), spec['reasoning_zh'])
        elif wid in positives:
            spec = positives[wid]
            decision.update(primary_label=spec['primary_label'], relevance_level=spec['relevance_level'],
                evidence_level='E3', af_related_label='related', af_use_label='yes', adoption_eligible='yes',
                evidence=[quote(packet, spec['block_index'], spec['quote'])], observed_actions=spec['actions'],
                action_evidence=[{'action': a, 'evidence_indices': [0]} for a in spec['actions']],
                reasoning_zh=spec['reasoning_zh'], prediction_origin_unclear=True)
            if spec.get('external_provenance'):
                decision['additional_provenance_manifest'] = pin(MODULE / spec['external_provenance'] / 'run_manifest.json')
                decision['external_provenance_not_in_model_input'] = True
        decision.update(publication_year=packet['input_material']['publication_year'],
                        title=packet['input_material']['title'], source_packet_sha256=fingerprint(packet),
                        decision_status='assistant_proposal_pending_user_confirmation', independent_human_gold=False,
                        previous_decision_sha256=fingerprint(old[wid]),
                        model_candidate_source=row['candidate_source'], API_success_credit=False,
                        reviewed_source_scope=policy['review_scope'])
        decisions.append(decision)
        response = row.get('candidate_response') or {}
        comparisons.append({'work_id': wid, 'review_id': row['review_id'], 'year': decision['publication_year'],
            'evidence_tier': packet['evidence_tier'], 'model_candidate_use': response.get('af_use_label', 'uncertain'),
            'proposed_use': decision['af_use_label'], 'proposed_adoption': decision['adoption_eligible'],
            'proposed_R': decision['relevance_level'], 'proposed_E': decision['evidence_level'],
            'reasoning_zh': decision['reasoning_zh'], 'status': decision['decision_status']})
    links = json.loads((VERSION / 'version_leads_private.json').read_text())
    proposed_links = []
    for wid in policy['new_version_proposal_work_ids']:
        matches = [x for x in links if x['work_id'] == wid and x.get('target') and
                   x['target']['af_use_label'] == x['target']['adoption_eligible'] == 'yes']
        require(len(matches) == 1 and not matches[0]['already_accepted_version_group'], 'Version target differs')
        lead = matches[0]; target = lead['target']
        require(lead['basis'] == 'biorxiv_published_doi' and lead['title_similarity'] >= .95, 'Version identity basis changed')
        proposed_links.append({'member_work_ids': [wid, target['work_id']],
            'representative_work_id': target['work_id'], 'representative_date': target['publication_date'],
            'basis': [lead['basis'], lead['linked_doi'], 'Exact publisher DOI plus concordant title; same-study identity only'],
            'approval_status': 'pending_user_confirmation', 'labels_propagated': False,
            'early_preprint_use_backfilled': False})
    updated = {d['work_id']: d for d in decisions}
    proposed_all = [copy.deepcopy(updated.get(d['work_id'], d)) for d in prior['decisions']]
    require(all(fingerprint(d) == fingerprint(old[d['work_id']]) for d in proposed_all if d['work_id'] not in packets),
            'Prior nonunknown decisions changed')
    counts = dict(Counter(d['af_use_label'] + '/' + d['adoption_eligible'] for d in decisions))
    summary = {'queue_works': 586, 'proposed_core_pairs': counts,
        'proposed_by_year': {str(y): dict(Counter(d['af_use_label'] for d in decisions if d['publication_year'] == y))
                             for y in sorted({d['publication_year'] for d in decisions})},
        'whole765_proposed_core_pairs': dict(Counter(d['af_use_label'] + '/' + d['adoption_eligible'] for d in proposed_all)),
        'old_nonunknown_decisions_preserved': 179, 'old_version_links_preserved': 12,
        'new_same_study_link_proposals': len(proposed_links), 'temporal_guard_works': 8,
        'other_relation_leads_not_automatically_merged': True,
        'API_valid_unchanged': {'a': 525, 'b': 468, 'c': 482},
        'local_format_candidates_separate_not_API_success': 10,
        'accepted_new_labels': 0, 'paid_requests_this_stage': 0,
        'approval_status': 'pending_one_user_confirmation', 'old_database_changed': False,
        'figure_recomputed': False, 'independent_human_gold': False,
        'methods_limitation': policy['review_scope'], 'budget': json.loads((BUDGET / 'summary.json').read_text())}
    proposal = {'schema': 'closure-one-confirmation-proposal-v1', 'approval_status': 'pending_one_user_confirmation',
        'decisions': decisions, 'proposed_all765_decisions': proposed_all,
        'preserved_old_version_links': prior['accepted_version_links'], 'proposed_version_links': proposed_links,
        'temporal_guards': json.loads((VERSION / 'temporal_leads_private.json').read_text()),
        'unknown_policy': policy['unknown_policy'], 'version_policy': policy['version_policy'], 'summary': summary}
    inputs = [pin(INPUT), pin(POLICY), pin(Path(__file__)), pin(PRIOR)]
    for directory in directories:
        inputs.append(pin(directory / 'run_manifest.json'))
        for name in json.loads((directory / 'run_manifest.json').read_text())['outputs']:
            inputs.append(pin(directory / name))
    return proposal, comparisons, inputs


def readme(proposal):
    s = proposal['summary']; c = s['proposed_core_pairs']
    positives = [d for d in proposal['decisions'] if d['af_use_label'] == 'yes']
    lines = '\n'.join(f"| {d['work_id']} | {d['publication_year']} | {d['relevance_level']} / {d['primary_label']} | {d['reasoning_zh']} |" for d in positives)
    versions = '\n'.join(f"- `{x['member_work_ids'][0]}` → `{x['representative_work_id']}`；保留正式版日期 {x['representative_date']}。" for x in proposal['proposed_version_links'])
    return f'''# Figure 1研究证据补查：一次性确认包

状态：**待你确认，尚未合并、冻结新标签或重算Figure 1**。无新增API调用；旧结果、原数据库与已接受179项判定/12组版本关系不变。

## 本轮建议

586项剩余候选建议分为：**3项采用、{c.get('no/no', 0)}项背景/综述等非采用、{c.get('uncertain/uncertain', 0)}项保留未知**。这是基于旧R/E及两个yes标签标准的辅助证据审阅，不是新人工双标金标准。

| work_id | 年份 | 建议 | 核查依据与动作边界 |
|---|---:|---|---|
{lines}

三项均不新增“运行AF/ColabFold”动作；TmAlphaFold也不记为下载了AF结构坐标。TRIO的R4依据是同一多案例队列、定义的准确率比较，不是一概纳入所有AF-like技术。

[586项逐项对照与理由](comparison_private.csv) · [建议标签及逐字证据、765项拟合并快照](proposal_private.json) · [机器可读汇总](summary.json)

## 为什么保留未知，不直接采用模型的115项否定建议

只有明确定位的正文背景/综述/未来语境才提出非采用建议。只凭AF参考文献、摘要未提AF、自主使用其他方法或模型多数票，不能证明未采用。CASP模型池归属不明、GCAP5中比较是否由本研究实施不明、附属图记录未映射母论文等情况保留未知。28项证据不足和2项超大包也不强制分类。

全流程有586项处置记录，但不声称每篇全文及不可见补充材料都经逐字人工审阅。阅读范围是冻结包、已定位AF正文语境、失败的阳性响应与重点完整方法/结果/讨论。无AF名称的筛查结果不是非使用判定。保留未知使研究数据证据层可以**有边界地收尾**；不是全球召回完备性证明，也不会为了消灭unknown重复付费。

## 版本身份与时间：一并请你确认

建议确认以下3组公开的预印本→正式版同研究关系；主分析继续以已经证实采用的正式版为代表，**不把其使用标签传播给早期预印本，不倒填首次采用日期**。

{versions}

原12组关系不变；8项arXiv修订时间风险保留，不把新版摘要当作初版证据。其余公开关系继续保留为线索，不自动合并，不声称完成全球全部版本去重。

## 已完成的调用与费用

真实A/B/C发送556 / 556 / 516次，共1,628次，低于授权5,274次上限。原API有效输出525 / 468 / 482条；10条本地格式候选与语义建议不冒充API成功。

A官方余额减少¥8.68（账户口径，可能含同期其他使用）；B保守费用上限¥4.835（不是实际账单）；C请求报告总费用$1.3633。A的旧请求名被服务端转到V4.1-Flash已经你同意；[版本、证据和预算方法披露](../evidence_closure_execution_v3_methods_zh.md)。[最终费用核对](../evidence_closure_final_budget_v1/summary.json)

## 确认后我会一起完成

1. 将本轮辅助判定、保留未知和3组同研究关系写入新的接受层版本；不覆盖旧final。
2. 接入Figure 1研究层，重算新版时间划分下的图和数字，检查分母、版本日期与回溯可复现性。
3. 同步更新中文Results、Methods、数量流程与图注，重新导出并验证ZIP及包内相对链接。

**请一次确认：接受上述3项采用建议、明确背景/综述的非采用建议、其余保留未知，以及3组版本身份关系（不传播标签/不倒填日期）。**
'''


def verify(directory):
    manifest = checked_archive(directory)
    for entry in manifest['inputs']:
        require(sha(Path(entry['path'])) == entry['sha256'], 'Confirmation upstream changed')
    proposal, comparison, _ = build()
    require(fingerprint(proposal) == fingerprint(json.loads((directory / 'proposal_private.json').read_text())),
            'Proposal reconstruction differs')
    require(proposal['approval_status'] == 'pending_one_user_confirmation', 'Builder cannot approve')
    return proposal['summary']


def main():
    import argparse
    p = argparse.ArgumentParser(); p.add_argument('--verify-only', action='store_true'); args = p.parse_args()
    if args.verify_only:
        summary = verify(OUT)
    else:
        proposal, comparisons, inputs = build()
        out = destination(OUT); out.mkdir(mode=0o700)
        write_json(out / 'proposal_private.json', proposal)
        write_json(out / 'summary.json', proposal['summary'])
        write_csv(out / 'comparison_private.csv', comparisons, list(comparisons[0]))
        # Markdown is a generated artifact from a saved, hashed script.
        with (out / 'README_zh.md').open('x') as f:
            f.write(readme(proposal))
        (out / 'README_zh.md').chmod(0o600)
        write_json(out / 'run_manifest.json', {'schema': 'closure-pending-confirmation-archive-v1',
            'inputs': inputs, 'outputs': inventory(out), 'summary': proposal['summary']})
        summary = verify(out)
    print('Confirmation reconstruction: PASS; proposed pairs:', summary['proposed_core_pairs'])
    print('Approval pending; no API, old-label writes, date backfill or figure integration:', OUT)


if __name__ == '__main__':
    main()
