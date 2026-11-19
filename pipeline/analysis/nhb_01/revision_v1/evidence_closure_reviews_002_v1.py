"""Individual handwritten abstract reviews 21–30, plus two targeted body follow-ups."""
import json
from local_recall import MODULE, require, sha, write_json

NOTES = {
 'W3021123910': ('FAcc结构构建使用深度距离网络、Rosetta及EM引导组装；未点名AF，不能把深度学习结构建模自动算AF。', 'computational protein folding using Rosetta', 'public_abstract'),
 'W3024291983': ('评价自研AWSEM-Suite在CASP13的预测与能量景观；未建立AF模型参与其比较，单是CASP13参赛不是AF采用。', 'AWSEM-Suite participated in CASP13 as a server predictor', 'public_abstract'),
 'W3025378907': ('摘要说明回顾template-free建模及CASP演化，未建立作者实际AF执行或评估；需阅读全文区分文献讨论与实测基准。', 'This review highlights the major strategies undertaken for template-free modelling', 'public_abstract'),
 'W3028175200': ('Fast SeqProp用于六种深度预测器，包括一个结构预测器；具体预测器未命名，AF输入/梯度接口归属待全文核查。', 'including a protein structure predictor.', 'local_abstract'),
 'W3033521949': ('ThreaderAI比较HHpred、CNFpred、CEthreader并测试CASP13 target数据；并未说明消费AF预测或AF作为比较者。', 'ThreaderAI outperforms currently popular template-based modelling methods HHpred, CNFpred', 'public_abstract'),
 'W4245849664': ('ZeroFold摘要说明二级结构事件提取及SARS-CoV-2 Spike测试，未点名AF；摘要中提示语只作为论文文本，未当成指令。', 'propose a balanced Protein Event extraction method', 'local_abstract'),
 'W3033632984': ('衰老研究方法综述谈模式生物、高通量与机器驱动方法；不确立AF采用。', 'We cover emerging model organisms, high-throughput methodologies and machine-driven approaches.', 'public_abstract'),
 'W3042405353': ('综述web服务器与预计算结构资源并讨论应用，摘要并未区分作者亲自操作与介绍既有应用。公开正式发表2021、本地2020，保留online/print日期差异待核对。', 'Here we review the web resources that biologists can use today', 'public_abstract'),
 'W3034301430': ('蛋白折叠历史/机器学习/量子计算的入门综述，未说明具体AF执行或实测。只有本地摘要。', 'this article reviews protein folding’s history', 'local_abstract'),
 'W2991593237': ('TCR概率生成模型，与2019预印本W2990374534摘要基本对应但题名略异；列为版本核对线索，不自动合并，不将VAE视为AF使用。', 'a knowledge-free variational autoencoder based on deep artificial neural networks.', 'public_abstract'),
}


def main():
    packets = json.loads((MODULE / 'evidence_closure_preparation_v1/packets_private.json').read_text())
    selected = [p for p in packets if p['prior_route'] == 'not_individually_reviewed'][20:30]
    require(set(NOTES) == {p['work_id'] for p in selected}, 'Reading scope differs')
    records = []
    for p in selected:
        note, quote, kind = NOTES[p['work_id']]
        # Preserve the exact apostrophe spelling of the archived arXiv abstract.
        if p['work_id'] == 'W3034301430': quote = "this article reviews protein folding's history"
        text = next(a['text'] for a in p['abstract_variants'] if a['source_kind'] == kind)
        require(quote in text and len(quote.split()) <= 25, 'Literal quote differs')
        records.append({
            'work_id': p['work_id'], 'review_id': p['review_id'], 'publication_year': p['publication_year'],
            'title': p['title'], 'primary_label': 'uncertain', 'relevance_level': 'RU', 'evidence_level': 'E1',
            'af_related_label': 'uncertain', 'af_use_label': 'uncertain', 'adoption_eligible': 'uncertain',
            'evidence': [{'source_kind': kind, 'quote': quote}], 'reasoning_zh': note,
            'reading_scope': {'abstract_variants_actually_read': ['local_abstract', 'public_abstract'],
                              'body_actually_read': False, 'external_search_this_stage': False},
            'closure_status': 'abstract_reviewed_retained_unknown',
            'unknown_reason': 'abstract_cannot_establish_AF_use_body_unavailable',
            'reviewer_id': 'root_assisted_evidence_closure', 'review_status': 'pending_user_acceptance',
            'independent_human_gold': False, 'source_body_sha256': None, 'needs_human_review': True})
    p = next(p for p in packets if p['work_id'] == 'W3025755767')
    # Full scientific sections 0–4 were read in exact-source chunks, after the
    # targeted reader; administrative sections and reference AF windows separately.
    quote = 'Certainly, the most significant breakthrough of the decade in the field of protein folding has been the development of AlphaFold .'
    doc = json.loads(__import__('pathlib').Path(p['body_document_path']).read_text())
    require(quote in doc['sections'][2]['text'] and len(quote.split()) <= 25, 'Body quote differs')
    records.append({
        'work_id': p['work_id'], 'review_id': p['review_id'], 'publication_year': p['publication_year'], 'title': p['title'],
        'primary_label': 'review_discussion', 'relevance_level': 'R2', 'evidence_level': 'E1',
        'af_related_label': 'related', 'af_use_label': 'no', 'adoption_eligible': 'no',
        'evidence': [{'source_kind': 'fulltext_body_section', 'section_index': 2, 'quote': quote}],
        'reasoning_zh': '已逐段阅读全文科学章节0–4。AF仅在机器学习参数化进展背景中出现；正文应用例为HADDOCK/MARTINI、ATTRACT、IMP、Rosetta及已有PDB-dev案例，没有本综述实际使用AF的工作流。建议从未知改为讨论性非使用，结论限于这篇可见全文，非排除作者其他研究使用。',
        'reading_scope': {'abstract_variants_actually_read': ['local_abstract', 'public_abstract'],
                          'body_actually_read': True, 'scientific_sections_read_complete': [0,1,2,3,4],
                          'references_read': 'all detected AF-related citation windows',
                          'complete_extracted_body_including_references_read': False,
                          'external_search_this_stage': False},
        'closure_status': 'reviewed_new_nonuse_proposal', 'unknown_reason': None,
        'source_body_sha256': sha(p['body_document_path']),
        'reviewer_id': 'root_assisted_evidence_closure', 'review_status': 'pending_user_acceptance',
        'independent_human_gold': False, 'needs_human_review': True})
    p = next(p for p in packets if p['work_id'] == 'W3062307266')
    quote = 'taking every model produced by every group.'
    doc = json.loads(__import__('pathlib').Path(p['body_document_path']).read_text())
    require(quote in doc['sections'][1]['text'], 'Methods quote differs')
    records.append({
        'work_id': p['work_id'], 'review_id': p['review_id'], 'publication_year': p['publication_year'], 'title': p['title'],
        'primary_label': 'uncertain', 'relevance_level': 'RU', 'evidence_level': 'E1',
        'af_related_label': 'related', 'af_use_label': 'uncertain', 'adoption_eligible': 'uncertain',
        'evidence': [{'source_kind': 'fulltext_body_section', 'section_index': 1, 'quote': quote}],
        'reasoning_zh': '进一步完整阅读方法、结果及结论。关键新发现：除了3DRobot，作者实测CASP13的全部组预测，52,296模型/133目标，并非只引用CASP13。若能核实该集合包含AF1/A7D提交，可构成AF预测的系统方法评估；目前尚未核实组映射，保留未知，不能误判为仅背景或直接当作采用。',
        'reading_scope': {'abstract_variants_actually_read': ['local_abstract', 'public_abstract'],
                          'body_actually_read': True, 'scientific_sections_read_complete': [1,2,3],
                          'partial_sections_read': [0], 'references_read': 'all detected AF-related citation windows',
                          'complete_extracted_body_including_references_read': False,
                          'external_search_this_stage': False},
        'closure_status': 'body_reviewed_retained_unknown',
        'unknown_reason': 'CASP13_all_group_dataset_AF1_inclusion_requires_primary_identity_check',
        'source_body_sha256': sha(p['body_document_path']),
        'reviewer_id': 'root_assisted_evidence_closure', 'review_status': 'pending_user_acceptance',
        'independent_human_gold': False, 'needs_human_review': True})
    write_json(MODULE / 'evidence_closure_reviews_002_v1.json', records)
    print('12 individual notes archived; one new nonuse proposal; one CASP13 provenance follow-up; acceptance pending')


if __name__ == '__main__': main()
