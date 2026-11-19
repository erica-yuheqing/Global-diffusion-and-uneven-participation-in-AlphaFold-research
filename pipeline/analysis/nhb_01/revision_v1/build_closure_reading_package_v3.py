"""Portable Figure1 release, from accepted closure and reconstructed numeric exports only."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
import pandas as pd
import pyarrow.parquet as pq
from local_recall import MODULE, PLAN, destination, pin, require, sha, write_json
from fetch_public_evidence import inventory
from verify_revised_country_bundle import verify as verify_analysis
from accept_closure_layer_v2 import verify as verify_acceptance, OUT as ACCEPTANCE
from build_revision_reading_package import links_ok, md_table, check_inventory

SOURCE=MODULE/'figure1_revision_final_v2'
MAP=MODULE/'first_observed_map_v2'
REVIEW=MODULE/'closure_visual_review_v2'
OUT=MODULE/'figure1_revision_reading_package_v3'
BUDGET=MODULE/'evidence_closure_final_budget_v1'
TABLES=['monthly_diffusion','country_first_observed','date_audit','annual_counts','annual_country_coverage',
    'annual_diffusion_counts','period_counts','country_period_profiles','annual_country_credits','annual_source_coverage',
    'fixed_ten_composition','concentration','concentration_sensitivity','concentration_endpoint_sensitivity',
    'raw_domestic_heatmap','paired_domestic_heatmaps','paired_domestic_heatmap_support']


def checked_zip(path, directory):
    files={str(Path(directory.name)/p.relative_to(directory)):p for p in directory.rglob('*') if p.is_file()}
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None,'ZIP CRC failure')
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(files),'ZIP inventory differs')
        for name,p in files.items():require(z.read(name)==p.read_bytes(),'ZIP bytes differ: '+name)
    return len(files)


def build():
    summary=verify_analysis(SOURCE);layer=verify_acceptance();check_inventory(MAP)
    visual=json.loads((REVIEW/'visual_review_record.json').read_text())
    require(visual['assistant_visual_review_completed'] and not visual['submission_ready'],'Actual bounded visual review required')
    require(visual['source_manifest_sha256']==sha(SOURCE/'run_manifest.json'),'Visual review belongs to another export')
    acceptance=json.loads((ACCEPTANCE/'acceptance_record.json').read_text())
    first=pd.read_csv(SOURCE/'country_first_observed.csv',keep_default_na=False).sort_values('country_code').reset_index(drop=True)
    loc=pd.read_csv(MAP/'country_first_observed_locations.csv',keep_default_na=False)
    pd.testing.assert_frame_equal(first,loc[first.columns].sort_values('country_code').reset_index(drop=True))
    out=destination(OUT);stage=Path(tempfile.mkdtemp(prefix='.closure-reading-',dir=MODULE))
    for sub in ['tables','figures','provenance']: (stage/sub).mkdir()
    for name in TABLES:shutil.copy2(SOURCE/(name+'.csv'),stage/'tables'/(name+'.csv'))
    for p in sorted((SOURCE/'figures').iterdir()):
        if p.is_file():shutil.copy2(p,stage/'figures'/p.name)
    for ext in ['png','pdf','svg']:shutil.copy2(MAP/f'supplement_first_observed_map.{ext}',stage/'figures'/f'supplement_first_observed_map.{ext}')
    shutil.copy2(MAP/'country_first_observed_locations.csv',stage/'tables/country_first_observed_locations.csv')
    for name in ['summary.json','protocol.json']:shutil.copy2(SOURCE/name,stage/name)
    for source,name in [(ACCEPTANCE/'acceptance_record.json','acceptance_record.json'),
        (BUDGET/'summary.json','budget_summary.json'),
        (MODULE/'evidence_closure_confirmation_v1/summary.json','closure_proposal_history_summary.json'),
        (REVIEW/'visual_review_record.json','visual_review_record.json')]:
        shutil.copy2(source,stage/'provenance'/name)
    # Public metadata/statuses only: no fulltext, private review cards, credentials or raw paid responses.
    routes=pd.read_csv(ACCEPTANCE/'accepted_routes.csv')
    routes.drop(columns=['source_review']).to_csv(stage/'tables/candidate_routes.csv',index=False)
    links=[]
    for i,g in enumerate(layer['accepted_version_links'],1):
        for w in g['member_work_ids']:
            links.append({'version_group':i,'work_id':w,'representative_work_id':g['representative_work_id'],
                'new_in_this_closure':i>12,'label_propagation':False,'preprint_use_backfill':False})
    pd.DataFrame(links).to_csv(stage/'tables/accepted_version_members.csv',index=False)
    annual=pd.read_csv(SOURCE/'annual_counts.csv').query('publication_year>=2020').set_index('publication_year')
    diffusion=pd.read_csv(SOURCE/'annual_diffusion_counts.csv');periods=pd.read_csv(SOURCE/'period_counts.csv')
    profiles=pd.read_csv(SOURCE/'country_period_profiles.csv');g=pd.read_csv(SOURCE/'concentration.csv').set_index('year')
    support=pd.read_csv(SOURCE/'paired_domestic_heatmap_support.csv');support['AF_retained_fraction']=support.AF_known_common/support.AF_known_before
    support.to_csv(stage/'tables/support_retention_display.csv',index=False)
    endpoint=pd.read_csv(SOURCE/'concentration_endpoint_sensitivity.csv')
    coverage=pd.read_csv(SOURCE/'annual_source_coverage.csv')
    last=g.loc[2025];af25=coverage.query("year==2025 and group=='AF'").iloc[0];c25=coverage.query("year==2025 and group=='C'").iloc[0]
    N=int(annual.confirmed_af.sum());cumulative=int(diffusion.cumulative_countries.iloc[-1]);active=int(diffusion.active_countries.iloc[-1])
    require(N==summary['confirmed_AF_main']==16414,'Closure effect must be +3 to previous Figure1')
    derived_n=pq.ParquetFile(SOURCE/'derived_study_records.parquet').metadata.num_rows
    require(derived_n==4686894-summary['removed_version_records'],'Version denominator reconstruction differs')
    annual_table=md_table(['年份','确认AF研究','年度活跃国家/地区','当年新增','累计（含主期前）'],
        [(int(r.year),int(annual.loc[r.year,'confirmed_af']),int(r.active_countries),int(r.new_countries),int(r.cumulative_countries)) for r in diffusion.itertuples()])
    period_table=md_table(['时期','AF研究','国家可归属','国家缺失','散点实际绘制国家数'],
        [(r.period_name,int(r.af_studies),int(r.af_assigned),int(r.af_unknown),int(profiles[profiles.period_name.eq(r.period_name)].scatter_included.sum())) for r in periods.itertuples()])
    focus=profiles[profiles.country_code.isin(['US','CN','DE','GB']) & profiles.period_name.isin(['AF2 era','AF3 era'])]
    country_table=md_table(['时期','国家代码','全球已知AF份额(%)','本地适格研究AF比重(%)'],
        [(r.period_name,r.country_code,f'{r.global_known_af_percent:.2f}',f'{r.domestic_local_af_percent:.2f}') for r in focus.itertuples()])
    lookup=profiles.set_index(['period_name','country_code'])
    for p in ['AF2 era','AF3 era']:
        require(lookup.loc[(p,'US'),'global_known_af_percent']>lookup.loc[(p,'DE'),'global_known_af_percent'], 'Selected global comparison differs')
        require(all(lookup.loc[(p,c),'domestic_local_af_percent']>lookup.loc[(p,'US'),'domestic_local_af_percent'] for c in ['DE','GB']), 'Selected domestic comparison differs')
    map_summary=json.loads((MAP/'summary.json').read_text())
    unknown=acceptance['all765']['retained_unknown'];years=', '.join(str(int(v)) for v in annual.confirmed_af)
    (stage/'results_zh.md').write_text(f'''# Findings 1：地理参与扩大，产出仍比同期领域背景集中

作者核阅草稿。数字来自本包底表，采用明确接受的辅助证据层，不宣称独立人工双标金标准。[数值与视觉检查](release_checks.json)

## a：首次观察的地理参与持续扩大

2020–2025年计入{N:,}项已证实的AF下游采用研究。至2025年底，累计首次观察到{cumulative}个国家／地区参与，其中1个在2020年前已有记录；2025年度活跃{active}个与累计{cumulative}个不是同一指标。后期仍有新进入，新增数降低不等于技术推动作用减弱。[月度证据](tables/monthly_diffusion.csv)；[年度证据](tables/annual_diffusion_counts.csv)。

{annual_table}

发表事件呈现地理进入的观察顺序，不代表首次实际运行时间，也不能据发布节点推断因果效果。

## b：全球贡献份额与本地AF比重不是同一排序

三个阶段均先累计分数信用再计算比例，阶段长短不同，不把阶段总量当成相同时间长度的增长率。

{period_table}

在AF2及AF3两个阶段，美国全球已知AF信用份额均高于德国，但德国、英国在本地所采领域的AF比重均高于美国。中国的全球份额和国内比重变化应分别理解，不能将它们直接称为技术能力或采用意愿变化。[完整国家×阶段表](tables/country_period_profiles.csv)。

{country_table}

最早阶段仅37项研究、4项国家缺失，国家排序需谨慎解释。

## c：数量增长与信用分配并存

主期研究总数由旧NHB基础16,341变为上一Figure1版16,411，再变为本版{N:,}；本轮增加3项，分别发表于2023、2024和2025年。2020年仍为11项。最早预印本只有在独立确认采用时才参与该成员自身国家的首次观察，不与正式版在年度产出中重复计数。[年度数量](tables/annual_counts.csv)；[版本成员](tables/accepted_version_members.csv)。

2025年实际前五国占已知归属AF信用{100*last.af_top5:.2f}%，实际前十国占{100*last.af_top10:.2f}%。该分母排除{int(af25.unknown_n)}项国家缺失研究（{100*(1-af25.coverage):.2f}%），不同于主图包含Unknown的100%柱。主图固定十国按全2020–2025信用选择，每年不换名单，不能称为每年实际前十。[全部国家信用](tables/annual_country_credits.csv)；[固定十国构成](tables/fixed_ten_composition.csv)。

## d：集中度期末低于期初，但仍高于背景

固定227个国家／地区并保留零信用国家，AF Gini由2020年的{g.loc[2020,'af_gini']:.4f}降至2025年的{last.af_gini:.4f}，2025年筛查阴性背景为{last.comparator_gini:.4f}；差值{last.delta_gini:.4f}，整篇研究重抽样的条件95%区间为[{last.delta_lower:.4f}, {last.delta_upper:.4f}]。这支持观察数据中AF产出比本地同期领域背景更集中，不证明AF造成国家机会不平等。[集中度](tables/concentration.csv)。

相对差非逐年单调下降；2023、2025较前一年略增。2021及2022起算的端点敏感性另列，不以2020小样本单一起点强推趋势，也不冒充已控制跨年团队依赖的正式检验。[端点敏感性](tables/concentration_endpoint_sensitivity.csv)。

## 覆盖与结论边界

共同支持保留全部已知国家AF研究，但背景适格研究保留率2020年为{100*support.iloc[0].ALL_retained_fraction:.2f}%，2025年为{100*support.iloc[-1].ALL_retained_fraction:.2f}%；匹配热图不是全范围原始比例的替代。2025年AF国家归属覆盖{100*af25.coverage:.2f}%，筛查阴性背景{100*c25.coverage:.2f}%，bootstrap不消除差异性缺失。[两侧支持](tables/support_retention_display.csv)；[来源覆盖](tables/annual_source_coverage.csv)。

765项补查候选中74项采用、159项明确背景/讨论等非采用、1项原始平台排除、{unknown}项未知。未知不混入筛查阴性背景；此次处置与接受已冻结，但不是全球召回或版本去重完备性证明。其他NHB章节未重算。[候选分流](tables/candidate_routes.csv)；[数据流程](data_flow_zh.md)。

[入口](README_zh.md) · [方法](methods_zh.md) · [图注](captions_zh.md) · [读者信息](reader_information_zh.md)
''',encoding='utf-8')
    methods=(SOURCE/'methods_zh.md').read_text().replace('# Figure 1 新版Methods草稿','# Figure 1：中文Methods正文')
    methods+=f'''
## 本轮证据收尾、接受及费用披露

原765项补查中179项非未知决定及12组版本关系保持不变，对剩余586项以原提示词、schema及采用定义进行A/B独立评审，再将缺有效结果、核心分歧、未知或证据例外送C。observed_actions差异不作为核心分流条件。556项适格（154正文证据包、402摘要包）发送A/B；28项证据不足、2项超大包不强制调用。C复核516项。真实发送A/B/C为556/556/516，共1,628次；有效响应525/468/482与本地格式修复分开，不把接受后的语义判定记为新增API成功。

证据扩充及清理保留版本与精确标识符来源；Crossref参考关系是元数据，不伪装成正文使用证据。原R/E框架不变，但增量上下文不是旧全量证据包的逐字复制。初始HTTP及验证重试设为0属于费用控制，不是放宽采用标准。

A请求旧名称deepseek-v4-flash，服务端转至V4.1-Flash已经用户接受，实际reported_model/system_fingerprint另存，不声称权重版本完全相同。B为glm-5.3-flash/high，C为OpenRouter openai/gpt-5.6-luna/xhigh。核查范围是冻结证据包、已定位AF语境、失败阳性响应和重点完整方法/结果/讨论，不是每篇全文及不可见补充材料逐字独立人工审阅。TmAlphaFold官方溯源另存，非模型输入内证据。

用户确认本轮3项采用、52项非采用、531项保留未知及3组版本身份关系；新接受层共74/159/1/531项及15组特定版本关联。新3组以正式版为代表、不传播标签、不倒填早期使用。8项arXiv修订时间风险保留；其他关系线索未自动归并。[接受记录](provenance/acceptance_record.json)；[候选处置](tables/candidate_routes.csv)；[版本成员](tables/accepted_version_members.csv)。

研究证据层的“收尾”指已执行、逐项处置、接受及审计冻结，不指未知全部消失、召回完备或新人工金标准。A官方账户余额减少¥8.68，可能含同期其他使用；B保守峰值无缓存加余量上界¥4.8346，不是实际账单；C逐请求报告$1.36329925。总发送低于授权5,274次上限，本轮整合、制图及打包没有新增付费/公开数据请求。[费用审计](provenance/budget_summary.json)。

## 图形呈现与软件

三阶段散点采用共同线性主轴与共同范围放大图，不改变分子、分母或样本；国家标签按全期规则固定。Gini完整0–1轴另列，未知以斜线/灰色或NA明确区分。

首次观察地图沿用已归档示意坐标，经逐代码日期核对与新版完全一致：{map_summary['located']}/{map_summary['country_codes']}代码可定位，未定位{', '.join(map_summary['unmapped'])}仍保留统计。坐标不是机构实址；统一陆地轮廓不表达主权判断。使用既有[Natural Earth公共领域底图](https://www.naturalearthdata.com/about/terms-of-use/)，没有重新下载地图。[坐标及来源](tables/country_first_observed_locations.csv)。

科学可视化和科学写作技能用于实际图片检查、同轴/分母审计、未知保留及结果—证据对应，不代替作者科学责任。软件流程参考：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. [doi:10.48550/arXiv.2609.00065](https://doi.org/10.48550/arXiv.2609.00065)，2026-10-09核对最新arXiv记录（当前v2，无版本后缀引用）。这是软件工作流说明，不是结果认证。

[日期审计](tables/date_audit.csv) · [时期分母](tables/period_counts.csv) · [国家信用](tables/annual_country_credits.csv) · [共同支持](tables/support_retention_display.csv) · [协议](protocol.json) · [入口](README_zh.md)
'''
    (stage/'methods_zh.md').write_text(methods,encoding='utf-8')
    (stage/'captions_zh.md').write_text(f'''# Figure 1图注与替代文本

**Figure 1｜地理参与扩大，但AF产出仍相对集中。**

**a，** 2020–2025月度累计首次观察国家/地区折线与当月新增柱（分开上下共用时间轴），主期前1个代码保留，期末累计{cumulative}。虚线为2021年7月AF2代码/AFDB及2024年5月AF3发布月份，不是实际执行日期或因果断点。

**b，** Pre-AF2 release（2020-01至2021-06）、AF2 era（2021-07至2024-04）、AF3 era（2024-05至2025-12）三阶段全球已知AF信用份额与本地所采领域全部适格信用中的AF比重。阶段内累计后取比例；1/k分数计数，固定点大小，共同线性主轴及共同放大范围。各期研究总量及实际绘制国家数见[时期表](tables/period_counts.csv)与[逐国表](tables/country_period_profiles.csv)。两个百分比的分母不同，不画45度参照线；无参与国家不堆在原点。

**c，** 年度AF研究量及国家信用100%构成，年度总数为{years}。全期2020–2025信用选取固定十国{', '.join(summary['fixed_ten'])}，跨年不换名单，Other与白底斜线Unknown保留，不把未知重摊；实际前十的已知归属份额与该柱的全部研究分母不同。

**d，** 固定227国家/地区含零的AF与筛查阴性背景Gini，以及ΔGini=AF−背景。1000次整研究重抽样的条件95%区间不涵盖漏检、标签错误、差异性国家缺失及跨年团队依赖。上图纵轴截取，完整0–1轴见补图；2020仅11项，不据此提出强趋势/因果判断。

**替代文本：** 四面板依次显示地理进入时间、阶段国家位置、年度总量与国家信用分配、集中度及相对差。累计参与增加，AF集中度期末低于期初且仍高于背景；相对差非逐年单调下降。未知归属与不可用分母分别显示，全部精确数字见底表。

## 补图/表

- [S1 年度活跃/新增/累计](figures/supplement_annual_country_diffusion.png)：区别三种覆盖指标。
- [S2 首次观察地图](figures/supplement_first_observed_map.png)：国家代码示意点，未定位不从统计中删除。
- [S3 全范围原始国内率](figures/supplement_raw_domestic_all_countries.pdf)：全部227代码，灰色不可用不是0。
- [S4 共同支持成对热图](figures/supplement_paired_domestic_all_countries.pdf)：左右相同支持，全部页共同色标；[两侧保留率](tables/support_retention_display.csv)。
- [S5 Gini完整轴](figures/supplement_gini_full_axis.png)：相同估计/区间，不重算统计。
- [S6 替代集中指标/设定](tables/concentration_sensitivity.csv)及[端点敏感性](tables/concentration_endpoint_sensitivity.csv)：不是所有设定都提供区间，不统一称为稳健检验。

[主图](figures/figure1_revised_a_d.png) · [入口](README_zh.md) · [读者信息](reader_information_zh.md)
''',encoding='utf-8')
    (stage/'reader_information_zh.md').write_text(f'''# 面板—读者信息—方法—发现一一对应

| 面板 | 读者应获得的信息 | 当前发现 | 方法及呈现修改原因 | 证据 |
|---|---|---|---|---|
| a | 何时首次观察进入，扩展到多少国家 | 累计{cumulative}；2025活跃{active}，指标不混用 | 年改月；累计/新增分开共轴，保留历史参与，不加机制箭头 | [月度](tables/monthly_diffusion.csv)、[年度](tables/annual_diffusion_counts.csv) |
| b | 全球贡献与本地AF比重是否同一排序 | 美全球份额高，德/英国内比例高 | 三时期共轴固定点；共尺度放大图解拥挤，不改用推断回归 | [逐国时期](tables/country_period_profiles.csv)、[分母](tables/period_counts.csv) |
| c | 产出增加如何分配到国家 | 主期{N:,}；2025实际前十占已知信用{100*last.af_top10:.2f}% | 总量与真100%信用分开；固定全期十国，未知不摊派 | [数量](tables/annual_counts.csv)、[构成](tables/fixed_ten_composition.csv) |
| d | 集中水平及相对背景差如何变化 | 2025 AF{last.af_gini:.4f}、背景{last.comparator_gini:.4f}、差{last.delta_gini:.4f}；非单调下降 | 水平/差上下分开；整研究bootstrap、固定零国家；完整轴另列 | [集中度](tables/concentration.csv)、[端点](tables/concentration_endpoint_sensitivity.csv) |
| 国内率补图 | 构成匹配是否改变国内比重的观察 | 原始全范围与共同支持分别可查 | 左右支持一致、NA不填0，明确假想匹配分母及两侧保留率 | [配对](tables/paired_domestic_heatmaps.csv)、[支持](tables/support_retention_display.csv) |
| 地图补图 | 首次观察的地理顺序 | {map_summary['located']}/{map_summary['country_codes']}可定位；未定位仍统计 | 仅示意国家代码，不虚构机构地址 | [坐标](tables/country_first_observed_locations.csv) |

这些是描述性信息，不能推断AF导致不平等、发布导致进入、国家科研能力或个人真实领导责任。未知、差异性覆盖及版本未穷尽核实仍是结果边界。

[主图](figures/figure1_revised_a_d.png) · [Results](results_zh.md) · [Methods](methods_zh.md) · [图注](captions_zh.md) · [原方案对照](plan_comparison_zh.md) · [入口](README_zh.md)
''',encoding='utf-8')
    (stage/'plan_comparison_zh.md').write_text(f'''# 原Figure1修订方案：满足、修改与未消除的限制

## 已满足

a月度扩散→b三阶段位置→c年度分配→d集中度及相对差；统一发表月份、累计/活跃区分、全球/国内分母区分、阶段累计后取比例；固定227零值国家、1000整研究bootstrap、Unknown信用保留；固定全期十国、共尺度放大图、2021/2022起点端点敏感性、完整Gini轴、全范围及相同支持热图、逐国CSV及中文正文/图注/读者信息。本轮586项处置和3组版本关系已接受，未改变原采用定义。

## 有依据的修改

- 原计划2020 n=10及主期16,341，按接受层实际重算为11及{N:,}；上一Figure1为16,411，本次新增3。不是为了增加早期样本而放宽阈值。
- 固定十国采用全期规则，不逐年换组；d内嵌改上下子图以提高可读性。
- a新增柱与累计曲线改同时间轴上下分开，不混叠双轴；b共享局部放大，保持共同线性主轴。
- 地图{map_summary['located']}/{map_summary['country_codes']}定位，未定位保留，不填邻国；首次观察日期与新版完全一致，缓存图可复用。
- 阶段边界是发表月份规则，不是实际所用模型版本或因果事件。

## 尚不能等同满足的研究证据保证

531项候选仍未知；所有记录已获处置，不表示每篇全文/不可见补充材料都经独立人工逐字核查。不宣称召回完备、版本穷尽去重或独立人工金标准。条件bootstrap不覆盖漏收/误标/差异性缺失/跨年团队依赖，不提供正式因果效果或机会不平等机制判断。

## 与NHB02–05的版本关系

本包仅更新Figure1独立研究层。旧NHB02–05仍以16,341主期基础为准，未覆盖任何历史输出。合写全篇时不能只替换总数而默认机构/活动/随访/领导/引用分析也已更新；若决定传播本接受层，须单独版本化重算相应下游。

[原方案存档](figure1_original_revision_plan.md) · [数据流程](data_flow_zh.md) · [入口](README_zh.md)
''',encoding='utf-8')
    by_year=routes.groupby(['publication_year','af_use_label','adoption_eligible']).size().reset_index(name='work_records')
    by_year.to_csv(stage/'tables/candidate_routes_by_year.csv',index=False)
    new=layer['decisions'];positives=[r for r in new if r['work_id'] in {'W4318317763','W4393581939','W4415354285'}]
    positive_table=md_table(['work_id','年份','R/E','动作边界'],[(r['work_id'],r['publication_year'],r['relevance_level']+'/'+r['evidence_level'], '、'.join(r['observed_actions'])) for r in positives])
    (stage/'data_flow_zh.md').write_text(f'''# 数据处理流程与数量总览：证据收尾版

## 研究总体及版本单位

冻结OpenAlex主表6,046,663条 → article/review/preprint、2015–2025基础4,686,896条 → 原已接受两组关联后4,686,894研究单位 → Figure1本次独立接受层15组特定关联、移除15个重复成员 → {derived_n:,}研究单位。主体数据于2026年4月3日所在周下载完成，不是本轮另行下载整个OpenAlex。旧复核库29,127条和原final不覆盖。

## 新召回与判定

旧筛查阴性范围中扩展关键词及AF1遗漏种子引用，召回826项线索，其中765项满足文献类型条件、61项其他类型。本阶段是跨年份补查，不只2020–2021；逐年处置见[年度候选分流](tables/candidate_routes_by_year.csv)。

765项此前为71采用/107非采用/1原始平台/586未知。本轮586项中556适格包进入A/B（154正文、402摘要），28证据不足、2超大包保留；C复核516项。A/B/C真实发送556/556/516，有效525/468/482；10条本地机械格式候选单列，不是新增API成功。原R/E、提示词、schema及两个yes条件沿用，observed_actions不作为核心分流条件。

本轮接受3采用、52非采用、531未知 → 全765项为**74采用、159非采用、1原始平台排除、531未知**。保留旧179非未知决定；15组关系=旧12+新增3，标签不传播、预印本时间不倒填。候选工作记录数与去重后的研究单位数不同，531不能直接当作正文分析中的未知研究总数。[逐项状态](tables/candidate_routes.csv)；[接受记录](provenance/acceptance_record.json)。

{positive_table}

三项均没有新增“运行AF/ColabFold”判定；TmAlphaFold不等于已证实下载了AF坐标。

## 主期分子与时期构成

旧16,341 → 首轮新增71确认记录减1正例重复研究=16,411 → 本轮新增3=**{N:,}**。新增3组关系移除的是未独立确认采用的预印本，正式版早已在分子中，不额外增加或减少已确认研究。

{annual_table}

{period_table}

主期前2019年4项用于历史首次观察，不并入2020–2025主期分子。74是补查候选的采用记录数，净增73是相对旧版的采用研究单位数，不与{N:,}混淆。三阶段是发表时期，不是论文所用AF版本。

## 分母、缺失与费用

765项候选全部从筛查阴性比较组移出，即使未知也不当作未使用；国内率分母为本地采集领域全部适格研究，非国家全部科学论文。国家信用按1/k，国家缺失留Unknown。2025年AF共{int(af25.n):,}项，{int(af25.assigned_n):,}可归属、{int(af25.unknown_n)}未知；累计{cumulative}国家代码与2025活跃{active}不同。

总付费发送1,628（上限5,274）；A账户减少¥8.68（不保证全归属本任务）、B保守上界¥4.8346非实际账单、C请求报告$1.36329925。本次接受/重算/图形/ZIP没有新付费请求。[预算审计](provenance/budget_summary.json)。

未知531仍需在限制中披露，但不再为消灭未知自动重试。这是有边界的证据处理收尾，不是全球召回/去重完备性或新人工金标准。

[Results](results_zh.md) · [Methods](methods_zh.md) · [方案对照](plan_comparison_zh.md) · [入口](README_zh.md)
''',encoding='utf-8')
    shutil.copy2(PLAN,stage/'figure1_original_revision_plan.md')
    (stage/'README_zh.md').write_text(f'''# Figure1 revision：研究证据收尾版阅读入口 v3

用户已接受本轮586项处置和3组版本身份关系，新接受层、重算、数值重建、图片检查及便携阅读包完成。**主期{N:,}项、2020年11项、累计{cumulative}国家/地区；补查候选531项未知仍保留。** 这是作者核阅草稿，不是独立人工金标准或期刊提交批准。

- [主图PNG](figures/figure1_revised_a_d.png) · [PDF](figures/figure1_revised_a_d.pdf) · [SVG](figures/figure1_revised_a_d.svg)
- [中文Results及明确findings](results_zh.md) · [中文Methods](methods_zh.md)
- [图注](captions_zh.md) · [逐面板读者信息/方法修改](reader_information_zh.md)
- [数据流程和数量总览](data_flow_zh.md) · [原方案满足/修改/限制](plan_comparison_zh.md)
- [年度地理覆盖](figures/supplement_annual_country_diffusion.png) · [首次观察地图](figures/supplement_first_observed_map.png)
- [原始国内率PDF](figures/supplement_raw_domestic_all_countries.pdf) · [同支持配对热图PDF](figures/supplement_paired_domestic_all_countries.pdf)
- [Gini完整轴](figures/supplement_gini_full_axis.png) · [检验记录](release_checks.json) · [声明—证据对应](claim_evidence_registry.json)

所有图片、汇总CSV及正文文件位于本包，相对链接解压后可跳转。不包含受许可限制正文、私有审阅证据卡、大型逐研究Parquet或API密钥。

**旧final、旧阅读ZIP和NHB02–05均未覆盖。** 本包Figure1与旧章节的研究基础不同，整稿采用前如决定统一全部新证据，需另行版本化传播和重算，不能仅修改全篇总数。
''',encoding='utf-8')
    registry={'submission_ready':False,'author_review':'pending','verification_scope':'assistant numeric reconstruction and user-accepted decisions; not independent human gold',
        'claims':{'R-F1-01':['tables/monthly_diffusion.csv','tables/annual_counts.csv'],
            'R-F1-02':['tables/period_counts.csv','tables/country_period_profiles.csv'],
            'R-F1-03':['tables/annual_country_credits.csv','tables/fixed_ten_composition.csv'],
            'R-F1-04':['tables/concentration.csv','tables/concentration_endpoint_sensitivity.csv'],
            'R-F1-05':['tables/support_retention_display.csv','tables/annual_source_coverage.csv'],
            'D-F1-01':['tables/candidate_routes.csv','provenance/acceptance_record.json']},
        'numeric_facts':{'confirmed_AF_main':N,'year2020':11,'cumulative_countries':cumulative,'active2025':active,
            'candidate_adopted_records':74,'candidate_unknown_records':531,'derived_study_units':derived_n,
            'annual_confirmed_af':{str(y):int(r.confirmed_af) for y,r in annual.iterrows()}}}
    write_json(stage/'claim_evidence_registry.json',registry)
    checks={'numeric_reconstruction':'PASS','acceptance_reconstruction':'PASS','new_version_groups':3,'all_version_groups':15,
        'unknown_not_nonuse':True,'visual_review_record':'provenance/visual_review_record.json',
        'source_first_observation_matches_cached_map':True,'paid_API_requests_this_stage':0,'public_data_requests_this_stage':0,
        'other_NHB_sections_recomputed':False,'old_database_changed':False,'independent_human_gold':False,'submission_ready':False,
        **registry['numeric_facts'],'portable_local_links_checked':0}
    write_json(stage/'release_checks.json',checks)
    checks['portable_local_links_checked']=links_ok(stage)
    # Only the unpublished generated checks are updated before its final manifest.
    (stage/'release_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copy2(Path(__file__),stage/'build_closure_reading_package_v3.py')
    write_json(stage/'run_manifest.json',{'schema':'figure1-evidence-closure-reading-v3','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'inputs':[pin(SOURCE/'run_manifest.json'),pin(ACCEPTANCE/'run_manifest.json'),pin(MAP/'run_manifest.json'),
            pin(REVIEW/'visual_review_record.json'),pin(BUDGET/'run_manifest.json'),pin(PLAN,PLAN.parent)],
        'outputs':inventory(stage),'executed_code':pin(Path(__file__)),'paid_api_calls':0})
    check_inventory(stage);stage.rename(out)
    archive=out.with_suffix('.zip');require(not archive.exists(),'Archive exists; choose new version')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,Path(out.name)/p.relative_to(out))
    n=checked_zip(archive,out)
    print('Closure reading package/relative links/ZIP bytes: PASS;',n,'files;',checks['portable_local_links_checked'],'links;',archive.stat().st_size,'bytes')
    print('Reading entrance:',out/'README_zh.md'); print('ZIP:',archive)


if __name__=='__main__':build()
