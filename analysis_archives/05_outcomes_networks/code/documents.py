"""Bilingual evidence-linked text; numerical values are generated, never hand typed."""
from common import *
def md(path,text):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text.strip()+'\n')
def link(path,base):
 import os
 return os.path.relpath(P/path,base)
def main():
 primary=pd.read_csv(T/'primary_estimates.csv');est=pd.read_csv(T/'T_SI3_estimates.csv');net=pd.read_csv(T/'T_SI9_network_models.csv');status=json.loads((Q/'panel_status.json').read_text());reg=pd.read_csv(P/'specification/registry/panel_registry.csv',encoding='utf-8-sig');values={};rows=[]
 gm={'L':'low','M':'middle','H':'high'}
 for _,r in primary.iterrows():
  f='fig6a' if r.sample_id=='journal_full2025' else 'fig6b';key=f+'.'+r.sample_id+'.'+gm[r.group]+'.'+r.metric;values[key]={k:(None if pd.isna(v) else v) for k,v in r.to_dict().items()};rows.append(dict(result_key=key,figure=f,source='tables/primary_estimates.csv'))
 for outcome,metric in [('journal','journal_position'),('citation','percentile_12m')]:
  for kind,l in [('own','a'),('partner','b')]:
   z=net[net.outcome.eq(outcome)&net.sample_id.eq('degree_'+kind)&net.metric.eq(metric)&net.coefficient.eq('slope')]
   for _,r in z.iterrows():
    key='fig7'+l+'.'+('degree' if kind=='own' else 'partner')+'.'+gm[r.group]+'.'+outcome+'_slope';values[key]={k:None if pd.isna(v) else v for k,v in r.to_dict().items()};rows.append(dict(result_key=key,figure='Fig7',source='tables/T_SI9_network_models.csv'))
 coverage=pd.read_csv(T/'coverage_summary_2024.csv')
 for _,r in coverage.iterrows():
  for event in ['af','venue','citation']:
   key='fig6c.fixed_B2_2020_2024.'+gm[r.group]+'.'+event;values[key]={'estimate':r[event+'_lower'],'upper':r[event+'_upper'],'unit':'percent','interval_type':'confirmed_possible_record_bounds_not_CI','n_countries':68,'fixed_group_denominator':{'L':17602,'M':14720,'H':15688}[r.group]};rows.append(dict(result_key=key,figure='Fig6',source='tables/coverage_summary_2024.csv'))
 dump(P/'manuscript/results_values.json',values);dump(P/'manuscript/cross_reference_map.json',rows)
 def fmt(r):return f'{r.estimate:.2f} [{r.lower:.2f}, {r.upper:.2f}]' if pd.notna(r.lower) else f'{r.estimate:.2f}（仅点估计）'
 def outcome_table(sample,metrics):
  text='|组别|指标|差异 [95%条件区间]|机构|唯一AF研究|唯一参照研究|\n|---|---|---:|---:|---:|---:|\n'
  for metric in metrics:
   for _,r in primary[primary.sample_id.eq(sample)&primary.metric.eq(metric)].iterrows():text+=f'|{r.group}|{metric}|{fmt(r)}|{int(r.n_institutions):,}|{int(r.n_af_works):,}|{int(r.n_control_works):,}|\n'
  return text
 jtab=outcome_table('journal_full2025',['journal_position','high_journal75']);ctab=outcome_table('citation_max',['percentile_12m','high_citation90']);ntab='|结果|预测量|组|斜率 [95%条件区间]|机构|唯一AF研究|\n|---|---|---|---:|---:|---:|\n'
 for outcome,metric in [('journal','journal_position'),('citation','percentile_12m')]:
  for kind in ['own','partner']:
   for _,r in net[net.outcome.eq(outcome)&net.sample_id.eq('degree_'+kind)&net.metric.eq(metric)&net.coefficient.eq('slope')].iterrows():ntab+=f'|{outcome}|{kind}|{r.group}|{fmt(r)}|{int(r.n_institutions):,}|{int(r.n_AF_unique):,}|\n'
 covtext='|组|至少一项AF研究|至少一项期刊≥75 AF研究|至少一项引用≥90 AF研究|\n|---|---:|---:|---:|\n'
 for _,r in coverage.set_index('group').reindex(['L','M','H']).reset_index().iterrows():covtext+='|'+r.group+'|'+'|'.join(f'{r[e+"_lower"]:.2f}–{r[e+"_upper"]:.2f}%' for e in ['af','venue','citation'])+'|\n'
 zh=f'''# Finding 5：科学关注、发表渠道与观察合作网络（v2.0）

本版按2026-11-01规范重建两条成果主分支，所有数值来自[稳定结果键](results_values.json)。L/M/H沿用2015–2019基线机构产出分组，不能解释为资源、算力或研究质量等级。全文是观察性比较。

## 同机构同期参照中的渠道与引用差异

[Figure 6](../figures/main/Fig6.png) a采用2020–2025期刊最大可比样本，b采用2020–2024成熟12个月引用最大样本。每项AF研究先与同机构、同发表年、同OpenAlex子领域、同文献类型的所有可用screen-negative研究比较，再在机构内对AF研究等权、机构间等权。两者不强制共享研究集合。下表前一类指标单位为分位点，阈值比例差单位为百分点。

{jtab}
{ctab}
在上述实际可比机构中，两类主结果各组平均差异为正。但不能据此说AF使文章质量提高、AF造成被引增长，或低产出机构总体机会已趋同。期刊指标衡量发表渠道的历史年度位置，引用指标衡量已收集语料内同龄同领域研究的相对引用关注。它们不是单篇研究质量的直接量尺。

## 固定总体覆盖与选择

Figure 6c保留全部48,010家B2机构（L=17,602、M=14,720、H=15,688）、相同68个国家和2020–2024窗口。先算国家×组覆盖，再对同68个国家等权。以下区间是记录不确定性的确认—可能上下界，不是置信区间。

{covtext}
少数已进入、可匹配机构的相对成果优势，与固定总体中低组较低的参与和成果覆盖同时存在，不能以条件样本的平均差异替代总体机会判断。2025年完整期刊/参与覆盖另列S-SI5f；没有将不成熟引用填为零。

## 基线网络位置及当前合作情境

[Figure 7](../figures/main/Fig7.png)使用2015–2019观察到的研究—机构共同署名网。B2网络48,010节点中47,972有可观察基线、1,822在该边界内为观察零连接；38家无可观察历史，指标保留缺失。基线有2,613,830条不同无向边。自身degree是不同合作机构数，不是质量、领导或桥接能力评分。伙伴身份来自当前AF研究，但评分来自历史网络；始终排除焦点机构。

{ntab}
own斜率单位是每增加1单位log(1+degree)的成果分位差变化；partner单位是当前AF伙伴的基线degree百分位均值每增加10点的变化。不同结果的有效机构和AF集合分别重建。Figure 7b主展示L；M/H全部结果保留在ED-SI4及表中，不按方向筛选。

自身位置的方向依结果和组别而异。低组自身degree与期刊差异正向关联，其引用斜率区间跨零；高组自身degree与期刊差异为负、与引用差异为正。低组伙伴斜率的两个区间均跨零，当前数据不能支持“与更中心伙伴合作就有稳定优势”的普遍论断。中/高组伙伴引用关联较明确，也不能作因果解释。

M1控制基线发文量、国家、年份、上位领域、文献类型并允许组别×自身位置交互；M2增加伙伴评分。M1在M2完全相同伙伴样本上另行拟合，防止把样本改变误读为系数调整。8个预定调整拟合均完成5,000/5,000次条件重采样。完整系数、设计矩阵秩、保守有效自由度、逐国留一、杠杆及重叠x范围检查见[T-SI9](../tables/T_SI9.csv)及[S-SI8](../figures/supplementary/S_SI8.png)。不以调整前后系数变化比例推断中介机制。

## 敏感性与可评估边界

共同2020–2024样本仅作选择敏感性。原共同起点的可比历史期刊比较，在L组最低历史数1/3/5/10时只有23/7/1/0家机构，不能将单机构负值当作总体逆转，也不能声称历史阈值稳健。稳定作者比较只支持H组453作者、288机构、380项AF研究；L/M没有共同支持。四类AF活动可重叠，未知不当作未使用；独立人工活动验证仍未完成。

全部预设权重、匹配、阈值、网络边界、滞后滚动网络、大团队剔除和伙伴缺失处理都列入[执行状态](../tables/T_SI5.csv)，包含负值、跨零和不可估计分支。网络主伙伴门槛仅认证“本地观察作者名单均有归属且所有观察伙伴可评分”，不等于出版方完整机构名单认证。严格出版方认证分支仍不可计算。作者自引排除和独立第二期刊来源也缺可靠输入，S-SI4d没有制作假面板。案例仅保留补充证据审阅，未恢复主案例。

## 读图及复核入口

[方法正文](methods_zh.md)；[逐图中文图注](../captions/captions_zh.md)；[英文图注](../captions/captions_en.md)；[全部面板与来源](../panel_index.md)；[六项补充说明](../supplementary/README.md)。本轮未新增API或LLM调用，沿用冻结语料；新结果不能弥补数据库覆盖和未观察资源等限制。
'''
 md(P/'manuscript/results_zh.md',zh)
 en=f'''# Scientific influence, publication venues and observed collaboration networks (v2.0)

The journal and citation branches use independently maximized comparable samples, rather than restricting both to their intersection. L/M/H denote frozen 2015–2019 institution publication-scale groups, not resource or quality classes. Journal outcomes cover 2020–2025; citation outcomes cover mature 12-month records published in 2020–2024. AF studies are compared with all usable screen-negative studies from the same institution, publication year, primary subfield and document type. Studies are averaged within institutions, then institutions receive equal weight.

## Relative outcomes among comparable institutions

{jtab}
{ctab}
All three groups have positive mean differences in the primary comparable samples. Percentile differences are in percentile points; threshold-share differences are in percentage points. These estimates describe venue position and relative citation attention, not article quality or causal effects of AF adoption. The journal and citation samples have different institution and study counts, as shown above.

## Fixed-population coverage

Figure 6c retains the same 48,010 baseline institutions and 68 countries in 2020–2024. Country-by-group rates are averaged equally across the same 68 countries. These confirmed–possible record bounds are not confidence intervals.

{covtext}
Positive conditional outcomes among observed entrants coexist with substantially lower population participation and outcome coverage in L. The complete 2025 participation/venue comparison is reported separately; immature citation outcomes are not coded zero.

## Historical network position

Figure 7 uses the observed 2015–2019 institution coauthorship graph: 47,972 of 48,010 nodes have observed historical records, including 1,822 within-boundary observed isolates; 38 historical scores remain missing. Degree counts distinct institutional collaborators. Current partners are identified from AF papers but scored using historical network positions, excluding the focal institution.

{ntab}
Own-position slopes are per unit log(1+degree); partner slopes are per 10 historical degree-percentile points. Own-position associations differ by outcome and group. In L, the journal association is positive but the citation interval spans zero. In H, own-position slopes have opposite signs for the two outcomes. Both L partner intervals span zero. These results do not support a universal network-core advantage or a causal benefit from central partners.

M1 adjusts for baseline output, country, year, parent field and document type, with group-specific own-position slopes. M2 adds partner score; M1 is also fitted on exactly the M2 partner sample. All eight adjusted fits had 5,000 successful conditional replicates. No coefficient-change ratio is interpreted as mediation.

Historical comparability in L falls to 23/7/1/0 institutions for minimum historical counts of 1/3/5/10. Stable-author support exists only in H (453 authors, 288 institutions, 380 AF studies). Independent activity-label validation remains incomplete. Complete author lists from publishers and a second historical journal metric source are unavailable; certified self-citation removal and publisher-certified partner analyses remain not computable. The practical partner analysis requires coverage of all locally observed author IDs and all observed partner scores; it does not certify globally complete affiliations. Case evidence remains supplementary, with no restored main case panel.

All prespecified variants, negative/zero results, support losses and unavailable branches are retained in T-SI5 and T-SI9. Conditional intervals hold network measurement and baseline scores fixed and do not cover database selection or missing resources. [Methods](methods_en.md), [captions](../captions/captions_en.md), [panel index](../panel_index.md).
'''
 md(P/'manuscript/results_en.md',en)
 methods_zh='''# 方法正文（中文工作稿，v2.0）

## 语料、分析单位与版本

输入为本地冻结的OpenAlex来源元数据、批准work→study桥、AF判读层、作者与机构关联、2015–2025年度SCImago完整榜单衍生指标、已完成的入向引用边及质量状态。元数据原采集于包含2026-04-03的一周；新增引用边采集于2026-10-30至31。施引发表截止2025-12-31。输入逐文件SHA-256和大小见inputs/provenance.json；上游版本桥保留4,686,896个work记录、4,686,879个批准study。未批准版本关联保持分开，不能称全量人工去重。

研究单位为批准study的连贯代表记录。机构关联在study×institution去重；同研究跨机构/组出现时不把关系行数当唯一研究数。L/M/H及国家映射沿用Finding2 v7固定2015–2019基线框架。B2共48,010机构和68国家，含未观察到AF的机构；不因当前成果或网络重新分组。完整观察机构名单在边界筛选前建立，保留B2外伙伴和缺失标志。

## AF标签与比较样本

confirmed_AF采用已冻结“AF使用且纳入采用分析”判定；所有可用screen_negative是参照候选，未决标签不作非AF。AF-like技术未自动扩展为AF采用。活动层独立叠加，不更改AF核心标签；四类活动多标签重叠，supported、not_established和uncertain保持区分，未知不视作阴性。旧A/B/C加人工证据流程及输入版本保留在来源文件，本轮没有新增模型调用。

期刊主样本为2020–2025具有期刊位置及同期同机构参照的最大集合journal_full2025；引用主样本为2020–2024逐篇成熟且指标、参照可用的citation_max。共同2020–2024样本仅作敏感性，不能约束主分支。同期匹配单元是institution×year×primary_subfield×document_type，每指标独立要求至少1项可用参照，使用全部合格参照。月/季度与至少5项参照规格重新检验支持，不能称仅改变权重。比较链接按年流式输出，明确焦点study、机构、参照study、单元和状态。

## 历史期刊位置

按年度精确ISSN桥映射SCImago来源，保留多候选/缺失状态。每年度类别内按SJR从低到高取平均秩r，N≥2时分位=100(r−1)/(N−1)，并对来源的可用类别等权平均。并列按平均秩，不选最好类别。≥75主阈值、≥90替代；供应商best-category Q1单列，不能等同平均类别分位或独立来源验证。历史比较以原共同样本起点，使用2015–2019同机构、同子领域、同类型历史研究，按当前AF构成标准化；最少历史数1/3/5/10预定。无可比历史保持缺失。

## 固定窗口引用与相对分位

work边经批准study桥合并并去重为(citing_study,cited_study)，保留施引日期。39,552条study自连接留在原始边快照用于审计，但不进入窗口引用计数；这不等于作者自引排除。窗口为发表日起至12或24个月日历周年之前的半开区间；逐篇周年不晚于施引截止才成熟。已完成分页、质量未隔离且成熟的研究没有窗口内边才能计零；质量隔离、未成熟、无完整查询不得记零。2020–2025中341,286项质量隔离研究不恢复为零。12/24对照固定相同AF及可同时计算两窗口的参照集合。

引用参考集是已采集、合格、指标可用语料中的全部标签研究，非全球OpenAlex全集。先用子领域×发表年月×类型，最低100；不足按预定相邻月±1/±2扩大，再按上位领域同规则（0/±1/±2月，仍不足时全年）回退，均输出最终参考单元与样本量。最低50/200另作敏感性。分位=100(更低值数量+0.5×同值数量)/N，保留并列；≥90/≥95是阈值事件，实际比例不强制等于10%/5%。作者列表完整性没有认证，因此作者自引排除not_computable，不把无共享观察ID当非自引。

## 估计量、权重及条件区间

每项AF先减去其单元全部可用参照均值，机构内AF等权、机构间等权。主结果同时提供AF、参照绝对均值和差异。阈值差乘100为百分点，分位差为分位点。国家等权先机构再国家，论文等权按唯一AF，机构年等权单独标识；固定支持对照与改变支持严格区分。少于10机构保留点值，不绘稳定区间；无支持为NA。

共5,000次Exp(1)乘数重采样，种子20261029，每个批准study在任何AF/参照角色、机构、组、结果和模型共享同一乘数。SHA256 study ID键经SplitMix64结合种子/重复编号产生开放53位U，再取−log(U)。这是在新网络系数前冻结的可分块、跨子集一致实现；与v1逐样本PCG实现的点值和n完全一致，但蒙特卡洛区间末位可有差异。每轮重新计算参照均值、机构内权重、组汇总及模型权重。95%为2.5/97.5百分位；模型至少4,750次成功才展示稳定区间。区间条件于冻结标签、机构ID、期刊桥、参考集、网络边界/测量、协变量编码，不覆盖来源覆盖误差和未观测作者依赖等。

## 固定总体覆盖与观察机会

三事件是2020–2024至少一项AF、至少一项期刊分位≥75 AF、至少一项12个月引用分位≥90 AF。每国家×组固定分母包含无AF机构，然后对同68国家等权。确认界限只用肯定标签和已知达标指标；可能界限也允许AF/采用未决、指标缺失且未被排除的事件。确认—可能范围是记录不确定性界限，不是随机置信区间。2020–2025参与/期刊另表；不引入不成熟2025引用。机会对照使用first_AF_date+36月≤截止的固定进入队列，比较同机构0–12/0–24月成果覆盖；不是固定总体替代。原始元数据日期精度字段保留，不假设人工核实的精确出版日。

## 网络及伙伴

2015–2019构建无向study–institution投影，先完整观察名单去重，再限B2边界；去自环，边以不同机构对唯一，degree为不同邻居数。基线可观察但边界内无连接为0；无历史为NULL。扩展边界、观察作者名单覆盖子网、[t−3,t−1]滚动网络和m_all>20大团队诊断预定。滚动只用发表年前记录。主degree不随重复合作频率增加；fractional strength每篇边贡献1/(m_boundary−1)，节点每合作研究总贡献1，不是全篇边权和1。大团队排除按边界筛选前完整观察m_all，网络排除、成果AF和参照排除、两者排除分别执行并保留固定交集对照。

有效基线节点内degree/strength取中秩百分位，不在AF参与者子集重新排名。自身为log1p(degree)。当前AF每个焦点机构排除自身后求所有观察伙伴的历史degree百分位均值；主P和D使用完全同一批AF记录，机构内等权。单机构研究P缺失，作为独立描述，不记零。边界外、历史未知伙伴导致主P缺失，保留覆盖比例；仅已评分均值、≥80%覆盖及最大值仅作敏感性。

上游未收集出版方全名单或截断标志。可操作主分析仅要求本地每个已观察author ID非空、均可找到归属、没有多余未匹配作者ID，焦点在原始名单内，且每个观察伙伴有基线分数。该门槛叫observed-author-roster covered，不能写成publisher-certified complete。严格出版方完整性分支不可计算；这一偏离及其测量局限在冻结配置与图注披露。

## 连续关联及模型诊断

M0按组对机构均值D_i拟合线性自身x或P/10。预定门槛是≥10机构、≥10唯一AF、≥3不同x、最大共享研究涉及≤一半机构、最大机构杠杆≤0.5及非零x方差，不按方向/显著性筛选。曲线仅在真实观察范围且通过门槛时绘制；x相邻间隔超过组观察范围15%时断线，不连接无数据大缺口。带是同模型乘数得到的逐点95%条件带，不是同时带。

M1研究—焦点机构层面D_ip ~ group*log_degree + log1p(V_i) + country + year + parent_field + document_type；M2加P_ip/10。没有机构固定效应，以免吸收固定自身指标。每轮每机构记录权重和1。类别采用该固定模型样本实际观察水平的预定处理编码，不能为显著性删协变量；要求设计满秩，保守有效自由度min(n机构,n唯一AF)−rank≥30，另报名义行自由度。M1伙伴同样本和M2键完全一致。组斜率由同一次系数抽样的线性对比得区间；M2伙伴项是共同斜率，不能贴成L组特有效应。

预定诊断包括2rank/n_rows以上高杠杆记录剔除后完整公式重拟合、固定网络逐国留一的精确点重拟合、共享研究与机构杠杆/加权残差、三组观察x交集重新估计和产出/团队/合作情境相关性。逐国留一只移除该国焦点成果，不删外部伙伴或重建网络；不是全删除jackknife。所有失败/跨零/负值保留。M1/M2不解释因果、中介或资源机制。

## 活动、作者、案例与复现

第一/末位/通讯任一角色与其他已知角色在研究—机构层面互斥，原子角色可重叠，缺失不归其他；位置不等于实际领导。国内类别需本地观察作者归属覆盖、观察国家齐全；国际为至少两个观察国家，未知另列。稳定作者按冻结ID历史与当前唯一同机构，非外部身份认证，仅旧共同样本H有支持。案例保留候选、全文证据索引、归属疑点和排除，不恢复主案例。

所有面板都由同一summary/coordinates绘制，字母标记无长标题；可编辑PDF/SVG及300dpi白底PNG。每面板records_index链接实际分析记录，lineage含hash。source_data/logical/views.sql以包根目录运行可查询12项逻辑契约，无需重复存放大型边表。code/run_all.py可离线重建，保存中间缓存和输入hash，原v7未覆盖。输出manifest、实际解压核验与相对链接审计随包提供；这些检查不认证活动语义独立金标准或期刊编辑接受。
'''
 md(P/'manuscript/methods_zh.md',methods_zh)
 methods_en='''# Methods (v2.0)

## Records and independently supported outcomes

Frozen OpenAlex-derived metadata were originally downloaded in the week containing 3 April 2026; incoming citation edges were collected on 30–31 October 2026. The citing-publication cutoff is 31 December 2025. The approved bridge contains 4,686,896 work records representing 4,686,879 approved studies; unresolved version links are not silently merged. Institution membership is deduplicated per study. L/M/H and the 48,010-institution, 68-country B2 population retain Finding2 v7 baseline 2015–2019 grouping; neither is redefined by outcomes or networks. Full observed affiliations are assembled before imposing the B2 boundary.

Confirmed AF adoption uses the frozen core labels. All usable screen-negative records are reference candidates; uncertain labels are not controls. Activity labels are a separate, potentially overlapping layer with unknowns retained. No new API or LLM calls were made. Journal 2020–2025 and mature citation 2020–2024 maximum samples are built independently. Controls are all usable records within institution × publication year × primary subfield × document type, with at least one usable control per metric. Month/quarter and minimum-five specifications rematch and report support loss. Common 2020–2024 support is a sensitivity, not the primary denominator.

## Journal and citation measures

Annual SCImago sources are mapped through the frozen exact-ISSN bridge. Within annual categories of size N≥2, ascending average SJR rank r is transformed to 100(r−1)/(N−1). Available category percentiles are averaged equally, never chosen by the best category. Thresholds ≥75 and ≥90 are separate from supplier best-category Q1. Historical comparisons start from the legacy common sample and use 2015–2019 records of the same institution, subfield and type, standardized to current AF composition; minimum histories 1/3/5/10 are retained, missing support is not zero.

Citation edges are deduplicated after the approved study bridge. The39,552 study-self edges remain in the raw snapshot for audit but are excluded from citation counts; this is distinct from author self-citation removal. Counts use half-open calendar-anniversary windows [publication date, date+12 or 24 months). Each anniversary must be no later than the citing cutoff. Zero requires mature, completed, non-quarantined ascertainment and no observed in-window edge. Immaturity, absent completeness and the 341,286 quality-quarantined 2020–2025 studies remain missing. The 12/24-month comparison fixes both the AF records and jointly available controls. Percentiles use all labels in the collected eligible, assessable corpus, not the entire global OpenAlex database. Reference cells start at subfield × publication month × type (minimum100), expand by prespecified adjacent months ±1/±2, then parent field (0/±1/±2 months, finally the same full year); minimum50/200 are sensitivities. Midrank percentile is100(lower+0.5×ties)/N. High-citation thresholds are≥90/≥95, with actual rates retained. Complete citing/cited author rosters are not certified, so author self-citation removal is not computable.

## Estimation and uncertainty

Each AF observation is contrasted with its control-cell mean, averaged equally over AF studies within institution and then equally over institutions. Threshold differences are percentage points; percentile differences are percentile points. Country-, study- and institution-year-weighted variants state their distinct weights and support. Fewer than10 institutions receive point-only results; no support is NA. The5,000 Exp(1) study multipliers use seed20261029. SHA256 study keys and SplitMix64 generate open53-bit uniforms transformed by−log(U), producing identical weights across subsets, outcomes and AF/control roles. Reference means, institution aggregation and model weights are recomputed each draw. Unlike the legacy per-sample PCG implementation, this keyed implementation is cross-subset invariant; point estimates and n reconcile exactly while Monte Carlo interval endpoints can differ. At least4,750 successful draws are required for stable95% percentile intervals. Intervals condition on frozen measurement, labels, IDs, networks and design, and do not quantify database coverage error or all author dependence.

## Fixed coverage and observation opportunity

The same B2 population and2020–2024 window define ≥1 AF study, ≥1 AF journal-percentile≥75 study and ≥1 AF12-month-citation-percentile≥90 study. Country-by-group rates are averaged equally across the same68 countries, including institutions without AF. Filled confirmed/open possible endpoints bound unresolved label/metric records; they are not confidence intervals. AF/venue coverage through2025 is separate; immature citation2025 is not zero. The same mature entrant cohort, requiring first AF date+36months≤cutoff, is compared at0–12/0–24months. Metadata date precision is retained and not upgraded to externally certified exact publication dates.

## Networks, partner scores and models

The primary undirected2015–2019 B2 graph projects deduplicated study–institution affiliations, excludes self-loops and counts distinct neighbors. Observed historical isolates have degree0; no observed history is NULL. Expanded boundaries, observed-roster-covered histories, lagged[t−3,t−1] networks and large-team exclusions are prespecified. Fractional edges receive1/(m_boundary−1) per study, giving each participating node total strength1 per coauthored study. Full observed m_all before boundary restriction defines m_all>20 exclusions, separately applied to network construction, AF plus controls, and both. Fixed-intersection variants separate definition from selection changes. Scores are midrank percentiles across valid network nodes, never AF-only ranks.

Own score islog1p(degree). Current AF partners are scored from historical networks after removing the focal institution. The main partner mean requires every locally observed partner to be scoreable, the focal institution to be in the original roster, and all locally observed author IDs to be nonmissing and assigned. Publisher roster completeness/truncation flags were not collected; this practical observed-author coverage gate is not publisher-certified completeness. The strict publisher-certified branch remains unavailable. Single-institution studies have partner scoreNA and separate descriptive results, never0. Scored-partner means, coverage≥80% and maxima are distinct sensitivities. P_i and D_i use exactly the same AF studies.

M0 regresses equal-institution differences on own score or partner percentile/10 within group. Gates require≥10 institutions,≥10 unique AF studies,≥3 distinct predictor values, no study involving more than half the focal institutions, maximum institution leverage≤0.5 and nonzero predictor variance. Curves stay inside observed ranges and break across gaps exceeding15% of the group predictor range. Bands are pointwise conditional intervals, not simultaneous inference. M1 uses study–institution D_ip with group×log_degree, log1p(baseline output), country, year, parent field and document type; M2 adds partner percentile/10. There are no institution fixed effects. Each replicate normalizes row weights to sum1 within institution. Model-sample observed categorical levels are frozen; full rank and conservative effective residual degrees of freedom min(n_institutions,n_unique_AF)−rank≥30 are required. M1 is refitted on exactly the M2 partner sample. Group slopes are linear contrasts of joint coefficient draws; the M2 partner term is a pooled slope, not a low-group-specific effect.

Diagnostics retain all prespecified directions and include removal of rows with leverage>2rank/n_rows under the complete formula, exact point leave-focal-country-out refits with the network fixed, shared-study/institution leverage and residuals, observed common-x overlap, and contextual correlations. These are not a full deletion jackknife. No effect is interpreted as causality, mediation, institutional quality or resources.

## Labels and delivery

Any first/last/corresponding vs other known positions is mutually exclusive at study–institution level; atomic roles may overlap and missing roles are not other. Positions are not actual decision authority. Domestic categories require locally covered authors and known observed countries; international means≥2 observed countries; unknown remains separate. Frozen stable-ID author support exists only in the legacy H cohort, not external identity certification. Activities retain overlapping labels and uncertainty; independent human activity validation is incomplete. Case evidence remains supplementary because institution-specific affiliation/task attribution is unverified.

Each figure and panel has editablePDF/SVG,300dpi white-backgroundPNG and source records/links, summaries, plotting coordinates and hash lineage. Portable SQL contracts query original package inputs without duplicating large graphs. Offline code, frozen configuration, actual execution states, manifests and extraction/link checks accompany the package. These certify computational integrity within stated limits, not journal acceptance or independent semantic validation.
'''
 md(P/'manuscript/methods_en.md',methods_en)
 # Captions are bilingual and include exact per-panel sample tables rather than silently sharing n.
 overview={
 'Fig6':('相对成果与固定总体覆盖。a期刊2020–2025，b成熟12个月引用2020–2024；各取独立最大样本。c固定48,010机构、68国家、2020–2024，国家等权，实心确认、空心可能界限（非CI）。','Relative outcomes and fixed-population coverage. a: journal2020–2025; b: mature12-month citations2020–2024, independently maximized samples. c: fixed48,010 institutions/68 countries/2020–2024; equal-country confirmed/possible bounds, not CIs.'),
 'Fig7':('基线网络与机构成果差异。a按L/M/H分面自身log1p(degree)；b低组当前AF伙伴的历史degree百分位均值。点为真实机构，线及逐点95%条件带仅在可估计且有观察x支持处显示。伙伴主门槛仅为本地观察作者归属与伙伴评分齐备，非出版方完整名单认证。','Historical network positions and institution differences. a: ownlog1p(degree), facetedL/M/H; b: L current AF partners’ historical degree-percentile mean. Dots are institutions; M0 lines and pointwise95% conditional bands are restricted to estimable observed support. Local observed-author/partner coverage is not publisher-certified roster completeness.'),
 'ED_SI1':('机构期刊均值ECDF、完整差异分布、稀疏历史比较和同窗口样本选择。实线AF、虚线参照；分布中位数/IQR不是均值CI。','Institution journal ECDFs, full difference distributions, sparse comparable history and same-window sample selection. SolidAF/dashed reference; median/IQR are distribution summaries, not mean CIs.'),
 'ED_SI2':('机构引用ECDF和差异分布；固定AF及参照的12/24个月对照；同窗最大与共同样本。','Institution citation ECDFs and differences;12/24-month contrasts with identical AF/control support; same-window maximum vs common support.'),
 'ED_SI3':('稳定作者仅H有支持；低组署名位置与合作类别的结果；同构成支持损失。期刊实心、引用空心，各自最大样本。','Stable authors (H support only), low-group author positions, collaboration categories and common-composition support loss. Filled journal/open citation, outcome-specific maximum samples.'),
 'ED_SI4':('网络样本选择、同网络样本AF/参照绝对表现、预设调整模型、伙伴结果和覆盖情境。','Network selection, absolute AF/reference outcomes on the same network samples, prespecified adjusted models and partner results/context.'),
 'S_SI1':('并行流程、组别保留、重叠缺失与单篇参与/参照支持；重叠原因不能相加。','Parallel flow, group retention, overlapping missingness and single-study/control support; overlapping causes must not be added.'),
 'S_SI2':('四类活动各显示独立期刊/引用主样本的组别差异。未知不当阴性，多标签重叠，独立人工活动验证未完成。','Four activity-specific contrasts on independent journal/citation samples. Unknown is not negative; labels overlap and independent human validation remains incomplete.'),
 'S_SI3':('权重、参照数量/时间匹配、共同样本/年份范围和共同构成绝对值；改变支持不称纯重加权，构成比较仅点估计非因果DID。','Weights, control-count/time matching, common-sample/year-range and absolute common-composition diagnostics; support changes are not pure reweighting; composition contrasts are point-only, not causal DID.'),
 'S_SI4':('期刊阈值、供应商最佳类别Q1、引用阈值/参考集、广谱期刊剔除。d无认证完整作者列表及独立第二期刊来源，未生成。','Journal thresholds, supplier best-categoryQ1, citation thresholds/reference cells and Multidisciplinary exclusion. d is not generated: complete author lists and an independent second journal source are unavailable.'),
 'S_SI5':('年度轨迹、首次AF/活跃年数、机构AF研究数、同成熟进入队列12/24月机会及固定总体2024/2025覆盖。未成熟或无支持为NA；箱线中位数/IQR，须1.5IQR，极端点全保留。','Annual outcomes, first AF/active years, institution AF counts, fixed mature-entrant12/24-month opportunity and fixed-population2024/2025 coverage. Immature/unsupported values areNA; boxes show median/IQR,1.5IQR whiskers and all extremes.'),
 'S_SI6':('历史未见source比例、年度渠道位置、可比历史数量/年份/覆盖及最低历史支持。未见不等于真正首次进入，L历史n=23/7/1/0。','Baseline-unseen source share, annual venue positions, historical count/year/coverage and minimum-history support. Unseen is not first-ever entry; L history n=23/7/1/0.'),
 'S_SI7':('degree/分数strength、滞后滚动、边界、完整观察大团队m>20分别作用网络/AF与参照/两者的对照。固定交集另列。','Degree/fractional strength, lagged networks, boundaries and observed-team m>20 exclusions in network/outcomes/both. Fixed intersections are separate specifications.'),
 'S_SI8':('国家组别保留、情境相关性、伙伴完整性/最大值、模型残差与影响、可选历史已见/未见伙伴。','Country/group retention, contextual correlations, partner coverage/maxima, model residual/influence and optional previously observed/unobserved historical connections.')}
 for lang in ['zh','en']:
  content='# 图注（中文）\n\n' if lang=='zh' else '# Figure captions\n\n'
  content+=('通用：L浅蓝圆、M绿方、H深蓝三角；机构内AF等权后机构等权，稳定作者例外。横线是5,000次共享study Exp(1)条件95%区间；无稳定区间时只点或NA。网络固定2015–2019，固定覆盖界限另定义。所有n可跨组重叠，不将关联行视作唯一研究。\n\n' if lang=='zh' else 'General: L light-blue circles, M green squares, H dark-blue triangles. Equal AF-study weights within institutions, then equal institutions (stable-author analysis excepted). Intervals use5,000 shared-study Exp(1) conditional draws; unsupported intervals remain absent/NA. Network measurement is held fixed. Coverage bounds are separately defined. Counts can overlap across groups; affiliation rows are not unique studies.\n\n')
  for fid in reg.figure_id.drop_duplicates():
   level={'main':'main','extended':'extended','supplementary':'supplementary'}[reg[reg.figure_id.eq(fid)].level.iloc[0]];content+=f'## {fid}\n\n{overview[fid][0 if lang=="zh" else 1]}\n\n[PDF](../figures/{level}/{fid}.pdf) · [PNG](../figures/{level}/{fid}.png)\n\n'
   for _,r in reg[reg.figure_id.eq(fid)].iterrows():
    st=next(x for x in status if x['figure_id']==fid and x['panel_id']==r.panel_id);content+=f'- **{r.panel_id}** {r.title_zh if lang=="zh" else r.source_data_target.split("/")[-1]}: {st["status"]}. [Summary](../{st["source_data"]}/summary.csv) · [records & n](../{st["source_data"]}/records_index.csv) · [coordinates](../{st["source_data"]}/coordinates.csv). '+st['reason']+'\n'
   content+='\n'
  content+='\nDiagnostic companions: '+ ' · '.join(f'[{n}](../figures/supplementary/{n}.png)' for n in ['S_SI1_details','S_SI5_activity_year_details','S_SI6_history_details','S_SI8_model_details'])+'\n\n[Methods](../manuscript/methods_'+lang+'.md) · [all numerical results](../tables/T_SI3.csv) · [network coefficients](../tables/T_SI9.csv).\n';md(P/f'captions/captions_{lang}.md',content)
 notes=[('样本、期刊、同期和历史估计量','Samples, journals and comparison estimands','T_SI1.csv','T_SI4.csv'),('引用窗口、参考集、零与缺失','Citation windows, reference sets, zeros and missingness','citation_assessability.csv','T_SI2.csv'),('活动、作者位置、稳定作者及合作形式','Activities, author roles, stable authors and collaboration','activity_assessability.csv','stable_author_estimates.csv'),('案例全文证据与归属限制','Case evidence and affiliation limitations','T_SI7.csv','T_SI7.csv'),('固定总体、未决界限与观察机会','Fixed population, unresolved bounds and opportunity','T_SI6.csv','entry_opportunity_summary.csv'),('网络、伙伴、模型、条件区间和诊断','Networks, partners, models, conditional intervals and diagnostics','T_SI8.csv','T_SI9.csv')]
 sections=methods_zh.split('\n## ');en_sections=methods_en.split('\n## ')
 noteparas=[sections[1]+'\n\n'+sections[2]+'\n\n'+sections[3]+'\n\n'+sections[5],sections[4],sections[-1],'''案例候选表全部保留，未按期望方向选择主案例。病例A的“Vanke(China)”归属由provider提供但出版方未核实；全文只证明具体计算或实验组分，不能将任务归给焦点机构、推断资源限制、实验被AF替代或临床效果。原直接证据索引与候选排除原因可在cases目录逐项核对。未恢复Fig6d。''',sections[6],sections[7]+'\n\n'+sections[8]]
  # Notes are detailed bilingual methodological records, not new analyses.
 for k,(title,english,t1,t2) in enumerate(notes,1):
  extra='\n\n[Case candidates](../cases/candidates.csv) · [Evidence index](../cases/evidence_index.csv)' if k==4 else ''
  md(P/f'supplementary/N_SI{k}.md',f'# N-SI{k} {title}\n\n{noteparas[k-1]}\n\n## English scope\n\n{english}. Definitions and limitations are fully stated in the [English methods](../manuscript/methods_en.md). This note preserves record-level uncertainty, conditional interpretation and all unsupported branches; no semantic gold certification is implied.\n\n[Detailed table](../tables/{t1}) · [Additional support](../tables/{t2}) · [Chinese methods](../manuscript/methods_zh.md) · [English methods](../manuscript/methods_en.md){extra}')
 md(P/'supplementary/README.md','# 补充说明\n\n'+'\n'.join(f'- [N-SI{k} {x[0]}](N_SI{k}.md)' for k,x in enumerate(notes,1))+'\n\n[补充图](../panel_index.md)')
 # Every prescribed branch is accounted for, including unavailable conditions.
 states=pd.DataFrame(status);states['record_type']='panel';extra=pd.DataFrame([{'record_type':'data_dependent_branch','sample_id':name,'status':'not_computable','reason':reason} for name,reason in [('publisher_certified_partner','publisher roster completeness flag not collected'),('author_self_citation_removed','complete citing/cited author roster not certified'),('independent_second_journal_source','no independent historical journal source'),('stable_authors_L_M','no stable-author common support in L/M'),('independent_activity_validation','independent human activity validation not completed')]]);network_states=net[[c for c in ['outcome','sample_id','group','metric','model_id','coefficient','status','n_institutions','n_AF_unique','reason'] if c in net]].drop_duplicates().assign(record_type='network_specification');table('T_SI5',pd.concat([states,extra,network_states],ignore_index=True))
 branches=est[['sample_id','group','metric','status','n_institutions','n_af_works']].drop_duplicates();branches.to_csv(T/'T_SI5_outcome_specifications.csv',index=False)
 md(Q/'deviations_zh.md','''# 规范执行与局限\n\n1. 主伙伴使用本地观察作者/伙伴覆盖门槛；出版方完整名单标志未采集，严格认证分支not_computable。不能改称名单完整。\n2. 历史网络fractional m为边界内不同机构；完整m_all另保留，用于大团队阈值。\n3. 分块共享study键式Exp(1)实现取代v1逐样本随机流，点/n相同，MC端点可有差异。\n4. 稳定作者仅H；历史低组稀疏；独立活动验证、作者自引排除、第二独立期刊指标来源不可补造。\n5. 无主案例恢复；源机构归属仍有限制。\n6. 数值诊断不覆盖全部测量或选择误差，不支持因果、中介、质量或资源结论。\n7. 面板中原始完整记录通过records_index相对链接复用，不在56处重复大文件。网络大型逻辑表用可移植SQL视图，物理源文件均在包内。\n8. 不为参考样式补造数据；不可计算S-SI4d只交状态/schema，没有假图。''')
 # Human navigation with portable relative links.
 index='# 全面板导航\n\n|图|面板|内容|状态|图|数值及记录|\n|---|---|---|---|---|---|\n'
 for _,r in reg.iterrows():
  st=next(x for x in status if x['figure_id']==r.figure_id and x['panel_id']==r.panel_id);image=f'[PNG](figures/{r.level}/panels/{r.figure_id}_{r.panel_id}.png)' if st['status']=='completed' else '未生成（缺输入）';index+=f'|{r.figure_id}|{r.panel_id}|{r.title_zh}|{st["status"]}|{image}|[source]({st["source_data"]}/lineage.json)|\n'
 index+='\n## Readable diagnostic companions\n\n'+ '\n'.join(f'- [{name}](figures/supplementary/{name}.png) · [PDF](figures/supplementary/{name}.pdf)' for name in ['S_SI1_details','S_SI5_activity_year_details','S_SI6_history_details','S_SI8_model_details']);md(P/'panel_index.md',index)
 md(P/'README.md','''# Scientific Influence analysis v2.0\n\n按finding5-revision-plan-v8（内部规范v2.0）执行。旧版v7未覆盖。\n\n- [中文Results](manuscript/results_zh.md) · [中文Methods](manuscript/methods_zh.md)\n- [English Results](manuscript/results_en.md) · [English Methods](manuscript/methods_en.md)\n- [Fig6 PNG](figures/main/Fig6.png) · [PDF](figures/main/Fig6.pdf) · [SVG](figures/main/Fig6.svg)\n- [Fig7 PNG](figures/main/Fig7.png) · [PDF](figures/main/Fig7.pdf) · [SVG](figures/main/Fig7.svg)\n- [全部56面板导航](panel_index.md) · [中文图注](captions/captions_zh.md) · [英文图注](captions/captions_en.md)\n- [六项补充说明](supplementary/README.md) · [合并补充PDF](supplementary/supplementary_v2.0.pdf)\n- [执行状态](tables/T_SI5.csv) · [完整成果估计](tables/T_SI3.csv) · [网络模型](tables/T_SI9.csv)\n- [结果键](manuscript/results_values.json) · [冻结配置](analysis_config.frozen.json) · [局限与偏离](qa/deviations_zh.md)\n- [验证报告](qa/validation_report.json) · [输入hash](inputs/provenance.json) · [逻辑数据契约](source_data/logical/views.sql)\n\n## 离线复现\n\nPython依赖版本见environment.lock。从解压目录运行 `python code/run_all.py`；重用已验证中间缓存。所有输入与原始分析记录均为冻结快照，不读取env、API密钥或网络。`python code/verify.py` 核验本包。重新抽样/模型拟合可能耗时；5,000轮结果及抽样系数已存。完整图/表/正文由保存脚本生成，无手动调整坐标。\n\n本轮新增2张主图、4张ED、8张补充图及各可计算单面板，S-SI4d因缺输入不生成。网络主伙伴门槛是本地观察覆盖，非出版方完整名单。自引、第二期刊来源、L/M稳定作者和独立活动验证不作完成宣称。\n\n本目录内链接均为相对路径；外部参考网址仅作来源。完整ZIP包含复现输入；小型review ZIP仅用于阅图/文字，明确不含全部复现记录。''')
 md(P/'manuscript/data_lineage.md',"""# 数据依赖流程 / Data lineage

```mermaid
flowchart TB
    A["冻结输入与批准版本桥<br/>4,686,896 works → 4,686,879 studies"] --> B["连贯代表记录与去重机构关联"]
    A --> C["年度SCImago类别位置"]
    A --> D["10,409,791项唯一施引边<br/>窗口成熟与质量隔离"]
    B --> J["期刊2020–2025最大样本<br/>同机构、年、子领域、类型参照"]
    C --> J
    B --> K["引用2020–2024最大成熟样本<br/>同机构、年、子领域、类型参照"]
    D --> K
    B --> N["2015–2019观察共同署名网<br/>B2边界48,010节点"]
    N --> O["自身degree与当前伙伴历史评分<br/>观察名单门槛与缺失覆盖"]
    J --> M["机构等权差异与5,000共享研究乘数"]
    K --> M
    O --> R["M0及M1/M2、预定敏感性与支持诊断"]
    M --> R
    B --> F["固定48,010机构、68国家<br/>同窗三事件确认—可能界限"]
    M --> X["Figure 6、ED、补充图表与正文"]
    F --> X
    R --> Y["Figure 7、网络ED/补充图表与正文"]
    X --> Z["逐面板坐标、来源hash、结果键<br/>manifest与实际解压核验"]
    Y --> Z
```

两条主结果分支独立建立，交集只是同窗口敏感性，不能视作互斥筛选链。网络固定历史边界和分数，成果期未用于回填基线。可能界限是记录不确定性，不是CI。原始入向边数为批准study配对去重后的本地冻结数；质量隔离仍保留。

[方法](methods_zh.md) · [面板导航](../panel_index.md) · [输入hash](../inputs/provenance.json)
""")
 readme=P/'README.md';readme.write_text(readme.read_text()+'\n[数据依赖流程图](manuscript/data_lineage.md)\n')
 print('BILINGUAL MANUSCRIPT, CAPTIONS, SIX NOTES AND NAVIGATION COMPLETE',flush=True)
if __name__=='__main__':main()
