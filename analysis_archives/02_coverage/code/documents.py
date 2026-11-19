"""Live manuscript/legends and per-panel tables from actual frozen/new results."""
from common import *
from draw import FIGURES
import shutil,re

def write(out,name,text):
 p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text.strip()+'\n')
def source_data(out):
 specs=json.loads((out/'provenance/requirements/05_tables/figure_specifications.json').read_text());meta=[]
 ready={'Figure2':['Fig2a_cumulative.csv','Fig2b_ratio.csv','Fig2c_gap.csv','Fig2d_benchmark_draws.csv','Fig2e_growth_components.csv'],
 'ED3':['ED3a_sample_flow.csv','ED3b_first_entries.csv'],'ED4':['ED4_country_endpoints.csv']*2,
 'S8':['S8_alternative_trajectories.csv']*4,'S9':['S9_annual_benchmark_gaps.csv']*4,
 'S10':['S10a_historical_thresholds.csv','new_weighting_disparities.csv','S10c_historical_benchmark_specs.csv','new_continuous_scale_predictions.csv']}
 for spec in specs:
  fig=spec['id']
  for i,panel in enumerate(spec['panels']):
   letter=panel['letter'];src=ready[fig][i];kind='tables' if src.startswith('new_') else 'inputs/ready';path=out/kind/src;d=pd.read_csv(path,keep_default_na=False)
   condition=panel['filter']
   if fig=='S8':d=d[(d.metric==['authors','partners','authors','partners'][i])&(d['sample']==('metric_valid' if i<2 else 'common_valid'))]
   if fig=='S9':d=d[d.context==CONTEXTS[i]]
   if fig=='S10' and letter=='b':d=d[d.year>=2021]
   name=f'{fig}_{letter}.csv';d.to_csv(out/'source_data'/name,index=False)
   units='percent_coverage' if fig=='Figure2' and letter=='a' or fig=='S8' else 'ratio' if fig=='Figure2' and letter=='b' or fig=='ED4' and letter=='a' else 'institutions' if fig=='ED3' else 'proportion_coverage_by_percentile' if fig=='S10' and letter=='d' else 'percentage_points'
   population='B0_date_resolved_entry' if fig=='ED3' and letter=='b' else 'B0_to_B2' if fig=='ED3' else 'alternative_or_common' if fig=='S8' else 'N10_N20_N30' if fig=='S10' and letter=='a' else 'B2'
   status='new_analysis' if fig=='S10' and letter in 'bd' else 'historical_reuse_after_audit' if fig=='S10' else 'frozen_result_replot'
   record={'figure':fig,'panel':letter,'source_data':'source_data/'+name,'units':units,'population_id':population,'weighting':'see_weighting_column' if fig=='S10' and letter=='b' else 'equal_country_standardized' if fig=='S10' and letter=='d' else 'equal_country' if fig!='ED3' else 'institution_count',
   'time_window':'2020–2025' if fig in ['ED3','S8'] or fig=='Figure2' and letter=='a' else '2025 cumulative' if fig=='S10' and letter=='d' else '2021–2025',
   'source_table':str(path.relative_to(out)),'source_columns':list(d.columns),'source_hash':sha(path),'filter':condition,'result_status':status,'denominator_definition':'fixed baseline within-country institution group; rate aggregation and special B0/alternative scopes defined in Methods M3–M4',
   'numerator_definition':'confirmed pool AF publication observed; cumulative or annual as panel specifies; ED3 is date-resolved first-publication count','rows':len(d),'interval_type':'AF label-reassignment conditional reference, not effect CI' if fig=='S9' or fig=='Figure2' and letter=='d' else 'none_descriptive_points_or_counts'}
   if fig=='S10' and letter=='d':record['supplemental_sources']=['tables/new_continuous_scale_bins.csv','tables/new_continuous_bin_summary.csv','quality/continuous_model.json']
   record['plotted_units']='percent' if fig=='S8' or (fig=='Figure2' and letter=='a') or (fig=='S10' and letter=='d') else units
   record['plot_transformation']='100 * predicted_coverage; bins 100 * coverage' if fig=='S10' and letter=='d' else 'coverage_pct = 100 * C' if fig=='S8' or (fig=='Figure2' and letter=='a') else 'use named metric column without rescaling'
   if fig=='Figure2' and letter=='d':record['analytic_summary']='inputs/ready/Fig2d_benchmark_summary.csv'
   meta.append(record)
 pd.DataFrame([{k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in x.items()} for x in meta]).to_csv(out/'source_data/panel_source_map.csv',index=False)
 dump(out/'source_data/panel_metadata.json',meta)
 for src,name in [('ED3b_eras.csv','ED3_b_eras.csv'),('Fig2d_benchmark_summary.csv','Figure2_d_summary.csv')]:shutil.copy2(out/'inputs/ready'/src,out/'source_data'/name)
 write(out,'source_data/README_zh.md','# 21个panel的直接源表\n\n[字段、分母、权重和来源契约](panel_metadata.json) · [CSV映射](panel_source_map.csv)\n\n'+'\n'.join(f'- [{r["figure"]}{r["panel"]}]({Path(r["source_data"]).name})：{r["rows"]}行；{r["result_status"]}' for r in meta)+'\n\n[Figure2d正式解析摘要](Figure2_d_summary.csv) · [ED3b精确日期时期计数](ED3_b_eras.csv) · [入口](../README_zh.md)\n\nNA国家代码按文本保留。空R为不可定义，绝非0。S10d上下界为空，interval_type明确为描述性点估计，不是缺失的假CI。')
 return specs,meta

def tables(out):
 for p in (out/'inputs/frozen').glob('*.csv'):shutil.copy2(p,out/'tables'/p.name)
 shutil.copy2(out/'inputs/frozen/Table_SX_S8_alternative_sample_audit.csv',out/'tables/Table_SX_d_metric_eligibility.csv')
 # Full 2020–2025 national-group results, computed from original country counts.
 cells=read(out,'country_group_year_primary.csv');cells=cells.loc[truth(cells.eligible_20)&cells.year.between(2020,2025)];rows=[]
 for context in CONTEXTS:
  q=cells if context=='All' else cells[cells.context==context]
  for yr,b in q.groupby('year'):
   v=b.groupby('group').A.mean();row={'context':context,'year':yr,'countries':b.country.nunique(),'institutions':int(b.fixed_N.sum()),'weighting':'equal_country','population_id':'B2','R':v.L/v.H if v.H>0 else np.nan,'R_defined':v.H>0,'G_pp':100*(v.H-v.L)}
   for g in GROUPS:row['annual_'+g+'_coverage_fraction']=v[g];row['annual_'+g+'_coverage_pct']=100*v[g]
   rows.append(row)
 save(out,'Table_SY_a_full_annual.csv',pd.DataFrame(rows))
 hist=read(out,'benchmark_summary.csv');hist['seed']=20261024;hist['source_release']='frozen_v5_historical_source_audited';hist['result_status']='historical_reuse_not_new_simulation';hist['formal_expected_definition']='exact_analytic_expectation_not_simulation_mean'
 save(out,'Table_SY_b_all_benchmarks.csv',hist)
 annual=read(out,'S9_annual_benchmark_gaps.csv','ready');save(out,'Table_SY_c_annual_benchmark.csv',annual)
 components=read(out,'S10_components.csv');save(out,'Table_SY_d_growth_components.csv',components)
 sens=[]
 for row in hist.loc[hist.context=='All'].itertuples():sens.append({'analysis':'benchmark_threshold_or_strata','variant':row.variant,'setting':row.setting,'countries':row.countries,'actual_delta_G_pp':row.actual_delta_G,'analytic_expected_delta_G_pp':row.expected_delta_G,'D_pp':row.excess,'result_status':'historical_reuse_not_new_simulation'})
 for row in table(out,'new_weighting_endpoints.csv').itertuples():sens.append({'analysis':'observed_weighting','variant':row.weighting,'setting':'N20','countries':68,'actual_delta_G_pp':row.delta_G_pp,'analytic_expected_delta_G_pp':np.nan,'D_pp':np.nan,'result_status':'new_observed_estimate_no_benchmark_transferred'})
 sens.append({'analysis':'continuous_domestic_rank','variant':'country_FE_RCS_logit','setting':'N20','countries':68,'actual_delta_G_pp':np.nan,'analytic_expected_delta_G_pp':np.nan,'D_pp':np.nan,'result_status':'new_descriptive_model_different_estimand'})
 save(out,'Table_SY_e_sensitivity_status.csv',pd.DataFrame(sens))
 f=table(out,'new_strata_diagnostic_summary.csv')
 for a,b,n in [('mutable_strata','strata','mutable_stratum_fraction'),('mutable_studies','studies','mutable_study_fraction'),('mutable_AF_studies','AF_studies','mutable_AF_study_fraction')]:f[n]=f[a]/f[b]
 save(out,'Table_SY_f_exchangeability_summary.csv',f)
 suites={'SX':{'a':['Table_SX_a_sample.csv'],'b':['Table_SX_b_coverage.csv'],'c':['Table_SX_c_cohort_partition.csv','Table_SX_c_cohort_summary.csv','Table_SX_c_status_totals.csv','Table_SX_c_institution_audit.csv','Table_SX_c_unknown_label_coverage.csv'],'d':['Table_SX_d_alternative_sample_groups.csv','Table_SX_d_metric_eligibility.csv','Table_SX_d_common_fixed_IDs.csv','Table_SX_d_author_missingness.csv']},
 'SY':{'a':['Table_SY_a_full_annual.csv','country_group_year_primary.csv','new_weighting_annual.csv','new_weighting_disparities.csv'],
 'b':['Table_SY_b_all_benchmarks.csv','independent_analytic_check_annual.csv'],'c':['Table_SY_c_annual_benchmark.csv','benchmark_annual_gap_replicates.csv','benchmark_annual_coverage_replicates.csv'],
 'd':['Table_SY_d_growth_components.csv'],'e':['Table_SY_e_sensitivity_status.csv','new_weighting_endpoints.csv','new_continuous_scale_predictions.csv','new_continuous_scale_bins.csv','new_continuous_bin_summary.csv','new_continuous_model_coefficients.csv','new_continuous_country_predictions.csv'],
 'f':['Table_SY_f_exchangeability_summary.csv','new_N20_exchangeability.csv','new_strata_diagnostics.csv','optional_activity_opportunity_decomposition.csv','optional_activity_opportunity_means.csv']}}
 for suite,parts in suites.items():
  body=f'# Table {suite} 套表\n\n'
  for part,names in parts.items():body+=f'## {suite}-{part}\n\n'+'\n'.join(f'- [{n}]({n})' for n in names)+'\n\n'
  write(out,f'tables/Table_{suite}_index.md',body+'SX-c独立条件行可能重叠；partition表互斥可加总。SY敏感性不同估计目标不能混成同一个效应，空值由状态解释，不补零。\n\n[字段字典](field_dictionary.csv) · [入口](../README_zh.md)')
 dictionary=[]
 for name in sorted((out/'tables').glob('*.csv')):
  header=pd.read_csv(name,nrows=0,keep_default_na=False).columns
  for col in header:
   countlike=col in ['fixed_N','active_N','AF_N','n_h','K_h','countries','institutions','draws','fixed_IDs','N_L','N_M','N_H','opportunity_relations','mutable_relations','AF_relations','mutable_AF_relations','studies','mutable_studies','AF_studies','mutable_AF_studies','strata','mutable_strata','fixed_institutions','active_institutions','effective_countries'] or col.endswith(('_institutions','_countries','_studies','_relations','_draws','_n'))
   unit='percentage_points' if col.endswith('_pp') or col in ['G_pp','r_pp','expected_delta_G','actual_delta_G','excess','delta_G','G2021','G2025'] else 'percent' if col.endswith('_pct') else 'integer_count' if countlike else 'calendar_year' if col=='year' else 'ratio_no_units' if col in ['R','R2021','R2025'] else 'proportion_0_to_1' if col in ['A','B','Q','C','analytic_A','coverage','predicted_coverage','percentile'] or col.endswith('_fraction') else 'identifier_or_descriptor_see_source_contract'
   dictionary.append({'table':name.name,'column':col,'units':unit,'empty_policy':'undefined/not applicable/empty bin/no interval; consult status column or Methods; never substitute zero','source':'frozen source or new documented analysis'})
 save(out,'field_dictionary.csv',pd.DataFrame(dictionary))

METHODS_ZH='''# Methods M3–M4：机构发表覆盖、条件参照与敏感性

## M3.1 固定基线与国内分组
2015–2019至少一项适格研究的52,098家机构组成B0。唯一已知基线国家者50,371家；未知/多国家1,727家不以后期AF国家补齐。type-7三分位基于国内整数研究数V_i，边界并列归低组，不拆相同值。100家处于collapsed/empty组国家，另2,261家处于任组不足20的国家，主B2为48,010家/68国。L/M/H人数为17,602/14,720/15,688，固定组及分母不随年改。国家发表规模组依据独立基线国家研究数，cutpoints为5384.333333333333和16350.999999999993，国家High/Middle/Low为23/22/23；不是收入或R&D能力分组。

## M3.2 年度、累计与三个队列口径
各country/group固定N；A=当年至少一项机会池确认AF研究机构数/N，C=截至该年至少一项/N，含已确认主期前记录。全年重复论文不增加二元机构分子。主估计先国家内算率、再国家等权平均，R=Abar_L/Abar_H，G=100(Abar_H−Abar_L)，ΔG=G2025−G2021。R无单位，G为百分点；H为0则R为NA，不加伪计数。年度覆盖包含首次及再次发表，不能称进入率或同机构持续参与率。

ED3使用B0中日期可识别首次出现、无确认主期前参与的6,369家；年份16/562/1636/1551/1231/1373，时期41/4249/2079。AF2为2021-07至2024-04，AF3为2024-05至2025-12；时期长度不同，计数不是速率。B2日期队列仅6,040家，而2025 pool/year累计覆盖7,654家，包含主期前；不能互换分子。全B0状态2主期前确认、6,369日期队列、1,663仅年份/其他旧队列排除、44,064无确认记录。1,663不是纯日期缺失，无确认不是实际未使用。完整可加总与重叠条件表分开列于SX-c。

## M3.3 替代规模、加权与连续描述
作者规模为不同非空关联author ID并集，主样本38家作者未观测不记0；重新分组后伊拉克不满足每组20，作者有效67国47,910。伙伴为基线共署名不同机构ID、去自身，允许主样本外伙伴，观察零保留；伙伴有效68国48,010。共同样本固定相同67国47,910个机构ID，再分别重分组；冻结ID及type-7切点独立核对。

S10b对固定B2逐国整数分子/分母分别计算国家等权mean(active/fixed)和合并机构Σactive/Σfixed，再求R/G，完整保留2020–2025，面板仅2021–2025。两权重估计目标不同，未把国家等权基准移给机构加权；不添效应CI。

S10d在拟合前固定logit二项模型、国家固定效应与限制性立方样条。x=(国内V_i平均秩−0.5)/国内N，同值共秩；y为first_pool_AF_year≤2025。空year表示未观察到确认pool发表，不认证真实未使用；不以日期队列替代。4个总结点取B2百分位分布5/35/65/95分位；重复结点按唯一结点降到3或2，不按显著性择模。尾部施加线性限制，样条基中心化/标准化；68个国家截距加3样条项，无重复全局截距。机构似然每家权重1，预测时在同一x网格对68国概率等权平均。拟合与标准化权重不同，单列说明。

SciPy/NumPy实现稳定logit似然、解析score/信息矩阵、Newton与回溯；最大100轮、归一化score容差1e-9。秩不足、分离或不收敛的预置fallback为全系数L2 λ=1e-6，保留失败与替代结果，不调参追求曲线。本次主模型收敛且未启用fallback。只给描述性点估计，不用机构独立SE带；模型不构成因果或国家依赖稳健推断。

国内百分位固定10箱，同值不拆，空箱NA。箱点为有非空箱国家的平均率，标签报告有效国家数，不能冒充固定68国目标。标准化曲线始终68国，超出部分国家观察百分位范围的部分画虚线；预测支持逐点保留。共同全68国观测范围约21.43–99.19百分位；范围外仅为明确标记的模型延伸。表中保留结点、系数、梯度有限差分核对、秩、收敛、原始箱计数与各国预测。

## M4.1 发表机会池与解析期望
冻结二元机会池2,200,061项研究、15,961项确认AF，未知AF标签不当阴性；原要求记录7,675项不确定主期AF标签排除二元池，该全局排除数不是把机构关系数相加重新估计。研究单位、AF标签和机构/国家映射未改。主h为primary_subfield(field)×year×完整已知country_set，保留document_type/team_bin作为变体条件。

每层n_h项研究、K_h确认标签；每轮无放回等概率抽K_h研究并向同篇全部机构共享标签。研究署名结构和每层K固定；不等于匹配AF/非AF团队规模分布，不据此检验已被条件固定的跨国扩散。机构无AF概率为各层comb(n_h−m_ih,K_h)/comb(n_h,K_h)之积，预期覆盖为1减该积；稳定log-gamma处理后按相同固定分母与国家权重聚合。正式期望为解析值，不能换成模拟均值或把平均覆盖之比当预期R。

本次复用seed20261024的5,000轮年度缓存与端点重复；不重新模拟，不因重绘更换draw order。解析ΔG=23.146794624720332pp；模拟均值23.143648721086013、MCSE0.006420333063631348只做数值核验。观察ΔG=20.142702753495918，D=−3.0040918712244142。所有差先完整精度计算再舍入。主d是未中心化ΔG分布，S9为逐点2.5/97.5分位参考带，不是同时CI或效应CI；centered null若保留在表中，应位于0附近，不能平移到观察D当误差线。既有p/Holm按原假设族存表，不新增显著性星号。

## M4.2 两端、历史敏感性与N20诊断
rH为H观察增长减解析预期增长，rL同理，D=rH−rL。主e画实际/预期增长，H21.20/24.68pp、L1.06/1.54pp；两端均低于期望。加性贡献H为rH，L为−rL，不能相加两个负数。S10a核验N10/N20/N30源哈希、91/68/57国和端点；S10c核验document_type与原team_bin变体，不重命名为控制所有团队特征。两者是历史复用而非本轮新模拟。

本轮从冻结raw重新重建主及两个变体n/K与可变层0<K<n，分别报告层、研究、AF研究可变比例。主194,625层、3,620可变；研究1,224,425/2,200,061、AF14,524/15,961在可变层。完整raw关系6,585,658，过滤固定B2后6,347,340，零重复/零孤立关系；历史6,404,572是N10关系，不能误标N20。按国家×国内组报告N20机会关系、可变关系、AF关系、可变AF关系及分母；可变层占比不等于可变论文占比。

可选发表活动分解另表：B为当年有机会池研究机构率，Q为有机会者的AF率，各国内cell有A=B×Q；B=0时Q未定义。国家平均后mean(BQ)一般不等于mean(B)mean(Q)，不把缺少观测机会解释为停止科研。该表不额外占panel。

## 外推、版本与软件
固定基线聚焦2015–2019在相关领域发表者，不覆盖所有后来新设/新入领域机构。保留92.15%机构不证明全球国家体系代表性充分；N20排除机构少的体系。共同署名AF覆盖不认证独立开展、贡献角色或稳定使用。所有观察/模型结果是发表记录覆盖的描述或条件参照，不识别资源机制及AF因果效应。

本版六图21panel，主a–e、ED3/ED4、S8–S10为本节编号；与Finding1的ED3冲突明确登记，不自行挪用ED5。旧输出及Word不覆盖，提供正文插入稿及引用映射。实际软件和参数见analysis_config.json与provenance/runtime.json；无新增数据API、LLM或模拟。统计分析和科学可视化工作流说明不替代实证来源、独立验证或期刊技术接收认证。
'''

def write_documents(out):
 tables(out);specs,meta=source_data(out)
 w=table(out,'new_weighting_endpoints.csv').set_index('weighting');model=json.loads((out/'quality/continuous_model.json').read_text());q=table(out,'new_continuous_scale_predictions.csv')
 p25,p90=np.interp([.25,.90],q.percentile,q.predicted_coverage)*100
 chinese=f'''# 机构参与：覆盖扩展、相对追赶与绝对差距扩大

国家总量无法说明AF是否触及不同前期规模的机构。我们固定2015–2019已有适格研究的52,098家机构，并保留未观察到AF发表者作为分母；国内前期发表量type-7三分位、并列归低组，各组至少20家后，主比较为68国48,010家。规模是前期发表量代理，不直接测量经费、人员或算力。

到2025年，国家等权累计覆盖为H37.91%、M8.30%、L2.35%（Fig.2a）。作者/伙伴替代分组及共同固定机构敏感性仍显示观察覆盖梯度（S8），但不分别识别人力或网络机制。累计口径包括确认主期前记录，不强制2020起点为零。

日期可识别首次发表队列另有6,369家，时期为41/4,249/2,079；时期时长不同，不作为进入率。该B0队列不同于B2中6,040家日期队列及2025年份/机会池累计覆盖7,654家（ED3；SX-c）。日期不明或未观察到确认发表均不证明实际未用AF。

年度低/高覆盖比由2021的0.0096升至2025的0.0445，表明相对追赶但仍远低于1；高减低绝对差则由3.36增至23.50个百分点（Fig.2b–c）。44个可配对国家中26个R上升，68国中67个绝对差扩大（ED4）。24个2021 H覆盖为零的国家R保留NA，不画成0；端点不证明逐年单调。

观察到的2021–2025绝对差扩大20.14个百分点，而发表机会基准正式解析预期23.15个百分点；按未舍入值计算，观察扩大低于预期3.00个百分点（Fig.2d；S9）。基准固定研究结构、年份/子学科/完整已知国家集合中的AF标签数，不是无AF反事实。5,000轮是冻结历史缓存，本轮没有新增模拟。

H端年度覆盖增长21.20个百分点，低于预期24.68；L端增长1.06，也低于预期1.54（Fig.2e）。rH=−3.48、rL=−0.48，净D=rH−rL=−3.00。较小扩大主要对应H端增长低于预期，而非L端超预期，不能改写为AF因果降低机构不平等。

新增机构加权结果同样显示绝对差扩大：G从{w.loc['pooled_institution','G2021_pp']:.2f}升至{w.loc['pooled_institution','G2025_pp']:.2f}个百分点，变化{w.loc['pooled_institution','delta_G_pp']:.2f}；国家等权变化20.14（S10b）。方向一致，但前者回答合并机构总体，后者回答典型国家，不能当作对真值的修正。历史门槛/基准条件敏感性完整保留（S10a/c），来源复核后复用，不冒称新模拟。

连续国内百分位模型在48,010家/68国上收敛，无惩罚fallback，保留国家固定效应并对68国等权标准化（S10d）。在所有国家共同观测支持内，第25至第90百分位预测覆盖约{p25:.2f}%至{p90:.2f}%，说明本模型下梯度不依赖三分位展示。模型是描述关联，不是规模独立因果作用；不提供依赖稳健CI。曲线超出部分国家观察范围时画虚线；原始十分箱有效国家44–68不等，不能与固定68国预测直接等同。

N20可交换性重新从raw核对，关系数6,347,340，区别于全池6,585,658及历史N10的6,404,572；主AF研究14,524/15,961处于可变层，不能仅据可变层数占比判断基准无效（SY-f）。国家/机构相关性、更细主题、信息缺失及固定基线外机构仍限制解释。本节仅论覆盖；进入后的再次发表留Finding3。

[入口](README_zh.md) · [方法](methods_zh.md) · [图注](captions_zh.md)
'''
 english=f'''# Institutional participation

Country-level growth may conceal uneven institutional participation. We therefore established a fixed framework of 52,098 institutions with eligible research in 2015–2019, retaining institutions with no confirmed AF publication. Within-country tertiles of baseline integer publication output, with ties kept together in the lower group, yielded 48,010 institutions across 68 countries with at least 20 institutions per group. These groups describe publication scale, rather than funding, staffing or computing resources (Methods M3; Table SX).

By 2025, equal-country cumulative AF coverage reached 37.91% among higher-output institutions, 8.30% among middle-output institutions and 2.35% among lower-output institutions (Fig.2a). Observed gradients were also present under linked-author and institutional-partner definitions, including the same fixed 47,910 institutions in 67 countries under both measures (Supplementary Fig.S8). These metadata measures do not separately identify human-resource or network mechanisms. Cumulative coverage retains confirmed pre-2020 participation rather than mechanically starting at zero.

A separate date-resolved first-publication cohort comprised 6,369 baseline institutions: 41 before July 2021, 4,249 during July 2021–April 2024 and 2,079 during May 2024–December 2025 (Extended Data Fig.3). These unequal-duration counts are not entry rates or first actual use dates. The date cohort differs from both the 6,040 date-resolved institutions within the main sample and its 7,654 institutions with confirmed pool/year coverage by 2025 (Table SX-c).

Annual coverage includes first and subsequent publications. Its lower-to-higher ratio increased from 0.0096 in 2021 to 0.0445 in 2025, indicating relative catch-up while remaining far from parity. Over the same period, the higher-minus-lower gap widened from 3.36 to 23.50 percentage points (pp; Fig.2b–c). Country-specific ratios increased in 26 of 44 countries with defined values at both endpoints, whereas absolute gaps widened in 67 of 68 countries (Extended Data Fig.4). Twenty-four undefined 2021 ratios remain NA; connected endpoints do not establish monotonic annual trajectories.

Higher publication opportunity can itself increase the probability of at least one AF paper. We therefore retained the frozen publication-opportunity benchmark that reassigns AF labels within year, primary subfield and complete known-country sets while preserving each study's affiliations. Observed gap widening was 20.14 pp, compared with the exact analytic expectation of 23.15 pp: 3.00 pp less widening, calculated before rounding (Fig.2d). The 5,000 cached reassignments provide conditional reference variation, not a causal-effect confidence interval or a world-without-AF counterfactual (Methods M4; Supplementary Fig.S9).

Smaller-than-expected widening arose mainly from the higher-output end. Annual coverage increased by 21.20 pp in that group versus 24.68 expected; lower-output coverage increased by 1.06 pp versus 1.54 expected (Fig.2e). Growth was below expectation at both ends. The signed deviations, −3.48 and −0.48 pp, combine by subtraction to give −3.00 pp; they cannot be added as two negative contributions. The result does not demonstrate above-benchmark gains among lower-output institutions or a causal AF reduction in inequality.

The new weighting check showed widening under pooled-institution weights as well: the gap rose from {w.loc['pooled_institution','G2021_pp']:.2f} to {w.loc['pooled_institution','G2025_pp']:.2f} pp, a {w.loc['pooled_institution','delta_G_pp']:.2f}-pp change, compared with 20.14 under equal country weights (Supplementary Fig.S10b). These target different summaries rather than corrected versus uncorrected truth. Threshold and benchmark-stratum checks retain their historically frozen results after source audits (S10a,c).

A prespecified restricted-cubic-spline logistic description of domestic baseline publication percentiles, with country fixed effects, converged without penalized fallback (S10d). Equally standardized across 68 countries, predicted cumulative coverage was approximately {p25:.2f}% at the 25th percentile and {p90:.2f}% at the 90th, both within the common observed rank range. This model-based gradient is not restricted to a tertile display, but remains associational. No dependence-robust confidence band is claimed. Out-of-country-range predictions are dashed; raw-bin country counts vary from 44 to 68 and do not share the standardized target.

New N20 diagnostics identified 6,347,340 institutional-study relations, distinct from the 6,585,658 full relations and the historical N10 count. In the primary strata, 14,524 of 15,961 AF studies were exchangeable. These diagnostics describe the conditional benchmark's scope, not its causal validity (Table SY-f). Together, institutional coverage expanded alongside relative catch-up and wider absolute gaps. We next examine subsequent AF publication after an institution's first appearance, rather than interpreting annual coverage as sustained use.

[Reading index](README_zh.md) · [Methods](methods_en.md)
'''
 write(out,'results_zh.md',chinese);write(out,'results_en.md',english);write(out,'methods_zh.md',METHODS_ZH+'\n\n[入口](README_zh.md) · [配置](analysis_config.json) · [运行环境](provenance/runtime.json)')
 # English method specification mirrors all implementation decisions without relying on an unavailable library.
 methods_en='''# Methods M3–M4

M3.1 Baseline B0 comprises 52,098 institutions; B1 has 50,371 unique known baseline countries. After invalid tertiles (100 institutions) and the minimum-20 rule (2,261), B2 contains 48,010 institutions/68 countries, with L/M/H=17,602/14,720/15,688. Integer baseline 2015–2019 output uses type-7 cutpoints; boundary ties remain lower. National output groups are distinct from domestic institution groups and contain 23/22/23 countries. No post-AF country replacement is made.

M3.2 A is the fraction of a fixed domestic group with at least one confirmed pool AF study in year t; C is the fraction by t, including prior confirmed years. Countries are equally weighted before R=AbarL/AbarH and G=100(AbarH−AbarL); zero H makes R undefined. ΔG=G2025−G2021. Annual coverage includes first and repeat publication, not entry hazard or sustained participation. Date-resolved B0 entry is a separate 6,369 cohort (41/4,249/2,079 by publication era); B2 has 6,040 of these but 7,654 pool/year-covered institutions. B0 states partition into 2 pre-2020, 6,369 date-resolved, 1,663 year-only/other legacy exclusions and 44,064 without confirmed publication. Unknown is not certified non-use.

M3.3 Alternative linked-author and other-institution partner counts use fixed baseline metadata; 38 unobserved author scales are not zeros. Author eligibility gives 47,910/67, partners 48,010/68. Common-valid panels use identical 47,910 IDs in 67 countries and reclassified domestic cutpoints for each measure. Pooled-institution coverage is summed active/summed fixed counts, not a mean country ratio; its target differs from equal-country coverage. No equal-country benchmark is transferred to pooled weights.

M3.4 The new binary logit model uses first_pool_AF_year≤2025 and domestic midrank percentile (average_rank−0.5)/country N, with tied values sharing ranks and bins. Four total restricted cubic spline knots are the pooled percentile's 5/35/65/95 quantiles. Duplicate knots reduce to unique 3 or 2 knots; the latter is linear. Country fixed intercepts and centered/scaled natural-tail spline terms have no duplicate global intercept. Each institution contributes one likelihood unit. Predictions average the same 68 country probabilities at each x. A SciPy/NumPy Newton solver uses exact score/information, backtracking, at most 100 iterations and normalized score tolerance 1e-9. The predeclared separation/rank/convergence fallback is L2 lambda=1e-6 on all coefficients; original failure is retained. Primary fitting converged without fallback. A finite-difference score check, rank, coefficients, knot values, scaling, convergence and support diagnostics are retained. No independent-institution SE band or causal CI is drawn. Raw fixed-decile bins retain empty cells as NA and report varying available-country n; they are not the same fixed-country estimand. Dashed curve portions include country-specific rank extrapolation; common observed support is about 21.43–99.19 percentile.

M4.1 The frozen binary opportunity pool contains 2,200,061 studies and 15,961 AF labels; uncertain labels are not coded negative. The handoff records 7,675 uncertain main-period labels excluded from this binary pool; this global count is archival, not obtained by summing institution relations. Within h=(primary subfield/year/complete known country set), n_h studies and K_h AF labels are fixed; uniformly drawing K_h without replacement assigns one shared label to every institution of that study. This preserves affiliations and country-set AF counts, not the AF/non-AF team-size distributions. It cannot test the cross-country diffusion already conditioned upon. No new AF identification, institution merging or data retrieval was done.

M4.2 Exact expected institution coverage is one minus the product over strata of comb(n_h−m_ih,K_h)/comb(n_h,K_h), with stable log-gamma/impossible-event handling, then the same fixed denominators and country weights. The formal expected 2021–2025 gap change is 23.146794624720332 pp; cached simulation mean 23.143648721086013 and MCSE0.006420333063631348 are numeric checks only. Observed20.142702753495918 minus analytic expectation gives −3.0040918712244142 pp. Cached 5,000 whole-study fixed-K draws/seed20261024 are reused, not rerun. Main d is uncentered ΔG; S9 intervals are pointwise 2.5/97.5 percentiles, not simultaneous or effect CIs. Centered null ranges stay around zero, never shifted to observed D. Legacy p/Holm remain archival with their original hypothesis family; no stars are added.

M4.3 rH/rL are observed-minus-expected coverage growth in the respective institution groups; D=rH−rL, with low-end additive contribution −rL. Both deviations are negative. Historical N10/N20/N30 and document_type/team_bin variants are source/endpoint audited, not described as newly simulated or controlling all team characteristics. New diagnostics reconstruct n/K from raw study keys and restrict membership counts to fixed B2 IDs. Main strata:194,625 total/3,620 mutable; mutable studies1,224,425/2,200,061 and AF14,524/15,961. Raw relations6,585,658; N20 relations6,347,340; historical N10 relations6,404,572 are distinct. Duplicated study-institution relations and orphans are zero. Relation/AF-relation mutable shares are reported separately by country/group and variant, not inferred from the fraction of mutable strata.

M4.4 Optional opportunity decomposition defines B=observed pool-publication activity and Q=AF among opportunity-active institutions. A=BQ holds within domestic cells; Q is undefined if B=0. Averaging country rates does not imply mean(A)=mean(B)mean(Q). Lack of pool opportunity does not establish cessation of research. The fixed baseline excludes some newer institutions/field entrants; 92.15% baseline retention does not establish global national representativeness. Coauthored coverage does not identify independent use or leadership. Conditional reference and spline associations do not identify causal effects. Local ED3/ED4 numbering conflicts with the latest Finding1 ED3 and is explicitly recorded pending global integration; S7/ED5 are not appropriated. Original releases and Word remain unchanged.

[Reading index](README_zh.md) · [Frozen model protocol](analysis_config.json) · [Runtime](provenance/runtime.json)
'''
 write(out,'methods_en.md',methods_en)
 en=(out/'provenance/requirements/06_captions/CAPTIONS_EN.md.source.txt').read_text();zh=(out/'provenance/requirements/06_captions/CAPTIONS_ZH.md.source.txt').read_text();alt=(out/'provenance/requirements/06_captions/ALT_TEXT_EN.md.source.txt').read_text()
 en=en.replace('English captions — generation drafts','Figure legends').replace('These captions describe the planned new layout. They are not confirmation that the new figures have been rendered. Replace pending fields only after the corresponding analyses have been completed and checked.','This release contains newly rendered figures. Historical frozen results and new analyses are identified separately.')
 en=en.replace('[PENDING: calculate the pooled estimates from fixed primary-sample counts]',f'(new pooled gap: {w.loc["pooled_institution","G2021_pp"]:.2f} to {w.loc["pooled_institution","G2025_pp"]:.2f} pp)').replace('[PENDING: fit and validate the prespecified descriptive model; document standardization, ties and uncertainty]','(new restricted cubic spline logit with country fixed effects; equal-country predictions; no inference band)')
 en=en.replace('Do not release this caption as final until b,d have been computed and all pending fields resolved.','The primary model converged without fallback. Dashed portions include out-of-country-range predictions; raw-bin n labels count available countries, so raw-bin and standardized targets differ. Full observed rank support across all countries is approximately 21.43–99.19 percentile.')
 zh=zh.replace('中文图注草稿','中文图注').replace('【待计算】',f'（新计算：机构加权G {w.loc["pooled_institution","G2021_pp"]:.2f}→{w.loc["pooled_institution","G2025_pp"]:.2f}pp）').replace('【待拟合/诊断】','（新模型已收敛，无fallback，仅描述性点估计）').replace('b/d完成前不能把本图列为正式成品。','虚线段含部分国家观察百分位范围外的预测；箱标签为有效国家数44–68，箱均值目标不同于固定68国标准化曲线，不称因果效应或依赖稳健CI。')
 alt=alt.replace('Planned sensitivity figure','Sensitivity figure').replace('Weighting and continuous-scale results are pending and must not be described as observed findings before computation.','Pooled-institution weighting also shows widening. The continuous country-standardized association is described without an inference band; raw-bin country coverage varies and extrapolated portions are dashed.')
 write(out,'captions_en.md',en+'\n\n[Reading index](README_zh.md)');write(out,'captions_zh.md',zh+'\n\n[入口](README_zh.md)');write(out,'alt_text_en.md',alt)
 guide='# 逐panel读者信息、方法与修改原因\n\n'
 for spec in specs:
  guide+='## '+spec['id']+'\n\n|panel|读者问题|具体图形和分析|本版变化|\n|---|---|---|---|\n'
  for panel in spec['panels']:
   m=next(x for x in meta if x['figure']==spec['id'] and x['panel']==panel['letter']);description=panel['visual'].replace('待计算','已新计算').replace('待拟合','已拟合');guide+=f'|[{panel["letter"]}]({m["source_data"]})|{panel["question"]}|{description}|{m["result_status"]}；口径按Methods和source metadata，不沿用旧字母含义|\n'
 write(out,'panel_guide_zh.md',guide+'\n[图注](captions_zh.md) · [Methods](methods_zh.md) · [入口](README_zh.md)')
 write(out,'compliance_zh.md','''# 要求对照与剩余边界

|要求|本版处理|
|---|---|
|六图21panel|Figure2 a–e，ED3/ED4各2，S8/S9/S10各4；新文件名，不复用旧a–c装新布局|
|原始结果保留|正式解析期望和5000轮缓存复用，无新模拟，无seed更换|
|S10b/d新增|两权重观察结果、固定国家标准化连续描述均新计算，原始箱与模型支持/收敛另表|
|N20诊断|raw重算，6347340关系，区别完整6585658与历史N106404572|
|SX/SY补表|互斥队列分区、重叠条件行、作者缺失、共同ID、全部年度重复和敏感性分别交付|
|样本/分母/缺失|固定B0/B2、type7并列归低、0参与保留、NA不画零；6369/6040/7654分开|
|解读|两端都低于基准，未写低端超预期；比值无单位、差为pp；不声称资源因果机制|
|版式|183mm宽；主215mm高，ED3 112mm，ED4 260mm，S8/S9 165mm/S10 175mm；字母无长标题|
|原稿修正|4249、higher-output group、remained far from parity；本节不再包含再次发表主panel|
|全稿编号|本节遵守ED3/ED4与S8–S10，不占S7/ED5；与Finding1 ED3的冲突显式未全局解决|

图件和科学代码的实际检查见quality，不复制历史PASS作本轮验证。连续模型无依赖稳健CI、未进行因果识别。原始Word不覆盖，本版提供完整中英文插入稿与引用映射。正式全稿唯一编号仍需协调；期刊接收认证不在本轮范围。
''')
 write(out,'manuscript/reference_mapping.md','''# 原稿引用与编号

- 新Fig2a：累计覆盖；新b/c：总体年度R/G；新d：未中心化ΔG基准分布；新e：旧S10总体两端分解。
- 旧国家组端点退出主图，完整年度进S9和SY；旧S9重复端点分布不重复画。
- ED3a为样本纳入，ED3b为日期队列年度计数；ED4逐国R/G。
- S8扩为四panel，显示共同固定机构；新S10为稳健性，含新计算加权与连续模型。
- AF2 4239→4249；higher-output output→higher-output group；retained far from parity→remained far from parity。
- 再次发表和固定随访不在本节，保留Finding3；仅在结尾衔接。

## 显式冲突

Finding1最新包使用本地ED1–3；本目录要求Finding2 ED3/ED4且不得占用ED5。此处以章节限定F1-ED3/F2-ED3等作为唯一工作ID，不静默改为ED4/ED5，不声称全稿编号已统一。最终合稿需统一分配；原Word与旧章节文件均未覆盖。

[新中文Results](../results_zh.md) · [English Results](../results_en.md) · [入口](../README_zh.md)
''')
 figurelinks='\n'.join(f'- **{name}**：[PDF](figures/{folder}/{name}.pdf) · [SVG](figures/{folder}/{name}.svg) · [600dpi PNG](figures/{folder}/{name}_600dpi.png) · [LZW TIFF](figures/{folder}/{name}_600dpi.tiff) · [预览](figures/{folder}/{name}_preview.png)' for name,folder in FIGURES.items())
 write(out,'README_zh.md',f'''# Finding 2 v7 阅读入口

严格按用户目录的六图21panel实施。冻结AF标签、研究/机构单位和基准结果不变；新增加权、连续国内规模、N20关系诊断与队列完整性表。无新增数据API/LLM调用，无新增模拟。

## 图件

{figurelinks}

## 正文与方法

[中文Results](results_zh.md) · [English Results](results_en.md) · [中文Methods M3/M4](methods_zh.md) · [English Methods](methods_en.md) · [中文图注](captions_zh.md) · [English legends](captions_en.md) · [English alt text](alt_text_en.md)

[逐panel读者信息和修改](panel_guide_zh.md) · [要求对照](compliance_zh.md) · [原稿引用与编号冲突](manuscript/reference_mapping.md)

## 数据与核对

[21panel直接Source Data](source_data/README_zh.md) · [Table SX](tables/Table_SX_index.md) · [Table SY](tables/Table_SY_index.md) · [协议配置](analysis_config.json) · [模型诊断](quality/continuous_model.json) · [数值检查](quality/numerical_checks.json) · [实际视觉检查](quality/visual_review.md) · [离线复现](REPRODUCE.md)

主结果为国家等权观察；机会基准正式期望为解析值，5000轮条件范围不是效应CI。两端均低于期望，不能写成低端超预期。连续曲线是描述关联，无依赖稳健或因果CI；原始箱国家组成可变。原Word/旧代码/旧数据保留，提供更新插入稿。ED全稿编号冲突显式待协调，不占S7/ED5。
''')
 write(out,'REPRODUCE.md','''# 离线复现

依赖现有Python及NumPy/Pandas/SciPy/PyArrow/DuckDB/Matplotlib/Pillow，实际版本见provenance/runtime.json；不依赖statsmodels/patsy，不联网。

只重绘：`python code/run.py --package-root /解压后的包根 --output-root /新目录 --redraw-only`。
重新计算本轮新增分析及重绘：同命令去掉`--redraw-only`。输入是包内冻结CSV/Parquet；原有5000轮基准仍复用，不重新模拟。输出目录必须不存在。验证：`python code/validate.py --root /包根`。

原代码/文献数据库不是运行依赖；历史说明按.source.txt存档，不作为当前导航。raw包含公开学术机构ID和研究关系，用于离线审计，不包含API密钥。独立数值核对与模型梯度检查不能认证因果、依赖稳健推断或期刊技术接收。原始交接hash保留，所有输入只读。
''')
