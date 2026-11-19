"""Portable reading documents, nine direct panel sources and denominator metadata."""
from pathlib import Path
import csv,json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1]
def read(p):
    with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def text(name,s):(ROOT/name).write_text(s.strip()+'\n')
def main():
    src=ROOT/'source_data';src.mkdir(exist_ok=True);tables=ROOT/'tables';tables.mkdir(exist_ok=True)
    panels=[('Figure3','a','Figure3a.csv','All AF2/AF3 entrants, L/M/H','Y','D','supported_pct','D/N separately','Four nonexclusive activities; unknown excluded only from Y/D'),('Figure3','b','Figure3b.csv','Complete 12-month cohort, All/L/M/H','C','N','confirmed_pct','(C+U)/N registered endpoint','All includes unclassified; unresolved events are not a CI'),('Figure3','c','Figure3c.csv','Author-overlap-assessable confirmed repeaters','n','N','percent','n/1312','825 unassessable among 2137 repeaters remain separate'),('ED_use_transitions','a','ED_use_transitions.csv','Category-specific assessable ordered institutional pairs','n10,n01','N','not_reestablished_pct,newly_established_pct','left -n10/N; right n01/N','Different N by activity; negative direction is visual only'),('ED_use_transitions','b','ED_development_cells.csv','Method/tool-development paired institutions','n','N','percent','n/220','Complete 2x2: 96/22/22/80; no use/capability inference')]
    for letter,g in zip('abcd',['All','L','M','H']):panels.append(('S_fixed_windows',letter,'S_fixed_windows.csv','Complete 12-month cohort, '+g,'C','N','confirmed_pct','(C+U)/N registered endpoint','Fixed same N at 3/6/12 months; true calendar-month spacing'))
    mapping=[]
    for fig,panel,source,pop,num,den,value,transform,limits in panels:
        rr=read(ROOT/'plot_data'/source)
        if fig=='S_fixed_windows':rr=[r for r in rr if r['size_group']==dict(zip('abcd',['All','L','M','H']))[panel]]
        dest=src/f'{fig}_{panel}.csv';write(dest,rr)
        mapping.append(dict(figure=fig,panel=panel,source_data=str(dest.relative_to(ROOT)),frozen_plot_source='plot_data/'+source,rows=len(rr),population=pop,numerator=num,denominator=den,value_columns=value,plotted_unit='percent (0–100); net_change_pp separately',transformation=transform,limits=limits,sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
    write(src/'panel_source_map.csv',mapping)
    (src/'panel_metadata.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
    field_defs={'panel_id':('identifier','Stable current panel; old source names are preserved separately'),'source_table':('file','Historical frozen source filename; not a current panel assignment'),'cohort':('category','All combines AF2 and AF3 entrants'),'size_group':('category','Inherited domestic baseline publication group; All includes unclassified'),'activity':('category','Nonexclusive four-activity composite key'),'activity_label':('text','Display label, not capability rank'),'activity_order':('order','Fixed structure/run/development/evaluation order'),'N':('institutions','Entrants, complete follow-up, author-assessable, or paired population, depending on panel'),'D':('institutions','Activity assessable: supported plus assessed not established'),'Y':('institutions','Activity supported among assessable'),'not_established':('institutions','Assessed without supporting evidence, not confirmed non-use'),'unknown':('institutions','N minus D; never imputed as zero'),'C':('institutions','Confirmed strictly later different AF study in the defined window'),'U':('institutions','No confirmed event, but unresolved registered potential event'),'known_no_event':('institutions','No confirmed or unresolved registered event; not proof of non-use'),'months':('calendar months','3, 6, or 12; same complete-12-month cohort'),'author_group':('category','initial_only/mixed/no_initial_overlap among assessable authors'),'author_label':('text','Author-set relation; not a team or diffusion label'),'n':('institutions','Author category or 2x2 evidence cell count'),'repeat_N':('institutions','2137 confirmed repeaters, distinct from author-assessable N=1312'),'n00':('institutions','Both studies assessed not established'),'n01':('institutions','Initial not established, subsequent supported'),'n10':('institutions','Initial supported, subsequent not established'),'n11':('institutions','Both supported'),'initial_evidence':('0/1','0 assessed not established; 1 supported'),'followup_evidence':('0/1','0 assessed not established; 1 supported'),'cell':('identifier','n00/n01/n10/n11'),'supported_pct':('%','100*Y/D'),'assessable_pct':('%','100*D/N'),'confirmed_pct':('%','100*C/N'),'recorded_event_upper_pct':('%','100*(C+U)/N; registered unresolved events only, not CI'),'percent':('%','100*n/N'),'newly_established_pct':('%','100*n01/N'),'not_reestablished_pct':('%','100*n10/N'),'changed_pct':('%','100*(n01+n10)/N'),'net_change_pp':('percentage points','100*(n01-n10)/N')}
    fields=sorted({f for x in mapping for f in read(ROOT/x['source_data'])[0]})
    if any(f not in field_defs for f in fields):raise ValueError('Undefined field '+str(set(fields)-set(field_defs)))
    write(tables/'field_dictionary.csv',[dict(field=f,unit=field_defs[f][0],definition=field_defs[f][1]) for f in fields])
    # Keep source manuscript byte-identical; corrections are suggestions, not silent edits.
    shutil.copy2(ROOT/'manuscript/final_received.txt',ROOT/'results_en.md')
    text('results_zh.md','''# AF使用形式与进入后的机构参与

机构覆盖扩展说明更多机构进入AF研究发表记录，但首次出现不能说明研究如何使用AF。本节区分预计算结构使用、预测运行、方法或工具开发、预测评估或验证四类非互斥活动；它们描述研究中的参与形式，不是能力高低的连续等级。

在首篇研究的预测运行可判定样本中，低发表规模机构127/147（86.39%）有支持证据，高发表规模机构为1848/2048（90.23%）。方法或工具开发相应为48/113（42.48%）与386/1275（30.27%）。低发表规模机构参与的研究并不限于既有结构使用（Fig.3a）。不过，这些比例以活动可判定者为分母；活动属于共同署名的研究，不能据此确定技术工作由哪家机构执行，也不据这些未经调整的比例宣称组间显著差异。

在具有完整12个月行政随访的4955家机构中，2137家确认发表后续不同AF研究，占43.13%。低、中、高组分别为19/176（10.80%）、128/630（20.32%）和1898/3903（48.63%）（Fig.3b）。另外307家只有登记未定事件而无确认事件；若这些登记事件全部确认，总体可达2444/4955（49.32%）。这段延伸范围不是置信区间，也不是所有潜在漏检的总体上界。All保留未分类机构，不能将All与L/M/H当成四个互斥组。

固定同一4955家完整12月队列，3、6、12月的确认再次发表比例为760/4955（15.34%）、1339/4955（27.02%）和2137/4955（43.13%）（Supplementary Note x配套图）。这些是同一观察队列内的累计窗口描述，不是生存估计或模型预测。高规模机构也可能拥有更多相关研究和再次发表机会；没有后续发表不能证明停止使用AF。

逐活动比较固定首篇和首个严格更晚确认研究时，类别特定可判定配对的状态改变率为13.46%—24.90%（Extended Data Fig. x）。开发活动220家配对中，22家后续新建立支持证据，另22家后续未再建立；净差为0.00个百分点，但44/220（20.00%）改变状态。总体份额不变可以同时存在机构证据状态流动；这里观察到的是研究报告证据变化，不是机构能力的获得或丧失。

确认再次发表的2137家中，1312家可以判定目标机构作者集合重叠，占61.39%；825家不可判定。可判定者中，358/1312（27.29%）的后续作者仅来自初始作者集合；119/1312（9.07%）同时包含初始及其他作者；835/1312（63.64%）没有初始机构作者重叠（Fig.3c）。机构再次发表常涉及初始作者之外的研究者，但作者集合不是稳定团队，初始论文未出现者也可能已有AF经验，不能据此证明知识扩散或人员替换。

上述发现分别回答“研究报告什么活动”“是否观察到再次发表”“哪些本机构作者参与后续研究”。活动未知、作者映射缺失及共享研究依赖仍限制解释；四类活动的独立人工语义验证尚未完成，本版保持review状态。

[入口](README_zh.md) · [方法](methods_zh.md) · [图注](captions_zh.md) · [正文数字源表](plot_data/manuscript_claims.csv)
''')
    text('methods_zh.md','''# 方法：AF活动、再次发表与机构作者集合

## 总体、分组与截止

分析单位是机构，在各图定义的有限观察总体内等机构权；一项共同署名研究可以对应多家机构，机构观察并非独立。固定基线是2015—2019适格发表机构，国内L/M/H和N20资格从前节继承，不在AF进入者内重分组。它们表示前期发表规模，不直接测量质量、经费、人员或算力。

AF2/AF3首次进入分析6328家：L332、M972、H4695、未分类329。截止2025-12-31。新增逐ID审计核对52098家基线的国家、发表量、阈值和资格字段与前节一致；Finding2日期队列6369家中的41家Pre-AF2进入者未进入本节，6328个共同ID的日期和阶段一致。这是冻结记录的跨节一致性核对，不是从论文全文重建最早进入日期。详见[逐ID清单](tables/cross_section_ID_audit.csv)和[核验报告](provenance/linkage_review.json)。

## 首篇活动三态与分母

四类非互斥活动的复合原子规则：预计算结构=retrieved_precomputed_structure；运行=ran_alphafold或ran_colabfold；开发=modified_or_extended或developed_downstream_tool；评估=benchmarked_or_evaluated。保留直接AF/ColabFold及方法修改/下游工具子标签；一般生物学实验不自动归为预测评估。复合类别任一组成动作supported即可，quarantine隔离规则优先；组成动作均经评估而无支持才为0。uncertain、not assessed、legacy未列及quarantine保留NA。

N为进入者，Y为支持数，D为可判定数（1+0），未知=N−D。Fig.3a显示100Y/D及独立列100D/N；不用N反推Y/D，不把未知填零，不将四活动比例相加。0是经评估未建立支持证据，不是已证实实际未开展。研究级证据关联共同署名机构，不识别技术执行地点。

## 再次发表与登记事件延伸

以首次AF发表日期t0定义(t0,t0+12日历月]，只纳入截至2025-12-31具有完整行政随访者。C为确认出现严格更晚、不同去重研究的机构；同日记录属于共同初始。U为无确认事件、但有登记可能事件的机构，已确认者不再计入U。N=C+U+known_no_event。

实心点100C/N；细虚线至空心圆100(C+U)/N。延伸只表示已登记事件未定，不是CI、不包含所有漏检、也不校正标签误分类。用途或作者未知不改变4955家随访分母。All含未分类246家（确认92、未定12）；L/M/H不是All的完整划分。无观察发表不等于实际未用或停止使用AF。

补充图固定同一12个月完整队列，All/L/M/H的N为4955/176/630/3903；3、6、12月按真实间距绘制，显示累计确认计数，不分别重新纳入早期窗口队列。

## 活动配对

冻结首篇及首个严格更晚确认、不同去重研究；用稳定study_id处理同日并列，不按资料完整程度或期望结果重选后续。次序不可靠者不进入用途比较；每类分别要求两篇状态均0/1。四类N=526/431/220/852，样本重叠且不要求四类同时完整。n00两篇均未建立，n01后续新建立，n10后续未再建立，n11两篇均支持。总改变率=100(n01+n10)/N，净差=100(n01−n10)/N百分点。左右方向是视觉约定，不是负概率或能力升降；条件延续与条件新建立是不同估计对象，不替换本图总改变率。

## 本机构作者集合

A0/A1仅含实际work中与目标机构关联的author_id，不把整篇多机构作者全部赋给每家机构。两篇身份和本机构映射均可判定、集合非空且次序可靠才分类：initial_only为非空A1⊆A0；mixed为A0∩A1与A1−A0均非空；no_initial_overlap为A0∩A1为空且A1非空。initial_only不要求所有初始作者返回。三条分母1312，825不可判定者单列；无重叠不直接识别新团队、知识扩散或人员替换，上游截断和身份合并错误也不能由观测映射齐全排除。

## 推断、验证与复现边界

12月队列共享研究图最大连通分量2811/4955；连通不等于完全相关，机构也不能全部视为独立。按本次要求不新增模型、bootstrap、CI、p值或显著性声明。用途独立人工验证仍未完成；240项work/960行空白盲评材料不构成新人工金标准，后续论文及关键转变格亦需覆盖。旧AF核心标签验证不替代四活动验证。

本包可以从冻结汇总表重建所有绘图数据和图件；额外冻结的机构级注册表只支持ID/分组/汇总状态核对，不支持从原始论文证据重建标签、去重、身份消歧或日期。旧数据与原稿保持不变。全局ED/补图/Note编号未指定，以稳定描述性名称及原稿占位保留。

[入口](README_zh.md) · [字段字典](tables/field_dictionary.csv) · [英文方法](methods_en.md) · [离线重绘](REPRODUCE.md)
''')
    text('methods_en.md','''# Methods: forms of use and repeat institutional participation

The unit is an institution, weighted equally within each displayed population. Multiple institutions can share a study. Domestic lower/middle/higher groups and N20 eligibility are inherited from 2015–2019 baseline publication output, not reassigned among AF entrants. Output is not a resource, quality or capability score. AF2/AF3 entrants total 6,328 (332/972/4,695 lower/middle/higher and 329 unclassified). The administrative cutoff is 31 December 2025. Cross-section ID checks reconcile 6,369 dated entrants in Finding2 with the present cohort: exactly 41 Pre-AF2 institutions are excluded; shared dates and phases agree. All 52,098 baseline IDs and inherited grouping fields agree. This checks frozen registries rather than reconstructing earliest dates from article evidence.

Four nonexclusive study-level activities are precomputed-structure use (retrieved_precomputed_structure), prediction runs (ran_alphafold OR ran_colabfold), method or tool development (modified_or_extended OR developed_downstream_tool), and prediction evaluation/validation (benchmarked_or_evaluated). A supported constituent suffices, subject to quarantine; zero requires every constituent to have been assessed without established support. Uncertain, not assessed, legacy not listed and quarantined states remain NA. Direct AF versus ColabFold and method modification versus downstream-tool subtypes are retained. General biological experiments do not automatically establish prediction evaluation. N is entrants, D assessable (supported plus assessed not established), Y supported; unknown=N−D. Figure3a separates Y/D from D/N. Neither unknown nor not established is proof of non-use, and coauthored-study evidence does not locate technical execution.

Confirmed repeat publication is a strictly later, different deduplicated AF study in (t0,t0+12 calendar months], among institutions with complete administrative follow-up. Same-day studies form the joint initial event. C counts confirmed repeaters; U counts institutions without confirmation but with unresolved registered potential events. C and U do not overlap, and N=C+U+known_no_event. Filled points show 100C/N; dotted extensions to open circles show 100(C+U)/N. These reflect registered-event uncertainty, are not CIs, do not bound all undetected studies and do not correct label error. Missing activity or authorship does not change the 4,955-institution follow-up denominator. All includes 246 unclassified institutions (92 confirmed, 12 unresolved). A missing publication does not establish stopped AF use.

The supplementary 3/6/12-month comparison keeps the same complete-12-month cohort: N=4,955/176/630/3,903 for All/lower/middle/higher. Calendar-month coordinates use their real spacing; confirmed counts are cumulative and printed above open endpoints. The plot is a window description, not a survival estimate or model prediction.

Activity pairs freeze the initial and first strictly subsequent confirmed different study, with stable study_id tie breaking; no selection is based on evidence completeness or desired outcomes. Uncertain ordering is excluded. Each activity requires assessable 0/1 states at both points, separately: paired N=526/431/220/852. Samples overlap and need not be jointly complete across activities. n00, n01, n10 and n11 denote the two evidence states. Total change is 100(n01+n10)/N, and net change is 100(n01−n10)/N percentage points. A negative plotting direction is a convention, not a negative probability or lost capability. Conditional persistence and newly established evidence have different denominators and do not replace total change.

Author sets A0/A1 include only observed author_id values actually linked to the focal institution on each work. Assessability requires nonempty sets, usable identities/affiliations and reliable order. Initial authors only means nonempty A1⊆A0; mixed requires both A0∩A1 and A1−A0 to be nonempty; no initial-author overlap requires empty intersection and nonempty A1. Not all initial authors need return. Percentages use the 1,312 assessable repeaters; 825 unavailable cases remain separate from the three categories. These sets do not identify stable teams, diffusion, first AF experience or replacement, and observed mapping cannot exclude upstream truncation or identity error.

Shared studies create dependence (largest 12-month graph component: 2,811/4,955); connectivity does not imply perfect correlation. No new models, bootstrap, confidence intervals or significance tests are added. Independent four-activity validation remains pending: 240 works/960 blank rating rows are preparation, not an independent gold standard; follow-up studies and key transition cells require coverage. Core AF-label validation is not activity-label validation. The package supports offline aggregate-table redraw and frozen institution-registry checks, not article-level relabeling, deduplication or author disambiguation. Global ED/Figure/Note numbers retain descriptive names and received placeholders.

[Entry](README_zh.md) · [Sources](source_data/README_zh.md) · [Reproduction](REPRODUCE.md)
''')
    # The supplied English legend already uses the required current panel mapping.
    shutil.copy2(ROOT/'04_英文图注与补充说明.md',ROOT/'captions_en.md')
    text('captions_zh.md','''# 中文图注（review）

**Figure 3｜AF使用形式与后续机构参与。** a，按继承的国内前期发表规模L/M/H组展示初始AF研究中的四类非互斥活动。点为活动可判定进入者中支持比例Y/D；相邻列给百分比及计数，另一列为进入者中可判定率D/N。活动属于共同署名研究，不确定本机构技术执行。b，完整12个月行政随访机构中确认再次发表比例。实心点C/N，细虚线延至空心圆(C+U)/N；U为没有确认事件而有登记未定可能事件者。这不是CI，也不涵盖全部可能漏检。All包括未分类机构。c，2137家确认再次发表机构中1312家作者重叠可判定者的本机构作者构成：仅初始作者、初始及其他作者、无初始作者重叠；三条都以1312为分母。仅初始作者允许部分初始作者未返回；825不可判定者单列，不计作无重叠。作者集合不直接识别稳定团队或知识传播。无推断区间。四活动独立人工语义验证仍待完成。

**Extended Data Figure [TBD]｜首篇及首个后续AF研究的活动证据变化。** a，每类分别纳入两次状态可判定、次序可靠的机构。左条为首篇支持但后续未再建立n10/N，右条为后续新建立n01/N；条内显示计数，右列为配对N、总改变率和净差百分点。负方向只是作图约定，四类分母不同。b，方法或工具开发220家配对的完整四格，96/22/22/80，各格百分比占220。双向各22，总改变44/220=20.00%，支持比例净差为0.00pp。未建立证据不是已证实未开展，研究证据变化也不证明能力获得或丧失。独立活动验证未完成。

**Supplementary Figure [TBD]（配套Supplementary Note [TBD]）｜固定机构队列的3、6和12个月再次发表。** a–d分别为All/L/M/H，同一完整12月队列N=4955/176/630/3903在各时间点保持不变。实心点及实线为确认累计比例；细虚线和空心端点包含登记未定事件，不是CI；端点上方C/N只表示确认计数。x用真实月份距离，y统一0—60%。All包括未分类机构。本图不是不同进入队列、模型预测或生存估计；未观察后续论文不等于停止使用AF。

[入口](README_zh.md) · [全部直接源表](source_data/README_zh.md)
''')
    text('alt_text_en.md','''# Figure descriptions

Figure3: Three panels. Panel a plots four initial-study activities for lower, middle and higher baseline-output institutions on a 0–100% assessable-sample scale, with distinct marker shapes and separate Y/D and D/N columns. Prediction-run support is 86.39% for lower and 90.23% for higher; development support is 42.48% and 30.27%, respectively. Panel b shows confirmed 12-month repeat publication: All 43.13%, lower 10.80%, middle 20.32%, higher 48.63%; dotted extensions include unresolved registered events rather than confidence intervals. Panel c uses 1,312 author-assessable repeaters, showing initial authors only 27.29%, mixed 9.07%, and no initial-author overlap 63.64%; 825 unavailable cases are separate. Review status remains because independent activity validation is pending.

ED_use_transitions: Four diverging horizontal pairs use their own assessable denominators. Left is initial support not re-established; right is newly established support. The development table contains 96 initially/finally not established, 22 newly established, 22 not re-established and 80 supported at both points. Total state change is 20.00% despite zero net difference. Negative direction is visual only; evidence states are not capability levels.

S_fixed_windows: Four panels All/lower/middle/higher show confirmed repeat-publication percentages at months 3, 6 and 12 in unchanged complete-12-month cohorts. Time spacing is proportional to months. All rises from 15.34% through 27.02% to 43.13%; all groups show cumulative increases. Open endpoints include registered unresolved events, not confidence intervals. Missing observed publication does not establish non-use.
''')
    text('panel_guide_zh.md','''# 逐面板读者信息、方法与图位变更

|当前面板|读者应获得的信息|方法与来源|相对旧图位的处理|
|---|---|---|---|
|Figure3 a|低规模机构参与的研究也报告运行和开发；Y/D限可判定者|四非互斥活动×三组，独立显示D/N；[源表](source_data/Figure3_a.csv)|保留旧3a四活动，不只挑运行/开发|
|Figure3 b|12个月确认再次发表有规模梯度；未知范围非CI|完整行政随访，All含未分类；[源表](source_data/Figure3_b.csv)|保留旧3b，不因用途/作者缺失缩分母|
|Figure3 c|机构重复参与与初始作者延续不同|三类n/1312；另列825不可判定；[源表](source_data/Figure3_c.csv)|旧3d移至新3c，旧3c不能沿用名称|
|ED a|双向证据改变与净改变不同|n10/N、n01/N各类独立N；[源表](source_data/ED_use_transitions_a.csv)|旧3c移出主图，不能称能力升级|
|ED b|净差0也有44/220状态改变|开发完整2×2，96/22/22/80；[源表](source_data/ED_use_transitions_b.csv)|补足开发四格，避免只看净值|
|S a|总体同队列累计窗口描述|N4955、C760/1339/2137；[源表](source_data/S_fixed_windows_a.csv)|旧S4以稳定描述性名字交付|
|S b|低组同队列窗口描述|N176、C10/12/19；[源表](source_data/S_fixed_windows_b.csv)|不另选3月/6月队列|
|S c|中组同队列窗口描述|N630、C39/78/128；[源表](source_data/S_fixed_windows_c.csv)|不画未验证CI|
|S d|高组同队列窗口描述|N3903、C682/1193/1898；[源表](source_data/S_fixed_windows_d.csv)|不称因果、模型或停止使用|

主图180×190mm，a全宽、b/c并列；扩展180×155mm；补充180×145mm。按用户既有偏好仅面板字母，无长面板标题；列标题、坐标、组别及分母说明保留。严格采用目录颜色/形状，未以Finding2新配色替代。本次把登记上端统一为空心圆，避免被误认成另一个组别点。

[入口](README_zh.md) · [图注](captions_zh.md) · [方法](methods_zh.md)
''')
    text('manuscript/reference_mapping.md','''# 旧新图位映射与原文保留

旧Fig3a→新Fig3a（四活动及可判定率）；旧Fig3b→新Fig3b（12月再次发表）；旧Fig3c→ED_use_transitions；旧Fig3d→新Fig3c（本机构作者集合）；旧Fig3e不纳入本次定稿；旧S4→S_fixed_windows。旧ED5年度贡献、ED6合作/标准化和ED7作者×开发仅保留来源索引，不增加核心结论，不重新占用编号。

原稿逐字存于[final_received.txt](final_received.txt)，[英文Results](../results_en.md)保持相同字节；中文Results是对应解读。收到稿中的Methods Mx、Extended Data Fig. x、Supplementary Note x及sustained participation标题保留；操作性结局使用repeat publication，不改为sustained capability。ED/补充图/Note编号待全稿统一。

原文小笔误只列建议，不自动修改：both counts towards→both count towards；assessable in both points→assessable at both points；Reported publication by an institution→Repeated publication by an institution；lower-out institutions→lower-output institutions；different information前句的逗号/and可供作者润色。

[精确旧新映射CSV](../plot_data/panel_map.csv) · [逐条正文数字](../plot_data/manuscript_claims.csv) · [入口](../README_zh.md)
''')
    text('open_items_zh.md','''# 状态与剩余事项

|事项|本版状态|
|---|---|
|三图九面板、直接源数据、正文/方法/图注|本轮实际生成与验证；机器检查及视觉记录另见provenance|
|6369→6328的41家差额|已逐ID核对，全为Pre-AF2；共同ID日期/阶段一致|
|继承基线分组|52098家ID及发表量/国家/阈值/资格字段与前节一致；是冻结注册表核对，不重建原始基线|
|四活动独立人工验证|仍未完成；240项work/960行盲评材料不是人工金标准；不能删除review|
|独立验证后续工作|需要实际独立标注，覆盖稀有活动、0状态、后续研究和关键转变格；现有核心AF验证不替代活动验证|
|共享研究依赖|仍存在；不增加未经验证CI、bootstrap、p值或因果解释|
|全稿ED/补图/Note编号|保留占位和稳定名称，不擅占ED5/6/7|
|原文小笔误|原稿未改，建议与图位映射一起列明|
|当前投稿技术规范|按明确尺寸/字体/原生分辨率验收，不冒称期刊已技术预审或接收|

[入口](README_zh.md) · [图位和文字建议](manuscript/reference_mapping.md)
''')
    text('REPRODUCE.md','''# 离线复现

依赖Python、reportlab==4.4.9、Pillow==12.3.0、pypdf==6.10.0；PDF栅格化使用Poppler的pdftoppm。实际解释器、字体和路径记录于provenance/software.json。程序不安装软件或联网；SVG保留文字，需要Arial或Helvetica等可用字体。

从包内数据在**不存在的新目录**执行：`python code/replay.py --package-root /解压包根 --output-root /新目录 --pdftoppm /本机/pdftoppm`。程序重建九份plot_data、跨节ID核对、阅读文件、三组图和新的数值/PDF检查；不调用项目数据库、API或LLM，不重标注、去重或选择研究。已有240/960独立活动验证仍待实际人工完成。

仅核验：`python code/verify.py`、`python code/prepare_linkage.py`、`python code/inspect_pdfs.py`、`python code/verify_release.py`；这些脚本将当前检查报告写入本包provenance。建议先复制一份，保护已发布归档。重绘后的独立人类语义验证、全稿编号和期刊技术预审不由代码自动完成。

[入口](README_zh.md) · [依赖](requirements.txt)
''')
    data='\n'.join(f'- [{r["figure"]} {r["panel"]}]({Path(r["source_data"]).name})：{r["population"]}；{r["rows"]}行。' for r in mapping)
    text('source_data/README_zh.md','# 九面板直接源数据\n\n'+data+'\n\n[映射与分母](panel_source_map.csv) · [机器元数据](panel_metadata.json) · [字段字典](../tables/field_dictionary.csv) · [全部历史汇总表](../tables/README_zh.md) · [入口](../README_zh.md)\n\nY/D与D/N分开，C/N与登记(C+U)/N分开，作者分母1312。百分比由精确计数计算，源表保留未舍入值；四活动不可加总。')
    tablelinks='\n'.join(f'- [{p.name}](../source_inputs/tables/{p.name})' for p in sorted((ROOT/'source_inputs/tables').glob('*.csv')))
    text('tables/README_zh.md','# 表格与原始汇总索引\n\n'+tablelinks+'\n\n[字段字典](field_dictionary.csv) · [跨节6369行ID核对](cross_section_ID_audit.csv) · [41家Pre-AF2排除](Pre_AF2_excluded_41.csv) · [进入组别计数](entry_group_ID_counts.csv) · [正文主张](../plot_data/manuscript_claims.csv) · [当前图位](../plot_data/panel_map.csv) · [入口](../README_zh.md)\n\n原始panel_denominator_dictionary使用旧图位；当前权威以本版panel_map和source_data元数据为准。')
    figlinks=[]
    for n in ['Figure3_review','ED_use_transitions_review','S_fixed_windows_review']:
        figlinks.append(f'- **{n}**：[PDF](figures/{n}.pdf) · [可编辑文字SVG](figures/{n}.svg) · [预览](figures/{n}.png) · [600dpi PNG](figures/{n}_600dpi.png) · [600dpi LZW TIFF](figures/{n}_600dpi.tiff)')
    text('README_zh.md','''# Finding 3 v7 阅读入口

严格按2026-10-28交接定稿生成：主图a首篇四活动、b十二个月再次发表、c本机构作者集合；用途转变移至扩展图；固定3/6/12月队列比较为补充图。共三组九面板，图内保留review。原交接包、旧数据、旧代码与原稿均未覆盖。

## 图件

'''+ '\n'.join(figlinks)+'''

## 正文、方法与逐面板解读

[中文Results](results_zh.md) · [收到的英文Results原文](results_en.md) · [中文Methods](methods_zh.md) · [English Methods](methods_en.md) · [中文图注](captions_zh.md) · [English legends](captions_en.md) · [Alt text](alt_text_en.md) · [逐面板读者信息](panel_guide_zh.md)

[旧新图位与原文建议](manuscript/reference_mapping.md) · [开放项与完成边界](open_items_zh.md)

## 数据、方法记录与验收

[九面板Source Data](source_data/README_zh.md) · [全部表格索引](tables/README_zh.md) · [配置](analysis_config.json) · [新算术核验](provenance/verification_report.json) · [跨节ID及分组核验](provenance/linkage_review.json) · [PDF及分辨率检查](provenance/pdf_qa.json) · [本轮发布检查](provenance/release_checks.json) · [本轮实际视觉复核](provenance/visual_review.md) · [离线复现](REPRODUCE.md)

本版补清了41家Pre-AF2跨节差额与继承分组一致性。活动独立人工验证仍未完成；现有240项work/960行空白盲评不构成金标准。算术/图件检查不能认证语义准确性或因果效应。登记未定范围不是CI；作者无重叠不是团队扩散。全稿ED/补充图/Note编号保留占位，不占其他章节编号。

根目录01—07及provenance/historical保留收到的要求/历史记录，原先开放项与旧PASS是历史状态；本轮状态见上方新报告与open_items。source_inputs内两篇旧中文说明以.md.source.txt逐字节存档，避免旧稿中未包含的历史分析链接混入当前导航；更新的输入清单保留原路径和同一哈希。活动定义、分母、配对和标签未重做，无API或LLM费用。
''')
    print('Nine panel sources, bilingual documents and reading entry prepared',flush=True)
if __name__=='__main__':main()
