"""Evidence-linked Chinese/English reporting without preselected conclusions."""
from support import *

def write(out):
    flow=load(out,'sample_flow');N=flow.set_index('stage').N.to_dict()
    country=load(out,'country_context');base=load(out,'baseline_groups');ctx=load(out,'context_group_year')
    main=load(out,'benchmark_summary').query('variant=="main" and setting=="main"').set_index('context')
    contrasts=load(out,'context_contrasts').query('variant=="main" and setting=="main"')
    overall=main.loc['All'];lh=contrasts[contrasts.primary].iloc[0]
    ddecision=json.loads((out/'provenance/panel_d_decision.json').read_text())
    exch=json.loads((out/'provenance/exchangeability_main.json').read_text())
    pre=ctx.query('analysis=="N20" and context=="All" and year==2019')
    endpoint=ctx.query('analysis=="N20" and context=="All" and year==2025').set_index('group')
    b=load(out,'panel_b_source')
    old=json.loads((OLD/'summary.json').read_text())
    ch=country[country.eligible_20].groupby('context').agg(countries=('country','size'),baseline_institutions=('baseline_institutions','sum'),
       min_baseline_country_studies=('baseline_country_studies','min'),max_baseline_country_studies=('baseline_country_studies','max')).reindex(['Low','Middle','High'])
    ch.to_csv(out/'tables/context_sample_summary.csv')
    rows=[]
    for context in ['Low','Middle','High']:
        a=b[b.context.eq(context)].set_index('year');m=main.loc[context]
        rows.append(f'| {context} | {int(m.countries)} | {a.loc[2021,"R"]:.4f} → {a.loc[2025,"R"]:.4f} | {a.loc[2021,"G"]:.2f} → {a.loc[2025,"G"]:.2f} | {m.excess:+.2f} | [{m.centered_low:+.2f}, {m.centered_high:+.2f}] |')
    btable='\n'.join(rows)
    af_full=int(old['global_af_studies'])
    allsens=load(out,'benchmark_summary').query('context=="All"')
    sensitivity_rows='\n'.join(f'| {r.variant} / {r.setting} | {int(r.countries)} | {r.actual_delta_G:+.2f} | {r.expected_delta_G:+.2f} | {r.excess:+.2f} |' for r in allsens.itertuples())
    noncountry=int(base.country.isna().sum());ambiguous=int(base.baseline_country_count.gt(1).sum())
    core_names='a–d' if ddecision['main_panel'] else 'a–c（d完整保留在Extended Data）'
    text=f'''# Figure 2：参与扩展、规模差距与发表机会基准

本版按2026-10-24方案及用户确认口径重算。主图为 **{core_names}**；不是上一版图形换皮，也不沿用原十国范围的结论。

## 数据与样本

原冻结总体为 {N['01_frozen_studies']:,} 项研究，2015–2019 年基线 {N['02_baseline_2015_2019']:,} 项，2020–2025 年 {N['08_main_period_all']:,} 项。基线机构仍为 {N['03_baseline_institutions']:,} 家。国家不能唯一确定的 {noncountry:,} 家（其中多国记录 {ambiguous} 家）留在审计中，不凭后来AF产出决定归属。

主分析按基线资格保留 **{N['06_main_N20_countries']} 个国家／地区、{N['07_main_N20_institutions']:,} 家机构**；每国国内低、中、高规模组都至少20家。国家前期科研发表基础低、中、高组分别为 {int(ch.loc['Low','countries'])}、{int(ch.loc['Middle','countries'])}、{int(ch.loc['High','countries'])} 国。这些是本合格国家集合内的发表基础组，不是旧R&D组，不代表收入、经费或算力等级。

机会池为 **{N['13_opportunity_pool']:,} 项研究**，含 **{N['14_opportunity_AF']:,} 项确认AF研究**；全语料的{af_full:,}项确认AF研究并非全部进入归属完整的机会池。{N['09_main_unknown_AF_label']:,} 项使用标签未知的研究不被改为non-AF，{N['15_outside_main_only_opportunities']:,} 项只连接主固定样本以外机构的研究仍保留在置换池中。

[完整数量流程](tables/sample_flow.csv)；[国内机构分组](tables/baseline_groups.csv)；[国家分组与阈值](tables/country_context.csv)。

## a：参与确实扩展，但不同规模机构并不同步

2025 年，全部合格国家等权的累计确认AF发表覆盖率，低、中、高机构规模组分别为 **{100*endpoint.loc['L','C']:.2f}%、{100*endpoint.loc['M','C']:.2f}%、{100*endpoint.loc['H','C']:.2f}%**。

这里分母包含未观察到参与的基线机构，不是只比较后来已经进入的机构。2019端点表示2020年前已观察参与，未计作2020年新增。年度累计确认观察不要求虚构精确月份，也不等同真实首次使用日期；更早可能使用的记录仍被标记。国家等权结果不能乘以48,010直接反推机构人数。

与旧版6,369家／52,098家、12.23%不同，本版为国内规模分组、固定合格国家、年度累计确认观察及国家等权；日期明确的首次进入子样本不再作为所有面板的分母。[a坐标与分母](figure2_source_data/panel_a.csv)。

## b：相对覆盖比与绝对百分点差必须同时阅读

| 国家前期发表基础 | 国家数 | 低／高覆盖比：2021→2025 | 高−低差距：2021→2025（pp） | 超出基准变化（pp） | 中心化95%基准范围（pp） |
|---|---:|---:|---:|---:|---:|
{btable}

比值增大表示相对覆盖更接近，不自动意味着绝对差距缩小。二者满足 G=100×A_H×(1−R)，不能作为两项独立证据。这里先算国家等权覆盖，再求比值，不平均各国比值。[b端点数据](figure2_source_data/panel_b.csv)。

## c：实际差距扩大，但小于这套发表机会基准的平均预期

全部合格国家等权汇总后，2021–2025 年高−低年度覆盖差距实际变化为 **{overall.actual_delta_G:+.2f} pp**；机会基准的解析预期为 **{overall.expected_delta_G:+.2f} pp**，条件基准95%范围为 **[{overall.reference_low:.2f}, {overall.reference_high:.2f}] pp**。

因此，实际减预期为 **{overall.excess:+.2f} pp**。负值不是“差距缩小”：实际差距仍扩大了{overall.actual_delta_G:.2f}个百分点，只是比这一基准预期扩大得少。

主置换固定每个主领域×年份×参与国家组合的AF研究数，保留整篇研究的全部机构连接。它说明，在已经发生的国家AF产出和研究发表组合下，实际标签分配产生的机构差距变化比条件基准更平缓。**不能据此称AF促进公平、降低资源障碍或产生因果改善。**

主分析5,000轮，先完成独立200轮试算。基准均值采用超几何解析期望，并与模拟均值核对。[c统计量](figure2_source_data/panel_c.csv)；[直方图坐标](figure2_source_data/panel_c_density.csv)；[解析核验](tables/analytic_expectation_check.csv)。

## d：国家情境差异是同一联合基准中的直接对比，不是独立重复验证

低基础国家组与高基础国家组的超出量之差为 **{lh.observed_excess_difference:+.2f} pp**；同轮联合置换得到的中心化参考范围为 **[{lh.centered_low:+.2f}, {lh.centered_high:+.2f}] pp**。

正值表示低基础组的“实际减预期”比高基础组更高，而不是证明其实际差距更大。必须同时阅读上表各组的实际差距变化、预期和超出量。国家内低规模组也不意味着跨国家具有相同绝对规模。

主图d保留状态：**{'保留：预定直接对比通过主范围及两项分层细化方向一致性规则' if ddecision['main_panel'] else '移至Extended Data：未满足预定稳定性规则'}**。灰线围绕基准零点，不围绕观测菱形，不能叫作观测超出量的95%置信区间。[直接组间对比](tables/context_contrasts.csv)；[d数据](figure2_source_data/panel_d.csv)。

## 稳健性与限制

总体结果的预定敏感性如下；N10／N30改变了合格国家总体，不能把数值差异全解释为同一总体的估计误差。

| 设定 | 国家数 | 实际变化（pp） | 预期变化（pp） | 超出量（pp） |
|---|---:|---:|---:|---:|
{sensitivity_rows}

总体超出量在上述设定中仍为负。低国家基础组本身的超出量在主分析约为−0.39pp，加入团队规模后约为+0.07pp，均在各自基准范围内；不能声称该组存在稳定的负偏离。主图d强调的是直接低−高对比，而不是由单个组的显著／不显著状态推导组间差异。

- 主基准 {exch['strata']:,} 个分层，其中 {exch['mutable_strata']:,} 层可交换；{exch['mutable_AF_papers']:,}/{exch['AF_papers']:,}（{100*exch['mutable_AF_papers']/exch['AF_papers']:.1f}%）AF研究在可交换层。不可交换层保留而不伪装成充分随机化。
- 预定加入文献类型、加入机构团队规模分箱的两套基准各5,000轮；N10／N30门槛、国家分数基线分组使用同一联合模拟另算。完整敏感性见[结果表](tables/benchmark_summary.csv)，不挑选最有利设定替代主分析。
- 国家等权主结果与机构数加权描述、一般科研活跃分母描述分开呈现。后两者只是不同描述性估计量，不冒称新的独立基准验证。
- 参照池包含screen-negative研究，不能称为每篇都经全文人工确认的non-AF。未知使用标签的排除可能具有选择性；已批准的版本合并不等于全语料所有版本已被完全识别。
- 国家组合只涵盖元数据中已知国家，并不保证所有作者国家完整。机构固定国家只按基线确定，后期迁移／多国署名不据结果重分组。
- 基准条件于研究期发表组合；细领域、团队组织和跨年活动连续性仍可能形成残差。p值（如查看底表）只检验这套标签交换模型，7项预定对比按Holm校正，不是AF的因果检验。

本节自然衔接Figure 3的进入后参与与延续；不再将进入队列的产出份额放进Figure 2主图。

[返回入口](README_zh.md) · [方法全文](methods_zh.md) · [图注](captions_zh_en.md) · [逐面板读者信息](panel_guide_zh.md)
'''
    (out/'results_zh.md').write_text(text)
    methods=f'''# Figure 2 plan 3：方法、口径与实现核验

## 1. 设计与语料

本研究是现有发表记录的观测性描述与条件标签交换参照分析。协议在分组、差距和模拟结果产生前落盘，见[实施方案](provenance/implementation_plan.md)。原用户方案的不可移植插图路径保留在[原文字节快照](provenance/figure2-revision-plan-3.source.txt)，便携说明见[方案](provenance/figure2-revision-plan-3.md)。

复用最新Figure 1已批准研究单位、版本连接与AF标签。研究总体 {N['01_frozen_studies']:,}；基线2015–2019；主期2020–2025，差距端点2021／2025。article、review、preprint及领域范围承接冻结语料，不按AF使用结果再筛领域。每研究由同一个已批准年度代表记录提供年份、主subfield、文献类型、全部已知国家集合与机构集合，不混合不同版本的日期和机构并集。研究内机构去重；不新建版本合并。

## 2. 标签与日期

confirmed_af=1为确认使用；否则，仅在不含possible_af时，以screen_negative、af_use_label=no或adoption_eligible=no作二元参照。最后一种包括提及AF但明确不构成采用的研究。其他标签保留未知并排除出二元池，不作为零。screen-negative是筛查阴性，不声称逐篇全文核验。基线一般科研发表量不因AF标签未知而删除。

主分析只需要可靠发表年份。现有YYYY-MM-DD字符串并不能证明原始日期精度，故date_precision明确记“年份已观察、月日精度未认证”，不把1月1日猜作月份或额外要求难以获得的精确日期。a为年度累计确认发表覆盖，2020年前确认参与记入初始值。更早未知证据不据此改成确认AF，也不宣称较晚确认日期是真实首次使用日期；[首次年份审计](tables/entry_year_audit.csv)另外标记。

## 3. 固定基线、机构国家与国内规模

完整论文—机构成员表重建整数研究数V_i，基线N={N['03_baseline_institutions']:,}。国家归属只在基线国家记录唯一时固定；未知／多国不凭后来AF结果分配。每国V_i按线性type-7的1/3、2/3切点分L、M、H，等于切点归较低组，等值不拆分。切点重合或空组不强造三组；失败原因与N10／20／30留存记录在[country_context](tables/country_context.csv)。主分析每组至少20机构，保留{N['06_main_N20_countries']}国、{N['07_main_N20_institutions']:,}机构；无当年论文者仍留固定分母。

国家前期科研发表基础为2015–2019相关语料中该国参与的唯一研究整数数。对N20合格国家、在AF结果比较前取国家三分位，固定阈值{country.context_cut_1.iloc[0]:.3f}与{country.context_cut_2.iloc[0]:.3f}，并列归较低组。N10／30敏感性沿用这些国家组阈值；国家分数基线作为另一定义敏感性。这不是旧FTE／GERD综合R&D指数。

## 4. 机会论文池与分母

主期明确二元标签、有机构身份、有至少一个已知国家的研究进入机会池N={N['13_opportunity_pool']:,}，AF={N['14_opportunity_AF']:,}。所有基线外机构论文也保留。没有机构或所有国家未知的研究单列排除，不虚构归属。机构国家固定归属与每篇实际已知参与国家集合不同者单列[代表记录归属审计](tables/representative_attribution_audit.parquet)。

Z_iy=1{{机构i在y年至少署名一项池内AF研究}}；A_cgy=活跃机构数／固定N_cg。C_cg为截至当年的累计确认覆盖；不是仅在已参与机构中的首次时间分布。全部国家主分析与国家组内均等权，先平均A再求R；不平均各国比值。

R=A_L/A_H；G=100(A_H−A_L)pp；ΔG=G_2025−G_2021。A_H=0时R未定义，不补零／伪计数；G仍可算。总体国家等权不是三个国家组均值的简单平均。各国机构数加权与一般科研仍活跃分母只作另列描述，不能冒称主结果。

## 5. 全局分层固定K置换

h=(primary_subfield_id, year, sorted unique full known country_set)。每层n_h项、K_h项AF，每轮均匀无放回选择K_h项。每轮全语料只产生一套标签，研究所有机构同时获得该标签；同轮计算所有国家／国家组和直接对比。保持研究元数据、机构连接、各分层AF数，因而保持各国年度AF研究参与量与国家分数credit；机构AF产出／活跃数／覆盖并不固定。

未知主领域若存在保留为命名分层，不按结果填补。主分析不合并国家组合或年份。K=0、K=n、n=1无交换，保留并输出[strata_audit](tables/strata_audit.csv)。研究机构集合取完整成员表，不只取能赋国家信用的机构。基线外机构论文有机会被选中，不能提前从抽样池删除。

主种子20261024；独立pilot种子20261025、200轮；主5,000轮。预定两套细化：增加文献类型；增加机构数分箱1／2–4／≥5；各5,000轮，保留国家集合与年份不变。若主聚合均值或直接低−高对比的MCSE超过0.05pp，按预设规则增至10,000轮，不以显著性为停止标准。实际轮数、耗时、种子见[运行配置](run_config.json)及provenance运行记录。

## 6. 解析期望与依赖

机构在层h有m_ih项研究时，P0(无AF)=Π_h[C(n_h−m_ih,K_h)/C(n_h,K_h)]。采用log-gamma稳定计算；n−m<K时因子0，K=0或m=0时因子1。q_iy=1−P0，按固定机构分母与国家权重得到解析A、G和ΔG预期。R逐轮计算，不能拿期望比代替比的期望。

每轮先计算“至少一篇”整数活跃，再聚合。有限样本枚举、合作论文共同移动、基线外机会、国家权重、零分母、并列处理等回归测试见[测试代码](code/test_revision.py)。模拟均值与解析均值按MC误差核对；pilot某格零样本方差不代表真实随机量确定不变，只有解析q全为0或1的格子才作确定性等值检查。合作依赖由同一全局标签保留，不把机构当相互独立的伯努利试验。

## 7. 超出量、区间与直接对比

μ_s=E0(ΔG_s)，主报告用解析μ；E_s=ΔG_obs−μ_s。U_s^b=ΔG_s^b−μ_s。d中点为E_s，灰线为U_s的2.5%／97.5%分位：围绕基准零点，**不是以观测点为中心的95%CI**。c画未中心化ΔG基准密度及实际／预期。这里不提供未经依赖处理的抽样置信区间。

国家组主要对比低−高，其次低−中、中−高，全部用同轮U差，不能独立相加方差。辅助条件随机化p=(1+Σ1{{|U|≥|E|}})/(B+1)，总体＋三国家组超出量及三直接对比为7项检验族、Holm校正；底表报告，不用星号代替效应和基准范围。该p针对可交换标签模型，不是因果或资源机制检验。

d主图保留规则在结果前固定：主要低−高对比在主基准中心化范围外，且两个细化基准中方向一致；否则移ED但不删除结果。当前判定：{ddecision['reason']}。

## 8. 新旧差异与局限

旧版十国按AF产出选择、国内规模用2017–2019参照分数产出；本版按基线资格选择国家、规模用2015–2019整数研究数。旧日期条件首次进入的6,369家不能与本版年度确认覆盖率直接比较。进入队列产出份额退出本版主图，历史文件保留不改。

这套基准条件于既有国家AF产出、合作国家组合与研究期发表机会，因此不是“没有障碍”的世界，更不能识别AF因果效应。未观察细领域、团队组织、跨年聚集、非随机标签未知和元数据缺失仍可影响偏离。元数据已知国家集合不保证所有真实国家被完整观测。基线较少国家可能因分组资格被排除，结论范围仅限合格国家／机构。

## 9. 可复现性与图像导出

全部源文件只读，哈希见[input_pins](provenance/input_pins.json)；独立新目录写派生表。一次性准备发生临时盘限额后，去掉无必要全表排序、释放中间表并使用单线程4GB内存／8GBscratch限额；未修改资格或结果以绕过错误。完整成员表与国家信用表用途明确分开。

原生183mm宽绘图，PDF／SVG保留可编辑矢量文本，另导出600dpi RGB／sRGB PNG和LZW TIFF用于审阅／留档。正式Nature主图优先可编辑矢量；600dpi不是自动通过投稿的证明。Extended Data另给300dpi RGB TIFF，避免把高分辨率留档直接当作网页投稿文件。[官方图形导出说明](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/)（2026-10-24核对）；最终以NHB所处投稿阶段要求和编辑意见为准。

分析辅助使用了数据分析、统计分析和科学可视化的程序化检查流程。软件方法参考：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. [arXiv / DOI](https://doi.org/10.48550/arXiv.2609.00065)（2026-10-24核对；不是本研究实证证据来源）。

[返回入口](README_zh.md) · [中文结果](results_zh.md)
'''
    (out/'methods_zh.md').write_text(methods)
    captions=f'''# Figure 2 图注

## 中文

**Figure 2｜机构AF发表参与扩展、规模覆盖差距与条件发表机会基准。**

**a**，{N['06_main_N20_countries']}个合格国家／地区、{N['07_main_N20_institutions']:,}家固定基线机构，按各国内2015–2019去重整数研究量分为低、中、高组，画年度累计确认AF发表覆盖的国家等权均值。未参与者留在固定分母；Pre-2020为起始已观察参与，不计作2020新增。**b**，按国家前期科研发表基础分组，展示2021（空心）与2025（实心）的低／高年度覆盖比及高−低百分点差；先平均国家覆盖率再求比。**c**，全体合格国家等权的2021–2025高−低差距变化，灰色为主领域×年份×全部已知参与国家集合内固定AF总数的5,000轮联合置换分布；虚线为解析预期，实线为观测值，超出量为观测减预期。**d**，各国家科研基础组超出量及预定低−高直接对比；灰线为中心化联合基准分布2.5–97.5%范围，菱形为观测超出量／直接差，**灰线不是观测效应的置信区间**。{'d在主图保留。' if ddecision['main_panel'] else 'd见Extended Data。'}

同一合作研究的全部机构共同获得置换标签；全部面板国家、机构分组与分母固定。未知标签不作non-AF。参照中包含筛查阴性研究。国家组表示样本内前期发表基础，不代表R&D投入；偏离条件基准不识别因果效应或资源障碍。

## English

**Figure 2 | Expansion of institutional AF publication participation and scale-related coverage disparities relative to a conditional publication-opportunity benchmark.**

**a**, Equal-country mean cumulative observed AF coverage by domestic baseline publication-output tertile, using fixed denominators ({N['06_main_N20_countries']} countries/regions; {N['07_main_N20_institutions']:,} institutions). Baseline output is the integer number of unique eligible studies in 2015–2019; tied counts are not split. Pre-2020 observations enter the initial state, not 2020 incident entries. **b**, Ratios of lower- to higher-scale annual coverage and higher-minus-lower coverage gaps in 2021 (open) and 2025 (filled), by pre-AF national publication-base group. Ratios are taken after equal-country aggregation. **c**, Observed 2021–2025 gap change versus 5,000 global fixed-K permutations stratified by primary subfield, year and the full known participating-country set. The dashed line marks the exact hypergeometric expectation; the solid line marks the observation. **d**, Context-specific excess changes and a paired low-minus-high context contrast. Diamonds are observed excesses; gray segments are the 2.5th–97.5th percentiles of centered conditional benchmark distributions, **not confidence intervals around the observed points**.

All institutions on a study receive the same permuted label. Unknown adoption labels are not treated as non-AF; comparison records include screen-negative studies. The benchmark conditions on observed publication and country-participation patterns and does not identify causal effects or resource mechanisms.

[入口](README_zh.md) · [逐面板说明](panel_guide_zh.md)
'''
    (out/'captions_zh_en.md').write_text(captions)
    guide='''# Figure 2 逐面板读者信息与要求对应

| 面板 | 图形／终点 | 读者应获得的信息 | 数据与方法位置 |
|---|---|---|---|
| a | 三条年度累计覆盖曲线 | 低中高规模机构参与扩展是否同步；未参与者仍在分母 | [坐标](figure2_source_data/panel_a.csv)，Methods 3–4 |
| b | 比值／百分点差端点连接图 | 相对覆盖与绝对差距方向可以不同，不能混为同一命题 | [端点](figure2_source_data/panel_b.csv)，Methods 4 |
| c | 条件基准密度、实际与预期竖线 | 已有发表机会能重现多少差距变化；超出量可为负而实际差距仍扩大 | [统计量](figure2_source_data/panel_c.csv)、[密度坐标](figure2_source_data/panel_c_density.csv)，Methods 5–7 |
| d | 超出量菱形、中心化灰色范围、直接组间差 | 国家情境异质性要直接配对比较；灰线不是观测值的CI | [d坐标](figure2_source_data/panel_d.csv)、[对比](tables/context_contrasts.csv)，Methods 7 |

## 与原要求一致的部分

固定基线和国内三组；基线国家资格而非AF前十国；国家等权；主领域×年份×完整已知国家集合固定K；整篇合作论文联合标签；基线外机构机会保留；解析超几何期望；先200再5000；直接组间对比；未知标签不作零；区间名实一致；所有必需底表。

## 按用户确认具体化的部分

国家科研基础用2015–2019国家参与整数研究数；国内组N20为主、10／30敏感性；a年度而非月度；主field用已有primary subfield；机构固定国以基线唯一归属为主。日期精度没有现成认证字段，明确记录年份可用、月日未认证，不虚构新精度。

## 保留的限制与额外材料

国家组只表示发表基础；不恢复R&D指数。只按已批准链接去重，不称完整识别所有版本。一般科研仍活跃分母／机构加权为额外描述，不冒称独立验证。旧进入队列产出份额退出主图，但旧版目录不改。国家／机构团队敏感性、逐国端点和3×3残差热图在Extended Data。p值只在底表辅助，未用星号强化结果。

[主图](figures/figure2_plan3_main.pdf) · [完整a–d审阅图](figures/extended_data/figure2_plan3_a_d.pdf) · [中文结果](results_zh.md) · [方法](methods_zh.md) · [入口](README_zh.md)
'''
    (out/'panel_guide_zh.md').write_text(guide)
    table=[dict(item='固定基线机构',previous=old['fixed_n'],current=N['03_baseline_institutions'],reason='完整成员表重建2015–2019整数研究基线'),
      dict(item='国内比较国家',previous=10,current=N['06_main_N20_countries'],reason='从研究期AF前十改为基线N20合格国家'),
      dict(item='国内比较机构',previous='机构—国家对；旧十国范围',current=N['07_main_N20_institutions'],reason='固定唯一基线国家；重建国内三等分'),
      dict(item='规模指标',previous='2017–2019参照分数产出',current='2015–2019去重整数研究数',reason='遵循新版基线定义'),
      dict(item='a的终点',previous='日期明确新增进入累计数／全局52,098',current='各国内规模组年度累计确认覆盖，国家等权',reason='避免仅日期明确进入者决定主图分母'),
      dict(item='b的终点',previous='三进入阶段队列的条件AF信用份额',current='2021/2025年度覆盖比和百分点差',reason='队列产出份额退出F2主图'),
      dict(item='c/d基准',previous='本版F2无此联合固定K基准',current='主＋两细化，各5000联合置换；先200pilot',reason='检验给定发表机会和国家AF参与组合后的差距变化')]
    pd.DataFrame(table).to_csv(out/'tables/old_new_comparison.csv',index=False)
    readme=f'''# Figure 2 plan 3 阅读入口

按2026-10-24新版要求重算。主分析{N['06_main_N20_countries']}国／地区、{N['07_main_N20_institutions']:,}家机构；国家等权；5,000轮整篇研究联合置换。旧数据、旧AF标签与旧版图文未覆盖，无新付费或LLM调用。

## 先看这些

- [主图 PNG](figures/figure2_plan3_main.png) · [矢量 PDF](figures/figure2_plan3_main.pdf) · [SVG](figures/figure2_plan3_main.svg) · [600dpi TIFF留档](figures/figure2_plan3_main.tiff)
- [中文 Results](results_zh.md)
- [中文 Methods与修改原因](methods_zh.md)
- [中英文图注](captions_zh_en.md)
- [逐面板读者信息与要求对应](panel_guide_zh.md)
- [新旧版口径／数量对照](tables/old_new_comparison.csv)
- [完整a–d审阅图](figures/extended_data/figure2_plan3_a_d.pdf)

## Extended Data

- [国家情境超出量与直接对比](figures/extended_data/ED_context_excess.pdf)
- [各国家组累计参与](figures/extended_data/ED_context_entry_trajectories.pdf)
- [3×3覆盖变化残差热图](figures/extended_data/ED_coverage_change_residuals.pdf)
- [基准与门槛敏感性](figures/extended_data/ED_benchmark_sensitivity.pdf)
- [逐国端点 1](figures/extended_data/ED_country_endpoints_1.pdf) · [2](figures/extended_data/ED_country_endpoints_2.pdf) · [3](figures/extended_data/ED_country_endpoints_3.pdf)

## 审计与底表

[样本流程](tables/sample_flow.csv) · [机构基线与分组](tables/baseline_groups.csv) · [国家组与阈值](tables/country_context.csv) · [国家×机构组×年](tables/country_group_year.csv) · [国家组×年](tables/context_group_year.csv) · [分层审计](tables/strata_audit.csv) · [逐轮联合模拟](tables/benchmark_replicates.csv) · [基准汇总](tables/benchmark_summary.csv) · [直接对比](tables/context_contrasts.csv) · [解析核验](tables/analytic_expectation_check.csv) · [配置](run_config.json) · [输入哈希](provenance/input_pins.json)

四张输入表也随包提供Parquet：[研究](tables/studies.parquet)、[研究—机构](tables/study_institution.parquet)、[机构基线](tables/baseline_groups.parquet)、[国家情境](tables/country_context.parquet)。它们是派生的最小分析数据，不含原始全文。

## 使用边界

负超出量不等于实际差距缩小；灰色基准范围不是观测值CI；国家发表基础不是资源／R&D等级；国家组对比不是独立重复验证。正文和Methods已经逐项说明。作者科学审阅与正式投稿验收仍待完成。

全部链接相对本包根目录；ZIP解压后可读。[重现方法](code/REPRODUCE.md)。
'''
    (out/'README_zh.md').write_text(readme)
    english=f'''# Figure 2 findings (English working draft)

Among {N['06_main_N20_countries']} baseline-qualified countries/regions ({N['07_main_N20_institutions']:,} institutions), cumulative observed AF coverage in 2025 was {100*endpoint.loc['L','C']:.2f}%, {100*endpoint.loc['M','C']:.2f}% and {100*endpoint.loc['H','C']:.2f}% in domestic lower-, middle- and higher-output groups, respectively (equal-country means).

The overall higher-minus-lower annual coverage gap increased by {overall.actual_delta_G:.2f} percentage points between 2021 and 2025. A global fixed-K conditional permutation benchmark predicted an increase of {overall.expected_delta_G:.2f} pp (95% conditional reference range {overall.reference_low:.2f} to {overall.reference_high:.2f} pp), yielding observed-minus-expected excess {overall.excess:+.2f} pp. Thus the gap widened in absolute terms, but less than under this specified opportunity allocation model. This is not evidence of causal equalization.

The directly paired low-minus-high national publication-base contrast in excess change was {lh.observed_excess_difference:+.2f} pp (centered conditional reference range {lh.centered_low:+.2f} to {lh.centered_high:+.2f} pp). These ranges are not confidence intervals around the observed excess. National publication-base categories are baseline descriptive strata, not measures of funding or resources.

[Figures and source data](README_zh.md) · [Methods (Chinese)](methods_zh.md)
'''
    (out/'results_en.md').write_text(english)

if __name__=='__main__':write(OUT)
