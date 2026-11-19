"""Evidence-linked bilingual narrative, panel CSVs and provisional numbered tables."""
from common import *

FIGS={'Figure1_a_d':'Figure 1','ED1_geographic_diffusion':'ED1','ED2_geographic_output':'ED2','S1_corpus_selection':'S1',
 'S2_identification_reference_comparison':'S2','S3_growth_disciplinary_composition':'S3','S4_disciplinary_patterns':'S4',
 'S5_country_normalized_participation':'S5','S6_concentration_sensitivity':'S6'}
def mdtable(x):
    return '| '+' | '.join(x.columns)+' |\n| '+' | '.join(['---']*len(x.columns))+' |\n'+''.join('| '+' | '.join(str(v).replace('|',' / ') for v in row)+' |\n' for row in x.itertuples(index=False,name=None))
def csv(out,name,x):x.to_csv(out/'source_data'/f'{name}.csv',index=False)

def run(out):
    c=load(out,'concentration').set_index('year');m=load(out,'matching_summary');ep=load(out,'matching_endpoint_changes');main=m[m.spec.eq('count_composition')].set_index('year')
    r=load(out,'country_year_AF_normalization');p=load(out,'subfield_period_top5_other').set_index('display_group');metrics=load(out,'Table_S2_pilot_metrics');final=metrics[metrics.system.eq('production')].iloc[0]
    counts=load(out,'annual_counts');nodes=load(out,'Table_S1_process_nodes')
    # Full country table: R, numerator/denominator and first observation separately joined.
    first=load(out,'first_observed_stage_map_source');allr=r.merge(first,on='country_code',how='left',validate='many_to_one')
    save(out,'Table_S4_country_year_R_first_observation',allr)
    # Supplement design explicitly separates historical performance from process certification.
    design=pd.DataFrame([['sample','150 deliberately selected candidate works, not a random corpus holdout'],['reference','122 determinate; 24 evidence-unresolved + 4 uncertain consensus excluded from performance'],['reference_process','Two reference annotation workbooks;109 adjudications;41 exact-reference agreements (not model A/B agreement)'],['final_linkage','150/150 work IDs overlap frozen production final v2; no new labels inferred'],['positive_rule','af_use_label=yes AND adoption_eligible=yes'],['C_scope','68 routed pilot works,53 determinate references; not comparable random full-150 scope'],['independence','Author confirmed on 2026-10-25 that human judgement preceded viewing model answers; recorded as author-reported blinding, not heldout certification'],['production_equivalence','Pilot and production-final overlap compared; not an independent held-out validation or incremental-closure validation'],['recall','Candidate-pilot positive recall, not OpenAlex retrieval recall']],columns=['item','definition'])
    save(out,'Table_S2_design',design)
    scope=load(out,'Table_S3_subfield_year')[['subfield','subfield_name']].drop_duplicates().sort_values('subfield')
    save(out,'Table_S1_subfield_scope',scope)
    # Small exact per-panel files, rather than many synonymous workbooks.
    panels={
      'Figure1a':pd.DataFrame([['Corpus',6046663,'publication records','22 subfields;2015–2025'],['Initial candidates',29127,'candidate work records','Keywords and four initial seed citations; later retrieval separate'],['Evidence assessment',None,'process','Further retrieval; AI abstracts/full texts; targeted human review'],['AF-use cohort',16414,'studies','2020–2025; two yes labels; approved links']],columns=['step','n','unit','definition']),
      'Figure1b_upper':load(out,'concentration').query('year>=2021'), 'Figure1b_lower':load(out,'concentration').query('year>=2021')[['year','delta_gini','delta_lower','delta_upper']],
      'Figure1c':m.query('spec=="count_composition" and year>=2021'),'Figure1d':load(out,'figure1d_top10_endpoints'),
      'ED1a':first,'ED1b':load(out,'monthly_diffusion'),'ED1c':load(out,'monthly_diffusion'),
      'ED2a':load(out,'ed2a_attributed_composition'),'ED2b':load(out,'concentration').query('year>=2021')[['year','af_top5','af_top10']].assign(top5_percent=lambda x:x.af_top5*100,top10_percent=lambda x:x.af_top10*100),
      'S1a':nodes.iloc[:5],'S1b':nodes.iloc[5:12],'S1c':nodes.iloc[12:],
      'S2a':load(out,'pilot_reference_states'),'S2b':load(out,'pilot_confusion').query('system=="production"'),'S2c':pd.DataFrame([['unresolved_evidence',24,150],['uncertain_consensus',4,150],['production_reference_negative_predicted_use',int(final.FP),122],['production_unknown_prediction',int(final.undecided_or_missing),122]],columns=['type','n','denominator']),
      'S3a':counts.query('publication_year>=2020'),'S3b':load(out,'subfield_period_top5_other'),
      'S4a':load(out,'subfield_year_top5_other')[['year','display_group','AF','eligible','AF_share']],
      'S4b':load(out,'subfield_year_top5_other')[['year','display_group','AF','eligible','AF_rate']],
      'S5a':load(out,'figure1_normalization_heatmap_source'),'S6a':load(out,'concentration'),
      'S6b':m,'S6c':ep,'S6d':load(out,'annual_source_coverage').query('year>=2020 and group in ["AF","C"]')}
    for name,x in panels.items():csv(out,name,x)
    save(out,'panel_source_index',pd.DataFrame([dict(panel=k,rows=len(v),path=f'source_data/{k}.csv') for k,v in panels.items()]))
    transition=(c.loc[2021,'delta_gini']-c.loc[2022,'delta_gini'])/(c.loc[2021,'delta_gini']-c.loc[2025,'delta_gini'])
    rawend=load(out,'concentration_endpoint_sensitivity').query('start==2021 and end==2025 and estimand=="AF_minus_C_Gini_endpoint_change"').iloc[0]
    examples=[]
    for code in ['GB','CN','US','DE']:
        x=r[r.country_code.eq(code)].set_index('year');examples.append(dict(country=code,R_2021=f'{x.loc[2021,"R"]:.2f}',R_2025=f'{x.loc[2025,"R"]:.2f}',r_2025=f'{100*x.loc[2025,"r"]:.2f}%'))
    results=f'''# Finding 1：Geographic expansion with persistent concentration

## 中文Results（本版对应a–d）

研究以6,046,663条2015–2025年OpenAlex生命科学发表记录为原始范围，覆盖22个适格subfields；关键词与四篇初始种子引用形成29,127条初始候选。随后进行补检、摘要／正文AI辅助评估和定向人工核查，以研究自身实际使用AF模型或预测结构的证据为条件纳入。去重及范围处理后，2020–2025年有16,414项AF-use studies，同期适格语料为2,714,594项studies（Fig. 1a；S1；Methods M1）。初始候选数不是最终研究集的简单上级分母，补检分支和单位变化在S1／Table S1分别列明。

历史pilot共150项候选，122项参考标签可判定、28项参考未决。我们已将全部150项ID与原生产最终库关联，122项可判定记录中的最终双yes规则与参考标签相比，positive precision为{final.precision:.3f}、recall为{final.recall:.3f}（S2；Table S2）。作者于2026-10-25确认人工判读在查看模型答案之前完成，作为作者报告的判读盲法存档。该比较仍**不是已确认独立留出、适用于所有增量标签的金标准验证**；pilot校准影响和后续流程适用范围不能由此消除。历史ensemble结果另列，不能与生产最终标签的结果混称。候选内recall不等于语料检索recall。

按发表月份观察，参与AF研究的国家／地区在Pre-AF2末、AF2末、2025年底累计为14、123、143；2025年当年活跃为128，两者不同（ED1；M2.1）。阶段界限是2021年7月的AF2 code + AFDB及2024年5月的AF3 publication/server，不是软件实际使用日期或逐篇版本认证。主期前历史首次观察保留在累计中，不加回2020–2025产出。年度AF研究数从2021年的393项增至2025年的5,573项；2020年仅11项，不强调从该小样本起点的百分比增长（S3–S4）。全期Molecular Biology占AF研究{100*p.loc['Molecular Biology','AF_share']:.1f}%，占适格语料{100*p.loc['Molecular Biology','eligible_share']:.1f}%。AF主期实际涉及21个subfields，适格范围仍为22个。

固定227个国家／地区、保留零产出且按研究国家集合分配1/k信用后，AF年度Gini从2021年{c.loc[2021,'af_gini']:.4f}降至2025年{c.loc[2025,'af_gini']:.4f}；原始AF−non-AF差从{c.loc[2021,'delta_gini']:.4f}降至{c.loc[2025,'delta_gini']:.4f}，端点变化{rawend.point:.4f}，条件95%整研究bootstrap区间[{rawend.lower:.4f}, {rawend.upper:.4f}]（Fig. 1b上／下层；M2.2–M2.3）。约{100*transition:.1f}%的净收窄发生于2021–2022；2023、2025小幅回升，不能称逐年单调下降。收窄与AF产出快速扩张同时发生，不预先把变化归因于数量增长。

因此进一步在同年抽取相同数量的non-AF研究，并匹配primary subfield与document type。每年2,000次无放回抽样、AF观察值固定后，主规格差值在2021和2025年分别为{main.loc[2021,'point']:.4f}与{main.loc[2025,'point']:.4f}（Fig. 1c；S6）。所有2021–2025主点估计均为正，观察序列没有持续收窄。图中的中心95%范围反映不同匹配non-AF样本的变异，**不是完整不确定性CI**；不能写作“统计上不变”“证明不趋同”或AF因果作用。仅数量匹配为{m.query('spec=="count_only" and year==2021').point.iloc[0]:.4f}→{m.query('spec=="count_only" and year==2025').point.iloc[0]:.4f}；已知归属限制及三规格×两起点的六行端点结果见S6/Table S5。

## 匹配底表的来源与本地复核

作者已提供Finding1_revision_handoff_v2，全部23份CSV通过其清单SHA256核对；原始集中度、国家A/T/R、前十国端点、已归属构成和132行学科数据均与本地冻结数据独立对应。主图／S6采用该包原匹配年度与六行端点汇总，统一为0.0168→0.0194。另保留固定种子{SEED}的独立本地2,000次匹配复核及[对照表](tables/handoff_local_matching_comparison.csv)，不将本地不同随机流的分位数冒充原手包分位数。轻量包未含原匹配逐重复draws／seed，因此原匹配区间的底层重复尚不能逐项重算认证；范围明确标注来源，不伪称本地原样复现。

## 国别异质性与下一节衔接

为补充总体比较，按2015–2019年适格分数信用固定前十国，以R=(国家AF份额)/(国家适格发表份额)比较2021／2025端点（Fig. 1d；S5；Table S4）。

'''+mdtable(pd.DataFrame(examples))+f'''
英国相对强度下降、中国上升，而美国两端舍入后约1.57；德国亦有所变化。端点不证明中间年度单调，舍入相同不证明等效稳定；R下降也不等于AF使用绝对数量下降。R分母含AF在内的全部适格语料，与Gini比较的non-AF池不同，不直接分解Fig. 1b/c的差值，也不是科研能力、真实使用概率或领域匹配后的“净优势”。

国家产出构成与年度头部份额另列ED2：前五约{100*c.loc[2021,'af_top5']:.1f}%→{100*c.loc[2025,'af_top5']:.1f}%，前十{100*c.loc[2021,'af_top10']:.1f}%→{100*c.loc[2025,'af_top10']:.1f}%。固定十国构成按已知国家信用重算；年度排名前五／前十允许成员改变，头部合计保持不等于各国份额都不变。

国家层面的参与并不说明国内机构均已广泛参与。因此，下一节转向按基线发表规模分组的机构进入与覆盖（Finding 2），不将机构首次进入曲线混入ED1国家扩散。

## 结论边界

2025年国家归属覆盖AF95.46%、non-AF78.59%。整研究bootstrap、匹配、已知归属限制及R归一化均不能恢复未知地理分布；各项结果限于观察到的发表产出。当前不作“降低科研门槛”“AF放大不平等”“无不平等效应”等因果判断。

[入口](README_zh.md) · [方法](methods_zh.md) · [图注](captions_zh_en.md) · [逐面板读者信息](panel_guide_zh.md)
'''
    (out/'results_zh.md').write_text(results)
    en=f'''# Finding 1 — Geographic expansion with persistent concentration

The observed cohort comprised 16,414 AF-use studies during 2020–2025, against 2,714,594 eligible studies. Initial keyword and four-seed retrieval identified 29,127 candidate records; further retrieval, evidence assessment and approved study links mean that the final cohort is not a simple subset funnel (Fig. 1a; S1). The author confirms that human reference judgement preceded viewing model answers. Historical pilot reference comparisons nevertheless do not establish corpus-wide retrieval recall or independent held-out validation (S2).

Observed geographic participation reached 14, 123 and 143 countries/regions by the three era endpoints; 128 countries were active in 2025 (ED1). Across a fixed registry of 227 countries and regions, AF Gini decreased from 0.9421 in 2021 to 0.9253 in 2025. The raw AF-minus-non-AF gap changed from 0.0415 to 0.0271, an endpoint change of −0.0144 (conditional 95% study-bootstrap interval, −0.0232 to −0.0105; Fig. 1b). Approximately {100*transition:.1f}% of the net narrowing occurred in 2021–2022, with small reversals in 2023 and 2025.

Most of the narrowing occurred as AF publication output grew rapidly. We therefore examined whether the gap still narrowed when AF and non-AF samples contained the same number of studies, further matching primary subfield and document type. In the supplied 2,000-draw matching summaries, the matched gap was {main.loc[2021,'point']:.4f} in 2021 and {main.loc[2025,'point']:.4f} in 2025; all main-period point estimates were positive, without sustained narrowing in the observed sequence (Fig. 1c; S6). Central matched ranges condition on fixed observed AF output and are not full confidence intervals. All23 supplied tables were hash-checked and aligned to local frozen data. Original full matching draws/seed are absent from the lightweight handoff; a separate local simulation is an audit, not a byte-identical replay of its quantiles.

To complement these aggregate comparisons, we examined country-level differences in AF participation relative to publication volume. For the fixed baseline-output top ten, UK R changed from 2.56 to 1.71 and China's from 0.43 to 0.59, whereas rounded US endpoints were both 1.57 (Fig. 1d; S5). These endpoints do not establish monotonicity, significance or equivalence. National participation, however, does not reveal how widely AF research is distributed among institutions within each country. We therefore next examine institutional entry and coverage across groups defined by baseline publication output.

Results concern observed publication output, not causal adoption effects or research barriers. Differential country attribution, incomplete retrieval, uncertain evidence and lack of a confirmed independent holdout/production-generalization design remain limitations.
'''
    (out/'manuscript/Results_en.md').write_text(en.replace('All23','All 23'))
    (out/'manuscript/Results_zh.md').write_text(results.replace('](tables/','](../tables/').replace('](README_zh','](../README_zh').replace('](methods_zh','](../methods_zh').replace('](captions_zh_en','](../captions_zh_en').replace('](panel_guide_zh','](../panel_guide_zh'))
    methods='''# Methods — Finding 1（M1、M2.1–M2.6）

## M1 语料、召回、证据判读、研究归并与验证

冻结OpenAlex主表6,046,663条publication records，2015–2025，22个生命科学subfields；原始采集在2026年4月3日所在周完成。本轮不更新整库快照。article/review/preprint适格work基础4,686,896条，经两项原关联为4,686,894项study units，再依已接受关联移除15个重复成员为4,686,879。2020–2025适格语料2,714,594项studies，其中16,414项满足AF-use纳入；records、works、studies与国家分数信用分别报告。

初始候选29,127项work records由关键词和四种seed引用召回；四种为AF2、AlphaFold-Multimer、AFDB、AF3。AF1属于后续补检，不回写成第五个初始seed。后续826项线索中765项满足文献类型；额外召回不是初始候选的简单串联子集。全765项最终74采用、159非采用、1平台、531未知；74项positive work records与相对旧16,341项主研究净增73不同。净增为先前71项positive减1同研究重复，再加最新3项。版本标签不自动传播，不倒填预印本使用或机构。

原29,127候选的证据包为19,202项有全文证据、8,928仅摘要、988证据不足、9超上下文；28,130模型可提交、997未强制提交。本轮增量586项中556适格（154正文包、402摘要包）进入A/B，28不足、2超大包保留；C复核516项。A/B分别判读相同冻结证据，核心分歧、未知或异常进入C及定向人工核查，C不是自动金标准。本版不新增调用、标签裁决或版本归并。

采用须有摘要或正文证据证明AF模型或预测结构用于该研究自身分析、实验、方法开发或评估。引用、背景讨论或未来计划不成立；证据不足保留uncertain。主队列执行af_use_label=yes AND adoption_eligible=yes，平台原始论文排除。两yes与动作细分类不是同一个验证任务，不将动作校准正确率代替采用识别正确率。

历史pilot150项候选具有两个参考注释工作簿、109项参考分歧裁决和41项参考一致；这里的参考annotator A/B不是生产LLM A/B。122项reference_status=resolved，另外24项证据未决和4项uncertain consensus从性能分母剔除但保留在150项审计中。将150个work ID直接关联原生产最终库，按双yes正例规则重新构建2×3混淆矩阵（yes/no/uncertain-or-missing）。precision=TP/(TP+FP)，positive recall=TP/参考positive；未知预测不作TN，strict TN只计明确no。C仅在其68项定向范围中评价53项可判定参考，不能同A/B全122项作随机性能排名。历史ensemble比较和生产最终标签比较分别列于Table S2。

作者于2026-10-25直接确认“人工判读前未查看模型答案”，其原话及来源存档为作者报告的判读盲法。pilot是否影响规则校准、是否为独立留出及与后续增量模型／提示词的适用性并未因此得到证实；两个参考工作簿也不自行证明两个完全独立的真实标注者。本版称“历史pilot参考标签比较”和“生产最终标签在pilot重叠子集的比较”，不称独立留出金标准，也不把候选内recall称为整库检索recall。未新造验证样本或性能CI，生产全库仍含未知／未决。

## M2.1 发表阶段、首次观察与扩散

主期Pre-AF2为2020-01至2021-06，AF2为2021-07至2024-04，AF3为2024-05至2025-12。ED1在共用月度轴标AF2 code + AFDB（July 2021）、AF3 publication/server（May 2024），不将后者标为AF3 code release。地图按首次观察发表月着阶段色，未观察／注册编码外分开；底图为已归档Natural Earth110m，小地区位置为示意／参考位置而非机构地址，RE无位置则保留统计、不猜坐标。累计曲线用step，不平滑。

主期前1个已观察国家保留在累计，历史2019的4项研究不进入2020–2025产出。阶段累计14/123/143从月度底表核验，2025当年活跃128不是累计143。首次发表不等于采用时刻，era不保证实际AF版本；不新增机构曲线或独立milestone图。

## M2.2 国家信用、non-AF与适格语料

每study的k个唯一国家各获1/k信用，保持研究完整国家集合。Gini固定227国／地区，包含零产出；国家未知不成为第228国、不重分摊。non-AF统一指原Figure1筛查阴性C池，不代表每项均经独立实证证实未使用，也不替换为Figure2更宽比较池。ALL eligible包含AF、C及其余适格记录，用于国别R和学科背景，不能改称non-AF。额外765项召回均从C移出，unknown不当作non-use。

ED2a固定十国US/CN/DE/GB/FR/JP/CA/IT/ES/IN按2020–2025 AF总分数信用选取；以known_AF_studies（等于已知国家AF总信用）重算credit/known_AF_studies，Other为剩余已知信用。旧fraction的分母是全部AF研究，不能直接当归属产出比例；本版ED2a不画Unknown段。ED2b每年在227国信用排序计算前五／前十，成员可改变，不能把固定十国合计替代动态前十。

## M2.3 原始Gini、差值与整研究bootstrap

排序非负信用向量x，n=227，G=Σ(2i−n−1)x_i/(nΣx_i)。总信用0时未定义。D_t=G_AF,t−G_nonAF,t，端点ΔD=D_2025−D_start，无量纲非pp。沿用原1000次整研究bootstrap、seed20261009，按完整国家集合的整数频数多项重抽样，与抽研究等价。对应replicate计算年度差值和端点变化再取2.5/97.5分位，不直接相减边际区间上下界。年度／组独立流不处理跨年团队依赖。原始区间条件于观察记录，不含漏检、标签和归属元数据误差。主图显示2021–2025，S6a保留2020–2025及0–1轴；2020仅11项，不依据其宣称普遍增长倍数。

## M2.4 论文数量与学科／类型匹配

主图及S6直接采用作者提供Finding1_revision_handoff_v2的匹配年度/端点汇总，15个年度点（2021–2025×三规格）、六个端点行、全部分层支持均核对。23份CSV均与handoff清单SHA256一致；本地冻结数据进一步确认研究数、国家信用、归一化与学科计数、所有匹配层目标和可用C池。每年2,000次，AF观察信用/Gini固定。

三规格：count_only在同年全部C池无放回抽AF研究数；count_composition在同年×primary subfield×document type每层抽与AF数相同的C研究；count_composition_known_country先双方限已知国家再同层抽样。包含未知国家的前两规格中，未知以空国家集合参与研究抽取但不生成国家信用；已知规格目标数因此不同。仅AF有正目标的层进入匹配，所有目标层先核验C可用数≥AF数；支持不足即停止，不跨层补样、不过滤不便的层。

独立本地复核以预先记录seed20261025、每年／规格SeedSequence([seed,spec_index,year])从同层完整国家集合的整数n多元超几何抽频数，再乘1/k信用矩阵；等价于对个体研究均匀无放回抽样，不是抽国家、不替换抽样、不用已知国家信用总量冒充研究数。保存本地层目标／可用数、逐重复实际研究数及已知信用。原handoff逐重复draws和seed未包含在轻量包；不把本地复核随机流当原匹配流。

E_t=G_AF,t−mean_r(G_nonAF,t,r^matched)，中心95%条件匹配范围为每次gap的2.5/97.5分位。handoff年度下/上界与固定AF减matched non-AF上/下分位的代数关系一致。范围只描述固定AF下non-AF匹配抽样变异，不是完整CI，不含AF样本、漏检、标签或跨年团队依赖。原交接说明将端点范围定义为逐重复gap_2025−gap_start分布；本地检查其六行点估计等于相应年度均值相减，但因原draws未附，不能独立重建原端点分位数。另存本地重复的端点范围用于复核，不取代原区间。跨零不证明等效或没有变化，点估计未持续下降也不是正式恒定性／趋势检验。

采用已提供原交接包后，正式图文主规格为0.0168→0.0194，与文档一致。本地独立模拟约0.0165→0.0195仅留在独立audit表，不混进主图，也不调seed贴原值。两套表的抽样池／目标一致并不意味着随机流、分位数逐项相同。原包历史列名excess/benchmark不表示因果超额效果。

## M2.5 时间窗、归属限制和学科组成

主图原始／匹配动态2021–2025；S6保留完整2020序列、三规格、2021/2022两个起点和归属覆盖。2025 AF可归属5320/5573=95.46%，non-AF78.59%。限制已知归属不能恢复未知真实分布，匹配不自动消除差异缺失。

S3/S4按相同主期适格study记录统计22学科×6年共132格，AF非零涉及21学科。固定五学科按全期AF研究数降序，余17学科合并Other，顺序跨年一致。年度组成以每组该年总study数为分母；学科内AF比重以该学科AF／eligible整数study数计算；Other先汇总分子分母，绝不平均子学科比例。全期Molecular Biology为AF67.8%、eligible45.4%。领域描述不同于匹配或国家R，不互相替代。

## M2.6 国别发表规模归一化

r_ct=A_ct/T_ct；R_ct=r_ct/(A_t/T_t)=(A_ct/A_t)/(T_ct/T_t)。A为AF已知国家分数信用，T为已采集全部适格生命科学研究信用（包含AF）；A_t/T_t在相同227国已知信用上汇总。不是国家全部科学产出，不是non-AF分母。R=1为同比例参照，不是公平或能力标准。A=0且T>0保留真实0；T=0未定义；无伪计数。

主图d按2015–2019 ALL信用固定前十：US CN JP DE GB IN FR KR IT CA，不按R或2025结果选国；2021空心、2025实心、细线配对，log2横轴以真实R刻度标0.25/0.5/1/2/4，端点均为正。S5为同基线前20＋Other的完整2021–2025热图；前20占基线已知信用83.69%，Other先合并其余207国A/T后计算，不平均各国R。色标log2 R中心1，紫色低于1、青绿高于1，仅颜色≤0.25／≥4饱和，不改源值；105个主格均正值，完整Table S4仍保留零／未定义及其状态，低分母不能当稳定排名。

R轨迹没有新增国家区间，不称显著变化、等效稳定或领域匹配净优势；R下降不推出AF绝对数量减少。国别R描述不是Fig1b/c的直接分解。现有共同支持构成加权仅另作可选分析，本版不强制重复全国家多页热图。

## 输出、版本与软件说明

1张a–d主图、2张ED、6张S组合；图内只保留面板字母，流程节点说明和坐标／图例不是面板标题。原生PDF/SVG、预览及600dpi RGB/sRGB PNG和LZW TIFF；每面板CSV，全精度原handoff底表、36,000本地audit匹配重复、原bootstrap、抽样支持与SHA256随包。原matching逐重复draws未提供，本地audit不冒充原区间认证。作者已确认人工先于模型答案判读，仍不能据此宣称独立留出或全量泛化金标准。Table S1–S5与S1–S6为本节暂编号，合稿需统一。

本轮仅写新目录，不修改旧库、旧图、旧Results/Methods，不覆盖后续机构M3/M4；无新增API/LLM或安装。数据分析、统计分析与科学可视化技能用于研究抽样单位、条件匹配范围／CI区分、分母守恒和实际渲染核验。沿用既有环境Python3.11.11、numpy1.26.4、pandas3.0.2、scipy1.17.1、matplotlib3.10.8、Pillow12.2.0。旧版Methods的Scientific Agent Skills软件参考保留，未将技能或辅助模型当成实证来源或独立标注者。

[入口](README_zh.md) · [表格与Source Data](source_data/README_zh.md) · [尚待核实项](author_confirmation_zh.md)
'''
    # Preserve the already dated workflow citation, without claiming a new literature check.
    historical=(out/'provenance/historical_methods_zh.source.txt').read_text()
    citation=[line for line in historical.splitlines() if '软件流程参考：' in line and 'Scientific Agent Skills' in line]
    if citation:methods+='\n## 历史软件引用记录（沿用原核对日期）\n\n'+citation[0]+'\n'
    (out/'methods_zh.md').write_text(methods)
    (out/'manuscript/Methods_M1_M2_zh.md').write_text(methods.replace('](README_zh','](../README_zh').replace('](source_data/','](../source_data/').replace('](author_confirmation_zh','](../author_confirmation_zh'))
    captions='''# Figure及Supplementary双语图注

## Figure 1 | Geographic diffusion and concentration of AlphaFold research.

**a,** Study identification in the frozen 2015–2025 OpenAlex life-science corpus (6,046,663 publication records;22 eligible subfields). Initial keyword and four-seed citation retrieval produced29,127 candidate work records; further retrieval, AI-assisted assessment of abstracts/full texts and targeted human review contributed to16,414 AF-use studies in2020–2025. The final study cohort is not a simple subset funnel of initial retrieval (S1;Methods M1). Actual use requires evidence in the study's own analysis, experiments, methods or evaluation; citation, background or future plans alone are insufficient.

**b,** Upper: annual AF/non-AF country-credit Gini, fixed227 countries/regions with zeros retained. Each study contributes1/k to its k observed unique countries. Unknown country attribution is neither a pseudo-country nor redistributed credit. Lower: original signed gaps, D_t=G_AF,t−G_nonAF,t, on the shared2021–2025 time axis. Shading/error bars are original conditional95% whole-study bootstrap intervals (1000 replicates). The2021–2025 gap change was−0.0144 (conditional95% interval−0.0232 to−0.0105), obtained from replicate endpoint differences rather than subtracting marginal intervals. Gini/gaps are dimensionless. Small reversals preclude monotonic-decline claims (M2.2–M2.3).

**c,** Same-year, primary-subfield and document-type matching:2,000 uniform without-replacement non-AF study samples per year, with observed AF Gini fixed. Points show E_t=G_AF,t−mean_r(G_nonAF,t,r^matched); error bars are central95% conditional matched ranges, not full confidence intervals. Points and ranges use the supplied hash-checked handoff_v2. Unknown-country sampling policy, all-stratum support, original-draw availability and separate local audit are reported in M2.4 and Table S5. The observed sequence does not show sustained narrowing; it is not a test of equivalence, constant inequality or causal AF effects.

**d,** Country R=(A_ct/A_t)/(T_ct/T_t), where A denotes AF known-country fractional credit and T all eligible known-country credit, including AF. Countries are the fixed baseline2015–2019 eligible-output top ten, ordered US/CN/JP/DE/GB/IN/FR/KR/IT/CA. Open/filled circles indicate2021/2025, joined within country; the log2 axis displays raw R ticks and the dashed reference is R=1. R is descriptive publication-normalized participation, not a research-capability rank or subfield-matched net advantage. Endpoints do not imply monotonic intervening trajectories; no country intervals are added (M2.6).

**中文说明：**a按记录／候选work／研究study区分单位；b上下为原始Gini及其差值，保留原条件bootstrap区间；c为AF固定下non-AF匹配范围，不能称完整CI；d为空心2021／实心2025的固定基线前十国端点，T含AF适格语料而非non-AF池。2025国家归属AF95.46%、non-AF78.59%，任何匹配或归一化均不能恢复未知地理分布。

## ED1 | Geographic diffusion of AlphaFold research.

a首次观察世界地图按pre-AF2、AF2、AF3发表阶段着色，未观察与注册集合外分开。b月度累计阶梯曲线；c同轴月度新增柱。阶段端点14、123、143；共用轴标AF2 code + AFDB（July2021）与AF3 publication/server（May2024），不是AF3 code release。历史主期前1个国家保留在累计，2019产出不重算为2020新增；2025累计143和活跃128不同。位置为归档示意位置，不是机构地址；RE未定位但计数保留。First observation is based on publication date, not actual adoption time or the AF version used; institutional diffusion is outside this figure (M2.1).

## ED2 | Geographic distribution of AlphaFold output.

a2021–2025固定十国＋Other的已知归属AF信用组成，以credit/known_AF_studies重算为100%，不沿用旧all-study fraction、不包含Unknown段。固定十国按2020–2025 AF信用选取，与主图d基线前十不同。b年度各自排名前五／前十国的合计份额，成员可改变，不以a固定十国之和替代。No raw Gini-gap third panel is repeated here (M2.2).

## S1 | Corpus construction and study selection.

a原始records→适格works→批准关联后的studies；b初始候选与额外补检为不同分支，列明765额外合格work及586项剩余证据处理；c额外候选处置、双yes与study去重、最终主期队列。初始29,127不是16,414的简单单链分母；74额外采用work对应相对旧研究集净增73个study。各节点、范围、剔除与版本关系见Table S1。Process transparency is not identification accuracy; author verification of historical design/selection remains pending (M1).

## S2 | Validation of AlphaFold-use identification: reference comparison, not certified independent validation.

a历史150候选pilot参考处理，122可评价，24证据未决＋4参考unknown保留但不纳入性能；109参考分歧裁决／41参考一致指参考注释者，不是模型A/B。b原生产最终标签在150项pilot交集中的双yes规则比较，仅122确定参考进入2×3矩阵；未知／缺响应独立成列而非TN。c错误与未决类型，各行分母150或122明确标出，不合并为同一个排除总数。最终生产positive precision103/105=0.981，recall103/103=1.000；15明确TN、2未知预测。历史ensembleprecision100/101=0.990、recall100/103=0.971另在Table S2，不能混成同一系统。C在其68项定向范围仅53项可评价。The author confirms human reference judgement preceded viewing model answers. Held-out status and generalization to final/incremental production are not certified. Candidate-pilot recall is not corpus-retrieval recall; workflow/model agreement is not independent gold certification (M1).

## S3 | Research growth and disciplinary composition.

a2020–2025 AF年度整数study数，2020仅11，不强调其起点倍数；b全期AF与全部适格语料学科份额，固定AF主期top5＋Other，Molecular Biology67.8% vs45.4%。适格22学科、AF非零21；分母2,714,594主期studies，不是6,046,663原始records (M2.5).

## S4 | Disciplinary patterns over time.

a同固定五学科＋Other的年度AF组成，100%堆叠；b各显示学科的AF/eligible年度study比重。Other先汇总AF/eligible计数再相除，绝不平均各学科率；完整22×6=132格见Table S3。Patterns are descriptive and do not establish discipline-specific causal effects (M2.5).

## S5 | Country-level participation relative to publication volume.

2021–2025 R热图，基线2015–2019 ALL信用前20固定排序＋pooled Other；前20覆盖基线已知信用83.69%。Other汇总剩余207国分子分母后算R。log2色阶以1为中心，紫低、青绿高，≤0.25／≥4仅限制颜色；不改精确底表。本图105格均正值、分母已定义；Table S4保留全227国真零和无分母状态，不加伪计数。Low-denominator extremes are not stable rankings; no new country uncertainty intervals or significance labels are implied (M2.6).

## S6 | Sensitivity of geographic concentration comparisons.

a完整2020–2025 Gini、0–1轴及原条件bootstrap区间；bcount_only、count_composition、count_composition_known_country年度匹配差和各自中央95%条件匹配范围；c三规格×2021/2022两起点、2025终点六行变化，区间由重复端点差得到，仍为条件匹配范围而非完整CI；dAF/non-AF归属覆盖百分比，2025为95.46%/78.59%。Known-country restriction cannot restore missing geography; ranges crossing zero do not establish equivalence (M2.3–M2.5).

以上S/ED/Table编号均为本节暂编号，全文合稿统一。所有面板图内只保留字母；长解释移入本图注。No causal adoption/barrier claim is made.

[入口](README_zh.md) · [Methods](methods_zh.md) · [面板CSV](source_data/README_zh.md)
'''
    # English readability without changing log2 or method IDs.
    for old,new in [('records;22','records; 22'),('produced29','produced 29'),('to16','to 16'),('in2020','in 2020'),('fixed227','fixed 227'),('contributes1','contributes 1'),('shared2021','shared 2021'),('conditional95','conditional 95'),('original conditional95','original conditional 95'),('The2021','The 2021'),('was−','was −'),('interval−','interval −'),('to−','to −'),('matching:2','matching: 2'),('central95','central 95'),('seed2026','seed 2026'),('baseline2015','baseline 2015'),('indicate2021','indicate 2021')]:captions=captions.replace(old,new)
    (out/'captions_zh_en.md').write_text(captions)
    # Explicit status: nine figures rendered != all methodological independence resolved.
    (out/'author_confirmation_zh.md').write_text('''# 作者补充确认及保留的证据边界

1. **原匹配source_data已提供并采用**：作者给出Finding1_revision_handoff_v2。23份CSV哈希、真实国家/学科分子分母和全部抽样支持与本地冻结数据均核对通过；正式图文采用原包0.0168→0.0194。原逐重复matching draws/seed未包含在轻量包，故不声称重新认证了其底层每次抽样或端点分位数。本地seed20261025复核留作独立audit，不替代原区间。
2. **人工先于模型答案判读已获直接确认**：作者于2026-10-25明确答复“人工判读前未查看模型答案”。存档为作者报告的盲法信息，不再写成“完全未知”。但这不等于确认pilot为独立留出样本、未用于规则校准或可外推到全部增量模型。已将150项pilot与生产最终库全部关联，单列最终生产和历史ensemble结果；不升级为全量独立gold certification。

所有已用节点都有来源；作者仍应在合稿时核对筛选策略及排除范围的文字与实际实施一致。现有材料允许真实制图，不等于召回完整、逐篇穷尽去重或独立留出验证。没有新增付费调用、样本裁决或原库更新。

[原包/本地audit对照](tables/handoff_local_matching_comparison.csv) · [pilot设计](tables/Table_S2_design.csv) · [作者原话存档](provenance/author_confirmation.json) · [入口](README_zh.md)
''')
    (out/'panel_guide_zh.md').write_text('''# Figure 1 plan3：逐面板读者信息、方法与要求对应

| 图/面板 | 读者应获得的信息 | 数据和方法 | 本版状态 |
|---|---|---|---|
|1a|如何从原始语料识别实际AF-use研究？|记录/候选/证据处理/研究单位；不画成简单29,127漏斗|已绘；完整节点S1；人工先于模型答案判读已获作者确认|
|1b上|AF国家产出是否仍高度集中？|固定227国、1/k信用、原整研究bootstrap；2021/2025端点|已绘，蓝AF/橙non-AF|
|1b下|原始集中度差如何变化？|共享年份、原差值重复区间、零线、−0.0144端点标记|已绘；不在ED2重复|
|1c|数量/领域/类型可比后差距是否持续缩小？|2,000无放回匹配、AF固定、中央95%匹配范围；非CI|采用经核对原handoff年度/端点表；本地复核另存|
|1d|相对自身发表规模，国别端点如何不同？|基线固定前十；2021空/2025实，log2 R，R=1|已绘；R分母ALL，与non-AF池不同|
|ED1a|国家何时首次被观察参与？|三阶段地图、未知/注册外分开|已绘；首观察发表月非实际采用月|
|ED1b/c|累计和月度新增如何变化？|共用轴、阶梯累计14/123/143及新增柱、两个正确milestones|已绘；累计与年度活跃区分|
|ED2a|固定主要国家贡献构成如何变化？|固定AF信用十国，credit/known_AF_studies重算+Other|已绘；无Unknown段，非旧全研究分母|
|ED2b|年度头部贡献份额是否变化？|每年独立排名top5/top10，成员可变|已绘；不替代固定十国总量|
|S1a–c|完整流程节点、单位与旁支是否透明？|历史冻结节点、补检分支、证据层/双yes/去重|已绘；非独立准确率证明|
|S2a–c|参考样本可判定覆盖、最终标签比较及错误/未知是什么？|150/122/28；原生产标签联结；2×3混淆矩阵；行分母明确|已绘；作者确认人工先于模型答案，独立留出泛化未认证|
|S3a/b|产出规模及总体学科组成是什么？|年度study数；固定top5+Other全期AF/eligible份额|已绘，67.8%/45.4%复核|
|S4a/b|构成变化与学科内AF比例如何区分？|100%年度构成；各学科AF/eligible，Other汇总比|已绘；22学科132行表|
|S5|完整年度国别R是否异质？|基线前20+pooled Other固定顺序、原R颜色log2|已绘；全227国表，不新增国家CI|
|S6a–d|完整窗口、三匹配、两起点、缺失覆盖是否支持解读边界？|原bootstrap与条件匹配范围区分、六端点行、覆盖率|已绘；跨零不等于等效|

主图仅a–d、无面板标题和大总标题；所有面板CSV在[Source Data](source_data/README_zh.md)。暂编号待合稿。已确认内容与剩余边界见[作者确认](author_confirmation_zh.md)。

[入口](README_zh.md)
''')
    # Numbered tables are grouped source tables, not redundant workbooks.
    tablegroups={
      'S1':['Table_S1_process_nodes','Table_S1_subfield_scope','initial_evidence_tiers','initial_candidate_dispositions','Table_S1_seed_registry','Table_S1_seed_references','Table_S1_milestones'],
      'S2':['Table_S2_design','Table_S2_pilot_metrics','pilot_confusion','pilot_reference_states','pilot_production_correspondence','pilot_production_routes'],
      'S3':['Table_S3_subfield_year'], 'S4':['Table_S4_country_year_R_first_observation','first_observed_stage_map_source','normalization_country_selection'],
      'S5':['concentration','concentration_endpoint_sensitivity','matching_summary','matching_endpoint_changes','matching_stratum_support','local_audit_matching_draws','annual_source_coverage','handoff_local_matching_comparison']}
    for number,names in tablegroups.items():
        (out/'tables'/f'Table_{number}_index.md').write_text('# Table '+number+'：精确机器可读表\n\n'+'\n'.join(f'- [{name}]({name}.csv)' for name in names)+'\n\n[入口](../README_zh.md)\n')
    refs=load(out,'Table_S1_seed_references')
    with (out/'tables/Table_S1_index.md').open('a') as f:
        f.write('\n## 四篇初始种子文献（AF1补检另列）\n\n')
        for row in refs.itertuples():f.write(f'- {row.authors} ({row.year}). {row.title}. {row.venue}. [DOI]({row.url})\n')
        f.write('\n## 22个适格subfields\n\n'+mdtable(scope))
    for path in (out/'tables').glob('*.parquet'):
        target=path.with_suffix('.csv')
        if not target.exists():pd.read_parquet(path).to_csv(target,index=False)
    # Source/figure mapping, accessible prose and no inter-folder absolute Markdown links.
    (out/'source_data/README_zh.md').write_text('# 面板Source Data\n\n'+'\n'.join(f'- [{k}]({k}.csv)：{len(v)}行' for k,v in panels.items())+'''

全精度r/R、零/未定义状态、原bootstrap、匹配重复及全部132行学科数据见Table S1–S5。CSV国家代码包含NA（Namibia），读取时应按文本保留，不将其自动当缺失；Parquet保留类型。统计重复不是新的观察论文。未知预测不充作TN，未知国家不重新分摊。

[入口](../README_zh.md)
''')
    links='\n'.join(f'- **{label}**：[PDF](figures/{name}.pdf) · [SVG](figures/{name}.svg) · [600dpi PNG](figures/{name}_600dpi.png) · [预览](figures/{name}_preview.png)' for name,label in FIGS.items())
    (out/'README_zh.md').write_text('''# Figure 1 plan3完整阅读入口

**Geographic expansion with persistent concentration**。按2026-10-25合作伙伴版重组为主图a–d、两张ED、六张S；图内只保留面板字母，无对应标题。原始数据、旧图和旧文稿未改。无新增API／LLM费用。

## 图形

'''+links+'''

## 文字、方法、核实边界

- [中文Results](results_zh.md) · [中文Methods M1/M2](methods_zh.md) · [双语图注](captions_zh_en.md)
- [逐面板读者信息与要求状态](panel_guide_zh.md) · [尚待作者核实](author_confirmation_zh.md)
- [英文Results插入稿](manuscript/Results_en.md) · [中文Results插入稿](manuscript/Results_zh.md) · [Methods插入稿](manuscript/Methods_M1_M2_zh.md)
- [面板CSV](source_data/README_zh.md) · [Table S1](tables/Table_S1_index.md) · [Table S2](tables/Table_S2_index.md) · [Table S3](tables/Table_S3_index.md) · [Table S4](tables/Table_S4_index.md) · [Table S5](tables/Table_S5_index.md)
- [数值／导出核验](validation_report.json) · [实际图片检查](provenance/visual_review_zh.md) · [新旧引用映射](manuscript/reference_mapping.csv)
- [复现说明](REPRODUCE.md) · [原文要求](provenance/figure1-revision-plan-3.md)

**来源与边界**：作者已提供handoff_v2的23份CSV，哈希和关键分子分母/支持全部核对；正式主匹配0.0168→0.0194，与要求一致。原matching逐重复/seed不在轻量包，独立本地复核另存、不冒充原分位数重算。作者已确认人工判读前未查看模型答案；这与独立留出、未参与校准和全量生产流程泛化是不同事项，后者不由当前pilot认证。

所有编号为本节暂编号，合稿统一。本版主图183×193mm，全部9张native PDF/SVG和600dpiRGB/sRGB；输出技术指标不是期刊接收认证。ZIP用相对链接，实际解压后核验。
''')
    pd.DataFrame([['plan2 a','Fig1b upper','Gini'],['plan2 b','Fig1b lower','raw Gini gap; not ED2c'],['plan2 c','S5','annual R heatmap'],['new identification','Fig1a;S1;S2','cohort/process/reference comparison'],['new matching','Fig1c;S6b/c','conditional matched ranges'],['new top10 endpoints','Fig1d','baseline-fixed R endpoints'],['diffusion map/monthly','ED1a/b/c','publication phase background'],['volume/composition','S3a;ED2a/b','volume vs attributed composition separated']],columns=['previous','current','meaning']).to_csv(out/'manuscript/reference_mapping.csv',index=False)
    (out/'REPRODUCE.md').write_text('''# 复现与审计

原项目环境：.venv/bin/python。无新安装、公开请求或模型调用。prepare.py固定来源字节并整理study-pattern、学科、归属和pilot；matching.py按固定seed20261025做独立本地audit；enrich.py核对生产库pilot交集及本地seed引用；import_handoff.py核对作者提供23份原CSV并采用原匹配年度/端点表，同时归档本地audit；draw.py原生绘图；report.py同步文字/面板CSV；verify.py独立数值/导出核验与打包。

新输出目录必须不存在；旧输出与ZIP不覆写。阅读包包含原handoff、绘图底表、整数study-country-set模式、原bootstrap及全部本地audit匹配重复，不含私有正文、密钥和大原始库。原matching draws未在手包，不伪造补入。源码及环境记录保留code/；完整上游准备仍需原项目冻结来源。无需将别人的电脑路径当运行输入。

主图c上下界是固定AF下匹配范围，不是完整CI。正式匹配表来自原手包且精确保存；本地audit与其分开。原区间的逐重复核验仍需原matching draws，而不是另一随机流；author_confirmation_zh.md列明。所有结果写入CSV，显示时舍入，不依据方向选择种子。

[入口](README_zh.md)
''')
    dump(out/'report_summary.json',dict(figures=9,main_panels=4,ED_figures=2,S_figures=6,panel_CSVs=len(panels),matching_seed=SEED,
      main_matched_endpoints=[main.loc[2021,'point'],main.loc[2025,'point']],raw_gap_change=rawend.point,
      early_raw_gap_narrowing_fraction=transition,reference_blinding='author_confirmed_pre_answer_human_judgement',independent_holdout=False,original_matching_handoff='supplied_hash_checked_and_used',original_matching_draws='not_in_lightweight_handoff',new_API_calls=0))
    print(f'Nine figure captions, {len(panels)} panel CSVs, Tables S1–S5, Results/Methods and explicit author-confirmation boundary written.',flush=True)

if __name__=='__main__':run(OUT)
