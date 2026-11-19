"""Evidence-linked Chinese Figure1 prose; no submission or human-review certification."""
import json
from pathlib import Path
import pandas as pd

def table(df,columns):
    lines=['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']
    for _,r in df[columns].iterrows():
        lines.append('| '+' | '.join('NA' if pd.isna(r[c]) else f'{r[c]:.4f}' if isinstance(r[c],float) else str(r[c]) for c in columns)+' |')
    return '\n'.join(lines)

def write(directory,tables,summary,protocol):
    directory=Path(directory);diagnostic=not summary['formal_revised_result']
    banner='**旧标签布局诊断，不能替换论文Results；765篇新增候选仍待语义接受。**\n\n' if diagnostic else '**稿件草稿：数值导出经程序核验，仍需作者检查图形和解读；辅助判定不是独立人工金标准。**\n\n'
    figure='figure1_revised_a_d_diagnostic' if diagnostic else 'figure1_revised_a_d'
    annual=tables['annual_counts'].query('publication_year>=2020')
    period=tables['period_counts'];m=tables['monthly_diffusion'];g=tables['concentration']
    end=g[g.year.eq(2025)].iloc[0];trend=tables['concentration_endpoint_sensitivity']
    (directory/'methods_zh.md').write_text('# Figure 1 新版Methods草稿\n\n'+banner+'''本分析使用已冻结OpenAlex数据及AF复核结果，限article、review和preprint，历史期为2015–2019年，扩散主期为2020–2025年。OpenAlex原始采集于2026年4月3日所在周完成；本轮补查仅补充特定候选的公共摘要／可用正文，不更新整库引用快照。新增候选由遗漏的AF1种子引用与扩展关键词召回，再以已有R/E标准辅助核查。引用AF论文、仅出现AF关键词或正文下载成功均不等于实际使用；无法建立使用的记录保留未知，不混入筛查阴性背景组。原始AF平台论文不计入下游采用分子。只有af_use_label=yes且adoption_eligible=yes的研究计入已证实采用。[M-F1-01；证据：summary.json、候选接受层]

同研究版本只按明确接受的关联归并，不按相同标题自动合并。年度与时期统计使用一个一致代表记录及其原有国家集合；新增已接受版本组的首次观察只使用独立确认采用的成员日期及该成员自己的国家集合，不把正式版的使用或机构回填到早期预印本。其余未核实版本线索仍保留，不能将本结果称为穷尽去重。[M-F1-02；证据：候选接受层、derived_study_records.parquet（如适用）]

每篇研究对所列k个国家／地区各分配1/k信用。同年／时期的已知国家AF信用总和等于国家可归属的AF研究数；国家缺失信用另列Unknown，不重新分摊。全球份额以已知国家AF信用为分母；国内AF比例以本地采集领域全部适格研究的国家信用为分母，不是国家全部科学论文或国家R&D投入。国家集中度统一在227个国家与地区上计算，零信用国家保留。[M-F1-03；证据：annual_country_credits.csv、country_period_profiles.csv]

时期按发表月份划分为2020年1月–2021年6月、2021年7月–2024年4月和2024年5月–2025年12月。发表月无法确定实际使用的AF版本与执行时间，时期命名只用于可复核的阶段描述。日期可解析不意味着月份精度得到完全认证；1月1日另列精度审查标志，未因此自动剔除。主期前首次观察的国家在累计曲线中保留。十国按2020–2025全期AF分数信用选择，六个年度使用同一名单，且显示Other及Unknown。[M-F1-04；证据：protocol.json、date_audit.csv、monthly_diffusion.csv、fixed_ten_composition.csv]

AF与筛查阴性背景的Gini分别进行1000次整篇研究重采样，固定随机种子20261009；相同国家集合的研究以多项分布频数聚合，等价于对研究而非国家重采样，未知国家记录同样进入抽样。每年／组使用独立随机流，AF与背景的对应重复作差得到ΔGini的百分位95%区间。这些区间条件于当前观察记录，不含漏检、标签误差、数据库差异及跨年作者／研究团队依赖。2021及2022起算的端点变化作为描述性敏感性分析，不是单调趋势或发布因果效应的正式检验。[M-F1-05；证据：bootstrap_draws.csv、concentration.csv、concentration_endpoint_sensitivity.csv]

补充国内比例热图在同一年度×类型×主要子领域共同支持下成对显示。未调整侧与匹配侧使用完全相同研究支持；匹配侧保持共同支持ALL总量，将各层分布匹配到AF构成，形成明确标注的假想国内分母。它仅是构成敏感性，不是因果调整或原始国内比例的替代。报告共同支持保留数量及比例，缺分母显示NA／灰色而不是0。[M-F1-06；证据：paired_domestic_heatmaps.csv、paired_domestic_heatmap_support.csv]

本轮修改是针对已观察到的早期稀疏与召回缺口的事后修订，不宣称事前注册。正文使用描述性“已观察扩散与集中度”措辞，不推断AF导致不平等或模型发布导致国家进入。全部辅助复核与作者接受保留独立溯源，原最终库不被覆盖。
''',encoding='utf-8')
    (directory/'results_zh.md').write_text('# Figure 1 新版Results与解读草稿\n\n'+banner+
        f'2020–2025年纳入已证实AF采用研究{summary["confirmed_AF_main"]:,}个。至2025年12月，共观察到{int(m.cumulative_countries.iloc[-1])}个国家／地区参与；主期开始前已观察到{int(m.pre2020_countries.iloc[0])}个。累计观察范围扩大不意味着每个国家连续参与，也不意味着所有年份的分布均匀化。[R-F1-01；证据：[monthly_diffusion.csv](monthly_diffusion.csv)、[annual_counts.csv](annual_counts.csv)]\n\n'+
        table(annual,['publication_year','confirmed_af'])+'\n\n三个阶段的研究数量及可归属情况如下；阶段长度不同，不能将数量直接解释为速度差异或发布效应。[R-F1-02；证据：[period_counts.csv](period_counts.csv)]\n\n'+
        table(period,['period_name','af_studies','af_assigned','af_unknown'])+'\n\n'+
        f'2025年AF国家信用Gini为{end.af_gini:.4f}，筛查阴性背景为{end.comparator_gini:.4f}，差值为{end.delta_gini:.4f}（条件95%区间[{end.delta_lower:.4f}, {end.delta_upper:.4f}]）。相对差值反映本地观察分布，而非因果差异；不能由高Gini直接推出低信用国家缺乏研究能力。[R-F1-03；证据：[concentration.csv](concentration.csv)]\n\n'+
        table(trend,['start','end','estimand','point','lower','upper'])+'\n\n'+
        '上述端点结果应逐项解读，不能选择早期起点中效果最明显的一项；区间跨0时只说明当前描述性数据不支持确定方向，不能视作无差异证明。[R-F1-04；证据：[concentration_endpoint_sensitivity.csv](concentration_endpoint_sensitivity.csv)]\n\n'+
        f'固定全期十国为{", ".join(summary["fixed_ten"])}。名单固定，年度构成仍可改变；Unknown权重保留在堆叠分母，因此本图份额与“仅已知国家”份额可能不同。[R-F1-05；证据：[fixed_ten_composition.csv](fixed_ten_composition.csv)]\n\n'+
        f'![Figure 1 a–d](figures/{figure}.png)\n\n[图注](captions_zh.md) · [逐面板读者信息](reader_information_zh.md) · [Methods](methods_zh.md)\n',encoding='utf-8')
    (directory/'captions_zh.md').write_text('# Figure 1 图注与替代文本\n\n'+banner+'''**Figure 1｜AlphaFold采用的已观察地理扩散、国内比重与相对集中度。** a，按发表月份观察的累计首次参与国家／地区及当月新增数量，主期前历史保留；虚线标记2021年7月和2024年5月阶段边界。b，三个阶段各国全球已知AF信用份额与本地领域国内AF比例，使用相同线性坐标、固定点大小和全期固定十国标注；各期n为该期研究数。c，年度AF研究量与固定十国分数信用构成，Other为其他已知国家，斜线Unknown为未归属国家信用，分母为全部AF研究。d，固定227国的AF及筛查阴性背景Gini与AF−背景差值；阴影／误差条为1000次整篇研究bootstrap的条件95%百分位区间，零线用于差值参照。Gini主图纵轴截取以显示差异，补充图提供完整0–1轴。未知数据与版本线索不能被这些区间消除。时期依据发表日期，不代表实际模型版本或发布因果效应。

**替代文本。** 四面板分别描述首次参与的月度累积、三个发表阶段的国家全球份额和国内比例、各年的研究数量及固定国家构成、AF与背景集中度及其差值。未知归属单独显示；主图使用颜色之外的点形与斜线区分组别，补充图给出完整轴及成对共同支持热图。具体数字以同目录底表和Results为准。
''',encoding='utf-8')
    guide='''# 逐面板读者信息、方法修改与支持边界

本文件逐项对照新版figure1-revision-plan；不以漂亮图形替代证据。正式状态见summary.json，作者稿件批准另行保留。

| 面板 | 读者应获得的信息 | 方法及修改原因 | 不应据此得出的结论 | 底表 |
| --- | --- | --- | --- | --- |
| a | 地理首次观察何时扩大、哪些月份增加，而非只看年末 | 改为月度累计线与共轴新增柱；保留主期前历史，减少2020稀疏造成的年度折线误读 | 发表月份不是实际采用时间；边界不是因果事件研究 | monthly_diffusion.csv、country_first_observed.csv |
| b | 全球AF贡献大与本地领域采用比重高不是同一排序 | 三个时期共用线性轴、固定点大小及固定国家标注；期间使用累计信用分子与累计信用分母而非平均比例 | 国内率不是国家全科学产出比例，也不是R&D能力分组 | country_period_profiles.csv、period_counts.csv |
| c | 研究数量增长与国家信用构成变化分开看 | 数量柱与100%构成上下共轴；固定十国按全2020–2025期选取，每年不替换；Other／Unknown保留 | 小样本早期份额没有稳定总体代表性；未知不得分摊 | annual_counts.csv、fixed_ten_composition.csv |
| d | AF集中程度及其相对于领域背景的差值是否变化 | 同时显示AF／背景Gini和ΔGini，研究级bootstrap，固定227国家含零；补充0–1轴及2021／2022起点检查 | 不能强称机会不平等由AF导致，也不能用2020单一起点证明持续单调收敛 | concentration.csv、concentration_endpoint_sensitivity.csv |
| 补充国内热图 | 国内比例与构成差异的敏感性，而不是另一次全球份额排序 | 同年×类型×子领域共同支持，未调整／AF构成匹配使用相同样本，逐国覆盖表公开 | 匹配后的假想分母不是原始国家分母，不是因果效应 | paired_domestic_heatmaps.csv、paired_domestic_heatmap_support.csv |

**原要求中尚未等同完成的内容：** 原始研究版本仍非穷尽去重；来源覆盖与标签不确定性仍存在；此模块不提供释放事件因果推断、跨年团队依赖稳健趋势或完整世界地图。这些限制不能用技术校验通过来掩盖，正文只使用可支持的描述性结论。首次观察国家清单和年月已导出，可不依赖地图传达具体首次观察信息。

图注、方法和Results的全部计数均来自同一导出。源文件锁、代码快照及数值检查是可复现性证据，不是独立人工金标准或期刊提交批准。
'''
    (directory/'reader_information_zh.md').write_text(banner+guide,encoding='utf-8')
    (directory/'claim_evidence_registry.json').write_text(json.dumps({'submission_ready':False,'author_review':'pending',
        'claims':{'R-F1-01':['monthly_diffusion.csv','annual_counts.csv'],'R-F1-02':['period_counts.csv'],
        'R-F1-03':['concentration.csv'],'R-F1-04':['concentration_endpoint_sensitivity.csv'],
        'R-F1-05':['fixed_ten_composition.csv']},'methods':['M-F1-01','M-F1-02','M-F1-03','M-F1-04','M-F1-05','M-F1-06']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
