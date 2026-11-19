"""Evidence-linked bilingual prose, four tables and panel-level source-data contracts."""
import shutil
from common import *

def pct(v):return f'{100*v:.2f}%'
def main():
    a=load('Fig3a_entry_uses');b=load('Fig3b_repeat12');c=load('Fig3c_use_transitions');d=load('Fig3d_author_groups');j=load('Fig3e_author_use');ctx=load('ED6c_partner_context');std=load('standardized_estimates')
    primary=c.query('cohort=="All" and size_group=="All"');author=d.query('cohort=="All" and size_group=="All"')
    def ar(g,m):return a[a.cohort.eq('All')&a.size_group.eq(g)&a.activity.eq(m)].iloc[0]
    def br(g):return b[b.cohort.eq('All')&b.size_group.eq(g)].iloc[0]
    partner=ctx.query('cohort=="All" and size_group=="L" and activity=="method_or_tool_development" and entry_state=="1" and partner_class=="confirmed_H_partner"').iloc[0]
    unknown=ctx.query('cohort=="All" and size_group=="L" and activity=="method_or_tool_development" and entry_state=="1" and partner_class=="partner_unknown"').iloc[0]
    dev=j[j.activity.eq(MODES[2])].set_index('author_group')
    title='# Finding 3：进入后的用途、再次发表与作者组合\n\n'
    text=title+'''本版按v6重组。以下均为既有冻结语料内的描述性结果；用途指机构参与研究报告的活动，不定位机构实际执行者。图中只有面板字母，说明置于图注。独立用途验证尚未完成，未给出未经依赖校正认证的CI或p值。

## 1. 首次用途：低产出进入者并非只参与结构下载

'''
    text+='首次进入已定位者6,328家，其中L/M/H为332/972/4,695家，未分类329家。低组首篇预测运行证据为127/147（86.39%），方法/工具开发为48/113（42.48%）；高组分别为1,848/2,048（90.23%）和386/1,275（30.27%）。这是各类别可判定者内比例，并不能据此认定低组开发能力更高。方法开发可判定率L为113/332（34.04%），H为1,275/4,695（27.16%）；其他未知仍保留。\n\n'
    text+='进入期标准化采用类别特定共同支持人群的统一权重，实际结果见[标准化表](tables/standardized_estimates.csv)；共同支持之外不外推。所有首篇用途的极端未知范围见[S5底表](tables/S5_extreme_missing_bounds.csv)，范围不能纠正已判定标签的误分类。\n\n'
    text+='## 2. 再次发表：12个月内仍有规模差异\n\n完整12个月行政随访4,955家，确认再次发表2,137家（43.13%）；307家事件未定，登记未知范围上端为49.32%。这不是CI，也不覆盖所有未发现研究。\n\n'
    for g in ['L','M','H']:
        row=br(g);text+=f'- {g}：{row.C}/{row.N}，确认比例{pct(row.fraction)}；未定{row.U}家，范围上端{pct(row.upper)}。\n'
    text+='\n用途或作者缺失不改变该分母。窗口内未观察到再次发表不等于停止使用AF。\n\n## 3. 净差小不等于用途没有变化\n\n'
    text+='| 用途 | 配对N | 后续新建立 | 后续未再建立 | 总改变率 | 净差（百分点） |\n|---|---:|---:|---:|---:|---:|\n'
    for label,row in zip(LABELS,primary.set_index('activity').loc[MODES].itertuples()):text+=f'| {label} | {row.N} | {row.n01} | {row.n10} | {pct(row.change_rate)} | {row.net_change_pp:+.2f} |\n'
    text+='\n方法开发新增22家、后续未再建立22家，净差为零，但44/220=20%的机构改变证据状态。这里的0表示经评估未建立证据，不能命名为实际停止该活动或能力退步。L组四类配对只有4/6/3/13家，因此不作为稳定的后续规模比较。\n\n## 4. 机构再次发表不等于初始作者继续参与\n\n'
    for k,label in zip(AUTH,AUTH_LABELS):
        row=author[author.author_group.eq(k)].iloc[0];text+=f'- {label}：{row.n}/{row.N}（{pct(row.fraction)}）。\n'
    text+='\n作者可判定1,312/2,137（61.39%），其余825家没有被归入“无初始重叠”。“仅初始作者”允许部分初始作者不返回；“其他作者”只是未在首篇目标机构集合出现，不代表新雇员或此前未用AF。\n\n## 5. 作者—用途关联需要区分方向\n\n'
    text+=f'方法开发用途：仅初始作者组延续{int(dev.loc["initial_only","n11"])}/{int(dev.loc["initial_only","retention_N"])}（{pct(dev.loc["initial_only","retention"])}），无初始重叠组为{int(dev.loc["no_initial_overlap","n11"])}/{int(dev.loc["no_initial_overlap","retention_N"])}（{pct(dev.loc["no_initial_overlap","retention"])}）；新建立分别为6/36（16.67%）与7/40（17.50%）。因此原始改变率差异的线索主要涉及后续未再建立开发证据，而非后者更多新增开发。\n\n'
    text+='这组开发比较的mixed分母很小；按三作者组同时要求每个共同支持格至少10家时，进入期标准化不满足支持，未输出调整后开发比例。其它可支持结果和不支持格全部见[共同支持表](tables/common_support_cells.csv)。[147条开发配对记录](tables/ED7_development_record_audit.csv)已重核作者集合与子动作来源，但尚未完成新的独立人工语义认证。不能将该线索解释为作者更替导致能力流失或证明知识扩散。\n\n'
    text+='## 6. 低组开发活动的合作背景\n\n'
    text+=f'L组48家首篇参与研究报告方法开发的机构中，{partner.n}/48（{pct(partner.fraction)}）有确认H伙伴，涉及{partner.work_N}项不同首篇研究；单一研究最多贡献{partner.max_single_work_institutions}家L机构。其余{unknown.n}/48伙伴背景未定。没有据缺失资料判为“无H伙伴”或“单机构”。这是共同署名背景，不证明高组实际开发、低组外包或资源依赖。\n\n'
    text+='## 7. 增长背景、敏感性与限制\n\nED5沿用全机构—研究计数，保留Unknown，与主图固定基线机构等权不是同一分母。窗口比较固定4,955家；日期、同日并列/合并、证据来源、共同可用、机构规模和大型共同研究等敏感性均保留底表。\n\n'
    diag=json.loads((OUT/'provenance/dependency12.json').read_text())
    text+=f'12个月全窗口依赖图包含{diag["components"]:,}个连通分量，最大分量{diag["largest_component"]:,}/{diag["N"]:,}（{100*diag["largest_fraction"]:.2f}%）。连通不等于完全相关，但不能把机构对直接当独立样本。没有运行新的bootstrap或显著性检验。\n\n'
    text+='独立验证已生成240项唯一首篇work、960行空白用途盲评材料；尚未收到新人工标签。冻结元数据没有模型/数据库参考文献ID，引用代理交叉核验尚不能完成。本轮未下载新证据，未运行付费LLM。期刊/引用历史结果不属于本版Finding 3主结论。\n'
    (OUT/'results_zh.md').write_text(text)
    en='''# Finding 3: Forms of participation and subsequent institutional engagement

Among 6,328 institutions with resolved AF2/AF3-era entry, the L/M/H groups contained 332/972/4,695 institutions; 329 were unclassified. Initial prediction-run evidence was supported for 127/147 assessable L institutions (86.39%) and 1,848/2,048 H institutions (90.23%). Method/tool-development evidence was supported for 48/113 (42.48%) and 386/1,275 (30.27%), respectively. These are category-specific assessable subsets, not estimates of local capability. Their unequal and incomplete coverage precludes ranking all institutions by these rates.

Of 4,955 institutions with complete 12-calendar-month administrative follow-up, 2,137 had confirmed repeat publication (43.13%). An additional 307 had unresolved registered events, yielding an identification upper endpoint of 49.32%, not a confidence limit. Confirmed repeat fractions were 19/176 (10.80%), 128/630 (20.32%), and 1,898/3,903 (48.63%) for L/M/H.

Category-specific ordered pairs numbered 526/431/220/852 for structures/runs/development/evaluation. Method/tool development had 22 newly established and 22 not re-established evidence states: zero net difference concealed a 20% total state-change fraction. Evidence not established does not demonstrate real-world non-use.

Local author sets were assessable for 1,312/2,137 repeat institutions: 358 had only initial-set authors, 119 mixed initial/other authors, and 835 no initial-set overlap. In the development subset, conditional retention was 31/34 versus 7/22 for initial-only versus no-overlap authors, whereas new establishment was 6/36 versus 7/40. These small, selected risk sets do not establish a causal author effect. Simultaneous three-author-group era standardization for development lacked common support under the prespecified denominator rule; no extrapolated adjusted rate was reported.

Of 48 L institutions whose initial studies reported development, 46 (95.83%) had a confirmed H partner, spanning 36 distinct studies; two had unknown partner context. Coauthorship does not identify the institution that performed development. All findings are descriptive. New independent four-use annotation remains pending, and no validated dependence-aware confidence intervals or p-values are released.
'''
    (OUT/'results_en.md').write_text(en)
    # Actual, executed Methods, with explicit uncompleted validation components.
    methods='''# Finding 3 Methods：v6实际执行口径

## M1 总体、规模与单位
复用Fig2 2015—2019至少一项适格研究的52,098家固定基线机构及原国内L/M/H与N20资格。按institution_id连接，不在AF进入者内重分组。主分析等机构权，未分类保留总体。机构参与研究的活动不等于各机构本地执行。

## M2 去重、事件及分期
复用批准study_id与真实成员work的机构关联及日期，不将另一版本的较早日期拼接到新机构集合。分析截止2025-12-31；AF2-era自2021-07-01、AF3-era自2024-05-01；这些是发表进入时期，不是实际模型版本。未知与可能更早事件沿用冻结规则。对3/6/12个月逐ID复核既有表；并实际重建月末日期、时期界限整体前移/后移一个日历月敏感性。

## M3 非互斥用途与三态
结构=retrieved_precomputed_structure；运行=ran_alphafold OR ran_colabfold；开发=modified_or_extended OR developed_downstream_tool；评估=benchmarked_or_evaluated。保留原子子标签；ColabFold不改写为直接运行AlphaFold。隔离优先；任一组成动作supported为1，所有组成动作均经评估not_established才为0，其余NA。旧未列动作不是0。一般实验验证不自动等同AF评估。四类不构成能力深度分数。
独立验证：实际生成分层work级240项、960行空白盲评表；按规模暴露、进入期、证据来源、文献类型、稀少0/开发优先标志分层，层内无放回抽样，种子20261026，抽样概率及还权已归档。没有新独立人工标签，未估计混淆/准确率；模型辅助接受记录不作为新金标准。冻结元数据缺参考文献ID，模型/数据库引用代理交叉核验未完成。

## M4 再次发表与资格
窗口为(t0,t0+12日历月]，月底截断。完整行政窗口不晚于截止。严格晚于t0的不同确认研究计再次发表；同日为共同初始。repeat=true在有确认事件时保留；无确认但登记可能事件为NA；其余false。C/N及(C+U)/N以全部完整随访者为分母，不按用途或作者完整性删人。范围只涵盖登记事件未知，不是CI。

## M5 固定配对
每机构唯一初始及第一篇严格更晚的确认研究，study_id稳定处理同日并列，不按资料完整或结果挑选。未定事件可能早于所选后续时排除顺序明确配对分支，但保留其确认重复状态。替代设定实际执行排同日并列、月末重建与共同初始合并；合并初始用途和作者并集是不同估计对象。合并用途隔离优先、任一正向为1、全经评估负向为0、余未知；作者并集须所有构成work可靠。

## M6 用途转变
按类别取两篇均0/1且次序明确的机构，不要求四类同时可判定。四格n11/n10/n01/n00和为N；新建立n01/N、后续未再建立n10/N、总改变(n01+n10)/N、净差100(n01−n10)/N。条件延续n11/(n11+n10)，条件新建立n01/(n00+n01)，风险集不同。净差不等于总改变，0不证明真实行为不存在。

## M7 目标机构作者集合
仅使用实际work中author_id—institution_id关联；不将全篇作者归给每个机构。两篇观测作者身份完整、观测作者集与机构映射集一致、本地作者集合非空且顺序可靠才可判定。A0/A1交集非空且A1−A0空为initial_only；两者非空为mixed；交集空且A1非空为no_initial_overlap。initial_only不要求所有初始作者返回。映射完整是观测层检验，不能认证OpenAlex无截断或身份合并错误。

## M8 合作承载、共同支持与标准化
完整伙伴映射来自所有事件work的历史机构关联及完整Fig2固定基线，不只来自进入者。确认H伙伴优先；其余依观测作者/机构关联完整性区分单机构、完整无H多机构与未知。基线外/未分类伙伴不当无H已知伙伴；无法确认原始截断情况保留局限。
直接标准化在每个比较组每格分母至少10家时定义共同支持，不按事件有无挑选。目标为对应类别可判定者在共同支持格的合并机构总体；权重为该目标的格占比，同一比较所有组使用同权重。6a比较规模组的首篇用途；6b在各规模/总体比较首篇1/0的确认再次发表及登记未知上端。先报告原始/时期分层，再给时期统一权重结果。国家共同支持及等国家权另列，后者是另一估计对象。
ED7分别在首篇0/1内检查进入期、首篇本机构作者数(1/2—4/5+)、两篇间隔(1—92/93—183/184—366日)、L/M/H/未分类及联合分层。无支持格不预测；mixed不合并；小格保留计数。未使用稀疏多参数因果模型。

## M9 缺失、选择、依赖与敏感性
首篇各用途报告D/N可判定率、Y/D支持比例、Y/N确认下端及(Y+N−D)/N极端未知上端。范围不纠正误分类、不是CI；覆盖率相近不意味着随机缺失。分别比较纳入/未纳入用途、作者配对的首篇构成。
3/6/12月纯窗口比较固定完整12月同一4955家；6→12新增分原6月已知无事件和原6月未定。实际执行四用途共同可用、显式overlay来源、两篇article/review、完整单机构、同日规则和日期、N10/N30及25%/75%替代切点、国内基线连续百分位分箱、同国家/等国家权、共同研究规模限制和初始研究标准化权重敏感性。
依赖图使用12个月内全部确认及可能事件关联，不只选中两篇；无日期事件依年份范围保守纳入。逐研究连接所有目标机构、诊断分量和大合作研究。连通并非完全相关；本版没有验证可用的抽样推断，未运行bootstrap、p值、独立Wilson或将旧工程阈值当统计定理。

## M10 产品、复现和解释
每面板归档analysis_id、窗口、目标总体、分组、权重、分子分母、未知/排除、证据版本、输入hash。四格、作者组、共同窗口单调、配对选择与图文数字一致性有自动验收。研究活动不等于机构能力；再次发表不等于所有持续使用；作者不同不等于知识传播。期刊位置、引用变化及一般发表机会benchmark未纳入本finding必做分析。

## 软件与工作流辅助
Python环境沿用项目锁；具体版本记录在provenance/software.json。使用Data analysis、Statistical analysis、Scientific visualization和Scientific writing技能辅助代码与图文审核。技能方法来源：Kassis T, Agarwal V, He Y, Patel D, Brueckner AM (2026), *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*, [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065)，2026-10-26核对当前记录。该文是软件工作流说明，不是本研究实证证据。
'''
    (OUT/'methods_zh.md').write_text(methods)
    (OUT/'methods_en.md').write_text('''# Finding 3 Methods

## M1 Population and scale
The fixed 2015–2019 institutional baseline and within-country integer-output L/M/H groups were inherited from Finding 2; groups were not re-estimated among AF entrants. Institutions received equal weight; unclassified institutions remained in overall estimates.

## M2 Study identity, dates and eras
Approved study/version links and actual member-work affiliations/dates were retained. The administrative cutoff was 31 December 2025. AF2/AF3 entry-era boundaries were July 2021 and May 2024; eras do not identify the model used. Event rules were reconstructed and checked institution by institution against frozen 3/6/12-month records.

## M3 Nonexclusive uses and validation
Four categories mapped to retrieved structures, AF/ColabFold execution, model modification/downstream-tool development, and benchmarking/evaluation. Quarantine takes precedence; any supported constituent yields one, all assessed not-established constituents yield zero, and other states remain missing. Zero denotes evidence not established, not proven non-use. A stratified work-level 240-work/960-row blinded validation design was exported; no new independent human annotations or accuracy estimates were available. Reference-ID proxy cross-checks could not be executed from the frozen metadata.

## M4 Twelve-month repeat publication
The window was (t0,t0+12 calendar months], with calendar-month truncation. Same-day studies were co-initial, not repeat events. Confirmation overrides additional uncertainty; otherwise registered possible events yield unknown. Both C/N and (C+U)/N use the complete administrative cohort; these identification endpoints are not CIs.

## M5 Fixed study pairs
Initial and first strictly later confirmed distinct studies were selected by date and stable study-ID ties, without outcome/completeness-based reselection. Uncertain ordering excluded paired branches but not confirmed-repeat status. Same-day exclusions, month-end dates and co-initial unions were distinct sensitivity specifications.

## M6 Transitions
Each use had its own ordered two-assessable-state sample. Four cells n11/n10/n01/n00 defined total change (n01+n10)/N, net change 100(n01−n10)/N, conditional retention n11/(n11+n10), and conditional new establishment n01/(n00+n01).

## M7 Local author sets
Only stable author IDs linked to the target institution on each selected work were used. Observed work-level identity/mapping completeness and nonempty local sets were required. Initial-only, mixed and no-initial-overlap author sets were retained separately; unknown sets were not assigned no overlap.

## M8 Collaboration and standardization
All observed work affiliations were joined to the complete Fig2 baseline mapping. Confirmed H partners were distinguished from observed-complete single-institution studies, complete non-H collaborations, and unknown contexts. Direct standardization used identical pooled category-specific common-support weights for compared groups. Strata required at least ten institutions per group, irrespective of outcomes. Era, country and author-opportunity composition checks were executed; unsupported cells were not extrapolated.

## M9 Missingness and dependence
Assessability and extreme missing-state bounds were reported separately. Window comparisons used the same 4,955 complete-12-month institutions. Robustness included evidence source, date/tie rules, common-use availability, single-institution studies, scale cutpoints/weights, and large shared studies. Dependence diagnostics included all confirmed/possible within-window study links, not just selected pairs. No unvalidated confidence intervals, bootstrap results or p-values were released.

## M10 Reproducibility and limits
Panel-specific numerators, denominators, targets, weights, evidence versions and input hashes were archived. Activity in a coauthored study does not locate institutional execution; author turnover does not establish diffusion. Historical venue positions and citation changes were outside this finding's required scope. Workflow assistance used Scientific Agent Skills (Kassis et al., 2026; https://doi.org/10.48550/arXiv.2609.00065); this is a software-method reference, not empirical evidence.
''')
    # Canonical source files and four supplementary table contracts.
    panel_sources={'Fig3a':'Fig3a_entry_uses','Fig3b':'Fig3b_repeat12','Fig3c':'Fig3c_use_transitions','Fig3d':'Fig3d_author_groups','Fig3e':'Fig3e_author_use','ED5a':'ED5_annual_cohort_output','ED5b':'ED5_annual_cohort_output','ED5c':'ED5_growth_contributions','ED6a':'ED6a_era_entry_uses','ED6b':'ED6b_entry_use_repeat','ED6c':'ED6c_partner_context','ED7a':'ED7_conditionals','ED7b':'ED7_conditionals','ED7c':'standardized_estimates'}
    panel_sources.update({'S1a':'S1_flow','S1b':'S1_state_missingness','S2a':'S2_evidence_coverage','S2b':'S2_single_institution_entry','S3a':'S3_cooccurrence','S3b':'S3_complete_combinations','S4a':'S4_common_windows','S4b':'S4_delayed','S5a':'S5_use_sensitivity','S5b':'S5_extreme_missing_bounds','S6a':'S6_author_opportunity','S6b':'S6_author_opportunity','S7a':'S7_continuous_scale','S7b':'S7_dependency_components'})
    panel_sources['S2c']='S2_reference_action_crosscheck'
    targets={'Fig3a':'all resolved AF2/AF3 entrants; category-specific assessable denominator','Fig3b':'complete 12m administrative cohort','Fig3c':'category-specific ordered paired evidence','Fig3d':'author-assessable repeat institutions','Fig3e':'author and category-specific ordered intersection'}
    registry=[];estimates=[]
    for panel,table in panel_sources.items():
        q=load(table)
        if panel=='S7b':q=q.groupby('component').size().rename('institutions').reset_index().sort_values('institutions',ascending=False)
        q['analysis_id']=q['analysis'] if 'analysis' in q else q['setting'] if 'setting' in q else 'main_calendar_12m' if not panel.startswith('ED5') else 'all_institution_output'
        if panel=='ED7c':q=q[q.analysis_id.str.startswith('ED7c_')].copy()
        if 'target_population' not in q:q['target_population']=targets.get(panel,'panel-specific population; see methods and native denominator fields')
        if 'weighting' not in q:q['weighting']='equal institutions' if not panel.startswith('ED5') else 'full institution-study count'
        q['evidence_version']='approved action layer v1 + frozen legacy + accepted candidate core';q['window_months']=q['months'] if 'months' in q else 12 if not panel.startswith('ED5') else np.nan
        q.to_csv(OUT/'source_data'/f'{panel}.csv',index=False)
        registry.append(dict(panel=panel,source_file=f'source_data/{panel}.csv',table=table,rows=len(q),target_population=targets.get(panel,'see native source and Methods'),CI='not released'))
        for row in q.to_dict('records'):
            for metric in ['fraction','coverage','change_rate','new_rate','not_reestablished_rate','net_change_pp','retention','new_establishment','n00','n01','n10','n11','share','institution_study_count','change','share_of_net_growth']:
                if metric not in row:continue
                N=row.get('D') if panel in ['Fig3a','ED6a'] and metric=='fraction' else row.get('retention_N') if metric=='retention' else row.get('new_N') if metric=='new_establishment' else row.get('retained_N') if panel=='ED7c' else row.get('N')
                n=row.get('Y') if panel in ['Fig3a','ED6a'] and metric=='fraction' else row.get('C') if panel in ['Fig3b','ED6b'] else row.get('n11') if metric=='retention' else row.get('n01') if metric in ['new_establishment','new_rate'] else row.get('n10') if metric=='not_reestablished_rate' else row.get('n')
                if metric=='change_rate':n=row.get('n01',0)+row.get('n10',0)
                if metric=='coverage' and panel in ['Fig3a','ED6a']:n=row.get('D');N=row.get('N')
                if metric=='coverage' and panel=='Fig3d':n=row.get('N');N=row.get('repeat_N')
                if metric in ['n00','n01','n10','n11']:n=row[metric];N=row.get('N')
                if metric=='share':n=row.get('institution_study_count');N=row.get('annual_total')
                if metric in ['institution_study_count','change']:n=row[metric];N=None
                if metric=='share_of_net_growth':n=row.get('change');N=row.get('total_net_growth')
                estimates.append(dict(panel=panel,metric=metric,numerator=n,denominator=N,estimate=row[metric],unit='percentage_points' if metric=='net_change_pp' else 'count' if metric in ['n00','n01','n10','n11','institution_study_count','change'] else 'proportion',target_population=row['target_population'],weighting=row['weighting'],evidence_version=row['evidence_version'],analysis_id=row['analysis_id'],activity=row.get('activity'),size_group=row.get('size_group'),author_group=row.get('author_group'),cohort=row.get('cohort'),entry_state=row.get('entry_state')))
    save('F3_T3_all_estimates',pd.DataFrame(estimates));save('panel_denominator_dictionary',pd.DataFrame(registry))
    t1=load('S1_state_missingness');t1['record_type']='use_state_missingness'
    flow=load('S1_flow');flow['record_type']='sample_stage';rep=b.copy();rep['record_type']='repeat_event_status';au=d.copy();au['record_type']='author_availability'
    save('F3_T1_samples_missingness',pd.concat([t1,flow,rep,au],ignore_index=True))
    t2=load('S2_dictionary').copy();t2['independent_validation']='240 works sampled; unannotated';t2['accuracy_estimated']=False;save('F3_T2_dictionary_validation',t2)
    t4=std.copy();t4['record_type']='standardized_estimate';t4['inferential_interval']='not validated; not estimated'
    ss=load('S5_use_sensitivity');primary_keys=c[['cohort','size_group','activity','net_change_pp','change_rate']].rename(columns={'net_change_pp':'primary_net_change_pp','change_rate':'primary_change_rate'})
    ss=ss.merge(primary_keys,on=['cohort','size_group','activity'],validate='many_to_one');ss['difference_from_primary_pp']=ss.net_change_pp-ss.primary_net_change_pp;ss['record_type']='pairing_sensitivity'
    cc=load('common_support_cells');cc['record_type']='support_cell';ww=load('standardization_weights');ww['record_type']='standardization_weight'
    extra=[]
    for table in ['S7_cutpoint_eligibility','S7_large_collaboration_sensitivity','S7_repeat_initial_weighting','S4_common_windows','S4_period_sensitivity']:
        z=load(table);z['record_type']=table;extra.append(z)
    save('F3_T4_support_sensitivity',pd.concat([t4,ss,cc,ww,*extra],ignore_index=True))
    # Copy the full supplied instruction tree so its own relative links also work offline.
    shutil.copytree(PLAN,OUT/'instructions',dirs_exist_ok=True)
    guide='''# 图注与逐面板读者信息

所有面板以可溯源模型辅助活动标签为基础；独立四用途人工验证未完成。比例的n/N、未知和证据覆盖见Source Data。各用途可同时成立，not_established不等于证实没有使用；这些图不证明因果、能力升级或知识扩散。

| 图/面板 | 图中编码及读者应获得的信息 | 分母及解释边界 |
|---|---|---|
| 3a | 四用途×L/M/H的已建立证据比例，旁列可判定覆盖率；进入者并不只有一种参与形式 | 全6328进入者；每类可判定N不同；总体/未分类留底表；不是能力排名 |
| 3b | 12个月确认再次发表比例与登记未定上端 | 完整4955；点为C/N，点线界限至(C+U)/N，非CI |
| 3c | 新建立与后续未再建立的双向比例，区别总改变和净差 | 每类526/431/220/852固定配对；左右共用N；不是升级/退步 |
| 3d | 机构重复参与与初始作者集合延续的区别 | 作者可判定1312/2137；仅初始、混合、无初始重叠三组；未知不并组 |
| 3e | 作者三组与用途改变率的对应 | 各格作者×相应用途交集；标改变数/N；不推断作者因果作用 |
| ED5a—c | 进入队列对年度产出、份额和增长贡献 | 全机构研究关系全计数，Unknown独立；不是主图固定机构分母 |
| ED6a | 分进入期看规模与用途的对应 | 相同四用途、各类N与覆盖在底表；时期不是模型版本 |
| ED6b | 同规模中首篇用途1/0与再次发表的对应 | 完整12月中相应首篇可判定者；未知用途和事件规模单列 |
| ED6c | L组首篇supported研究的合作承载背景 | 完整Fig2伙伴映射；单机构/确认H/完整无H/未知；不定位谁实际执行 |
| ED7a | 首篇已有证据的后续延续 | n11/(n11+n10)，按作者三组 |
| ED7b | 首篇未建立证据者的后续新建立 | n01/(n00+n01)，与a的风险集不同 |
| ED7c | 共同进入期标准化后的条件率 | 无共同支持格留空，详细构成和支持在T4；没有外推复杂模型 |

**Figure 3 caption.** Forms of AlphaFold participation and subsequent institutional engagement. (a) Initial-use evidence and assessability by inherited domestic baseline-output group. (b) Confirmed repeat publication within twelve calendar months; dotted registered-event identification ranges are not confidence intervals. (c) Category-specific paired transitions distinguish newly established from not re-established evidence. (d) Target-institution local author-set combinations among assessable repeating institutions. (e) Use-state changes within each author combination. Uses overlap; evidence not established does not demonstrate real-world non-use. Studies can contribute to multiple institutions, and no unvalidated inferential intervals are displayed.

**Extended Data 5 caption.** Annual institution–study output, composition and 2021–2025 growth contribution by bounded entry era, retaining Unknown. Full institution–study counting differs from equal-institution main-panel denominators.

**Extended Data 6 caption.** Initial uses by entry era and scale; registered-event repeat-publication proportions by initial-use state and scale; and observed partner context of L institutions whose initial study supports each use. All categories are nonexclusive. Confirmed H partnership is not proof of the location of technical execution. Exact denominators, unknowns, coverage and standardized analyses are in source data.

**Extended Data 7 caption.** Author-specific conditional evidence retention, conditional new establishment and common-era standardized conditional proportions where supported. Three author groups are retained. Unsupported cells are blank and are not imputed.

## 补充图图注与读者信息

- S1：一次性展示样本路径和类别信息可用性；选入/未选入者特征见同名表，不把缺资料当未参与。
- S2：实际证据来源与完整单机构限制结果；验证包是设计，尚未标注，不把该图误读成准确率认证。
- S3：非互斥首篇共现和四类共同可判定者的组合；不是能力阶梯。
- S4：同一4955家机构的窗口路径与6→12月新增，分清原6月无事件和原6月未知；时期边界敏感性见底表。
- S5：日期/同日/证据来源/共同可用改变下的用途净差，以及未知用途极端界限；共同初始合并是不同估计对象。
- S6：作者组首篇本机构作者数和配对时间机会；不能将不同观察机会的原始率直接当作者因果作用。
- S7：细化的国内基线连续百分位分箱与共享研究依赖；替代切点、国家权重、大合作和重复首篇影响见T4配套表。分量不是独立样本认证。
'''
    (OUT/'panel_guide_zh.md').write_text(guide)
    requirements=[('主图a—e','completed','figures/main/Figure3_a_e_preview.png'),('12个月底表与旧表逐ID一致','completed','provenance/preparation.json'),('ED5','completed','figures/ED5/Extended_Data_Figure5_preview.png'),('ED6a/b及进入期标准化','completed_with_sparse_cells','tables/standardized_estimates.csv'),('ED6c完整固定基线伙伴映射','completed_observed_mapping_limit','tables/ED6c_partner_context.csv'),('ED7a/b','completed_descriptive','tables/ED7_conditionals.csv'),('ED7c共同支持/标准化','executed_unsupported_cells_retained','tables/common_support_cells.csv')]
    requirements += [(f'S{i}','executed_descriptive',f'figures/S{i}/F3_S{i}_'+suffix+'_preview.png') for i,suffix in enumerate(['sample_and_coverage','evidence_and_attribution','nonexclusive_cooccurrence','windows_and_uncertainty','pairing_and_missingness','author_opportunity','scale_and_shared_studies'],1)]
    requirements += [('四用途独立人工验证','pending_human_annotations','validation_materials/README_zh.md'),('模型/数据库引用代理核验','blocked_missing_reference_ID_field','tables/S2_proxy_field_audit.csv'),('12个月相关性推断','diagnosed_no_validated_CI_released','provenance/dependency12.json')]
    requirements=[(r,'executed_observed_reference_proxy' if r=='模型/数据库引用代理核验' else s,p) for r,s,p in requirements]
    save('requirements_status',pd.DataFrame(requirements,columns=['requirement','status','evidence']))
    (OUT/'compliance_zh.md').write_text('# v6要求对应与未完成事项\n\n'+ '\n'.join(f'- **{r}**：{s}。[证据]({path})' for r,s,path in requirements)+'\n\nT1/T2/T3/T4及M1—M10已输出。S2独立标签、引用代理核验和有效CI未被标成完成；没有因结果方向换主图。原期刊和引用结果保留在旧版，不恢复为本finding必做分析。\n')
    readme='''# Finding 3 v6 阅读入口

主线：进入时用途与科研规模 → 12个月再次发表 → 用途转变 → 作者组合与用途转变。作者审阅稿，独立用途验证待完成；没有新付费调用。

- [主图PDF](figures/main/Figure3_a_e.pdf) · [主图预览](figures/main/Figure3_a_e_preview.png)
- [中文Results](results_zh.md) · [英文Results](results_en.md)
- [中文Methods M1—M10](methods_zh.md) · [英文Methods](methods_en.md)
- [图注与逐面板读者信息](panel_guide_zh.md) · [要求对应及未完成项](compliance_zh.md)
- [ED5](figures/ED5/Extended_Data_Figure5.pdf) · [ED6](figures/ED6/Extended_Data_Figure6.pdf) · [ED7](figures/ED7/Extended_Data_Figure7.pdf)
- [样本及缺失T1](tables/F3_T1_samples_missingness.csv) · [分类及验证T2](tables/F3_T2_dictionary_validation.csv)
- [全部估计T3](tables/F3_T3_all_estimates.csv) · [共同支持及敏感性T4](tables/F3_T4_support_sensitivity.csv)
- [各panel分母及source data索引](tables/panel_denominator_dictionary.csv) · [Source Data](source_data/)
- [独立人工验证待办材料](validation_materials/README_zh.md)
- [原始v6要求](instructions/README.md) · [实际分析配置](analysis_config.json)
- [验证报告](validation_report.json) · [代码](code/)

期刊位置及引用比较未进入本版主图。解压后请保留目录结构，所有本地链接均使用相对路径。独立panel矢量/600dpi图位于figures/main/；所有补充组位于figures/S1/至S7/。

离线绘图：在项目兼容Python环境运行 `python code/draw.py --package-root . --output-root /新的空输出目录`。完整原始底表重建仍需源项目，不声称ZIP包含所有原始数据库。
'''
    (OUT/'README_zh.md').write_text(readme)
    with (OUT/'methods_zh.md').open('a') as f:f.write('\n既有100篇/900动作人工校准资料已做来源哈希核验；其中24篇属于本轮首篇work，但旧材料用于随后口径调校，因此不能作为当前规则的新独立测试。新增盲评抽样排除这些旧校准与185项命名修订涉及的首篇work；抽样总体及排除数见验证包登记，不能把还权结果外推到排除记录。\n')
    with (OUT/'methods_en.md').open('a') as f:f.write('\nThe existing 100-work/900-action human calibration archive was inventoried and hash-checked; 24 works overlapped current first events. Because these cases informed subsequent policy tuning, they were not treated as a new independent test of current rules. The new blinded sample excludes known historical calibration and named accepted-revision cases; inverse-probability estimates would apply only to the remaining sampling population.\n')
    replacements={
      '冻结元数据没有模型/数据库参考文献ID，引用代理交叉核验尚不能完成。':'首层分析底表不含引用ID，但本次补读72份本地参考文献Parquet，已完成模型/数据库种子引用代理与活动三态的交叉核对。没有记录匹配不等于证实未引用；种子引用参与过候选发现，因此不是独立分类准确性验证。',
      '冻结元数据缺参考文献ID，模型/数据库引用代理交叉核验未完成。':'首层底表缺引用ID，本次实际补读72份本地参考文献Parquet及冻结四种子登记，执行模型/数据库引用代理交叉核验；无记录匹配不是已证明未引用。该代理参与过候选发现，不是独立金标准，不替换动作标签。',
      'Reference-ID proxy cross-checks could not be executed from the frozen metadata.':'Observed model/database seed-reference proxies were reconstructed from 72 local reference shards and the frozen four-seed registry and cross-tabulated with action states. Missing recorded matches do not prove absence of citation. These proxies participated in candidate retrieval and are not independent accuracy validation.',
      'S2独立标签、引用代理核验和有效CI未被标成完成':'引用代理核验已用本地参考文献分片补做；S2独立人工标签仍待完成，有效CI未被标成完成'
    }
    for name in ['results_zh.md','methods_zh.md','methods_en.md','compliance_zh.md']:
        path=OUT/name;content=path.read_text()
        for old,new in replacements.items():content=content.replace(old,new)
        path.write_text(content)
    t2=load('F3_T2_dictionary_validation');t2['reference_proxy_crosscheck']='executed from 72 local reference shards; not independent accuracy validation';save('F3_T2_dictionary_validation',t2)
    with (OUT/'README_zh.md').open('a') as f:f.write('\n补充证据入口：[实际用途证据正反例](tables/S2_actual_evidence_examples.csv) · [原子子类型](tables/S2_atomic_subtypes.csv) · [种子引用与动作交叉表](tables/S2_reference_action_crosscheck.csv) · [依赖与共同研究诊断](provenance/dependency12.json)。\n')
    with (OUT/'methods_zh.md').open('a') as f:f.write('\n可得元数据扩展：另从本地原始派生works分片核对首篇的宽field映射；同一work存在冲突则不指派field。实际执行进入期×文献类型及进入期×宽field的6a/6b共同支持标准化，小格不外推，缺协变量人数单列；结果和权重进入T4及common_support_cells/standardization_weights表。国内连续基线位置的图采用五个固定百分位区间展示，连续原值另存；每类可判定子样本中同一初始study的机构权重和为1。\n')
    with (OUT/'methods_en.md').open('a') as f:f.write('\nAvailable-metadata extensions used original local derived work shards to recover broad fields; conflicting field IDs were left unassigned. Era-by-type and era-by-broad-field standardization was executed for ED6a/b with covariate-missing counts retained. Initial-study normalized weighting was recalculated within each category-specific assessable sample. The domestic continuous-scale visualization used five fixed percentile bins, with unbinned values archived.\n')
    print('Bilingual Results/Methods, captions, reader guide, T1–T4 and source-data registry written',flush=True)
if __name__=='__main__':main()
