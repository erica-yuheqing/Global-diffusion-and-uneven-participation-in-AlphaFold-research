"""Offline annual SCImago import; exact ISSN identity links, no rank modelling.

The original semicolon CSV is archived byte-for-byte. Annual SJR and category
quartiles remain distinct from CiteScore percentiles and article quality.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

import pandas as pd

from collect import HERE, SOURCE, STORE, dump_new, issn, now, require, sha

MAX_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100000


def number(value):
    text = value.strip()
    if text in {"", "-", "N/A", "NA"}:
        return None
    require(bool(re.fullmatch(r"\d+(?:[,.]\d+)?", text)), "Unexpected SJR number convention")
    result = float(text.replace(",", "."))
    require(math.isfinite(result) and result >= 0, "Invalid SJR value")
    return result


def parse(path, year):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Expected regular CSV, not symlink")
    require(path.stat().st_nlink == 1 and path.stat().st_size <= MAX_BYTES, "Input link/byte limit")
    require(2015 <= year <= 2025, "Metric year outside approved scope")
    csv.field_size_limit(65536)
    records, categories, issues = [], [], []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader([stream.readline()], delimiter=";", strict=True))
        require(10 <= len(header) <= 64, "Unexpected column count")
        counts = Counter(header)
        require({k: v for k, v in counts.items() if v > 1} in ({}, {"Publisher": 2}), "Unreviewed duplicate headers")
        years = [int(m.group(1)) for col in header if (m := re.fullmatch(r"Total Docs\. \((\d{4})\)", col))]
        require(years == [year], "Declared year does not match annual document header")
        required = {"Sourceid", "Title", "Type", "Issn", "SJR", "SJR Best Quartile", "Categories"}
        require(required <= set(header), "Missing SCImago fields")
        # Two Publisher columns are preserved positionally, not silently overwritten.
        seen = Counter()
        names = []
        for name in header:
            seen[name] += 1
            names.append(f"{name}_{seen[name]}" if counts[name] > 1 else name)
        ids = set()
        for line_number, line in enumerate(stream, 2):
            # Some provider exports contain unescaped quotation marks in titles.
            # Compatibility parsing never skips a row. Flag and quarantine such
            # records from usable metrics; retain original bytes for review.
            quote_warning = False
            try:
                row = next(csv.reader([line], delimiter=";", strict=True))
            except csv.Error:
                row = next(csv.reader([line], delimiter=";", strict=False))
                quote_warning = True
            require(len(records) < MAX_ROWS, "Row limit exceeded; no partial import")
            require(len(row) == len(header), "Non-rectangular annual CSV")
            raw = dict(zip(names, row))
            identifier = raw["Sourceid"].strip()
            require(bool(re.fullmatch(r"\d+", identifier)), "Invalid SCImago source ID")
            require(identifier not in ids, "Duplicate annual SCImago source ID")
            ids.add(identifier)
            if quote_warning:
                issues.append({"scimago_source_id": identifier, "issue": "csv_quote_syntax_quarantined", "raw_value": f"physical_line={line_number}"})
            valid = set()
            for token in raw["Issn"].split(","):
                if not token.strip():
                    continue
                normalized = issn(token)
                if normalized:
                    valid.add(normalized)
                else:
                    issues.append({"scimago_source_id": identifier, "issue": "invalid_issn", "raw_value": token})
            quartile = raw["SJR Best Quartile"].strip()
            require(quartile in {"Q1", "Q2", "Q3", "Q4", "-", ""}, "Unexpected best quartile")
            category_names = set()
            for token in raw["Categories"].split(";"):
                token = token.strip()
                if not token:
                    continue
                match = re.fullmatch(r"(.+?)\s*\((Q[1-4])\)", token)
                name, q = (match.group(1).strip(), match.group(2)) if match else (token, None)
                require(name not in category_names, "Duplicate category within annual source")
                category_names.add(name)
                categories.append({"scimago_source_id": identifier, "metric_year": year, "category": name, "category_quartile": q})
            records.append({**raw, "scimago_source_id": identifier, "metric_year": year,
                            "provider_type": raw["Type"].strip().lower(), "sjr": number(raw["SJR"]),
                            "best_quartile": quartile if quartile.startswith("Q") else None,
                            "valid_issns_json": json.dumps(sorted(valid)), "csv_quote_warning": quote_warning})
    require(len(records) > 0, "Empty annual CSV")
    return (pd.DataFrame(records), pd.DataFrame(categories, columns=["scimago_source_id", "metric_year", "category", "category_quartile"]),
            pd.DataFrame(issues, columns=["scimago_source_id", "issue", "raw_value"]), header)


def match_sources(metadata, providers, year):
    index = defaultdict(set)
    for row in providers.itertuples(index=False):
        for value in json.loads(row.valid_issns_json):
            index[value].add(row.scimago_source_id)
    lookup = providers.set_index("scimago_source_id")
    output = []
    for row in metadata.itertuples(index=False):
        values = json.loads(row.issns_json) if isinstance(row.issns_json, str) else []
        candidates = sorted(set().union(*(index[x] for x in values))) if values else []
        result = {"source_id": row.source_id, "metric_year": year, "source_type": row.source_type,
                  "candidate_ids_json": json.dumps(candidates), "scimago_source_id": None,
                  "sjr": None, "best_quartile": None, "usable_journal_metric": False}
        if not values:
            status = "no_valid_source_issn"
        elif not candidates:
            status = "no_exact_issn_match"
        elif len(candidates) > 1:
            status = "ambiguous_provider_ids_quarantined"
        else:
            p = lookup.loc[candidates[0]]
            result.update(scimago_source_id=candidates[0], sjr=p.sjr, best_quartile=p.best_quartile)
            if p.csv_quote_warning:
                status = "provider_csv_quote_warning_quarantined"
            elif row.source_type != "journal" or p.provider_type != "journal":
                status = "nonjournal_identity_match_only"
            elif pd.isna(p.sjr):
                status = "matched_journal_sjr_missing"
            else:
                status = "matched_journal_sjr"
                result["usable_journal_metric"] = True
        output.append({**result, "match_status": status})
    frame = pd.DataFrame(output)
    require(frame.source_id.is_unique and len(frame) == len(metadata), "Source match cardinality differs")
    return frame


def frozen_inputs():
    mp = sorted((STORE / "snapshots").glob("*/snapshot_manifest.json"))[-1]
    sm = json.loads(mp.read_text())
    snapshot = mp.parent
    ap = STORE / "audits" / snapshot.name / "audit_manifest.json"
    am = json.loads(ap.read_text())
    require(am["snapshot_manifest_sha256"] == sha(mp), "Metadata/audit lineage differs")
    pins = {}
    for directory, manifest in [(snapshot, sm), (ap.parent, am)]:
        for name, pin in manifest["outputs"].items():
            path = directory / name
            require(sha(path) == pin["sha256"], "Frozen metadata/audit output differs")
            pins[str(path)] = sha(path)
    for name, digest in am["code"].items():
        require(sha(HERE / name) == digest, "Upstream collector/audit code differs")
    studies = SOURCE / "data/studies.parquet"
    upstream = SOURCE / "run_manifest.json"
    require(sha(studies) == json.loads(upstream.read_text())["outputs"]["data/studies.parquet"]["sha256"], "Frozen studies differ")
    for path in [mp, ap, upstream, studies]:
        pins[str(path)] = sha(path)
    return (pd.read_parquet(snapshot / "source_metadata.parquet"),
            pd.read_parquet(ap.parent / "source_year_requirements.parquet"), studies, pins)


def assemble(path, year):
    providers, categories, issues, header = parse(path, year)
    metadata, needs, studies_path, pins = frozen_inputs()
    matches = match_sources(metadata, providers, year)
    needs_y = needs[needs.year.eq(year)].merge(matches.drop(columns=["source_type"]), on="source_id", how="left", validate="one_to_one")
    studies = pd.read_parquet(studies_path, columns=["study_id", "year", "work_type", "confirmed_af", "source_id", "group_name"])
    studies = studies[studies.year.eq(year)]
    require(studies.study_id.is_unique, "Study IDs duplicate before source join")
    joined = studies.merge(matches[["source_id", "match_status", "usable_journal_metric", "scimago_source_id", "sjr", "best_quartile"]], on="source_id", how="left", validate="many_to_one")
    joined["usable_journal_metric"] = joined.usable_journal_metric.fillna(False).astype(bool)
    joined["match_status"] = joined.match_status.fillna("source_absent_or_outside_selected_scope")
    coverage = joined.groupby(["group_name", "work_type", "match_status"], dropna=False).agg(studies=("study_id", "size"), usable_sjr=("usable_journal_metric", "sum")).reset_index()
    af = joined[joined.confirmed_af]
    af_journal_types = af[af.work_type.isin(["article", "review"])]
    require(int(coverage.studies.sum()) == len(studies), "Coverage join expanded/dropped studies")
    summary = {"metric_year": year, "provider_rows": len(providers), "provider_type_counts": providers.provider_type.value_counts().to_dict(),
               "sjr_present_rows": int(providers.sjr.notna().sum()), "best_quartile_present_rows": int(providers.best_quartile.notna().sum()),
               "category_rows": len(categories), "category_quartile_present_rows": int(categories.category_quartile.notna().sum()),
               "invalid_provider_issn_tokens": int(issues.issue.eq("invalid_issn").sum()),
               "provider_csv_quote_warning_rows": int(providers.csv_quote_warning.sum()),
               "selected_source_match_status_counts": matches.match_status.value_counts().to_dict(),
               "required_source_year_cells": len(needs_y), "required_source_year_cells_with_sjr": int(needs_y.usable_journal_metric.sum()),
               "AF_studies_this_year": len(af), "AF_studies_with_usable_sjr": int(af.usable_journal_metric.sum()),
               "AF_article_review_studies": len(af_journal_types), "AF_article_review_with_usable_sjr": int(af_journal_types.usable_journal_metric.sum()),
               "missing_metric_years": [y for y in range(2015,2026) if y != year], "formal_position_analysis_ready": False,
               "dataset_scope": "user-supplied annual export; all rows preserved; global filter completeness not certified from CSV alone"}
    frames = {"provider_records.parquet": providers, "category_quartiles.parquet": categories,
              "invalid_issns_review.csv": issues, "source_matches.parquet": matches,
              "source_year_matches.parquet": needs_y, "study_coverage.csv": coverage,
              "AF_study_matches.parquet": af}
    return frames, summary, pins, header


def report(summary):
    n = summary["AF_article_review_studies"]
    k = summary["AF_article_review_with_usable_sjr"]
    return f"""# SCImago {summary['metric_year']} 接收、导入与匹配核验

## 本次结果

- 全文件扫描并保留：{summary['provider_rows']:,}条来源，其中journal {summary['provider_type_counts'].get('journal', 0):,}条。
- 有SJR数值：{summary['sjr_present_rows']:,}条；逐类别记录：{summary['category_rows']:,}条。
- 本研究冻结范围内：{summary['required_source_year_cells']:,}个2025来源—年需求单元；可用SJR覆盖{summary['required_source_year_cells_with_sjr']:,}个。
- 2025年已确认AF研究：{summary['AF_studies_this_year']:,}项；可接入期刊SJR的有{summary['AF_studies_with_usable_sjr']:,}项。
- 限定article/review：{n:,}项，其中{k:,}项可接入SJR（{100*k/n:.1f}%）。这是研究级覆盖，不是机构比较的最终支持样本。

## 格式与连接规则

观测单位为一个SCImago来源×2025年；逐学科分区另表保存，不能直接与论文多对多连接。
文件是UTF-8、分号分隔、小数逗号格式。年份依据用户提交文件及`Total Docs. (2025)`表头；不以文件名单独认定年份。
两个Publisher列按位置保留；原文件逐字节归档，没有修改或丢行。

发现{summary['provider_csv_quote_warning_rows']}条引号语法不规范记录，以兼容读取保存、另列核验，并从可用指标中隔离。
发现{summary['invalid_provider_issn_tokens']}个ISSN校验失败值，原值保留，不进入连接。
{summary['selected_source_match_status_counts'].get('ambiguous_provider_ids_quarantined', 0)}个OpenAlex来源匹配多个SCImago ID，单列冲突，不凭名称或最佳排名挑选。

精确匹配使用校验通过的印刷／电子ISSN。同一来源有多个ISSN也只生成一行来源匹配和一行研究匹配。
OpenAlex和SCImago均为journal且SJR可用、无引号隔离问题时才算可用期刊指标。
未匹配、非期刊、缺指标与真实零分开，未知不填0、不归Q4。

## 字段与可解释边界

| 字段 | 含义 | 单位／缺失规则 |
|---|---|---|
| metric_year | 指标对应年 | 2025，不能倒填其他年 |
| sjr | 导出SJR原值 | 非负；空／-保留缺失；不是跨领域百分位 |
| best_quartile | 官方最佳类别分区 | Q1–Q4；不是类别均值 |
| category_quartile | 各学科类别分区 | 另表；无分区保留空，不伪造 |
| usable_journal_metric | 期刊身份、唯一ISSN匹配及SJR均可用 | 覆盖标志，不是质量评价 |
| match_status | 缺失／冲突／非期刊原因 | 互斥状态；不自动替换来源身份 |

保留全文件所有行，但CSV本身没有国家／学科筛选元信息，因此不能仅由文件证明它是无筛选的全球完整版。
本次不计算新的学科内百分位、不选择多学科聚合规则、不运行模型，也不改变Figure5旧结果。
期刊定位不等同单篇文章质量；当前结果不能回答AF是否导致机构进入更好的渠道。

## 接下来需要的文件

还缺2015–2024年各年的官方全量CSV，共10份。2015–2019用于机构前期定位；2020–2024用于发表年对应比较。
下载时保留全国家、全学科、全类型默认范围；不只下载AF期刊。
齐备后再冻结多类别处理规则，并重建同机构／年／类型／子领域参照支持，才进行期刊定位关联比较。

## 文件入口

- [原始归档](raw/annual.csv)
- [完整来源记录](provider_records.parquet)
- [逐类别分区](category_quartiles.parquet)
- [来源匹配状态](source_matches.parquet)
- [实际来源—年份匹配](source_year_matches.parquet)
- [研究级覆盖分类](study_coverage.csv)
- [2025 AF研究匹配](AF_study_matches.parquet)
- [格式／ISSN问题清单](invalid_issns_review.csv)
- [输入输出哈希及口径](import_manifest.json)

## 工具说明

沿用本项目已验证的Parquet环境；数据检查技能促使逐项保留缺失、冲突与原始字节，不做自动填补。
软件方法参考：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026).
[Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065)。
"""


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "import_manifest.json").read_text())
    require(sha(Path(__file__)) == manifest["importer_sha256"], "Importer version differs")
    for path, digest in manifest["input_pins"].items():
        require(sha(path) == digest, "Pinned input differs")
    for name, pin in manifest["outputs"].items():
        require(sha(directory / name) == pin["sha256"], "Imported output differs")
    frames, summary, _, header = assemble(directory / "raw/annual.csv", manifest["metric_year"])
    require(summary == manifest["summary"] and header == manifest["original_header"], "Summary/header reconstruction differs")
    require((directory / "report_zh.md").read_text() == report(summary), "Report reconstruction differs")
    for name, expected in frames.items():
        if name.endswith(".parquet"):
            actual = pd.read_parquet(directory / name)
            # Dataframe index is intentionally not exported; compare records.
            pd.testing.assert_frame_equal(actual.reset_index(drop=True), expected.reset_index(drop=True), check_dtype=False)
        else:
            require((directory / name).read_text() == expected.to_csv(index=False), "CSV reconstruction differs")
    print("Annual raw bytes / exact ISSN matches / study cardinality reconstruction: PASS")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=HERE / "scimago_2025_v1")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        verify(args.output_dir)
        return
    require(args.input is not None, "Supply annual CSV")
    frames, summary, pins, header = assemble(args.input, args.year)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("Complete bounded offline import/matching audit; no writes, API or keys")
        return
    require(not args.output_dir.exists(), "Output version exists; no overwrite")
    stage = Path(tempfile.mkdtemp(prefix=".scimago-import-incomplete-", dir=HERE))
    (stage / "raw").mkdir()
    shutil.copyfile(args.input, stage / "raw/annual.csv")
    require(sha(args.input) == sha(stage / "raw/annual.csv"), "Raw copy differs")
    for name, frame in frames.items():
        if name.endswith(".parquet"):
            frame.to_parquet(stage / name, index=False)
        else:
            frame.to_csv(stage / name, index=False)
    (stage / "report_zh.md").write_text(report(summary), encoding="utf-8")
    pins[str(args.input.resolve())] = sha(args.input)
    outputs = {str(p.relative_to(stage)): {"sha256": sha(p), "bytes": p.stat().st_size}
               for p in stage.rglob("*") if p.is_file()}
    dump_new(stage / "import_manifest.json", {"created_utc": now(), "metric_year": args.year, "provider": "SCImago",
             "year_evidence": f"user-supplied filename/year; header Total Docs. ({args.year})",
             "original_header": header, "input_pins": pins, "outputs": outputs, "summary": summary,
             "importer_sha256": sha(Path(__file__)), "software": {"pandas": pd.__version__},
             "policy": {"match": "checksum-valid exact ISSNs; multiple provider IDs quarantined; no title guessing",
                        "metric": "annual raw SJR + separate category quartiles; no derived percentile or chosen multi-category outcome",
                        "missing": "not zero/Q4; nonjournals and absent source identities separate", "api_calls": 0}})
    verify(stage)
    stage.rename(args.output_dir)
    print("Saved independent annual supplement:", args.output_dir)


if __name__ == "__main__":
    main()
