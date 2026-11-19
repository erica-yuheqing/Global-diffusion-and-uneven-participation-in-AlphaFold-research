"""Write source-linked internal results/methods and explicit plan completion."""
import hashlib
import json
import pandas as pd
from support import *

def write(out):
    a=load(out,'panel_a_participation');b=load(out,'panel_b_observed_expected')
    gradient=load(out,'benchmark_gradient_comparison').set_index('variant')
    models=load(out,'initial_model_diagnostics');c=load(out,'panel_c_initial_use')
    d=load(out,'panel_d_group_shares');all_d=d[d.variant.eq('primary')&d.quintile.eq('All')].set_index('category')
    fixed=load(out,'author_fixed_count_sensitivity');fixed_common=fixed[fixed.scope.eq('common_at_least5')&fixed.quintile.eq('All')&fixed.category.eq('Mixed')].sort_values('later_papers_sampled')
    source=load(out,'benchmark_reference_counts');prep=load(out,'preparation_audit')
    main=models[models.variant.eq('main_linear_log_scale')].set_index('activity')
    state=a.set_index('status');q=b.set_index('quintile')
    month=load(out,'window_policy_sensitivity');month=month[month.policy.eq('all_month_precision_sensitivity')].set_index('state')
    month_n=int(month.denominator.iloc[0]);month_both=int(month.loc['both_intervals','institutions']);month_pct=month.loc['both_intervals','percent']
    btable='\n'.join(f'| Q{int(r.quintile)} | {int(r.N):,} | {100*r.observed:.1f}% | {100*r.expected:.1f}% | {r.difference_pp:+.1f} |' for r in b.itertuples())
    ctable='\n'.join(f'| {label} | {int(main.loc[m,"N"]):,} | {100*main.loc[m,"adjusted_absent"]:.1f}% | {100*main.loc[m,"adjusted_present"]:.1f}% | {main.loc[m,"difference_pp"]:+.1f} |' for m,label in zip(MODES,LABELS))
    dtable='\n'.join(f'| {cat} | {int(all_d.loc[cat,"N"]):,} | {all_d.loc[cat,"percentage"]:.1f}% |' for cat in ['Linked-only','Mixed','Unlinked-only','Unresolved'])
    reference_rows='\n'.join(f'| {name} | {gradient.loc[name,"observed_gradient_pp"]:+.1f} | {gradient.loc[name,"expected_gradient_pp"]:+.1f} | {gradient.loc[name,"residual_gradient_pp"]:+.1f} |' for name in ['main','leave_institution_and_shared_papers_out','all_corpus_reference','year_only','subfield_two_year_bins'])
    (out/'README_zh.md').write_text('''# Figure 3 plan 3：首次参与后的延续、机会基准与作者联系

本版从冻结数据重新计算，并尽量按新文件落实。机器数值与导出检查通过；作者科学审定及投稿前图形终审待完成。没有调用LLM/API、没有修改原数据库或旧图表。

## 推荐阅读

1. [核心主图 a–b PDF](figures/figure3_core_a_b.pdf) · [600 dpi PNG](figures/figure3_core_a_b.png) · [TIFF](figures/figure3_core_a_b.tiff) · [可编辑SVG](figures/figure3_core_a_b.svg)
2. [四面板完整阅读版](figures/figure3_a_d_reading_not_full_inference.pdf)：c 明确标为探索性惩罚估计，**不是完整满足95% CI要求的最终主图**。
3. 独立扩展面板：[c 初始使用方式](figures/extended_data/figure3c_initial_use_exploratory.pdf)、[d 作者延续](figures/extended_data/figure3d_author_continuity.pdf)。d 为可纳入正文的描述性分析，但必须保留Unresolved。
4. [中文Results](results_zh.md) · [中文Methods](methods_zh.md) · [中英文图注](captions_zh_en.md) · [逐面板读者信息](panel_guide_zh.md)
5. [要求逐项对照与未满足项](plan_comparison_zh.md) · [全部源数据入口](source_data_zh.md) · [验证报告](validation_report.json)

## 必须知道的限制

c 的四个非惩罚Logistic模型均检测到完全或准完全分离；每个模型的共享论文连通组也未通过预设的区间可靠性门槛。已按预先说明的ridge方案计算探索性概率及敏感性，未伪造95% CI，不能据此宣称显著差异。初始分类复用旧证据和已接受裁决，没有新一轮独立人工金标准认证。

b 是条件独立的发文机会参照，不是因果模型；参照范围会影响剩余梯度的数值。d 的“无重合”仅限观察到且通过完整性筛查的作者—机构名单，不证明新团队成立。

[用户原方案副本](provenance/source_plan.md) · [执行口径](code/README.md) · [保留的旧Figure 3及活动分析](previous_figure3_v6/README_zh.md)
''')
    (out/'results_zh.md').write_text(f'''# Figure 3 中文 Results（内部可追溯稿）

## 1. 首次参与后的延续并不普遍

在52,098家固定基线机构中，Figure 2识别的6,369家主期明确进入者进一步分为：2,604家未达到完整24个月观察期，1,426家随访存在未定AF记录，最终2,339家进入完整且可判定的主随访分析。它们不是全部AF参与机构的随机样本；较晚进入与证据不足者的排除均有明确记录。[claim:C001] [evidence:E001,E002]

两个12日历月后续窗口均观察到AF研究的机构为454家（19.4%），仅第一窗口403家（17.2%），仅第二窗口398家（17.0%），均未观察到1,084家（46.3%）。至少一个窗口出现后续AF研究的机构为1,255家（53.7%）。这描述发表参与，不将未再发表等同停止使用。[claim:C002] [evidence:E001]

将所有日期统一按月处理的敏感性分析得到{month_n:,}家完整可判定机构，其中{month_both:,}家（{month_pct:.1f}%）双窗口参与；主分析沿用可用日级日期，没有为保持旧人数而修改窗口，也未把每月1日自动判定为月级精度。月末边界使用日历月份偏移，明确包含闰年2月29日。[claim:C003] [evidence:E003]

## 2. 原始规模梯度并不能直接说明AF特有的延续优势

新版发文机会表包含254,033条去重研究—机构关系。参照池跨机构去重后包含204,593项研究，其中2,324项确认AF参与、202,269项操作性背景比较记录，本主队列后续机会池中未出现记录为未定类别的研究。这里的筛查阴性背景不等于每项都经过独立全文非使用验证。[claim:C004] [evidence:E004,E005]

按基线论文量固定五分位后，实际双窗口参与率从Q1的6.4%上升至Q5的46.8%。条件独立的发文机会基准则从1.2%上升至57.5%。实际减预期的差值从Q1的+5.1个百分点变为Q5的−10.8个百分点。[claim:C005] [evidence:E006]

| 基线论文量组 | 机构数 | 实际双窗口参与率 | 机会基准预期率 | 实际−预期（pp） |
|---|---:|---:|---:|---:|
{btable}

实际Q5−Q1梯度为{gradient.loc['main','observed_gradient_pp']:.1f}个百分点，机会预期梯度为{gradient.loc['main','expected_gradient_pp']:.1f}个百分点，剩余梯度为{gradient.loc['main','residual_gradient_pp']:+.1f}个百分点。该结果不支持“相对于这一机会参照，大机构仍有额外更陡的持续参与优势”。但这不是“机会已被因果证明完全解释”的结论。[claim:C006] [evidence:E007]

将当前机构以及与其共享的全部研究从基准参照中留出后，剩余梯度为{gradient.loc['leave_institution_and_shared_papers_out','residual_gradient_pp']:+.1f}个百分点，与主方案接近。将参照改为整个合格研究库后，预期梯度为{gradient.loc['all_corpus_reference','expected_gradient_pp']:.1f}个百分点，与实际梯度接近，剩余为{gradient.loc['all_corpus_reference','residual_gradient_pp']:+.1f}个百分点。参照范围改变了剩余值的大小和方向；不能选择有利设定来宣称AF能力差异。[claim:C007] [evidence:E007]

| 参照设定 | 实际高低组梯度（pp） | 预期高低组梯度（pp） | 剩余梯度（pp） |
|---|---:|---:|---:|
{reference_rows}

## 3. 初始使用方式：已计算，但仅能作为探索性扩展

四类初始使用方式按每类可评估机构分别分析，不再只选择已双窗口参与的454家。可评估样本依次为1,127、923、666、1,431家；未知没有补成未使用。调整前期论文量、基线国家、进入年份和基线主subfield后，非惩罚Logistic均检测到完全或准完全分离。采用拟合前记录的标准化ridge（λ=1）计算探索性标准化概率，并保留λ=0.1/10及非线性规模敏感性。[claim:C008] [evidence:E008,E009]

| 初始类型 | 可评估机构数 | Assessed absent 调整概率 | Present 调整概率 | Present−absent（pp） |
|---|---:|---:|---:|---:|
{ctable}

四个模型的最大共享论文连通组分别占模型样本的{', '.join(f'{100*main.loc[m,"largest_component_fraction"]:.1f}%' for m in MODES)}，均超过预设10%的保守门槛，同时存在非惩罚估计分离。因此本轮**没有可发布的依赖校正95% CI**，这些数值不构成显著性或因果证据。c放在Extended Data；四面板阅读版明确标记其探索状态，而不是把缺失区间隐藏。[claim:C009] [evidence:E009]

初始标签仅代表机构关联的初始研究中观察到该使用方式，不能在合作论文无法定位执行者时解释为该机构亲自执行。没有在本轮新建独立人工金标准。[evidence:E008]

## 4. 作者联系与机构内其他作者参与并存

在1,255家再次发表机构中，332家（26.5%）所有后续研究均观察到初始本机构作者重合；225家（17.9%）同时观察到有重合与可判定无重合的后续研究；327家（26.1%）全部后续研究均为可判定无重合；371家（29.6%）信息不足，保留未定。分类使用论文上的本机构作者关联，不是论文全部作者名单。[claim:C010] [evidence:E010,E011]

| 类别 | 机构数 | 占全部再次发表机构比例 |
|---|---:|---:|
{dtable}

作者重合不能直接证明同一实验室，无重合不能直接证明新团队成立。Unresolved比例随组别变化，因此不能简单将规模组间差异解释为组织更新速度差异。[evidence:E010,E011]

为区分发文次数机会，在同一批至少5篇后续研究的{int(fixed_common.N_eligible.iloc[0])}家机构内，分别抽取2、3、5篇研究，Mixed的精确预期比例为{', '.join(f'{r.exact_expected_percentage:.1f}%' for r in fixed_common.itertuples())}。这显示Mixed分类确实受到观察论文数量影响；所附500次抽样分布是固定样本内的抽样波动，不是总体置信区间。另有按每个k分别符合条件的样本结果，不能忽视其分母变化。[claim:C011] [evidence:E012]

## 结果的使用边界

可在正文使用a的参与分布、b的条件机会比较，以及d带有缺失披露的作者联系描述。c只作为探索性关联线索；不能声称某种初始使用方式显著提高持续参与。旧454家机构的活动份额与活动证据轨迹仍完整保留在历史/扩展材料，不与本版c、d的新分母混用。
''')
    (out/'methods_zh.md').write_text('''# Figure 3 plan 3：Methods 与 Supplementary Methods

## 设计、数据版本与分析意图

本研究为冻结文献样本的描述性与探索性关联分析。本次是作者要求下的分析修订，不宣称在原数据收集前预注册。以最新已接受的16,414项2020–2025 AF主期研究为依据，沿用已批准版本关联，不新增自动合并。原OpenAlex下载快照完成于2026年4月3日所在周，行政随访截止2025-12-31。原始数据库、旧结果与先前裁决不修改。

采用数据分析、统计分析、科学可视化及证据绑定写作技能辅助可重复性、缺失处理、推断边界和导出；这些技能不是独立统计验证或人工金标准。Parquet按已检查的本地Arrow/DuckDB schema处理，不交由不支持该格式的通用EDA工具猜测解析。既有依赖环境记录于执行协议和manifest，没有安装软件或调用外部模型。

## 1. 基线、首次日期、窗口与样本

固定基线为2015–2019年观察到至少一条合格论文的52,098家机构。机构首次AF事件来自实际具有独立确认证据的版本成员自身日期，不把其他成员机构集合、标签或更早日期拼接回填。首次进入未定、2020年前已观察到的参与、行政观察不足及随访存在未定事件分别记录。主队列是完整且可判定的24日历月随访子集，而不是全部进入者。

日级主方案使用(t_i,t_i+12日历月]和(t_i+12日历月,t_i+24日历月]；首次日期当天的所有确认AF研究构成初始集合，不计后续。没有把12个月替换为365天。冻结导出不存在明确的日期精度字段，因此使用现有可用日期；每月1日不自动判为月级精度。敏感性将所有日期映射到月末并完整重建首次、初始集合、窗口与不确定性，等价于进入月全部AF研究为初始、后续第1–12和13–24个月为随访。敏感性使用其自身的完整样本，不强制相同人数。

主要结局为两个窗口均有确认AF研究；任一窗口有后续研究另记repeat。四状态互斥，以主完整随访机构数为统一分母。无后续发表不能证明现实中停止使用AF。

主规模指标为完整随访样本的2015–2019年论文数量。type-7五分位切点为20/40/60/80%，并列归较低边界组；仅分组键round到12位以消除浮点求和伪差异，原始数量不修改。不随机拆分并列，不把零或未知当作正值。活跃作者与一般伙伴各自固定五分位用于Extended Data，不暗示三者能独立识别经费、FTE或算力。

## 2. 机会表、基准率与期望概率

分析单位为机构内去重的研究ID，使用整数篇数，不用fractional credit。非AF候选机会连接冻结年度代表记录的实际机构关联及日期；确认AF机会连接本机构实际确认版本成员的日期与归属。两个AF窗口的整数计数必须逐机构复现旧的bin1/bin2。保存代表年份与本机构事件年份差异检查；本次为零。可能落入窗口的缺失/冲突日期单独标记，不能当作零机会；本次没有因该项缺失而排除主队列机构。

主参照为完整随访机构后续窗口内出现的研究池，跨机构去重，每项研究只按冻结代表的subfield及日历年份贡献一次基准记录。标签分为确认AF、操作性比较背景和未定。比较背景包括screen-negative和已审定非使用，但不宣称所有筛查阴性研究都独立全文确认过非使用。记录为未定或其他不符合AF采用定义的已审研究不转成negative。

主p_s=AF_s/(AF_s+comparison_s)，而n_iws计该窗口该stratum的全部可观察合格论文机会。若参照存在未定标签，补充p_low=AF/all与p_high=(AF+unknown)/all；本主参照未出现该类未定记录，因此两边界与主设定一致。全库替代参照仍保留它自己的未定计数。

稀疏规则在新聚合前固定：已知基准研究至少100项使用subfield×日历年份，否则使用同一日历年份的汇总率。Unknown subfield独立保留，不由ID猜测上层领域。敏感性为阈值50/200、仅年份、subfield×两年段、全库参照、以及留出当前机构全部机会研究。留出时，与该机构共享的论文从整个参照池移除，不能只删除该机构的一行却在其他机构保留同一论文。

计算q_iw=1−exp[Σ_s n_iws log(1−p_s)]，e_i=q_i1×q_i2。使用log1p/expm1提高数值稳定性；p=0或1按公式处理；实际没有机会的窗口为零，有缺失或无法估计率则保留缺失。各组对同一可比较机构集计算实际均值O_g、预期均值E_g和D_g=100(O_g−E_g)。剩余高低组梯度为D_Q5−D_Q1，而不是只判断某组O>E。

该模型假定给定分层后的论文AF标识及两个窗口机会条件独立，不能捕捉同一作者、团队或合作研究的全部相关性。它是条件描述参照，不是“若同一机构没有采用AF”的反事实因果模型。此次不添加非必要模拟带；因此不存在将基准模拟分布误称置信区间的问题。主结果与全部预先指定参照设定共同报告。

## 3. 初始使用方式、证据和回归

仅使用初始集合的既有动作证据，四类可重叠：precomputed结构取用；运行AlphaFold/ColabFold新预测；方法/工具开发；预测评估/验证。映射沿用已接受的动作口径，不因为只提及模型或数据库而记支持，也不将运行ColabFold自动记为直接运行AlphaFold。合并为prediction runs时保留原动作来源。

每类只要初始集合有supported即present；无正例且全部初始记录均为可判定not_established才为assessed absent；否则unassessable。旧共识记录未列出动作、uncertain、未评估及新增仅core接受的研究不补成absence。保留逐初始研究的state、action_source、实际source work ID及原证据文件哈希指针。原先的人类校准及特定接受裁决不被本轮重新声称为全量独立人工验证；新增独立人工验证未实施。因此分类质量本身也限制c的结论。

每种初始类型分别在其可评估完整随访机构中拟合：logit P(Y=1)=α+βT+γ log(1+B)+国家固定效应+进入年份固定效应+基线主subfield固定效应。国家按基线机构—论文归属计数决定，最高计数并列保留多国标记；基线主subfield按前期论文数最高者决定，完全并列按ID固定顺序选择。全部主队列少于30家机构的国家和少于50家的subfield在按类型筛选及拟合前并入Other，Unknown独立。国家、领域不由后续结果分配。规模二次项作为预设敏感性；不按方向挑模型。设计矩阵只移除恒定或线性冗余列，报告全部模型及诊断。

先尝试非惩罚MLE，并用既有经测试本地求解器检查分离与收敛。本次四个主模型均分离。拟合前补充记录的计算回退为标准化斜率ridge，λ=1、截距不惩罚，另列λ=0.1/10，不将其说成非惩罚MLE。回退只产生探索性Extended Data点估计。调整后概率是在相同可评估机构协变量上，分别将初始类型设为present/absent后预测并机构等权平均；差值是两者百分点差，而非odds ratio。

依赖诊断使用初始和后续共享研究建立机构连通组。预设区间发布条件为：MLE可估计、至少30组、最大组不超过模型样本10%、信息矩阵可用、每个初始类型×结局格至少10家。该保守检查不是独立性证明。若可用，拟使用连通组聚类score sandwich及标准化概率delta method；本次估计/依赖门槛未通过，因此没有发布该95% CI，也没有p值或显著性星号。c不作为满足原方案推断要求的最终主图面板。

## 4. 本机构作者延续

样本为所有repeat机构。作者集合来自实际AF事件来源论文的author–work–institution关联，不把一篇论文的全部作者分配给每个机构。初始本机构作者集合为全部初始记录的并集；后续逐研究与它比较，保留论文级及机构级结果。

正重合由至少一个可链接的初始本机构作者ID再次出现建立。无重合的判定要求观察名单通过保守完整性屏查：来源论文有观察作者、无缺失作者ID、观察作者均至少具有一个观察机构链接、焦点机构存在本机构作者，并且初始来源集合也满足条件。只有这些观察条件满足且无交集才记unlinked，否则unresolved。该屏查不能证明原数据库没有遗漏作者、错误合并或拆分ID，因而结论始终限于观察名单。补充要求正重合也满足完整元数据，检查结果对规则的依赖。

全部后续linked为Linked-only；观察到linked和unlinked为Mixed（已有两类证据不因其他未定研究而消失）；全部后续unlinked为Unlinked-only；其余Unresolved。空的后续集合不进入作者延续分析。分层使用主随访样本冻结的论文量五分位，不能在1,255家repeat子集中重新分组。

固定篇数敏感性分别取2、3、5篇后续研究，种子20261023，每机构500次不放回抽样。另用组合计数求各类别精确期望，检验模拟实现。既报告每个k各自有足够论文的机构，也报告同一至少5篇机构集合下的k变化，避免分母变化混同篇数机会。所列2.5–97.5%是固定样本内抽样分布，不是总体置信区间，不用于显著性判断。

## 5. 保存、验证与导出

脚本分为prepare、benchmark、initial_models、authors、figures及报告/验证；真实计算保存在代码而不是临时命令行。检查源文件SHA256、机构—研究唯一性、样本流向、初始排除、整数计数、公式重建、参考去重、未知状态、类别分区和论文数守恒。保留导致失败的MLE诊断与所有替代参照，不因方向不符合预期而删去。

以183 mm原生宽度导出PDF/SVG及600 dpi RGB/sRGB PNG、LZW TIFF，不放大旧截图。主图a–b为核心，c/d作为独立扩展，另附明确标识c探索状态的四面板阅读排版。旧Figure 3 v6及其454家活动分布/连续性材料整体保留。ZIP实际解压后核对文件哈希及Markdown相对链接。

软件流程参考：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. [DOI](https://doi.org/10.48550/arXiv.2609.00065)；本轮核对当前arXiv元数据。该参考不是实证数据的来源。作者最终科学审定、期刊格式终审和投稿批准仍待完成。
''')
    (out/'captions_zh_en.md').write_text('''# Figure 3 图注

## 中文

**首次AF发表后的参与延续及其发文机会参照。** a，在2,339家完整且可判定24个月随访的固定基线机构中，首次日期后的两个连续12日历月窗口的四种参与状态。每格面积等于机构数占全队列的比例，格内标人数及百分比；初始日期当天的AF研究不计入后续，至少一个窗口有后续发表的机构另作摘要。b，基线论文量五分位内的实际双窗口参与率（实心实线）与条件独立发文机会基准预期率（空心虚线）；下方为实际−预期百分点差及零线。基准根据已进入机构后续机会研究池中按subfield×日历年份估计的AF比例，结合每个机构两个窗口的整数论文数计算；稀疏类别按预设规则合并。参照跨机构去重，完整设定和留出共享论文检查见Extended Data。没有将该参照解释为因果模型，也未提供模拟置信区间。筛查阴性比较背景不是逐项独立全文验证过的真实非使用。

**扩展c：初始使用方式。** 四类初始记录present/assessed absent的调整后双窗口参与概率及同一可评估样本上的百分点差。灰色线段只连接两种状态的概率点，不表示置信区间。调整前期规模、基线国家、进入年与基线主subfield。四个非惩罚模型均分离，展示预设ridge回退的探索性点估计；95% CI未通过估计/共享论文依赖门槛，不能据此判断显著性。未知不作为absent，四类不互斥，不表示能力深浅等级。该面板未满足作为正式推断主图的条件。

**扩展d：作者延续。** 在1,255家再次发表机构中，按全部后续AF研究是否含初始本机构作者分为Linked-only、Mixed、Unlinked-only及Unresolved，以全部repeat机构或相应冻结基线规模组为分母。无重合要求观察作者名单通过完整性屏查；未知单列，不当作新作者团队。跨机构共享论文的作者不自动归给每家机构。作者重合不证明同一实验室；无重合不证明新团队成立。固定篇数抽样见Extended Data。

## English

**Post-entry participation and a publication-opportunity benchmark.** a, Four mutually exclusive states across two successive entry-relative 12-calendar-month windows among 2,339 fixed-baseline institutions with complete, identifiable follow-up. Cell area encodes the proportion of institutions; counts and full-cohort percentages are printed inside cells. Initial-date studies are excluded from subsequent participation. b, Observed both-window participation (filled markers, solid line) and expected participation under a conditional independent-publication benchmark (open markers, dashed line), by fixed baseline-paper quintile. The lower plot shows observed-minus-expected percentage points. Reference probabilities are estimated by subfield and calendar year from unique studies represented in entered institutions' follow-up opportunities, with prespecified sparse-cell pooling. Institution-level opportunity counts are integer unique studies, not fractional credits. Shared-study leave-out and alternative references are provided. The benchmark is descriptive, not causal; no simulation interval is presented as a confidence interval.

**Extension c.** Adjusted participation probabilities for assessed-absent versus present initial activities. Unknown evidence is excluded rather than labeled absent. All unpenalized models exhibited separation; plotted ridge estimates are exploratory, and dependence-aware 95% CIs are withheld. **Extension d.** Local-author continuity categories among all 1,255 repeat-publication institutions, overall and by baseline-paper quintile. Unlinked observations require complete observed metadata under the stated screen; unresolved cases remain explicit. Neither author overlap nor its absence establishes laboratory identity or team formation.
''')
    (out/'panel_guide_zh.md').write_text('''# 逐面板：图、读者信息、方法与修改原因

| 面板 | 图形与文件 | 读者应获得的信息 | 方法与变化原因 |
|---|---|---|---|
| a | [四状态马赛克图](figures/figure3_core_a_b.pdf) | 首次发表之后，多少机构双窗口参与、只在某窗口参与、或未观察到后续发表 | 成员自身日期；排除初始；统一24日历月；复现2,339/454/1,255。保留原描述形式，新增月级敏感性 |
| b | [实际率／机会预期率与差值](figures/figure3_core_a_b.pdf) | 原始规模梯度与一般发文机会基准是否不同；剩余梯度如何依赖参照 | 新建AF＋背景整数机会表和领域×年份概率；不再只展示原规模热图。比较Q5−Q1实际与预期梯度，不把残差当能力效应 |
| c | [初始方式调整概率](figures/extended_data/figure3c_initial_use_exploratory.pdf) | 不同初始使用证据与后续参与的探索性关联，以及哪些证据尚不足 | 改用全部完整随访中的可评估机构，避免按已持续参与选择样本；MLE分离及依赖门槛使95% CI未完成，明确转为Extended Data |
| d | [本机构作者延续堆叠柱](figures/extended_data/figure3d_author_continuity.pdf) | 初始作者联系、不同本机构作者参与及信息不足各占多少 | 改用全部repeat机构，真实作者—机构关联，保守无重合判定；新增同一机构集合固定后续论文数检查 |

## Extended Data

- [ED01：全部机会参照敏感性](figures/extended_data/ED01_opportunity_reference_sensitivity.pdf)：不可只保留有利的参照设定。
- [ED02：作者／伙伴原始规模梯度](figures/extended_data/ED02_raw_scale_gradients.pdf)：规模相关，不是三种独立资源效应。
- [ED03：初始分类覆盖与未知](figures/extended_data/ED03_initial_activity_assessability.pdf)：未知不能补为未使用。
- [ED04：固定篇数及完整性规则](figures/extended_data/ED04_author_opportunity_and_completeness.pdf)：Mixed受论文数机会影响，分母固定的检查更可比。
- [ED05：日期／窗口敏感性](figures/extended_data/ED05_window_precision_sensitivity.pdf)：日期口径可改变成员与计数，必须显示自身分母。
- [旧454家活动描述及历史补图](previous_figure3_v6/README_zh.md)：保留，不与新c/d混淆。

## 无障碍文字说明

核心图左侧显示四个面积按人数编码的参与状态；右侧实心实际率与空心机会预期率均随规模上升，但主参照预期梯度更陡，下方差值由正转负。c为空心／实心成对概率点，无可发布CI；d为100%分类堆叠，显式包含约三成未定。原始数据表可供不依赖颜色的核对。
''')
    (out/'plan_comparison_zh.md').write_text('''# 新方案要求逐项对照

| 要求 | 状态 | 对应产物或边界 |
|---|---|---|
| 复核2,339与Figure2母样本关系 | 已完成 | complete_cohort、cohort_flow、初始日期一致性检查 |
| 日级／月级两套窗口、排除初始 | 已完成 | 主日级复现旧数；全月敏感性独立重建，使用自身分母，含闰年2月29日边界测试，不猜日期精度 |
| 主样本论文量固定五分位、并列不拆 | 已完成 | quintile_cut_points；作者／伙伴另列 |
| a四状态人数、比例、至少一次后续 | 已完成 | panel_a_participation.csv；核心图a |
| b全部相关领域AF＋背景整数机会表 | 已完成 | 254,033条去重关系；AF计数逐机构复现旧窗口 |
| 领域×年份p_s及预期公式 | 已完成 | field_year_benchmark_rates、机构q1/q2/e_i |
| 实际−预期、剩余Q5−Q1梯度 | 已完成 | panel_b_observed_expected、benchmark_gradient_comparison |
| 留出机构及共享论文、替代参照、粒度检查 | 已完成 | 9套预先指定设定全部保留，未按方向筛选 |
| b可选共享论文模拟带 | 未添加，非必需项 | 主图点值参照不冒充抽样CI；不影响公式与敏感性复现 |
| c仅初始记录、四类多标签、未知不为阴性 | 已完成 | 初始逐研究证据与每机构状态表；不选择454家作为模型队列 |
| c调整国家／年份／领域／规模并输出概率差 | 已完成探索性估计 | 4类主设计、非线性与惩罚敏感性，全部失败诊断保留 |
| c可靠95% CI、正式推断主图 | **未满足，降级Extended Data** | MLE分离，最大共享组19.8%–40.5%，未通过预设条件；CI字段为空且标明原因 |
| 初始分类证据留存及人工验证 | 证据关联完成；新增独立人工验证未实施 | 复用旧动作证据、人工校准与特定接受，不扩称全量人工金标准 |
| d本机构作者ID、全部repeat机构、未知保留 | 已完成观察层面的分类 | 1,255家；332/225/327/371四类，身份消歧完整性不保证 |
| d固定后续篇数机会检查 | 已完成 | 2/3/5篇、500次；同时给组合精确期望与同一≥5篇机构集合 |
| 原活动描述、作者伙伴梯度、缺失检查进ED | 已完成 | 5张新增ED与完整保留的旧版阅读包 |
| Methods、Source Data、字典、图注及代码 | 已完成 | 本包相对链接及源文件哈希核对；作者审定仍待完成 |

本版没有为满足表面完整而给c绘制不可靠的误差条，也没有声称独立人工重新标注过所有初始研究。这两项是实际未满足项，不会标为全完成。
''')
    source_text='''# Source Data / Supplementary Data

全部路径为包内相对链接。表中的NA保持缺失，不替换为零。概率字段使用0–1，percentage与difference_pp使用百分比/百分点；N为机构数，n为整数去重研究数，均不是分数信用。

- [a：四状态](tables/panel_a_participation.csv)
- [b：实际／预期／差值](tables/panel_b_observed_expected.csv)
- [c：初始方式概率与空缺CI状态](tables/panel_c_initial_use.csv)
- [d：逐机构作者分类](tables/panel_d_author_continuity.csv) · [各组份额](tables/panel_d_group_shares.csv)
- [机构分析底表](tables/institution_analysis_base.csv) · [样本流向](tables/cohort_flow.csv) · [窗口敏感性](tables/window_policy_sensitivity.csv)
- [领域×年份概率](tables/field_year_benchmark_rates.csv) · [全部基准设置](tables/benchmark_sensitivity.csv) · [剩余梯度](tables/benchmark_gradient_comparison.csv)
- [初始证据逐记录](tables/initial_activity_evidence.csv) · [分类可评估率](tables/initial_activity_assessability.csv)
- [回归全部诊断](tables/initial_model_diagnostics.csv) · [系数](tables/initial_model_coefficients.csv)
- [作者逐后续论文判定](tables/author_continuity_papers.csv) · [作者元数据完整性](tables/author_work_completeness.csv) · [固定篇数检查](tables/author_fixed_count_sensitivity.csv)
- [大表：全部发文机会Parquet](tables/publication_opportunities.parquet) · [去重基准研究池](tables/benchmark_reference_unique_studies.parquet)
- [数据字典及缺失计数](tables/data_dictionary.csv) · [输入校验哈希](provenance/input_pins.json) · [结果汇总](summary.json)

## 核心字段解释

`institution_id`为OpenAlex机构标识，`study_id`为已批准关联后的研究单元，`source_work_id`/`event_source_work_id`为真实来源版本；不能将来源版本ID与研究ID当作同一单位重复计数。`interval=0`为初始集合，1/2为两个后续窗口。`quintile`在完整主队列冻结，repeat和活动子集中不重算。

`observed`为双窗口AF参与二元结局的机构等权平均，`expected`为机会模型e_i均值，`difference_pp=100(observed−expected)`；`residual_gradient_pp`是Q5差值减Q1差值。`rate_level`记录subfield×年或稀疏池化到年。`label_state`的comparison是操作性背景，不是全量人工非使用金标准。

`initial_state`仅为present/assessed_absent/unassessable；`adjusted_probability`是在同一可评估样本上标准化的探索性概率，不是因果干预效应。`CI_status`解释CI为何留空；空CI不代表零误差。

`link_state`是linked/unlinked/unresolved；机构`category`为Linked-only/Mixed/Unlinked-only/Unresolved。`observed_mapping_complete`是观察到的作者ID与映射一致，不等于现实无漏记或消歧正确。固定篇数的`sampling_p025/p975`是抽样分布位置，不是总体CI；`common_at_least5`在不同k下使用同一机构集合。
'''
    (out/'source_data_zh.md').write_text(source_text)
    # Structured dictionary for every derived table, with complete local missingness counts.
    dictionary=[]
    for p in sorted((out/'tables').glob('*.parquet')):
        if p.stem=='data_dictionary':continue
        df=pd.read_parquet(p)
        for col in df.columns:dictionary.append(dict(table=p.stem,column=col,dtype=str(df[col].dtype),rows=len(df),missing=int(df[col].isna().sum()),
          role='identifier_not_independent_sample_size' if col.endswith('_id') else 'see_source_data_methods_and_protocol'))
    save(out,'data_dictionary',pd.DataFrame(dictionary))
    # Numeric claims are machine-linked, not marked as independently human verified.
    sources=[('E001','tables/panel_a_participation.csv'),('E002','tables/cohort_flow.csv'),('E003','tables/window_policy_sensitivity.csv'),
      ('E004','tables/preparation_audit.csv'),('E005','tables/benchmark_reference_counts.csv'),('E006','tables/panel_b_observed_expected.csv'),
      ('E007','tables/benchmark_gradient_comparison.csv'),('E008','tables/initial_activity_assessability.csv'),('E009','tables/initial_model_diagnostics.csv'),
      ('E010','tables/panel_d_group_shares.csv'),('E011','tables/author_continuity_papers.csv'),('E012','tables/author_fixed_count_sensitivity.csv')]
    dump(out/'provenance/source_manifest.json',dict(status='machine_reconstructed_author_verification_pending',sources=[dict(id=i,path=p,sha256=sha(out/p)) for i,p in sources]))
    claims=[]
    for line in (out/'results_zh.md').read_text().splitlines():
        import re
        m=re.search(r'\[claim:(C\d+)\].*\[evidence:([^\]]+)\]',line)
        if m:claims.append(dict(claim_id=m.group(1),text_sha256=hashlib.sha256(line.encode()).hexdigest(),evidence=m.group(2),status='author_review_pending'))
    pd.DataFrame(claims).to_csv(out/'provenance/claim_evidence.csv',index=False)
    dump(out/'summary.json',dict(complete_cohort=2339,repeat=1255,both_windows=454,
      opportunity_relations=int(prep.set_index('check').loc['opportunity_relations','value']),reference_unique_studies=int(source.all_n.sum()),
      observed_Q1_pct=100*q.loc[1,'observed'],observed_Q5_pct=100*q.loc[5,'observed'],
      main_expected_Q1_pct=100*q.loc[1,'expected'],main_expected_Q5_pct=100*q.loc[5,'expected'],
      main_residual_gradient_pp=gradient.loc['main','residual_gradient_pp'],all_corpus_residual_gradient_pp=gradient.loc['all_corpus_reference','residual_gradient_pp'],
      author_categories=all_d.N.to_dict(),initial_mode_main_CI_released=int((c.variant.eq('main_linear_log_scale')&c.comparison.eq('present')&c.CI_status.eq('released_component_cluster_95CI')).sum()),
      initial_classification_new_independent_human_validation=False,api_calls=0,main_panels=['a','b'],extension_panels=['c_exploratory_no_CI','d_descriptive'],scientific_submission_certified=False))

if __name__=='__main__':write(OUT)
