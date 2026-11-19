"""Export four disjoint evidence-review groups; no use classification or API calls."""
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import tempfile

import prepare_candidate_review as prep
from local_recall import MODULE,require,sha,write_csv,write_json,destination
from fetch_public_evidence import inventory

SOURCE=MODULE/'candidate_review_v1'
OUT=MODULE/'candidate_triage_v1'


def group(packet):
    if packet['route']=='fulltext_body_available_semantic_review':return 'P1_verified_body_review'
    if packet['route']=='insufficient_evidence_retain_unknown_until_review':return 'P4_missing_or_invalid_evidence'
    require(packet['route']=='abstract_available_semantic_review','Unknown review route')
    hits=any(v['quality']['structural_status']=='usable' and v['quality']['af_term_occurrences']>0 for v in packet['abstract_variants'])
    return 'P2_abstract_af_mention_review' if hits else 'P3_abstract_without_af_term_targeted_body_or_unknown'


def build(packets):
    rows=[{'review_id':p['review_id'],'work_id':p['work_id'],'publication_year':p['publication_year'],
           'review_group':group(p),'version_lead_count':p['version_lead_count'],
           'af_use_label':'','adoption_eligible':'','review_status':'pending_semantic_review'} for p in packets]
    s={'candidate_works':len(rows),'disjoint_review_groups':dict(Counter(r['review_group'] for r in rows)),
       'by_year':{str(y):dict(Counter(r['review_group'] for r in rows if r['publication_year']==y)) for y in sorted({r['publication_year'] for r in rows})},
       'network_requests':0,'paid_llm_calls':0,'use_decisions':0,'merges':0,'semantic_validation':False}
    return rows,s


def report(s):
    groups=s['disjoint_review_groups']
    counts=lambda key:groups.get(key,0)
    years='\n'.join(f'| {y} | {v.get("P1_verified_body_review",0)} | {v.get("P2_abstract_af_mention_review",0)} | {v.get("P3_abstract_without_af_term_targeted_body_or_unknown",0)} | {v.get("P4_missing_or_invalid_evidence",0)} |' for y,v in s['by_year'].items())
    return f'''# 765篇候选：下一步该怎么评审

本页是对已完成技术筛查的四组互斥分流，不是自动使用判定。已停止所有公开API访问，不调用付费LLM，原始标签与研究版本不变。

| 优先组 | 数量 | 建议行动 |
| --- | ---: | --- |
| P1：已核验正文 | {counts('P1_verified_body_review')} | 先审阅正文及AF归属链，优先解决2020年使用与讨论的区别 |
| P2：摘要出现AF文字 | {counts('P2_abstract_af_mention_review')} | 可先做摘要语义审阅；提到AF不等于使用，明确使用仍按E2证据标记及复核 |
| P3：有摘要但无AF文字，且未核验正文 | {counts('P3_abstract_without_af_term_targeted_body_or_unknown')} | 不用摘要“无AF词”自动判no；若摘要不足，定向正文或保留不确定 |
| P4：缺摘要或技术上不适格，且无正文 | {counts('P4_missing_or_invalid_evidence')} | 保留证据不足待补；不能成为不使用对照 |

## 各年组成

| 年份 | P1正文 | P2摘要有AF字样 | P3摘要无AF字样 | P4证据不足 |
| --- | ---: | ---: | ---: | ---: |
{years}

分组只是字符串检索与证据存在性检查，不证明本研究确实使用或不使用AF；缩写与拼写检索仍可漏检。P3中可能有大量仅引用AF1的论文，但必须以正文或可归属证据判定，不能当作已知非使用。P1／P2总数也不代表实际采用数。

## 版本去重如何处理

完整冻结主表核查发现156篇候选有189条同DOI／同标题线索（两种理由可指向同一对作品，不是189个研究）。15个对应work已在旧候选库受过评审。不能直接复制旧标签或自动合并；先核对是否同一研究、哪个版本确实包含AF使用、日期与内容是否变化，再形成经确认的版本决定。

对于改题、无DOI及未采集正式版本，现有检查不保证发现。当前所有765篇仍保留work级身份，study级去重与新版图发布均未完成。

## 可点击操作入口

- [完整技术筛查与2020年分册证据卡](../candidate_review_v1/README_zh.md)
- [四组操作清单（无预填标签）](review_groups_private.csv)
- [全部765篇空白裁决表](../candidate_review_v1/review_decisions_blank_private.csv)
- [版本线索单独核对表](../candidate_review_v1/version_leads_private.csv)
- [全部765篇来源标记证据包](../candidate_review_v1/review_packets_private.json)
- [首批公开证据与剩余缺口](../public_evidence_v2/README_zh.md)
- [总实施入口](../README_zh.md)

## 剩余任务

1. 先进行P1及P2的语义审阅，逐项给出可回查证据和使用／采用建议，不把机器建议冒充人工裁决。
2. 在该结果基础上，决定哪些P3需要正文补查。请求已暂停，任何扩大取证或付费模型调用另行确认；不用盲目对765篇全量重跑LLM。
3. 确认新标签、去重与事件日期后，再移出旧筛查阴性、重建比较组和正式Figure 1；不只增加AF分子。

技术质量筛查与评审分流已完成，语义裁决尚未完成；原先2020年的10篇确认使用仍为旧冻结计数。
'''


def verify(directory):
    m=prep.strict_json(directory/'run_manifest.json')
    require(inventory(directory)==m['outputs'],'Triage inventory differs')
    for pin in m['inputs']:
        require(sha(Path(pin['path']))==pin['sha256'],'Triage source changed')
    rows,s=build(prep.strict_json(SOURCE/'review_packets_private.json'))
    import csv
    with (directory/'review_groups_private.csv').open(newline='',encoding='utf-8') as f:actual=list(csv.DictReader(f))
    require(actual==[{k:str(v) for k,v in r.items()} for r in rows],'Triage membership reconstruction differs')
    require(prep.strict_json(directory/'summary.json')==s==m['summary'],'Triage counts differ')
    return s


def main():
    prep.verify(SOURCE)
    packets=prep.strict_json(SOURCE/'review_packets_private.json')
    rows,s=build(packets)
    out=destination(OUT);stage=Path(tempfile.mkdtemp(prefix='.candidate-triage-incomplete-',dir=MODULE));stage.chmod(0o700)
    write_csv(stage/'review_groups_private.csv',rows,list(rows[0]))
    write_json(stage/'summary.json',s)
    (stage/'README_zh.md').write_text(report(s),encoding='utf-8');(stage/'README_zh.md').chmod(0o600)
    pins=[SOURCE/'run_manifest.json',SOURCE/'review_packets_private.json',Path(__file__)]
    write_json(stage/'run_manifest.json',{'schema':'figure1-candidate-disjoint-triage-v1',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'summary':s,
        'inputs':[{'path':str(p.absolute()),'sha256':sha(p)} for p in pins],'outputs':inventory(stage)})
    stage.rename(out);verify(out)
    print(f'Disjoint evidence-review groups/export verification PASS: {s["disjoint_review_groups"]}')
    print('No API, use classification, version merge or old-data changes')


if __name__=='__main__':main()
