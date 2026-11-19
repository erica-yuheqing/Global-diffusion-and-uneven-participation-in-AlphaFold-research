# Final-v1 分析数据字典

## 数据层级

`works_analysis_master.parquet` 和 `reviewed_candidates.parquet` 都以标准化后的 OpenAlex
`work_id` 为唯一键，一篇论文一行。作者、机构、国家或领域的重复关系不得在论文层统计中直接当成独立论文。

- `works_analysis_master.parquet`：全部来源论文，包含已审定候选集和启发式筛选阴性对照。
- `reviewed_candidates.parquet`：只包含最终数据库中的 29,127 条候选论文。
- 候选集外记录是 `screen_negative comparator`，不是人工或模型确认的 AF 非使用论文。

## 核心标识与书目信息

| 字段 | 类型 | 来源/含义 | 缺失与使用规则 |
|---|---|---|---|
| `work_id` | string | 标准化 OpenAlex ID，如 `W4311539894` | 主键，不允许缺失或重复 |
| `doi` | string | DOI | 可缺失；不作为主键 |
| `title` | string | 代表性 works 行中的题名 | 缺失时记录警告 |
| `abstract` | string | OpenAlex 派生表中的摘要 | 可缺失；不是最终审定证据包的完整替代物 |
| `publication_year` | integer | 发表年份 | 缺失时不进入年度分析 |
| `publication_date` | date/string | 发表日期 | 可缺失 |
| `cited_by_count` | integer | OpenAlex 抓取时的引用数快照 | 具有时间截面属性，不应解释为永久值 |
| `work_type` | string | OpenAlex 文献类型 | 经规范化后用于排除 editorial、letter 等类型 |
| `journal_or_source_id` | string | 来源期刊/平台 ID | 可缺失 |
| `journal_or_source_name` | string | 来源期刊/平台名称 | 可缺失 |

## 学科与主题

| 字段 | 类型 | 含义 | 分析规则 |
|---|---|---|---|
| `domain_labels` | pipe-delimited string | 同一论文的去重领域标签 | 领域分析前拆分 |
| `domain_count` | integer | 论文具有的非空领域数量 | 用于分数计数 |
| `domain_fraction` | float | `1 / domain_count` | 一篇论文跨多个领域时总权重仍为 1 |
| `primary_topic_*` | string | OpenAlex primary topic | 论文级代表性元数据 |
| `primary_field_*` | string | OpenAlex field | 论文级代表性元数据 |
| `primary_subfield_*` | string | OpenAlex subfield | 论文级代表性元数据 |
| `primary_domain_*` | string | OpenAlex primary domain | 与多领域 `domain_labels` 分开保留 |

## 筛选与来源

| 字段 | 类型 | 允许值/含义 |
|---|---|---|
| `legacy_screen_positive` | boolean | 旧启发式规则是否曾将论文筛入候选集 |
| `legacy_af_usage_level` | string | 旧启发式 AF 使用等级，只用于方法比较，不作为最终结局 |
| `candidate_reviewed` | boolean | 是否出现在最终 29,127 条审定数据库中 |
| `screening_status` | category | `reviewed_candidate` 或 `screen_negative` |
| `is_screen_negative_comparator` | boolean | 候选集外启发式阴性对照；不得称为确认非使用 |
| `decision_route` | category | 最终标签形成路径，如 A/B 共识、Model C 或人工裁决 |
| `source_route` | category | 合并时使用的更细来源路径 |
| `final_record_sha256` | string | 单条最终记录完整性哈希；候选记录必须存在 |

## 最终审定核心标签

| 字段 | 允许值 | 解释 |
|---|---|---|
| `primary_label` | protocol-defined category | 最终主要分类标签 |
| `relevance_level` | `R0`–`R4`, `RU` | AF 相关程度；`RU` 为证据不足导致的不确定 |
| `evidence_level` | `E0`–`E3` | 支撑判断的证据强度等级 |
| `evidence_tier` | `fulltext_evidence`, `abstract_only`, `insufficient_evidence`, `oversize_context_human_review` 等 | 输入证据来源层级 |
| `af_related_label` | protocol-defined category | 是否与 AF 主题实质相关 |
| `af_use_label` | `yes`, `no`, `uncertain` | 作者是否实际运行、获取或下游使用 AF 预测 |
| `adoption_eligible` | `yes`, `no`, `uncertain` | 是否满足研究预先规定的“技术采用”定义 |
| `exclusion_reason` | category | 未计为确认采用/使用的主要原因 |
| `future_or_hypothetical_only` | boolean | 是否仅讨论未来或假设性使用 |

`uncertain` 是有实质含义的审定类别，不是普通缺失值。它不得重编码为 `no`。主分析的 resolved-case
比例使用 `yes / (yes + no)`；同时报告把不确定计入分母的保守下界，以及把不确定视为潜在使用的扩张上界。

## 动作层标签

| 字段 | 含义 | 主分析资格 |
|---|---|---|
| `observed_actions_status` | 动作标签的共识/裁决状态 | 仅 `ab_exact_consensus` 和 `adjudicated` 合格 |
| `final_observed_actions` | 最终动作集合 | 仅在上述合格状态中分析 |
| `model_a_observed_actions` | Model A 动作集合 | 审计字段 |
| `model_b_observed_actions` | Model B 动作集合 | 审计字段 |

`disagreement_unadjudicated` 与 `not_assessed_insufficient_evidence` 不进入动作频率主分析，但不影响记录依据其
最终核心标签进入 AF 关系、使用和采用分析。

## 质量与分析派生变量

| 字段 | 类型 | 含义 |
|---|---|---|
| `needs_human_review` | boolean | 合并前/合并时的复核标志；不自动推翻最终标签 |
| `confidence` | numeric/category | 标签置信信息，按原最终数据库保留 |
| `semantic_heuristic_warning` | boolean | 语义启发式质量警告 |
| `semantic_warning_sources` | string/list-like | 触发警告的来源 |
| `is_af_related_confirmed` | boolean | `af_related_label == 'related'` |
| `is_af_use_confirmed` | boolean | `af_use_label == 'yes'` |
| `is_af_non_use_confirmed` | boolean | `af_use_label == 'no'` |
| `is_af_use_resolved` | boolean | `af_use_label in {'yes','no'}` |
| `is_af_use_uncertain` | boolean | `af_use_label == 'uncertain'` |
| `is_adoption_confirmed` | boolean | `adoption_eligible == 'yes'` |
| `is_adoption_resolved` | boolean | `adoption_eligible in {'yes','no'}` |
| `action_analysis_eligible` | boolean | 动作状态已共识或已裁决 |
| `is_main_period` | boolean | 发表年份为 2019–2025 |
| `analytical_document_type_eligible` | boolean | 不属于预设排除的文献类型 |

## 缺失值语义

1. 候选集外记录的最终标签为空是结构性缺失，因为这些论文没有进入最终审定流程。
2. 正文缺失、摘要缺失或证据等级低不等于确认未使用 AF。
3. `uncertain` 是审定结果，不应转换为 `NA`。
4. 年份、领域或书目信息缺失属于元数据缺失，应单独报告覆盖率。
5. 动作未评估和动作有分歧属于动作层状态，不应改变核心使用/采用标签。

## 计数与分母

- 论文总量：唯一 `work_id`。
- 候选集标签构成：分母为 29,127 条已审定候选论文。
- resolved-case 使用率：分母为 `af_use_label` 等于 `yes` 或 `no` 的记录。
- resolved-case 采用率：分母为 `adoption_eligible` 等于 `yes` 或 `no` 的记录。
- 领域分析：一篇论文在其各领域中使用 `1 / domain_count` 分数权重。
- 动作频率：分母仅包括 `action_analysis_eligible == True` 且动作字段可解释的记录。
