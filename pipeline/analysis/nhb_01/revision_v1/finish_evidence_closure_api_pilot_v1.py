"""Verify the complete bounded pilot and export a candid Chinese report.

No requests, acceptance, label changes, merges, or reruns of old analyses.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from compare_evidence_closure_api_v1 import CORE, load_results, verify_c_route
from evidence_closure_api_v1 import INPUTS, OUTPUTS, read_jsonl
from fetch_public_evidence import inventory
from inspect_evidence_closure_api_v1 import model_status
from local_recall import MODULE, destination, pin, require, sha, write_csv, write_json
import prepare_evidence_closure_api_v2 as repaired

OUT = MODULE / 'evidence_closure_api_pilot_report_v1'
HOLDS = {
    'W3062307266':'CASP13全部组模型可能包含AF1；A/B的FP一致不能排除使用，C也保留未知。补入AF1参考文献仍不能证明哪些模型被实际评价。',
    'W4318317763':'RAD52讨论中的AF预测来源和整合程度不清；A建议采用、C建议仅讨论，需保留边界问题，不自动取C为金标准。',
    'W4393581939':'AlphaMissense分数比较是否属于本研究AF采用尚不明确；不能仅因工具基于AF就自动纳入，也不自动将自建ICM工具标成AF下游开发。',
    'W4407745252':'DeepCROSS工作流没有明确AF使用，但另一种工作流的存在本身不证明候选身份为FP；应核对召回参考文献/正文，暂不接受排除。',
}


def assemble():
    route = verify_c_route(); repaired_summary = repaired.verify()
    packets = read_jsonl(INPUTS/'smoke20_model_inputs.jsonl'); by_id = {p['work_id']:p for p in packets}
    results, pins = {}, []
    for m in 'abc':
        results[m], added = load_results(m, by_id); pins += added
    c_inputs = read_jsonl(OUTPUTS/'comparison_v1/smoke20_c_inputs.jsonl')
    require(set(results['c']) == {p['work_id'] for p in c_inputs}, 'C pilot not fully valid')
    rows = []
    for packet in packets:
        wid = packet['work_id']
        a, b, c = [results[m].get(wid) for m in 'abc']
        selected = c or a
        require(selected is not None, 'No valid suggestion for pilot work')
        if c is None:
            require(b is not None and all(a['response'][k] == b['response'][k] for k in CORE), 'Unreviewed core disagreement')
        row = {'work_id':wid, 'publication_year':packet['input_material']['publication_year'],
               'title':packet['input_material']['title'], 'material_tier':packet['evidence_tier'],
               'selected_suggestion_source':'C' if c else 'A_B_agreement',
               'semantic_status':'pending_not_an_accepted_label', 'specific_hold_zh':HOLDS.get(wid, '')}
        for m, result in zip('abc', [a,b,c]):
            row[m+'_api_valid'] = result is not None
            for k in CORE: row[m+'_'+k] = result['response'][k] if result else None
        row['selected_primary_suggestion'] = selected['response']['primary_label']
        rows.append(row)
    paired = set(results['a']) & set(results['b'])
    disagreements = sum(any(results['a'][w]['response'][k] != results['b'][w]['response'][k] for k in CORE) for w in paired)
    error_rows = []
    for m in 'ab':
        for r in read_jsonl(OUTPUTS/f'model_{m}_smoke20_v1.errors.jsonl'):
            error_rows.append({'model':m, 'work_id':r['work_id'], 'errors':r.get('validation_errors', [])})
    old_material = {p['work_id']:p['input_material'] for p in packets}
    new_packets = read_jsonl(repaired.OUT/'smoke20_model_inputs.jsonl')
    summary = {'pilot_works':20, 'actual_http_calls':58,
               'models':[model_status(m) for m in 'abc'],
               'ab_paired_valid':len(paired), 'ab_core_disagreement_paired_valid':disagreements,
               'c_routed':route['c_routed'],
               'c_primary_suggestions':dict(Counter(r['response']['primary_label'] for r in results['c'].values())),
               'selected_suggestions_for_20':dict(Counter(r['selected_primary_suggestion'] for r in rows)),
               'specific_semantic_hold_works':list(HOLDS), 'failed_model_records':error_rows,
               'v2_input_repair':repaired_summary,
               'pilot_input_material_changed_in_v2':sum(p['input_material'] != old_material[p['work_id']] for p in new_packets),
               'accepted_new_labels':0, 'full_queue_ready':False,
               'independent_human_gold':False, 'old_final_database_changed':False,
               'old_figures_changed':False, 'new_public_requests':0}
    pins += [pin(INPUTS/'run_manifest.json'), pin(OUTPUTS/'comparison_v1/run_manifest.json'),
             pin(repaired.OUT/'run_manifest.json'), pin(Path(__file__))]
    return rows, summary, pins


def report(summary):
    statuses = {r['model']:r for r in summary['models']}
    lines = ['# Figure1新增证据收尾：A/B→C 20项先导结果', '',
        '## 结论', '',
        '接口和存档流程可用，但尚不能冻结586项科学判定。多数先导样本没有可识别AF使用的科学证据；增加模型数量不能补出未提供的事实。已经修复输入中的参考文献身份丢失，另存v2，不改v1 API档案。', '',
        '此次是有意覆盖年份与证据类型的20项流程/边界先导，不是随机性能样本；不能将其成功率、分歧率或新增采用率外推至554项。API校验通过只表明当前结构、字面引文及规则校验通过，不代表独立人工语义认证。', '',
        '## 实际执行及费用', '',
        '|模型|提交论文/HTTP请求|API有效输出|失败|报告input/output tokens|报告费用|',
        '|---|---:|---:|---:|---:|---|']
    for m, name in [('a','A：DeepSeek flash / high'),('b','B：GLM flash / high'),('c','C：OpenRouter GPT-5.6-luna / xhigh')]:
        r = statuses[m]; cost = f"US${r['reported_cost_usd']:.8f}" if r['reported_cost_usd'] is not None else '未报告货币金额，查平台账单；不是0'
        t = r['reported_token_totals']
        lines.append(f"|{name}|{r['http_started']}|{r['validated_outputs']}|{r['failed_records']}|{t['input_tokens']:,} / {t['output_tokens']:,}|{cost}|")
    lines += ['', '共58次请求，A/B各20，C18；每阶段2并发，HTTP及验证重试均为0，max output tokens=20,000。C收到相同证据，不收到A/B答案；不存在重跑失败引文的额外自动费用。原接口、提示词v4和schema v2均沿用。', '',
        f"A/B共同有效13项，六个核心字段存在分歧{summary['ab_core_disagreement_paired_valid']}项；`observed_actions`没有进入核心一致性判断。C还包含双方共同未知、FP排除风险及一侧失败，因此18项C分流不等于18项A/B分歧。", '',
        'A有1条、B有7条失败：3条记录仅引文超25词；A另一条同时超长且不为原文子串；2条schema多余字段、1条枚举值错误、1条缺AF标识却给正向关系。上述类别按记录计，合计8条模型记录，涉及的论文有重叠。未将失败响应充作API成功。', '',
        'C的18项建议：15未知、1讨论性非采用、1疑似误召回FP、1采用/方法开发。其余2项A/B一致建议为背景提及。20项全部有可追溯的候选建议，但新增已接受标签为0。', '',
        '## 必须保留的四个语义边界', '']
    for wid, note in HOLDS.items(): lines += [f'- `{wid}`：{note}']
    lines += ['', '其余摘要中未出现AF，不能据此标“未使用”。C把一些全文无AF标识记录保留为E1/RU，是“AF相关证据强度低”的建议，不表示没有全文。模型置信度也不等于正确概率。', '',
        '## 已完成的v2离线修复', '',
        '全586项重新构建：554项API合格（400仅摘要、154有可用科学正文），30项缺科学证据、2项超30,000估算token上限留人工；不会偷偷截断，也不会把Forced-U当非采用。', '',
        '71篇恢复了真实源文献中的AF DOI/数据库标题参考摘录，每条有源文档SHA256、章节及字符偏移。它们单独置于`matched_seed_references`，不作为正文E3、使用证据或执行证据。并额外移除了160个已识别行政章节。仍不承诺正文内嵌行政文字、表格、方程、补充材料全部被完整提取。', '',
        '摘录范围可能包含相邻参考条目；其身份标识明确，但不能自行建立正文中的编号链接。CASP全部模型与AF1模型是否真正对应仍需额外证据。不是“71篇新AF采用”。', '',
        f"先导20项中{summary['pilot_input_material_changed_in_v2']}项input_material实际改变；所有20项context_policy版本改变。v1输出不能作为v2 resume credit。无需为了消除8条结构失败立刻再付费重跑，C已为18项提供有效建议。", '',
        '12项v2回归测试、v2完整导出/重建通过。30项缺证和2项超限没有发送API。旧数据库、Figure1、已接受765候选层及52条先前助手核查笔记均未修改。', '',
        '## 后续合并执行计划与停止点', '',
        '1. 核对召回参考文献和正文缺口，优先处理2019–2021、仅摘要且无法定位AF关系的条目。此前公开下载计划不因本次付费先导自动扩大；若要继续获取尚缺正文需另行确定公开请求预算。',
        '2. 统一AlphaMissense“仅比较AF衍生工具分数”边界：建议不把它单独当作已证实直接AF结构采用；若要纳入AF衍生工具采用，需事先明确扩展定义，不能只为纳入一例改变标准。RAD52和CASP13保持未决，不按多数投票强判。',
        '3. 在修复后的输入上做必要的定向语义复查后，才生成/执行全量A/B→C队列。证据仍不足的记录明确标“已审阅仍未知”，不是永远要求把unknown消灭。模型输出分流＋异常审阅＋用户确认可合并为一个新接受层。',
        '4. 验证新接受层、版本去重及新增数量，再统一重建Figure1和中文结果/方法/zip。未知保留在覆盖与敏感性说明，不混入已证实AF采用分母。', '',
        '当前停止在科学定义/证据闸门：不运行全554、不再消费API、不合并判定、不更新论文结果。', '',
        '## 可点击文件', '',
        '- [逐论文A/B/C对照（CSV）](pilot_comparison_private.csv)',
        '- [完整先导汇总（JSON）](summary.json)',
        '- [v2输入汇总](../evidence_closure_api_inputs_v2/summary.json)',
        '- [v2修补代码](../prepare_evidence_closure_api_v2.py)',
        '- [A原始有效输出](../evidence_closure_api_smoke_v1/model_a_smoke20_v1.jsonl)',
        '- [B原始有效输出](../evidence_closure_api_smoke_v1/model_b_smoke20_v1.jsonl)',
        '- [C原始有效输出](../evidence_closure_api_smoke_v1/model_c_smoke20_v1.jsonl)',
        '- [执行协议](../evidence_closure_api_protocol_v2_zh.md)', '',
        '## 方法和软件披露', '',
        'Scientific Critical Thinking技能影响了本次“缺失证据不等于非采用”、FP一致性拦截及独立人工金标准的边界说明；没有正式使用临床GRADE评级。技能属于流程辅助，不是论文的AF事实证据，也不作为标注者。软件库参考：[Kassis等，ScientificAgentSkills（2026，arXiv预印本）](https://arxiv.org/abs/2609.00065)。', '',
        '结构化输出格式核对使用[OpenAI官方说明](https://developers.openai.com/api/docs/guides/structured-outputs)；它不证明OpenRouter路由的语义正确性或A/B货币费用。', '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--verify-only', action='store_true'); args = p.parse_args()
    rows, summary, pins = assemble()
    if args.verify_only:
        m = json.loads((OUT/'run_manifest.json').read_text())
        require(inventory(OUT) == m['outputs'], 'Pilot report changed')
        for source in m['inputs']: require(sha(source['path']) == source['sha256'], 'Pilot pin changed')
        require(summary == json.loads((OUT/'summary.json').read_text()), 'Pilot summary reconstruction differs')
        require((OUT/'results_zh.md').read_text() == report(summary), 'Pilot Chinese report differs')
        print('Pilot report reconstruction: PASS; accepted labels 0; full queue gated'); return
    out = destination(OUT); stage = Path(tempfile.mkdtemp(prefix='.closure-pilot-report-', dir=MODULE)); stage.chmod(0o700)
    write_csv(stage/'pilot_comparison_private.csv', rows, list(rows[0]))
    write_json(stage/'summary.json', summary)
    with (stage/'results_zh.md').open('x') as f: f.write(report(summary))
    (stage/'results_zh.md').chmod(0o600)
    write_json(stage/'run_manifest.json', {'schema':'figure1-closure-pilot-report-v1', 'inputs':pins, 'outputs':inventory(stage)})
    stage.rename(out)
    print('Pilot report + verified archives saved:', out, '; no acceptance/merge/API')


if __name__ == '__main__': main()
