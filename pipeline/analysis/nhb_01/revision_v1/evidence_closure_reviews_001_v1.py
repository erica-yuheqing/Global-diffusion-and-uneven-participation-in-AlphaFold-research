"""Handwritten assisted reading notes, NOT an automated semantic classifier."""
from local_recall import MODULE, require, write_json
import json

# Written by the assistant after actually reading both supplied abstract variants.
# Each note is limited to that observed scope, not a claim about an unread body.
NOTES = {
 'W2952771283': ('LSTM以螺旋蛋白的φ/ψ角生成主链；未说明AF输入或执行。与2020年RamaNet题名相近，但GAN版本差异需核实，不能自动归并。2019原始日期不证明引用清单同年形成。', 'The LSTM model used only the ϕ and ψ angles', 'public_abstract'),
 'W2979255327': ('GCN训练/应用源为PDB、同源建模和SWISS-MODEL；预测结构未具体归属AF，不能从结构预测推断AF采用。需核对后续正式版或正文测试集。', 'We use our method to annotate PDB and SWISS-MODEL proteins', 'public_abstract'),
 'W2990374534': ('比较TCR序列概率的知识模型和VAE，摘要并非结构预测工作；本研究是否另用AF不能仅凭摘要排除，保持未知。', 'Here, we compare two inference methods trained on high-throughput sequencing data', 'public_abstract'),
 'W3037890437': ('公开摘要补齐酶-底物建模综述内容，未明确采用AF；正文未提供，不能把机器学习方法综述认作实际采用。元数据日期06-27与本地01-01需保留精度差异。', 'In this book chapter, we will analyze these techniques', 'public_abstract'),
 'W3090531330': ('讨论肽纳米载体合成、自组装及体内研究，未点名AF使用；非使用也不能仅凭摘要无AF词确定。', 'In this review, we discuss recent work in engineering peptide nanocarriers', 'public_abstract'),
 'W3001669356': ('DNA表型记录及RBS序列功能深度学习；实验工作流程明确，但未建立AF与本研究程序关系。', 'we apply this approach to record translation kinetics of more than 300,000 bacterial ribosome binding sites', 'public_abstract'),
 'W3003840103': ('QDeep为蛋白模型质量估计，比较ProQ/MESHI等；未给出AF模型或AF专门评估归属，CASP/通用预测模型不自动计作AF。', 'We present a new distance-based single-model quality estimation method called QDeep', 'public_abstract'),
 'W3004906356': ('任务为单细胞基因型矩阵的肿瘤系统发育拓扑，摘要没有AF过程；保持未知，未按研究主题猜测未使用。', 'we introduce fast deep-learning solutions', 'public_abstract'),
 'W3005927952': ('接触信息来源为直接耦合分析/NMR及随机原生接触，神经网络进展只见作者摘要背景；未建立AF模型输入或AF执行。', 'direct coupling analysis or NMR spectroscopy', 'public_abstract'),
 'W3008186720': ('两种摘要均缺失，Europe PMC未形成可核验身份命中，只有题名/DOI；不能进行使用语义判断。优先补取出版方摘要/开放预印本。', '', 'none'),
 'W3010484674': ('讨论cryo-EM探索构象景观的潜力，属于观点性摘要；未建立作者实际使用AF。', 'We argue that the recent advances of cryo-electron microscopy', 'public_abstract'),
 'W3011238454': ('DeepDist自行预测距离并在43个CASP13 hard domains评估；这些事实不证明AF是其基准输入。需查看AF1引用所在正文及比较表。', 'we develop a multi-task deep learning distance predictor (DeepDist)', 'public_abstract'),
 'W3013383818': ('本地所谓摘要仅为补充数据通知，无科学内容；公开摘要说明CRiSP自建模板/序列对齐/三机器学习预测器，未点名AF。本轮只把公开摘要视为可读科学证据。', 'based on a customized template database with cystine-specific sequence alignment and three machine-learning predictors.', 'public_abstract'),
 'W3025299761': ('卷积自编码器分析CATH超家族结构关系；结构来源没有AF归属。公开摘要缺失，全文未提供，保留未知。', 'Here, we describe our training of DL models on protein domain structures', 'local_abstract'),
 'W3016986592': ('以Hi-C/组蛋白数据预测染色质HICR/TAD，摘要并无AF使用程序；不因领域不同判为FP。', 'This approach utilises gradient boosted trees and convolutional neural networks', 'public_abstract'),
 'W3018227322': ('OPUS-Fold折叠框架结合多种子方法/约束，并含OPUS-Rota2；未建立AF预测输入，开放代码链接不等于AF执行。', 'OPUS-Fold is based on torsion-angle sampling.', 'public_abstract'),
 'W3018535642': ('本地XML摘要可读出LSTM-GAN生成主链及未来序列设计；未提供AF来源。与2019 RamaNet可能为版本关联，但LSTM/GAN变化使其需定向身份确认。', 'The LSTM-based GAN model used only', 'local_abstract'),
 'W3020925100': ('逆Ising/Potts方法综述讨论蛋白接触推断、非平衡系统及动力学参数；未明确AF程序。公开未命中、只有本地摘要，未知保留。', 'In this review we discuss two types of problems', 'local_abstract'),
 'W3022525784': ('VoroCNN在Voronoi蛋白表示上估计模型局部质量，摘要未说明AF是否构成测试来源；需正文数据来源核查。', 'We trained our model, called VoroCNN, to predict local qualities of 3D protein folds.', 'public_abstract'),
 'W3023984985': ('主要叙述Neoleukin-2/15 de novo蛋白设计及癌症免疫治疗；未建立AF输入/执行，不能把de novo计算设计泛化为AF采用。', 'we used de novo protein engineering to create Neoleukin-2/15', 'public_abstract'),
}


def rows():
    packets = json.loads((MODULE / 'evidence_closure_preparation_v1/packets_private.json').read_text())
    records = []
    selected = [p for p in packets if p['prior_route'] == 'not_individually_reviewed'][:20]
    require({p['work_id'] for p in selected} == set(NOTES), 'Handwritten reading scope differs')
    for p in selected:
        note, quote, kind = NOTES[p['work_id']]
        if quote:
            text = next(a['text'] for a in p['abstract_variants'] if a['source_kind'] == kind)
            require(quote in text and len(quote.split()) <= 25, 'Note source quote differs')
        records.append({
            'work_id': p['work_id'], 'review_id': p['review_id'],
            'publication_year': p['publication_year'], 'title': p['title'],
            'primary_label': 'uncertain', 'relevance_level': 'RU',
            'af_related_label': 'uncertain', 'af_use_label': 'uncertain', 'adoption_eligible': 'uncertain',
            'evidence_level': 'E1' if quote else 'E0',
            'evidence': [{'source_kind': kind, 'quote': quote}] if quote else [],
            'reasoning_zh': note,
            'reading_scope': {'abstract_variants_actually_read': ['local_abstract', 'public_abstract'],
                              'body_actually_read': False, 'external_search_this_stage': False},
            'closure_status': 'abstract_reviewed_retained_unknown' if quote else 'metadata_and_availability_checked_no_scientific_text',
            'unknown_reason': 'abstract_cannot_establish_AF_use_body_unavailable' if quote else 'no_usable_scientific_evidence',
            'reviewer_id': 'root_assisted_evidence_closure', 'review_status': 'pending_user_acceptance',
            'independent_human_gold': False, 'source_body_sha256': None,
            'needs_human_review': True})
    return records


def main():
    out = MODULE / 'evidence_closure_reviews_001_v1.json'
    require(not out.exists(), 'Review file exists; choose a new version')
    write_json(out, rows())
    print('20 individual reading notes archived; 19 abstract reviews + 1 availability check; no label changes/requests')


if __name__ == '__main__': main()
