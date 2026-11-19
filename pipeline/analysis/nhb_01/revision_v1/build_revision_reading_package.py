"""Assemble verified Figure1-only portable results, methods, panels and supplements."""
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote
import pandas as pd
import fetch_public_evidence as e
from local_recall import MODULE, PLAN, destination, pin, require, sha, write_json
from verify_revised_country_bundle import verify

SOURCE=MODULE/'figure1_revision_final_v1'
FIGURES=MODULE/'figure1_revision_figures_v3'
MAP=MODULE/'first_observed_map_v2'
OUTPUT=MODULE/'figure1_revision_reading_package_v2'

def check_inventory(directory):
    m=json.loads((directory/'run_manifest.json').read_text())
    require(e.inventory(directory)==m['outputs'],'Presentation inventory differs: '+str(directory))

def links_ok(directory):
    checked=0
    for path in directory.rglob('*.md'):
        for value in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            value=value.strip('<>').split('#',1)[0]
            if not value or re.match(r'https?://',value):continue
            target=(path.parent/unquote(value)).resolve()
            require(target.is_relative_to(directory.resolve()) and target.is_file(),f'Broken/nonportable link: {path.name}: {value}')
            checked+=1
    return checked

def md_table(headers,rows):
    return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in rows)

def build():
    summary=verify(SOURCE);require(summary['formal_revised_result'],'Formal accepted results required')
    check_inventory(FIGURES);check_inventory(MAP)
    out=destination(OUTPUT);stage=Path(tempfile.mkdtemp(prefix='.figure1-reading-package-',dir=MODULE))
    (stage/'tables').mkdir();(stage/'figures').mkdir()
    names=['monthly_diffusion','country_first_observed','date_audit','annual_counts','annual_country_coverage',
        'annual_diffusion_counts','period_counts','country_period_profiles','annual_country_credits','annual_source_coverage',
        'fixed_ten_composition','concentration','concentration_sensitivity','concentration_endpoint_sensitivity',
        'raw_domestic_heatmap','paired_domestic_heatmaps','paired_domestic_heatmap_support']
    for name in names:shutil.copy2(SOURCE/(name+'.csv'),stage/'tables'/(name+'.csv'))
    for path in (FIGURES/'figures').iterdir():shutil.copy2(path,stage/'figures'/path.name)
    for ext in ['png','pdf','svg']:shutil.copy2(MAP/f'supplement_first_observed_map.{ext}',stage/'figures'/f'supplement_first_observed_map.{ext}')
    shutil.copy2(MAP/'country_first_observed_locations.csv',stage/'tables/country_first_observed_locations.csv')
    for name in ['summary.json','protocol.json']:shutil.copy2(SOURCE/name,stage/name)
    annual=pd.read_csv(stage/'tables/annual_counts.csv').query('publication_year >= 2020')
    diffusion=pd.read_csv(stage/'tables/annual_diffusion_counts.csv')
    d=pd.read_csv(stage/'tables/concentration.csv').set_index('year');last=d.loc[2025]
    profiles=pd.read_csv(stage/'tables/country_period_profiles.csv');periods=pd.read_csv(stage/'tables/period_counts.csv')
    support=pd.read_csv(stage/'tables/paired_domestic_heatmap_support.csv')
    support['AF_retained_fraction']=support.AF_known_common/support.AF_known_before
    support.to_csv(stage/'tables/paired_domestic_heatmap_support.csv',index=False)
    map_summary=json.loads((MAP/'summary.json').read_text())
    require(int(annual.confirmed_af.sum())==summary['confirmed_AF_main']==16411,'Expected accepted main count')
    require(int(diffusion.cumulative_countries.iloc[-1])==143,'Monthly/yearly geography mismatch')
    require(all(support.AF_retained_fraction.eq(1)),'Unexpected AF support loss')
    lookup=profiles.set_index(['period_name','country_code'])
    def pair(period,code):
        r=lookup.loc[(period,code)];return f'{r.global_known_af_percent:.2f}%／{r.domestic_local_af_percent:.2f}%'
    annual_table=md_table(['年份','确认AF研究','年度活跃国家／地区','当年新增','累计（含主期前1个）'],
        [(int(r.year),int(annual.set_index('publication_year').loc[r.year,'confirmed_af']),int(r.active_countries),int(r.new_countries),int(r.cumulative_countries)) for r in diffusion.itertuples()])
    period_table=md_table(['时期','确认AF研究','已知国家归属','未知国家归属','实际绘制国家数'],
        [(r.period_name,int(r.af_studies),int(r.af_assigned),int(r.af_unknown),int(profiles.query('period_name == @r.period_name').scatter_included.sum())) for r in periods.itertuples()])
    (stage/'results_zh.md').write_text(f'''# Findings 1：地理参与扩大，但产出仍较集中

这是可用于正文修改的中文结果草稿；采用已接受的辅助证据层，不宣称独立人工金标准。所有数字来自本包CSV，而非从图估计。

## a：首次观察的地理参与扩大

截至2025年底，本地证据中累计观察到143个国家／地区参与已证实的AF研究，其中1个在2020年前已有记录。2020–2025年年度活跃国家／地区分别为7、52、88、108、111及128；年度活跃128与累计143不是同一个指标。新增进入分别为6、45、40、25、11及15个，后期仍有新增，不能把新增数减少直接解释为技术驱动力减弱。月度曲线显示扩展的时间顺序，不证明发布事件导致进入。[证据](tables/monthly_diffusion.csv)；[年度覆盖](tables/annual_diffusion_counts.csv)。

## b：全球贡献份额与本地研究中的AF比重不同

三时期均按发表月份切分，期间长短不同；不能直接把阶段总量当成同时间长度的增长率。

{period_table}

在AF2时代，美国的全球已知AF信用份额／本地AF比重为{pair('AF2 era','US')}，德国为{pair('AF2 era','DE')}，英国为{pair('AF2 era','GB')}。到AF3时代，对应为美国{pair('AF3 era','US')}、德国{pair('AF3 era','DE')}、英国{pair('AF3 era','GB')}。美国全球份额最大，但德国、英国在本地采集领域的AF比重更高，说明两种指标不是同一个排序。

中国的全球份额／国内比重由AF2时代的{pair('AF2 era','CN')}变为AF3时代的{pair('AF3 era','CN')}。这一构成变化是观察关联，不是技术能力或采用意愿的直接测量。早期阶段只有37项研究，且国家归属缺失4项，其散点和国家排序应谨慎解读。[逐国分子、分母及精确比例](tables/country_period_profiles.csv)。

## c：总量增长与份额分配并存

新增证据接受及12组版本关联后，主期计入16,411个研究单位，比旧版16,341增加70（71个新增确认记录减1个已确认重复研究）。2020年度一致代表为11，而非原计划中的10；CopulaNet早期预印本保留自身国家首次观察，但年度产出以2021代表计数，不能在两年各计一次。

{annual_table}

2025年实际前五国占已知归属AF信用{last.af_top5*100:.2f}%，实际前十国占{last.af_top10*100:.2f}%。这里的已知归属分母排除253项国家缺失研究（253／5,572，4.54%），与主图包含Unknown的100%构成柱不同；不能把74.44%直接看作彩色区域高度。主图固定十国按全期2020–2025信用选取，逐年不换名单，也不称其为每年实际前十。[年度数](tables/annual_counts.csv)；[全部国家信用](tables/annual_country_credits.csv)；[固定十国构成](tables/fixed_ten_composition.csv)。

## d：集中度期末低于期初，但仍高于背景

在固定227个国家／地区且保留零信用国家的口径下，AF Gini从2020年的{d.loc[2020,'af_gini']:.4f}降至2025年的{last.af_gini:.4f}，同期筛查阴性背景2025年为{last.comparator_gini:.4f}。2025年ΔGini为{last.delta_gini:.4f}，整篇研究重抽样条件95%区间为[{last.delta_lower:.4f}, {last.delta_upper:.4f}]。这支持“观察到的AF产出仍比本地同期领域背景更集中”，不证明AF造成国家机会不平等。

ΔGini从2020年的{d.loc[2020,'delta_gini']:.4f}总体缩小，但2023和2025较前一年略增，因此不能写“逐年持续收敛”。2021及2022起算、至2024／2025终点的AF Gini与相对差端点变化均为负，方向不只依赖2020小样本；这是条件描述性敏感性，不是已控制跨年研究团队依赖的正式趋势检验。[Gini及HHI／头部份额](tables/concentration.csv)；[端点敏感性](tables/concentration_endpoint_sensitivity.csv)。

## 证据覆盖与结论边界

共同支持热图保留全部国家已知AF研究，但适格背景的保留率2020年仅42.29%，2025年98.44%；2020年构成调整不能替代全范围原始比例。不同组国家归属覆盖也不同：2025年AF为95.46%，筛查阴性背景为78.59%。bootstrap不消除这类覆盖偏差。[共同支持两侧保留率](tables/paired_domestic_heatmap_support.csv)；[来源覆盖](tables/annual_source_coverage.csv)。

765个新增候选中，71个接受为yes／yes、107个非采用、1个原始平台排除、586个保留未知。未知没有作为非使用证据，也没有并入筛查阴性背景。版本关联只处理本次接受的12组及此前已接受关联；其余未核实线索、原有标签误差仍可能影响结果。本包不声称完整去重或召回完整。

[返回总入口](README_zh.md) · [方法](methods_zh.md) · [图注](captions_zh.md) · [原方案对照](plan_comparison_zh.md)
''',encoding='utf-8')
    methods=(SOURCE/'methods_zh.md').read_text().replace('# Figure 1 新版Methods草稿','# Figure 1：中文Methods正文')
    methods+='''
## 本次呈现修订及软件记录

三时期散点主轴共用线性范围；为解决低值重叠，另设同为全球份额0–10%、本地比重0–3.5%的局部放大图。放大图重复展示同一批点，不改分子、分母或样本。十国标签按全期规则固定，未按有趣结果选择。

首次观察年份补图用国家代码对应的示意坐标，并非论文实际机构地理坐标。优先使用本地已归档World Bank首府坐标，无坐标时仅按Natural Earth精确ISO2匹配的多边形内部点补充；不以名称近似或邻国代填。143个已观察代码中142个可定位，RE（留尼汪）在机器可读表中保留但未绘制。底图为统一陆地轮廓，不按争议边界着色，不表达主权判断。Natural Earth底图为[公共领域数据](https://www.naturalearthdata.com/about/terms-of-use/)，本轮一次公开底图请求；未重新请求OpenAlex，不读取项目模型密钥，不调用付费LLM。765篇证据补查与地图请求分别记账。

辅助工具的科学可视化／写作技能用于共轴和分母审计、未知项保留、结果—证据链接以及条件推断边界；工具输出由作者负责核查。软件工作流参考：Kassis et al. (2026), *Scientific Skills: An Open-Source Library for Research Agents*, [arXiv](https://doi.org/10.48550/arXiv.2609.00065)。这不是结果真实性认证或稿件作者署名。

### 可点击底表

- [日期及精度标志](tables/date_audit.csv)
- [月份／首次观察](tables/monthly_diffusion.csv) · [国家首次观察清单](tables/country_first_observed.csv)
- [阶段分母及覆盖](tables/period_counts.csv) · [国家×阶段](tables/country_period_profiles.csv)
- [年度国家权重](tables/annual_country_credits.csv) · [未知归属及来源覆盖](tables/annual_source_coverage.csv)
- [Gini／HHI／头部份额](tables/concentration.csv) · [构成及计数敏感性](tables/concentration_sensitivity.csv)
- [共同支持保留率](tables/paired_domestic_heatmap_support.csv) · [成对国内热图](tables/paired_domestic_heatmaps.csv)

[返回入口](README_zh.md) · [结果](results_zh.md) · [逐面板信息](reader_information_zh.md)
'''
    (stage/'methods_zh.md').write_text(methods,encoding='utf-8')
    (stage/'captions_zh.md').write_text('''# 图注

## Figure 1. 地理参与扩大，但AF产出仍比同期领域背景集中

**a，** 2020–2025月度首次观察：累计国家／地区折线与当月新增柱；保留主期前1个已有参与代码，2025年末累计143。虚线为2021年7月AF2代码／AFDB及2024年5月AF3发布月份，不是因果断点或实际运行时间。

**b，** Pre-AF2 release（2020-01至2021-06）、AF2 era（2021-07至2024-04）和AF3 era（2024-05至2025-12）国家位置。横轴为全球已知归属AF分数信用份额，纵轴为AF信用／本地所采领域同期全部适格信用。按1/k计数，固定点大小、共同线性主轴；三个放大图使用相同范围。仅绘制AF信用>0且分母可用的国家，分别14、123、134个；没有参与国家不堆到原点。标题总研究数包含国家缺失项；国家归属覆盖另见补表。不存在有统计含义的45度等值线。

**c，** 年度确认研究总量及国家信用100%构成，2020–2025分别为11、393、2,389、3,903、4,143、5,572。固定十国US、CN、DE、GB、FR、JP、CA、IT、ES、IN依据全期信用选择，Other为其余已知国家，Unknown白底斜线为未知归属信用。未知不重摊。

**d，** 固定227国家／地区且保留零值的Gini，及ΔGini=AF−筛查阴性背景。阴影／误差线为1000次整篇研究重抽样的条件95%区间，不涵盖漏检、标签误差、差异性国家缺失及跨年团队依赖。上图纵轴局部截取；完整0–1轴见补图。2020仅11研究，不能据此强推趋势或因果效果。

## 补充材料

- [S1 年度活跃／新增／累计](figures/supplement_annual_country_diffusion.png)：三个不同覆盖指标，累计包含主期前参与。
- [S2 首次观察年份示意地图](figures/supplement_first_observed_map.png)：定位142／143代码，RE缺坐标而不绘制，仍计入全部统计；点非机构实际位置。首次观察非首次真实采用。
- [S3 全范围原始国内比例](figures/supplement_raw_domestic_all_countries.pdf)：227国家代码×年度；灰色为分母不可用，不是0。
- [S4 共同支持成对热图](figures/supplement_paired_domestic_all_countries.pdf)：同年×类型×主要子领域共同支持；左侧原始，右侧按AF构成匹配的假想国内分母。左右相同支持，全部分页共同色标。两侧保留率见[补表](tables/paired_domestic_heatmap_support.csv)。
- [S5 Gini完整轴](figures/supplement_gini_full_axis.png)：相同数值和条件区间，不重算统计。
- [S6 集中度替代设定及端点敏感性表](tables/concentration_sensitivity.csv)：全文计数有条件区间；扩展背景、历史国家集合与AF构成匹配仅点估计，不能统一称有稳健区间。

[主图](figures/figure1_revised_a_d.png) · [入口](README_zh.md) · [逐面板读者信息](reader_information_zh.md)
''',encoding='utf-8')
    (stage/'reader_information_zh.md').write_text('''# 面板—读者信息—方法—证据对应

| 面板 | 读者应获得的信息 | 已核验发现 | 修改及原因 | 底表 |
| --- | --- | --- | --- | --- |
| a | 地理首次观察何时扩大、扩展到多少国家 | 累计143；2025活跃128，不混淆 | 年度改月度；累计及新增分开共轴；保留历史参与 | [月度](tables/monthly_diffusion.csv)、[年度](tables/annual_diffusion_counts.csv) |
| b | 全球贡献和国内AF比重是否同一排序 | 美国全球份额领先；德、英国内率更高 | 三阶段共尺度、固定点；低值加共享放大图，不改变样本 | [国家×阶段](tables/country_period_profiles.csv)、[阶段覆盖](tables/period_counts.csv) |
| c | 研究总量增长如何分配到各国 | 主期16,411；2025前十占已知信用74.44% | 真比例柱；固定全期十国，Other／Unknown保留 | [年度](tables/annual_counts.csv)、[构成](tables/fixed_ten_composition.csv) |
| d | 集中度水平及相对差如何变化 | 2025 AF0.9253、背景0.8983、差0.0271；差非逐年下降 | 两个上下子图避免遮挡；整研究bootstrap、零国家固定 | [集中度](tables/concentration.csv)、[端点](tables/concentration_endpoint_sensitivity.csv) |
| 国内比例补图 | 构成是否影响国内比例观察 | 提供全范围及共同支持；2020背景支持仅42.29% | 分开展示范围筛选与假想构成分母，NA灰色 | [支持](tables/paired_domestic_heatmap_support.csv)、[配对比例](tables/paired_domestic_heatmaps.csv) |
| 地图补图 | 首次观察的地理顺序 | 142代码可定位，RE未定位但统计保留 | 国家示意点避免赋予未核实机构精确地址 | [首次观察坐标及来源](tables/country_first_observed_locations.csv) |

Figure1各面板是描述性证据，不是AF导致机会不平等或模型发布带来扩散的因果检验。原计划的“读者信息”已按相同四面板对应；早期样本稀疏、未知证据、差异性来源覆盖不因绘图完成而消失。

[主图](figures/figure1_revised_a_d.png) · [结果](results_zh.md) · [方法](methods_zh.md) · [图注](captions_zh.md) · [方案对照](plan_comparison_zh.md) · [入口](README_zh.md)
''',encoding='utf-8')
    (stage/'plan_comparison_zh.md').write_text('''# 与2026-10-08 Figure1修改方案的对照

## 已满足

四面板顺序a扩散→b位置→c分配→d集中度及相对差；三时期按同一发表月份规则；累计143与活跃128区分；全球份额和本地国内率分母区分；阶段累计后算比率；固定227含零国Gini；1000整研究重采样；Unknown信用不分摊；共同支持左右热图与两侧保留率；所有国家机器可读底表、HHI及头部份额；2021／2022起点敏感性；完整0–1 Gini补图；年度覆盖补图；首次观察地图及未定位清单；中文结果、方法和读者信息。

## 有依据的修改

| 原计划 | 最终做法 | 原因 |
| --- | --- | --- |
| 2020 n=10、总量16,341 | 2020 n=11、总量16,411 | 新增71确认记录及已接受版本去重减少1正例，非为扩大早期样本而改阈值 |
| 2020 AF Gini约0.9857／差0.0824 | 0.9838／0.0806 | 同一接受层重建国家信用，而非沿用旧数字 |
| 固定十国规则待定 | 全期2020–2025规则已接受 | 描述全期组成，跨年不换集合 |
| d小内嵌相对差 | 同面板上下子图 | 印刷空间和可读性，统计相同 |
| b低值重叠时考虑放大 | 共尺度线性主图＋共同范围放大 | 不改用对数而隐藏0附近，且不放大部分时期 |
| 74.4%图旁可单独标注 | 在Results／表报告74.44%，不放堆叠柱边界 | 已知国家分母与含Unknown柱不同，避免误读 |
| 全覆盖首次观察地图 | 142／143示意定位；RE列明未定位 | 没有可靠坐标不填邻国；统计累计仍143 |

## 尚不能认证／不强推的内容

586候选仍未知（其中430未有实质逐篇复核），不能当非使用；不声称候选召回完整、版本穷尽去重或独立人工金标准。月份有效不保证实际采用日期精度。bootstrap不涵盖标签／漏检／国家缺失或跨年团队依赖。没有正式因果事件研究或“不平等由AF引起”的结论。地图示意并非完整精细行政边界制图。

## 与其他分析版本的关系

本次是Figure1独立版本，不覆盖旧最终库、NHB02–05、原completion文件夹或原阅读zip。新版Figure1采用16,411，旧NHB02–05仍以16,341为主期基数。正式合写全文之前，应另行决定是否把新接受层传播到机构、活动、随访、领导和引用分析；不能只替换全篇总数而假设其余模型也更新。

[原修改方案存档](figure1_original_revision_plan.md) · [本次数据流程](data_flow_zh.md) · [入口](README_zh.md)
''',encoding='utf-8')
    (stage/'data_flow_zh.md').write_text(f'''# 数据处理流程与数量：Figure1修订

冻结OpenAlex主表6,046,663记录 → article／review／preprint、2015–2025研究基础4,686,896记录 → 原先已接受P0/P1关联后4,686,894单位 → 本次再接受12组版本、移除12个重复成员后4,686,882单位。不是新增下载一个更大的OpenAlex总体。

原候选复核库29,127记录；本轮针对AF1种子引用遗漏及关键词召回，新增765个适格候选（另有61个非适格类型，不纳入765）。352次公开论文证据请求后，313篇具核验正文，734篇至少一种非空摘要（非全部质量合格），31篇仍无摘要。335篇有逐篇辅助复核，430篇未有实质逐篇复核。全部765篇均有明确路由：71 yes／yes＋107非采用＋1原始平台排除＋586未知=765。作者接受这些特定路由及12组版本关系，并非为所有765篇认证独立人工金标准。

原主期16,341＋71新增确认－1正例版本重复=16,411。其余11个移除版本不影响AF正例总数，但会影响适格背景分母。本轮同时重建相应分母，未知不放入筛查阴性比较组。

年度及地区组成见下表；阶段主期总量37＋8,182＋8,192=16,411。

{annual_table}

地图另用1次公开底图请求，没有LLM付费API。主图／底表／阅读包阶段只读取本地数据。数据类型、国家1/k权重、Unknown与共同支持两侧保留率见[Methods](methods_zh.md)；单国精确值见[tables年度信用](tables/annual_country_credits.csv)。

[原方案对照](plan_comparison_zh.md) · [入口](README_zh.md)
''',encoding='utf-8')
    shutil.copy2(PLAN,stage/'figure1_original_revision_plan.md')
    # Original plan is historical evidence; its absolute paths and links are prose,
    # not navigation. Its online reference links remain unchanged.
    (stage/'README_zh.md').write_text('''# Figure1 revision：完整阅读入口

已完成新接受层驱动的计算、数值重建、主图视觉检查及独立阅读包；这是作者核阅版本，不是期刊提交批准。请使用本入口，不与旧completion_v3中的Figure1混用。

- [主图PNG](figures/figure1_revised_a_d.png) · [PDF](figures/figure1_revised_a_d.pdf) · [SVG](figures/figure1_revised_a_d.svg)
- [中文Results／明确findings](results_zh.md)
- [中文Methods／修改理由](methods_zh.md)
- [完整图注](captions_zh.md) · [逐面板读者信息](reader_information_zh.md)
- [原方案逐项对照：满足／修改／限制](plan_comparison_zh.md)
- [数据流程与数量总览](data_flow_zh.md)
- [年度活跃／新增／累计补图](figures/supplement_annual_country_diffusion.png)
- [首次观察地图](figures/supplement_first_observed_map.png)
- [全范围国内率PDF](figures/supplement_raw_domestic_all_countries.pdf) · [共同支持配对热图PDF](figures/supplement_paired_domestic_all_countries.pdf)
- [Gini完整0–1轴补图](figures/supplement_gini_full_axis.png)
- [数值／语义与视觉边界校验记录](release_checks.json)

主期16,411研究；2020年11；累计143国家／地区，2025活跃128；586新增候选保留未知。所有图片及CSV在本包内，Markdown使用相对链接，解压后可跳转。未包含受许可限制的全文、候选私有证据卡或大型逐研究Parquet。

**旧最终数据库、NHB02–05及旧阅读包未覆盖。** 新Figure1与旧NHB02–05的研究基数不同，整稿采用前仍需统一版本。正文只使用可支持的描述性判断，不将AF解释为造成不平等的因果因素。
''',encoding='utf-8')
    checks={'numerical_reconstruction':'PASS','formal_accepted_layer':True,'main_figure_visual_review':'PASS_local_labels_shared_zoom',
        'map_visual_review':'PASS_after_tight_bbox_export','heatmaps_visual_review':'PASS_all_10_pages; raw_title_wrapped_in_figures_v3',
        'confirmed_AF_main':16411,'year2020':11,'cumulative_countries':143,'active2025':128,
        'AF_retained_fraction_explicit':True,'map_located':map_summary['located'],'map_unmapped':map_summary['unmapped'],
        'other_NHB_sections_recomputed':False,'independent_human_gold':False,'submission_ready':False,'paid_API_calls':0}
    write_json(stage/'release_checks.json',checks)
    count=links_ok(stage);checks['portable_local_links_checked']=count
    # Recreate only this not-yet-published generated check record.
    (stage/'release_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    shutil.copy2(Path(__file__),stage/'build_revision_reading_package.py')
    write_json(stage/'run_manifest.json',{'schema':'figure1-revision-reading-package-v2',
        'inputs':[pin(SOURCE/'run_manifest.json'),pin(FIGURES/'run_manifest.json'),pin(MAP/'run_manifest.json'),pin(PLAN,PLAN.parent)],
        'outputs':e.inventory(stage),'executed_code':pin(Path(__file__)),'paid_api_calls':0})
    check_inventory(stage);stage.rename(out)
    zip_path=out.with_suffix('.zip');require(not zip_path.exists(),'ZIP already exists')
    with zipfile.ZipFile(zip_path,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(out.rglob('*')):
            if path.is_file():z.write(path,Path(out.name)/path.relative_to(out))
    with zipfile.ZipFile(zip_path) as z:require(z.testzip() is None,'ZIP CRC failure')
    print('Portable package:',out,'local links:',count,'ZIP:',zip_path,'bytes:',zip_path.stat().st_size)

if __name__=='__main__':build()
