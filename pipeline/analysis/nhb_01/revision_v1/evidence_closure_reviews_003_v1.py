"""Handwritten observations after reading records 31–50, no automated AF labels."""
import json
from local_recall import MODULE, require, write_json

NOTES = {
 'W3036600652': '核糖体共翻译折叠/蛋白稳态综述，未给AF执行或输入归属。',
 'W3037651327': 'Swarm Learning基于血液转录组及去中心化隐私机制进行疾病分类，未建立AF过程。',
 'W3037700187': '自研同源二聚体接触图网络/梯度下降、PDB测试；方法可能借鉴其他网络，不等于采用AF。',
 'W3037809191': 'Mj.TyrRS以晶体结构及Rosetta建模、机器学习校正进行突变筛选，没有AF来源。',
 'W3045346722': '双向循环网络/随机森林做二级结构预测，使用PDB/CB数据；未指明AF输入。',
 'W3038926185': 'DConStruct转换接触/距离图并与CNS等比较；CASP12/13 targets不是AF模型来源证明，需核查输入图及比较者。',
 'W3042567394': '本地摘要只有补充数据通知。公开完整摘要为OPUS-TASS Transformer角度/二级结构预测，比较SPOT-1D；并非AF。是否其他部分消费AF仍待正文。',
 'W3042615946': 'minimal genome研究自称DMPfold建模438蛋白，不能将DMPfold作为AF采用；全文其他AF比较仍未排除。',
 'W3121781769': '蛋白3D几何卷积/池化算法，未披露AF作为训练/测试数据来源。与W3155077355完全同DOI，版本身份线索保留。',
 'W3155077355': '摘要同一几何卷积工作，文本含字面\\n转义，原文保留。与W3121781769同arXiv DOI，不独立推断AF采用。',
 'W3043176067': 'cryo-EM自动模型构建使用GCN/LSTM与rotamer候选，未声明AF；不能因EM建模即推断AF。',
 'W3093994104': '本地仅补充通知，公开摘要为RNAsnap2、LinearPartition的RNA溶剂可及性预测；没有AF输入证据。公开2021、本地2020日期差异保留。',
 'W3112910679': 'PASS/S4PRED单序列二级结构预测，未建立AF来源；可借鉴深度学习不等于运行AF。',
 'W3033096976': 'CATH超家族混合卷积自编码器，Urfold背景；与早期同名论文可能版本相关但未自动归并。',
 'W3042780272': '深度学习结构建模/设计综述，声明总结与讨论算法；未给作者AF实测过程。',
 'W3044773187': '明确将随机序列输入trRosetta并Monte Carlo优化，属于独立结构网络，不扩展为AF-like采用；尚未读后续验证正文，仍不能完全排除其他AF部分。',
 'W3046534009': 'CoCoNet以DCA/浅CNN预测RNA接触，在约60个RNA结构验证；蛋白网络是背景，不确立AF。',
 'W3048258966': 'Ig-VAE直接生成免疫球蛋白坐标及RBD结合者，结构生成器非AF；未说明预测验证来源。',
 'W3049265861': '高/低分辨率及NMR结构的卷积分类，不说明AF结构为样本。',
 'W3048402997': 'DCA序列重采样分离系统发育与功能耦合；未说明运行AF或读取AF结构。',
}


def main():
    packets = json.loads((MODULE / 'evidence_closure_preparation_v1/packets_private.json').read_text())
    selected = [p for p in packets if p['prior_route'] == 'not_individually_reviewed'][30:50]
    require(set(NOTES) == {p['work_id'] for p in selected}, 'Actual reading scope differs')
    rows = []
    for p in selected:
        rows.append({
            'work_id': p['work_id'], 'review_id': p['review_id'], 'publication_year': p['publication_year'],
            'title': p['title'], 'primary_label': 'uncertain', 'relevance_level': 'RU', 'evidence_level': 'E1',
            'af_related_label': 'uncertain', 'af_use_label': 'uncertain', 'adoption_eligible': 'uncertain',
            'evidence': [], 'reasoning_zh': NOTES[p['work_id']] + '已完整阅读两种可提供的摘要，缺正文时保留未知，不据摘要缺词直接判未使用。',
            'reading_scope': {'abstract_variants_actually_read': ['local_abstract','public_abstract'],
                              'body_actually_read': False, 'external_search_this_stage': False},
            'closure_status': 'abstract_reviewed_retained_unknown',
            'unknown_reason': 'abstract_cannot_establish_AF_use_body_unavailable',
            'reviewer_id': 'root_assisted_evidence_closure', 'review_status': 'pending_user_acceptance',
            'independent_human_gold': False, 'source_body_sha256': None, 'needs_human_review': True})
    write_json(MODULE / 'evidence_closure_reviews_003_v1.json', rows)
    print('20 additional individual abstract reviews archived; labels remain unknown; no requests/acceptance')


if __name__ == '__main__': main()
