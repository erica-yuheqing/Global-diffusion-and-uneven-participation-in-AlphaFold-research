"""Evidence-linked bilingual text and panel/source-data maps for v7."""
from common import *
import csv,re,shutil
from figures import NAMES

def write(out,name,text):
 p=out/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(text.strip()+'\n')

PANEL_MAP=[('Figure1a','Figure1b_upper.csv'),('Figure1b_raw','Figure1b_lower.csv'),('Figure1b_matched','Figure1c.csv'),('ED1','Figure1a.csv'),('ED2a','ED1a.csv'),('ED2b','ED1b.csv'),('ED2c','ED1c.csv'),('ED3a','Figure1d.csv'),('ED3b','ED2b.csv'),('ED3c','ED2a.csv')]+[(x,x+'.csv') for x in ['S1a','S1b','S1c','S2a','S2b','S2c','S3a','S3b','S4a','S4b','S5a','S6a','S6b','S6c','S6d']]
MESSAGES=[
('Figure1a','AF自身Gini下降，但仍高于同期non-AF。','固定227国、研究1/k信用；1,000轮条件整研究bootstrap。','旧主图b上半部移至主a；2021–2025；放大轴由S6a补全尺度。'),
('Figure1b_raw','原始差距确实缩小，约65.9%净收窄发生于2021–2022。','同年AF−non-AF；原始bootstrap带；端点差沿用配对重复汇总。','与匹配差距合并同轴，灰色菱形；不再独立另图放大。'),
('Figure1b_matched','匹配后的观察序列未持续收窄；不等于正式证明不收敛。','同年×primary subfield×类型无放回；AF固定，2,000轮中央95%匹配范围。','紫色虚线圆点与原始差距同轴；非完整CI。'),
('ED1','候选不等于应用；研究自身应用证据决定纳入。','初始检索与补检独立侧支；双yes、平台排除、批准study关联。','旧主a移至ED1并精简，完整审计另见S1。'),
('ED2a','首次观察覆盖的空间次序，不是真实采用时刻或模型版本。','首次发表阶段；归档Natural Earth；无坐标不猜位置。','旧ED1a重编号；注册集合外与未观察分开。'),
('ED2b','累计覆盖从14到123到143；2020前1国保留在基数。','72个月累计step曲线、阶段边界。','旧ED1b移至ED2b；不用平滑线。'),
('ED2c','新增速度有时间差异；累计143与2025活跃128不同。','每月首次观察国家整数数目，与b共享月度窗口。','旧ED1c移至ED2c；无双轴或2026观测。'),
('ED3a','CN与GB相对位置改变，不能由R下降推出绝对论文减少。','固定基线前十；ALL分母含AF；log2真实R刻度；无新增CI。','旧主d移至ED3a；不按结果选国家。'),
('ED3b','动态top5份额接近，top10略降，不代表成员或内部份额不变。','每年独立排名，已知国家信用为分母。','旧ED2b移至ED3b；不混固定十国。'),
('ED3c','固定国家对已归属AF产出的构成如何变化。','固定全期AF前十加Other；credit/known_AF_studies。','旧ED2a移至ED3c；不画Unknown段，国家名完整列出。'),
('S1a','publication records、works和批准关联后的studies依次区分。','5个原始计数节点及其时期、单位。','完整审计而非主图塞满流程。'),
('S1b','初始29,127与额外826/765不是单链递减漏斗。','补检179已审、586后审，556 A/B及516 C路由。','独立分支，28证据不足和2超大明确保留。'),
('S1c','74个positive works仅净增73项studies。','765互斥处置=74+159+1+531；16341+70+3=16414。','非采用、平台、未知不画入positive筛选箭头。'),
('S2a','150参考样本中122可判定、28不确定。','参考route×state原始计数；作者报告判读先于模型答案。','不声称独立留出或全量泛化认证。'),
('S2b','最终生产标签在pilot确定参考中的对应情况。','2×3矩阵；precision103/105、候选内recall103/103。','历史ensemble另表，未知不作TN。'),
('S2c','错误与未知类型使用各自分母，不能跨行相加。','证据未决24/150、一致未知4/150；误报2/122、预测未知2/122。','不把候选内recall称为检索recall。'),
('S3a','年度AF研究从2021的393到2025的5573。','整数study数；2020仅11。','不以稀疏2020宣传倍数。'),
('S3b','AF与适格研究的学科构成不同。','各自全期分母，固定AF前五加Other。','22适格学科与21非零AF学科区分。'),
('S4a','AF每年由哪些学科组成。','年度AF总数分母；固定五学科加Other，100%组成。','与学科内AF比例分图。'),
('S4b','各学科的适格研究中多少为AF。','AF/eligible；Other先合并计数再相除。','完整132格保留在Table S3。'),
('S5a','国别R年度路径，端点不证明中间年份单调。','基线前20加Other；log2 R中心1；Other合并207国信用。','零/未定义不同；颜色饱和不改真值。'),
('S6a','2020稀疏与完整尺度对理解主图很重要。','2020–2025；Gini轴0–1；标2020 n=11。','主a放大显示的全尺度诊断。'),
('S6b','匹配规格影响比较条件。','count-only、composition、known-country三种；统一轴。','主图只保留composition，其余移到诊断。'),
('S6c','起点变化和条件匹配范围限制端点解释。','三规格×两起点共6行；逐重复端点差定义沿用。','跨零不是等效；原draws缺失不冒充独立复现。'),
('S6d','国家归属覆盖不同会限制地理比较。','2020–2025 AF/C各自归属率；2025为95.46%/78.59%。','已知归属限制不等于恢复真实地理分布。')]

RESULTS_ZH='''# 地域扩展与产出集中程度的变化

我们先从国家层面观察AlphaFold（AF）研究的地域范围，再区分“更多国家参与”与“发表产出在国家之间更均匀”这两个问题。研究库包含2020–2025年16,414项AF-use studies，涉及22个适格生命科学subfields中的21个。关键词与种子论文引用仅用于召回候选；纳入还要求摘要或正文证据表明，AF模型或预测结构用于研究自身的方法、分析、实验、开发或评估。仅引用、背景或未来计划不成立，证据不足保留未知（ED1；S1–S2）。

累计参与从AF2阶段前的14个国家/地区增至2024年4月的123个，并在2025年12月达到143个；2025年当年有产出的国家为128个。首次观察按发表日期确定，不是实际采用时刻；阶段也不认证逐篇研究使用的模型版本（ED2）。

在固定227个国家/地区、包含零产出的口径下，每项研究向其k个已知唯一国家各分配1/k信用。AF产出的Gini由2021年的0.9421降至2025年的0.9253，表明集中度有所下降；同期non-AF保持在约0.90，AF仍更集中（Figure 1a）。原始AF−non-AF差距从0.0415缩小至0.0271，变化为−0.0144，条件95%整研究bootstrap区间为[−0.0232,−0.0105]（Figure 1b）。约65.9%的净收窄发生在2021–2022；2023和2025有小幅反向变动，不能概括为2022之后完全没有继续收窄。

数量、学科与文献类型也影响可比性。沿用同年×primary subfield×document type分层无放回匹配、每年2,000次且AF固定的结果，匹配差距依次为0.0168、0.0212、0.0253、0.0180、0.0194；观察序列未呈现持续收窄（Figure 1b）。紫色误差线表示固定AF后的中央95%匹配范围，与原始差距的条件bootstrap区间不同；不能依靠区间重叠检验差异，也不能据范围跨零证明等效。

总体集中程度并不代替国别位置。国别相对AF强度R定义为国家AF信用份额除以其适格发表信用份额；适格分母包含AF。R=1为相对发表基数的同比例参照，不是公平或能力标准。固定基线十国中，中国R从0.43升至0.59但仍低于1，英国从2.56降至1.71但仍高于1（ED3a）。完整年度路径见S5；这些端点不证明单调变化，也不意味着英国AF论文数量下降。年度动态top5份额约61.4%→61.4%，top10约76.3%→74.4%；固定十国构成使用另一套预先声明的国家集合，不与年度排名混用（ED3b–c）。

这支持的表述是：地域覆盖扩大与AF原始集中度下降、国别相对位置变化并存，但相对于匹配non-AF研究未观察到持续的差距收窄。数据不能确定2025年以后的最终格局，也不能识别AF发布的因果效应。国家归属覆盖差异仍在，2025年AF为95.46%、non-AF为78.59%（S6d）。接下来应观察国家内部机构参与，而非把国家结果替代机构层面的证据。

[阅读入口](../README_zh.md) · [方法](Methods_M1_M2_zh.md) · [图注](captions_zh_en.md)
'''

METHODS_EN='''# Methods M1–M2: data, identification and country-level comparisons

## M1 Corpus construction and AF-use identification
The frozen OpenAlex corpus contains 6,046,663 publication records from 2015–2025 in 22 eligible life-science primary subfields. The original bulk download was completed during the week containing 3 April 2026; this presentation update does not refresh the snapshot. Article/review/preprint eligibility yields 4,686,896 works. Approved links reduce this to 4,686,894 original study units and subsequently 4,686,879 units after 15 further duplicate-member removals. The 2020–2025 eligible scope comprises 2,714,594 studies, including 16,414 AF-use studies in 21 nonzero subfields. Version links do not automatically propagate use labels or backdate institutional participation.

Initial keywords and citations to AF2, Multimer, AFDB and AF3 retrieved 29,127 candidate work records. AF1 belongs to supplementary retrieval, not a fifth initial seed. Supplementary retrieval identified 826 leads, of which 765 were eligible works; these form a separate branch, not a subset to subtract sequentially from the initial candidate count. Final supplementary dispositions were 74 use, 159 non-use, one platform and 531 uncertain works. Seventy-four positive works produced 73 net additional studies: 16,341 + 70 + 3 = 16,414.

Evidence packets used abstracts or available full texts. Independent production models A/B evaluated the same frozen packet; disagreements, unknowns and exceptions were routed to C and targeted human review. In the remaining supplementary set of 586, 556 were A/B-eligible (154 full-text and 402 abstract packets); 28 lacked sufficient evidence and two exceeded the packet limit. C reviewed 516 routed works. C is not an automatic gold standard. No new calls or adjudications were made for this release.

Inclusion required explicit evidence that AF models or predicted structures were used in the study's own analysis, methods, experiments, development or evaluation, with both af_use_label=yes and adoption_eligible=yes; platform resource papers were excluded. Citation, background or prospective use alone did not establish use. Unknown evidence remained unknown, rather than being assigned negative labels.

The historical pilot contains 150 deliberately selected candidate works. Of these, 122 references were resolved, 24 remained evidence-unresolved and four had uncertain consensus. The 122 resolved references were compared with original production-final two-yes labels using a 2×3 matrix retaining uncertain/missing predictions separately. Precision was 103/105 and candidate-level positive recall 103/103; historical ensemble precision/recall were 100/101 and 100/103, reported separately. Candidate recall is not corpus retrieval recall. The author reported that human judgement preceded viewing model answers; independent held-out status, absence of calibration involvement and incremental-production generalizability remain unconfirmed. Unknown predictions are not true negatives.

## M2.1 Publication eras and first observed participation
Publication-date eras are pre-AF2 through June 2021, AF2 July 2021–April 2024 and AF3 May 2024–December 2025. The main monthly window begins January 2020 and retains one previously observed country in its cumulative baseline. Monthly cumulative values are drawn as steps without smoothing. Milestones denote July 2021 AF2 code/AFDB availability and May 2024 AF3 publication/server availability, not AF3 code release. First publication is not actual adoption and era does not certify model version. The archived Natural Earth base map and archived small-region positions are reused. Unlocated RE retains its statistical count without invented coordinates. Cumulative participation is 143 by December 2025; 128 countries were active during 2025.

## M2.2 Country credits and comparison pools
For each study with k observed unique countries, each country receives 1/k credit, preserving complete coauthorship country sets. Gini coefficients use 227 fixed countries/regions, including zeros. Completely unknown geography creates no 228th country and is not redistributed. Non-AF denotes the frozen Figure1 screen-negative C pool, not all eligible studies minus AF, nor a corpus of independently certified negatives. Supplementary candidate works are removed from C rather than treating uncertain labels as non-use.

## M2.3 Gini coefficients and raw differences
For sorted nonnegative country credits x_i and n=227, G=Σ(2i−n−1)x_i/(nΣx_i); zero total is undefined. Raw differences are D_t=G_AF,t−G_nonAF,t. Annual and endpoint summaries retain the archived 1,000-replicate whole-study bootstrap. Conditional percentile intervals reflect sampling of observed studies with their full country sets; they do not include label error, missing geography or longitudinal author/team dependence. Endpoint differences use paired replicate values, not subtraction of marginal interval endpoints. The 2021–2025 raw change is −0.0144273, with conditional interval [−0.0232282,−0.0104707]. Figure1a expands the axis to 0.89–0.96; S6a retains 2020–2025 on a 0–1 axis, including sparse 2020 n=11.

## M2.4 Conditional matching
The main specification samples non-AF studies without replacement within publication year × primary subfield × document type, matching AF study counts in each target stratum. AF output is held fixed for 2,000 samples per year. Unsupported strata are not filled from other strata. Geography itself is not matched. E_t=G_AF,t−mean_r(G_nonAF,t,r matched). Central 95% ranges describe matched non-AF sampling with AF fixed, not full confidence intervals. Count-only and known-country composition specifications are retained in S6b. Endpoint ranges follow archived replicate-difference definitions and are not tests of equivalence.

This release reuses the 45 frozen CSVs exactly, including handoff annual/endpoint matching summaries. Original handoff draw-level samples and seeds are absent from the lightweight source package. Algebraic identities and support can be checked, but original matching quantiles are not independently reproduced. Previously generated local audit simulations are not substituted for handoff estimates; no new seed is selected or fitting performed.

## M2.5 Composition and missing attribution
AF and eligible subfield compositions have separate denominators. The full-period AF top-five subfields are fixed over time, with remaining subfields pooled as Other. AF/eligible rates for Other use summed numerator/denominator counts, not mean subfield rates. Full 22×6 counts remain in Table S3. Country-attribution coverage is reported separately; 2025 values are 5,320/5,573=95.46% for AF and 78.59% for C. Known-geography restrictions do not restore unobserved true geography.

## M2.6 Relative AF intensity and country selection
R_ct=(A_ct/A_t)/(T_ct/T_t), where A is attributed AF country credit and T attributed credit of all eligible sampled life-science research, including AF. R=1 is proportional representation relative to this base, not fairness or capability. A=0 with T>0 remains zero; T=0 is undefined and no pseudocount is added. ED3a uses the fixed 2015–2019 eligible-credit top ten (US/CN/JP/DE/GB/IN/FR/KR/IT/CA), with open 2021 and filled 2025 points on a log2 axis labelled in R units. S5 uses the baseline top20 plus Other, pooling 207 remaining countries' A/T rather than averaging ratios. Colour saturates at R≤0.25 and R≥4 without truncating source values. NA denotes Namibia, not missing data.

ED3b ranks countries independently each year for top5/top10 shares. ED3c instead fixes the 2020–2025 AF-credit top ten (US/CN/DE/GB/FR/JP/CA/IT/ES/IN), plus Other. Both use attributed AF credit as denominator; ED3c uses attributed_fraction rather than the older all-study fraction and includes no Unknown country segment. No country-specific CI, trend test or causal release effect is added.

## Presentation and numbering
The release contains one two-panel main figure, three ED, six supplementary figures and five table suites, with original full-precision CSVs, provenance and portable redraw code. Supplementary/ED numbers are mapped for manuscript integration; archived later-section outputs remain unchanged. All uncertainty is conditional descriptive uncertainty, not a certification of dependence-robust or causal inference. Physical dimensions and 600dpi exports are checked but do not certify publisher acceptance.
'''

def write_documents(out,source,prior):
    mapping=[]
    for new,old in PANEL_MAP:
        src=out/'inputs/source_data'/old;dest=out/'source_data'/f'{new}.csv';shutil.copy2(src,dest)
        # Keep all numeric strings at their original precision while appending provenance.
        with src.open(newline='',encoding='utf-8-sig') as handle:
            reader=csv.DictReader(handle);rows=list(reader);fields=reader.fieldnames
        for row in rows:
            row.setdefault('source','frozen_v7/inputs/source_data/'+old)
            if 'interval_type' not in row:
                row['interval_type']='conditional_95pct_whole_study_bootstrap_1000' if new in ['Figure1a','Figure1b_raw','S6a'] else 'not_applicable_descriptive_counts_or_ratios'
        with dest.open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=fields+[x for x in ['source','interval_type'] if x not in fields]);writer.writeheader();writer.writerows(rows)
        mapping.append({'new_panel':new,'input':'inputs/source_data/'+old,'source_data':'source_data/'+new+'.csv','rows':len(pd.read_csv(src,keep_default_na=False))})
    pd.DataFrame(mapping).to_csv(out/'provenance/panel_input_mapping.csv',index=False)
    for f in (out/'inputs/tables').glob('*.csv'):shutil.copy2(f,out/'tables'/f.name)
    for new,old in [('raw_annual_Gini.csv','Figure1b_upper.csv'),('raw_annual_gap.csv','Figure1b_lower.csv'),('main_matched_gap.csv','Figure1c.csv')]:shutil.copy2(out/'inputs/source_data'/old,out/'tables'/new)
    suites={1:['Table_S1_process_nodes','Table_S1_seed_references','Table_S1_subfield_scope','Table_S1_milestones'],2:['Table_S2_design','Table_S2_pilot_metrics','pilot_confusion','pilot_reference_states','pilot_comparison_records'],3:['Table_S3_subfield_year'],4:['Table_S4_country_year_R_first_observation','normalization_country_selection','first_observed_stage_map_source'],5:['raw_annual_Gini','raw_annual_gap','main_matched_gap','concentration_endpoint_sensitivity','matching_summary','matching_endpoint_changes','matching_stratum_support','annual_source_coverage']}
    for n,names in suites.items():
        t=f'# Table S{n} 数据套表\n\n'+'\n'.join(f'- [{name}]({name}.csv)：{len(pd.read_csv(out/"tables"/(name+".csv"),keep_default_na=False))}行' for name in names)
        if n==5:t+='\n\n原始bootstrap区间与AF固定中央匹配范围不同；原handoff draws/seed未包含，不能声称独立重现分位数。'
        write(out,f'tables/Table_S{n}_index.md',t+'\n\n[阅读入口](../README_zh.md)')
    write(out,'source_data/README_zh.md','# 逐面板Source Data\n\n所有数值CSV保留原始全精度。原始CSV和指纹在inputs与provenance；绘图未更换seed或重新估计。\n\n'+'\n'.join(f'- [{r["new_panel"]}]({r["new_panel"]}.csv)：{r["rows"]}行；原字段与区间定义保持。' for r in mapping)+'\n\nRaw bootstrap=1,000次整研究条件95%区间；matched=AF固定、2,000次中央95%范围。国家NA=Namibia。ED3c使用attributed_fraction；表内旧fraction保留但不作为所绘分母。\n\n[完整表套](../README_zh.md)')
    write(out,'manuscript/Results_en.md',(source/'Diffusion_revised_EN.md').read_text()+'\n\n[Reading index](../README_zh.md) · [Methods](Methods_M1_M2_en.md) · [Captions](captions_zh_en.md)')
    write(out,'manuscript/Results_zh.md',RESULTS_ZH);write(out,'manuscript/Methods_M1_M2_en.md',METHODS_EN+'\n\n[Reading index](../README_zh.md)')
    old=(prior/'methods_zh.md').read_text();old=old[:old.index('## 输出、版本与软件说明')]
    old=old.replace('ED1在共用月度轴','ED2在共用月度轴').replace('ED2a固定十国','ED3c固定十国').replace('本版ED2a','本版ED3c').replace('ED2b每年','ED3b每年').replace('主图d按','ED3a按').replace('Fig1b/c','Fig1b').replace('主图及S6直接采用作者提供Finding1_revision_handoff_v2','主图及S6直接采用本轮v7目录内冻结CSV（对应既有Finding1_revision_handoff_v2）')
    m24='''## M2.4 论文数量与学科／类型匹配\n\n主图与S6直接采用v7目录内45份冻结CSV的年度/端点汇总，所有输入与上一版正式结果逐字节一致。三规格×五年共15个匹配点，三规格×两个起点共六个端点行；所有目标层的可用C数均≥AF目标数。本版不重新估计、不更换seed、不以独立本地模拟替换handoff。\n\n主规格count_composition在同年×primary subfield×document type各层无放回抽取与AF数相同的non-AF研究。AF固定，每年2,000次；不匹配国家构成。count_only只匹配数量；count_composition_known_country限制双方已知国家后再按同层抽样。未知地理可在前两规格中以空国家集合参与抽取，但不产生国家信用。支持不足不跨层补样。\n\nE_t=G_AF,t−mean_r(G_nonAF,t,r matched)。上下界是每次gap的2.5/97.5分位，属于固定AF后的中央95%匹配范围，不是完整CI，不包含AF样本变异、漏检、标签、归属误差或跨年团队依赖。原始handoff逐重复draws和seed未附；本轮检查年度/端点点估计恒等式、区间逆向代数与层支持，不宣称逐项独立重现原分位数。端点范围沿用原包的逐重复差值定义，不相减边际区间。跨零不能证明等效。正式主规格为0.0168→0.0194；点序列不持续下降不是正式恒定性或因果检验。\n\n'''
    start=old.index('## M2.4 ');end=old.index('## M2.5 ')
    old=old[:start]+m24+old[end:]
    old+='''\n## v7呈现与来源边界\n\n本轮45份CSV与上一版正式结果逐字节一致，只重排为双面板主图、ED1–3及S1–S6；不重估bootstrap、匹配或国别R。主a为AF/non-AF年度Gini，主b为原始和匹配差距同轴。原始差距用整研究bootstrap带，匹配差距用AF固定中央95%匹配范围；主a放大轴0.89–0.96、S6a给完整0–1尺度。\n\nED1是精简识别流程；ED2为地图及月度累计/新增；ED3a是基线前十国R端点，ED3b为年度动态top5/top10，ED3c为另一套固定十国构成。读者须区分所有估计对象。Figures内只保留面板字母，不设置面板标题。英文Results以v7提供的632词稿为基线。\n\n记录Python、Matplotlib等实际运行时；使用scientific-visualization技能进行区间、单位、轴和导出审计。原始方法说明及作者确认存档，历史软件引用保留在provenance/historical_methods_zh.source.txt。\n\n[阅读入口](../README_zh.md) · [逐面板Source Data](../source_data/README_zh.md)\n'''
    write(out,'manuscript/Methods_M1_M2_zh.md',old)
    brief=(source/'Figure1_generation_brief_ZH.md').read_text();caps=brief.split('## 图注英文稿\n',1)[1].split('## 排版与制作规格',1)[0]
    zh_caps=[
    'a，固定227国的AF/non-AF年度Gini，含零产出；每研究1/k国家信用；阴影为1,000次条件整研究bootstrap区间。放大轴0.89–0.96，完整尺度见S6a。b，原始与匹配差距同轴。灰带是原始bootstrap区间，紫误差线是AF固定2,000次匹配中央95%范围，非完整CI。原始2021→2025变化−0.0144，条件区间[−0.0232,−0.0105]；约65.9%净收窄发生于2021–2022。连线不是拟合或发布因果效应。',
    '初始关键词与四seed候选及补检旁支汇入摘要/正文证据评估；研究自身应用、双yes及批准关联形成16,414项AF studies。仅引用/背景/未来计划不足；未知保留。简流程不承担准确率证明，完整计数见S1/Table S1。',
    'a，按首次观察发表阶段着色，不同于采用时刻或模型版本；未观察和注册集合外分别显示。b/c，72个月累计阶梯与月度新增；保留2020前1国基数。AF2 code+AFDB为2021-07，AF3 publication/server为2024-05。累计14/123/143，2025活跃128。RE无位置不猜坐标但计数保留。',
    'a，固定基线十国R=(国家AF份额)/(国家eligible份额)，eligible包含AF；2021空心/2025实心、log2真实R刻度，R=1参照，无新增CI。b，年度独立排名top5/top10。c，全期AF固定十国+Other的已归属信用构成，不加Unknown段。a/c国家集合不同；R不是能力或Gini分解。',
    'a为records→works→批准关联studies及主期范围；b初始与补检为独立旁支，826→765、179+586、556 A/B及516 C路由明确；c处置74/159/1/531守恒，positive works净增73 studies。各节点标单位/时期，不把未知当阴性。',
    'a，历史pilot150中122可判定、28保留未知。b，生产最终双yes在122确定参考的2×3矩阵，precision103/105、候选内recall103/103；未知不作TN。c，错误/未知各用150或122分母，类别可重叠。作者报告人工先于模型答案判读，不认证独立留出或全库检索召回。历史ensemble单列。',
    'a，2020–2025整数AF study数，2020仅11不夸大倍数。b，全期AF与eligible各自分母下固定五学科+Other份额；Molecular Biology为67.8%与45.4%。',
    'a为年度AF学科组成、b为各学科AF/eligible比例；Other先汇总分子分母再相除。固定五学科与Other跨年一致，完整22×6=132格见Table S3。',
    '固定2015–2019 eligible信用前20+Other，2021–2025共105格。log2 R以1为中心，紫低青绿高；≤0.25/≥4仅颜色饱和。Other合并207国A/T后算R；真零与无分母分开，不加伪计数。',
    'a，2020–2025完整Gini 0–1轴，2020 n=11。b，三种匹配统一轴及零线。c，三规格×2021/2022起点共6端点变化，条件匹配范围跨零不证明等效。d，AF/non-AF归属覆盖，2025为95.46%/78.59%。不把已知归属限制当作恢复真实地理分布；原matching draws/seed未提供，不能认证原分位数重现。']
    blocks=[b.strip() for b in caps.split('\n\n') if b.strip()]
    assert len(blocks)==10
    write(out,'manuscript/captions_zh_en.md','# 中英文图注\n\n'+'\n\n'.join(f'## {name}\n\n**中文：** {zh}\n\n{en}' for name,zh,en in zip(NAMES,zh_caps,blocks))+'\n\n[阅读入口](../README_zh.md)')
    guide='# 逐面板读者信息、方法与修改原因\n\n| 面板 | 读者应获得的信息 | 分析方法与限制 | 相对旧版的修改 |\n|---|---|---|---|\n'
    for key,msg,method,why in MESSAGES:guide+=f'| [{key}](source_data/{key}.csv) | {msg} | {method} | {why} |\n'
    write(out,'panel_guide_zh.md',guide+'\n[图注](manuscript/captions_zh_en.md) · [入口](README_zh.md)')
    comparison='# v7要求逐项对照\n\n| 要求 | 实施结果 |\n|---|---|\n'
    for k,text in [('1–2','10张逻辑图件，主a/b各5个年度点；图内无面板title'),('3–5','差值恒等式及区间检查；raw bootstrap带与AF固定匹配范围单独解释'),('6','月度累计14/123/143、主期前1国基数、2025活跃128'),('7–8','固定227、ALL含AF、基线十国/全期AF十国/年度top10分别固定或排序'),('9','S2生产与ensemble分开；作者报告判读先于答案，独立留出未认证'),('10','S6完整范围与覆盖；NA/Namibia按文本保留'),('11','PDF/SVG/600dpi、正文图注Source Data同步；视觉记录单列'),('12','提供Finding1–5合稿编号表及更新引用副本；原DOCX和旧章节包未覆盖')]:comparison+=f'| 验收{k} | {text} |\n'
    comparison+='\n## 保留边界\n\n原始匹配draws与seed不在轻量包；重绘与恒等式审计不等于原分位数逐项重现。pilot非已认证独立留出。期刊技术接收和完整作者/团队依赖稳健推断不由本轮认证。对原始Word稿的最终合并仍须使用合稿映射，不宣称已修改原Word稿。\n'
    write(out,'requirement_comparison_zh.md',comparison)
    write(out,'manuscript/reviewer_response_draft_zh.md','''# 审稿回复证据定位草稿

- R1 国家尺度：本节将国家分析限定为起点，结尾接机构分析；不代替机构或职业阶段测量。
- R1 候选与验证：ED1说明实际应用识别；S1完整审计；S2报告122确定参考上的生产最终标签比较及28未知，不声称独立留出或检索召回率。
- R1 动态：主图展示2021–2025完整年度原始/匹配序列，ED2给月度覆盖；承认AF自身集中度下降。
- R2 reinforces/因果：补原始差距变化−0.0144及条件bootstrap区间；匹配不等于无AF反事实，结论限于观察关联。
- R2 归一化：ED3a/S5及Table S4显示国别R，分母包含AF；R不测国家能力。
- R2 覆盖偏差：S6d量化归属缺失差异；非英语/全球南方索引偏差仍非该指标可完整解决。
- R3 diffusion与broader participation：区分累计、新增、年度产出和当年活跃；不以视觉拐点识别发布效应。

以上为可插入回复信的证据定位稿，不代表已覆盖原始Word回复信。
''')
    figure_links='\n'.join(f'- **{name}**：[PDF](figures/{name}.pdf) · [SVG](figures/{name}.svg) · [600dpi PNG](figures/{name}_600dpi.png) · [预览](figures/{name}_preview.png)' for name in NAMES)
    write(out,'README_zh.md',f'''# Finding 1 v7 阅读入口

本版严格执行2026-10-28目录要求：双面板主图、3张ED、6张S、5套表；冻结45份CSV，无重新估计或API/LLM调用。旧数据、旧图和旧正文保留。

## 图件

{figure_links}

## 正文、方法与证据

[中文Results](manuscript/Results_zh.md) · [English Results](manuscript/Results_en.md) · [中文Methods](manuscript/Methods_M1_M2_zh.md) · [English Methods](manuscript/Methods_M1_M2_en.md) · [双语图注](manuscript/captions_zh_en.md)

[逐面板读者信息与修改原因](panel_guide_zh.md) · [要求对照](requirement_comparison_zh.md) · [审稿回复定位](manuscript/reviewer_response_draft_zh.md) · [合稿编号与更新引用](manuscript/global_reference_integration.md)

[Source Data](source_data/README_zh.md) · [Table S1](tables/Table_S1_index.md) · [Table S2](tables/Table_S2_index.md) · [Table S3](tables/Table_S3_index.md) · [Table S4](tables/Table_S4_index.md) · [Table S5](tables/Table_S5_index.md)

[数值和导出核验](validation_report.json) · [实际视觉检查](provenance/visual_review_zh.md) · [复现说明](REPRODUCE.md) · [原要求](provenance/requirements/Figure1_generation_brief_ZH.md)

## 解释边界

AF Gini下降、原始差距缩小与匹配序列未持续收窄分别报告。原始bootstrap区间与AF固定匹配范围不同。原matching draws/seed未附，不能认证原分位数逐项重现。作者报告人工先于模型答案判读，但非已认证独立留出。600dpi是导出属性，不是期刊接收认证。本包提供合稿引用副本，未覆盖原始Word稿。
''')
    write(out,'REPRODUCE.md','''# 离线重绘与验证

使用现有环境的Python运行 `python code/redraw.py --output /新的空目录`；脚本只读本包45份CSV与归档地图，不读取原数据库，不调用API或重估bootstrap/匹配。依赖numpy、pandas、matplotlib、Pillow、geopandas；实际版本见provenance/runtime.json。无需额外数据JSONL。

运行 `python code/verify.py` 核对本包；若检查重绘目录则传其路径。原始要求中的ericayu路径只作历史来源说明，不作为执行依赖。所有新输出位于新目录；不覆盖旧图。

原始年度匹配、端点匹配范围和bootstrap分位数由冻结CSV复用；离线重绘不认证draw级原始估计复现。正式输出PDF/SVG及原生600dpiRGB/sRGB PNG，未通过放大旧截图生成。
''')

def reference_integration(out,project):
    """Supply synchronized copies with globally unique figure numbers, never edit releases."""
    sections={
      2:project/'analysis/nhb_02/revision_v7/finding2_plan6_final_v1',
      3:project/'analysis/nhb_03/revision_v10/finding3_plan6_final_v1',
      4:project/'analysis/nhb_04/revision_v3/finding4_plan2_final_v1',
      5:project/'analysis/nhb_05/revision_v3/reading_v2'}
    maps={2:({3:4,4:5},{8:8,9:9,10:10}),3:({5:6,6:7,7:8},{i:i+10 for i in range(1,8)}),4:({1:9,2:10},{i:i+17 for i in range(1,6)}),5:({}, {})}
    registry=[];audit=[];folder=out/'manuscript/global_integration';folder.mkdir()
    # F1 is numbered 1–3 / S1–S6 in its own final deliverables.
    for n,name in enumerate(NAMES[1:4],1):registry.append({'section':1,'type':'ED','old':n,'global':n,'file':'../figures/'+name+'.pdf','state':'available'})
    for n,name in enumerate(NAMES[4:],1):registry.append({'section':1,'type':'S','old':n,'global':n,'file':'../figures/'+name+'.pdf','state':'available'})
    for section,root in sections.items():
        ed,ss=maps[section]
        for kind,mp in [('ED',ed),('S',ss)]:
            for old,new in mp.items():
                if section==4 and kind=='S' and old==5:
                    registry.append({'section':section,'type':kind,'old':old,'global':new,'file':'','state':'optional_not_run_reserved'});continue
                if section==2:
                    pattern=f'Extended_Data_Figure{old}.pdf' if kind=='ED' else ('Supplementary_gap_details.pdf' if old==7 else f'Supplementary_Figure_S{old}.pdf')
                elif section==3:pattern=f'Extended_Data_Figure{old}.pdf' if kind=='ED' else f'F3_S{old}_*.pdf'
                else:pattern=('Extended_Data_1*.pdf' if old==1 else 'Extended_Data_2*.pdf') if kind=='ED' else f'Supplementary_{old}*.pdf'
                files=list((root/'figures').rglob(pattern))
                # Keep all institution pagination, but reserve one logical number.
                entries=[]
                for src in files:
                    leaf=f'F{section}_{kind}{new}_{src.name}';dst=folder/'figures'/leaf;dst.parent.mkdir(exist_ok=True);shutil.copy2(src,dst)
                    entries.append('global_integration/figures/'+leaf)
                registry.append({'section':section,'type':kind,'old':old,'global':new,'file':' | '.join(entries),'state':'available' if files else 'mapping_only_no_matching_file'})
        # F2's previously unnumbered supplementary gap details receive S7.
        if section==2:
            src=root/'figures/Supplementary_gap_details.pdf';dst=folder/'figures/F2_S7_gap_details.pdf';shutil.copy2(src,dst)
            registry.append({'section':2,'type':'S','old':'gap_details','global':7,'file':'global_integration/figures/'+dst.name,'state':'available'})
        for name in ['results_en.md','results_zh.md','methods_en.md','methods_zh.md','captions_zh_en.md','panel_guide_zh.md','captions_and_reader_messages_zh.md']:
            path=root/name
            if not path.exists():continue
            text=path.read_text()
            # Reading copies omit local navigation hyperlinks; original frozen text fingerprints recorded.
            text=re.sub(r'!?\[([^\]]*)\]\(([^\n]+?)\)',lambda m:m[1],text)
            protected={}
            def table_ref(m):
                key=f'@@TABLE{len(protected)}@@';protected[key]=f'Finding {section} '+m[0];return key
            text=re.sub(r'(?:Table\s*S\d+(?:[––-]S?\d+)?|Tables\s*S\d+(?:[––-]S?\d+)?|Table\s*S[XY]|表\s*S\d+)',table_ref,text)
            def ed_ref(m):return m[1]+str(ed.get(int(m[2]),int(m[2])))
            text=re.sub(r'((?:Extended Data\s*(?:Fig(?:ure)?\.?\s*)?|ED))([0-9]+)',ed_ref,text)
            text=re.sub(r'(?<![A-Za-z0-9_])S(\d+)(?![0-9_])',lambda m:'S'+str(ss.get(int(m[1]),int(m[1]))),text)
            for key,value in protected.items():text=text.replace(key,value)
            if section==2:text=text.replace('Supplementary_gap_details','Supplementary Figure S7')
            header=f'> 合稿引用更新副本：Finding {section}。仅修改图表引用编号、明确表的章节归属及移除原包导航链接；数据和结论不变。原文件未覆盖。\n\n'
            dest=f'F{section}_{name}';write(out,'manuscript/global_integration/'+dest,header+text+'\n\n[合稿编号入口](../global_reference_integration.md)')
            audit.append({'section':section,'source':str(path),'source_sha256':sha(path),'copy':'global_integration/'+dest,'copy_sha256':sha(folder/dest)})
    # Disallow duplicate global numbers for distinct logical ED or S figures.
    for kind in ['ED','S']:
        vals=[r['global'] for r in registry if r['type']==kind];require(len(vals)==len(set(vals)),'Global numbering collision '+kind)
    pd.DataFrame(registry).to_csv(out/'manuscript/global_figure_numbering.csv',index=False)
    pd.DataFrame(audit).to_csv(out/'provenance/global_text_copy_pins.csv',index=False)
    table='|章节|类型|旧编号|全稿编号|状态/图件|\n|---|---|---|---|---|\n'
    for r in registry:
        links=' · '.join(f'[PDF]({f})' for f in r['file'].split(' | ') if f) or r['state']
        table+=f'|Finding {r["section"]}|{r["type"]}|{r["old"]}|{r["type"]}{r["global"]}|{links}|\n'
    copies='\n'.join(f'- [Finding {r["section"]} / {Path(r["copy"]).name}]({r["copy"]})' for r in audit)
    write(out,'manuscript/global_reference_integration.md',f'''# Finding1–5合稿编号与引用更新副本

Finding1的ED1–3使Finding2原ED3/4顺延为ED4/5，Finding3原ED5–7顺延为ED6–8，Finding4本地ED1/2改为ED9/10。S1–6用于Finding1，Finding2补细节为S7、其S8–10保留；Finding3本地S1–7为S11–17，Finding4本地S1–4为S18–21、可选未运行S5仅预留S22。Finding5现版未定义编号ED/S，不虚构新编号。主文Figure1–5不改。

补充表仍按套表组织，其他章节表引用显式加Finding章节限定，不把表号与图号混改。正式期刊若要求全局连续表号，应在确定所有最终套表后另行统一。

{table}

## 更新引用的文字副本

{copies}

这些副本已经使用上表编号；PDF按映射随附，PDF文件内部原章节标题作为历史标记保留。原始Word稿和后续章节原包未改。本包不声称原Word已合并或后续图内标题已重绘；最终交稿应使用本映射和副本替换对应引用。Finding5原结果不因本次编号更新改变。

[机器编号表](global_figure_numbering.csv) · [入口](../README_zh.md)
''')
