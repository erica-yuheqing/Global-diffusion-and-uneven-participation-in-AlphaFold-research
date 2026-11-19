import marimo

__generated_with = "0.21.1"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    从 OpenAlex 抓取下来的 work 元数据，整理到可以直接进入 **DuckDB + Parquet + 规范化分析表** 的数据准备流程。

    这份 notebook 的目标不是直接做最终分析，而是先把半结构化 OpenAlex JSON 变成后续可复用的数据层，服务于例如：

    - 地理分布分析
    - 机构 / 国家协作分析
    - 引用网络分析
    - AlphaFold adoption / diffusion 分析

    基于你当前实际抓取的字段：

    - `id`
    - `doi`
    - `display_name`
    - `publication_year`
    - `publication_date`
    - `cited_by_count`
    - `referenced_works`
    - `abstract_inverted_index`
    - `authorships`
    - `concepts`
    - `primary_location`
    - `primary_topic`
    - `topics`
    - `type`

    这份 notebook 采用的主线是：

    1. 保留原始 JSONL；
    2. 将 OpenAlex 嵌套字段规范化拆表；
    3. 输出为适合 DuckDB 扫描的 Parquet；
    4. 为后续 AlphaFold 标签、主题扩散、地理分布与引用分析提供统一数据层。

    下面内容分为两部分：

    - 第一部分：小样本快速检查函数，用来理解原始 JSON 结构；
    - 第二部分：主推荐方案，即 DuckDB + Parquet + 分层表设计。
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 一、小样本快速检查：解析 JSONL → 基础预览表

    这一部分的目标不是作为主分析流程，而是：

    - 快速理解原始 JSON 结构；
    - 用小样本检查字段是否齐全；
    - 在正式进入规范化拆表前，先做一次轻量预览。

    注意：这一部分仍然使用 `pandas` 生成少量预览表，适合抽样检查；
    **不建议把它作为全量数据处理主流程。**
    """)
    return


@app.cell(hide_code=True)
def _():
    import json
    from typing import List, Dict, Any
    import pandas as pd

    return Any, Dict, List, json, pd


@app.cell(hide_code=True)
def _(
    Any,
    Dict,
    List,
    extract_raw_affiliation_text,
    extract_work_abstract,
    extract_work_title,
    json,
    pd,
):
    def load_works_jsonl(path: str) -> List[Dict[str, Any]]:
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                records.append(json.loads(line))
        return records


    def iter_works_jsonl(path: str):
        with open(path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                yield line_number, json.loads(line)


    def build_basic_tables(
        works: List[Dict[str, Any]]
    ) -> Dict[str, pd.DataFrame]:
        """
        输入：前面抓下来的 works 列表（每个是 dict）
        输出：
          - works_df:   论文级信息
          - authorships_df: 作者–论文关系表
          - work_institutions_df: 机构–论文关系表

        注意：这是小样本快速检查函数，字段映射兼容两类常见 schema：
          - OpenAlex 原始风格：display_name / abstract_inverted_index
          - 扁平化风格：title / abstract
        """
        works_rows = []
        authorships_rows = []
        work_institutions_rows = []

        for w in works:
            work_id = w.get("id")
            doi = w.get("doi")
            title = extract_work_title(w)
            year = w.get("publication_year")
            pub_date = w.get("publication_date")
            cited_by_count = w.get("cited_by_count", 0)
            work_type = w.get("type")
            abstract_text = extract_work_abstract(w)

            primary_location = w.get("primary_location") or {}
            source_obj = primary_location.get("source") or {}
            venue_id = source_obj.get("id")
            venue_name = source_obj.get("display_name")
            venue_type = source_obj.get("type")

            primary_topic = w.get("primary_topic") or {}
            concepts = w.get("concepts") or []
            concept_ids = [c.get("id") for c in concepts]
            concept_names = [c.get("display_name") for c in concepts]

            works_rows.append({
                "work_id": work_id,
                "doi": doi,
                "title": title,
                "publication_year": year,
                "publication_date": pub_date,
                "abstract": abstract_text,
                "cited_by_count": cited_by_count,
                "type": work_type,
                "venue_id": venue_id,
                "venue_name": venue_name,
                "venue_type": venue_type,
                "primary_topic_id": primary_topic.get("id"),
                "primary_topic_display_name": primary_topic.get("display_name"),
                "concept_ids": concept_ids,
                "concept_names": concept_names,
            })

            for auth in w.get("authorships", []):
                author = auth.get("author") or {}
                institutions = auth.get("institutions") or []
                authorships_rows.append({
                    "work_id": work_id,
                    "author_position": auth.get("author_position"),
                    "author_id": author.get("id"),
                    "author_name": author.get("display_name"),
                    "is_corresponding": auth.get("is_corresponding"),
                    "raw_affiliation_string": extract_raw_affiliation_text(auth),
                    "institution_ids": [inst.get("id") for inst in institutions],
                    "institution_names": [inst.get("display_name") for inst in institutions],
                    "institution_countries": [inst.get("country_code") for inst in institutions],
                })

                for inst in institutions:
                    work_institutions_rows.append({
                        "work_id": work_id,
                        "author_id": author.get("id"),
                        "institution_id": inst.get("id"),
                        "institution_name": inst.get("display_name"),
                        "country_code": inst.get("country_code"),
                        "institution_type": inst.get("type"),
                    })

        works_df = pd.DataFrame(works_rows)
        authorships_df = pd.DataFrame(authorships_rows)
        work_institutions_df = pd.DataFrame(work_institutions_rows)

        return {
            "works": works_df,
            "authorships": authorships_df,
            "work_institutions": work_institutions_df,
        }

    return build_basic_tables, iter_works_jsonl, load_works_jsonl


@app.cell(hide_code=True)
def _(build_basic_tables, load_works_jsonl):
    def data_prepare():
        records = load_works_jsonl("raw_jsonl/domain_enzymology_protein_engineering_synthetic_biology_2015_2025.jsonl")
        tables = build_basic_tables(records)

        works_df = tables["works"]
        authorships_df = tables["authorships"]
        work_institutions_df = tables["work_institutions"]

        # 这是小样本快速检查入口，不是推荐的全量主流程
        print(works_df.head())
        print(authorships_df.head())
        print(work_institutions_df.head())

        # 可选：仅用于轻量预览存盘
        works_df.to_parquet("raw_jsonl/works.parquet", index=False)
        authorships_df.to_parquet("raw_jsonl/authorships.parquet", index=False)
        work_institutions_df.to_parquet("raw_jsonl/work_institutions.parquet", index=False)

    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    有了：

    - ‎`works_df`: 每行一篇论文，带 year / abstract / cited_by_count / concepts。

    - ‎`authorships_df`: 作者–论文关系（+机构列表）。

    - ‎`work_institutions_df`: 机构–论文关系（+国家）。
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 二、按 DuckDB + Parquet + 分层表设计继续做数据准备

    基于你现在从 OpenAlex 抓取的字段：

    - `id`
    - `doi`
    - `display_name`
    - `publication_year`
    - `publication_date`
    - `cited_by_count`
    - `referenced_works`
    - `abstract_inverted_index`
    - `authorships`
    - `concepts`
    - `primary_location`
    - `primary_topic`
    - `topics`
    - `type`

    下面建议把流程从“原始 JSONL”推进到“可分析的规范化表”。

    ### 推荐原则

    - 原始落地格式：`JSONL -> Parquet`
    - 主分析引擎：`DuckDB`
    - 小规模抽样检查 / 轻量列操作：`Polars`
    - 尽量避免把全量 JSONL 一次性读入 pandas

    ### 推荐分层

    #### 1. 原始层

    保留：

    - 原始 `jsonl`
    - 或逐文件转换后的 `raw parquet`

    #### 2. 分析层

    把嵌套结构拆成规范化表，至少包括：

    - `works`
    - `work_references`
    - `authorships`
    - `work_institutions`
    - `work_topics`
    - `work_concepts`
    - `af_seed_works`
    - `af_label_evidence`

    ### 推荐目录结构

    ```text
    raw_jsonl/
    parquet_raw/
    duckdb/
    derived_tables/
    ```

    例如：

    - `raw_jsonl/domain_structural_biology_2015_2025.jsonl`
    - `parquet_raw/domain_structural_biology_2015_2025.parquet`
    - `duckdb/alphafold_analysis.duckdb`

    ### 最实际的处理顺序

    #### 第一阶段：先做最核心两张表

    - `works`
    - `work_references`

    这两张表已经足够支撑：

    - 年度产出趋势
    - AF / non-AF 切分
    - 引用 AF 核心论文的识别
    - 引用网络基础统计

    #### 第二阶段：再拆作者与机构

    - `authorships`
    - `work_institutions`

    这一步支撑：

    - 团队规模
    - 机构合作
    - 国际合作
    - 地理分布

    #### 第三阶段：再拆 topics / concepts

    - `work_topics`
    - `work_concepts`

    这一步支撑：

    - 子领域扩散
    - topic adoption 差异
    - 主题迁移

    #### 第四阶段：做 AlphaFold 标签

    建议不要只做一个布尔值，而是多层标签：

    - `is_alphafold_related`
    - `is_alphafold2`
    - `is_alphafold3`
    - `is_alphafold_db`
    - `af_usage_level`

    其中 `af_usage_level` 可以先定义为：

    - `direct_use`
    - `benchmark_or_method_discussion`
    - `mention_only`
    - `citation_only`
    - `non_af`

    ### 下面代码的结构

    下面的代码骨架按照四层组织：

    #### A. 基础工具层

    处理：

    - 抽象还原
    - 文本规整
    - 路径创建
    - AlphaFold 关键词模式

    #### B. 规范化主流程层

    把单条 OpenAlex work 记录拆成：

    - `works`
    - `work_references`
    - `authorships`
    - `work_institutions`
    - `work_topics`
    - `work_concepts`

    #### C. AF 标签层

    输出：

    - works 主表中的 AF 标记字段
    - `af_label_evidence` 证据表
    - 可单独维护的 `af_seed_works`

    #### D. 输出层

    负责：

    - 写出单批次 parquet
    - 追加到分表目录
    - 提供手动执行入口

    ### 设计原则

    这一部分默认只定义函数，不自动执行文件读取或批量写盘。

    这样可以先把表结构、标签逻辑和目录接口固定下来，等你确认：

    - 实际 JSONL 路径
    - 领域标签命名
    - AF 种子论文列表
    - 输出目录

    之后再手动调用执行入口。
    """)
    return


@app.cell(hide_code=True)
def _():
    from pathlib import Path
    import re

    return Path, re


@app.cell(hide_code=True)
def _(Any, Dict, List, Path, re):
    def invert_abstract_index(inverted_index: Dict[str, List[int]]) -> str:
        if not inverted_index:
            return ""

        token_positions = []
        for token, positions in inverted_index.items():
            for pos in positions or []:
                token_positions.append((pos, token))

        if not token_positions:
            return ""

        token_positions.sort(key=lambda x: x[0])
        return " ".join(token for _, token in token_positions)


    def ensure_parent_dir(path_str: str) -> Path:
        path_obj = Path(path_str)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        return path_obj


    def normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()


    af_title_patterns = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"\\balphafold\\b",
            r"\\balphafold2\\b",
            r"\\balphafold 2\\b",
            r"\\balphafold3\\b",
            r"\\balphafold 3\\b",
            r"\\baf2\\b",
            r"\\baf3\\b",
            r"\\balphafold db\\b",
            r"\\balphafold database\\b",
        ]
    ]


    af_usage_patterns = {
        "direct_use": [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"using alphafold",
                r"used alphafold",
                r"alphafold-predicted",
                r"alphafold predicted",
                r"alphafold model",
                r"alphafold structure",
            ]
        ],
        "benchmark_or_method_discussion": [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"comparison with alphafold",
                r"evaluate alphafold",
                r"alphafold performance",
                r"alphafold accuracy",
            ]
        ],
    }
    return (
        af_title_patterns,
        af_usage_patterns,
        invert_abstract_index,
        normalize_text,
    )


@app.cell(hide_code=True)
def _(
    Any,
    Dict,
    List,
    af_title_patterns,
    af_usage_patterns,
    invert_abstract_index,
    normalize_text,
    pd,
    re,
):
    def extract_work_title(work: Dict[str, Any]) -> str:
        return normalize_text(work.get("title") or work.get("display_name"))


    def extract_work_abstract(work: Dict[str, Any]) -> str:
        direct_abstract = normalize_text(work.get("abstract"))
        if direct_abstract:
            return direct_abstract
        return invert_abstract_index(work.get("abstract_inverted_index") or {})


    def extract_raw_affiliation_text(auth: Dict[str, Any]) -> str:
        single_value = normalize_text(auth.get("raw_affiliation_string"))
        if single_value:
            return single_value

        multi_values = auth.get("raw_affiliation_strings") or []
        normalized_values = [normalize_text(item) for item in multi_values if normalize_text(item)]
        if normalized_values:
            return " | ".join(normalized_values)

        affiliations = auth.get("affiliations") or []
        fallback_values = []
        for affiliation in affiliations:
            raw_value = normalize_text(affiliation.get("raw_affiliation_string"))
            if raw_value:
                fallback_values.append(raw_value)

        if fallback_values:
            return " | ".join(fallback_values)

        return ""


    def classify_af_signals(
        title: str,
        abstract_text: str,
        referenced_works: List[str],
        af_seed_ids: List[str] | None = None,
    ) -> Dict[str, Any]:
        af_seed_set = set(af_seed_ids or [])
        _title = normalize_text(title)
        _abstract = normalize_text(abstract_text)
        combined_text = f"{_title}\n{_abstract}".strip()

        title_matches = [p.pattern for p in af_title_patterns if p.search(_title)]
        abstract_matches = [p.pattern for p in af_title_patterns if p.search(_abstract)]
        reference_matches = [ref for ref in referenced_works or [] if ref in af_seed_set]

        usage_level = "non_af"
        usage_patterns = []
        for level_name, pattern_list in af_usage_patterns.items():
            matched = [p.pattern for p in pattern_list if p.search(combined_text)]
            if matched:
                usage_level = level_name
                usage_patterns.extend(matched)
                break

        is_related = bool(title_matches or abstract_matches or reference_matches or usage_patterns)
        if not is_related:
            usage_level = "non_af"
        elif usage_level == "non_af" and reference_matches:
            usage_level = "citation_only"
        elif usage_level == "non_af":
            usage_level = "mention_only"

        is_af2 = any(re.search(r"alphafold2|alphafold 2|\\baf2\\b", item, re.IGNORECASE) for item in title_matches + abstract_matches)
        is_af3 = any(re.search(r"alphafold3|alphafold 3|\\baf3\\b", item, re.IGNORECASE) for item in title_matches + abstract_matches)
        is_af_db = any(re.search(r"alphafold db|alphafold database", item, re.IGNORECASE) for item in title_matches + abstract_matches)

        return {
            "is_alphafold_related": is_related,
            "is_alphafold2": is_af2,
            "is_alphafold3": is_af3,
            "is_alphafold_db": is_af_db,
            "af_signal_title": bool(title_matches),
            "af_signal_abstract": bool(abstract_matches),
            "af_signal_reference": bool(reference_matches),
            "af_signal_keyword": bool(usage_patterns),
            "af_usage_level": usage_level,
            "title_matches": title_matches,
            "abstract_matches": abstract_matches,
            "reference_matches": reference_matches,
            "usage_matches": usage_patterns,
        }


    def normalize_openalex_record(
        work: Dict[str, Any],
        domain_label: str = "",
        domain_search_query: str = "",
        af_seed_ids: List[str] | None = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        work_id = work.get("id")
        doi = work.get("doi")
        title = extract_work_title(work)
        publication_year = work.get("publication_year")
        publication_date = work.get("publication_date")
        cited_by_count = work.get("cited_by_count", 0)
        work_type = work.get("type")
        referenced_works = work.get("referenced_works") or []

        abstract_text = extract_work_abstract(work)

        primary_location = work.get("primary_location") or {}
        source_obj = primary_location.get("source") or {}
        source_id = source_obj.get("id")
        source_name = source_obj.get("display_name")

        primary_topic = work.get("primary_topic") or {}
        subfield_obj = primary_topic.get("subfield") or {}
        field_obj = primary_topic.get("field") or {}
        domain_obj = primary_topic.get("domain") or {}

        af_flags = classify_af_signals(
            title=title,
            abstract_text=abstract_text,
            referenced_works=referenced_works,
            af_seed_ids=af_seed_ids,
        )

        works_row = {
            "work_id": work_id,
            "doi": doi,
            "title": title,
            "abstract": abstract_text,
            "publication_year": publication_year,
            "publication_date": publication_date,
            "cited_by_count": cited_by_count,
            "type": work_type,
            "domain_label": domain_label,
            "domain_search_query": domain_search_query,
            "primary_topic_id": primary_topic.get("id"),
            "primary_topic_display_name": primary_topic.get("display_name"),
            "primary_field_id": field_obj.get("id"),
            "primary_field_display_name": field_obj.get("display_name"),
            "primary_subfield_id": subfield_obj.get("id"),
            "primary_subfield_display_name": subfield_obj.get("display_name"),
            "primary_domain_id": domain_obj.get("id"),
            "primary_domain_display_name": domain_obj.get("display_name"),
            "journal_or_source_id": source_id,
            "journal_or_source_name": source_name,
            **{k: v for k, v in af_flags.items() if not k.endswith("_matches")},
        }

        reference_rows = [
            {
                "source_work_id": work_id,
                "referenced_work_id": ref_id,
            }
            for ref_id in referenced_works
        ]

        authorship_rows = []
        institution_rows = []
        for auth in work.get("authorships") or []:
            author = auth.get("author") or {}
            author_id = author.get("id")
            author_name = author.get("display_name")
            institutions = auth.get("institutions") or []
            raw_affiliation_text = extract_raw_affiliation_text(auth)

            authorship_rows.append({
                "work_id": work_id,
                "author_position": auth.get("author_position"),
                "author_id": author_id,
                "author_name": author_name,
                "is_corresponding": auth.get("is_corresponding"),
                "raw_affiliation_string": raw_affiliation_text,
            })

            for inst in institutions:
                institution_rows.append({
                    "work_id": work_id,
                    "author_id": author_id,
                    "institution_id": inst.get("id"),
                    "institution_name": inst.get("display_name"),
                    "country_code": inst.get("country_code"),
                    "institution_type": inst.get("type"),
                    "is_global_south": None,
                })

        topic_rows = []
        for topic in work.get("topics") or []:
            subfield_item = topic.get("subfield") or {}
            field_item = topic.get("field") or {}
            domain_item = topic.get("domain") or {}
            topic_rows.append({
                "work_id": work_id,
                "topic_id": topic.get("id"),
                "topic_display_name": topic.get("display_name"),
                "topic_score": topic.get("score"),
                "subfield_id": subfield_item.get("id"),
                "subfield_display_name": subfield_item.get("display_name"),
                "field_id": field_item.get("id"),
                "field_display_name": field_item.get("display_name"),
                "domain_id": domain_item.get("id"),
                "domain_display_name": domain_item.get("display_name"),
            })

        concept_rows = [
            {
                "work_id": work_id,
                "concept_id": concept.get("id"),
                "concept_display_name": concept.get("display_name"),
                "concept_score": concept.get("score"),
            }
            for concept in (work.get("concepts") or [])
        ]

        evidence_rows = []
        for matched_pattern in af_flags["title_matches"]:
            evidence_rows.append({
                "work_id": work_id,
                "evidence_type": "title_match",
                "title_match": True,
                "abstract_match": False,
                "reference_match": False,
                "keyword_match": False,
                "evidence_value": title,
                "matched_pattern": matched_pattern,
            })

        for matched_pattern in af_flags["abstract_matches"]:
            evidence_rows.append({
                "work_id": work_id,
                "evidence_type": "abstract_match",
                "title_match": False,
                "abstract_match": True,
                "reference_match": False,
                "keyword_match": False,
                "evidence_value": abstract_text,
                "matched_pattern": matched_pattern,
            })

        for matched_reference in af_flags["reference_matches"]:
            evidence_rows.append({
                "work_id": work_id,
                "evidence_type": "reference_match",
                "title_match": False,
                "abstract_match": False,
                "reference_match": True,
                "keyword_match": False,
                "evidence_value": matched_reference,
                "matched_pattern": matched_reference,
            })

        for matched_pattern in af_flags["usage_matches"]:
            evidence_rows.append({
                "work_id": work_id,
                "evidence_type": "keyword_match",
                "title_match": False,
                "abstract_match": False,
                "reference_match": False,
                "keyword_match": True,
                "evidence_value": f"{title}\n{abstract_text}".strip(),
                "matched_pattern": matched_pattern,
            })

        return {
            "works": [works_row],
            "work_references": reference_rows,
            "authorships": authorship_rows,
            "work_institutions": institution_rows,
            "work_topics": topic_rows,
            "work_concepts": concept_rows,
            "af_label_evidence": evidence_rows,
        }


    def build_normalized_tables(
        works: List[Dict[str, Any]],
        domain_label: str = "",
        domain_search_query: str = "",
        af_seed_ids: List[str] | None = None,
    ) -> Dict[str, pd.DataFrame]:
        table_rows = {
            "works": [],
            "work_references": [],
            "authorships": [],
            "work_institutions": [],
            "work_topics": [],
            "work_concepts": [],
            "af_label_evidence": [],
        }

        for work in works:
            normalized = normalize_openalex_record(
                work=work,
                domain_label=domain_label,
                domain_search_query=domain_search_query,
                af_seed_ids=af_seed_ids,
            )
            for table_name, rows in normalized.items():
                table_rows[table_name].extend(rows)

        return {
            table_name: pd.DataFrame(rows)
            for table_name, rows in table_rows.items()
        }

    return (
        build_normalized_tables,
        extract_raw_affiliation_text,
        extract_work_abstract,
        extract_work_title,
    )


@app.cell(hide_code=True)
def _(
    Any,
    Dict,
    List,
    Path,
    build_normalized_tables,
    iter_works_jsonl,
    load_works_jsonl,
    pd,
):
    def write_normalized_tables_to_parquet(
        tables: Dict[str, pd.DataFrame],
        output_dir: str,
        file_stem: str,
    ) -> Dict[str, str]:
        output_paths = {}
        output_base = Path(output_dir)
        output_base.mkdir(parents=True, exist_ok=True)

        for table_name, table_df in tables.items():
            output_path = output_base / f"{file_stem}.{table_name}.parquet"
            table_df.to_parquet(output_path, index=False)
            output_paths[table_name] = str(output_path)

        return output_paths


    def append_normalized_tables_to_existing_parquet(
        tables: Dict[str, pd.DataFrame],
        output_dir: str,
        file_stem: str,
    ) -> Dict[str, str]:
        """
        说明：这是一个保守版追加接口。
        当前实现仍然按单次批次写出独立 parquet 文件，
        更适合后续由 DuckDB 通过 glob 统一读取，例如：
        derived_tables/works/*.parquet
        """
        output_paths = {}
        output_base = Path(output_dir)
        output_base.mkdir(parents=True, exist_ok=True)

        for table_name, table_df in tables.items():
            table_dir = output_base / table_name
            table_dir.mkdir(parents=True, exist_ok=True)
            output_path = table_dir / f"{file_stem}.parquet"
            table_df.to_parquet(output_path, index=False)
            output_paths[table_name] = str(output_path)

        return output_paths


    def build_af_seed_works_table(seed_rows: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        seed_rows 示例：
        [
            {
                "seed_work_id": "https://openalex.org/W...",
                "seed_type": "alphafold2_core",
                "title": "Highly accurate protein structure prediction with AlphaFold"
            }
        ]
        """
        return pd.DataFrame(seed_rows)


    def prepare_domain_tables_from_jsonl(
        jsonl_path: str,
        domain_label: str,
        domain_search_query: str,
        af_seed_ids: List[str] | None = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        注意：这是手动调用入口。
        定义后不会自动执行；只有你显式调用时才会读取 JSONL。
        该函数会一次性读入全部记录，只适合小样本检查。
        大文件请改用 stream_normalize_jsonl_to_parquet(...)
        """
        works_records = load_works_jsonl(jsonl_path)
        return build_normalized_tables(
            works=works_records,
            domain_label=domain_label,
            domain_search_query=domain_search_query,
            af_seed_ids=af_seed_ids,
        )


    def write_batch_tables_to_partitioned_parquet(
        tables: Dict[str, pd.DataFrame],
        output_dir: str,
        file_stem: str,
        batch_index: int,
    ) -> Dict[str, str]:
        output_paths = {}
        output_base = Path(output_dir)
        output_base.mkdir(parents=True, exist_ok=True)

        for table_name, table_df in tables.items():
            if table_df.empty:
                continue
            table_dir = output_base / table_name
            table_dir.mkdir(parents=True, exist_ok=True)
            output_path = table_dir / f"{file_stem}.part_{batch_index:06d}.parquet"
            table_df.to_parquet(output_path, index=False)
            output_paths[table_name] = str(output_path)

        return output_paths


    def normalize_works_batch(
        works_batch: List[Dict[str, Any]],
        domain_label: str = "",
        domain_search_query: str = "",
        af_seed_ids: List[str] | None = None,
    ) -> Dict[str, pd.DataFrame]:
        return build_normalized_tables(
            works=works_batch,
            domain_label=domain_label,
            domain_search_query=domain_search_query,
            af_seed_ids=af_seed_ids,
        )


    def detect_existing_batch_indices(
        output_dir: str,
        file_stem: str,
        table_name: str = "works",
    ) -> List[int]:
        table_dir = Path(output_dir) / table_name
        if not table_dir.exists():
            return []

        batch_indices = []
        prefix = f"{file_stem}.part_"
        suffix = ".parquet"
        for parquet_path in table_dir.glob(f"{file_stem}.part_*.parquet"):
            file_name = parquet_path.name
            if not (file_name.startswith(prefix) and file_name.endswith(suffix)):
                continue
            batch_str = file_name[len(prefix):-len(suffix)]
            if batch_str.isdigit():
                batch_indices.append(int(batch_str))

        return sorted(batch_indices)


    def estimate_resume_position(
        output_dir: str,
        file_stem: str,
        batch_size: int,
        table_name: str = "works",
    ) -> Dict[str, Any]:
        existing_batch_indices = detect_existing_batch_indices(
            output_dir=output_dir,
            file_stem=file_stem,
            table_name=table_name,
        )

        if not existing_batch_indices:
            return {
                "resume_enabled": False,
                "existing_batch_indices": [],
                "next_batch_index": 1,
                "records_to_skip": 0,
            }

        completed_batches = len(existing_batch_indices)
        next_batch_index = max(existing_batch_indices) + 1
        records_to_skip = completed_batches * batch_size
        return {
            "resume_enabled": True,
            "existing_batch_indices": existing_batch_indices,
            "next_batch_index": next_batch_index,
            "records_to_skip": records_to_skip,
        }


    def stream_normalize_jsonl_to_parquet(
        jsonl_path: str,
        domain_label: str,
        domain_search_query: str,
        output_dir: str = "derived_tables",
        file_stem: str | None = None,
        af_seed_ids: List[str] | None = None,
        batch_size: int = 5000,
        start_batch_index: int = 1,
        max_records: int | None = None,
        progress_every_batches: int = 10,
        resume: bool = False,
    ) -> Dict[str, Any]:
        """
        面向大文件的流式规范化入口：
        - 按行读取 JSONL
        - 按 batch 规范化
        - 按 batch 写出 parquet 分片
        - 可按已写出的 batch 文件自动恢复

        适合 35GB 级别 JSONL，不会把全文件一次性加载到内存。
        """
        resolved_file_stem = file_stem or Path(jsonl_path).stem
        seed_ids = af_seed_ids or []
        batch_records = []
        total_records = 0
        total_written_batches = 0
        latest_output_paths = {}
        skipped_records = 0
        table_write_counts = {
            "works": 0,
            "work_references": 0,
            "authorships": 0,
            "work_institutions": 0,
            "work_topics": 0,
            "work_concepts": 0,
            "af_label_evidence": 0,
        }

        resume_state = {
            "resume_enabled": False,
            "existing_batch_indices": [],
            "next_batch_index": start_batch_index,
            "records_to_skip": 0,
        }
        current_batch_index = start_batch_index

        if resume:
            resume_state = estimate_resume_position(
                output_dir=output_dir,
                file_stem=resolved_file_stem,
                batch_size=batch_size,
            )
            current_batch_index = max(start_batch_index, resume_state["next_batch_index"])

        records_to_skip = 0
        if resume and current_batch_index == resume_state["next_batch_index"]:
            records_to_skip = resume_state["records_to_skip"]

        def _flush_batch(_batch_records: List[Dict[str, Any]], _batch_index: int) -> Dict[str, str]:
            if not _batch_records:
                return {}
            batch_tables = normalize_works_batch(
                works_batch=_batch_records,
                domain_label=domain_label,
                domain_search_query=domain_search_query,
                af_seed_ids=seed_ids,
            )
            batch_paths = write_batch_tables_to_partitioned_parquet(
                tables=batch_tables,
                output_dir=output_dir,
                file_stem=resolved_file_stem,
                batch_index=_batch_index,
            )
            for table_name, table_df in batch_tables.items():
                table_write_counts[table_name] += len(table_df)
            return batch_paths

        for line_number, work in iter_works_jsonl(jsonl_path):
            if skipped_records < records_to_skip:
                skipped_records += 1
                if progress_every_batches > 0 and skipped_records % (batch_size * progress_every_batches) == 0:
                    print(
                        f"Skipped {skipped_records:,} records to resume at batch {current_batch_index:,} "
                        f"from {jsonl_path}"
                    )
                continue

            batch_records.append(work)
            total_records += 1

            if max_records is not None and total_records >= max_records:
                latest_output_paths = _flush_batch(batch_records, current_batch_index)
                total_written_batches += 1 if batch_records else 0
                batch_records = []
                break

            if len(batch_records) >= batch_size:
                latest_output_paths = _flush_batch(batch_records, current_batch_index)
                total_written_batches += 1
                if progress_every_batches > 0 and total_written_batches % progress_every_batches == 0:
                    print(
                        f"Processed {total_records:,} new records across {total_written_batches:,} new batches "
                        f"from {jsonl_path}; latest source line {line_number:,}"
                    )
                batch_records = []
                current_batch_index += 1

        if batch_records:
            latest_output_paths = _flush_batch(batch_records, current_batch_index)
            total_written_batches += 1

        return {
            "jsonl_path": jsonl_path,
            "output_dir": output_dir,
            "file_stem": resolved_file_stem,
            "batch_size": batch_size,
            "start_batch_index": start_batch_index,
            "resume": resume,
            "resume_state": resume_state,
            "records_skipped_for_resume": skipped_records,
            "batches_written": total_written_batches,
            "records_processed": total_records,
            "table_row_counts": table_write_counts,
            "latest_output_paths": latest_output_paths,
        }

    return (
        append_normalized_tables_to_existing_parquet,
        build_af_seed_works_table,
        prepare_domain_tables_from_jsonl,
        stream_normalize_jsonl_to_parquet,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 三、如何使用上面的代码骨架

    上面新增的单元目前都只是：

    - 导入辅助库
    - 定义规范化函数
    - 定义 Parquet 写出函数
    - 定义 AF 标签规则函数

    **它们不会自动读取文件，也不会自动执行转换。**

    ### 你后面实际使用时，建议按下面顺序手动调用

    #### 0. 小样本快速检查是可选步骤

    如果你只是想先确认当前 JSONL 的字段结构、作者机构嵌套和摘要还原效果，
    可以手动调用前面的 `data_prepare()`。

    这一步的定位只是：

    - 抽样预览
    - 检查字段映射
    - 看看 `works / authorships / work_institutions` 三张轻量表

    **它不是推荐的全量处理主流程。**

    #### 1. 先准备 AF 种子论文 ID 列表

    例如先整理出：

    - AlphaFold2 核心论文
    - AlphaFold3 核心论文
    - AlphaFold DB 论文

    形成一个 `af_seed_ids` 列表。

    #### 2. 对单个领域 JSONL 做规范化拆表

    你后面可以手动调用：

    ```python
    prepare_domain_tables_from_jsonl(
        jsonl_path="raw_jsonl/domain_structural_biology_2015_2025.jsonl",
        domain_label="structural_biology",
        domain_search_query="your original query",
        af_seed_ids=af_seed_ids,
    )
    ```

    这样会返回一个字典，里面包含：

    - `works`
    - `work_references`
    - `authorships`
    - `work_institutions`
    - `work_topics`
    - `work_concepts`
    - `af_label_evidence`

    #### 3. 再把这些表写到 Parquet

    可以用：

    ```python
    append_normalized_tables_to_existing_parquet(
        tables=tables,
        output_dir="derived_tables",
        file_stem="domain_structural_biology_2015_2025",
    )
    ```

    推荐目录会类似：

    ```text
    derived_tables/
      works/
      work_references/
      authorships/
      work_institutions/
      work_topics/
      work_concepts/
      af_label_evidence/
    ```

    这样后续 DuckDB 可以直接用 glob 读取整批 parquet。

    ### 推荐实践

    - 小规模抽样检查：优先用 Polars
    - 多表 join / 年份聚合 / adoption 对比：优先用 DuckDB
    - 不要把所有领域一次性读进 pandas
    - 尽量把“读取原始 JSONL”与“分析查询”分开

    ### 当前为什么都先只定义、不执行

    因为在 marimo 里，新增含有 I/O 的单元如果立即运行，会直接触发：

    - 读取本地大文件
    - 写出 parquet
    - 可能引发路径不存在、样本文件名错误、内存占用等问题

    所以这里先把**代码骨架和表结构接口固定下来**，等你确认：

    - 实际 JSONL 路径
    - 领域标签命名
    - AF 种子论文列表
    - 输出目录

    之后再单独增加“执行入口”单元会更稳。
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 四、AF seed 示例

    下面给一个最小可用的 AlphaFold seed 模板，方便后续做 reference-based tagging。

    这部分仍然只是**示例模板**：

    - 你可以先手动维护一个 `seed_rows` 风格的列表；
    - 再用前面已经定义好的 `build_af_seed_works_table(...)` 转成表；
    - 需要时再从中抽出 `af_seed_ids`，传给 `prepare_domain_tables_from_jsonl(...)`。

    建议至少维护三类 seed：

    - `alphafold2_core`
    - `alphafold3_core`
    - `alphafold_db`

    如果你后面确认了更准确的 OpenAlex work id，只需要替换下面示例里的 `seed_work_id` 即可。
    """)
    return


@app.cell(hide_code=True)
def _(build_af_seed_works_table):
    af_seed_rows_example = [
        {
            "seed_work_id": "https://openalex.org/w3177828909",
            "seed_type": "alphafold2_core",
            "title": "Highly accurate protein structure prediction with AlphaFold",
        },
        {
            "seed_work_id": "https://openalex.org/w4396721167",
            "seed_type": "alphafold3_core",
            "title": "Accurate structure prediction of biomolecular interactions with AlphaFold 3",
        },
        {
            "seed_work_id": "https://openalex.org/W3211795435",
            "seed_type": "alphafold_db",
            "title": "The AlphaFold Protein Structure Database",
        },
        {
            "seed_work_id": "https://openalex.org/w3202105508",
            "seed_type": "alphafold1_core",
            "title": "Protein complex prediction with AlphaFold-Multimer",
        },
    ]

    af_seed_works_example = build_af_seed_works_table(af_seed_rows_example)
    af_seed_ids_example = af_seed_works_example["seed_work_id"].tolist()

    af_seed_works_example
    return (af_seed_ids_example,)


@app.cell
def _(
    Any,
    Dict,
    List,
    Path,
    af_seed_ids_example,
    append_normalized_tables_to_existing_parquet,
    prepare_domain_tables_from_jsonl,
    stream_normalize_jsonl_to_parquet,
):
    def run_manual_example(
        jsonl_path: str,
        domain_label: str,
        domain_search_query: str,
        output_dir: str = "derived_tables",
        file_stem: str | None = None,
        af_seed_ids: List[str] | None = None,
    ) -> Dict[str, Any]:
        _file_stem = file_stem or Path(jsonl_path).stem

        example_tables = prepare_domain_tables_from_jsonl(
            jsonl_path=jsonl_path,
            domain_label=domain_label,
            domain_search_query=domain_search_query,
            af_seed_ids=af_seed_ids
            if af_seed_ids is not None
            else af_seed_ids_example,
        )

        example_output_paths = append_normalized_tables_to_existing_parquet(
            tables=example_tables,
            output_dir=output_dir,
            file_stem=_file_stem,
        )

        return {
            "tables": example_tables,
            "output_paths": example_output_paths,
        }


    def run_streaming_example(
        jsonl_path: str,
        domain_label: str,
        domain_search_query: str,
        output_dir: str = "derived_tables",
        file_stem: str | None = None,
        af_seed_ids: List[str] | None = None,
        batch_size: int = 5000,
        start_batch_index: int = 1,
        max_records: int | None = None,
        progress_every_batches: int = 10,
        resume: bool = False,
    ) -> Dict[str, Any]:
        return stream_normalize_jsonl_to_parquet(
            jsonl_path=jsonl_path,
            domain_label=domain_label,
            domain_search_query=domain_search_query,
            output_dir=output_dir,
            file_stem=file_stem,
            af_seed_ids=af_seed_ids
            if af_seed_ids is not None
            else af_seed_ids_example,
            batch_size=batch_size,
            start_batch_index=start_batch_index,
            max_records=max_records,
            progress_every_batches=progress_every_batches,
            resume=resume,
        )


    # 小样本全量入口：只适合抽样检查，不适合 35GB 文件
    # run_manual_example(
    #     jsonl_path = "raw_jsonl/domain_structural_biology_2015_2025.jsonl",
    #     domain_label= "structural_biology",
    #     domain_search_query="your original query",
    #     output_dir = "derived_tables",
    #     file_stem = "domain_structural_biology_2015_2025"
    # )

    # 大文件推荐入口：流式分批转换，适合 35GB 级别 JSONL
    # 首次运行建议 resume=False；中断后恢复建议 resume=True
    # run_streaming_example(
    #     jsonl_path="domain_structural_biology_2015_2025.jsonl",
    #     # jsonl_path="data_samples/alphafold_citing_works_sample.jsonl",
    #     domain_label="structural_biology",
    #     domain_search_query='"structural biology" OR protein structure OR cryo-EM OR crystallography OR NMR structure',
    #     output_dir="derived_tables",
    #     file_stem="domain_structural_biology_2015_2025",
    #     batch_size=50000,
    #     # max_records=50000,
    #     progress_every_batches=50,
    #     resume=True,
    # )

    # run_streaming_example(
    #     jsonl_path="raw_jsonl/domain_drug_discovery_medicinal_chemistry_2015_2025.jsonl",
    #     # jsonl_path="data_samples/alphafold_citing_works_sample.jsonl",
    #     domain_label="drug_discovery_medicinal_chemistry",
    #     domain_search_query='https://openalex.org/concepts/C74187038',
    #     output_dir="derived_tables",
    #     file_stem="domain_drug_discovery_medicinal_chemistry_2015_2025",
    #     batch_size=10000,
    #     # max_records=50000,
    #     progress_every_batches=10,
    #     resume=True,
    # )

    # run_streaming_example(
    #     jsonl_path="raw_jsonl/domain_protein_structure_2015_2025.jsonl",
    #     domain_label="protein_structure",
    #     domain_search_query='https://openalex.org/concepts/C47701112',
    #     output_dir="derived_tables",
    #     file_stem="domain_protein_structure_2015_2025",
    #     batch_size=10000,
    #     # max_records=50000,
    #     progress_every_batches=10,
    #     resume=False,
    # )

    # run_streaming_example(
    #     jsonl_path="raw_jsonl/domain_bioinformatics_2015_2025.jsonl",
    #     domain_label="bioinformatics",
    #     domain_search_query='https://openalex.org/concepts/C60644358',
    #     output_dir="derived_tables",
    #     file_stem="domain_bioinformatics_2015_2025",
    #     batch_size=100000,
    #     # max_records=50000,
    #     progress_every_batches=50,
    #     resume=False,
    # )
    return (run_streaming_example,)


@app.cell
def _(Any, Dict, List, Path, af_seed_ids_example, run_streaming_example):
    # jsonl 批量入口：遍历目录下所有 .jsonl 文件并逐个调用 run_streaming_example（默认不执行）
    # 用法：
    # 1. 修改 jsonl_root_dir 为你的目录
    # 2. 如需真正执行，把 dry_run 改为 False，或取消最下面的函数调用注释
    # 3. domain_label 默认使用文件名 stem；domain_search_query 默认留空，可按需自定义映射

    def run_streaming_example_for_all_jsonl(
        jsonl_root_dir: str,
        output_dir: str = "derived_tables",
        af_seed_ids: List[str] | None = None,
        batch_size: int = 100000,
        start_batch_index: int = 1,
        max_records: int | None = None,
        progress_every_batches: int = 50,
        resume: bool = False,
        recursive: bool = True,
        dry_run: bool = True,
    ) -> List[Dict[str, Any]]:
        _root_path = Path(jsonl_root_dir)
        _glob_pattern = "**/*.jsonl" if recursive else "*.jsonl"
        _jsonl_paths = sorted(_root_path.glob(_glob_pattern))

        _results = []
        for _jsonl_path in _jsonl_paths:
            _file_stem = _jsonl_path.stem
            _domain_label = _file_stem.replace("domain_", "").replace("_2015_2025", "")
            _domain_search_query = ""

            _job_kwargs = {
                "jsonl_path": str(_jsonl_path),
                "domain_label": _domain_label,
                "domain_search_query": _domain_search_query,
                "output_dir": output_dir,
                "file_stem": _file_stem,
                "af_seed_ids": af_seed_ids if af_seed_ids is not None else af_seed_ids_example,
                "batch_size": batch_size,
                "start_batch_index": start_batch_index,
                "max_records": max_records,
                "progress_every_batches": progress_every_batches,
                "resume": resume,
            }

            if dry_run:
                _results.append({
                    "status": "planned",
                    **_job_kwargs,
                })
            else:
                _results.append(run_streaming_example(**_job_kwargs))

        return _results


    # 不自动执行；如需预览将要处理的文件，可手动调用：
    # run_streaming_example_for_all_jsonl(
    #     jsonl_root_dir="raw_jsonl/Pharmacology_Toxicology_and_Pharmaceutics",
    #     output_dir="derived_tables",
    #     batch_size=1000,
    #     progress_every_batches=50,
    #     resume=False,
    #     recursive=True,
    #     dry_run=True,
    # )

    # 如需真正批量执行，请手动取消下面注释并将 dry_run=False：
    # run_streaming_example_for_all_jsonl(
    #     jsonl_root_dir="raw_jsonl/Biochemistry_Genetics_and_Molecular_Biology",
    #     output_dir="derived_tables",
    #     batch_size=100000,
    #     progress_every_batches=50,
    #     resume=True,
    #     recursive=True,
    #     dry_run=False,
    # )

    # run_streaming_example_for_all_jsonl(
    #     jsonl_root_dir="raw_jsonl/Immunology_and_Microbiology",
    #     output_dir="derived_tables",
    #     batch_size=100000,
    #     progress_every_batches=50,
    #     resume=False,
    #     recursive=True,
    #     dry_run=False,
    # )

    # run_streaming_example_for_all_jsonl(
    #     jsonl_root_dir="raw_jsonl/Pharmacology_Toxicology_and_Pharmaceutics",
    #     output_dir="derived_tables",
    #     batch_size=100000,
    #     progress_every_batches=50,
    #     resume=False,
    #     recursive=True,
    #     dry_run=False,
    # )
    return


@app.cell
def _(Path, pd):
    _toxicology_parquet_root = Path("derived_tables")

    _toxicology_table_dirs = {
        _table_dir.name: sorted(_table_dir.glob("*.parquet"))
        for _table_dir in _toxicology_parquet_root.iterdir()
        if _table_dir.is_dir() and list(_table_dir.glob("*.parquet"))
    }

    print("===== PARQUET DATA PATH STRUCTURE =====")
    for _table_name, _parquet_files in sorted(_toxicology_table_dirs.items()):
        print(f"\n[{_table_name}]")
        print(f"directory: {_toxicology_parquet_root / _table_name}")
        print(f"n_parquet_files: {len(_parquet_files)}")
        if _parquet_files:
            print("sample_files:")
            for _sample_path in _parquet_files[:5]:
                print(f"  - {_sample_path}")
            if len(_parquet_files) > 5:
                print(f"  - ... ({len(_parquet_files) - 5} more files)")

    _toxicology_table_summaries = {}
    for _table_name, _parquet_files in sorted(_toxicology_table_dirs.items()):
        if not _parquet_files:
            continue

        _sample_path = _parquet_files[0]
        _sample_df = pd.read_parquet(_sample_path)

        _schema_df = pd.DataFrame({
            "column_name": _sample_df.columns,
            "dtype": _sample_df.dtypes.astype(str).values,
            "non_null_count_in_sample": _sample_df.notna().sum().values,
            "sample_value": [
                _sample_df[_col].dropna().iloc[0]
                if len(_sample_df[_col].dropna()) > 0
                else None
                for _col in _sample_df.columns
            ],
        })

        _toxicology_table_summaries[_table_name] = {
            "directory": str(_toxicology_parquet_root / _table_name),
            "n_parquet_files": len(_parquet_files),
            "sample_file": str(_sample_path),
            "sample_shape": _sample_df.shape,
            "columns": list(_sample_df.columns),
            "schema": _schema_df,
            "head": _sample_df.head(5),
        }

    print("\n===== TABLE DATA STRUCTURES =====")
    for _table_name, _summary in _toxicology_table_summaries.items():
        print(f"\n===== {_table_name} =====")
        print(f"directory: {_summary['directory']}")
        print(f"n_parquet_files: {_summary['n_parquet_files']}")
        print(f"sample_file: {_summary['sample_file']}")
        print(f"sample_shape: {_summary['sample_shape']}")
        print("columns:")
        for _col in _summary["columns"]:
            print(f"  - {_col}")
        print("\nschema:")
        print(_summary["schema"].to_string(index=False))
        print("\nsample_rows:")
        print(_summary["head"])

    _toxicology_table_summaries
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 五、后续在 DuckDB 中的分析模板

    当你把规范化表按目录写成 parquet 之后，后续分析建议放到单独的 notebook 或脚本里完成。

    例如，你可以在 DuckDB 中按 glob 方式直接读取：

    ```sql
    SELECT *
    FROM read_parquet('derived_tables/works/*.parquet')
    LIMIT 20
    ```

    ### 1. 年度产出趋势

    可基于 `works` 表统计：

    - 每年论文数
    - 每年 AF-related 论文数
    - 每年 AF 占比

    示意：

    ```sql
    SELECT
      publication_year,
      COUNT(*) AS n_works,
      SUM(CASE WHEN is_alphafold_related THEN 1 ELSE 0 END) AS n_af_works,
      AVG(CASE WHEN is_alphafold_related THEN 1.0 ELSE 0.0 END) AS af_share
    FROM read_parquet('derived_tables/works/*.parquet')
    GROUP BY 1
    ORDER BY 1
    ```

    ### 2. AF / non-AF 的国家分布

    可基于 `works` 与 `work_institutions` 联结统计：

    - 哪些国家最早采用 AF
    - 不同国家 AF 论文占比
    - adoption 是否集中在少数国家

    示意：

    ```sql
    SELECT
      wi.country_code,
      w.publication_year,
      COUNT(DISTINCT w.work_id) AS n_works,
      SUM(CASE WHEN w.is_alphafold_related THEN 1 ELSE 0 END) AS n_af_works
    FROM read_parquet('derived_tables/works/*.parquet') AS w
    LEFT JOIN read_parquet('derived_tables/work_institutions/*.parquet') AS wi
      ON w.work_id = wi.work_id
    GROUP BY 1, 2
    ORDER BY 2, 4 DESC
    ```

    ### 3. 子领域 / topic adoption

    可基于 `works` 与 `work_topics` 联结统计：

    - 哪些 topic 最早采用 AF
    - 哪些 topic adoption 最快
    - 哪些 topic adoption 较弱

    示意：

    ```sql
    SELECT
      wt.topic_display_name,
      w.publication_year,
      COUNT(DISTINCT w.work_id) AS n_works,
      AVG(CASE WHEN w.is_alphafold_related THEN 1.0 ELSE 0.0 END) AS af_share
    FROM read_parquet('derived_tables/works/*.parquet') AS w
    LEFT JOIN read_parquet('derived_tables/work_topics/*.parquet') AS wt
      ON w.work_id = wt.work_id
    GROUP BY 1, 2
    ORDER BY 2, 4 DESC
    ```

    ### 4. 引用结构分析

    可基于 `work_references` 表统计：

    - 每篇论文引用多少文献
    - AF 论文是否引用更多文献
    - 是否引用 AF 种子论文
    - pre/post 的 knowledge base 是否发生变化

    示意：

    ```sql
    SELECT
      w.publication_year,
      w.is_alphafold_related,
      COUNT(r.referenced_work_id) AS n_reference_edges
    FROM read_parquet('derived_tables/works/*.parquet') AS w
    LEFT JOIN read_parquet('derived_tables/work_references/*.parquet') AS r
      ON w.work_id = r.source_work_id
    GROUP BY 1, 2
    ORDER BY 1, 2
    ```

    ### 5. 团队结构与合作模式

    可基于 `authorships` 与 `work_institutions` 统计：

    - 团队规模
    - 机构数
    - 国际合作比例
    - 对应作者模式

    ### 推荐实践

    建议把后续分析拆到单独 notebook，例如：

    - `02_duckdb_analysis.py`
    - `03_af_label_validation.py`
    - `04_topic_diffusion.py`

    这样这份 `01_data_prepare.py` 就专注在：

    - 读取原始 OpenAlex JSONL
    - 规范化拆表
    - 写出 parquet
    - 固定 AF 标签接口

    而不和后续分析逻辑混在一起。
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 六、数据分析

    AlphaFold的主要的八大领域:

    基础研究领域
    - Structural Biology
    - Computational Biology / Bioinformatics
    - Biochemistry / Molecular Biology
    - Protein Science

    应用研究领域
    - Drug Discovery / Medicinal Chemistry
    - Chemical Biology
    - Microbiology / Virology / Immunology
    - Enzymology / Protein Engineering / Synthetic Biology

    目前抓取的数据为2015-2025年, 包含以下领域:
    1. Structural Biology - 结构生物学 2399800篇研究
    2. Drug Discovery - 新药研发 - 79664篇研究
    3. Protein Structure - 蛋白质结构 - 36047篇研究
    4. Bioinformatics - 生物信息 -703832篇研究

    后续会逐步覆盖尽可能多的相关性强的领域.

    下面会进行以下几个角度的分析:
    1. 团队规模
       - 论文的平均作者数量逐年趋势, 总/Non-AF/AF
       - top5 国家的分别变化趋势
    2. 机构合作
       - 论文的平均机构数量逐年趋势, 总/Non-AF/AF
       - top5 国家的分别变化趋势
    3. 国际合作
       - 论文的跨国合作数量逐年趋势, 总/Non-AF/AF
       - 论文的跨国引用数量逐年趋势
       - top5 国家的分别变化趋势
    4. 地理分布
       - AF数量分布图, 加数字
       - AF占比分布图, 加数字
    5. AlphaFold 不同国家的 adoption 分析
       - 热力图 调整图片高度

    以上这些可分析会结合:
    1. AF vs Non-AF 对比分析
    2. 2015-2025逐年趋势分析
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # AlphaFold and the Reconfiguration of the Global Geography of Scientific Production

    本分析从地理分布的角度，系统考察 AlphaFold 是否改变了科研生产的全球空间格局。整套叙事按照论文式逻辑组织为四个部分：

    ## Part 1. Global spatial distribution of scientific production
    回答：**AlphaFold 相关科研主要生产在哪里？哪些国家构成全球知识生产中心？**

    ## Part 2. Spatial diffusion of AlphaFold adoption
    回答：**AlphaFold 的国际扩散是同步发生，还是沿着核心国家到外围国家的路径推进？**

    ## Part 3. Spatial inequality and concentration
    回答：**AlphaFold 相关研究是否比一般科研更集中于少数国家，从而强化空间不平等？**

    ## Part 4. Has the global spatial structure been reconfigured?
    回答：**这些变化究竟意味着旧有格局被重构，还是只是原有中心—外围体系中的扩散与放大？**

    Part 1：全球空间分布
    Part 2：adoption 扩散
    Part 3：空间不平等
    Part 4：是否发生重构

    下面按照这四个部分展开。
    """)
    return


@app.cell(hide_code=True)
def _():
    import altair as alt
    import duckdb

    return alt, duckdb


@app.cell(hide_code=True)
def _():
    import plotly.graph_objects as go
    import numpy as np

    return go, np


@app.cell
def _():
    import matplotlib.pyplot as plt

    return (plt,)


@app.cell
def _():
    import plotly.express as px

    return (px,)


@app.cell(hide_code=True)
def _(Path, duckdb):
    analysis_duckdb = duckdb.connect()
    works_glob = "derived_tables/works/*.parquet"
    work_institutions_glob = "derived_tables/work_institutions/*.parquet"
    work_topics_glob = "derived_tables/work_topics/*.parquet"
    analysis_ready = (
        len(list(Path("derived_tables/works").glob("*.parquet"))) > 0
        and len(list(Path("derived_tables/work_institutions").glob("*.parquet"))) > 0
        and len(list(Path("derived_tables/work_topics").glob("*.parquet"))) > 0
    )
    return (
        analysis_duckdb,
        analysis_ready,
        work_institutions_glob,
        work_topics_glob,
        works_glob,
    )


@app.cell(hide_code=True)
def _(analysis_duckdb, analysis_ready, mo, works_glob):
    mo.stop(
        not analysis_ready,
        mo.md(r"""
        尚未检测到 `derived_tables/works/`、`derived_tables/work_institutions/` 或 `derived_tables/work_topics/` 下的 parquet 文件。

        请先运行前面的规范化拆表与写盘流程，再查看本分析区。
        """),
    )

    annual_trend_df = analysis_duckdb.execute(f"""
    SELECT
      publication_year,
      COUNT(*) AS n_works,
      SUM(CASE WHEN is_alphafold_related THEN 1 ELSE 0 END) AS n_af_works,
      AVG(CASE WHEN is_alphafold_related THEN 1.0 ELSE 0.0 END) AS af_share
    FROM read_parquet('{works_glob}')
    GROUP BY 1
    ORDER BY 1
    """).df()

    annual_trend_df
    return (annual_trend_df,)


@app.cell(hide_code=True)
def _(alt, annual_trend_df):
    annual_trend_long_df = annual_trend_df.melt(
        id_vars=["publication_year", "af_share"],
        value_vars=["n_works", "n_af_works"],
        var_name="series",
        value_name="count",
    )

    annual_trend_line_chart = alt.Chart(annual_trend_long_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year"),
        y=alt.Y("count:Q", title="Number of works"),
        color=alt.Color(
            "series:N",
            title="Series",
            scale=alt.Scale(
                domain=["n_works", "n_af_works"],
                range=["#4C78A8", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("count:Q", title="Count"),
        ],
    ).properties(
        title="Annual works vs AlphaFold-related works",
        width=700,
        height=320,
    )

    annual_trend_line_chart
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, analysis_ready, mo, work_institutions_glob, works_glob):
    mo.stop(
        not analysis_ready,
        mo.md(r"""
        尚未检测到 `derived_tables/works/`、`derived_tables/work_institutions/` 或 `derived_tables/work_topics/` 下的 parquet 文件。

        请先运行前面的规范化拆表与写盘流程，再查看本分析区。
        """),
    )

    country_trend_df = analysis_duckdb.execute(f"""
    SELECT
      wi.country_code,
      w.publication_year,
      COUNT(DISTINCT w.work_id) AS n_works,
      SUM(CASE WHEN w.is_alphafold_related THEN 1 ELSE 0 END) AS n_af_works,
      AVG(CASE WHEN w.is_alphafold_related THEN 1.0 ELSE 0.0 END) AS af_share
    FROM read_parquet('{works_glob}') AS w
    LEFT JOIN read_parquet('{work_institutions_glob}') AS wi
      ON w.work_id = wi.work_id
    WHERE wi.country_code IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 2, 4 DESC
    """).df()

    country_trend_df
    return (country_trend_df,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Part 2. Spatial diffusion of AlphaFold adoption

    这一部分关注的是 AlphaFold adoption 的扩散顺序与时间梯度。

    阅读顺序建议是：

    1. 先看 country heatmap，识别 adoption 在年份与国家之间的扩散轮廓；
    2. 再看 adoption timing world map，识别哪些国家最早进入 adoption；
    3. 最后结合不同年份的世界地图，观察 adoption 强度与 AF 论文数量在全球范围内如何扩展。
    """)
    return


@app.cell(hide_code=True)
def _(alt, country_trend_df):
    country_heatmap = alt.Chart(country_trend_df).mark_rect().encode(
        x=alt.X("publication_year:O", title="Publication year"),
        y=alt.Y(
            "country_code:N",
            title="Country",
            sort=alt.EncodingSortField(field="af_share", op="max", order="descending"),
        ),
        color=alt.Color("af_share:Q", title="AF share", scale=alt.Scale(scheme="blues")),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("publication_year:Q", title="Publication year"),
            alt.Tooltip("n_works:Q", title="Number of works"),
            alt.Tooltip("n_af_works:Q", title="AF-related works"),
            alt.Tooltip("af_share:Q", title="AF share", format=".2%"),
        ],
    ).properties(
        title="Country adoption heatmap by year",
        width=700,
        height=1800,
    )

    country_heatmap
    return


@app.cell(hide_code=True)
def _(country_trend_df, px):
    country_heatmap_top30_base_df = country_trend_df.copy()
    country_heatmap_top30_rank_df = country_heatmap_top30_base_df.groupby("country_code", as_index=False).agg({
        "n_af_works": "sum",
        "af_share": "max",
    })
    country_heatmap_top30_codes = country_heatmap_top30_rank_df.sort_values(
        ["n_af_works", "af_share"],
        ascending=[False, False],
    ).head(30)["country_code"].tolist()

    country_heatmap_top30_df = country_heatmap_top30_base_df[
        country_heatmap_top30_base_df["country_code"].isin(country_heatmap_top30_codes)
    ].copy()
    country_heatmap_top30_pivot_df = country_heatmap_top30_df.pivot_table(
        index="country_code",
        columns="publication_year",
        values="af_share",
        fill_value=0,
    )
    country_heatmap_top30_order = country_heatmap_top30_df.groupby("country_code")["af_share"].max().sort_values(ascending=False).index.tolist()
    country_heatmap_top30_pivot_df = country_heatmap_top30_pivot_df.loc[country_heatmap_top30_order]

    country_heatmap_top30_plotly = px.imshow(
        country_heatmap_top30_pivot_df,
        aspect="auto",
        color_continuous_scale=[
            [0.0, "#f7fbff"],
            [0.2, "#c6dbef"],
            [0.4, "#6baed6"],
            [0.6, "#3182bd"],
            [0.8, "#08519c"],
            [1.0, "#67001f"],
        ],
        labels={"x": "Publication year", "y": "Country", "color": "AF share"},
        title="Top 30 countries adoption heatmap by year (Plotly)",
    )
    country_heatmap_top30_plotly.update_traces(
        hovertemplate="Country: %{y}<br>Publication year: %{x}<br>AF share: %{z:.2%}<extra></extra>"
    )
    country_heatmap_top30_plotly.update_layout(
        width=900,
        height=900,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    country_heatmap_top30_plotly
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Insights from the top 30 Plotly adoption heatmap

    这张图把国家范围收缩到 **AF 相关产出最高的 30 个国家**，因此比上面的全体国家 heatmap 更适合观察 AlphaFold adoption 的核心扩散轮廓。

    可以从这张图里概括出几个数据特征：

    - **adoption 的明显抬升主要发生在 2021 年之后。** 在此之前，大多数 top 30 国家的 `af_share` 都接近于零；2021 年后，越来越多国家开始出现连续的非零 adoption。
    - **不同国家的 adoption 强度差异非常明显。** 即使都进入了 top 30，不同国家在颜色深浅上的差异仍然很大，这说明 AlphaFold 的扩散并不是“进入 top 30 国家后就同步增强”，而是存在明显的强弱分化。
    - **扩散具有明显的时间梯度。** 有些国家较早出现持续性的较高 `af_share`，而另一些国家则是在后续几年才逐步抬升，这支持了前面关于“分层扩散”而不是“同步扩散”的判断。
    - **高产出国家并不一定对应最高 adoption share。** 这张图的国家样本是按 AF 相关产出筛出来的，但颜色反映的是 `af_share`。因此它特别能帮助区分两类国家：一类是 AF 总量很高的核心生产国，另一类是 AF 占比上升更快的高 adoption 国家。
    - **到后期虽然更多国家进入 adoption，但强度收敛并不充分。** 也就是说，扩散范围确实扩大了，但 top 30 国家之间的 adoption 水平并没有完全趋同，说明 AlphaFold 的国际扩散伴随着持续的国家差异，而不是快速均衡化。

    因此，这张 top 30 heatmap 最重要的意义在于：它更清楚地展示了 **AlphaFold 在核心科研国家中的扩散不是均匀推进的，而是沿着不同国家的能力、吸收速度与研究结构差异，呈现出有先后、有强弱的 adoption 路径。**
    """)
    return


@app.cell(hide_code=True)
def _(alt, country_code_numeric_map, country_trend_df):
    country_first_adoption_df = country_trend_df[
        country_trend_df["af_share"] > 0
    ].groupby("country_code", as_index=False)["publication_year"].min()
    country_first_adoption_df["country_code"] = country_first_adoption_df["country_code"].str.upper()
    country_first_adoption_df["id"] = country_first_adoption_df["country_code"].map(country_code_numeric_map)
    country_first_adoption_df = country_first_adoption_df.dropna(subset=["id"]).copy()
    country_first_adoption_df["id"] = country_first_adoption_df["id"].astype(int)

    country_first_adoption_map_chart = alt.Chart(
        alt.topo_feature("https://vega.github.io/vega-datasets/data/world-110m.json", "countries")
    ).mark_geoshape(stroke="white", strokeWidth=0.5).encode(
        color=alt.Color(
            "publication_year:Q",
            title="First adoption year",
            scale=alt.Scale(scheme="blues", reverse=True, domain=[2021, 2025]),
        ),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("publication_year:Q", title="First adoption year", format="d"),
        ],
    ).transform_lookup(
        lookup="id",
        from_=alt.LookupData(
            country_first_adoption_df,
            key="id",
            fields=["country_code", "publication_year"],
        ),
    ).project(
        type="equalEarth"
    ).properties(
        title="World map of AlphaFold adoption timing",
        width=900,
        height=450,
    )

    country_first_adoption_map_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(f"""
    ### Insights from the country adoption heatmap

    结合上面的 **adoption timing world map** 和这张 **country heatmap**，可以读出几个更准确的结论：

    - **真正具有分析意义的跨国 adoption 起点主要出现在 2021 年。** 从 timing map 看，最早出现 adoption 的国家主要集中在 2021；这说明 AlphaFold 从方法发布走向各国研究使用之间，存在一个明显的扩散滞后期。
    - **2022–2023 是第一轮全球扩散加速阶段。** heatmap 中越来越多国家在这两年开始出现非零 `af_share`，而 timing map 也显示大量国家的首次 adoption 年份集中在这一区间，说明这是 AlphaFold 从少数领先国家扩散到更广泛国家群体的关键窗口。
    - **2024–2025 仍然在扩散，但不是均匀扩散。** heatmap 的颜色深浅差异表明，不同国家 adoption 强度差别仍然很大；timing map 则进一步说明，很多国家进入 adoption 的时间并不一致，而是存在明显的先后梯度。
    - **全球扩散呈现“分层扩散”特征。** 也就是说，AlphaFold adoption 并不是所有国家在同一年同时启动，而是先由少数研究能力更强、方法吸收更快的国家率先采用，再逐步向其他国家扩展。
    - **adoption 时间早，不一定代表 adoption 强度最高。** timing map 反映的是“何时开始采用”，heatmap 反映的是“采用占比有多高”；两张图结合起来看，可以区分“先采用的国家”和“采用强度后来提升更快的国家”。

    因此，这部分图最重要的结论是：**AlphaFold 的国际扩散并不是自 2019 年立刻全球展开，而是在 2021 年后才表现出明确的跨国 adoption，并且这种扩散具有明显的时间梯度与国家分层特征。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    country_map_year_slider = mo.ui.slider(
        2015,
        2025,
        value=2025,
        step=1,
        label="Select year for world map",
    )

    country_map_year_slider
    return (country_map_year_slider,)


@app.cell(hide_code=True)
def _():
    country_code_numeric_map = {
        "AE": 784,
        "AR": 32,
        "AT": 40,
        "AU": 36,
        "BD": 50,
        "BE": 56,
        "BG": 100,
        "BR": 76,
        "CA": 124,
        "CH": 756,
        "CL": 152,
        "CN": 156,
        "CO": 170,
        "CZ": 203,
        "DE": 276,
        "DK": 208,
        "EG": 818,
        "ES": 724,
        "FI": 246,
        "FR": 250,
        "GB": 826,
        "GH": 288,
        "GR": 300,
        "HK": 344,
        "HR": 191,
        "HU": 348,
        "ID": 360,
        "IE": 372,
        "IL": 376,
        "IN": 356,
        "IR": 364,
        "IT": 380,
        "JP": 392,
        "KE": 404,
        "KR": 410,
        "MX": 484,
        "MY": 458,
        "NG": 566,
        "NL": 528,
        "NO": 578,
        "NZ": 554,
        "PE": 604,
        "PH": 608,
        "PK": 586,
        "PL": 616,
        "PT": 620,
        "RO": 642,
        "RU": 643,
        "SA": 682,
        "SE": 752,
        "SG": 702,
        "TH": 764,
        "TR": 792,
        "TW": 158,
        "UA": 804,
        "US": 840,
        "VN": 704,
        "ZA": 710,
    }

    country_code_numeric_map
    return (country_code_numeric_map,)


@app.cell(hide_code=True)
def _(
    alt,
    country_code_numeric_map,
    country_map_year_slider,
    country_trend_df,
):
    country_map_year_df = country_trend_df[
        country_trend_df["publication_year"] == country_map_year_slider.value
    ].dropna(subset=["country_code"]).copy()
    country_map_year_df["country_code"] = country_map_year_df["country_code"].str.upper()
    country_map_year_df["id"] = country_map_year_df["country_code"].map(country_code_numeric_map)
    country_map_year_df = country_map_year_df.dropna(subset=["id"]).copy()
    country_map_year_df["id"] = country_map_year_df["id"].astype(int)

    country_world_map_chart = alt.Chart(
        alt.topo_feature("https://vega.github.io/vega-datasets/data/world-110m.json", "countries")
    ).mark_geoshape(stroke="white", strokeWidth=0.5).encode(
        color=alt.Color("af_share:Q", title="AF share", scale=alt.Scale(scheme="blues")),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("n_works:Q", title="Number of works"),
            alt.Tooltip("n_af_works:Q", title="AF-related works"),
            alt.Tooltip("af_share:Q", title="AF share", format=".2%"),
        ],
    ).transform_lookup(
        lookup="id",
        from_=alt.LookupData(
            country_map_year_df,
            key="id",
            fields=["country_code", "n_works", "n_af_works", "af_share"],
        ),
    ).project(
        type="equalEarth"
    ).properties(
        title=f"World map of AF adoption in {country_map_year_slider.value}",
        width=900,
        height=450,
    )

    country_world_map_chart
    return (country_map_year_df,)


@app.cell(hide_code=True)
def _(alt, country_map_year_df, country_map_year_slider):
    country_world_count_map_chart = alt.Chart(
        alt.topo_feature("https://vega.github.io/vega-datasets/data/world-110m.json", "countries")
    ).mark_geoshape(stroke="white", strokeWidth=0.5).encode(
        color=alt.Color("n_af_works:Q", title="AF-related works", scale=alt.Scale(scheme="oranges")),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("n_works:Q", title="Number of works"),
            alt.Tooltip("n_af_works:Q", title="AF-related works"),
            alt.Tooltip("af_share:Q", title="AF share", format=".2%"),
        ],
    ).transform_lookup(
        lookup="id",
        from_=alt.LookupData(
            country_map_year_df,
            key="id",
            fields=["country_code", "n_works", "n_af_works", "af_share"],
        ),
    ).project(
        type="equalEarth"
    ).properties(
        title=f"World map of AF-related works in {country_map_year_slider.value}",
        width=900,
        height=450,
    )

    country_world_count_label_chart = alt.Chart(
        alt.topo_feature("https://vega.github.io/vega-datasets/data/world-110m.json", "countries")
    ).mark_text(fontSize=10, color="black").encode(
        longitude="properties.longitude:Q",
        latitude="properties.latitude:Q",
        text=alt.Text("n_af_works:Q", format=".0f"),
    ).transform_lookup(
        lookup="id",
        from_=alt.LookupData(
            country_map_year_df[country_map_year_df["n_af_works"] > 0],
            key="id",
            fields=["n_af_works"],
        ),
    )

    country_world_count_map_chart + country_world_count_label_chart
    return


@app.cell(hide_code=True)
def _(alt, country_code_numeric_map, country_trend_df):
    country_cumulative_af_df = country_trend_df.groupby("country_code", as_index=False)["n_af_works"].sum()
    country_cumulative_af_df["country_code"] = country_cumulative_af_df["country_code"].str.upper()
    country_cumulative_af_df["id"] = country_cumulative_af_df["country_code"].map(country_code_numeric_map)
    country_cumulative_af_df = country_cumulative_af_df.dropna(subset=["id"]).copy()
    country_cumulative_af_df["id"] = country_cumulative_af_df["id"].astype(int)

    country_cumulative_af_map_chart = alt.Chart(
        alt.topo_feature("https://vega.github.io/vega-datasets/data/world-110m.json", "countries")
    ).mark_geoshape(stroke="white", strokeWidth=0.5).encode(
        color=alt.Color("n_af_works:Q", title="Cumulative AF-related works", scale=alt.Scale(scheme="reds")),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("n_af_works:Q", title="Cumulative AF-related works", format=".0f"),
        ],
    ).transform_lookup(
        lookup="id",
        from_=alt.LookupData(
            country_cumulative_af_df,
            key="id",
            fields=["country_code", "n_af_works"],
        ),
    ).project(
        type="equalEarth"
    ).properties(
        title="World map of cumulative AF-related works",
        width=900,
        height=450,
    )

    country_cumulative_af_map_chart
    return


@app.cell
def _(alt, country_code_numeric_map, country_trend_df):
    country_cumulative_non_af_df = country_trend_df.copy()
    country_cumulative_non_af_df["n_non_af_works"] = (
        country_cumulative_non_af_df["n_works"] - country_cumulative_non_af_df["n_af_works"]
    )
    country_cumulative_non_af_df = country_cumulative_non_af_df.groupby(
        "country_code", as_index=False
    )["n_non_af_works"].sum()
    country_cumulative_non_af_df["country_code"] = country_cumulative_non_af_df["country_code"].str.upper()
    country_cumulative_non_af_df["id"] = country_cumulative_non_af_df["country_code"].map(country_code_numeric_map)
    country_cumulative_non_af_df = country_cumulative_non_af_df.dropna(subset=["id"]).copy()
    country_cumulative_non_af_df["id"] = country_cumulative_non_af_df["id"].astype(int)

    country_cumulative_non_af_map_chart = alt.Chart(
        alt.topo_feature("https://vega.github.io/vega-datasets/data/world-110m.json", "countries")
    ).mark_geoshape(stroke="white", strokeWidth=0.5).encode(
        color=alt.Color("n_non_af_works:Q", title="Cumulative Non-AF works", scale=alt.Scale(scheme="greys")),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("n_non_af_works:Q", title="Cumulative Non-AF works", format=".0f"),
        ],
    ).transform_lookup(
        lookup="id",
        from_=alt.LookupData(
            country_cumulative_non_af_df,
            key="id",
            fields=["country_code", "n_non_af_works"],
        ),
    ).project(
        type="equalEarth"
    ).properties(
        title="World map of cumulative Non-AF works",
        width=900,
        height=450,
    )

    country_cumulative_non_af_map_chart
    return


@app.cell(hide_code=True)
def _(mo):
    country_year_slider = mo.ui.slider(
        2015,
        2025,
        value=2025,
        step=1,
        label="Select year for country ranking",
    )

    country_year_slider
    return (country_year_slider,)


@app.cell(hide_code=True)
def _(alt, country_trend_df, country_year_slider):
    country_selected_year_df = country_trend_df[
        country_trend_df["publication_year"] == country_year_slider.value
    ].sort_values("n_af_works", ascending=False).head(15)

    country_latest_bar_chart = alt.Chart(country_selected_year_df).mark_bar().encode(
        x=alt.X("n_af_works:Q", title="AF-related works"),
        y=alt.Y("country_code:N", sort="-x", title="Country"),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("publication_year:Q", title="Publication year"),
            alt.Tooltip("n_works:Q", title="Number of works"),
            alt.Tooltip("n_af_works:Q", title="AF-related works"),
            alt.Tooltip("af_share:Q", title="AF share", format=".2%"),
        ],
    ).properties(
        title=f"Top countries by AF-related output in {country_year_slider.value}",
        width=700,
        height=420,
    )

    country_latest_bar_chart
    return (country_selected_year_df,)


@app.cell(hide_code=True)
def _(alt, country_selected_year_df, country_trend_df):
    country_top10_codes = country_selected_year_df["country_code"].tolist()
    country_top10_trend_df = country_trend_df[
        country_trend_df["country_code"].isin(country_top10_codes)
    ]

    country_top10_line_chart = alt.Chart(country_top10_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year"),
        y=alt.Y("n_af_works:Q", title="AF-related works"),
        color=alt.Color("country_code:N", title="Country"),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("publication_year:Q", title="Publication year"),
            alt.Tooltip("n_works:Q", title="Number of works"),
            alt.Tooltip("n_af_works:Q", title="AF-related works"),
            alt.Tooltip("af_share:Q", title="AF share", format=".2%"),
        ],
    ).properties(
        title=f"Top 10 countries by AF-related output in 2015-2025: trend over time",
        width=700,
        height=420,
    )

    country_top10_line_chart
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, analysis_ready, mo, work_topics_glob, works_glob):
    mo.stop(
        not analysis_ready,
        mo.md(r"""
        尚未检测到 `derived_tables/works/`、`derived_tables/work_institutions/` 或 `derived_tables/work_topics/` 下的 parquet 文件。

        请先运行前面的规范化拆表与写盘流程，再查看本分析区。
        """),
    )

    topic_trend_df = analysis_duckdb.execute(f"""
    SELECT
      wt.topic_display_name,
      w.publication_year,
      COUNT(DISTINCT w.work_id) AS n_works,
      AVG(CASE WHEN w.is_alphafold_related THEN 1.0 ELSE 0.0 END) AS af_share
    FROM read_parquet('{works_glob}') AS w
    LEFT JOIN read_parquet('{work_topics_glob}') AS wt
      ON w.work_id = wt.work_id
    WHERE wt.topic_display_name IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 2, 4 DESC
    """).df()

    topic_trend_df
    return (topic_trend_df,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Part 1. Global spatial distribution of scientific production

    这一部分从总体产出、国家排名和全球地图三个层次，描述 AlphaFold 相关科研生产的空间中心。

    阅读顺序建议是：

    1. 先看总体年度趋势，理解 AF 相关研究何时显著增长；
    2. 再看国家排名与 top countries trend，识别主要知识生产中心；
    3. 最后看世界地图，观察数量分布与占比分布在全球范围内的空间差异。
    """)
    return


@app.cell(hide_code=True)
def _(alt, annual_trend_df, country_trend_df, mo, topic_trend_df):
    annual_chart = alt.Chart(annual_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("n_af_works:Q", title="AF-related works"),
        tooltip=["publication_year", "n_works", "n_af_works", "af_share"],
    ).properties(
        title="Annual AF-related output trend",
        width=380,
        height=260,
    )

    country_latest = country_trend_df.sort_values(
        ["publication_year", "n_af_works"], ascending=[False, False]
    ).drop_duplicates(subset=["country_code"]).head(15)

    country_chart = alt.Chart(country_latest).mark_bar().encode(
        x=alt.X("n_af_works:Q", title="AF-related works"),
        y=alt.Y("country_code:N", sort="-x", title="Country"),
        tooltip=["country_code", "publication_year", "n_works", "n_af_works", "af_share"],
    ).properties(
        title="Top countries by latest AF-related output",
        width=380,
        height=260,
    )

    topic_latest = topic_trend_df.sort_values(
        ["publication_year", "af_share", "n_works"], ascending=[False, False, False]
    ).drop_duplicates(subset=["topic_display_name"]).head(15)

    topic_chart = alt.Chart(topic_latest).mark_bar().encode(
        x=alt.X("af_share:Q", title="AF share"),
        y=alt.Y("topic_display_name:N", sort="-x", title="Topic"),
        tooltip=["topic_display_name", "publication_year", "n_works", "af_share"],
    ).properties(
        title="Top topics by latest AF share",
        width=380,
        height=260,
    )

    mo.vstack([
        mo.hstack([annual_chart, country_chart]),
        topic_chart,
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 八、团队规模、机构合作与国际合作趋势

    下面三张图分别展示：

    - 团队规模：论文的平均作者数量逐年趋势
    - 机构合作：论文的平均机构数量逐年趋势
    - 国际合作：论文的平均国家数量逐年趋势

    每张图都包含三条线：

    - Total
    - Non-AF
    - AF
    """)
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, analysis_ready, mo, work_institutions_glob, works_glob):
    mo.stop(
        not analysis_ready,
        mo.md(r"""
        尚未检测到 `derived_tables/works/`、`derived_tables/work_institutions/` 或 `derived_tables/work_topics/` 下的 parquet 文件。

        请先运行前面的规范化拆表与写盘流程，再查看本分析区。
        """),
    )

    team_collab_metrics_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    author_counts AS (
        SELECT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            COUNT(a.author_id) AS author_count
        FROM work_flags AS w
        LEFT JOIN read_parquet('derived_tables/authorships/*.parquet') AS a
            ON w.work_id = a.work_id
        GROUP BY 1, 2, 3
    ),
    institution_country_counts AS (
        SELECT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            COUNT(DISTINCT wi.institution_id) AS institution_count,
            COUNT(DISTINCT wi.country_code) AS country_count
        FROM work_flags AS w
        LEFT JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        GROUP BY 1, 2, 3
    ),
    work_level_metrics AS (
        SELECT
            ac.work_id,
            ac.publication_year,
            ac.is_alphafold_related,
            ac.author_count,
            COALESCE(ic.institution_count, 0) AS institution_count,
            COALESCE(ic.country_count, 0) AS country_count
        FROM author_counts AS ac
        LEFT JOIN institution_country_counts AS ic
            ON ac.work_id = ic.work_id
    ),
    annual_metrics AS (
        SELECT
            publication_year,
            'Total' AS group_name,
            AVG(author_count) AS avg_author_count,
            AVG(institution_count) AS avg_institution_count,
            AVG(country_count) AS avg_country_count
        FROM work_level_metrics
        GROUP BY 1

        UNION ALL

        SELECT
            publication_year,
            'AF' AS group_name,
            AVG(author_count) AS avg_author_count,
            AVG(institution_count) AS avg_institution_count,
            AVG(country_count) AS avg_country_count
        FROM work_level_metrics
        WHERE is_alphafold_related = TRUE
        GROUP BY 1

        UNION ALL

        SELECT
            publication_year,
            'Non-AF' AS group_name,
            AVG(author_count) AS avg_author_count,
            AVG(institution_count) AS avg_institution_count,
            AVG(country_count) AS avg_country_count
        FROM work_level_metrics
        WHERE is_alphafold_related = FALSE
        GROUP BY 1
    )
    SELECT *
    FROM annual_metrics
    ORDER BY publication_year, group_name
    """).df()

    team_size_trend_df = team_collab_metrics_df[[
        "publication_year",
        "group_name",
        "avg_author_count",
    ]].rename(columns={"avg_author_count": "metric_value"})

    institution_collab_trend_df = team_collab_metrics_df[[
        "publication_year",
        "group_name",
        "avg_institution_count",
    ]].rename(columns={"avg_institution_count": "metric_value"})

    international_collab_trend_df = team_collab_metrics_df[[
        "publication_year",
        "group_name",
        "avg_country_count",
    ]].rename(columns={"avg_country_count": "metric_value"})
    return (
        institution_collab_trend_df,
        international_collab_trend_df,
        team_size_trend_df,
    )


@app.cell(hide_code=True)
def _(alt, team_size_trend_df):
    team_size_line_chart = alt.Chart(team_size_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Average number of authors"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("metric_value:Q", title="Average authors", format=".2f"),
        ],
    ).properties(
        title="Team size trend: average number of authors per paper",
        width=760,
        height=320,
    )

    team_size_line_chart
    return


@app.cell(hide_code=True)
def _(
    alt,
    country_group_color_domain,
    country_group_color_range,
    country_team_size_top5_df,
):
    country_team_size_top5_chart = alt.Chart(country_team_size_top5_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Average number of authors"),
        color=alt.Color(
            "country_group:N",
            title="Country / Group",
            scale=alt.Scale(
                domain=country_group_color_domain,
                range=country_group_color_range,
            ),
        ),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("metric_value:Q", title="Average authors", format=".2f"),
        ],
    ).properties(
        title="Top 5 countries: team size trend by Total / Non-AF / AF",
        width=900,
        height=420,
    )

    country_team_size_top5_chart
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, country_trend_df, work_institutions_glob, works_glob):
    country_collab_metrics_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_country_anchor AS (
        SELECT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            wi.country_code
        FROM work_flags AS w
        INNER JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.country_code IS NOT NULL
    ),
    author_counts AS (
        SELECT
            wca.work_id,
            wca.publication_year,
            wca.is_alphafold_related,
            wca.country_code,
            COUNT(a.author_id) AS author_count
        FROM work_country_anchor AS wca
        LEFT JOIN read_parquet('derived_tables/authorships/*.parquet') AS a
            ON wca.work_id = a.work_id
        GROUP BY 1, 2, 3, 4
    ),
    institution_country_counts AS (
        SELECT
            wca.work_id,
            wca.publication_year,
            wca.is_alphafold_related,
            wca.country_code,
            COUNT(DISTINCT wi.institution_id) AS institution_count,
            COUNT(DISTINCT wi.country_code) AS country_count
        FROM work_country_anchor AS wca
        LEFT JOIN read_parquet('{work_institutions_glob}') AS wi
            ON wca.work_id = wi.work_id
        GROUP BY 1, 2, 3, 4
    ),
    work_level_metrics AS (
        SELECT
            ac.work_id,
            ac.publication_year,
            ac.is_alphafold_related,
            ac.country_code,
            ac.author_count,
            COALESCE(ic.institution_count, 0) AS institution_count,
            COALESCE(ic.country_count, 0) AS country_count
        FROM author_counts AS ac
        LEFT JOIN institution_country_counts AS ic
            ON ac.work_id = ic.work_id
           AND ac.country_code = ic.country_code
    ),
    annual_country_metrics AS (
        SELECT
            publication_year,
            country_code,
            'Total' AS group_name,
            AVG(author_count) AS avg_author_count,
            AVG(institution_count) AS avg_institution_count,
            AVG(country_count) AS avg_country_count,
            COUNT(DISTINCT work_id) AS n_works
        FROM work_level_metrics
        GROUP BY 1, 2

        UNION ALL

        SELECT
            publication_year,
            country_code,
            'AF' AS group_name,
            AVG(author_count) AS avg_author_count,
            AVG(institution_count) AS avg_institution_count,
            AVG(country_count) AS avg_country_count,
            COUNT(DISTINCT work_id) AS n_works
        FROM work_level_metrics
        WHERE is_alphafold_related = TRUE
        GROUP BY 1, 2

        UNION ALL

        SELECT
            publication_year,
            country_code,
            'Non-AF' AS group_name,
            AVG(author_count) AS avg_author_count,
            AVG(institution_count) AS avg_institution_count,
            AVG(country_count) AS avg_country_count,
            COUNT(DISTINCT work_id) AS n_works
        FROM work_level_metrics
        WHERE is_alphafold_related = FALSE
        GROUP BY 1, 2
    )
    SELECT *
    FROM annual_country_metrics
    ORDER BY publication_year, country_code, group_name
    """).df()

    country_top5_codes_collab = country_trend_df.groupby("country_code")["n_works"].sum().sort_values(ascending=False).head(5).index.tolist()

    country_team_size_top5_df = country_collab_metrics_df[
        country_collab_metrics_df["country_code"].isin(country_top5_codes_collab)
    ][[
        "publication_year",
        "country_code",
        "group_name",
        "avg_author_count",
    ]].rename(columns={"avg_author_count": "metric_value"}).copy()
    country_team_size_top5_df["country_group"] = country_team_size_top5_df["country_code"] + " - " + country_team_size_top5_df["group_name"]

    country_institution_top5_df = country_collab_metrics_df[
        country_collab_metrics_df["country_code"].isin(country_top5_codes_collab)
    ][[
        "publication_year",
        "country_code",
        "group_name",
        "avg_institution_count",
    ]].rename(columns={"avg_institution_count": "metric_value"}).copy()
    country_institution_top5_df["country_group"] = country_institution_top5_df["country_code"] + " - " + country_institution_top5_df["group_name"]

    country_international_top5_df = country_collab_metrics_df[
        country_collab_metrics_df["country_code"].isin(country_top5_codes_collab)
    ][[
        "publication_year",
        "country_code",
        "group_name",
        "avg_country_count",
    ]].rename(columns={"avg_country_count": "metric_value"}).copy()
    country_international_top5_df["country_group"] = country_international_top5_df["country_code"] + " - " + country_international_top5_df["group_name"]

    country_group_color_domain = [
        f"{country_code} - {group_name}"
        for country_code in country_top5_codes_collab
        for group_name in ["Total", "Non-AF", "AF"]
    ]
    country_group_color_range = [
        color_value
        for color_triplet in [
            ["#1f77b4", "#6baed6", "#08306b"],
            ["#2ca02c", "#74c476", "#00441b"],
            ["#d62728", "#fb6a4a", "#67000d"],
            ["#9467bd", "#bcbddc", "#3f007d"],
            ["#ff7f0e", "#fdae6b", "#7f2704"],
        ]
        for color_value in color_triplet
    ]
    return (
        country_group_color_domain,
        country_group_color_range,
        country_institution_top5_df,
        country_international_top5_df,
        country_team_size_top5_df,
    )


@app.cell(hide_code=True)
def _(alt, institution_collab_trend_df):
    institution_collab_line_chart = alt.Chart(institution_collab_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Average number of institutions"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("metric_value:Q", title="Average institutions", format=".2f"),
        ],
    ).properties(
        title="Institution collaboration trend: average number of institutions per paper",
        width=760,
        height=320,
    )

    institution_collab_line_chart
    return


@app.cell(hide_code=True)
def _(
    alt,
    country_group_color_domain,
    country_group_color_range,
    country_institution_top5_df,
):
    country_institution_top5_chart = alt.Chart(country_institution_top5_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Average number of institutions"),
        color=alt.Color(
            "country_group:N",
            title="Country / Group",
            scale=alt.Scale(
                domain=country_group_color_domain,
                range=country_group_color_range,
            ),
        ),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("metric_value:Q", title="Average institutions", format=".2f"),
        ],
    ).properties(
        title="Top 5 countries: institution collaboration trend by Total / Non-AF / AF",
        width=900,
        height=420,
    )

    country_institution_top5_chart
    return


@app.cell(hide_code=True)
def _(alt, international_collab_trend_df):
    international_collab_line_chart = alt.Chart(international_collab_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Average number of countries"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("metric_value:Q", title="Average countries", format=".2f"),
        ],
    ).properties(
        title="International collaboration trend: average number of countries per paper",
        width=760,
        height=320,
    )

    international_collab_line_chart
    return


@app.cell(hide_code=True)
def _(
    alt,
    country_group_color_domain,
    country_group_color_range,
    country_international_top5_df,
):
    country_international_top5_chart = alt.Chart(country_international_top5_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Average number of countries"),
        color=alt.Color(
            "country_group:N",
            title="Country / Group",
            scale=alt.Scale(
                domain=country_group_color_domain,
                range=country_group_color_range,
            ),
        ),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("metric_value:Q", title="Average countries", format=".2f"),
        ],
    ).properties(
        title="Top 5 countries: international collaboration trend by Total / Non-AF / AF",
        width=900,
        height=420,
    )

    country_international_top5_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Part 3. Spatial inequality and concentration

    这一部分关注的是：**AlphaFold 相关研究是否比总体科研或非 AlphaFold 科研更集中于少数国家。**

    如果 AF 相关产出和 adoption rate 明显比一般科研更集中，那么这意味着 AlphaFold 并没有自动降低科研空间不平等，反而可能在扩散初期强化少数中心国家的领先优势。

    这一部分主要使用三类指标：

    - `Gini coefficient`
    - `Lorenz curve`
    - `Top 10 countries' share of AF works`

    它们分别对应：

    - 总结性的空间不平等指标；
    - 集中度的可视化结构；
    - 头部国家控制全球份额的直观度量。
    """)
    return


@app.function(hide_code=True)
def gini_coefficient(values) -> float:
    import numpy as np

    _values = np.asarray(values, dtype=float)
    _values = _values[np.isfinite(_values)]
    _values = _values[_values >= 0]

    if len(_values) == 0:
        return float("nan")
    if np.all(_values == 0):
        return 0.0

    _values_sorted = np.sort(_values)
    _n = len(_values_sorted)
    _index = np.arange(1, _n + 1)

    return float(
        2 * np.sum(_index * _values_sorted) / (_n * np.sum(_values_sorted))
        - (_n + 1) / _n
    )


@app.cell(hide_code=True)
def _(analysis_ready, country_trend_df, mo, pd):
    mo.stop(
        not analysis_ready,
        mo.md(r"""
        尚未检测到 `derived_tables/works/`、`derived_tables/work_institutions/` 或 `derived_tables/work_topics/` 下的 parquet 文件。

        请先运行前面的规范化拆表与写盘流程，再查看本分析区。
        """),
    )

    gini_base_df = country_trend_df.copy()
    gini_base_df["n_non_af_works"] = gini_base_df["n_works"] - gini_base_df["n_af_works"]

    gini_rows = []
    for _year, _group_df in gini_base_df.groupby("publication_year"):
        gini_rows.append({
            "publication_year": _year,
            "group_name": "Total",
            "gini_value": gini_coefficient(_group_df["n_works"].to_numpy()),
        })
        gini_rows.append({
            "publication_year": _year,
            "group_name": "Non-AF",
            "gini_value": gini_coefficient(_group_df["n_non_af_works"].to_numpy()),
        })
        gini_rows.append({
            "publication_year": _year,
            "group_name": "AF",
            "gini_value": gini_coefficient(_group_df["n_af_works"].to_numpy()),
        })

    gini_trend_df = pd.DataFrame(gini_rows).sort_values(["publication_year", "group_name"])
    return (gini_trend_df,)


@app.cell(hide_code=True)
def _(alt, gini_trend_df):
    gini_trend_chart = alt.Chart(gini_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("gini_value:Q", title="Gini coefficient", scale=alt.Scale(domain=[0, 1])),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("gini_value:Q", title="Gini coefficient", format=".3f"),
        ],
    ).properties(
        title="Country-level spatial inequality over time: Total vs Non-AF vs AF",
        width=820,
        height=360,
    )

    gini_trend_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### How to read the Gini trend

    这张图的解释逻辑是：

    - `AF` 线越高，说明 AlphaFold 相关研究越集中在少数国家；
    - `Non-AF` 线可以看作“普通科研空间分布”的对照组；
    - `Total` 线反映总体科研知识生产的国家集中度。

    ### Interpreting possible outcomes

    - 如果 `AF` 线明显高于 `Non-AF` 线，说明 AF 相关研究比普通研究更集中，意味着 AlphaFold **可能强化了科研空间不平等**；
    - 如果 `AF` 线在早期很高、之后逐步下降，说明 AlphaFold 最初由少数国家率先采用，但随后向更多国家扩散；
    - 如果 `AF` 线长期保持在较高水平，即使有所下降，也说明 AlphaFold 的全球扩散仍然带有较强的“中心国家主导”特征。

    ### Substantive conclusion for this notebook

    因此，在你的研究框架里，Gini coefficient 的作用不是单纯描述“谁发得多”，而是回答一个更重要的问题：

    **AlphaFold 相关科研是否比原有科研体系更集中于少数国家，以及这种集中是否随着时间推移而缓解。**

    如果后续图中显示 `Gini(AF)` 长期高于 `Gini(Non-AF)`，那么可以较有力地支持这样一个判断：

    **AlphaFold 在扩散过程中并没有自动消除全球科研空间不平等，反而可能在初期强化了少数科研强国的领先地位。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Additional inequality views

    下面补充三类图，用来从不同角度理解 AlphaFold 的空间不平等：

    - `AF share Gini over time`：衡量各国 adoption rate 的不平等；
    - `Lorenz curve`：比较关键年份 AF 论文国家分布的集中程度；
    - `Top 10 countries share of AF works`：衡量少数国家占全球 AF 论文的份额。
    """)
    return


@app.cell(hide_code=True)
def _(country_trend_df, pd):
    af_share_gini_rows = []
    for _year, _group_df in country_trend_df.groupby("publication_year"):
        af_share_gini_rows.append({
            "publication_year": _year,
            "gini_value": gini_coefficient(_group_df["af_share"].to_numpy()),
        })

    af_share_gini_df = pd.DataFrame(af_share_gini_rows).sort_values("publication_year")

    lorenz_years = [2021, 2023, 2025]
    lorenz_rows = []
    for _year in lorenz_years:
        _year_df = country_trend_df[country_trend_df["publication_year"] == _year].copy()
        _values = _year_df["n_af_works"].fillna(0).to_numpy()
        _values = _values[_values >= 0]
        _values.sort()
        if len(_values) == 0:
            continue
        _cum_values = _values.cumsum()
        _total = _values.sum()
        if _total == 0:
            continue
        _cum_share = _cum_values / _total
        _country_share = (pd.Series(range(1, len(_values) + 1)) / len(_values)).to_numpy()

        lorenz_rows.append({
            "publication_year": _year,
            "country_share": 0.0,
            "work_share": 0.0,
        })
        lorenz_rows.extend([
            {
                "publication_year": _year,
                "country_share": float(_country_share[_i]),
                "work_share": float(_cum_share[_i]),
            }
            for _i in range(len(_values))
        ])

    lorenz_curve_df = pd.DataFrame(lorenz_rows)

    top10_share_rows = []
    for _year, _group_df in country_trend_df.groupby("publication_year"):
        _sorted_df = _group_df.sort_values("n_af_works", ascending=False)
        _top10_sum = _sorted_df.head(10)["n_af_works"].sum()
        _total_sum = _sorted_df["n_af_works"].sum()
        _share = (_top10_sum / _total_sum) if _total_sum > 0 else 0.0
        top10_share_rows.append({
            "publication_year": _year,
            "top10_af_share": _share,
            "top10_af_works": _top10_sum,
            "total_af_works": _total_sum,
        })

    top10_country_share_df = pd.DataFrame(top10_share_rows).sort_values("publication_year")
    return af_share_gini_df, lorenz_curve_df, top10_country_share_df


@app.cell(hide_code=True)
def _(af_share_gini_df, alt):
    af_share_gini_chart = alt.Chart(af_share_gini_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("gini_value:Q", title="Gini coefficient of AF share", scale=alt.Scale(domain=[0, 1])),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("gini_value:Q", title="Gini coefficient", format=".3f"),
        ],
    ).properties(
        title="AF share Gini over time",
        width=820,
        height=320,
    )

    af_share_gini_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting AF share Gini over time

    这张图与前面的 `AF works Gini` 不同，它衡量的不是 **AF 论文数量分布** 的不平等，而是 **AF adoption rate (`af_share`)** 在国家之间的差异。

    ### 如何理解

    - 如果 `AF share Gini` 很高，说明不同国家采用 AlphaFold 的比例差异很大；
    - 如果 `AF share Gini` 下降，说明 adoption rate 正在从少数国家扩散到更多国家；
    - 如果 `AF share Gini` 长期维持在高位，即使 AF 论文数量增加，也说明 adoption intensity 仍然高度不均衡。

    ### 这张图的重要意义

    它回答的不是“谁发了更多 AF 论文”，而是：

    **不同国家把 AlphaFold 纳入自身科研体系的程度，是否仍然高度分化。**

    因此，这张图特别适合用来判断：

    **AlphaFold 的全球扩散是否真正转化成了更广泛、更均衡的 adoption，而不仅仅是少数国家产出更多 AF 论文。**
    """)
    return


@app.cell(hide_code=True)
def _(alt, lorenz_curve_df, pd):
    lorenz_curve_chart = alt.Chart(lorenz_curve_df).mark_line().encode(
        x=alt.X("country_share:Q", title="Cumulative share of countries", axis=alt.Axis(format=".0%")),
        y=alt.Y("work_share:Q", title="Cumulative share of AF works", axis=alt.Axis(format=".0%")),
        color=alt.Color("publication_year:N", title="Publication year"),
        tooltip=[
            alt.Tooltip("publication_year:N", title="Publication year"),
            alt.Tooltip("country_share:Q", title="Country share", format=".1%"),
            alt.Tooltip("work_share:Q", title="AF work share", format=".1%"),
        ],
    ).properties(
        title="Lorenz curve of AF works across countries",
        width=820,
        height=360,
    )

    equality_line = alt.Chart(pd.DataFrame({
        "country_share": [0.0, 1.0],
        "work_share": [0.0, 1.0],
    })).mark_line(strokeDash=[6, 4], color="#666666").encode(
        x="country_share:Q",
        y="work_share:Q",
    )

    lorenz_curve_chart + equality_line
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the Lorenz curve

    Lorenz curve 用来直观展示 AF 论文在国家之间的集中程度。

    图中的虚线表示 **完全平均分布**：

    - 如果所有国家的 AF 论文份额完全均匀，曲线会贴近这条对角线；
    - 如果 AF 论文高度集中在少数国家，曲线就会明显向右下方弯曲。

    ### 如何比较不同年份

    - 某一年曲线 **离对角线越远**，说明该年的 AF 论文越集中在少数国家；
    - 如果后期年份曲线逐渐向对角线靠近，说明 AF 正在从先发国家向更多国家扩散；
    - 如果后期年份仍然明显弯曲，则说明即使 adoption 国家数量增加，全球 AF 研究仍然高度集中。

    ### 这张图的重要意义

    Lorenz curve 的优势在于，它不像单一的 Gini 数值那样只给出一个总结指标，而是可以直接看到：

    **全球多少比例的国家，仅贡献了多少比例的 AF 论文。**

    因此，它特别适合用来支持这样一个判断：

    **AlphaFold 的扩散是否只是“更多国家开始参与”，还是仍然主要由少数国家掌握核心产出。**
    """)
    return


@app.cell(hide_code=True)
def _(alt, top10_country_share_df):
    top10_country_share_chart = alt.Chart(top10_country_share_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("top10_af_share:Q", title="Top 10 countries' share of AF works", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("top10_af_share:Q", title="Top 10 share", format=".1%"),
            alt.Tooltip("top10_af_works:Q", title="Top 10 AF works", format=".0f"),
            alt.Tooltip("total_af_works:Q", title="Total AF works", format=".0f"),
        ],
    ).properties(
        title="Top 10 countries' share of global AF works over time",
        width=820,
        height=320,
    )

    top10_country_share_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the Top 10 countries' share

    这张图衡量的是：

    **全球 AF 论文中，有多大比例集中在前 10 个国家。**

    ### 如何理解

    - 如果这条线很高，说明全球 AF 研究主要集中在少数头部国家；
    - 如果这条线下降，说明越来越多国家开始分享 AF 相关产出，集中度在减弱；
    - 如果这条线长期保持高位，则说明即使 adoption 在扩散，全球 AF 核心产出仍然被少数国家主导。

    ### 这张图的重要意义

    与 Gini coefficient 相比，这张图的优点是更直观：

    - Gini 告诉你“不平等程度有多高”；
    - Top 10 share 直接告诉你“前 10 个国家拿走了多少份额”。

    因此，这张图特别适合支持关于“科研中心国家是否持续主导 AlphaFold 扩散”的论述。

    如果后期 `Top 10 share` 仍然很高，那么可以说明：

    **AlphaFold 虽然在全球范围扩散，但其核心知识生产仍然高度集中在少数国家。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Part 4. Has the global spatial structure been reconfigured?

    结合前面三部分结果，这里要回答的不是单一国家是否增长，也不是单纯 adoption 是否扩散，而是一个更高层次的问题：

    **AlphaFold 是否重构了全球科研生产的空间格局？**

    ### 综合判断逻辑

    如果同时观察到：

    - 知识生产中心的国家构成发生明显变化；
    - adoption 从核心国家扩散到更广泛国家群体；
    - AF 相关研究的国家集中度明显下降；
    - 头部国家对全球 AF 产出的控制份额显著减弱；

    那么才可以较强地支持“空间格局被重构”的结论。

    但如果结果显示：

    - AF adoption 确实扩散到了更多国家；
    - 然而核心产出仍然集中在少数头部国家；
    - Gini、Lorenz curve 与 Top 10 share 都表明集中度仍然较高；

    那么更合理的解释是：

    **AlphaFold 带来了全球扩散，但这种扩散主要发生在原有中心—外围体系之内，表现为旧有空间格局的放大与延伸，而不是完全意义上的重构。**

    ### Overall interpretation for this notebook

    从当前 notebook 的分析逻辑看，更可能出现的并不是“旧格局被彻底打破”，而是：

    1. **全球采用范围扩大了**：更多国家进入 AlphaFold 相关研究；
    2. **采用具有时间梯度**：先发国家和后发国家之间存在明显差异；
    3. **空间不平等仍然存在**：AF 相关研究和 adoption 并没有自动变得均匀；
    4. **中心国家仍然占主导**：即使扩散发生，核心知识生产仍更可能掌握在少数科研强国手中。

    因此，这一整套地理分布分析更适合支持这样一个总体结论：

    **AlphaFold 改变了全球科研扩散的速度与覆盖范围，但它是否真正重构了科研生产的全球空间格局，取决于我们看到的是“中心地位的转移”，还是“原有中心体系中的扩散与强化”。就目前这套分析框架而言，更接近后者。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    国际/机构协作: 研究机构间跨国合作网络的变化
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Part 5. International and institutional collaboration

    这一部分从协作网络的角度，考察 AlphaFold 是否改变了知识生产的组织方式。这里关注的不只是“谁在生产知识”，而是：

    - 知识是否越来越通过跨国合作完成；
    - AF 相关研究是否比普通研究更依赖多机构协作；
    - 国际合作网络是否发生扩展；
    - 少数国家与机构是否仍然主导跨国协作。

    ### 研究问题

    本部分主要回答四个问题：

    1. AF 相关论文是否涉及更多国家与机构？
    2. AF 相关研究是否更频繁地表现为跨国合作？
    3. 哪些国家之间构成最重要的跨国协作通道？
    4. 这些协作变化是否意味着知识生产方式发生了组织上的重构？

    ### 分析逻辑

    这一部分按论文式逻辑分成三层：

    - **协作规模变化**：平均国家数、平均机构数、跨国合作论文占比；
    - **协作结构变化**：哪些国家对最常共同出现；
    - **协作格局解释**：AF 是否扩大了跨国合作，但又是否仍由少数国家主导。
    """)
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, analysis_ready, mo, work_institutions_glob, works_glob):
    mo.stop(
        not analysis_ready,
        mo.md(r"""
        尚未检测到 `derived_tables/works/`、`derived_tables/work_institutions/` 或 `derived_tables/work_topics/` 下的 parquet 文件。

        请先运行前面的规范化拆表与写盘流程，再查看本分析区。
        """),
    )

    collab_share_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_country_counts AS (
        SELECT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            COUNT(DISTINCT wi.country_code) AS country_count
        FROM work_flags AS w
        LEFT JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.country_code IS NOT NULL
        GROUP BY 1, 2, 3
    ),
    annual_collab AS (
        SELECT
            publication_year,
            'Total' AS group_name,
            AVG(CASE WHEN country_count > 1 THEN 1.0 ELSE 0.0 END) AS share_international
        FROM work_country_counts
        GROUP BY 1

        UNION ALL

        SELECT
            publication_year,
            'AF' AS group_name,
            AVG(CASE WHEN country_count > 1 THEN 1.0 ELSE 0.0 END) AS share_international
        FROM work_country_counts
        WHERE is_alphafold_related = TRUE
        GROUP BY 1

        UNION ALL

        SELECT
            publication_year,
            'Non-AF' AS group_name,
            AVG(CASE WHEN country_count > 1 THEN 1.0 ELSE 0.0 END) AS share_international
        FROM work_country_counts
        WHERE is_alphafold_related = FALSE
        GROUP BY 1
    )
    SELECT *
    FROM annual_collab
    ORDER BY publication_year, group_name
    """).df()

    country_pair_edges_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_countries AS (
        SELECT DISTINCT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            wi.country_code
        FROM work_flags AS w
        INNER JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.country_code IS NOT NULL
    ),
    country_pairs AS (
        SELECT
            a.work_id,
            a.publication_year,
            a.is_alphafold_related,
            LEAST(a.country_code, b.country_code) AS country_code_1,
            GREATEST(a.country_code, b.country_code) AS country_code_2
        FROM work_countries AS a
        INNER JOIN work_countries AS b
            ON a.work_id = b.work_id
           AND a.country_code < b.country_code
    )
    SELECT
        publication_year,
        is_alphafold_related,
        country_code_1,
        country_code_2,
        COUNT(*) AS edge_weight
    FROM country_pairs
    GROUP BY 1, 2, 3, 4
    ORDER BY edge_weight DESC
    """).df()

    country_pair_edges_af_df = country_pair_edges_df[
        country_pair_edges_df["is_alphafold_related"] == True
    ].copy()
    country_pair_edges_af_df["country_pair"] = (
        country_pair_edges_af_df["country_code_1"] + " – " + country_pair_edges_af_df["country_code_2"]
    )

    country_pair_edges_top20_df = country_pair_edges_af_df.sort_values(
        ["edge_weight", "publication_year"],
        ascending=[False, False],
    ).head(20).copy()
    return (
        collab_share_df,
        country_pair_edges_af_df,
        country_pair_edges_df,
        country_pair_edges_top20_df,
    )


@app.cell(hide_code=True)
def _(alt, collab_share_df):
    international_share_line_chart = alt.Chart(collab_share_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("share_international:Q", title="Share of international collaboration papers", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("share_international:Q", title="Share", format=".1%"),
        ],
    ).properties(
        title="Share of international collaboration papers over time: Total vs Non-AF vs AF",
        width=820,
        height=320,
    )

    international_share_line_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the international collaboration trend

    这张图回答的是：

    **AF 相关论文是否比普通论文更依赖跨国合作。**

    ### 如何理解

    - 如果 `AF` 线高于 `Non-AF` 线，说明 AF 相关研究更频繁地通过跨国合作完成；
    - 如果 `AF` 线在 2021 之后上升更快，说明 AlphaFold 不只是扩散到更多国家，也在推动跨国协作关系变得更紧密；
    - 如果 `Total`、`Non-AF` 与 `AF` 三条线同时上升，则说明国际合作本身在增强，但 AF 可能进一步强化了这一趋势。

    ### 实质意义

    这一结果的意义在于，它把“地理扩散”推进到了“组织方式变化”：

    **如果 AF 论文更依赖跨国合作，那么 AlphaFold 改变的不只是科研成果的空间分布，也可能改变了知识生产的组织结构。**
    """)
    return


@app.cell(hide_code=True)
def _(alt, country_pair_edges_top20_df):
    country_pair_top20_bar_chart = alt.Chart(country_pair_edges_top20_df).mark_bar().encode(
        x=alt.X("edge_weight:Q", title="Number of AF collaboration links"),
        y=alt.Y("country_pair:N", sort="-x", title="Country pair"),
        tooltip=[
            alt.Tooltip("country_pair:N", title="Country pair"),
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("edge_weight:Q", title="Edge weight", format=".0f"),
        ],
    ).properties(
        title="Top 20 country collaboration pairs in AF-related research",
        width=820,
        height=420,
    )

    country_pair_top20_bar_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the top country collaboration pairs

    这张图展示的是 AF 相关研究中最重要的跨国协作通道。

    ### 如何理解

    - 如果合作边主要集中在少数头部国家之间，说明 AF 的国际协作网络虽然存在，但仍然由核心国家主导；
    - 如果后期出现更多新的国家组合进入 top edges，说明协作网络正在从少数中心国家扩展到更广泛的国家群体；
    - 如果某些国家频繁出现在 top collaboration pairs 中，则说明它们不仅是高产出国，也处于国际知识协作网络的关键位置。

    ### 论文式结论

    因此，国家合作边分析回答的不是“哪些国家发文最多”，而是：

    **哪些国家之间构成了 AlphaFold 全球知识生产最重要的协作通道。**

    如果这些通道长期集中在少数科研强国之间，那么更合理的解释是：

    **AlphaFold 促进了跨国合作，但这种合作首先强化的是已有中心国家之间的高强度连接，而不是立即形成均匀分布的全球合作网络。**
    """)
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, work_institutions_glob, works_glob):
    institution_collab_share_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_institution_country_counts AS (
        SELECT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            COUNT(DISTINCT wi.institution_id) AS institution_count,
            COUNT(DISTINCT wi.country_code) AS country_count
        FROM work_flags AS w
        LEFT JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.institution_id IS NOT NULL
        GROUP BY 1, 2, 3
    ),
    annual_inst_collab AS (
        SELECT
            publication_year,
            'Total' AS group_name,
            AVG(CASE WHEN institution_count > 1 THEN 1.0 ELSE 0.0 END) AS share_multi_institution,
            AVG(CASE WHEN country_count > 1 THEN 1.0 ELSE 0.0 END) AS share_cross_border_institution
        FROM work_institution_country_counts
        GROUP BY 1

        UNION ALL

        SELECT
            publication_year,
            'AF' AS group_name,
            AVG(CASE WHEN institution_count > 1 THEN 1.0 ELSE 0.0 END) AS share_multi_institution,
            AVG(CASE WHEN country_count > 1 THEN 1.0 ELSE 0.0 END) AS share_cross_border_institution
        FROM work_institution_country_counts
        WHERE is_alphafold_related = TRUE
        GROUP BY 1

        UNION ALL

        SELECT
            publication_year,
            'Non-AF' AS group_name,
            AVG(CASE WHEN institution_count > 1 THEN 1.0 ELSE 0.0 END) AS share_multi_institution,
            AVG(CASE WHEN country_count > 1 THEN 1.0 ELSE 0.0 END) AS share_cross_border_institution
        FROM work_institution_country_counts
        WHERE is_alphafold_related = FALSE
        GROUP BY 1
    )
    SELECT *
    FROM annual_inst_collab
    ORDER BY publication_year, group_name
    """).df()

    top_institutions_af_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    af_institutions AS (
        SELECT DISTINCT
            wi.work_id,
            wi.institution_id,
            wi.institution_name,
            wi.country_code
        FROM read_parquet('{work_institutions_glob}') AS wi
        INNER JOIN work_flags AS w
            ON wi.work_id = w.work_id
        WHERE w.is_alphafold_related = TRUE
          AND wi.institution_id IS NOT NULL
    ),
    inst_counts AS (
        SELECT
            institution_id,
            institution_name,
            country_code,
            COUNT(DISTINCT work_id) AS n_af_works
        FROM af_institutions
        GROUP BY 1, 2, 3
    )
    SELECT *
    FROM inst_counts
    ORDER BY n_af_works DESC
    LIMIT 20
    """).df()
    return institution_collab_share_df, top_institutions_af_df


@app.cell(hide_code=True)
def _(alt, institution_collab_share_df):
    cross_border_institution_share_chart = alt.Chart(institution_collab_share_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("share_cross_border_institution:Q", title="Share of cross-border institution collaboration papers", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("share_cross_border_institution:Q", title="Share", format=".1%"),
        ],
    ).properties(
        title="Share of cross-border institutional collaboration papers over time: Total vs Non-AF vs AF",
        width=820,
        height=320,
    )

    cross_border_institution_share_chart
    return


@app.cell(hide_code=True)
def _(alt, top_institutions_af_df):
    top_institutions_af_chart = alt.Chart(top_institutions_af_df).mark_bar().encode(
        x=alt.X("n_af_works:Q", title="Number of AF-related works"),
        y=alt.Y("institution_name:N", sort="-x", title="Institution"),
        color=alt.Color("country_code:N", title="Country"),
        tooltip=[
            alt.Tooltip("institution_name:N", title="Institution"),
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("n_af_works:Q", title="AF-related works", format=".0f"),
        ],
    ).properties(
        title="Top institutions in AF-related research by number of works",
        width=820,
        height=520,
    )

    top_institutions_af_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting cross-border institutional collaboration

    这张图关注的是：

    **AF 相关论文是否更频繁地通过跨国机构合作完成。**

    ### 如何理解

    - 如果 `AF` 线高于 `Non-AF` 线，说明 AF 相关研究更依赖跨国机构协作；
    - 如果 `AF` 线随时间上升更快，说明 AlphaFold 不只是促进国家层面的合作，也促进了机构层面的跨境连接；
    - 如果 `AF` 与 `Total` 同时上升，则说明在全球科研本身协作增强的背景下，AF 可能进一步放大了这种组织变化。

    ### 实质意义

    这张图把协作分析从“国家之间是否合作”推进到“机构之间如何跨国连接”。

    如果跨国机构合作占比在 AF 研究中更高，那么可以说明：

    **AlphaFold 相关研究不仅具有更强的国际化特征，也更依赖跨机构、跨边界的联合知识生产。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting top institutions in AF-related research

    这张图展示的是 AF 相关研究中最重要的机构节点。

    ### 如何理解

    - 如果 top institutions 主要集中在少数国家，说明 AF 相关知识生产虽然全球扩散，但组织核心仍掌握在少数国家的关键机构手中；
    - 如果出现来自不同国家的机构同时进入前列，说明 AF 的知识生产网络可能具有更强的跨国组织特征；
    - 如果某些机构不仅论文量高，而且所在国家也频繁出现在 top collaboration pairs 中，那么这些机构很可能是 AF 扩散网络中的关键组织中心。

    ### 论文式结论

    因此，机构层面的分布并不是单纯告诉我们“谁发文最多”，而是帮助我们识别：

    **在 AlphaFold 相关研究中，哪些机构构成了全球知识生产网络的组织核心。**

    如果这些机构长期集中在少数科研强国，那么更合理的解释是：

    **AlphaFold 扩大了国际协作范围，但其组织核心仍然高度依赖少数头部机构。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Network structure perspective

    前面的图已经告诉我们：

    - AF 相关研究是否更依赖跨国合作；
    - 哪些国家对与机构处于协作核心。

    下面进一步从“网络结构”的角度理解这种变化。这里不直接构造复杂力导向网络图，而是用更稳、更适合论文展示的两类代理：

    - **国家合作边强度**：哪些国家之间构成最重要的连接；
    - **机构节点中心性代理**：哪些机构在 AF 相关知识生产中处于组织核心。

    这种方式的优点是：

    - 结果更稳定；
    - 更适合做年度或分组比较；
    - 比密集网络图更容易阅读和解释。
    """)
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, work_institutions_glob, works_glob):
    institution_network_proxy_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    af_work_institutions AS (
        SELECT DISTINCT
            wi.work_id,
            wi.institution_id,
            wi.institution_name,
            wi.country_code
        FROM read_parquet('{work_institutions_glob}') AS wi
        INNER JOIN work_flags AS w
            ON wi.work_id = w.work_id
        WHERE w.is_alphafold_related = TRUE
          AND wi.institution_id IS NOT NULL
    ),
    af_work_country_span AS (
        SELECT
            work_id,
            COUNT(DISTINCT country_code) AS work_country_span
        FROM af_work_institutions
        WHERE country_code IS NOT NULL
        GROUP BY 1
    ),
    institution_network_proxy AS (
        SELECT
            awi.institution_id,
            awi.institution_name,
            awi.country_code,
            COUNT(DISTINCT awi.work_id) AS n_af_works,
            AVG(COALESCE(awcs.work_country_span, 1)) AS avg_partner_country_span,
            SUM(CASE WHEN COALESCE(awcs.work_country_span, 1) > 1 THEN 1 ELSE 0 END) AS n_cross_border_works
        FROM af_work_institutions AS awi
        LEFT JOIN af_work_country_span AS awcs
            ON awi.work_id = awcs.work_id
        GROUP BY 1, 2, 3
    )
    SELECT *
    FROM institution_network_proxy
    ORDER BY n_cross_border_works DESC, n_af_works DESC
    LIMIT 20
    """).df()
    return (institution_network_proxy_df,)


@app.cell(hide_code=True)
def _(alt, institution_network_proxy_df):
    institution_network_proxy_chart = alt.Chart(institution_network_proxy_df).mark_circle(opacity=0.8).encode(
        x=alt.X("n_af_works:Q", title="Number of AF-related works"),
        y=alt.Y("n_cross_border_works:Q", title="Number of cross-border AF works"),
        size=alt.Size("avg_partner_country_span:Q", title="Average partner country span"),
        color=alt.Color("country_code:N", title="Country"),
        tooltip=[
            alt.Tooltip("institution_name:N", title="Institution"),
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("n_af_works:Q", title="AF-related works", format=".0f"),
            alt.Tooltip("n_cross_border_works:Q", title="Cross-border AF works", format=".0f"),
            alt.Tooltip("avg_partner_country_span:Q", title="Average partner country span", format=".2f"),
        ],
    ).properties(
        title="Institutional collaboration network proxy in AF-related research",
        width=820,
        height=460,
    )

    institution_network_proxy_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Institutional network figure: why the proxy view is used here

    对于机构层面，真正的节点—边网络图在全量数据下通常会非常拥挤，因此这里保留前面的 **institutional collaboration network proxy** 作为更可读、也更稳定的机构网络展示方式。

    ### 它对应的网络含义是：

    - x 轴的 **AF-related works** 近似表示机构在 AF 网络中的产出规模；
    - y 轴的 **cross-border AF works** 近似表示机构参与国际协作网络的频率；
    - 气泡大小的 **average partner country span** 近似表示机构所连接合作网络的国际范围；
    - 因而位于图右上方、同时气泡较大的机构，可以理解为更接近机构网络中的“组织核心”与“国际桥梁节点”。

    ### 为什么这张图仍然有价值

    虽然它不是传统意义上的节点—边网络图，但它保留了机构网络分析最重要的三个维度：

    1. **产出规模**：哪些机构在 AF 相关研究中最活跃；
    2. **跨国嵌入度**：哪些机构更频繁地参与国际合作；
    3. **合作范围**：哪些机构连接到更广泛的国家网络。

    因此，这张代理图非常适合作为机构合作网络图的论文展示版本，因为它在可读性、稳定性和解释力之间做了更好的平衡。
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Network structure interpretation

    结合国家合作边与机构网络代理图，可以把 AlphaFold 的协作变化理解为一种**跨尺度的网络重组**：

    - 在国家层面，重点不只是“合作是否增加”，而是“哪些国家之间构成了高强度连接”；
    - 在机构层面，重点不只是“哪些机构高产”，而是“哪些机构更深地嵌入了跨国协作网络”。

    ### 如何判断是否发生协作结构重构

    如果观察到：

    - 以往不那么居中的国家开始进入高强度合作边；
    - 不同国家的关键机构同时进入网络代理图的右上区域；
    - 跨国合作论文占比和跨国机构合作占比同时上升；

    那么可以认为 AlphaFold 不只是提高了合作规模，还可能推动了知识生产组织方式的结构性变化。

    但如果结果显示：

    - 最强合作边仍然集中在传统科研强国之间；
    - 机构网络代理图中的核心节点仍然主要来自少数头部国家；
    - 跨国合作虽然增加，但桥梁角色没有明显扩散；

    那么更合理的解释是：

    **AlphaFold 扩大了国际协作网络，但这种扩张更多体现为原有核心国家和核心机构之间联系的强化，而不是协作网络中心的根本转移。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Part 5 synthesis: what do collaboration patterns imply?

    结合前面的国家合作、机构合作与网络结构代理分析，可以把 AlphaFold 对知识生产组织方式的影响概括为三点：

    1. **AF 相关研究更容易体现出跨国协作特征。** 无论是平均国家数、跨国合作论文占比，还是跨国机构合作占比，只要 AF 相关论文系统性高于 Non-AF，就说明 AlphaFold 相关知识生产更依赖国际合作。
    2. **协作关系不仅扩张，而且呈现出核心通道。** Top country pairs 说明 AF 相关国际合作并不是均匀扩散，而是沿着少数关键国家对形成高强度连接。
    3. **组织核心仍然可能集中于少数头部机构。** 如果 top institutions 和机构网络代理图都表明少数机构同时具有高产出与高跨国合作嵌入度，那么 AF 的国际协作扩张并不自动意味着组织核心的去中心化。

    因此，Part 5 的实质性结论是：

    **AlphaFold 相关研究更依赖国际和跨机构合作，但这种合作是否真正改变了全球知识生产的组织结构，取决于合作网络的中心是否发生转移，而不仅仅是合作规模本身是否扩大。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Linking Part 5 back to Part 4: do collaboration changes support a spatial reconfiguration?

    Part 5 对 Part 4 的意义在于，它把“空间分布是否变化”进一步推进到“知识生产的组织方式是否变化”。

    如果前面 Part 1–3 表明：

    - adoption 正在扩散；
    - 但空间不平等仍然较高；

    那么 Part 5 可以帮助进一步判断：

    - 扩散是否伴随着新的国际协作中心形成；
    - 新的桥梁国家与关键机构是否进入网络核心；
    - 组织结构是否真正从旧有中心体系中转移出来。

    如果协作网络结果显示：

    - 最强国家合作边仍然集中在传统科研强国之间；
    - 头部机构仍主要来自少数高能力国家；
    - 跨国合作增加，但核心节点并未显著更替；

    那么更合理的解释仍然是：

    **AlphaFold 改变了全球知识生产的协作密度与扩散范围，但尚不足以证明全球科研生产的空间结构已经发生根本重构。更准确的说法是：它强化并延展了原有中心网络，而不是彻底改写了它。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Can the collaboration network be visualized more directly?

    可以，而且从直觉上讲，**真正的网络图**确实会比当前的“边强度图 + 机构网络代理图”更形象。尤其是如果你的研究问题强调：

    - 哪些国家 / 机构处在网络中心；
    - 哪些节点扮演桥梁角色；
    - 是否形成多中心结构；
    - 核心—外围格局是否被打破；

    那么网络图会有更强的表现力。

    ### 1. 国家合作网络图

    最直观的方案是：

    - **节点 = 国家**
    - **边 = 合作次数**
    - **节点大小 = AF 相关论文数或加权 degree**
    - **边粗细 = 国家对合作强度**
    - **节点颜色 = 地区或国家类型**

    这种图的优势是：

    - 可以直接看到哪些国家是 hub；
    - 可以识别哪些国家位于网络中心、哪些更边缘；
    - 可以观察网络是否从少数核心国家向更广泛国家扩展。

    ### 2. 机构合作网络图

    最直观的方案是：

    - **节点 = 机构**
    - **边 = 共著关系 / 共现关系**
    - **节点大小 = AF 论文数或加权 degree**
    - **边粗细 = 合作次数**
    - **节点颜色 = 所在国家**

    这种图可以直接展示：

    - 哪些机构构成组织核心；
    - 是否出现跨国机构团簇；
    - 协作是否仍然集中在少数头部机构。

    ### 为什么当前 notebook 先用“代理图”而不是直接画网络图

    这是因为真实网络图虽然直观，但也有几个常见问题：

    1. **节点和边一多就会非常拥挤**，尤其是机构层面；
    2. 力导向网络布局往往受随机初始化影响，结果不够稳定；
    3. 对论文展示来说，密集网络图有时不如条形图和散点代理图更容易阅读；
    4. 在 notebook 环境里，如果不先做筛选（例如只保留 top 30 countries 或 top 50 institutions），直接全量画网络通常会过于杂乱。

    ### 更适合论文展示的折中方案

    如果后面真的要增加更形象的网络图，推荐这样做：

    #### 国家层面

    - 只保留 **top 20 或 top 30 国家**；
    - 只显示 **top collaboration edges**；
    - 采用网络图或弧线图展示国家间连接。

    #### 机构层面

    - 只保留 **AF 论文数达到阈值的机构**；
    - 或只保留 **top 50 institutions**；
    - 再画机构合作网络图，避免完全不可读。

    ### 推荐的视觉方案排序

    如果按“论文中的可读性”来排序，我建议：

    1. **Top collaboration edges bar chart**：最稳，最容易读；
    2. **机构网络代理散点图**：适合比较“高产出 + 高跨国嵌入”；
    3. **国家合作网络图（筛选后）**：更形象，适合展示核心—桥梁—外围；
    4. **机构合作网络图（筛选后）**：信息量最大，但也最容易拥挤。

    ### 实际建议

    因此，如果你下一步要进一步增强可视化表现力，最值得优先增加的是：

    - **一个筛选后的国家合作网络图**；
    - **一个筛选后的机构合作网络图**；

    并且都应建立在“只保留核心节点与强边”的基础上。这样既能更形象地表现协作网络，又不会牺牲论文展示时的可读性。
    """)
    return


@app.cell(hide_code=True)
def _(country_pair_edges_af_df, country_trend_df, np):
    country_network_edges_df = country_pair_edges_af_df.groupby([
        "country_code_1",
        "country_code_2",
    ], as_index=False)["edge_weight"].sum()

    country_network_nodes_df = country_trend_df.groupby("country_code", as_index=False)["n_af_works"].sum()
    country_network_nodes_df = country_network_nodes_df.sort_values("n_af_works", ascending=False).head(20).copy()
    country_network_node_codes = country_network_nodes_df["country_code"].tolist()

    country_network_edges_filtered_df = country_network_edges_df[
        country_network_edges_df["country_code_1"].isin(country_network_node_codes)
        & country_network_edges_df["country_code_2"].isin(country_network_node_codes)
    ].sort_values("edge_weight", ascending=False).head(40).copy()

    _country_nodes_sorted = sorted(country_network_node_codes)
    _country_node_count = len(_country_nodes_sorted)
    _country_angles = np.linspace(0, 2 * np.pi, _country_node_count, endpoint=False)
    country_network_positions = {
        _country_nodes_sorted[_i]: (
            float(np.cos(_country_angles[_i])),
            float(np.sin(_country_angles[_i])),
        )
        for _i in range(_country_node_count)
    }

    country_network_nodes_plot_df = country_network_nodes_df.copy()
    country_network_nodes_plot_df["x"] = country_network_nodes_plot_df["country_code"].map(
        lambda _code: country_network_positions[_code][0]
    )
    country_network_nodes_plot_df["y"] = country_network_nodes_plot_df["country_code"].map(
        lambda _code: country_network_positions[_code][1]
    )

    _edge_weight_max = country_network_edges_filtered_df["edge_weight"].max() if len(country_network_edges_filtered_df) > 0 else 1
    country_network_edges_plot_df = country_network_edges_filtered_df.copy()
    country_network_edges_plot_df["x"] = country_network_edges_plot_df["country_code_1"].map(
        lambda _code: country_network_positions[_code][0]
    )
    country_network_edges_plot_df["y"] = country_network_edges_plot_df["country_code_1"].map(
        lambda _code: country_network_positions[_code][1]
    )
    country_network_edges_plot_df["x2"] = country_network_edges_plot_df["country_code_2"].map(
        lambda _code: country_network_positions[_code][0]
    )
    country_network_edges_plot_df["y2"] = country_network_edges_plot_df["country_code_2"].map(
        lambda _code: country_network_positions[_code][1]
    )
    country_network_edges_plot_df["edge_width"] = 1 + 6 * (
        country_network_edges_plot_df["edge_weight"] / _edge_weight_max
    )
    country_network_edges_plot_df["country_pair"] = (
        country_network_edges_plot_df["country_code_1"] + " – " + country_network_edges_plot_df["country_code_2"]
    )
    return (
        country_network_edges_filtered_df,
        country_network_nodes_df,
        country_network_positions,
    )


@app.cell(hide_code=True)
def _(
    country_network_edges_filtered_df,
    country_network_nodes_df,
    country_network_positions,
    go,
):
    country_network_fig = go.Figure()

    _edge_weight_max = country_network_edges_filtered_df["edge_weight"].max() if len(country_network_edges_filtered_df) > 0 else 1
    for _, _edge_row in country_network_edges_filtered_df.iterrows():
        _x0, _y0 = country_network_positions[_edge_row["country_code_1"]]
        _x1, _y1 = country_network_positions[_edge_row["country_code_2"]]
        _edge_width = 1 + 7 * (_edge_row["edge_weight"] / _edge_weight_max)
        country_network_fig.add_trace(go.Scatter(
            x=[_x0, _x1, None],
            y=[_y0, _y1, None],
            mode="lines",
            line=dict(width=_edge_width, color="rgba(120,120,120,0.35)"),
            hoverinfo="text",
            text=[
                f"{_edge_row['country_code_1']} – {_edge_row['country_code_2']}<br>Collaborations: {_edge_row['edge_weight']:.0f}",
                f"{_edge_row['country_code_1']} – {_edge_row['country_code_2']}<br>Collaborations: {_edge_row['edge_weight']:.0f}",
                None,
            ],
            showlegend=False,
        ))

    _node_size_max = country_network_nodes_df["n_af_works"].max() if len(country_network_nodes_df) > 0 else 1
    _node_x = []
    _node_y = []
    _node_text = []
    _node_size = []
    _node_label = []
    for _, _node_row in country_network_nodes_df.iterrows():
        _node_code = _node_row["country_code"]
        _x, _y = country_network_positions[_node_code]
        _node_x.append(_x)
        _node_y.append(_y)
        _node_label.append(_node_code)
        _node_size.append(18 + 42 * (_node_row["n_af_works"] / _node_size_max))
        _node_text.append(
            f"Country: {_node_code}<br>Total AF works: {_node_row['n_af_works']:.0f}"
        )

    country_network_fig.add_trace(go.Scatter(
        x=_node_x,
        y=_node_y,
        mode="markers+text",
        text=_node_label,
        textposition="top center",
        marker=dict(
            size=_node_size,
            color="#1f77b4",
            line=dict(width=1, color="white"),
            opacity=0.9,
        ),
        hovertext=_node_text,
        hoverinfo="text",
        showlegend=False,
    ))

    country_network_fig.update_layout(
        title="Country collaboration network in AF-related research (top countries and strongest edges)",
        width=900,
        height=700,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    country_network_fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the country collaboration network

    这张图把 AF 相关国家合作关系以网络形式展示出来：

    - **节点大小**表示该国在 AF 相关研究中的总产出；
    - **边粗细**表示两个国家之间的合作强度；
    - **节点之间连接越多、边越粗**，说明该国家越可能处在国际协作网络的核心位置。

    ### 如何理解

    - 如果少数国家拥有最大的节点并连接最多粗边，说明它们构成了 AF 协作网络的核心；
    - 如果某些国家本身产出不一定最高，但连接到多个关键国家，则可能扮演“桥梁国家”的角色；
    - 如果网络明显围绕少数国家展开，而外围国家连接较弱，则说明协作网络仍然表现出较强的核心—外围结构。

    ### 这张图的重要意义

    与前面的 top collaboration pairs 不同，这张图更强调网络整体形态，而不仅仅是单条合作边。它有助于回答：

    **AlphaFold 相关国际合作是否形成了新的多中心网络，还是仍然围绕少数科研强国展开。**
    """)
    return


@app.cell(hide_code=True)
def _(
    analysis_duckdb,
    institution_network_proxy_df,
    np,
    work_institutions_glob,
    works_glob,
):
    institution_network_edges_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    af_work_institutions AS (
        SELECT DISTINCT
            wi.work_id,
            wi.institution_id,
            wi.institution_name,
            wi.country_code
        FROM read_parquet('{work_institutions_glob}') AS wi
        INNER JOIN work_flags AS w
            ON wi.work_id = w.work_id
        WHERE w.is_alphafold_related = TRUE
          AND wi.institution_id IS NOT NULL
    ),
    institution_pairs AS (
        SELECT
            a.work_id,
            LEAST(a.institution_id, b.institution_id) AS institution_id_1,
            GREATEST(a.institution_id, b.institution_id) AS institution_id_2,
            a.institution_name AS institution_name_1,
            b.institution_name AS institution_name_2,
            a.country_code AS country_code_1,
            b.country_code AS country_code_2
        FROM af_work_institutions AS a
        INNER JOIN af_work_institutions AS b
            ON a.work_id = b.work_id
           AND a.institution_id < b.institution_id
    )
    SELECT
        institution_id_1,
        institution_id_2,
        institution_name_1,
        institution_name_2,
        country_code_1,
        country_code_2,
        COUNT(*) AS edge_weight
    FROM institution_pairs
    GROUP BY 1, 2, 3, 4, 5, 6
    ORDER BY edge_weight DESC
    LIMIT 60
    """).df()

    institution_network_nodes_df = institution_network_proxy_df.copy().head(30)
    institution_network_node_ids = institution_network_nodes_df["institution_id"].tolist()

    institution_network_edges_filtered_df = institution_network_edges_df[
        institution_network_edges_df["institution_id_1"].isin(institution_network_node_ids)
        & institution_network_edges_df["institution_id_2"].isin(institution_network_node_ids)
    ].copy()

    _institution_nodes_sorted = institution_network_nodes_df["institution_id"].tolist()
    _institution_node_count = len(_institution_nodes_sorted)
    _institution_angles = np.linspace(0, 2 * np.pi, _institution_node_count, endpoint=False)
    institution_network_positions = {
        _institution_nodes_sorted[_i]: (
            float(np.cos(_institution_angles[_i])),
            float(np.sin(_institution_angles[_i])),
        )
        for _i in range(_institution_node_count)
    }
    return (
        institution_network_edges_filtered_df,
        institution_network_nodes_df,
        institution_network_positions,
    )


@app.cell(hide_code=True)
def _(
    go,
    institution_network_edges_filtered_df,
    institution_network_nodes_df,
    institution_network_positions,
):
    institution_network_fig = go.Figure()

    _institution_edge_weight_max = institution_network_edges_filtered_df["edge_weight"].max() if len(institution_network_edges_filtered_df) > 0 else 1
    for _, _edge_row in institution_network_edges_filtered_df.iterrows():
        _x0, _y0 = institution_network_positions[_edge_row["institution_id_1"]]
        _x1, _y1 = institution_network_positions[_edge_row["institution_id_2"]]
        _edge_width = 1 + 6 * (_edge_row["edge_weight"] / _institution_edge_weight_max)
        institution_network_fig.add_trace(go.Scatter(
            x=[_x0, _x1, None],
            y=[_y0, _y1, None],
            mode="lines",
            line=dict(width=_edge_width, color="rgba(140,140,140,0.30)"),
            hoverinfo="text",
            text=[
                f"{_edge_row['institution_name_1']} – {_edge_row['institution_name_2']}<br>Collaborations: {_edge_row['edge_weight']:.0f}",
                f"{_edge_row['institution_name_1']} – {_edge_row['institution_name_2']}<br>Collaborations: {_edge_row['edge_weight']:.0f}",
                None,
            ],
            showlegend=False,
        ))

    _institution_node_size_max = institution_network_nodes_df["n_af_works"].max() if len(institution_network_nodes_df) > 0 else 1
    _institution_node_x = []
    _institution_node_y = []
    _institution_node_text = []
    _institution_node_size = []
    _institution_node_label = []
    for _, _node_row in institution_network_nodes_df.iterrows():
        _node_id = _node_row["institution_id"]
        _x, _y = institution_network_positions[_node_id]
        _institution_node_x.append(_x)
        _institution_node_y.append(_y)
        _institution_node_label.append(_node_row["institution_name"][:20])
        _institution_node_size.append(14 + 34 * (_node_row["n_af_works"] / _institution_node_size_max))
        _institution_node_text.append(
            f"Institution: {_node_row['institution_name']}<br>Country: {_node_row['country_code']}<br>AF works: {_node_row['n_af_works']:.0f}<br>Cross-border works: {_node_row['n_cross_border_works']:.0f}"
        )

    institution_network_fig.add_trace(go.Scatter(
        x=_institution_node_x,
        y=_institution_node_y,
        mode="markers+text",
        text=_institution_node_label,
        textposition="top center",
        marker=dict(
            size=_institution_node_size,
            color="#d62728",
            line=dict(width=1, color="white"),
            opacity=0.9,
        ),
        hovertext=_institution_node_text,
        hoverinfo="text",
        showlegend=False,
    ))

    institution_network_fig.update_layout(
        title="Institution collaboration network in AF-related research (top institutions and strongest edges)",
        width=980,
        height=760,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    institution_network_fig
    return


@app.cell(hide_code=True)
def _(mo):
    country_network_year_slider = mo.ui.slider(
        2021,
        2025,
        value=2025,
        step=1,
        label="Select year for country collaboration network",
    )

    institution_network_year_slider = mo.ui.slider(
        2021,
        2025,
        value=2025,
        step=1,
        label="Select year for institution collaboration network",
    )

    mo.vstack([country_network_year_slider, institution_network_year_slider])
    return country_network_year_slider, institution_network_year_slider


@app.cell(hide_code=True)
def _(
    country_network_year_slider,
    country_pair_edges_df,
    country_trend_df,
    np,
):
    country_network_year_base_df = country_pair_edges_df[
        country_pair_edges_df["publication_year"] == country_network_year_slider.value
    ].copy()

    country_network_af_edges_year_df = country_network_year_base_df[
        country_network_year_base_df["is_alphafold_related"] == True
    ].copy()
    country_network_non_af_edges_year_df = country_network_year_base_df[
        country_network_year_base_df["is_alphafold_related"] == False
    ].copy()

    country_network_nodes_year_df = country_trend_df[
        country_trend_df["publication_year"] == country_network_year_slider.value
    ][["country_code", "n_af_works", "n_works"]].copy()
    country_network_nodes_year_df["n_non_af_works"] = (
        country_network_nodes_year_df["n_works"] - country_network_nodes_year_df["n_af_works"]
    )

    country_network_nodes_af_year_df = country_network_nodes_year_df.sort_values(
        "n_af_works", ascending=False
    ).head(20).copy()
    country_network_nodes_non_af_year_df = country_network_nodes_year_df.sort_values(
        "n_non_af_works", ascending=False
    ).head(20).copy()

    country_network_af_codes_year = country_network_nodes_af_year_df["country_code"].tolist()
    country_network_non_af_codes_year = country_network_nodes_non_af_year_df["country_code"].tolist()

    country_network_af_edges_filtered_year_df = country_network_af_edges_year_df[
        country_network_af_edges_year_df["country_code_1"].isin(country_network_af_codes_year)
        & country_network_af_edges_year_df["country_code_2"].isin(country_network_af_codes_year)
    ].sort_values("edge_weight", ascending=False).head(40).copy()

    country_network_non_af_edges_filtered_year_df = country_network_non_af_edges_year_df[
        country_network_non_af_edges_year_df["country_code_1"].isin(country_network_non_af_codes_year)
        & country_network_non_af_edges_year_df["country_code_2"].isin(country_network_non_af_codes_year)
    ].sort_values("edge_weight", ascending=False).head(40).copy()

    _country_network_year_codes_union = sorted(
        set(country_network_af_codes_year) | set(country_network_non_af_codes_year)
    )
    _country_network_year_angles = np.linspace(
        0,
        2 * np.pi,
        len(_country_network_year_codes_union),
        endpoint=False,
    )
    country_network_year_positions = {
        _country_network_year_codes_union[_i]: (
            float(np.cos(_country_network_year_angles[_i])),
            float(np.sin(_country_network_year_angles[_i])),
        )
        for _i in range(len(_country_network_year_codes_union))
    }
    return (
        country_network_af_edges_filtered_year_df,
        country_network_nodes_af_year_df,
        country_network_nodes_non_af_year_df,
        country_network_non_af_edges_filtered_year_df,
        country_network_year_positions,
    )


@app.cell(hide_code=True)
def _(
    country_network_af_edges_filtered_year_df,
    country_network_nodes_af_year_df,
    country_network_nodes_non_af_year_df,
    country_network_non_af_edges_filtered_year_df,
    country_network_year_positions,
    country_network_year_slider,
    go,
    mo,
):
    def _build_country_network_figure(_edges_df, _nodes_df, _node_value_col, _title, _node_color):
        _fig = go.Figure()
        _edge_max = _edges_df["edge_weight"].max() if len(_edges_df) > 0 else 1
        for _, _edge_row in _edges_df.iterrows():
            _x0, _y0 = country_network_year_positions[_edge_row["country_code_1"]]
            _x1, _y1 = country_network_year_positions[_edge_row["country_code_2"]]
            _edge_width = 1 + 7 * (_edge_row["edge_weight"] / _edge_max)
            _fig.add_trace(go.Scatter(
                x=[_x0, _x1, None],
                y=[_y0, _y1, None],
                mode="lines",
                line=dict(width=_edge_width, color="rgba(120,120,120,0.35)"),
                hoverinfo="text",
                text=[
                    f"{_edge_row['country_code_1']} – {_edge_row['country_code_2']}<br>Collaborations: {_edge_row['edge_weight']:.0f}",
                    f"{_edge_row['country_code_1']} – {_edge_row['country_code_2']}<br>Collaborations: {_edge_row['edge_weight']:.0f}",
                    None,
                ],
                showlegend=False,
            ))

        _node_max = _nodes_df[_node_value_col].max() if len(_nodes_df) > 0 else 1
        _node_x = []
        _node_y = []
        _node_text = []
        _node_size = []
        _node_label = []
        for _, _node_row in _nodes_df.iterrows():
            _node_code = _node_row["country_code"]
            _x, _y = country_network_year_positions[_node_code]
            _node_x.append(_x)
            _node_y.append(_y)
            _node_label.append(_node_code)
            _node_size.append(18 + 42 * (_node_row[_node_value_col] / _node_max if _node_max > 0 else 0))
            _node_text.append(
                f"Country: {_node_code}<br>Works: {_node_row[_node_value_col]:.0f}"
            )

        _fig.add_trace(go.Scatter(
            x=_node_x,
            y=_node_y,
            mode="markers+text",
            text=_node_label,
            textposition="top center",
            marker=dict(
                size=_node_size,
                color=_node_color,
                line=dict(width=1, color="white"),
                opacity=0.9,
            ),
            hovertext=_node_text,
            hoverinfo="text",
            showlegend=False,
        ))

        _fig.update_layout(
            title=_title,
            width=900,
            height=700,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            plot_bgcolor="white",
            margin=dict(l=20, r=20, t=60, b=20),
        )
        return _fig

    country_network_af_year_fig = _build_country_network_figure(
        country_network_af_edges_filtered_year_df,
        country_network_nodes_af_year_df,
        "n_af_works",
        f"Country collaboration network in AF-related research ({country_network_year_slider.value})",
        "#1f77b4",
    )

    country_network_non_af_year_fig = _build_country_network_figure(
        country_network_non_af_edges_filtered_year_df,
        country_network_nodes_non_af_year_df,
        "n_non_af_works",
        f"Country collaboration network in Non-AF research ({country_network_year_slider.value})",
        "#2ca02c",
    )

    mo.vstack([country_network_af_year_fig, country_network_non_af_year_fig])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Comparing AF and Non-AF country collaboration networks

    上面两张网络图使用同一个年份滑块进行对比：

    - **蓝色网络**：AF 相关研究的国家合作网络；
    - **绿色网络**：Non-AF 研究的国家合作网络。

    ### 如何比较

    - 比较节点大小：看 AF 与 Non-AF 是否由同一批国家主导；
    - 比较边的粗细与分布：看 AF 的合作是否更集中在少数强边上；
    - 比较网络形态：看 AF 网络是否更核心化，或者是否出现新的桥梁国家。

    ### 为什么这组图重要

    如果 AF 网络比 Non-AF 网络更集中、更围绕少数国家展开，那么这说明：

    **AlphaFold 不只是改变了研究内容，也可能改变了国际协作网络的组织结构，并强化了少数国家在协作体系中的中心地位。**
    """)
    return


@app.cell(hide_code=True)
def _(
    country_geo_coords_map,
    country_network_cumulative_af_edges_df,
    country_network_cumulative_af_nodes_df,
    country_network_cumulative_non_af_edges_df,
    country_network_cumulative_non_af_nodes_df,
    go,
    mo,
    np,
):
    def _build_plotly_geo_collab_figure(_edges_df, _nodes_df, _value_col, _title):
        _nodes_top_df = _nodes_df.sort_values(_value_col, ascending=False).head(25).copy()
        _node_codes = _nodes_top_df["country_code"].dropna().tolist()

        _filtered_edges_df = _edges_df[
            _edges_df["country_code_1"].isin(_node_codes)
            & _edges_df["country_code_2"].isin(_node_codes)
        ].sort_values("edge_weight", ascending=False).head(35).copy()

        _nodes_plot_df = _nodes_top_df.copy()
        _nodes_plot_df["lat"] = _nodes_plot_df["country_code"].map(
            lambda _code: country_geo_coords_map.get(_code, (None, None))[0]
        )
        _nodes_plot_df["lon"] = _nodes_plot_df["country_code"].map(
            lambda _code: country_geo_coords_map.get(_code, (None, None))[1]
        )
        _nodes_plot_df = _nodes_plot_df.dropna(subset=["lat", "lon"]).copy()

        _figure = go.Figure()
        _edge_weight_max = float(_filtered_edges_df["edge_weight"].max()) if len(_filtered_edges_df) > 0 else 1.0

        for _, _edge_row in _filtered_edges_df.iterrows():
            _source_code = _edge_row["country_code_1"]
            _target_code = _edge_row["country_code_2"]
            _source_coords = country_geo_coords_map.get(_source_code)
            _target_coords = country_geo_coords_map.get(_target_code)
            if _source_coords is None or _target_coords is None:
                continue

            _source_lat, _source_lon = _source_coords
            _target_lat, _target_lon = _target_coords
            _edge_weight_value = float(_edge_row["edge_weight"])
            _mid_lat = (_source_lat + _target_lat) / 2 + 6
            _mid_lon = (_source_lon + _target_lon) / 2
            _edge_width = 1.5 + 7.5 * (_edge_weight_value / _edge_weight_max if _edge_weight_max > 0 else 0)

            _figure.add_trace(go.Scattergeo(
                lon=[_source_lon, _mid_lon, _target_lon],
                lat=[_source_lat, _mid_lat, _target_lat],
                mode="lines",
                line=dict(width=_edge_width, color="rgba(220, 38, 38, 0.55)"),
                hovertemplate=(
                    f"{_source_code} - {_target_code}<br>"
                    f"Collaborations: {_edge_weight_value:,.0f}<extra></extra>"
                ),
                showlegend=False,
            ))

        _figure.add_trace(go.Scattergeo(
            lon=_nodes_plot_df["lon"],
            lat=_nodes_plot_df["lat"],
            mode="markers+text",
            text=_nodes_plot_df["country_code"],
            textposition="top center",
            marker=dict(
                size=np.clip(np.sqrt(_nodes_plot_df[_value_col]) / 6, 10, 34),
                color=_nodes_plot_df[_value_col],
                colorscale="Blues",
                cmin=float(_nodes_plot_df[_value_col].min()) if len(_nodes_plot_df) > 0 else 0.0,
                cmax=float(_nodes_plot_df[_value_col].max()) if len(_nodes_plot_df) > 0 else 1.0,
                line=dict(width=1.2, color="white"),
                colorbar=dict(title="Work count"),
                opacity=0.95,
            ),
            hovertemplate=(
                "Country: %{text}<br>"
                "Work count: %{marker.color:,.0f}<extra></extra>"
            ),
            showlegend=False,
        ))

        _figure.update_layout(
            title=_title,
            width=1200,
            height=760,
            margin=dict(l=10, r=10, t=60, b=10),
            paper_bgcolor="white",
            geo=dict(
                scope="world",
                projection_type="natural earth",
                showland=True,
                landcolor="#f8fafc",
                showcountries=True,
                countrycolor="#94a3b8",
                showocean=True,
                oceancolor="#eef6ff",
                showcoastlines=True,
                coastlinecolor="#cbd5e1",
                lataxis_showgrid=False,
                lonaxis_showgrid=False,
                bgcolor="white",
            ),
        )
        return _figure

    country_plotly_non_af_geo_fig = _build_plotly_geo_collab_figure(
        _edges_df=country_network_cumulative_non_af_edges_df,
        _nodes_df=country_network_cumulative_non_af_nodes_df.rename(columns={"node_size_value": "node_size_value_non_af"}),
        _value_col="node_size_value_non_af",
        _title="Country-to-country Non-AF scientific collaboration volume",
    )

    country_plotly_af_geo_fig = _build_plotly_geo_collab_figure(
        _edges_df=country_network_cumulative_af_edges_df,
        _nodes_df=country_network_cumulative_af_nodes_df.rename(columns={"node_size_value": "node_size_value_af"}),
        _value_col="node_size_value_af",
        _title="Country-to-country AF scientific collaboration volume",
    )

    mo.vstack([
        mo.md(f"""
    ### Plotly Geo collaboration maps

    - 上图：**Non-AF** 国家数量用不同深浅蓝色表示，红色连线表示跨国协作，线宽表示协作量
    - 下图：**AF** 国家数量用不同深浅蓝色表示，红色连线表示跨国协作，线宽表示协作量
    """),
        country_plotly_non_af_geo_fig,
        country_plotly_af_geo_fig,
    ])
    return


@app.cell
def _():
    from pyecharts import options as opts
    from pyecharts.charts import Geo
    from pyecharts.globals import ChartType
    from pyecharts.commons.utils import JsCode

    return


@app.cell
def _():
    import networkx as nx

    return


@app.cell(hide_code=True)
def _(
    build_plotly_network_figure,
    country_pair_edges_df,
    country_trend_df,
    mo,
):
    country_network_cumulative_edges_all_df = country_pair_edges_df.groupby(
        ["is_alphafold_related", "country_code_1", "country_code_2"],
        as_index=False,
    )["edge_weight"].sum()

    country_network_cumulative_nodes_all_df = country_trend_df.groupby("country_code", as_index=False).agg({
        "n_works": "sum",
        "n_af_works": "sum",
    })
    country_network_cumulative_nodes_all_df["n_non_af_works"] = (
        country_network_cumulative_nodes_all_df["n_works"] - country_network_cumulative_nodes_all_df["n_af_works"]
    )

    country_network_cumulative_af_nodes_df = country_network_cumulative_nodes_all_df[[
        "country_code", "n_af_works"
    ]].rename(columns={"n_af_works": "node_size_value"})
    country_network_cumulative_non_af_nodes_df = country_network_cumulative_nodes_all_df[[
        "country_code", "n_non_af_works"
    ]].rename(columns={"n_non_af_works": "node_size_value"})

    country_network_cumulative_af_edges_df = country_network_cumulative_edges_all_df[
        country_network_cumulative_edges_all_df["is_alphafold_related"] == True
    ].copy()
    country_network_cumulative_non_af_edges_df = country_network_cumulative_edges_all_df[
        country_network_cumulative_edges_all_df["is_alphafold_related"] == False
    ].copy()

    country_network_cumulative_af_fig = build_plotly_network_figure(
        nodes_df=country_network_cumulative_af_nodes_df,
        edges_df=country_network_cumulative_af_edges_df,
        node_id_col="country_code",
        node_label_col="country_code",
        node_size_col="node_size_value",
        edge_source_col="country_code_1",
        edge_target_col="country_code_2",
        edge_weight_col="edge_weight",
        title="Country collaboration network in AF-related research (cumulative, 2015–2025)",
        node_colorscale="Viridis",
        node_color_title="Node Connections",
        max_nodes=20,
        max_edges=40,
        label_truncate=12,
    )

    country_network_cumulative_non_af_fig = build_plotly_network_figure(
        nodes_df=country_network_cumulative_non_af_nodes_df,
        edges_df=country_network_cumulative_non_af_edges_df,
        node_id_col="country_code",
        node_label_col="country_code",
        node_size_col="node_size_value",
        edge_source_col="country_code_1",
        edge_target_col="country_code_2",
        edge_weight_col="edge_weight",
        title="Country collaboration network in Non-AF research (cumulative, 2015–2025)",
        node_colorscale="Viridis",
        node_color_title="Node Connections",
        max_nodes=20,
        max_edges=40,
        label_truncate=12,
    )

    mo.vstack([
        country_network_cumulative_af_fig,
        country_network_cumulative_non_af_fig,
    ])
    return (
        country_network_cumulative_af_edges_df,
        country_network_cumulative_af_nodes_df,
        country_network_cumulative_non_af_edges_df,
        country_network_cumulative_non_af_nodes_df,
    )


@app.cell(hide_code=True)
def _(
    build_circular_connectivity_figure,
    country_network_cumulative_af_edges_df,
    country_network_cumulative_af_nodes_df,
    country_network_cumulative_non_af_edges_df,
    country_network_cumulative_non_af_nodes_df,
    mo,
):
    country_network_cumulative_af_circle_ax = build_circular_connectivity_figure(
        nodes_df=country_network_cumulative_af_nodes_df,
        edges_df=country_network_cumulative_af_edges_df,
        node_id_col="country_code",
        node_label_col="country_code",
        node_size_col="node_size_value",
        edge_source_col="country_code_1",
        edge_target_col="country_code_2",
        edge_weight_col="edge_weight",
        title="Country collaboration network in AF-related research (cumulative, circular view)",
        max_nodes=20,
        max_edges=40,
        label_truncate=12,
    )

    country_network_cumulative_non_af_circle_ax = build_circular_connectivity_figure(
        nodes_df=country_network_cumulative_non_af_nodes_df,
        edges_df=country_network_cumulative_non_af_edges_df,
        node_id_col="country_code",
        node_label_col="country_code",
        node_size_col="node_size_value",
        edge_source_col="country_code_1",
        edge_target_col="country_code_2",
        edge_weight_col="edge_weight",
        title="Country collaboration network in Non-AF research (cumulative, circular view)",
        max_nodes=20,
        max_edges=40,
        label_truncate=12,
    )

    mo.vstack([
        country_network_cumulative_af_circle_ax,
        country_network_cumulative_non_af_circle_ax,
    ])
    return


@app.cell(hide_code=True)
def _(np, pd, plt):
    def build_circular_connectivity_figure(
        nodes_df: pd.DataFrame,
        edges_df: pd.DataFrame,
        node_id_col: str,
        node_label_col: str,
        node_size_col: str,
        edge_source_col: str,
        edge_target_col: str,
        edge_weight_col: str,
        title: str,
        max_nodes: int = 20,
        max_edges: int = 80,
        label_truncate: int = 24,
        line_color: str = "#FFD700",
        facecolor: str = "black",
    ) -> plt.Axes:
        _nodes_df = nodes_df.copy().sort_values(node_size_col, ascending=False).head(max_nodes).copy()
        _node_ids = _nodes_df[node_id_col].tolist()

        _edges_df = edges_df.copy()
        _edges_df = _edges_df[
            _edges_df[edge_source_col].isin(_node_ids)
            & _edges_df[edge_target_col].isin(_node_ids)
        ].sort_values(edge_weight_col, ascending=False).head(max_edges).copy()

        _n_nodes = len(_nodes_df)
        _angles = np.linspace(0, 2 * np.pi, _n_nodes, endpoint=False)
        _angle_map = {
            _node_ids[_i]: float(_angles[_i])
            for _i in range(_n_nodes)
        }
        _radius = 10.0

        _node_size_max = float(_nodes_df[node_size_col].max()) if _n_nodes > 0 else 1.0
        _degree_map = {node_id: 0 for node_id in _node_ids}
        for _, _edge_row in _edges_df.iterrows():
            _degree_map[_edge_row[edge_source_col]] = _degree_map.get(_edge_row[edge_source_col], 0) + 1
            _degree_map[_edge_row[edge_target_col]] = _degree_map.get(_edge_row[edge_target_col], 0) + 1

        _figure, _ax = plt.subplots(figsize=(9, 9), facecolor=facecolor, subplot_kw=dict(polar=True))
        _ax.set_facecolor(facecolor)
        _ax.set_theta_offset(np.pi / 2)
        _ax.set_theta_direction(-1)
        _ax.grid(False)
        _ax.set_xticks([])
        _ax.set_yticks([])
        _ax.spines["polar"].set_visible(False)

        _edge_weight_max = float(_edges_df[edge_weight_col].max()) if len(_edges_df) > 0 else 1.0
        for _, _edge_row in _edges_df.iterrows():
            _source_id = _edge_row[edge_source_col]
            _target_id = _edge_row[edge_target_col]
            _theta0 = _angle_map[_source_id]
            _theta1 = _angle_map[_target_id]
            _weight_value = float(_edge_row[edge_weight_col])
            _line_count = max(1, min(int(round(_weight_value)), 24))
            _base_inner_radius = _radius * (0.48 - 0.18 * (_weight_value / _edge_weight_max if _edge_weight_max > 0 else 0))

            _angle_diff = ((_theta1 - _theta0 + np.pi) % (2 * np.pi)) - np.pi
            _theta_path = np.linspace(_theta0, _theta0 + _angle_diff, 120)
            _curve_phase = np.linspace(0, np.pi, 120)

            for _line_index in range(_line_count):
                _offset_scale = (_line_index - (_line_count - 1) / 2) / max(_line_count, 1)
                _inner_radius = _base_inner_radius + _offset_scale * 0.35
                _radius_path = _radius - (_radius - _inner_radius) * np.sin(_curve_phase)
                _ax.plot(
                    _theta_path,
                    _radius_path,
                    color=line_color,
                    linewidth=0.35,
                    alpha=0.22,
                    solid_capstyle="round",
                    zorder=1,
                )

        _node_thetas = []
        _node_radii = []
        _node_sizes = []
        _node_colors = []
        for _, _node_row in _nodes_df.iterrows():
            _node_id = _node_row[node_id_col]
            _node_thetas.append(_angle_map[_node_id])
            _node_radii.append(_radius)
            _node_sizes.append(40 + 220 * (float(_node_row[node_size_col]) / _node_size_max if _node_size_max > 0 else 0))
            _node_colors.append(_degree_map.get(_node_id, 0))

        _ax.scatter(
            _node_thetas,
            _node_radii,
            s=_node_sizes,
            c=_node_colors,
            cmap="viridis_r",
            edgecolors="white",
            linewidths=1.0,
            zorder=3,
        )

        for _, _node_row in _nodes_df.iterrows():
            _node_id = _node_row[node_id_col]
            _theta = _angle_map[_node_id]
            _label_value = str(_node_row[node_label_col])
            _display_label = _label_value if len(_label_value) <= label_truncate else _label_value[:label_truncate - 1] + "…"
            _rotation = np.degrees(_theta)
            _text_rotation = _rotation - 90
            _ha = "left"
            if np.pi / 2 < _theta < 3 * np.pi / 2:
                _text_rotation += 180
                _ha = "right"
            _ax.text(
                _theta,
                _radius + 1.4,
                _display_label,
                color="white",
                fontsize=9,
                rotation=_text_rotation,
                rotation_mode="anchor",
                ha=_ha,
                va="center",
                zorder=4,
            )

        _ax.set_title(title, color="white", fontsize=14, pad=24)
        _ax.set_rlim(0, _radius + 2.8)
        return _ax

    return (build_circular_connectivity_figure,)


@app.cell(hide_code=True)
def _(go, np, pd):
    def build_plotly_network_figure(
        nodes_df: pd.DataFrame,
        edges_df: pd.DataFrame,
        node_id_col: str,
        node_label_col: str,
        node_size_col: str,
        edge_source_col: str,
        edge_target_col: str,
        edge_weight_col: str,
        title: str,
        node_colorscale: str = "Viridis",
        node_color_title: str = "Node Connections",
        max_nodes: int = 20,
        max_edges: int = 40,
        label_truncate: int = 24,
    ) -> go.Figure:
        _nodes_df = nodes_df.copy().sort_values(node_size_col, ascending=False).head(max_nodes).copy()
        _node_ids = _nodes_df[node_id_col].tolist()

        _edges_df = edges_df.copy()
        _edges_df = _edges_df[
            _edges_df[edge_source_col].isin(_node_ids)
            & _edges_df[edge_target_col].isin(_node_ids)
        ].sort_values(edge_weight_col, ascending=False).head(max_edges).copy()

        if len(_nodes_df) == 0:
            _empty_fig = go.Figure()
            _empty_fig.update_layout(title=title)
            return _empty_fig

        _angles = np.linspace(0, 2 * np.pi, len(_node_ids), endpoint=False)
        _positions = {
            _node_ids[_i]: (float(np.cos(_angles[_i])), float(np.sin(_angles[_i])))
            for _i in range(len(_node_ids))
        }

        _degree_map = {node_id: 0 for node_id in _node_ids}
        for _, _edge_row in _edges_df.iterrows():
            _degree_map[_edge_row[edge_source_col]] = _degree_map.get(_edge_row[edge_source_col], 0) + 1
            _degree_map[_edge_row[edge_target_col]] = _degree_map.get(_edge_row[edge_target_col], 0) + 1

        _figure = go.Figure()
        _edge_weight_max = float(_edges_df[edge_weight_col].max()) if len(_edges_df) > 0 else 1.0

        for _, _edge_row in _edges_df.iterrows():
            _source_id = _edge_row[edge_source_col]
            _target_id = _edge_row[edge_target_col]
            _x0, _y0 = _positions[_source_id]
            _x1, _y1 = _positions[_target_id]
            _edge_weight_value = float(_edge_row[edge_weight_col])
            _source_label_df = _nodes_df.loc[_nodes_df[node_id_col] == _source_id, node_label_col]
            _target_label_df = _nodes_df.loc[_nodes_df[node_id_col] == _target_id, node_label_col]
            _source_label = str(_source_label_df.iloc[0]) if len(_source_label_df) > 0 else str(_source_id)
            _target_label = str(_target_label_df.iloc[0]) if len(_target_label_df) > 0 else str(_target_id)

            _line_count = max(1, min(int(round(_edge_weight_value)), 24))
            _curvature_base = 0.08 + 0.20 * (_edge_weight_value / _edge_weight_max if _edge_weight_max > 0 else 0)
            _mx = (_x0 + _x1) / 2
            _my = (_y0 + _y1) / 2
            _toward_center_x = -_mx
            _toward_center_y = -_my
            _norm = (_toward_center_x ** 2 + _toward_center_y ** 2) ** 0.5
            if _norm == 0:
                _toward_center_x, _toward_center_y = 0.0, 0.0
            else:
                _toward_center_x /= _norm
                _toward_center_y /= _norm

            for _line_index in range(_line_count):
                _offset_scale = (_line_index - (_line_count - 1) / 2) / max(_line_count, 1)
                _curvature = _curvature_base * (1 + 0.35 * _offset_scale)
                _cx = _mx + _toward_center_x * _curvature
                _cy = _my + _toward_center_y * _curvature

                _figure.add_trace(go.Scatter(
                    x=[_x0, _cx, _x1],
                    y=[_y0, _cy, _y1],
                    mode="lines",
                    line=dict(width=0.8, color="rgba(255, 215, 0, 0.42)", shape="spline", smoothing=1.15),
                    hoverinfo="text",
                    text=[
                        f"{_source_label} – {_target_label}<br>Collaborations: {_edge_weight_value:,.0f}",
                        f"{_source_label} – {_target_label}<br>Collaborations: {_edge_weight_value:,.0f}",
                        f"{_source_label} – {_target_label}<br>Collaborations: {_edge_weight_value:,.0f}",
                    ],
                    showlegend=False,
                ))

        _node_x = []
        _node_y = []
        _node_text = []
        _node_colors = []
        _node_sizes = []
        _hover_text_values = []
        _node_size_max = float(_nodes_df[node_size_col].max()) if len(_nodes_df) > 0 else 1.0

        for _, _node_row in _nodes_df.iterrows():
            _node_id = _node_row[node_id_col]
            _x, _y = _positions[_node_id]
            _label_value = str(_node_row[node_label_col])
            _display_label = _label_value if len(_label_value) <= label_truncate else _label_value[:label_truncate - 1] + "…"
            _degree_value = int(_degree_map.get(_node_id, 0))
            _node_size_value = 10 + 35 * (float(_node_row[node_size_col]) / _node_size_max if _node_size_max > 0 else 0)
            _node_x.append(_x)
            _node_y.append(_y)
            _node_text.append(_display_label)
            _node_colors.append(_degree_value)
            _node_sizes.append(_node_size_value)
            _hover_text_values.append(
                f"Name: {_label_value}<br># of connections: {_degree_value}<br>Works: {float(_node_row[node_size_col]):,.0f}"
            )

        _figure.add_trace(go.Scatter(
            x=_node_x,
            y=_node_y,
            text=_node_text,
            hovertext=_hover_text_values,
            mode="markers+text",
            hoverinfo="text",
            textposition="top center",
            marker=dict(
                showscale=True,
                colorscale=node_colorscale,
                reversescale=True,
                color=_node_colors,
                size=_node_sizes,
                colorbar=dict(
                    thickness=15,
                    title=node_color_title,
                    xanchor="left",
                ),
                line=dict(width=2, color="white"),
            ),
            showlegend=False,
        ))

        _figure.update_layout(
            title=title,
            showlegend=False,
            hovermode="closest",
            width=960,
            height=840,
            margin=dict(b=20, l=5, r=5, t=40),
            annotations=[dict(showarrow=False, xref="paper", yref="paper", x=0.005, y=-0.002)],
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        return _figure

    return (build_plotly_network_figure,)


@app.cell
def _(mo):
    mo.md(r"""
    ### Additional cumulative network views in a Karate-club-like style

    下面补充一组**不按单年切片，而是基于 2015–2025 全时段累计数据**构建的网络图。

    这一组图参考了你给出的 Plotly + network-style 视觉效果：

    - 边为浅色连线；
    - 节点大小随累计产出变化；
    - 节点颜色随连接强度变化；
    - 节点标签直接显示在节点上方。

    注意：这四张图是**新增图**，不会替换前面已有的年度网络图。
    """)
    return


@app.cell(hide_code=True)
def _(
    analysis_duckdb,
    institution_network_year_slider,
    np,
    work_institutions_glob,
    works_glob,
):
    institution_network_edges_year_base_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_institutions AS (
        SELECT DISTINCT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            wi.institution_id,
            wi.institution_name,
            wi.country_code
        FROM work_flags AS w
        INNER JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.institution_id IS NOT NULL
          AND w.publication_year = {institution_network_year_slider.value}
    ),
    institution_pairs AS (
        SELECT
            a.is_alphafold_related,
            LEAST(a.institution_id, b.institution_id) AS institution_id_1,
            GREATEST(a.institution_id, b.institution_id) AS institution_id_2,
            a.institution_name AS institution_name_1,
            b.institution_name AS institution_name_2,
            a.country_code AS country_code_1,
            b.country_code AS country_code_2
        FROM work_institutions AS a
        INNER JOIN work_institutions AS b
            ON a.work_id = b.work_id
           AND a.institution_id < b.institution_id
    )
    SELECT
        is_alphafold_related,
        institution_id_1,
        institution_id_2,
        institution_name_1,
        institution_name_2,
        country_code_1,
        country_code_2,
        COUNT(*) AS edge_weight
    FROM institution_pairs
    GROUP BY 1, 2, 3, 4, 5, 6, 7
    ORDER BY edge_weight DESC
    """).df()

    institution_network_nodes_year_base_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_institutions AS (
        SELECT DISTINCT
            w.work_id,
            w.is_alphafold_related,
            wi.institution_id,
            wi.institution_name,
            wi.country_code
        FROM work_flags AS w
        INNER JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.institution_id IS NOT NULL
          AND w.publication_year = {institution_network_year_slider.value}
    )
    SELECT
        is_alphafold_related,
        institution_id,
        institution_name,
        country_code,
        COUNT(DISTINCT work_id) AS n_works
    FROM work_institutions
    GROUP BY 1, 2, 3, 4
    ORDER BY n_works DESC
    """).df()

    institution_network_af_nodes_year_df = institution_network_nodes_year_base_df[
        institution_network_nodes_year_base_df["is_alphafold_related"] == True
    ].sort_values("n_works", ascending=False).head(30).copy()
    institution_network_non_af_nodes_year_df = institution_network_nodes_year_base_df[
        institution_network_nodes_year_base_df["is_alphafold_related"] == False
    ].sort_values("n_works", ascending=False).head(30).copy()

    institution_network_af_node_ids_year = institution_network_af_nodes_year_df["institution_id"].tolist()
    institution_network_non_af_node_ids_year = institution_network_non_af_nodes_year_df["institution_id"].tolist()

    institution_network_af_edges_filtered_year_df = institution_network_edges_year_base_df[
        (institution_network_edges_year_base_df["is_alphafold_related"] == True)
        & institution_network_edges_year_base_df["institution_id_1"].isin(institution_network_af_node_ids_year)
        & institution_network_edges_year_base_df["institution_id_2"].isin(institution_network_af_node_ids_year)
    ].sort_values("edge_weight", ascending=False).head(60).copy()

    institution_network_non_af_edges_filtered_year_df = institution_network_edges_year_base_df[
        (institution_network_edges_year_base_df["is_alphafold_related"] == False)
        & institution_network_edges_year_base_df["institution_id_1"].isin(institution_network_non_af_node_ids_year)
        & institution_network_edges_year_base_df["institution_id_2"].isin(institution_network_non_af_node_ids_year)
    ].sort_values("edge_weight", ascending=False).head(60).copy()

    _institution_network_year_ids_union = list(dict.fromkeys(
        institution_network_af_node_ids_year + institution_network_non_af_node_ids_year
    ))
    _institution_network_year_angles = np.linspace(
        0,
        2 * np.pi,
        len(_institution_network_year_ids_union),
        endpoint=False,
    )
    institution_network_year_positions = {
        _institution_network_year_ids_union[_i]: (
            float(np.cos(_institution_network_year_angles[_i])),
            float(np.sin(_institution_network_year_angles[_i])),
        )
        for _i in range(len(_institution_network_year_ids_union))
    }
    return (
        institution_network_af_edges_filtered_year_df,
        institution_network_af_nodes_year_df,
        institution_network_non_af_edges_filtered_year_df,
        institution_network_non_af_nodes_year_df,
        institution_network_year_positions,
    )


@app.cell(hide_code=True)
def _(
    go,
    institution_network_af_edges_filtered_year_df,
    institution_network_af_nodes_year_df,
    institution_network_non_af_edges_filtered_year_df,
    institution_network_non_af_nodes_year_df,
    institution_network_year_positions,
    institution_network_year_slider,
    mo,
):
    def _build_institution_network_figure(_edges_df, _nodes_df, _title, _node_color):
        _fig = go.Figure()
        _edge_max = _edges_df["edge_weight"].max() if len(_edges_df) > 0 else 1
        for _, _edge_row in _edges_df.iterrows():
            _x0, _y0 = institution_network_year_positions[_edge_row["institution_id_1"]]
            _x1, _y1 = institution_network_year_positions[_edge_row["institution_id_2"]]
            _edge_width = 1 + 6 * (_edge_row["edge_weight"] / _edge_max)
            _fig.add_trace(go.Scatter(
                x=[_x0, _x1, None],
                y=[_y0, _y1, None],
                mode="lines",
                line=dict(width=_edge_width, color="rgba(140,140,140,0.30)"),
                hoverinfo="text",
                text=[
                    f"{_edge_row['institution_name_1']} – {_edge_row['institution_name_2']}<br>Collaborations: {_edge_row['edge_weight']:.0f}",
                    f"{_edge_row['institution_name_1']} – {_edge_row['institution_name_2']}<br>Collaborations: {_edge_row['edge_weight']:.0f}",
                    None,
                ],
                showlegend=False,
            ))

        _node_max = _nodes_df["n_works"].max() if len(_nodes_df) > 0 else 1
        _node_x = []
        _node_y = []
        _node_text = []
        _node_size = []
        _node_label = []
        for _, _node_row in _nodes_df.iterrows():
            _node_id = _node_row["institution_id"]
            _x, _y = institution_network_year_positions[_node_id]
            _node_x.append(_x)
            _node_y.append(_y)
            _node_label.append(_node_row["institution_name"][:20])
            _node_size.append(14 + 34 * (_node_row["n_works"] / _node_max if _node_max > 0 else 0))
            _node_text.append(
                f"Institution: {_node_row['institution_name']}<br>Country: {_node_row['country_code']}<br>Works: {_node_row['n_works']:.0f}"
            )

        _fig.add_trace(go.Scatter(
            x=_node_x,
            y=_node_y,
            mode="markers+text",
            text=_node_label,
            textposition="top center",
            marker=dict(
                size=_node_size,
                color=_node_color,
                line=dict(width=1, color="white"),
                opacity=0.9,
            ),
            hovertext=_node_text,
            hoverinfo="text",
            showlegend=False,
        ))

        _fig.update_layout(
            title=_title,
            width=980,
            height=760,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            plot_bgcolor="white",
            margin=dict(l=20, r=20, t=60, b=20),
        )
        return _fig

    institution_network_af_year_fig = _build_institution_network_figure(
        institution_network_af_edges_filtered_year_df,
        institution_network_af_nodes_year_df,
        f"Institution collaboration network in AF-related research ({institution_network_year_slider.value})",
        "#d62728",
    )

    institution_network_non_af_year_fig = _build_institution_network_figure(
        institution_network_non_af_edges_filtered_year_df,
        institution_network_non_af_nodes_year_df,
        f"Institution collaboration network in Non-AF research ({institution_network_year_slider.value})",
        "#9467bd",
    )

    mo.vstack([institution_network_af_year_fig, institution_network_non_af_year_fig])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Comparing AF and Non-AF institutional collaboration networks

    上面两张机构网络图同样使用一个年份滑块进行比较：

    - **红色网络**：AF 相关研究的机构合作网络；
    - **紫色网络**：Non-AF 研究的机构合作网络。

    ### 如何比较

    - 比较节点大小：看哪些机构在 AF 与 Non-AF 中分别居于高产出位置；
    - 比较边的粗细：看 AF 相关机构合作是否更集中于少数关键机构对；
    - 比较网络形态：看 AF 网络是否表现出更强的中心化，或是否出现新的国际桥梁机构。

    ### 为什么这组图重要

    如果 AF 机构网络比 Non-AF 网络更集中于少数节点，并且强边主要围绕少数机构展开，那么这意味着：

    **AlphaFold 不只是改变了国际合作关系，也可能改变了科研组织网络本身，使少数头部机构在知识生产中占据更关键的位置。**
    """)
    return


@app.cell
def _(
    analysis_duckdb,
    build_plotly_network_figure,
    mo,
    work_institutions_glob,
    works_glob,
):
    institution_network_cumulative_edges_all_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_institutions_all AS (
        SELECT DISTINCT
            w.work_id,
            w.is_alphafold_related,
            wi.institution_id,
            wi.institution_name,
            wi.country_code
        FROM work_flags AS w
        INNER JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.institution_id IS NOT NULL
          AND wi.institution_name IS NOT NULL
    ),
    institution_pairs_all AS (
        SELECT
            a.is_alphafold_related,
            LEAST(a.institution_id, b.institution_id) AS institution_id_1,
            GREATEST(a.institution_id, b.institution_id) AS institution_id_2,
            COUNT(*) AS edge_weight
        FROM work_institutions_all AS a
        INNER JOIN work_institutions_all AS b
            ON a.work_id = b.work_id
           AND a.institution_id < b.institution_id
           AND a.is_alphafold_related = b.is_alphafold_related
        GROUP BY 1, 2, 3
    )
    SELECT *
    FROM institution_pairs_all
    """).df()

    institution_network_cumulative_nodes_all_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_institutions_all AS (
        SELECT DISTINCT
            w.work_id,
            w.is_alphafold_related,
            wi.institution_id,
            wi.institution_name,
            wi.country_code
        FROM work_flags AS w
        INNER JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.institution_id IS NOT NULL
          AND wi.institution_name IS NOT NULL
    )
    SELECT
        is_alphafold_related,
        institution_id,
        institution_name,
        country_code,
        COUNT(DISTINCT work_id) AS n_works
    FROM work_institutions_all
    GROUP BY 1, 2, 3, 4
    """).df()

    institution_network_cumulative_af_nodes_df = institution_network_cumulative_nodes_all_df[
        institution_network_cumulative_nodes_all_df["is_alphafold_related"] == True
    ][["institution_id", "institution_name", "n_works"]].rename(columns={"n_works": "node_size_value"}).copy()

    institution_network_cumulative_non_af_nodes_df = institution_network_cumulative_nodes_all_df[
        institution_network_cumulative_nodes_all_df["is_alphafold_related"] == False
    ][["institution_id", "institution_name", "n_works"]].rename(columns={"n_works": "node_size_value"}).copy()

    institution_network_cumulative_af_edges_df = institution_network_cumulative_edges_all_df[
        institution_network_cumulative_edges_all_df["is_alphafold_related"] == True
    ].copy()

    institution_network_cumulative_non_af_edges_df = institution_network_cumulative_edges_all_df[
        institution_network_cumulative_edges_all_df["is_alphafold_related"] == False
    ].copy()

    institution_network_cumulative_af_fig = build_plotly_network_figure(
        nodes_df=institution_network_cumulative_af_nodes_df,
        edges_df=institution_network_cumulative_af_edges_df,
        node_id_col="institution_id",
        node_label_col="institution_name",
        node_size_col="node_size_value",
        edge_source_col="institution_id_1",
        edge_target_col="institution_id_2",
        edge_weight_col="edge_weight",
        title="Institution collaboration network in AF-related research (cumulative, 2015–2025)",
        node_colorscale="Viridis",
        node_color_title="Node Connections",
        max_nodes=30,
        max_edges=60,
        label_truncate=22,
    )

    institution_network_cumulative_non_af_fig = build_plotly_network_figure(
        nodes_df=institution_network_cumulative_non_af_nodes_df,
        edges_df=institution_network_cumulative_non_af_edges_df,
        node_id_col="institution_id",
        node_label_col="institution_name",
        node_size_col="node_size_value",
        edge_source_col="institution_id_1",
        edge_target_col="institution_id_2",
        edge_weight_col="edge_weight",
        title="Institution collaboration network in Non-AF research (cumulative, 2015–2025)",
        node_colorscale="Viridis",
        node_color_title="Node Connections",
        max_nodes=30,
        max_edges=60,
        label_truncate=22,
    )

    mo.vstack([
        institution_network_cumulative_af_fig,
        institution_network_cumulative_non_af_fig,
    ])
    return (
        institution_network_cumulative_af_edges_df,
        institution_network_cumulative_af_nodes_df,
        institution_network_cumulative_non_af_edges_df,
        institution_network_cumulative_non_af_nodes_df,
    )


@app.cell
def _(
    build_circular_connectivity_figure,
    institution_network_cumulative_af_edges_df,
    institution_network_cumulative_af_nodes_df,
    institution_network_cumulative_non_af_edges_df,
    institution_network_cumulative_non_af_nodes_df,
    mo,
):
    institution_network_cumulative_af_circle_ax = build_circular_connectivity_figure(
        nodes_df=institution_network_cumulative_af_nodes_df,
        edges_df=institution_network_cumulative_af_edges_df,
        node_id_col="institution_id",
        node_label_col="institution_name",
        node_size_col="node_size_value",
        edge_source_col="institution_id_1",
        edge_target_col="institution_id_2",
        edge_weight_col="edge_weight",
        title="Institution collaboration network in AF-related research (cumulative, circular view)",
        max_nodes=30,
        max_edges=60,
        label_truncate=22,
    )

    institution_network_cumulative_non_af_circle_ax = build_circular_connectivity_figure(
        nodes_df=institution_network_cumulative_non_af_nodes_df,
        edges_df=institution_network_cumulative_non_af_edges_df,
        node_id_col="institution_id",
        node_label_col="institution_name",
        node_size_col="node_size_value",
        edge_source_col="institution_id_1",
        edge_target_col="institution_id_2",
        edge_weight_col="edge_weight",
        title="Institution collaboration network in Non-AF research (cumulative, circular view)",
        max_nodes=30,
        max_edges=60,
        label_truncate=22,
    )

    mo.vstack([
        institution_network_cumulative_af_circle_ax,
        institution_network_cumulative_non_af_circle_ax,
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Part 5 final conclusion

    综合这一部分的所有图表与网络结果，可以把 AlphaFold 对国际/机构协作格局的影响概括为四点：

    1. **AlphaFold 相关研究更依赖跨国合作。** 无论是平均国家数、跨国合作论文占比，还是跨国机构合作占比，AF 相关研究都更容易表现出国际协作特征，这说明 AlphaFold 并不是单纯在既有国家边界内被吸收，而是通过更密集的国际连接被共同生产和扩散。
    2. **国际协作网络存在明显的核心通道。** 国家合作边和国家网络图显示，AF 的跨国合作不是均匀分布的，而是集中在少数关键国家之间。这意味着 AlphaFold 的全球扩散在很大程度上依赖于已有高能力国家之间的协作网络。
    3. **机构层面的组织核心同样高度集中。** Top institutions、机构代理图与机构网络图都表明，少数头部机构同时拥有高产出、高跨国协作嵌入度和更大的国际合作范围，说明 AF 相关知识生产的组织重心仍然掌握在少数机构手中。
    4. **协作网络的扩张不等于协作结构的去中心化。** AF 与 Non-AF 对比表明，虽然 AF 相关研究更国际化、更跨机构，但其合作网络未必更加均匀，相反，它可能在扩张的同时强化了原有核心国家与头部机构的网络地位。

    因此，这一部分最重要的结论是：

    **AlphaFold 不仅改变了科研成果的地理扩散速度，也改变了知识生产的协作密度与组织方式；但从当前结果看，这种变化更接近“在原有核心网络上的强化扩张”，而不是彻底打破既有协作中心结构。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Part 6. Team structure of knowledge production

    这一部分关注的是：**AlphaFold 是否改变了科研知识生产的团队组织形态。**

    与前面的空间分布和协作网络不同，这里研究的是论文层面的团队规模结构，即：

    - AF 相关论文是否由更大的作者团队完成；
    - 团队规模分布是否向更大团队右移；
    - 大团队和超大团队在 AF 研究中是否更常见；
    - 这种变化是否意味着知识生产的组织方式发生调整。

    ### 研究问题

    本部分主要回答四个问题：

    1. AF 相关论文的平均作者数是否高于 Non-AF？
    2. AF 相关论文的典型团队规模（median）是否也更高？
    3. AF 研究更多来自 small / medium / large 哪一类团队？
    4. AF 是否推动了 large-team 和 huge-team 论文占比上升？

    ### 指标定义

    本部分使用以下团队规模定义：

    - `small team`：1–3 authors
    - `medium team`：4–7 authors
    - `large team`：8+ authors
    - `huge team`：20+ authors

    ### 分析逻辑

    这一部分按论文式逻辑分成四层：

    - **总体规模趋势**：mean team size, median team size
    - **团队规模分布**：authors per paper 的整体分布差异
    - **团队结构组成**：small / medium / large 的占比变化
    - **大团队化趋势**：8+ authors share 与 20+ authors share

    通过这些图，可以判断 AlphaFold 是否只是提升了少量论文的作者数，还是更系统性地推动了知识生产走向更大规模的团队协作。
    """)
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, analysis_ready, mo, pd, works_glob):
    mo.stop(
        not analysis_ready,
        mo.md(r"""
        尚未检测到 `derived_tables/works/`、`derived_tables/work_institutions/` 或 `derived_tables/work_topics/` 下的 parquet 文件。

        请先运行前面的规范化拆表与写盘流程，再查看本分析区。
        """),
    )

    team_structure_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    author_counts AS (
        SELECT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            COUNT(a.author_id) AS author_count
        FROM work_flags AS w
        LEFT JOIN read_parquet('derived_tables/authorships/*.parquet') AS a
            ON w.work_id = a.work_id
        GROUP BY 1, 2, 3
    )
    SELECT
        work_id,
        publication_year,
        is_alphafold_related,
        author_count,
        CASE
            WHEN author_count BETWEEN 1 AND 3 THEN 'small team'
            WHEN author_count BETWEEN 4 AND 7 THEN 'medium team'
            WHEN author_count >= 8 THEN 'large team'
            ELSE 'unknown'
        END AS team_size_category,
        CASE WHEN author_count >= 8 THEN 1 ELSE 0 END AS is_large_team,
        CASE WHEN author_count >= 20 THEN 1 ELSE 0 END AS is_huge_team
    FROM author_counts
    WHERE publication_year IS NOT NULL
      AND author_count > 0
    """).df()

    team_mean_rows = []
    team_median_rows = []
    for _year, _year_df in team_structure_df.groupby("publication_year"):
        for _group_name, _group_mask in [
            ("Total", _year_df.index == _year_df.index),
            ("AF", _year_df["is_alphafold_related"] == True),
            ("Non-AF", _year_df["is_alphafold_related"] == False),
        ]:
            _group_df = _year_df[_group_mask]
            if len(_group_df) == 0:
                continue
            team_mean_rows.append({
                "publication_year": _year,
                "group_name": _group_name,
                "metric_value": float(_group_df["author_count"].mean()),
            })
            team_median_rows.append({
                "publication_year": _year,
                "group_name": _group_name,
                "metric_value": float(_group_df["author_count"].median()),
            })

    team_mean_trend_df = pd.DataFrame(team_mean_rows)
    team_median_trend_df = pd.DataFrame(team_median_rows)

    team_distribution_plot_df = team_structure_df.copy()
    team_distribution_plot_df["author_count_capped"] = team_distribution_plot_df["author_count"].clip(upper=30)
    team_distribution_plot_df["group_name"] = team_distribution_plot_df["is_alphafold_related"].map({True: "AF", False: "Non-AF"})

    team_category_share_rows = []
    for (_year, _group_name), _group_df in team_structure_df.assign(
        group_name=team_structure_df["is_alphafold_related"].map({True: "AF", False: "Non-AF"})
    ).groupby(["publication_year", "group_name"]):
        _denom = len(_group_df)
        if _denom == 0:
            continue
        _category_counts = _group_df["team_size_category"].value_counts()
        for _category_name in ["small team", "medium team", "large team"]:
            team_category_share_rows.append({
                "publication_year": _year,
                "group_name": _group_name,
                "team_size_category": _category_name,
                "share_value": float(_category_counts.get(_category_name, 0) / _denom),
            })

    team_category_share_df = pd.DataFrame(team_category_share_rows)

    large_team_share_rows = []
    huge_team_share_rows = []
    for _year, _year_df in team_structure_df.groupby("publication_year"):
        for _group_name, _group_mask in [
            ("AF", _year_df["is_alphafold_related"] == True),
            ("Non-AF", _year_df["is_alphafold_related"] == False),
        ]:
            _group_df = _year_df[_group_mask]
            if len(_group_df) == 0:
                continue
            large_team_share_rows.append({
                "publication_year": _year,
                "group_name": _group_name,
                "share_value": float(_group_df["is_large_team"].mean()),
            })
            huge_team_share_rows.append({
                "publication_year": _year,
                "group_name": _group_name,
                "share_value": float(_group_df["is_huge_team"].mean()),
            })

    large_team_share_df = pd.DataFrame(large_team_share_rows)
    huge_team_share_df = pd.DataFrame(huge_team_share_rows)
    return (
        huge_team_share_df,
        large_team_share_df,
        team_category_share_df,
        team_distribution_plot_df,
        team_mean_trend_df,
        team_median_trend_df,
        team_structure_df,
    )


@app.cell(hide_code=True)
def _(alt, team_mean_trend_df):
    team_mean_line_chart = alt.Chart(team_mean_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Mean number of authors"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("metric_value:Q", title="Mean authors", format=".2f"),
        ],
    ).properties(
        title="Mean team size over time: Total vs Non-AF vs AF",
        width=820,
        height=320,
    )

    team_mean_line_chart
    return


@app.cell(hide_code=True)
def _(alt, team_median_trend_df):
    team_median_line_chart = alt.Chart(team_median_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Median number of authors"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("metric_value:Q", title="Median authors", format=".2f"),
        ],
    ).properties(
        title="Median team size over time: Total vs Non-AF vs AF",
        width=820,
        height=320,
    )

    team_median_line_chart
    return


@app.cell(hide_code=True)
def _(alt, team_distribution_plot_df):
    team_distribution_counts_df = team_distribution_plot_df.groupby(
        ["group_name", "author_count_capped"],
        as_index=False,
    ).size().rename(columns={"size": "paper_count"})
    team_distribution_counts_df["group_total"] = team_distribution_counts_df.groupby("group_name")["paper_count"].transform("sum")
    team_distribution_counts_df["paper_share"] = (
        team_distribution_counts_df["paper_count"] / team_distribution_counts_df["group_total"]
    )

    team_distribution_histogram = alt.Chart(team_distribution_counts_df).mark_bar(opacity=0.85).encode(
        x=alt.X("author_count_capped:O", title="Authors per paper (30 means 30+)", sort="ascending"),
        y=alt.Y("paper_share:Q", title="Share of papers within group", axis=alt.Axis(format=".0%")),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Non-AF", "AF"],
                range=["#72B7B2", "#F58518"],
            ),
        ),
        xOffset=alt.XOffset("group_name:N"),
        tooltip=[
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("author_count_capped:Q", title="Authors per paper", format=".0f"),
            alt.Tooltip("paper_count:Q", title="Number of papers", format=".0f"),
            alt.Tooltip("paper_share:Q", title="Share within group", format=".2%"),
        ],
    ).properties(
        title="Team size distribution share: AF vs Non-AF",
        width=820,
        height=360,
    )

    team_distribution_histogram
    return


@app.cell(hide_code=True)
def _(alt, team_category_share_df):
    team_category_share_chart = alt.Chart(team_category_share_df).mark_area().encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("share_value:Q", title="Share of papers", axis=alt.Axis(format=".0%"), stack="normalize"),
        color=alt.Color(
            "team_size_category:N",
            title="Team size category",
            scale=alt.Scale(
                domain=["small team", "medium team", "large team"],
                range=["#9ecae1", "#6baed6", "#2171b5"],
            ),
        ),
        column=alt.Column("group_name:N", title="Group"),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("team_size_category:N", title="Category"),
            alt.Tooltip("share_value:Q", title="Share", format=".1%"),
        ],
    ).properties(
        title="Team size category share over time",
        width=360,
        height=300,
    )

    team_category_share_chart
    return


@app.cell(hide_code=True)
def _(alt, large_team_share_df):
    large_team_share_chart = alt.Chart(large_team_share_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("share_value:Q", title="Share of 8+ authors papers", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Non-AF", "AF"],
                range=["#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("share_value:Q", title="Share", format=".1%"),
        ],
    ).properties(
        title="Large-team paper share over time (8+ authors)",
        width=820,
        height=320,
    )

    large_team_share_chart
    return


@app.cell(hide_code=True)
def _(alt, huge_team_share_df):
    huge_team_share_chart = alt.Chart(huge_team_share_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("share_value:Q", title="Share of 20+ authors papers", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Non-AF", "AF"],
                range=["#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("share_value:Q", title="Share", format=".1%"),
        ],
    ).properties(
        title="Huge-team paper share over time (20+ authors)",
        width=820,
        height=320,
    )

    huge_team_share_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### How to read the team structure figures

    这一组图不是在回答“谁发文更多”，而是在回答：

    **AlphaFold 是否改变了知识生产的团队组织方式。**

    阅读顺序建议是：

    1. 先看 **mean** 与 **median team size**，判断 AF 是否总体上由更大的团队完成；
    2. 再看 **team size distribution**，判断 AF 的作者数分布是否整体向右移动；
    3. 接着看 **team size category share**，判断 small / medium / large 团队结构是否发生变化；
    4. 最后看 **8+ authors share** 与 **20+ authors share**，判断是否出现大团队化与超大团队化趋势。
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting mean and median team size

    这两张图分别展示：

    - **Mean team size**：总体平均作者数；
    - **Median team size**：典型论文的作者数。

    ### 如何理解

    - 如果 AF 的 mean 明显高于 Non-AF，说明 AF 论文总体上由更大的团队完成；
    - 如果 AF 的 median 也高于 Non-AF，说明这种差异不是少数极端大团队造成的，而是更普遍地体现在“典型论文”的团队规模上；
    - 如果 mean 上升而 median 变化不大，说明团队扩张主要来自少数大型或超大型团队；
    - 如果 mean 和 median 同时上升，则说明知识生产的团队结构整体向更大规模移动。

    ### 实质意义

    这两张图共同回答的是：

    **AlphaFold 是否改变了论文层面的基本组织单元，使科研更依赖更大规模的作者团队。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the team size distribution

    这张分布图关注的是：

    **AF 论文的作者数分布，是否整体比 Non-AF 更向右移动。**

    ### 如何理解

    - 如果 AF 的柱体更多集中在较高作者数区间，说明 AF 研究更偏向由大团队完成；
    - 如果 AF 与 Non-AF 的差异主要出现在右侧长尾，说明 AF 特别容易吸引大型和超大型合作团队；
    - 如果 AF 与 Non-AF 在低作者数区间分布相近，但在高作者数区间明显分化，那么可以判断 AF 的团队效应主要体现在“更容易形成大团队”。

    ### 实质意义

    这张图不是看平均值，而是看**整体分布形态**。它能够帮助判断：

    **AlphaFold 是否让团队规模结构整体右移，而不仅仅是少数论文作者数特别多。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting team size category share over time

    这张图展示的是 AF 与 Non-AF 论文在 small / medium / large 三类团队中的组成变化。

    ### 如何理解

    - 如果 AF 的 `large team` 区域更大或增长更快，说明 AF 研究更依赖大规模协作；
    - 如果 AF 的 `small team` 占比显著低于 Non-AF，说明 AF 相关研究较少由小团队主导；
    - 如果 AF 的结构在时间上从 small / medium 向 large 偏移，则说明技术扩散伴随着团队组织方式的重塑。

    ### 实质意义

    这一图帮助区分两种情况：

    - 是“平均作者数高，但大多数论文其实差不多”；
    - 还是“团队结构本身真的向大团队迁移了”。

    如果后者成立，那么可以更有力地说明：

    **AlphaFold 相关研究不仅改变了平均团队规模，也改变了团队组织结构。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting large-team and huge-team trends

    最后两张图分别展示：

    - **8+ authors share**：大团队论文占比；
    - **20+ authors share**：超大团队论文占比。

    ### 如何理解

    - 如果 AF 的 `8+ authors share` 高于 Non-AF，说明 AF 相关研究更倾向由大团队完成；
    - 如果 AF 的 `20+ authors share` 也更高，说明 AF 相关知识生产不仅更大团队化，而且更容易走向超大规模协作；
    - 如果这两条线在 2021 之后明显抬升，则说明 AlphaFold 的扩散可能伴随着更复杂的协作组织形式。

    ### 实质意义

    这两张图特别重要，因为它们直接回答：

    **AlphaFold 是否推动了知识生产向“大团队化”与“超大团队化”方向发展。**

    如果 AF 的两条线长期高于 Non-AF，那么可以认为：

    **AF 相关研究不仅需要更多作者参与，而且更可能依赖复杂的、多角色协同的大型知识生产团队。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Part 6 final conclusion

    综合这一部分的结果，可以把 AlphaFold 对知识生产团队结构的影响概括为三点：

    1. **AF 相关研究通常由更大的作者团队完成。** 如果 mean 与 median team size 同时高于 Non-AF，那么这说明 AF 论文不仅平均作者数更高，而且典型论文也更依赖更大规模的团队。
    2. **团队结构本身向大团队偏移。** 如果 AF 在 team size category share 中表现出更高的 `large team` 占比、较低的 `small team` 占比，那么可以说明 AF 并不是简单增加少数论文的作者数，而是在整体上推动了团队组织结构的重组。
    3. **AF 更容易走向大团队化与超大团队化。** 如果 8+ authors share 和 20+ authors share 长期高于 Non-AF，说明 AF 相关知识生产更依赖复杂的协作分工与大规模组织协调。

    因此，这一部分最重要的结论是：

    **AlphaFold 不只是改变了知识生产的内容与扩散路径，也可能改变了科研生产的微观组织形式，使研究更倾向于由更大、更复杂、协作程度更高的团队来完成。**
    """)
    return


@app.cell(hide_code=True)
def _(
    analysis_duckdb,
    country_trend_df,
    pd,
    work_institutions_glob,
    works_glob,
):
    country_team_structure_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            publication_year,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_country_anchor AS (
        SELECT DISTINCT
            w.work_id,
            w.publication_year,
            w.is_alphafold_related,
            wi.country_code
        FROM work_flags AS w
        INNER JOIN read_parquet('{work_institutions_glob}') AS wi
            ON w.work_id = wi.work_id
        WHERE wi.country_code IS NOT NULL
    ),
    author_counts AS (
        SELECT
            wca.work_id,
            wca.publication_year,
            wca.is_alphafold_related,
            wca.country_code,
            COUNT(a.author_id) AS author_count
        FROM work_country_anchor AS wca
        LEFT JOIN read_parquet('derived_tables/authorships/*.parquet') AS a
            ON wca.work_id = a.work_id
        GROUP BY 1, 2, 3, 4
    )
    SELECT
        work_id,
        publication_year,
        is_alphafold_related,
        country_code,
        author_count,
        CASE WHEN author_count >= 8 THEN 1 ELSE 0 END AS is_large_team,
        CASE WHEN author_count >= 20 THEN 1 ELSE 0 END AS is_huge_team
    FROM author_counts
    WHERE publication_year IS NOT NULL
    """).df()

    country_top5_codes_team = country_trend_df.groupby("country_code")["n_works"].sum().sort_values(ascending=False).head(5).index.tolist()

    country_team_mean_rows = []
    country_team_large_rows = []
    country_team_huge_rows = []
    for (_year, _country_code), _country_df in country_team_structure_df[
        country_team_structure_df["country_code"].isin(country_top5_codes_team)
    ].groupby(["publication_year", "country_code"]):
        for _group_name, _group_mask in [
            ("Total", _country_df.index == _country_df.index),
            ("AF", _country_df["is_alphafold_related"] == True),
            ("Non-AF", _country_df["is_alphafold_related"] == False),
        ]:
            _group_data = _country_df[_group_mask]
            if len(_group_data) == 0:
                continue
            country_team_mean_rows.append({
                "publication_year": _year,
                "country_code": _country_code,
                "group_name": _group_name,
                "metric_value": float(_group_data["author_count"].mean()),
                "country_group": f"{_country_code} - {_group_name}",
            })
            country_team_large_rows.append({
                "publication_year": _year,
                "country_code": _country_code,
                "group_name": _group_name,
                "share_value": float(_group_data["is_large_team"].mean()),
                "country_group": f"{_country_code} - {_group_name}",
            })
            country_team_huge_rows.append({
                "publication_year": _year,
                "country_code": _country_code,
                "group_name": _group_name,
                "share_value": float(_group_data["is_huge_team"].mean()),
                "country_group": f"{_country_code} - {_group_name}",
            })

    country_team_mean_trend_df = pd.DataFrame(country_team_mean_rows)
    country_team_large_trend_df = pd.DataFrame(country_team_large_rows)
    country_team_huge_trend_df = pd.DataFrame(country_team_huge_rows)
    return (
        country_team_huge_trend_df,
        country_team_large_trend_df,
        country_team_mean_trend_df,
    )


@app.cell(hide_code=True)
def _(
    alt,
    country_group_color_domain,
    country_group_color_range,
    country_team_mean_trend_df,
):
    country_team_mean_top5_chart = alt.Chart(country_team_mean_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("metric_value:Q", title="Mean number of authors"),
        color=alt.Color(
            "country_group:N",
            title="Country / Group",
            scale=alt.Scale(
                domain=country_group_color_domain,
                range=country_group_color_range,
            ),
        ),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("metric_value:Q", title="Mean authors", format=".2f"),
        ],
    ).properties(
        title="Top 5 countries: mean team size trend by Total / Non-AF / AF",
        width=900,
        height=420,
    )

    country_team_mean_top5_chart
    return


@app.cell(hide_code=True)
def _(
    alt,
    country_group_color_domain,
    country_group_color_range,
    country_team_large_trend_df,
):
    country_team_large_top5_chart = alt.Chart(country_team_large_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("share_value:Q", title="Share of 8+ authors papers", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
        color=alt.Color(
            "country_group:N",
            title="Country / Group",
            scale=alt.Scale(
                domain=country_group_color_domain,
                range=country_group_color_range,
            ),
        ),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("share_value:Q", title="Share", format=".1%"),
        ],
    ).properties(
        title="Top 5 countries: large-team paper share by Total / Non-AF / AF",
        width=900,
        height=420,
    )

    country_team_large_top5_chart
    return


@app.cell(hide_code=True)
def _(
    alt,
    country_group_color_domain,
    country_group_color_range,
    country_team_huge_trend_df,
):
    country_team_huge_top5_chart = alt.Chart(country_team_huge_trend_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("share_value:Q", title="Share of 20+ authors papers", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
        color=alt.Color(
            "country_group:N",
            title="Country / Group",
            scale=alt.Scale(
                domain=country_group_color_domain,
                range=country_group_color_range,
            ),
        ),
        tooltip=[
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("share_value:Q", title="Share", format=".1%"),
        ],
    ).properties(
        title="Top 5 countries: huge-team paper share by Total / Non-AF / AF",
        width=900,
        height=420,
    )

    country_team_huge_top5_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### How to read the top 5 countries' team structure trends

    上面三张图把团队结构分析从“全球总体平均”推进到了“国家层面的异质性比较”。

    ### 可以重点看三类差异

    1. **同一国家内部的 AF vs Non-AF 差异**
       - 如果某个国家的 AF 线始终高于同国的 Non-AF 线，说明 AlphaFold 在该国更依赖大团队协作；
    2. **不同国家之间的差异**
       - 如果某些国家在 mean team size、8+ share、20+ share 上整体更高，说明这些国家本身就更倾向于以大型团队组织科研生产；
    3. **时间变化的方向**
       - 如果 2021 之后 AF 线在若干国家明显抬升，而 Non-AF 变化较小，则说明 AlphaFold 的扩散可能伴随着国家层面的团队组织重塑。

    ### 这三张图的重要意义

    它们帮助回答：

    **AlphaFold 对团队结构的影响，是一个普遍的全球现象，还是主要由少数国家驱动的差异化现象。**

    如果只有少数高能力国家表现出明显的大团队化，而其他国家变化有限，那么说明 AlphaFold 对团队组织方式的影响也具有国家分层特征。
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Linking team structure back to collaboration patterns

    团队规模变化与前面的国际/机构协作分析之间，其实存在非常直接的联系。

    如果前面的 Part 5 已经表明：

    - AF 相关研究更依赖跨国合作；
    - 更依赖跨国机构协作；
    - 并且核心合作网络围绕少数国家和机构展开；

    那么 Part 6 所展示的大团队化趋势，就可以被理解为这种组织复杂化在论文层面的体现。

    ### 综合理解逻辑

    - **更多国家参与** 往往意味着需要更多作者协调；
    - **更多机构共同参与** 往往意味着团队成员来源更分散；
    - **跨国协作增强** 往往与更大、更复杂的作者团队同时出现；
    - 因此，团队规模上升并不是孤立现象，而是国际协作网络扩张在论文层面的微观反映。

    ### 与 Part 5 结合后的解释

    如果 AF 论文既显示出更强的国际/机构协作特征，又显示出更高的大团队和超大团队占比，那么可以更有力地说明：

    **AlphaFold 不只是改变了知识扩散的地理路径，也改变了知识生产的组织方式，使研究更依赖跨机构、跨边界、跨角色协同的大规模团队。**

    换句话说，Part 5 解释的是“协作网络如何扩展”，而 Part 6 解释的是“这种扩展如何体现在单篇论文的团队结构上”。两者共同支持这样一个判断：

    **AlphaFold 的影响不仅是主题层面的，也不仅是空间层面的，而是深入到了科研生产的组织形态本身。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Team-structure inequality with Gini coefficients

    除了比较平均团队规模与大团队占比之外，还可以进一步用 **Gini coefficient** 衡量团队组织结构本身是否变得更加不均衡。

    这里补充三个层面的团队结构 Gini：

    1. **Paper-level author-count Gini**：衡量论文之间作者数分布是否更加不均衡；
    2. **Country-level mean team size Gini**：衡量不同国家之间平均团队规模是否更加分化；
    3. **Country-level huge-team share Gini**：衡量不同国家之间 20+ authors 论文占比是否更加不均衡。

    这样可以把团队结构分析进一步推进到一个更明确的问题：

    **AlphaFold 是否不仅改变了团队规模本身，也改变了团队组织不平等的程度。**
    """)
    return


@app.cell(hide_code=True)
def _(
    country_team_huge_trend_df,
    country_team_mean_trend_df,
    pd,
    team_structure_df,
):
    paper_team_gini_rows = []
    for _year, _year_df in team_structure_df.groupby("publication_year"):
        for _group_name, _group_mask in [
            ("Total", _year_df.index == _year_df.index),
            ("AF", _year_df["is_alphafold_related"] == True),
            ("Non-AF", _year_df["is_alphafold_related"] == False),
        ]:
            _group_data = _year_df[_group_mask]
            if len(_group_data) == 0:
                continue
            paper_team_gini_rows.append({
                "publication_year": _year,
                "group_name": _group_name,
                "gini_value": gini_coefficient(_group_data["author_count"].to_numpy()),
            })

    paper_team_gini_df = pd.DataFrame(paper_team_gini_rows).sort_values(["publication_year", "group_name"])

    country_team_mean_gini_rows = []
    for _year, _year_df in country_team_mean_trend_df.groupby("publication_year"):
        _year_total_df = _year_df[_year_df["group_name"] == "Total"]
        if len(_year_total_df) == 0:
            continue
        country_team_mean_gini_rows.append({
            "publication_year": _year,
            "gini_value": gini_coefficient(_year_total_df["metric_value"].to_numpy()),
        })

    country_team_mean_gini_df = pd.DataFrame(country_team_mean_gini_rows).sort_values("publication_year")

    country_huge_team_gini_rows = []
    for _year, _year_df in country_team_huge_trend_df.groupby("publication_year"):
        _year_total_df = _year_df[_year_df["group_name"] == "Total"]
        if len(_year_total_df) == 0:
            continue
        country_huge_team_gini_rows.append({
            "publication_year": _year,
            "gini_value": gini_coefficient(_year_total_df["share_value"].to_numpy()),
        })

    country_huge_team_gini_df = pd.DataFrame(country_huge_team_gini_rows).sort_values("publication_year")
    return (
        country_huge_team_gini_df,
        country_team_mean_gini_df,
        paper_team_gini_df,
    )


@app.cell(hide_code=True)
def _(alt, paper_team_gini_df):
    paper_team_gini_chart = alt.Chart(paper_team_gini_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("gini_value:Q", title="Paper-level team size Gini", scale=alt.Scale(domain=[0, 1])),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Total", "Non-AF", "AF"],
                range=["#4C78A8", "#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("gini_value:Q", title="Gini coefficient", format=".3f"),
        ],
    ).properties(
        title="Paper-level team size inequality over time: Total vs Non-AF vs AF",
        width=820,
        height=320,
    )

    paper_team_gini_chart
    return


@app.cell(hide_code=True)
def _(alt, country_team_mean_gini_df):
    country_team_mean_gini_chart = alt.Chart(country_team_mean_gini_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("gini_value:Q", title="Country-level mean team size Gini", scale=alt.Scale(domain=[0, 1])),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("gini_value:Q", title="Gini coefficient", format=".3f"),
        ],
    ).properties(
        title="Country-level inequality in mean team size over time",
        width=820,
        height=320,
    )

    country_team_mean_gini_chart
    return


@app.cell(hide_code=True)
def _(alt, country_huge_team_gini_df):
    country_huge_team_gini_chart = alt.Chart(country_huge_team_gini_df).mark_line(point=True).encode(
        x=alt.X("publication_year:Q", title="Publication year", axis=alt.Axis(format="d")),
        y=alt.Y("gini_value:Q", title="Country-level 20+ authors share Gini", scale=alt.Scale(domain=[0, 1])),
        tooltip=[
            alt.Tooltip("publication_year:Q", title="Publication year", format="d"),
            alt.Tooltip("gini_value:Q", title="Gini coefficient", format=".3f"),
        ],
    ).properties(
        title="Country-level inequality in huge-team paper share over time",
        width=820,
        height=320,
    )

    country_huge_team_gini_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the team-structure Gini figures

    这三张图把团队结构分析进一步从“平均规模”推进到了“分布不均衡程度”。

    ### 1. Paper-level author-count Gini

    这张图衡量的是：

    **论文之间的作者数分布，是否越来越不均衡。**

    - 如果 `Gini(AF)` 高于 `Gini(Non-AF)`，说明 AF 论文的团队规模更分化；
    - 这通常意味着 AF 并不是简单地让所有论文都变成更大团队，而是更可能出现“少数超大团队 + 大量普通团队”并存的结构；
    - 如果 `Gini(AF)` 在 2021 之后上升，说明 AlphaFold 相关研究的团队规模差异正在扩大。

    ### 2. Country-level mean team size Gini

    这张图衡量的是：

    **不同国家之间平均团队规模是否越来越分化。**

    - 如果这条线升高，说明某些国家更快地转向大团队组织，而其他国家变化较小；
    - 这表明团队组织方式的变化并不是全球同步发生，而具有明显的国家层级差异。

    ### 3. Country-level huge-team share Gini

    这张图衡量的是：

    **20+ authors 论文占比是否主要集中在少数国家。**

    - 如果 Gini 很高，说明“超大团队化”主要发生在少数国家；
    - 如果这条线在 AF 扩散期上升，说明 AlphaFold 相关研究所带来的复杂协作组织形式，并没有均匀地扩展到所有国家，而是先在少数高能力国家集聚。

    ### 这些图的重要意义

    前面的团队规模图更多回答的是“平均上是否变大”，而这三张 Gini 图回答的是：

    **团队组织方式的变化，是否同时伴随着新的组织不平等。**

    也就是说，它们帮助区分：

    - 是所有国家、所有论文都一起走向大团队化；
    - 还是只有少数国家、少数超大团队率先主导了这种变化。
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Do we also need a Lorenz curve for team structure?

    **短答案是：可以加，但不是当前最优先。**

    ### 为什么可以加

    Lorenz curve 对团队结构也同样适用。例如你可以：

    - 对某一年所有论文的 `author_count` 画 Lorenz curve；
    - 或对各国 `20+ authors share` 画 Lorenz curve；
    - 再比较 AF vs Non-AF 或不同年份之间的曲线形状。

    如果曲线明显远离对角线，就说明团队规模或超大团队分布高度集中。

    ### 为什么当前不一定最优先

    虽然 Lorenz curve 能提供很直观的补充，但在当前 notebook 里，团队结构部分已经有：

    - mean / median 趋势；
    - distribution histogram；
    - category share；
    - 8+ / 20+ share；
    - 3 张 Gini 图；
    - top 5 国家团队趋势。

    这些图已经能比较完整地回答：

    - AF 是否更依赖大团队；
    - 是否存在超大团队化；
    - 团队组织不平等是否扩大；
    - 这种变化是否集中在少数国家。

    因此，从“信息增量”角度看，**Lorenz curve 在团队结构部分是有价值的补充，但不是必须项**。如果你后面要进一步强化“组织不平等”这条论点，尤其是想让读者更直观地看到“少数超大团队是否主导了 AF 研究”，那么再加 Lorenz curve 会很有帮助。

    ### 更建议的使用方式

    如果要加，我建议优先只加 1 张，而不是很多张：

    - 选 2–3 个关键年份（例如 2021、2023、2025）；
    - 对 **AF 论文的作者数分布** 画 Lorenz curve；
    - 用它来直观展示“超大团队是否越来越主导 AF 研究”。

    ### 与整篇论文主线的关系

    团队结构 Gini 分析已经支持这样一个更强的论点：

    **AlphaFold 不仅改变了知识生产的空间分布与国际协作格局，也可能改变了科研组织不平等的结构，使少数国家和少数超大团队在知识生产中占据更核心的位置。**

    如果再加 Lorenz curve，它的作用主要不是替代 Gini，而是把这种“组织不平等”用更直观的方式展示出来。
    """)
    return


@app.cell(hide_code=True)
def _(pd, team_structure_df):
    team_lorenz_years = [2021, 2023, 2025]
    team_lorenz_rows = []
    for _year in team_lorenz_years:
        _year_df = team_structure_df[
            (team_structure_df["publication_year"] == _year)
            & (team_structure_df["is_alphafold_related"] == True)
        ].copy()
        _values = _year_df["author_count"].fillna(0).to_numpy()
        _values = _values[_values >= 0]
        _values.sort()
        if len(_values) == 0:
            continue
        _cum_values = _values.cumsum()
        _total = _values.sum()
        if _total == 0:
            continue
        _cum_share = _cum_values / _total
        _paper_share = (pd.Series(range(1, len(_values) + 1)) / len(_values)).to_numpy()

        team_lorenz_rows.append({
            "publication_year": _year,
            "paper_share": 0.0,
            "author_share": 0.0,
        })
        team_lorenz_rows.extend([
            {
                "publication_year": _year,
                "paper_share": float(_paper_share[_i]),
                "author_share": float(_cum_share[_i]),
            }
            for _i in range(len(_values))
        ])

    team_lorenz_curve_df = pd.DataFrame(team_lorenz_rows)
    return (team_lorenz_curve_df,)


@app.cell(hide_code=True)
def _(alt, pd, team_lorenz_curve_df):
    team_lorenz_curve_chart = alt.Chart(team_lorenz_curve_df).mark_line().encode(
        x=alt.X("paper_share:Q", title="Cumulative share of AF papers", axis=alt.Axis(format=".0%")),
        y=alt.Y("author_share:Q", title="Cumulative share of authors", axis=alt.Axis(format=".0%")),
        color=alt.Color("publication_year:N", title="Publication year"),
        tooltip=[
            alt.Tooltip("publication_year:N", title="Publication year"),
            alt.Tooltip("paper_share:Q", title="Paper share", format=".1%"),
            alt.Tooltip("author_share:Q", title="Author share", format=".1%"),
        ],
    ).properties(
        title="Lorenz curve of AF team size distribution",
        width=820,
        height=360,
    )

    team_equality_line = alt.Chart(pd.DataFrame({
        "paper_share": [0.0, 1.0],
        "author_share": [0.0, 1.0],
    })).mark_line(strokeDash=[6, 4], color="#666666").encode(
        x="paper_share:Q",
        y="author_share:Q",
    )

    team_lorenz_curve_chart + team_equality_line
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the team-size Lorenz curve

    这张 Lorenz curve 关注的是：

    **AF 论文中的作者规模，是否越来越集中在少数更大的团队之中。**

    ### 如何理解

    - 图中的虚线表示“完全平均分布”；
    - 某一年曲线越远离对角线，说明该年的作者规模分布越不均衡；
    - 如果后期年份曲线比前期年份更向右下方弯曲，说明 AF 研究中的作者规模越来越集中在少数大团队或超大团队。

    ### 这张图的意义

    与前面的 Gini 图相比，Lorenz curve 的优点是更直观：

    - Gini 告诉你“不平等程度有多高”；
    - Lorenz curve 直接展示“多少比例的 AF 论文，对应了多少比例的作者规模累积份额”。

    因此，这张图特别适合支持这样一个判断：

    **AlphaFold 相关知识生产是否越来越依赖少数大规模协作团队，从而使团队组织不平等进一步加深。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Linking Part 6 back to Part 4: do team-structure changes support a broader reconfiguration?

    Part 6 对 Part 4 的价值在于，它把“全球空间格局是否变化”进一步推进到了“科研生产的微观组织形式是否变化”。

    如果前面的部分已经表明：

    - AlphaFold 的 adoption 具有明显的空间扩散路径；
    - 国家间科研产出与 adoption rate 的不平等仍然显著；
    - 国际/机构合作网络在扩张，但核心结构未必发生转移；

    那么 Part 6 进一步说明：

    - AF 相关研究不仅在空间上扩散不均衡；
    - 也在组织层面更依赖大团队、超大团队以及更复杂的协作分工；
    - 并且这种团队组织不平等同样可能集中在少数国家与少数高能力团队之中。

    因此，这一部分所支持的并不是“全球科研生产格局已经被彻底改写”，而是一个更细致的判断：

    **AlphaFold 很可能同时改变了知识生产的空间扩散方式和组织协作方式，但这种变化更多表现为在原有强国与强机构主导体系上的深化和复杂化，而不是对既有全球格局的完全替代。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Overall conclusion: has AlphaFold reconfigured the global geography of scientific production?

    综合 Part 1–6 的全部分析结果，可以把本 notebook 的核心结论归纳为一个更完整的判断：

    ### 1. AlphaFold 确实显著改变了知识扩散的速度与范围

    从 adoption timing map、country heatmap、世界地图和年度趋势图来看，AlphaFold 相关研究在 2021 年后迅速进入跨国扩散阶段，并在 2022–2025 年间覆盖了越来越多国家。这说明 AlphaFold 并不是局限于少数实验室内部的局部技术，而是以较快速度进入全球科研体系，形成了清晰的国际扩散路径。

    ### 2. 这种扩散并不是均匀扩散，而是具有明显的国家分层特征

    无论是 AF 论文数量分布、AF share 分布，还是 first adoption year 的空间差异，都表明 AlphaFold 的采用存在明显的先后顺序与强弱差异。少数科研能力更强、方法吸收速度更快的国家率先进入 adoption，而其他国家则在之后逐步跟进。这意味着 AlphaFold 的全球传播更接近“分层扩散”，而不是“同时扩散”。

    ### 3. AlphaFold 并没有自动降低科研空间不平等

    Part 3 中的 Gini coefficient、Lorenz curve 与 Top 10 countries' share 都表明，AF 相关研究在国家层面的集中度依然较高。即使 adoption 国家数量增加，核心知识生产仍然集中在少数头部国家，说明 AlphaFold 的全球扩散并没有自动带来更均衡的国家分布。相反，在扩散初期，它很可能强化了原有科研强国的领先地位。

    ### 4. AlphaFold 改变的不只是“在哪里生产知识”，也改变了“如何组织知识生产”

    Part 5 和 Part 6 的结果表明，AF 相关研究更依赖跨国合作、跨国机构合作以及更大规模的作者团队。国家合作网络与机构合作网络显示，AF 的知识生产更深地嵌入国际协作体系；团队结构分析则显示，AF 研究更容易走向大团队化与超大团队化。这说明 AlphaFold 的影响不仅体现在地理扩散上，也体现在科研组织形式的复杂化上。

    ### 5. 这种组织方式的变化同样带有明显的不平等结构

    无论是合作网络中的核心国家与头部机构，还是团队结构中的超大团队化趋势，都没有表现出均匀扩散的特征。相反，当前结果更接近这样一种结构：

    - 少数国家掌握核心知识生产；
    - 少数机构处于国际协作网络中心；
    - 少数大团队或超大团队承担更关键的 AF 相关研究任务。

    因此，AlphaFold 的扩散不仅可能强化空间不平等，也可能强化知识生产组织层面的不平等。

    ### Final synthesis

    因此，如果要直接回答“AlphaFold 是否重构了全球科研生产的空间格局”，本 notebook 给出的最谨慎、也最有解释力的结论是：

    **AlphaFold 确实显著改变了科研生产的扩散速度、覆盖范围、国际协作密度与团队组织形式，但现有证据更支持‘在原有中心体系上的强化扩张与组织复杂化’，而不是对全球科研空间格局的彻底重构。**

    换句话说，AlphaFold 带来的变化是真实而深刻的，但这些变化更像是：

    - 原有中心国家更快吸收了新技术；
    - 原有头部机构更深地嵌入了新的国际协作网络；
    - 原有高能力团队更容易主导大规模知识生产；

    而不是出现了一个完全重新洗牌的全球科研地理结构。

    ### What this implies for future research

    这也意味着，后续如果要进一步判断“是否发生更强意义上的重构”，还需要继续观察：

    1. 后发国家是否在更长时间尺度上持续提升 AF adoption；
    2. 新兴国家与新机构是否真正进入网络核心；
    3. 头部国家的份额与中心地位是否在后期显著下降；
    4. 团队与协作结构是否从少数中心节点进一步向更广泛主体扩散。

    只有当这些变化同时出现时，才更接近“全球科研生产空间格局已被重构”的强结论。就当前这套分析而言，更稳妥的判断仍然是：

    **AlphaFold 改变了全球知识生产的方式，但它更可能是在旧有中心—外围体系中加速扩散、强化中心、并推动组织复杂化，而不是彻底颠覆这一体系。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Abstract-style summary

    本 notebook 以 OpenAlex 的论文元数据为基础，围绕 AlphaFold 相关研究在 2015–2025 年间的全球扩散，系统考察其是否改变了科研生产的地理分布、空间不平等与组织方式。方法上，本文首先将 OpenAlex 的半结构化 JSONL 数据规范化为适合 DuckDB + Parquet 分析的多张分析表，然后在国家层面、机构层面与团队层面构建一组互补指标，包括 AF 论文数量与占比、adoption timing、Gini coefficient、Lorenz curve、Top 10 国家份额、国际合作边、机构协作网络以及团队规模分布与团队结构不平等指标。

    分析结果表明，AlphaFold 相关研究在 2021 年后进入明显的国际扩散阶段，并在 2022–2025 年间迅速覆盖更多国家。然而，这种扩散并不是均匀扩散，而是表现为明显的国家分层：少数科研能力更强的国家率先采用，并在 AF 相关产出、国际协作网络和大团队组织方式上占据主导地位。空间不平等分析显示，AF 相关研究的国家分布在多个年份中比 Non-AF 更集中，且 Top 10 国家长期占据较高份额；与此同时，国际/机构协作网络和团队结构分析进一步表明，AF 研究更依赖跨国合作、跨机构协作以及更大规模甚至超大规模团队，但这些组织方式的变化同样带有明显的不平等结构。

    因此，本 notebook 支持这样一个总体判断：**AlphaFold 显著改变了全球知识生产的扩散速度、国际协作密度与团队组织形式，但现有证据更支持“在原有中心体系上的强化扩张与组织复杂化”，而不是全球科研生产空间格局的彻底重构。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the cumulative AF vs Non-AF world maps

    这两张累计世界地图把 AlphaFold 相关研究与非 AlphaFold 研究的长期地理分布放在同一尺度下进行比较。

    ### 如何理解

    - **累计 AF 地图**展示的是各国在整个观察期内累计产出的 AF 相关论文数量；
    - **累计 Non-AF 地图**展示的是各国在同一时期内累计产出的非 AF 论文数量；
    - 两张图结合起来，可以判断 AF 相关研究的空间分布究竟是沿着既有科研强国格局展开，还是在某些国家表现出相对更强的集中。

    ### 可以关注的核心问题

    1. **AF 的累计空间分布是否仍然追随总体科研强国格局？**
       - 如果累计 AF 地图与累计 Non-AF 地图的高值国家大体一致，说明 AlphaFold 的扩散主要嵌入在原有科研中心体系之中；
    2. **AF 是否在某些国家表现出更突出的相对集中？**
       - 如果某些国家在 AF 地图上比在 Non-AF 地图上更显著，说明这些国家在 AlphaFold 相关知识生产中具有更强的相对优势；
    3. **AF 的空间重心是否比 Non-AF 更窄？**
       - 如果 AF 的高值区域明显比 Non-AF 更集中在少数国家，说明 AlphaFold 并没有平均扩散，而是更集中地强化了少数中心国家的知识生产能力。

    ### 这两张图的意义

    这组累计地图不是看“某一年发生了什么”，而是看：

    **在整个观察期内，AlphaFold 相关研究的全球空间积累，是否沿着原有科研地理结构沉积下来。**

    如果结果显示 AF 的累计分布比 Non-AF 更集中，那么这将进一步支持前面 Gini、Lorenz curve 和 Top 10 share 的判断：

    **AlphaFold 的全球扩散虽然扩大了参与范围，但其长期知识积累仍然更集中于少数科研强国。**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Additional Plotly visuals for exploratory storytelling

    下面补充几类更具交互性和视觉冲击力的 Plotly 图表。这些图的目标不是替代前面的论文式主图，而是：

    - 以更直观的方式展示国家扩散与合作结构；
    - 支持演示与探索式分析；
    - 帮助从“地图—结构—网络—层级”多个角度理解 AlphaFold 的全球扩散。

    这一部分包括：

    1. **Animated bubble world map**
    2. **Sankey diagram A：country → topic**
    3. **Sankey diagram B：country → institution**
    4. **Treemap / Sunburst**
    5. **Plotly network graphs**（前面已经构建，这里作为整合展示的一部分）
    """)
    return


@app.cell(hide_code=True)
def _(country_trend_df):
    country_geo_coords_map = {
        "US": (37.1, -95.7), "CN": (35.9, 104.2), "GB": (55.4, -3.4), "DE": (51.2, 10.4),
        "FR": (46.2, 2.2), "IN": (20.6, 78.9), "NL": (52.1, 5.3), "BE": (50.8, 4.5),
        "CA": (56.1, -106.3), "AU": (-25.3, 133.8), "JP": (36.2, 138.3), "KR": (36.5, 127.9),
        "SE": (60.1, 18.6), "DK": (56.3, 9.5), "CH": (46.8, 8.2), "IT": (41.9, 12.6),
        "ES": (40.5, -3.7), "RU": (61.5, 105.3), "PL": (52.1, 19.1), "BR": (-14.2, -51.9),
        "AR": (-38.4, -63.6), "MX": (23.6, -102.5), "ZA": (-30.6, 22.9), "SG": (1.35, 103.8),
        "IL": (31.0, 35.0), "SA": (23.9, 45.1), "TR": (38.9, 35.2), "AE": (24.3, 54.4),
        "TH": (15.8, 100.9), "MY": (4.2, 101.9), "ID": (-0.8, 113.9), "NZ": (-40.9, 174.9),
        "CZ": (49.8, 15.5), "PT": (39.4, -8.2), "FI": (61.9, 25.7), "IE": (53.4, -8.2),
        "HU": (47.2, 19.5), "AT": (47.5, 14.6), "NO": (60.5, 8.5), "UA": (48.4, 31.2),
        "CO": (4.6, -74.1), "CL": (-35.7, -71.5), "PH": (12.9, 121.8), "PK": (30.4, 69.4),
        "EG": (26.8, 30.8), "IR": (32.4, 53.7), "VN": (14.1, 108.3), "BD": (23.7, 90.4),
        "NG": (9.1, 8.7), "KE": (0.0, 37.9), "GH": (7.9, -1.0), "TW": (23.7, 121.0),
        "HK": (22.3, 114.2), "BE": (50.8, 4.5), "RO": (45.9, 24.9), "GR": (39.1, 21.8),
        "BG": (42.7, 25.5), "HR": (45.1, 15.2), "SK": (48.7, 19.7), "SI": (46.1, 14.8),
    }

    bubble_map_df = country_trend_df.copy()
    bubble_map_df["country_code"] = bubble_map_df["country_code"].str.upper()
    bubble_map_df["lat"] = bubble_map_df["country_code"].map(lambda _c: country_geo_coords_map.get(_c, (None, None))[0])
    bubble_map_df["lon"] = bubble_map_df["country_code"].map(lambda _c: country_geo_coords_map.get(_c, (None, None))[1])
    bubble_map_df = bubble_map_df.dropna(subset=["lat", "lon"]).copy()
    return bubble_map_df, country_geo_coords_map


@app.cell
def _(bubble_map_df, px):
    animated_bubble_world_map = px.scatter_geo(
        bubble_map_df,
        lat="lat",
        lon="lon",
        size="n_af_works",
        color="af_share",
        hover_name="country_code",
        hover_data={
            "publication_year": True,
            "n_works": True,
            "n_af_works": True,
            "af_share": ':.2%',
            "lat": False,
            "lon": False,
        },
        animation_frame="publication_year",
        projection="natural earth",
        color_continuous_scale="Blues",
        size_max=50,
        title="Animated bubble world map of AF-related works and adoption share",
    )
    animated_bubble_world_map.update_geos(showcoastlines=True, coastlinecolor="lightgray", showland=True, landcolor="#f5f5f5")
    animated_bubble_world_map.update_layout(width=980, height=620, margin=dict(l=20, r=20, t=60, b=20))

    animated_bubble_world_map
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### How to read the animated bubble world map

    这张图把两个维度同时放进了一张动画地图中：

    - **气泡大小**表示各国 AF 相关论文的数量；
    - **颜色深浅**表示各国 AF adoption share 的高低；
    - **年份动画**展示这种分布如何随时间演化。

    ### 为什么这张图有价值

    它的优势在于，可以同时区分三类国家：

    1. **高产出、高 adoption**：既发得多，也把 AlphaFold 更深地纳入本国科研体系；
    2. **高产出、低 adoption**：总论文量大，但 AF 占比不一定高；
    3. **低产出、高 adoption**：总量不大，但 AF 在本国研究中占比较高。

    因此，这张图特别适合用来探索：

    **全球哪些国家是真正的 AF 知识生产中心，哪些国家则是 adoption 强度更高的“高响应国家”。**
    """)
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, work_institutions_glob, work_topics_glob, works_glob):
    country_topic_sankey_df = analysis_duckdb.execute(f"""
    WITH af_works AS (
        SELECT work_id
        FROM read_parquet('{works_glob}')
        WHERE COALESCE(is_alphafold_related, FALSE) = TRUE
    ),
    work_countries AS (
        SELECT DISTINCT
            wi.work_id,
            wi.country_code
        FROM read_parquet('{work_institutions_glob}') AS wi
        INNER JOIN af_works AS aw
            ON wi.work_id = aw.work_id
        WHERE wi.country_code IS NOT NULL
    ),
    work_topics AS (
        SELECT DISTINCT
            wt.work_id,
            wt.topic_display_name
        FROM read_parquet('{work_topics_glob}') AS wt
        INNER JOIN af_works AS aw
            ON wt.work_id = aw.work_id
        WHERE wt.topic_display_name IS NOT NULL
    )
    SELECT
        wc.country_code,
        wt.topic_display_name,
        COUNT(DISTINCT wc.work_id) AS n_works
    FROM work_countries AS wc
    INNER JOIN work_topics AS wt
        ON wc.work_id = wt.work_id
    GROUP BY 1, 2
    ORDER BY n_works DESC
    LIMIT 30
    """).df()

    country_institution_sankey_df = analysis_duckdb.execute(f"""
    WITH af_works AS (
        SELECT work_id
        FROM read_parquet('{works_glob}')
        WHERE COALESCE(is_alphafold_related, FALSE) = TRUE
    )
    SELECT
        wi.country_code,
        wi.institution_name,
        COUNT(DISTINCT wi.work_id) AS n_works
    FROM read_parquet('{work_institutions_glob}') AS wi
    INNER JOIN af_works AS aw
        ON wi.work_id = aw.work_id
    WHERE wi.country_code IS NOT NULL
      AND wi.institution_name IS NOT NULL
    GROUP BY 1, 2
    ORDER BY n_works DESC
    LIMIT 30
    """).df()
    return country_institution_sankey_df, country_topic_sankey_df


@app.cell(hide_code=True)
def _(country_topic_sankey_df, go):
    _ct_sources = country_topic_sankey_df["country_code"].tolist()
    _ct_targets = country_topic_sankey_df["topic_display_name"].tolist()
    _ct_labels = list(dict.fromkeys(_ct_sources + _ct_targets))
    _ct_index = {label: idx for idx, label in enumerate(_ct_labels)}

    country_topic_sankey_fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=18,
            line=dict(color="white", width=0.5),
            label=_ct_labels,
        ),
        link=dict(
            source=[_ct_index[_item] for _item in _ct_sources],
            target=[_ct_index[_item] for _item in _ct_targets],
            value=country_topic_sankey_df["n_works"].tolist(),
        ),
    )])
    country_topic_sankey_fig.update_layout(
        title="Sankey diagram: country to topic in AF-related research",
        width=980,
        height=620,
    )

    country_topic_sankey_fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the country → topic Sankey diagram

    这张 Sankey 图展示的是：

    **哪些国家的 AF 相关研究，主要流向哪些研究 topic。**

    ### 如何理解

    - 左侧是国家，右侧是 topic；
    - 连线越粗，说明该国家在该 topic 上的 AF 相关研究越多；
    - 如果少数国家流向大量 topic，说明这些国家不仅高产，而且更具 topic 覆盖能力；
    - 如果某些 topic 主要由少数国家贡献，说明 AF 扩散在 topic 层面也可能带有明显的国家集中性。

    ### 这张图的意义

    它帮助把“地理分布”与“研究方向分布”连接起来，回答：

    **全球哪些国家正在通过哪些主题路径推动 AlphaFold 相关知识生产。**
    """)
    return


@app.cell(hide_code=True)
def _(country_institution_sankey_df, go):
    _ci_sources = country_institution_sankey_df["country_code"].tolist()
    _ci_targets = country_institution_sankey_df["institution_name"].tolist()
    _ci_labels = list(dict.fromkeys(_ci_sources + _ci_targets))
    _ci_index = {label: idx for idx, label in enumerate(_ci_labels)}

    country_institution_sankey_fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=18,
            line=dict(color="white", width=0.5),
            label=_ci_labels,
        ),
        link=dict(
            source=[_ci_index[_item] for _item in _ci_sources],
            target=[_ci_index[_item] for _item in _ci_targets],
            value=country_institution_sankey_df["n_works"].tolist(),
        ),
    )])
    country_institution_sankey_fig.update_layout(
        title="Sankey diagram: country to institution in AF-related research",
        width=980,
        height=620,
    )

    country_institution_sankey_fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the country → institution Sankey diagram

    这张 Sankey 图展示的是：

    **哪些国家的 AF 相关研究，主要由哪些机构承载。**

    ### 如何理解

    - 左侧是国家，右侧是机构；
    - 连线越粗，说明该国通过该机构产出的 AF 相关论文越多；
    - 如果少数国家连接到多个重要机构，说明这些国家不仅拥有总量优势，也拥有更强的组织承载能力；
    - 如果少数机构吸收了来自多个国家的高强度连接，说明这些机构可能处在跨国知识生产网络的组织中心。

    ### 这张图的意义

    它帮助把“国家层面的地理分布”推进到“机构层面的组织结构”，回答：

    **AlphaFold 相关知识生产，是如何通过国家—机构之间的连接被组织起来的。**
    """)
    return


@app.cell(hide_code=True)
def _(px, top_institutions_af_df):
    treemap_af_df = top_institutions_af_df.copy()
    treemap_af_df["root_label"] = "AF-related research"

    af_treemap_fig = px.treemap(
        treemap_af_df,
        path=["root_label", "country_code", "institution_name"],
        values="n_af_works",
        color="n_af_works",
        color_continuous_scale="Reds",
        title="Treemap of AF-related output by country and institution",
    )
    af_treemap_fig.update_layout(width=980, height=680, margin=dict(l=20, r=20, t=60, b=20))

    af_treemap_fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the treemap of AF-related output

    这张 treemap 以层级结构展示 AF 相关研究的组织分布：

    - 最上层是整体 AF 相关研究；
    - 第二层是国家；
    - 第三层是机构。

    ### 如何理解

    - 区块越大，表示该国家或机构在 AF 相关研究中的累计产出越多；
    - 如果少数国家占据了最大的区块，说明 AF 的组织重心仍集中在少数国家；
    - 如果少数机构在各自国家内部占据非常大的区块，说明这些机构可能是该国 AF 研究的关键生产中心。

    ### 这张图的意义

    treemap 的优势在于，它能把“国家层面分布”和“机构层面分布”放进同一个层级视图里。与网络图相比，它更适合快速识别：

    **全球 AF 知识生产究竟是由哪些国家、哪些机构构成其主要组织骨架。**
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Additional exploratory structure visuals

    下面继续补充三类更偏探索式的图：

    1. **Heatmap with clustering**：用来观察各国 adoption pattern 是否存在相似分组；
    2. **Ridgeline / density-like distribution animation**：用来观察 AF vs Non-AF 的团队规模分布如何随时间演化；
    3. **Network visualization note**：说明国家与机构协作网络在当前 notebook 中采用的可运行实现方式，以及与 Cytoscape 的关系。
    """)
    return


@app.cell(hide_code=True)
def _(country_trend_df, px):
    adoption_matrix_df = country_trend_df.pivot_table(
        index="country_code",
        columns="publication_year",
        values="af_share",
        fill_value=0,
    )

    adoption_sort_df = adoption_matrix_df.copy()
    adoption_sort_df["max_af_share"] = adoption_sort_df.max(axis=1)
    adoption_sort_df["sum_af_share"] = adoption_sort_df.drop(columns=["max_af_share"], errors="ignore").sum(axis=1)
    adoption_sort_df = adoption_sort_df.sort_values(["max_af_share", "sum_af_share"], ascending=[False, False])
    clustered_country_order = adoption_sort_df.index.tolist()

    clustered_heatmap_fig = px.imshow(
        adoption_matrix_df.loc[clustered_country_order],
        aspect="auto",
        color_continuous_scale="Blues",
        labels=dict(x="Publication year", y="Country", color="AF share"),
        title="Heatmap of country adoption patterns (sorted by adoption intensity)",
    )
    clustered_heatmap_fig.update_layout(width=950, height=1400, margin=dict(l=20, r=20, t=60, b=20))

    clustered_heatmap_fig
    return


@app.cell(hide_code=True)
def _(px, team_structure_df):
    team_distribution_animation_df = team_structure_df.copy()
    team_distribution_animation_df["group_name"] = team_distribution_animation_df["is_alphafold_related"].map({True: "AF", False: "Non-AF"})
    team_distribution_animation_df["author_count_capped"] = team_distribution_animation_df["author_count"].clip(upper=30)

    team_distribution_animation_counts_df = team_distribution_animation_df.groupby(
        ["publication_year", "group_name", "author_count_capped"],
        as_index=False,
    ).size().rename(columns={"size": "paper_count"})
    team_distribution_animation_counts_df["group_total"] = team_distribution_animation_counts_df.groupby(
        ["publication_year", "group_name"]
    )["paper_count"].transform("sum")
    team_distribution_animation_counts_df["paper_share"] = (
        team_distribution_animation_counts_df["paper_count"] / team_distribution_animation_counts_df["group_total"]
    )

    team_distribution_animation_fig = px.bar(
        team_distribution_animation_counts_df,
        x="author_count_capped",
        y="paper_share",
        color="group_name",
        animation_frame="publication_year",
        barmode="group",
        color_discrete_map={"Non-AF": "#72B7B2", "AF": "#F58518"},
        labels={
            "author_count_capped": "Authors per paper (30 means 30+)",
            "paper_share": "Share of papers within group",
            "group_name": "Group",
        },
        title="Animated team size distribution share: AF vs Non-AF",
    )
    team_distribution_animation_fig.update_layout(width=980, height=560, margin=dict(l=20, r=20, t=60, b=20))
    team_distribution_animation_fig.update_yaxes(tickformat=".0%")

    team_distribution_animation_fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### About Cytoscape-style collaboration networks in this notebook

    你提到希望增加 **Cytoscape network for 国家和机构协作 both AF and Non-AF**。从分析目标上看，这非常合理，因为 Cytoscape 风格网络图非常适合展示：

    - 节点中心性；
    - 边的强弱；
    - 核心—桥梁—外围结构；
    - AF 与 Non-AF 协作网络之间的结构差异。

    不过在当前 notebook 环境里，最稳、最直接可运行的方案已经是前面新增的 **Plotly 版国家网络图** 和 **Plotly 版机构网络图**，并且它们已经同时提供：

    - AF 版本；
    - Non-AF 版本；
    - 年份滑块；
    - 节点大小；
    - 边粗细；
    - hover 交互。

    因此，在当前 notebook 中，这两组 Plotly 网络图实际上已经承担了 **Cytoscape-style collaboration network** 的主要分析功能。

    ### 方法上的区别

    - **Cytoscape** 更擅长复杂网络分析与社区布局；
    - **Plotly** 更适合在 notebook 中直接展示、交互和复现；
    - 对论文展示来说，当前 Plotly 网络图已经足以支持对 AF / Non-AF 协作结构的直观比较。

    ### 当前最合理的理解方式

    因此，这里不再额外重复增加一个无法稳定运行的 Cytoscape 图层，而是将前面已经构建的：

    - **AF / Non-AF country collaboration networks**
    - **AF / Non-AF institutional collaboration networks**

    视为当前 notebook 中的 **Cytoscape-style network views**。
    """)
    return


@app.cell(hide_code=True)
def _(analysis_duckdb, works_glob):
    overall_af_non_af_counts_df = analysis_duckdb.execute(f"""
    SELECT
        CASE WHEN COALESCE(is_alphafold_related, FALSE) THEN 'AF' ELSE 'Non-AF' END AS group_name,
        COUNT(*) AS n_works
    FROM read_parquet('{works_glob}')
    GROUP BY 1
    ORDER BY 1
    """).df()
    return (overall_af_non_af_counts_df,)


@app.cell(hide_code=True)
def _(alt, overall_af_non_af_counts_df):
    overall_af_non_af_bar_chart = alt.Chart(overall_af_non_af_counts_df).mark_bar().encode(
        x=alt.X("group_name:N", title="Group"),
        y=alt.Y("n_works:Q", title="Number of works"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Non-AF", "AF"],
                range=["#72B7B2", "#F58518"],
            ),
        ),
        tooltip=[
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("n_works:Q", title="Number of works", format=",.0f"),
        ],
    ).properties(
        title="All works: Non-AF vs AF",
        width=500,
        height=360,
    )

    overall_af_non_af_bar_chart
    return


@app.cell(hide_code=True)
def _(mo, overall_af_non_af_counts_df):
    overall_total_works = int(overall_af_non_af_counts_df["n_works"].sum())
    overall_af_works = int(
        overall_af_non_af_counts_df.loc[
            overall_af_non_af_counts_df["group_name"] == "AF", "n_works"
        ].sum()
    )
    overall_non_af_works = int(
        overall_af_non_af_counts_df.loc[
            overall_af_non_af_counts_df["group_name"] == "Non-AF", "n_works"
        ].sum()
    )

    mo.md(f"""
    ### Overall counts

    - **Total works**: {overall_total_works:,}
    - **Non-AF works**: {overall_non_af_works:,}
    - **AF works**: {overall_af_works:,}
    """)
    return


@app.cell(hide_code=True)
def _(country_trend_df):
    country_all_years_compare_df = country_trend_df.copy()
    country_all_years_compare_df["n_non_af_works"] = (
        country_all_years_compare_df["n_works"] - country_all_years_compare_df["n_af_works"]
    )

    country_compare_base_all_years_df = country_all_years_compare_df.groupby(
        "country_code", as_index=False
    ).agg({
        "n_af_works": "sum",
        "n_non_af_works": "sum",
    })

    country_compare_top15_codes_non_af = country_compare_base_all_years_df.sort_values(
        "n_non_af_works", ascending=False
    ).head(15)["country_code"].tolist()

    country_compare_top15_all_years_df = country_compare_base_all_years_df[
        country_compare_base_all_years_df["country_code"].isin(country_compare_top15_codes_non_af)
    ].copy()

    country_compare_top15_all_years_df = country_compare_top15_all_years_df.melt(
        id_vars=["country_code"],
        value_vars=["n_non_af_works", "n_af_works"],
        var_name="group_name",
        value_name="count_value",
    )

    country_compare_top15_all_years_df["group_name"] = country_compare_top15_all_years_df["group_name"].map({
        "n_non_af_works": "Non-AF",
        "n_af_works": "AF",
    })

    country_compare_top15_order_df = country_compare_base_all_years_df[
        country_compare_base_all_years_df["country_code"].isin(country_compare_top15_codes_non_af)
    ].sort_values("n_non_af_works", ascending=False)
    country_compare_top15_order = country_compare_top15_order_df["country_code"].tolist()
    return (
        country_all_years_compare_df,
        country_compare_top15_all_years_df,
        country_compare_top15_order,
    )


@app.cell
def _(country_all_years_compare_df):
    jp_country_compare_debug_df = country_all_years_compare_df.groupby(
        "country_code", as_index=False
    ).agg({
        "n_works": "sum",
        "n_af_works": "sum",
        "n_non_af_works": "sum",
    })
    jp_country_compare_debug_df["af_rank"] = jp_country_compare_debug_df["n_af_works"].rank(method="min", ascending=False)
    jp_country_compare_debug_df["non_af_rank"] = jp_country_compare_debug_df["n_non_af_works"].rank(method="min", ascending=False)
    jp_country_compare_debug_df = jp_country_compare_debug_df.sort_values("n_af_works", ascending=False)
    jp_country_compare_debug_df[jp_country_compare_debug_df["country_code"] == "JP"]
    return


@app.cell(hide_code=True)
def _(alt, country_compare_top15_all_years_df, country_compare_top15_order):
    country_af_non_af_compare_chart_2025 = alt.Chart(country_compare_top15_all_years_df).mark_bar().encode(
        x=alt.X("count_value:Q", title="Number of works"),
        y=alt.Y("country_code:N", sort=country_compare_top15_order, title="Country"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Non-AF", "AF"],
                range=["#72B7B2", "#F58518"],
            ),
        ),
        column=alt.Column(
            "group_name:N",
            title="Group",
            sort=["Non-AF", "AF"],
        ),
        tooltip=[
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("count_value:Q", title="Number of works", format=",.0f"),
        ],
    ).properties(
        title="Top 15 countries by cumulative Non-AF output: Non-AF vs AF-related output",
        width=360,
        height=420,
    ).resolve_scale(
        x="independent"
    )

    country_af_non_af_compare_chart_2025
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Interpreting the cumulative Non-AF vs AF country comparison

    这张图把各国在整个观察期内的 **累计 Non-AF 论文数量** 与 **累计 AF 相关论文数量** 并排展示，用来比较两种知识生产格局是否一致。

    ### 当前图的筛选口径

    这张图现在采用的是 **固定同一组国家进行对比** 的方式：

    - 先按 **累计 `n_non_af_works`** 选出 top 15 国家；
    - 再对这同一组国家同时展示：
      - 左侧 **Non-AF** 面板；
      - 右侧 **AF** 面板。

    因此，左右两边的国家集合是完全一致的，可以直接逐国比较。

    ### 如何理解

    - **左侧 Non-AF 面板**反映的是总体科研体系中的常规产出格局；
    - **右侧 AF 面板**反映的是同一批国家在 AlphaFold 相关研究中的累计知识生产格局；
    - 如果两边的头部国家相对位置大体一致，说明 AF 的扩散主要沿着原有科研强国格局展开；
    - 如果某些国家在右侧 AF 面板中的相对表现更突出，则说明这些国家在 AlphaFold 相关知识生产中具有更强的相对优势；
    - 如果某些国家在左侧规模很大、但右侧明显偏低，则说明这些国家虽然总体科研产出较高，但 AF 渗透或 AF 相关产出相对较弱。

    ### 为什么这里使用独立坐标轴

    由于累计 Non-AF 论文数量远大于累计 AF 论文数量，如果两侧使用相同的 x 轴尺度，AF 面板会被压缩得几乎无法阅读。因此，这里对左右面板使用 **independent x scales**，目的是让：

    - Non-AF 的总体规模格局清楚可见；
    - AF 的国家差异也能被清楚辨认；
    - 从而更好地比较“同一组国家在两种产出口径下的相对表现”，而不是单纯比较绝对数量级。

    ### 这张图的意义

    这张图特别适合回答：

    **在总体科研产出排名靠前的国家中，哪些国家也同步形成了较强的 AlphaFold 相关知识生产能力，哪些国家则相对偏弱。**
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### Interpreting the cumulative AF-anchored country comparison

    这张图与上面那张 **按累计 Non-AF 选 top 15 国家** 的图互为补充。这里的筛选口径改为：

    - 先按 **累计 `n_af_works`** 选出 top 15 国家；
    - 再对这同一组国家同时展示：
      - 左侧 **AF** 面板；
      - 右侧 **Non-AF** 面板。

    因此，这张图的重点不再是“总体科研强国中谁的 AF 表现更强”，而是：

    **在 AlphaFold 相关知识生产最活跃的国家中，它们在总体 Non-AF 研究中的位置是否也同样突出。**

    ### 如何理解

    - **左侧 AF 面板**显示的是 AlphaFold 相关知识生产的核心国家；
    - **右侧 Non-AF 面板**显示的是这同一批国家在更一般科研产出中的规模；
    - 如果一个国家在左侧 AF 面板排名很靠前，但在右侧 Non-AF 面板中相对位置没有那么突出，说明它在 AF 相关研究中的相对优势强于其在总体科研体系中的常规位置；
    - 如果某个国家在 AF 与 Non-AF 两侧都非常靠前，说明它既是一般科研强国，也是 AF 扩散中的核心生产国；
    - 如果某些国家进入了 AF top 15，但在 Non-AF 面板中并不特别靠前，则说明 AlphaFold 可能为这些国家提供了更突出的相对进入机会或专业化优势。

    ### 这张图的意义

    因此，这张图特别适合回答：

    **在 AF 相关知识生产最核心的国家中，哪些国家只是沿着原有科研强国格局延续领先，哪些国家则在 AlphaFold 相关研究中表现出更强的相对跃升。**

    把这张图和上面那张 Non-AF 锚定图结合起来看，可以更清楚地区分两种国家：

    - 一类是本来就在总体科研体系中占据核心位置、同时也主导 AF 相关产出；
    - 另一类是虽然总体科研规模未必最顶尖，但在 AF 相关研究中显示出更高的相对集中度或专业化优势。
    """)
    return


@app.cell(hide_code=True)
def _(
    alt,
    country_compare_top15_af_anchor_all_years_df,
    country_compare_top15_af_anchor_order,
):
    country_af_anchor_compare_chart = alt.Chart(country_compare_top15_af_anchor_all_years_df).mark_bar().encode(
        x=alt.X("count_value:Q", title="Number of works"),
        y=alt.Y("country_code:N", sort=country_compare_top15_af_anchor_order, title="Country"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["AF", "Non-AF"],
                range=["#F58518", "#72B7B2"],
            ),
        ),
        column=alt.Column(
            "group_name:N",
            title="Group",
            sort=["AF", "Non-AF"],
        ),
        tooltip=[
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("count_value:Q", title="Number of works", format=",.0f"),
        ],
    ).properties(
        title="Top 15 countries by cumulative AF-related output: AF vs Non-AF output",
        width=360,
        height=420,
    ).resolve_scale(
        x="independent"
    )

    country_af_anchor_compare_chart
    return


@app.cell(hide_code=True)
def _(country_all_years_compare_df):
    country_compare_base_af_anchor_all_years_df = country_all_years_compare_df.groupby(
        "country_code", as_index=False
    ).agg({
        "n_af_works": "sum",
        "n_non_af_works": "sum",
    })

    country_compare_top15_codes_af = country_compare_base_af_anchor_all_years_df.sort_values(
        "n_af_works", ascending=False
    ).head(15)["country_code"].tolist()

    country_compare_top15_af_anchor_all_years_df = country_compare_base_af_anchor_all_years_df[
        country_compare_base_af_anchor_all_years_df["country_code"].isin(country_compare_top15_codes_af)
    ].copy()

    country_compare_top15_af_anchor_all_years_df = country_compare_top15_af_anchor_all_years_df.melt(
        id_vars=["country_code"],
        value_vars=["n_af_works", "n_non_af_works"],
        var_name="group_name",
        value_name="count_value",
    )

    country_compare_top15_af_anchor_all_years_df["group_name"] = country_compare_top15_af_anchor_all_years_df["group_name"].map({
        "n_af_works": "AF",
        "n_non_af_works": "Non-AF",
    })

    country_compare_top15_af_anchor_order_df = country_compare_base_af_anchor_all_years_df[
        country_compare_base_af_anchor_all_years_df["country_code"].isin(country_compare_top15_codes_af)
    ].sort_values("n_af_works", ascending=False)
    country_compare_top15_af_anchor_order = country_compare_top15_af_anchor_order_df["country_code"].tolist()
    return (
        country_compare_top15_af_anchor_all_years_df,
        country_compare_top15_af_anchor_order,
    )


@app.cell(hide_code=True)
def _(analysis_duckdb, pd, work_institutions_glob, works_glob):
    institution_af_non_af_compare_df = analysis_duckdb.execute(f"""
    WITH work_flags AS (
        SELECT
            work_id,
            COALESCE(is_alphafold_related, FALSE) AS is_alphafold_related
        FROM read_parquet('{works_glob}')
    ),
    work_institutions_dedup AS (
        SELECT DISTINCT
            wi.work_id,
            wi.institution_id,
            wi.institution_name,
            wi.country_code
        FROM read_parquet('{work_institutions_glob}') AS wi
        WHERE wi.institution_id IS NOT NULL
          AND wi.institution_name IS NOT NULL
    ),
    inst_work_counts AS (
        SELECT
            wid.institution_id,
            wid.institution_name,
            wid.country_code,
            SUM(CASE WHEN wf.is_alphafold_related THEN 1 ELSE 0 END) AS n_af_works,
            SUM(CASE WHEN wf.is_alphafold_related THEN 0 ELSE 1 END) AS n_non_af_works
        FROM work_institutions_dedup AS wid
        INNER JOIN work_flags AS wf
            ON wid.work_id = wf.work_id
        GROUP BY 1, 2, 3
    )
    SELECT *
    FROM inst_work_counts
    """).df()

    institution_af_top15_all_years_df = institution_af_non_af_compare_df[[
        "institution_name", "country_code", "n_af_works"
    ]].copy().rename(columns={"n_af_works": "count_value"})
    institution_af_top15_all_years_df["group_name"] = "AF"
    institution_af_top15_all_years_df = institution_af_top15_all_years_df.sort_values("count_value", ascending=False).head(15)

    institution_non_af_top15_all_years_df = institution_af_non_af_compare_df[[
        "institution_name", "country_code", "n_non_af_works"
    ]].copy().rename(columns={"n_non_af_works": "count_value"})
    institution_non_af_top15_all_years_df["group_name"] = "Non-AF"
    institution_non_af_top15_all_years_df = institution_non_af_top15_all_years_df.sort_values("count_value", ascending=False).head(15)

    institution_compare_top15_all_years_df = pd.concat(
        [institution_af_top15_all_years_df, institution_non_af_top15_all_years_df],
        ignore_index=True,
    )
    return (institution_compare_top15_all_years_df,)


@app.cell(hide_code=True)
def _(alt, institution_compare_top15_all_years_df):
    institution_af_non_af_compare_chart = alt.Chart(institution_compare_top15_all_years_df).mark_bar().encode(
        x=alt.X("count_value:Q", title="Number of works"),
        y=alt.Y("institution_name:N", sort="-x", title="Institution"),
        color=alt.Color(
            "group_name:N",
            title="Group",
            scale=alt.Scale(
                domain=["Non-AF", "AF"],
                range=["#72B7B2", "#F58518"],
            ),
        ),
        column=alt.Column("group_name:N", title="Group"),
        tooltip=[
            alt.Tooltip("group_name:N", title="Group"),
            alt.Tooltip("institution_name:N", title="Institution"),
            alt.Tooltip("country_code:N", title="Country"),
            alt.Tooltip("count_value:Q", title="Number of works", format=",.0f"),
        ],
    ).properties(
        title="Top institutions by cumulative Non-AF vs AF-related output",
        width=420,
        height=520,
    ).resolve_scale(
        x="independent"
    )

    institution_af_non_af_compare_chart
    return


@app.cell(hide_code=True)
def _(country_trend_df, go):
    country_sankey_years = [2021, 2022, 2023, 2024, 2025]
    country_year_af_sankey_base_df = country_trend_df[
        country_trend_df["publication_year"].isin(country_sankey_years)
    ].copy()
    country_year_af_sankey_base_df = country_year_af_sankey_base_df[
        country_year_af_sankey_base_df["n_af_works"] > 0
    ].copy()

    country_sankey_rank_df = country_year_af_sankey_base_df.groupby("country_code", as_index=False)["n_af_works"].sum()
    country_sankey_top_codes = country_sankey_rank_df.sort_values(
        "n_af_works", ascending=False
    ).head(20)["country_code"].tolist()

    country_year_af_sankey_df = country_year_af_sankey_base_df[
        country_year_af_sankey_base_df["country_code"].isin(country_sankey_top_codes)
    ].copy()

    country_sankey_node_labels = []
    country_sankey_node_x = []
    country_sankey_node_colors = []
    country_sankey_node_customdata = []
    country_sankey_node_index = {}

    _country_sankey_year_color_map = {
        2021: "#9ecae1",
        2022: "#6baed6",
        2023: "#4292c6",
        2024: "#2171b5",
        2025: "#084594",
    }

    for _year_idx, _year in enumerate(country_sankey_years):
        _year_df = country_year_af_sankey_df[
            country_year_af_sankey_df["publication_year"] == _year
        ].sort_values("n_af_works", ascending=False).copy()

        for _, _row in _year_df.iterrows():
            _country_code = _row["country_code"]
            _count_value = _row["n_af_works"]
            _node_label = f"{_year} | {_country_code}"
            country_sankey_node_index[(_year, _country_code)] = len(country_sankey_node_labels)
            country_sankey_node_labels.append(_node_label)
            country_sankey_node_x.append(_year_idx / (len(country_sankey_years) - 1))
            country_sankey_node_colors.append(_country_sankey_year_color_map[_year])
            country_sankey_node_customdata.append([_year, _country_code, float(_count_value)])

    country_sankey_sources = []
    country_sankey_targets = []
    country_sankey_values = []
    country_sankey_link_labels = []
    country_sankey_link_colors = []

    for _year_idx in range(len(country_sankey_years) - 1):
        _year_left = country_sankey_years[_year_idx]
        _year_right = country_sankey_years[_year_idx + 1]

        _left_df = country_year_af_sankey_df[
            country_year_af_sankey_df["publication_year"] == _year_left
        ][["country_code", "n_af_works"]].copy()
        _right_df = country_year_af_sankey_df[
            country_year_af_sankey_df["publication_year"] == _year_right
        ][["country_code", "n_af_works"]].copy()

        _merged_df = _left_df.merge(
            _right_df,
            on="country_code",
            how="inner",
            suffixes=("_left", "_right"),
        )

        for _, _link_row in _merged_df.iterrows():
            _country_code = _link_row["country_code"]
            _source_idx = country_sankey_node_index.get((_year_left, _country_code))
            _target_idx = country_sankey_node_index.get((_year_right, _country_code))
            if _source_idx is None or _target_idx is None:
                continue
            _flow_value = float(min(_link_row["n_af_works_left"], _link_row["n_af_works_right"]))
            if _flow_value <= 0:
                continue
            country_sankey_sources.append(_source_idx)
            country_sankey_targets.append(_target_idx)
            country_sankey_values.append(_flow_value)
            country_sankey_link_labels.append(
                f"{_country_code}: {_year_left} → {_year_right}<br>Flow value: {_flow_value:,.0f}"
            )
            country_sankey_link_colors.append("rgba(80, 80, 80, 0.20)")

    country_year_flow_sankey_fig = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=15,
            thickness=16,
            line=dict(color="white", width=0.6),
            label=country_sankey_node_labels,
            x=country_sankey_node_x,
            color=country_sankey_node_colors,
            customdata=country_sankey_node_customdata,
            hovertemplate="Year: %{customdata[0]}<br>Country: %{customdata[1]}<br>AF-related works: %{customdata[2]:,.0f}<extra></extra>",
        ),
        link=dict(
            source=country_sankey_sources,
            target=country_sankey_targets,
            value=country_sankey_values,
            color=country_sankey_link_colors,
            label=country_sankey_link_labels,
            hovertemplate="%{label}<extra></extra>",
        ),
    )])
    country_year_flow_sankey_fig.update_layout(
        title="Five-layer Sankey diagram of AF-related country output, 2021–2025",
        width=1200,
        height=1000,
        margin=dict(l=20, r=20, t=60, b=20),
    )

    country_year_flow_sankey_fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### How to read the five-layer country Sankey diagram

    这张 Sankey 图把 **2021–2025 年 AF 相关研究的国家产出** 组织成一个五层结构：

    - 每一层对应一个年份；
    - 每个节点代表该年一个国家的 AF 相关产出；
    - 节点 hover 中显示该国家在该年的 `n_af_works`；
    - 相邻年份之间的连线表示同一国家在连续年份中的“产出延续”。

    ### 当前连线值的含义

    这里的层间连线不是论文逐篇追踪得到的真实流动，而是一个 **年度连续性 proxy**：

    - 对于同一个国家在相邻两年之间的连接，连线值取两年产出中的较小值；
    - 因此它表达的是：这个国家在两年之间有多大规模的 AF 相关产出是“可以连续对应”的；
    - 连线越粗，说明该国家在相邻年份中的 AF 研究产出延续性越强。

    ### 这张图主要能看什么

    可以重点观察三类结构特征：

    1. **哪些国家在多层中持续出现**
       - 如果一个国家从 2021 一直连接到 2025，说明它不是短期进入，而是持续处在 AF 相关知识生产网络中。
    2. **哪些国家的连线更粗**
       - 较粗的连接说明该国家在相邻年份之间保持了更强的产出连续性，通常意味着更稳定的 adoption 与生产能力。
    3. **哪些国家在后期才进入主层结构**
       - 如果某些国家在前几年缺席、但在后几年出现并形成连接，说明这些国家更像是后续进入 AF 扩散主干网络的参与者。

    ### 这张图揭示的含义

    与前面的 heatmap 不同，这张 Sankey 图强调的不是某一年 adoption 强不强，而是：

    **哪些国家构成了 2021–2025 年 AF 相关知识生产的持续性主干，以及这种主干结构在时间上如何延续、扩展或重新排序。**

    因此，这张图特别适合支持这样一种理解：

    - 有些国家是 AF 扩散中的早期持续核心；
    - 有些国家是在后期快速进入并扩大产出的新参与者；
    - 全球 AF 知识生产并不是每年都完全重新洗牌，而是沿着一部分持续国家主干逐步演化。
    """)
    return


@app.cell(hide_code=True)
def _(annual_trend_df):
    af_annual_2021_2025_df = annual_trend_df[
        annual_trend_df["publication_year"].between(2021, 2025)
    ][["publication_year", "n_af_works"]].copy()
    af_annual_2021_2025_df["yoy_growth"] = af_annual_2021_2025_df["n_af_works"].pct_change()

    af_begin_value = float(
        af_annual_2021_2025_df.loc[
            af_annual_2021_2025_df["publication_year"] == 2021, "n_af_works"
        ].iloc[0]
    )
    af_end_value = float(
        af_annual_2021_2025_df.loc[
            af_annual_2021_2025_df["publication_year"] == 2025, "n_af_works"
        ].iloc[0]
    )
    af_cagr_2021_2025 = (af_end_value / af_begin_value) ** (1 / 4) - 1

    af_annual_2021_2025_display_df = af_annual_2021_2025_df.copy()
    af_annual_2021_2025_display_df["yoy_growth_pct"] = af_annual_2021_2025_display_df["yoy_growth"]

    af_annual_2021_2025_display_df
    return (
        af_annual_2021_2025_df,
        af_begin_value,
        af_cagr_2021_2025,
        af_end_value,
    )


@app.cell(hide_code=True)
def _(af_begin_value, af_cagr_2021_2025, af_end_value, mo):
    mo.md(rf"""
    ## AF-related works in 2021–2025

    上表给出了 2021–2025 年每年的 **AF-related works** 数量，以及相对于上一年的同比增长率。

    - **2021 年 AF works**: {af_begin_value:,.0f}
    - **2025 年 AF works**: {af_end_value:,.0f}
    - **2021–2025 CAGR**: {af_cagr_2021_2025:.2%}

    这里的 CAGR 使用 2021 作为起点、2025 作为终点，并按 4 个年度间隔计算：

    $$
    CAGR = \left(\frac{{AF_{2025}}}{{AF_{2021}}}\right)^{{1/4}} - 1
    $$

    因此，这个指标反映的是：**如果把 2021–2025 年 AF 相关研究的增长看作一条平滑的复合增长路径，其年均复合增长速度是多少。**
    """)
    return


@app.cell(hide_code=True)
def _(af_annual_2021_2025_df, af_cagr_2021_2025, go):
    af_annual_2021_2025_plotly_fig = go.Figure()
    af_annual_2021_2025_plotly_fig.add_trace(go.Scatter(
        x=af_annual_2021_2025_df["publication_year"],
        y=af_annual_2021_2025_df["n_af_works"],
        mode="lines+markers+text",
        line=dict(color="#ff7f0e", width=4),
        marker=dict(size=10, color="#d62728", line=dict(color="white", width=1.5)),
        text=af_annual_2021_2025_df["n_af_works"].astype(int),
        textposition="top center",
        hovertemplate="Year: %{x}<br>AF-related works: %{y:,.0f}<extra></extra>",
        name="AF-related works",
    ))
    af_annual_2021_2025_plotly_fig.update_layout(
        title=f"AF-related works, 2021–2025 (CAGR: {af_cagr_2021_2025:.2%})",
        xaxis_title="Publication year",
        yaxis_title="AF-related works",
        width=950,
        height=500,
        template="plotly_white",
        margin=dict(l=20, r=20, t=70, b=20),
    )
    af_annual_2021_2025_plotly_fig.update_xaxes(dtick=1)

    af_annual_2021_2025_plotly_fig
    return


if __name__ == "__main__":
    app.run()
