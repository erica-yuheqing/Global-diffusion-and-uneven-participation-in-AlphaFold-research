"""Bilingual evidence-linked manuscript, panel guide and seven logical table groups."""
from common import *
def tab(n):return pd.read_parquet(ROOT/'tables'/(n+'.parquet'))
def write(name,text): (ROOT/name).write_text(text.strip()+'\n')
def fmt(x,n=3):return f'{x:.{n}f}'
def main():
    R=tab('strict_main_R');D=tab('strict_main_delta');C=tab('strict_main_benchmark_change');P=tab('strict_main_pairings');S=tab('strict_main_structure');period=tab('period_direct_changes');nr=json.loads((ROOT/'provenance/N01_complete.json').read_text())
    for a in [R,D,C,P,S]: a.drop(a.index[~a.setting.eq('standardized')],inplace=True)
    def rr(cp,b,r):return R[R.corpus.eq(cp)&R.benchmark.eq(b)&R.role.eq(r)&R.entity_id.eq('group:lower')].iloc[0]
    def dd(b,r):return D[D.benchmark.eq(b)&D.role.eq(r)&D.entity_id.eq('group:lower')].iloc[0]
    def cc(r):return C[C.role.eq(r)&C.entity_id.eq('group:lower')].iloc[0]
    def ss(cp,cat):return S[S.corpus.eq(cp)&S.category.eq(cat)].iloc[0]
    def pp(cp,fg='higher',lg='higher'):return P[P.corpus.eq(cp)&P.first_group.eq(fg)&P.last_group.eq(lg)].iloc[0]
    def interval(x,value='delta'):return f'{x[value]:+.3f} [{x.ci_low:+.3f}, {x.ci_high:+.3f}]'
    f,l=cc('first'),cc('last');hh=pp('AF');hhr=pp('reference');hhd=pp('AF_minus_reference')
    cats=['same_country_same_institution','same_country_different_institutions','same_country_institutional_relation_unresolved','different_countries']
    structure_lines='\n'.join('|'+label+'|'+f'{100*ss("AF",cat).share:.2f}%|{100*ss("reference",cat).share:.2f}%|{100*ss("AF_minus_reference",cat).share:+.2f}|' for label,cat in zip(['同国同机构','同国不同机构','同国内机构关系未决','不同国家'],cats))
    write('manuscript/results_zh.md',f'''# Finding 4：主要署名是否与参与相称

本轮以用户指定Finding 4 v7及新的Figure 5专项要求为准。先完成逐篇核验，发现旧作者完整参照中6项由同一作者占据首末位置；按2026年10月30日明确确认统一排除。AF原始及共同支持均为5,087项，严格参照原始438,473项、共同支持332,760项，173个年份×类型×主要子领域单元。参照标准化权重合计5,087，ESS=193,059.65。旧版点、范围和图均保留，[旧新版逐点对照](../tables/Figure4_legacy_strict_comparison.csv)提供透明追溯。

## 参与基准改变了署名代表性的判断（Figure 4）

在相同研究、权重和首末位分子下，低基线发表规模国家组在AF中的国家产出信用份额为{100*rr('AF','country','first').participation_credit/5087:.6f}%，作者信用份额为{100*rr('AF','author','first').participation_credit/5087:.6f}%，首位及末位信用份额分别为{100*rr('AF','country','first').role_credit/5087:.6f}%和{100*rr('AF','country','last').role_credit/5087:.6f}%。因此，每篇按国家等分与按作者构成分配，提出的是不同的参与基准，并非两套独立贡献测量。

以国家产出为基准，低组AF首位R={rr('AF','country','first').R:.3f}、参照R={rr('reference','country','first').R:.3f}，AF−参照差为{interval(dd('country','first'))}；末位差为{interval(dd('country','last'))}。改用作者份额后，首位差为{interval(dd('author','first'))}，末位差为{interval(dd('author','last'))}。方括号是固定观察样本、支持和目标下2,000次整研究分层bootstrap的95%条件范围。

两基准共享同一研究的抽样次数，直接计算的基准变化C=ΔR作者−ΔR国家：首位{interval(f,'C')}，末位{interval(l,'C')}，均无量纲。C为正不能一概等同于更接近零；绝对差缩减B=|ΔR国家|−|ΔR作者|分别为{f.B:.3f} [{f.B_ci_low:.3f}, {f.B_ci_high:.3f}]及{l.B:.3f} [{l.B_ci_low:.3f}, {l.B_ci_high:.3f}]。特别是末位B的条件范围包括零。结果支持“署名差异的描述依赖参与基准”，不能解释为公平已被证明、作者规模因果解释了某一比例，或低组没有潜在差异。

[Figure 4 PDF](../figures/Figure4.pdf) · [Figure 4预览](../figures/Figure4_preview.png) · [完整R](../tables/strict_main_R.csv) · [直接差及C/B](../source_data/F4_T2.md)

## 首末位置如何组合（Figure 5 / F4_PAIRING）

Figure 5a、b、c严格使用与Figure 4相同的研究ID和权重。机构缺失不剔除研究；角色国家信用先在其实际对齐机构中分摊，无法对齐的国家信用保留为institution_unknown。四个互斥类别如下，差值单位为百分点。

|首末配对结构|AF|参照|AF−参照|
|---|---:|---:|---:|
{structure_lines}

AF首末同国总信用为{100*(1-ss('AF','different_countries').share):.2f}%，参照为{100*(1-ss('reference','different_countries').share):.2f}%。因此，团队国际化不等于两个主要署名位置跨国；但这也不能证明其他国家被排斥。多重归属用分数配对信用，不将这些百分比称作拥有唯一来源的论文比例。不同国家优先归跨国，即使同一机构ID出现在不同实际国家；两个unknown从不判为同机构。

Figure 5b保留higher/middle/lower/outside全部16种组合，高→高占AF配对信用的{100*hh.observed_share:.2f}%，参照为{100*hhr.observed_share:.2f}%。同组不等于同国：两名高组国家作者可以来自不同国家。每个语料各自归一为100%，连线没有知识或权力流动含义。

Figure 5c在同一团队中均匀抽取两名不同作者建立构成参照。AF高→高精确期望为{100*hh.expected_share:.2f}%，观察−期望为{hh.observed_minus_expected_pp:+.2f}个百分点，条件范围[{hh.deviation_ci_low:.2f}, {hh.deviation_ci_high:.2f}]；参照超额为{hhr.observed_minus_expected_pp:+.2f}个百分点。直接AF−参照超额差为{interval(hhd,'observed_minus_expected_pp')}个百分点。这一高→高对照未给出明确AF特异超额方向；不能将其泛化为全部16格没有差异。全部格、稀疏/零格、反向及直接方向对比均在T6完整提供，不按区间筛选。

构成参照并未固定观察首末边际，也未控制资历、实际贡献或职责。O−E不是“控制署名边际后的合作偏好”，首末顺序不是实际指导、支配或公平的认证。

[Figure 5 PDF](../figures/Figure5.pdf) · [Figure 5预览](../figures/Figure5_preview.png) · [完整配对与期望](../source_data/F4_T6.md)

## 国内机构、有限机会及时期稳健性

国内机构R按每国机构信用分别归一；中位数和IQR描述机构异质性，不能与国家组汇总R或旧全球机构R混用。预选US/CN/GB均属高国家组，英国低基线机构组仅5家。共同机构对比先逐机构相减，再汇总差值；不以两个中位数之差替代。

N05另要求观察作者ID一致且首末作者不同，可参照机构研究为AF 5,425项、参照477,291项，与主国家配对和历史全部机构分母不同。得到任意正机构角色信用的概率pi使用隶属该机构的作者人数/团队作者数；分数角色信用q另算，不能拿q代替pi计算零机会。在AF首次角色分母有定义的5,719个国家—机构单位中，3,213个观察为零，团队端点参照的期望零单位数为3,157.18。单位是国家—机构，不是去重全球机构ID。该有限差距及完整条件模拟范围见T7，不升级为排斥、能力不足或贡献不平等解释。末位、参照及1/2–4/5–9/10+参与机会箱同样完整保留。

支持门槛1/5/10/20、严格跨作者国际、机构关系完整、唯一国家角色及其正确候选池都已运行。唯一国家且唯一机构结构子样本原始覆盖AF 2,336/5,087、参照203,327/438,473，另做对称支持，不能用其替代主样本。AF2与AF3共享领域×类型的AF合并目标，并计算直接时期变化；较低组作者基准ΔR的首、末变化分别为{interval(period[(period.outcome=='R_difference_change')&(period.benchmark=='author')&(period.role=='first')&(period.group=='lower')].iloc[0],'estimate')}及{interval(period[(period.outcome=='R_difference_change')&(period.benchmark=='author')&(period.role=='last')&(period.group=='lower')].iloc[0],'estimate')}。没有以一期跨零、另一期不跨零推断时期变化，也不凭发表日期划分推断模型发布的因果作用。

[全部ED/S图与逐面板信息](panel_guide_zh_en.md) · [方法](methods_zh.md) · [补表入口](../source_data/README_zh.md)

## 证据边界

全部范围是预先固定支持/权重/目标下的条件描述，不校准跨论文作者或机构依赖、检索漏失和标签误差。未进行多重比较后的全体格显著性筛选。共同首末贡献、完整联盟名单及字母排序缺可靠信息，状态为unavailable。参照为screen-negative背景，不是逐篇认证不使用AF或AI。观察署名位置与实际领导、贡献和公平保持区分。
''')
    write('manuscript/results_en.md',f'''# Finding 4: Authorship representation depends on the participation benchmark

Following an explicit user-approved eligibility correction, six reference studies with an identical first and last author were removed. The strict author-country-complete cohort contained 5,087 AF and 438,473 reference studies. Common support comprised 173 year–document-type–primary-subfield cells, retaining 5,087 AF and 332,760 reference studies. Reference weights summed to 5,087 and had ESS 193,059.65. Historical estimates and ranges remain separately archived.

In this identical cohort, lower-baseline-output countries received {100*rr('AF','country','first').participation_credit/5087:.3f}% of AF country participation credit but {100*rr('AF','author','first').participation_credit/5087:.3f}% of author participation credit. Their First and Last credit shares were {100*rr('AF','country','first').role_credit/5087:.3f}% and {100*rr('AF','country','last').role_credit/5087:.3f}%. With country participation as denominator, AF–reference differences in R were {interval(dd('country','first'))} for First and {interval(dd('country','last'))} for Last (Fig. 4a,b). With author participation, differences were {interval(dd('author','first'))} and {interval(dd('author','last'))}, respectively (Fig. 4c,d). Brackets denote 95% conditional whole-study bootstrap ranges, not network-robust population intervals.

The directly paired change between benchmarks, C=ΔR_author−ΔR_country, was {interval(f,'C')} for First and {interval(l,'C')} for Last. The corresponding changes in absolute differences, B, were {f.B:.3f} [{f.B_ci_low:.3f}, {f.B_ci_high:.3f}] and {l.B:.3f} [{l.B_ci_low:.3f}, {l.B_ci_high:.3f}]. The Last B range included zero. These comparisons show benchmark dependence; they do not establish equal contributions, equivalence, fairness, or a causal explanation by author scale.

In the same studies, AF first–last pairing credit was {100*ss('AF',cats[0]).share:.2f}% same-country/same-institution, {100*ss('AF',cats[1]).share:.2f}% same-country/different-institutions, {100*ss('AF',cats[2]).share:.2f}% same-country/institution-unresolved, and {100*ss('AF',cats[3]).share:.2f}% cross-country. Reference shares were {100*ss('reference',cats[0]).share:.2f}%, {100*ss('reference',cats[1]).share:.2f}%, {100*ss('reference',cats[2]).share:.2f}%, and {100*ss('reference',cats[3]).share:.2f}% (Fig. 5a). Institutional missingness did not change the cohort; fractional credits retain actual country–institution links.

Higher→higher country-group pairing accounted for {100*hh.observed_share:.2f}% of AF pairing credit (Fig. 5b). The exact within-team distinct-author expectation was {100*hh.expected_share:.2f}%; observed minus expected was {hh.observed_minus_expected_pp:+.2f} percentage points [{hh.deviation_ci_low:.2f}, {hh.deviation_ci_high:.2f}]. Reference excess was {hhr.observed_minus_expected_pp:+.2f} points. The direct AF–reference excess difference was {interval(hhd,'observed_minus_expected_pp')} points (Fig. 5c). This particular comparison did not establish a clearly directed AF-specific excess; other pairs are reported in full, rather than inferred from this cell. Within-group pairing is not necessarily within-country. The reference retains team composition but not observed role margins, seniority, responsibilities or contributions.

Domestic institution R distributions and same-institution differences are reported separately (ED3, S1, T4). Prespecified US/CN/GB examples all belong to the higher national group; the GB lower institution group contains only five AF-active institutions. An additional conditional endpoint-opportunity cohort contained 5,425 AF and 477,291 reference studies with consistent observed author IDs and distinct role authors. For First, 3,213 of 5,719 role-defined AF country–institution units had zero observed credit, versus an analytic expected zero count of 3,157.18. The endpoint reference is not a model of exclusion or contribution. Its ranges and all Last/reference results remain separate from bootstrap intervals (T7).

Support thresholds, strict internationality, institution completeness, unique-country endpoint pools and period comparisons were executed. AF2 and AF3 shared a pooled AF field/type target and were compared directly, with support/retention/ESS gates recorded. Uncertain or unavailable evidence was not recoded as zero. Shared authors/institutions across studies and retrieval/label errors remain uncalibrated; none of these descriptive comparisons establishes causal effects or actual leadership.

[Methods](methods_en.md) · [Figure captions](captions_zh_en.md) · [Source Data](../source_data/README_zh.md)
''')
    methods_zh='''# Finding 4 / Figure 5 方法说明（执行版）

## 研究单位、语料和版本链

2020–2025年article/review/preprint，沿用获准study_id与一致代表work的作者记录；未跨预印本/正式版拼接作者。AF使用标签和screen-negative参照沿用冻结证据层，本轮不下载、调用LLM或重标注。二元比较池16,414项AF与2,686,183项参照；观察国际分别6,118与541,052。国际是至少两个观察有效国家，另有严格跨作者国际敏感性。

冻结旧作者完整样本为AF 5,087、参照438,479。逐篇ID核对发现6项参照的首末作者ID相同。用户2026-10-30明确确认Figure 4也应排除并保留旧对照，故新主分析为5,087/438,473；共同支持5,087/332,760、173单元。旧参照支持332,764，不与新样本数混称。10个缓存角色国家信用差异全属于这6项；其余严格样本信用复现。

## 观察完整性与归属

逐研究核对显式唯一首末位置、不同首末作者ID、作者存在于同一代表版本名单、观察ID数量一致，以及所有观察作者均有可判定国家。直接作者国家优先，缺少时回退该作者机构国家；来源保留。国家信用按去重国家等分，作者基准再按观察作者等分；每研究总信用为1。名单“观察完整”不认证全文联盟名单未截断。字面NA为Namibia，未知国家不补成NA国家。机构只保留已观察国家—机构关系，不作无依据笛卡尔积。

## 冻结基线组与估计量

国家组继承2015–2019整数发表规模、type-7切点、并列归低、基线≥20机构等既定资格；68国分为higher/middle/lower=23/22/23。它们不是收入组或R&D能力组。其他国家保持outside，全部全球信用分母仍包含outside。

每篇国家产出信用为参与国家等分；作者产出信用为每名观察作者等分一篇再等分其国家。先汇总参与与角色信用，再计算R=(角色信用/全球角色信用)/(参与信用/全球参与信用)，不平均国家R。First/Last使用相同真实角色分子。R=1表示相对于该基准比例相称，不表示公平。ΔR=R_AF−R_reference；C=ΔR_author−ΔR_country；B=|ΔR_country|−|ΔR_author|。四者无量纲，不能标百分比/百分点。

主支持为年份×文献类型×主要子领域中AF≥1、reference≥5。目标固定为支持内AF构成，AF权重1，reference权重n_AF/n_reference。保存raw_full、common_raw和standardized；原始研究数、权重和、信用和与ESS=(Σw)^2/Σw²分别列明。Fig4/5相同有序研究ID和权重已比对；机构unknown不改变主配对样本。

## 国家及机构联合配对

逐研究构建J_cd=u_First,c×u_Last,d，总信用1，先实际国家对再汇总H/M/L/outside，不能从角色边际反推。国家组对角不等于同国。首末方向只编码两个位置，无知识流、指导或权力方向含义。

为Fig5a，将每个角色国家信用等分到该作者在该国有效去重机构ID；没有对齐机构则放institution_unknown。联合信用z_r,c,i在每国机构上的和严格等于原国家信用。跨国c≠d优先归不同国家；同国中有效相同ID为同机构，不同有效ID为不同机构，至少一方unknown为关系未决。两个unknown不算同机构。4类互斥且合计1；前三类合计实际国家配对矩阵对角和，不是组矩阵对角和。预先保留全部4类，不依据配对方向或显著性调整图形。

## 团队构成参照与直接比较

每篇A≥2，作者a的国家组分数信用为f_a,g。有序、不放回的两名不同作者端点精确期望：

T_gh = [(Σ_a f_a,g)(Σ_a f_a,h) − Σ_a f_a,g f_a,h] / [A(A−1)]。

对角也扣同一作者项，不能用q_gq_h。主热图B_k,gh=100(O_k,gh−E_k,gh)，单位百分点；两语料共同零中心色标。完整16格、稀疏/零格和outside保留。直接AF−参照差及(B_gh−B_hg)的正反方向直接比较进入T6，不比较单格区间跨零与否来推断组间/时期差。未保持观察首末角色边际，不称“控制边际后的特殊合作偏好”。完整227×227国家网格的观察份额、精确期望、O−E及直接语料差均补做2,000次联合整研究bootstrap（seed 20351119），原始与标准化分别报告。逐篇同一抽样次数联合用于O/E，再直接比较语料；无观察支持的结构零和退化范围单列，不画伪精确CI。组层全16格同样具有条件范围。

## 三种不同的不确定性

观察份额、R、ΔR、C/B、O−E、结构及直接语料差使用语料×年×类型×子领域内2,000次整研究bootstrap。支持、权重和目标固定；同一研究国家/作者/首末/配对/机构结构共用一次抽样次数，每轮重新归一。可对完全相同联合向量在层内精确二进制压缩，多项抽样恢复整研究抽样，不舍入向量、不拆开国家行或两基准。主seed=20261029，各分析独立派生种子见完成记录。至少95%轮有定义才提供2.5–97.5%条件范围，退化和无定义单列；不以点估计±独立边际标准误代替直接范围。

另运行2,000次同团队有序不同作者端点模拟，保留作者隶属和原研究权重，用于团队构成条件参照范围与机构零事件计数范围。固定随机种子20265033，原生C++ mt19937_64，未调用外部服务。该模拟范围不是观察估计的bootstrap CI。机构中位数/IQR只描述单位分布，也不是CI。未作多重格显著性筛选；所有条件区间不校准跨论文作者/机构依赖、分类或检索误差。

## 国内机构R与有限机会

国内机构R仍按每国机构的参与/角色总信用归一。既有角色分配为先等分机构ID、再分该机构的实际国家关系，与Fig5a“国家优先”联合信用定义不同，不能互相替代。同一显式首末ID记录从国内分布中也剔除；旧结果仍归档。活跃分布保留真实R=0；零产出或国家角色总量0时R未定义。固定基线零产出机构、未知/新机构另列；后者不自动归低组。

同机构差先在AF/参照共同可定义机构逐家相减，再求中位数/IQR。US/CN/GB在读取署名结果前按覆盖预选，均为高国家组；英国低机构组AF活跃仅5家。全国家、两角色、门槛1/2/5/10、1/2–4/5–9/10+机会箱全部交付，不从示例推广全球。

N05机构机会参照另限于ID一致、显式不同首末作者且机构角色可用的研究（AF5,425、参照477,291），不是主国家完整样本，也不替换全部国内机构分布。对国家—机构单位i、参与研究p，pi_ip=拥有任一已观察有效机构i隶属的作者人数/A_p；P0_i=∏_p(1−pi_ip)，用稳定log1p计算。pi是任意正信用事件概率；期望分数角色信用q另按ID优先分配求和，不能用q代替pi。模拟同一研究两端点不同作者，对实际国家—机构单位记录是否命中过；国家角色分母无定义者另列。每家analytic P0和模拟均值、分组零数范围都保存。此参照假定研究间端点选择独立，不是资历、贡献、排斥或合作机制模型。

## 预设敏感性与时期

运行参照最低支持1/5/10/20、严格跨作者国际、角色机构关系完整、唯一角色国家。唯一角色国家的条件期望只从同一研究恰有一个国家的作者候选池选两名不同作者，候选池至少2；观察与参照资格一致。另运行唯一国家且唯一机构的结构子样本，重建对称支持/目标；它的结构与覆盖另报，其通用expected列不作为唯一国家候选池参照。

AF2为2021-07-01–2024-04-30，AF3为2024-05-01–2025-12-31。两期共享领域×类型的合并AF目标，在两期均有支持的单元估计；每期内部仍按语料×年×类型×子领域bootstrap。直接AF3−AF2差由不重叠时期抽样差计算。展示组别需各期AF≥20、保留≥80%、ESS≥20，不足写NA及原因。配对全部16格时期直接变化也保存，但不据单期显著性称反复、稳定或改善；版本时期不是随机处理。

## 可复现与限制

包内含冻结输入、规范化逐篇Parquet、派生矩阵、逐轮联合池、全部CSV/Parquet、代码、运行环境、种子和哈希。大矩阵另有CSV gzip；标准分析可从这些本地规范化快照复核，无需外置JSONL/API。原始72分片的外部路径/哈希是来源记录，不是移动后的运行依赖；从最上游重建仍需原项目文件。旧交接目录按原字节归档，其说明中的旧状态不覆盖本执行说明。

共同首末贡献、联盟完整成员和字母排序无可靠字段，登记unavailable，不称“已排除”或“稳健性通过”。原始作者名单截断、漏检和采用标签误差未另校准。此分析没有测量实际领导、资金、算力、资历或公平；未拟合相应机制模型。
'''
    write('manuscript/methods_zh.md',methods_zh)
    write('manuscript/methods_en.md','''# Methods: Finding 4 and first–last authorship pairings

## Cohort and provenance

We used frozen representative study units from 2020–2025 (articles, reviews and preprints), preserving approved AF adoption labels and study-version links. Authorship records came from a single coherent representative work. The comparison pool comprised 16,414 AF and 2,686,183 screen-negative background studies; screen-negative does not certify non-use of AF or AI. Observed internationally coauthored studies contained at least two valid observed countries (6,118 AF; 541,052 reference). A stricter across-author definition was examined separately.

The legacy author-country-complete sample contained 5,087 AF and 438,479 reference studies. Six reference records had the same explicit first and last author. On 30 October 2026 the user approved their exclusion from both new Figure 4 and Figure 5, retaining all historical results as a comparison. The strict full cohort therefore contained 5,087/438,473 studies; common support retained 5,087/332,760 in 173 cells. Ten legacy role-country credit discrepancies were confined to the six removed records.

We required explicit unique, distinct first/last author IDs, both present in the representative author list, consistent observed author-ID counts and a determinable country for every observed author. Direct authorship countries had priority; author-specific institution-country fallback was retained with provenance. Countries were deduplicated and equally allocated within author. Observed completeness does not certify that consortium or collective-author rosters were untruncated. Namibia's literal code NA was retained. Affiliation-country links were observed, never manufactured by Cartesian matching.

## Baseline groups, weights and representation

Frozen national groups used 2015–2019 integer publication participation, type-7 cut points, lower-side boundary ties and established eligibility, yielding 68 countries (23 higher, 22 middle, 23 lower). Remaining countries were outside the fixed groups and retained in all global denominators. Groups do not measure income, R&D resources or contributions.

Country participation divided each study equally among participating countries. Author participation first divided one study equally among observed authors and then among each author's countries. R was pooled role-credit share divided by pooled participation-credit share; country R values were never averaged to construct group R. Role numerators were identical under both benchmarks. R, ΔR=R_AF−R_reference, C=ΔR_author−ΔR_country, and B=|ΔR_country|−|ΔR_author| are dimensionless. R=1 denotes proportional representation under the chosen benchmark, not fairness.

Common support was year × document type × primary subfield, requiring at least one AF and five reference studies. The target was the supported AF composition: AF weight 1 and reference weight n_AF/n_reference. Full raw, common raw and standardized estimates were retained. Study counts, credit sums, weight sums and ESS=(Σw)²/Σw² were separate fields. Figure 4 and all Figure 5 panels used the same study IDs, weights and target; institutional missingness did not alter this cohort.

## Joint role pairing and institutional correspondence

For study p, actual country pairing credit was J_cd=u_First,c u_Last,d, summing to one. Actual country pairs were aggregated to all 16 higher/middle/lower/outside combinations. A within-group pairing need not be within-country. First-to-last order encodes recorded position, not knowledge flow, supervision or authority.

For Figure 5a, each role's country credit was equally divided among its valid deduplicated institutions actually aligned to that country. Unaligned residual country credit was assigned to institution_unknown. The resulting joint credit z_r,c,i preserved every role-country margin. Pairs were classified, in order, as different countries; same country/same known institution; same country/different known institutions; or same country/institutional relationship unresolved. Two unknown institutions were not treated as equal. The three same-country categories summed to the country-pair diagonal, not the country-group diagonal. All four categories were retained before examining directions.

## Team-composition expectation and contrasts

For A observed authors and author group-credit vector f_a,g, the exact expectation from two uniformly sampled distinct ordered authors was T_gh=[(Σ_a f_a,g)(Σ_a f_a,h)−Σ_a f_a,g f_a,h]/[A(A−1)]. The same-author term was removed even on diagonal cells. Independent with-replacement q_g q_h was not substituted. The primary deviation was 100(O−E), in percentage points, with a shared zero-centered color scale across corpora. All cells, including sparse/zero cells and outside groups, were retained. Direct AF–reference deviations and reversed-direction contrasts were estimated jointly. Observed role margins, seniority and contributions were not fixed by this reference. The complete 227×227 country grid additionally has 2,000 joint whole-study bootstrap replicates (seed 20351119) for observed shares, exact expectations, deviations and direct corpus-deviation differences, for raw and standardized settings. Each country-pair O/E draw shares study multiplicities; structural zero and degenerate ranges are explicit rather than printed as falsely precise intervals. All group cells also have conditional ranges.

## Conditional uncertainty

We ran 2,000 whole-study bootstrap replicates stratified by corpus × year × document type × primary subfield, fixing observed support, weights and targets. Within a replicate, each study's country/author participation, both roles, pairings and institutional structure received the same multiplicity and were renormalized. Binary-identical full feature vectors could be compressed within strata and sampled multinomially without rounding or independently resampling countries/benchmarks. Main seed 20261029 generated analysis-specific streams recorded in completion reports. Percentile 2.5–97.5 ranges required at least 95% defined replicates; degeneracy and undefined outcomes were explicit. Direct C/B and corpus/period contrasts were computed from joint draws, not from marginal interval endpoints.

Separately, 2,000 conditional endpoint draws selected two distinct authors within each observed team, retaining their affiliations and study weights. Seed 20265033 and C++ mt19937_64 were recorded. These conditional reference ranges are not bootstrap confidence intervals. Institution medians/IQRs describe units, not estimate uncertainty. No cell was selected by statistical significance. Shared authors/institutions across papers and retrieval/label error were not calibrated, so conditional ranges are not claimed as network-robust population inference.

## Domestic institutions and zero-event opportunity

Domestic institutional R normalized participation and role credit within each country and corpus. Its inherited role allocation divided credit by institution ID and then by that institution's actual country links; this differs from the country-first pairing definition. Explicit identical first/last IDs were removed from the updated domestic estimates as well. Positive output with zero role credit retained R=0; zero output or zero national role denominator was undefined. New/unknown institutions were not assigned to the lower baseline group. Paired institution differences were computed within the same institution before summarizing. US/CN/GB examples were selected by baseline/output coverage, not role results; all three are higher national-group countries and the GB lower institutional group has only five AF-active institutions. All countries, roles, thresholds 1/2/5/10 and opportunity bins 1/2–4/5–9/10+ were supplied.

The additional endpoint-opportunity cohort required consistent observed author IDs and distinct explicit role authors among institution-usable studies (5,425 AF; 477,291 reference). It did not replace the full domestic denominator. For a country–institution unit i in a participating study p, pi_ip was the number of observed authors with any valid i affiliation divided by A_p; P0_i=∏_p(1−pi_ip) was calculated using stable log1p. Expected fractional role credit q was computed separately under the inherited institutional allocation and was not substituted for pi. Simulated zero-event counts retained within-study distinct-role sampling and multi-affiliations; role-undefined national denominators were separate. Individual analytic probabilities, Monte Carlo diagnostics, counts and aggregate reference ranges were saved. The reference assumes independent endpoint selection between papers and is not a contribution, seniority or exclusion model.

## Sensitivities and periods

Executed variants changed minimum reference support to 1/5/10/20, required strict across-author internationality, required aligned role institutions, or restricted observed role authors to unique countries. For the unique-country endpoint sensitivity, both sampled endpoints came only from that study's observed unique-country-author pool, requiring at least two eligible authors; its exact expectation was recomputed accordingly. A separate unique-country-plus-unique-institution structure cohort used symmetric support/weights and reported coverage; its general expectation columns were not interpreted as the unique-country-pool reference.

AF2 was 1 July 2021–30 April 2024 and AF3 was 1 May 2024–31 December 2025. Both periods shared a pooled AF field/type target over cells supported in both periods. Period-specific bootstrap still stratified by corpus/year/type/subfield. Direct AF3−AF2 contrasts used disjoint period draws. Display support required AF n≥20, retention≥80% and ESS≥20 in each group-period; unsupported results were labeled. All 16 pairing-period direct contrasts were retained, without inferring period changes from separate zero-crossing decisions or claiming release-date causality.

## Reproducibility and unavailable evidence

The bundle supplies frozen normalized long tables, caches, exact matrices, joint replicate pools, CSV/Parquet outputs, code, versions, seeds and hashes. Large country grids also have compressed CSV exports. Analysis can be verified from packaged normalized snapshots without external JSONL or APIs. External raw-shard paths/hashes document upstream provenance; rebuilding from those raw shards still requires the original project. Original handoff documentation is byte-preserved historical material rather than the current execution status.

Reliable shared-first/shared-last contribution, complete consortium membership and alphabetical-order fields were unavailable. These checks were not claimed as exclusions or successful sensitivities. No actual leadership, fairness, resource or causal mechanism was measured.

[Chinese detailed methods](methods_zh.md) · [Execution and requirement map](requirements_comparison_zh.md)
''')
    # Seven logical groups retain typed detailed tables and companion sheets.
    groups={
      'F4_T1':('样本流程、覆盖与领域',['strict_annual_flow','strict_group_annual_retention','strict_exclusive_final_flow'],['sample_flow_exclusive.csv','sample_missingness_overlapping.csv','Table_S1_collected_subfields.csv']),
      'F4_T2':('国家组两基准、直接差及C/B',['strict_main_R','strict_main_delta','strict_main_benchmark_change'],[]),
      'F4_T3':('全部注册国家及无定义诊断',['strict_main_R','strict_main_delta','strict_main_benchmark_change'],['country_registry.csv','country_display_dictionary.csv','country_support_coverage.csv']),
      'F4_T4':('国内机构分布、配对、门槛及固定基线零产出',['strict_domestic_institution_R','strict_domestic_institution_paired','strict_institution_distribution','strict_institution_paired_summary','strict_institution_fixed_baseline','institution_zero_entities'],[]),
      'F4_T5':('敏感性、时期、支持与执行状态',['sensitivity_coverage_and_status','period_shared_target','period_AF2_R','period_AF3_R','period_AF2_delta','period_AF3_delta','period_direct_changes','unique_institution_coverage'],['Table_S5_R.csv','Table_S5_estimates.csv','Table_S5_samples.csv','Table_S5_support.csv','Table_S5_execution_status.csv']),
      'F4_T6':('完整国家与国家组配对、期望及不确定性',['strict_main_pairings','strict_main_direction_contrasts','conditional_pair_reference','unique_role_country_candidate_pool_pairings','period_AF2_pairings','period_AF3_pairings'],[]),
      'F4_T7':('机构结构、实际零与条件期望',['strict_main_structure','strict_main_same_country','unique_role_country_institution_structure','unique_institution_coverage','domestic_institution_group_pairings','institution_zero_reference','institution_zero_entities'],[])}
    registry=[]
    for ID,(title,names,legacy) in groups.items():
      lines=[f'# {ID} — {title}','', '一张逻辑补表包含以下伴随表；CSV为阅读格式，Parquet保留字段类型。国家字面NA不可当空值。', '', '|伴随表|CSV|Parquet|','|---|---|---|']
      for n in names:lines.append(f'|{n}|[CSV](../tables/{n}.csv)|[Parquet](../tables/{n}.parquet)|');registry.append(dict(table_group=ID,sheet=n,path='tables/'+n+'.parquet',status='executed'))
      if legacy:
        lines+=['','以下为逐字节保留的历史伴随表，样本/资格与新主分析可能不同；原时期/角色特定口径不冒称已统一严格样本。','']
        for n in legacy:lines.append(f'- [历史 {n}](../inputs/handoff/06_data/existing/{n})')
      if ID=='F4_T6':lines+=['','[完整227×227国家网格CSV gzip](../tables/full_country_pair_matrices.csv.gz) · [Parquet](../tables/full_country_pair_matrices.parquet)。国家及组层bootstrap均已计算；结构零/退化明确标记，端点参照范围另表。']
      if ID=='F4_T5':lines+=['','[执行状态与不可用字段](execution_status.json)。共同贡献、联盟完整性、字母排序均为unavailable；不是通过检查。']
      if ID=='F4_T7':lines+=['','P0用任意正隶属概率pi；expected_fractional_role_credit是另一个q。观察计数与条件模拟范围不可解释为贡献/排斥模型。']
      write('source_data/'+ID+'.md','\n'.join(lines))
    pd.DataFrame(registry).to_csv(ROOT/'source_data/table_registry.csv',index=False)
    status=dict(status='EXECUTED_WITH_EXPLICIT_LIMITATIONS',date='2026-10-30',N01='reconstructed; six legacy same-author studies excluded with explicit approval',N02='2000 joint-study bootstrap',N03='actual country/institution linked pairs',N04='exact distinct-author expectation and separate 2000 conditional endpoint simulations',N05='analytic pi-based P0 and 2000 joint endpoint simulations',N06='executed thresholds, strictness, unique pool and shared-target period contrasts',unavailable={'shared_first_last_contribution':'no reliable field','complete_consortium_roster':'no reliable field','alphabetical_order':'no reliable field'},not_estimated={'network_dependence_robust_inference':'conditional whole-study intervals only','institution_author_fractional_alternative_R':'not part of required domestic main; q diagnostic provided'},API_calls=0,LLM_calls=0)
    dump(ROOT/'source_data/execution_status.json',status)
    write('source_data/README_zh.md','''# Source Data总入口

研究数、信用、权重和、ESS分别记录。R/ΔR/C/B无量纲，配对偏离用百分点；NaN表示无定义或未估计，不填成零。Namibia的国家代码是字面NA。

'''+ '\n'.join(f'- [{ID}：{g[0]}]({ID}.md)' for ID,g in groups.items())+'''

## 逐篇关系数据和重现

- [研究资格及互斥排除原因](study_eligibility.parquet)
- [实际研究权重与支持](study_weights.csv)
- [角色国家信用](role_country_credit.parquet)
- [规范化studies](studies.csv) · [roles](roles.csv) · [country_groups](country_groups.csv)
- [作者国家长表](../inputs/normalized/authors_countries.parquet) · [作者机构长表](../inputs/normalized/authors_institutions.parquet)
- [角色国家—机构联合信用](../inputs/normalized/role_country_institution_credit.parquet)
- [实际国家配对信用](../inputs/normalized/country_pair_credit.parquet) · [精确国家配对期望](../inputs/normalized/country_pair_expected.parquet)
- [同研究联合特征矩阵](../inputs/normalized/feature_matrix.npz) · [列与偏移定义](../inputs/normalized/feature_metadata.json)
- [抽样池与逐轮结果目录](../draws/) · [环境版本](../provenance/runtime.json)

Parquet是实际长表，不是缺失CSV的空模板。大国家网格另给压缩CSV以控制包大小。原始上游路径是来源记录；规范化快照已随包提供，复核不需要外置JSONL或API。
''')
    captions='''# 图注 / Captions

## Figure 4 / F4_MAIN

**中文。** 不同参与基准下的署名代表性。a、b为国家参与基准，c、d为作者参与基准；左列First、右列Last，国家组在2015–2019冻结。AF实心、参照空心；竖线R=1。全部四面板使用相同严格样本、角色分子、173个支持单元和权重：AF5,087，参照332,760，参照ESS193,059.65；组外信用仍在全球分母。横线为2,000次整研究分层bootstrap的95%条件范围，未校准跨研究共享作者/机构依赖。R无量纲，首末位置不认证贡献或实际领导。

**English.** Authorship representation under country and author participation benchmarks. a,b, country participation; c,d, author participation. Columns show First and Last positions, respectively. National baseline groups were fixed using 2015–2019 output. Filled symbols denote AF and open symbols reference; the vertical line denotes R=1. All panels share the strict cohort, role numerators, 173 support cells and weights (AF n=5,087; reference n=332,760; reference ESS=193,059.65), retaining outside-group credit in global denominators. Segments are 95% conditional ranges from 2,000 stratified whole-study bootstrap replicates. Shared-author/institution dependence is not calibrated. R is dimensionless; recorded positions do not certify actual contributions or leadership.

## Figure 5 / F4_PAIRING（暂定全稿编号）

**中文。** 国际研究的首末位联合配对。a为同国同机构、同国不同机构、同国内机构关系未决及跨国的分数配对信用；机构未决约AF0.10%、参照0.07%，灰色细段完整保留。b为全部higher/middle/lower/outside组间配对，左右分别First/Last，每个语料总信用100%，线无因果箭头；宽度不是整数论文数。c为观察份额减去同团队均匀抽取两名不同作者的精确构成期望，单位百分点，两语料共用零中心色标。全部三面板与Figure4相同研究和权重。组内配对不必同国。直接语料差及条件范围在T6；模拟参照范围与bootstrap分开。参照未保持观察角色边际，也未控制资历、贡献、职责或公平。

**English.** First–last authorship pairings in international research. a, Fractional pairing credit classified by geographic and institutional correspondence; same-country unresolved institutional credit is retained in gray (AF approximately 0.10%; reference 0.07%). b, Complete fixed-baseline country-group pairings, First on the left and Last on the right, with outside groups retained. Each corpus sums to 100%; ribbons encode fractional credit rather than integer study counts or causal flow. c, Observed minus exact expected shares under uniform ordered selection of two different observed team authors, in percentage points, with a shared zero-centered scale. All three panels use the same study IDs and weights as Figure 4. Within-group need not mean within-country. Direct corpus contrasts, conditional whole-study ranges and separate endpoint-reference ranges are supplied in T6. This reference does not preserve observed role margins or measure seniority, contributions, fairness or decision-making authority.

## Extended Data

**F4_ED1。** a年度国际合作率，分母国家已知研究，2020 AF仅9项。b团队观察作者数中位数/IQR，总体与国际分别展示。c总研究→国际→角色合格→严格作者完整的嵌套数量（log轴，不能相加）。d按国家组的AF年度作者完整保留率，全部语料/角色保留率在T1。

**F4_ED1 (English).** Annual international collaboration among country-known studies (a; 2020 AF denominator nine), observed team-author medians/IQRs for country-known and international scopes (b), nested study flow on a logarithmic scale (c), and AF group/year complete-author retention (d). IQR is not a confidence interval. Complete corpus/role retention data are in T1.

**F4_ED2。** 全部227注册国家按冻结基线顺序分页：a国家基准ΔR；b作者基准ΔR；c配对基准变化C；d参与ESS。首位圆、末位三角；a–c条件范围；空白保留无定义原因，不按效应选国。组外/零AF国家仍列出。d蓝AF、红参照。

**F4_ED2 (English).** All 227 registry countries in fixed baseline order across pages: country-benchmark ΔR (a), author-benchmark ΔR (b), paired benchmark change C (c), and participation ESS (d). Circles denote First and triangles Last; ranges in a–c are conditional. Blank estimates are undefined, not zero. Countries with no AF output and countries outside the fixed groups remain registered. Panel d uses blue for AF and red for reference.

**F4_ED3。** 预选US/CN/GB国内机构a活跃分布中位数/IQR、b同机构先相减的差分布；First摘要在图中，两角色全结果见S1/T4。c按1/2–4/5–9/10+机会箱的零First比例与n，d实际零First与条件端点参照范围。N05机会参照有额外ID资格，不替换完整机构分母；英国低组AF仅5家，三个国家均为高国家组。IQR和模拟范围均不是依赖稳健CI。

**F4_ED3 (English).** Prespecified US/CN/GB domestic institution distributions (a, median/IQR), same-institution differences before summarizing (b), observed zero First credit by study-count opportunity bin with n (c), and observed zero First credit versus a conditional endpoint reference (d). Both roles and all countries are available in S1/T4. The opportunity cohort has additional ID requirements. The GB lower group has five AF-active institutions; all three national examples belong to the higher group. IQRs and endpoint ranges are not dependence-robust estimate intervals.

**F4_ED4。** a主样本机构结构；b唯一角色国家+机构子样本对称标准化结构，c主样本角色国家组构成（覆盖数见T7），d在US/CN/GB已知同国内机构配对中条件化的国内H/M/L/未分组矩阵。国内分组不表示跨国绝对资源，d分母另立，不能与全体配对比例混称。a/b颜色与Figure5a一致。

**F4_ED4 (English).** Main-cohort structure (a), symmetric restandardization of the unique-role-country/institution subset (b), main-cohort role-country composition with subset coverage in T7 (c), and domestic institutional baseline-group pairing conditional on known same-country pairs in US/CN/GB (d). Domestic groups are relative within-country categories, not cross-national absolute resources. The panel-d denominator is separate from all-study pairing shares. Structure colors match Figure 5a.

## Supplementary Figure groups

**F4_S1 / Domestic institution distributions.** 全部冻结基线国家分页，显示国内R中位数/IQR、共同机构ΔR中位数/IQR、两角色零信用与机会箱、最低参与门槛1/2/5/10。Blue AF/red Reference; circles/solid First, triangles/dashed Last. Empty values are undefined. Each institution pair is differenced before its summary; thresholds change observed opportunities, not contributions.

**F4_S2 / Counting and standardization.** AF国家/作者基准R，raw_full/common_raw/standardized及outside。Historical whole-country/full-role variants in T5 retain different qualification/targets and are not mislabeled strict same-sample adjustments.

**F4_S3 / Eligibility and support sensitivities.** 低组作者基准首末ΔR条件范围，完整主/严格国际/机构完整/唯一国家候选池/支持1/10/20对照；各自重建支持。Unknown contribution metadata remain unavailable. These are not independent replications.

**F4_S4 / Period contrasts.** AF3−AF2对AF−reference ΔR的直接变化，两基准分色、角色分列；未满足各期n/保留率/ESS者不作稳定展示。Both periods share a pooled AF field/type target. Pair-cell direct period contrasts and all gates are in T5/T6.

**F4_S5 / Pairing diagnostics.** 完整组层观察份额、精确团队期望与O−E，raw及标准化、唯一国家池、全国家网格及分开的模拟范围在T6。The exact expectation subtracts the same-author term; full country-cell conditional bootstrap intervals are supplied, with structural zeros and degeneracy explicit.

**F4_S6 / Distinct conditional estimands.** a为两基准共享研究抽样得到的C条件范围，b为实际机构零First比例与pi推导的条件均值，按机会箱比较。Bootstrap intervals and endpoint reference distributions are separate estimands; neither addresses actual contributions or cross-study network dependence.
'''
    write('manuscript/captions_zh_en.md',captions)
    notes=[
      ('S1','研究范围、六项修正及观察完整性','Scope, six-record correction and observability', '二元比较池16,414/2,686,183不等于主分析样本。国际6,118/541,052，旧角色共同5,558/489,814，严格作者完整5,087/438,473。新共同支持5,087/332,760。6项同作者首末修正已经用户确认；旧版完整保留。观察完整不保证联盟名单完整。','The binary comparison pool, international cohort, role-complete cohort and strict author-complete common support are distinct denominators. Six identical-endpoint reference records were removed with explicit approval; historical results remain archived. Observed author completeness does not certify an untruncated consortium list.'),
      ('S2','两个参与基准与配对C/B','Two participation benchmarks and paired C/B',f'低组首/末C为{interval(f,"C")}和{interval(l,"C")}，无量纲。B分别{f.B:.3f}、{l.B:.3f}，末位B范围含零。不能靠各自CI跨零推断两基准差，不能把C称解释比例或公平证明。','Both benchmarks share the same role numerators and study multiplicities. Direct C and absolute-change B answer different questions; a positive C does not universally imply reduced absolute difference. Neither is a causal explained fraction or evidence of fairness.'),
      ('S3','国内机构R、零与机会','Domestic institutional R, zeros and opportunities','国内R每国归一；零产出与零角色不同。中位数/IQR描述单位分布，不是CI；共同机构先相减。N05另要求ID一致，pi与q不同，P0用pi。AF机会样本5,425、参照477,291，不能代替全部机构样本。','Domestic R is country-normalized. Zero output is undefined whereas positive output with zero role credit can give R=0. IQR describes institutions. The endpoint reference uses event probability pi rather than fractional credit q and has its own additional-ID-restricted cohort.'),
      ('S4','真实配对、机构未知与团队条件参照','Actual pairing, institutional unknowns and team reference','Fig5全部面板相同IDs/权重。4类互斥信用合计1；同国不是同组。不同作者精确期望扣同一作者项。保留16格，反向与AF−参照直接差另算。高→高直接超额差0.163pp的范围跨零不表示所有格均相同。','Actual country pairs precede group aggregation. The country-first institution allocation preserves margins and unresolved credit. Exact expectations sample different observed authors; they do not fix observed role margins. The absence of a clearly directed higher→higher corpus contrast is not a null claim about all cells.'),
      ('S5','时期共同目标和直接变化','Shared period target and direct change','AF2/AF3共享合并AF领域×类型目标，直接时期变化用不重叠时期draws相减。各组n≥20、保留率≥80%、ESS≥20，未满足不作稳定展示。发表时期不能解释模型发布因果效应。','Disjoint publication periods share a pooled AF field/type target. Direct period changes, not separate zero-crossing decisions, are evaluated. Group support/retention/ESS gates are explicit; unsupported values do not justify recurrent-pattern claims or release-date causality.'),
      ('S6','三种范围及未测量问题','Three kinds of ranges and unmeasured evidence','2,000整研究bootstrap、2,000条件端点模拟、机构IQR分别对应估计条件范围、假定端点参照和分布离散度。均未校准网络依赖/标签/漏检。共同贡献、联盟完整性和字母排序unavailable。完整国家网格及组层条件区间均交付；结构零/退化范围与有信息区间区分。','Conditional whole-study bootstrap ranges, conditional endpoint simulation ranges and institutional IQRs are not interchangeable. Cross-study dependence, label error and retrieval error remain uncalibrated. Shared contribution, complete consortium membership and alphabetical ordering are unavailable; country-cell and country-group conditional intervals are supplied with structural-zero and degeneracy flags.')]
    write('manuscript/supplementary_notes_zh_en.md','# Supplementary Notes（执行版）\n\n'+'\n\n'.join(f'## Note {ID} {zh} / {en}\n\n{body}\n\n{eng}' for ID,zh,en,body,eng in notes))
    panels=[('Figure4','a','国家基准、First','First roles relative to country participation','strict_main_R','相同样本分子分母；不是实际贡献'),('Figure4','b','国家基准、Last','Last roles relative to country participation','strict_main_R','R=1为比例基准'),('Figure4','c','作者基准、First','First roles relative to author participation','strict_main_R','分母改变，不重标角色'),('Figure4','d','作者基准、Last','Last roles relative to author participation','strict_main_R','CI跨零不证明等效'),('Figure5','a','同国同机构/同国不同机构/机构未决/跨国','Geographic and institutional correspondence','strict_main_structure','国家优先的机构信用，4类总和1'),('Figure5','b','完整组间实际配对','Actual first–last group pairings','strict_main_pairings','同组不必同国；不画因果流'),('Figure5','c','超出团队构成的偏离','Observed minus exact team-composition expectation','strict_main_pairings','不同作者；未固定首末边际')]
    for ID,descs in {'F4_ED1':['国际率','团队median/IQR','嵌套样本','年度保留率'],'F4_ED2':['国家ΔR','作者ΔR','直接C','覆盖/ESS'],'F4_ED3':['国内机构分布','同机构配对差','机会箱零角色','实际零与条件参照'],'F4_ED4':['主结构','唯一国家机构子样本','角色构成与覆盖底表','国内组配对']}.items():
      for k,desc in enumerate(descs):panels.append((ID,'abcd'[k],desc,desc,'see_source_data_registry','分母、条件范围与限制见完整图注'))
    pd.DataFrame(panels,columns=['figure_id','panel','reader_message_zh','reader_message_en','source_table','limit_zh']).to_csv(ROOT/'manuscript/panel_registry.csv',index=False)
    guide=['# 逐面板读者信息、方法、修改原因与图件','', '主图仅保留字母标记；必要的基准行、角色列及语料名称保留。F4_PAIRING是候选Figure 5，未覆盖另一Finding的Figure5。','', '|图/面板|读者应获得的信息|来源/方法|解释边界|','|---|---|---|---|']
    for ID,panel,msg,en,source,limit in panels:guide.append(f'|[{ID} {panel}](../figures/{ID}.pdf)|{msg} / {en}|{source}|{limit}|')
    guide+=['','所有图注含中英文说明、实际分母及不确定性：[完整图注](captions_zh_en.md)。','', '修改原因：两基准以相同严格资格比较，避免把样本变化混成基准变化；新增真实首末联合关系补足边际图无法回答的问题；机构unknown单列避免制造同/异机构关系；模拟和bootstrap分开避免把不同不确定性混称。六项排除源于用户明确确认的身份规则，不依赖结果方向。','', '全部补图：']
    for k in range(1,7):guide.append(f'- [F4_S{k} PDF](../figures/F4_S{k}.pdf)：说明见[图注](captions_zh_en.md)，底表见[Source Data](../source_data/README_zh.md)。')
    guide+=['','## Alt text / 可访问描述','', 'Figure 4 is a 2×2 dot-and-range chart. Lower-group AF representation is farther below reference under country participation than under author participation; both roles, identical sample and a shared R=1 benchmark are visible.','', 'Figure 5 contains two stacked credit bars, two parallel first–last alluvial diagrams and two complete 4×4 observed-minus-expected heatmaps. Same-country credit is separated into known same/different institutions and unresolved institutions. Higher→higher credit dominates the alluvial areas, while deviations from team composition are much smaller and include both signs.','', 'Extended/Supplementary graphics show all-country heterogeneity, sample retention, domestic institutional zeros/opportunities and period/support sensitivities. Underlying numeric data are supplied so color or thin ribbons are not the sole evidence source.']
    write('manuscript/panel_guide_zh_en.md','\n'.join(guide))
    write('manuscript/requirements_comparison_zh.md','''# 原要求—实际交付核对

以Finding4 v7目录为主，Figure5新专项目录覆盖旧5a要求；2026-10-30用户明确确认的六项排除优先于旧“只重排不重估”条款。

|要求|交付|实际状态/变化|
|---|---|---|
|Figure4 a–d同样本两基准|Figure4、T2、逐点旧新对照|已严格重估2,000轮；旧版原样保留|
|Figure5 a四类结构|Figure5a、T7、实际联合长表|完成；unknown灰色保留，未换样本|
|Figure5 b/c真实16配对/精确参照|Figure5b/c、T6|完成；非边际反推；扣同作者项|
|N02直接配对C/B|T2/T3、ED2、S6|完成；共享整研究draws|
|N04条件端点参照|T6、S5|精确期望+2,000端点模拟；与bootstrap分表|
|N05有限机会|ED3、S6、T7|analytic P0+2,000模拟；独立资格与角色无定义记录|
|N06支持/严格/唯一池/时期|S3/S4、T5/T6|完成；共享时期目标和直接变化，不保证方向一致|
|全部注册国家/国内机构|ED2十页、S1全基线国家分页、T3/T4|空值/零/outside不静默丢弃；国内R重新排除同作者端点|
|四组ED、六组S、七组T、六节Notes|图件注册表、Source Data、Notes|全部交付，组数不等于页数|
|中英Results/Methods/captions、读者信息|manuscript目录|已更新真实新数值和限制|
|主图PDF/SVG/600dpiRGB PNG/TIFF|figures目录|183mm宽，字体/像素/布局检查；不冒称期刊接收认证|
|旧版对照/不改源数据|inputs/handoff、provenance、对照表|原始文件字节哈希复核|
|共同首末贡献、完整联盟、字母排序|T5 execution_status|unavailable，非已排除或PASS|
|国家×国家单格bootstrap|T6|完整227×227网格、raw/standardized、O/E/偏离/直接语料差的2,000轮条件范围；退化/结构零明确标记|
|正式依赖稳健/因果推断|全部方法和解释边界|未实施且不声称；条件分析不是机制检验|

Figure5留在候选主图，因为它加入同研究的真实联合位置、同机构/同国结构和构成参照信息；这一判断不以某格p值、区间跨零或效应方向为依据。正式全稿图号由F4_MAIN/F4_PAIRING稳定ID装配，不覆盖其他Finding。

[结果](results_zh.md) · [方法](methods_zh.md) · [全部图件/面板](panel_guide_zh_en.md)
''')
    figures=json.loads((ROOT/'provenance/figure_registry.json').read_text());entries=[]
    for x in figures:entries.append(f'|{x["figure_id"]}|{x["pages"]}|[PDF]({x["pdf"]})|[预览]({x["preview"]})|')
    write('README_zh.md','''# Finding 4 v7 与 Figure 5 联合交付

2026-10-30。**这是实际执行后的新版本。** 旧方案中的pending数字与旧图保留作档案，不是当前状态。

先读：[中文结果](manuscript/results_zh.md) · [中文方法](manuscript/methods_zh.md) · [逐面板读者信息](manuscript/panel_guide_zh_en.md) · [原要求核对](manuscript/requirements_comparison_zh.md)

English: [Results](manuscript/results_en.md) · [Methods](manuscript/methods_en.md) · [Bilingual captions](manuscript/captions_zh_en.md)

## 本次完成

Figure4与Figure5统一剔除6篇参照中首末同作者记录：主共同支持AF5,087 / reference332,760、173单元。重建真实国家/机构配对、精确不同作者期望，完成两基准共享2,000整研究bootstrap、2,000端点条件模拟、机构零机会与预设敏感性/时期直接比较。旧图、点、范围未覆盖。没有新增API或LLM费用。

## 全部图件

|稳定ID|PDF页数|矢量图|屏幕预览|
|---|---:|---|---|
'''+ '\n'.join(entries)+'''

主图还提供 [Figure4 SVG](figures/Figure4.svg)、[600dpi PNG](figures/Figure4_600dpi.png)、[TIFF](figures/Figure4_600dpi.tiff)；[Figure5 SVG](figures/Figure5.svg)、[600dpi PNG](figures/Figure5_600dpi.png)、[TIFF](figures/Figure5_600dpi.tiff)。SVG文字可编辑但需本机字体。Figure5是F4_PAIRING暂定全文图号，与另一Finding不相互覆盖。

## 表、Notes与验证

- [七组Source Data及逐篇数据](source_data/README_zh.md)
- [六节Supplementary Notes](manuscript/supplementary_notes_zh_en.md)
- [执行状态与不可用项](source_data/execution_status.json)
- [数值与交付核验](provenance/validation_summary.json)
- [全包文件哈希](manifest.json)
- [图件视觉核验](provenance/visual_review.json)
- [软件与离线复现](code/README.md)
- [逐点旧新对照](tables/Figure4_legacy_strict_comparison.csv)
- [六篇排除名单](tables/legacy_same_author_role_exclusions.csv) · [用户确认记录](provenance/accepted_scope_change.json)

旧版来源按原字节保留在inputs/handoff及inputs/handoff_figure5；它们是不可改写的历史档案，可能包含旧绝对路径和旧pending文字。**当前阅读导航均采用相对路径，解压后从本README进入。** 当前数值以本包tables/manuscript为准。大表使用Parquet，完整国家矩阵另有CSV gzip；不需要外置JSONL即可从规范化快照复核。

本交付提供条件描述和条件参照，不认证实际领导、公平或因果效应。共同贡献、完整联盟、字母排序等缺可靠字段，明确unavailable；国家网格及组层区间完整提供；退化及结构零另外标记。183mm与600dpi是实际导出参数，不是期刊技术接收认证。
''')
    dump(ROOT/'provenance/report_complete.json',dict(status='PASS',bilingual_results=True,bilingual_methods=True,bilingual_captions=True,notes=6,table_groups=7,figure_groups=len(figures),figure_pages=sum(x['pages'] for x in figures),source_numbers='loaded from committed tables; no manually invented empirical values'))
    print('Bilingual manuscript / seven table groups / six Notes written',flush=True)
if __name__=='__main__':main()
