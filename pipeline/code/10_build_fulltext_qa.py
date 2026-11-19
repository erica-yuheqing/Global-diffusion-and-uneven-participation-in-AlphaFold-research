#!/usr/bin/env python3
"""Export a read-only review queue for parse errors and zero-context documents.

This tool does not fetch, parse, run models, change the manifest, or assign AF
adoption labels. It writes a new JSONL snapshot plus provenance and a short guide.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "af-fulltext-qa-review-v1"
OUTPUT_NAMES = ("fulltext_qa_review.jsonl", "fulltext_qa_review.meta.json", "README.md")


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def redact(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"(?i)(api[_-]?key|access_token|token|password)=([^\s;&]+)", r"\1=[REDACTED]", text)
    return re.sub(r"(?i)(Bearer\s+)\S+", r"\1[REDACTED]", text)


def file_info(value: Any) -> dict[str, Any]:
    if not value:
        return {"exists": False, "bytes": None}
    try:
        path = Path(value)
        return {"exists": path.is_file(), "bytes": path.stat().st_size if path.is_file() else None}
    except OSError:
        return {"exists": False, "bytes": None}


def error_category(message: str | None) -> str:
    text = message or ""
    if "[NO_BLOCKS]" in text:
        return "no_blocks"
    if "[BAD_INPUT_DATA]" in text:
        match = re.search(r"error code:\s*(\d+)", text)
        return "pdf_conversion_" + (match.group(1) if match else "unknown")
    if any(token in text.lower() for token in ("timeout", "timed out", "connection", "http 503", "http 429")):
        return "network_or_service"
    return "other_parse_error"


def document_metrics(row: dict[str, Any]) -> dict[str, Any]:
    result = {"document_read_status": "not_parsed", "document_read_error": None,
              "document_sha256": None, "document_schema": None, "document_work_id_matches": None,
              "paragraph_count": None, "extracted_characters": None, "document_context_count": None,
              "matched_seed_reference_count": None}
    if row["parse_status"] != "success":
        return result
    if not row.get("parsed_document_path"):
        result["document_read_status"] = "missing"
        return result
    try:
        data = Path(row["parsed_document_path"]).read_bytes()
        result["document_sha256"] = digest(data)
        document = json.loads(data)
        if not isinstance(document, dict):
            raise ValueError("Parsed document must be an object")
        paragraphs = document.get("paragraphs")
        contexts = document.get("evidence_contexts")
        references = document.get("matched_seed_references")
        if not all(isinstance(value, list) for value in (paragraphs, contexts, references)):
            raise ValueError("Expected paragraphs/evidence_contexts/matched_seed_references lists")
        if any(not isinstance(item, dict) or not isinstance(item.get("text"), str) for item in paragraphs):
            raise ValueError("Malformed paragraph records")
        texts = [item["text"].strip() for item in paragraphs if item["text"].strip()]
        result.update(document_read_status="ok", document_schema=document.get("schema_version"),
                      document_work_id_matches=document.get("work_id") == row["work_id"],
                      paragraph_count=len(texts), extracted_characters=sum(map(len, texts)),
                      document_context_count=len(contexts), matched_seed_reference_count=len(references))
    except FileNotFoundError:
        result["document_read_status"] = "missing"
    except (OSError, ValueError, TypeError) as exc:
        result.update(document_read_status="unreadable", document_read_error=redact(f"{type(exc).__name__}: {exc}"))
    return result


def make_record(row: dict[str, Any], short_text_chars: int, observations: dict[str, Any]) -> dict[str, Any]:
    raw = file_info(row.get("local_path"))
    parsed = file_info(row.get("parsed_document_path"))
    metrics = document_metrics(row)
    flags = []
    if not raw["exists"]:
        flags.append("raw_file_missing")
    if row["parse_status"] == "error":
        issue = error_category(row.get("parse_error"))
        priority = "P1"
        action = "核对 PDF 完整性、可读性与转换日志；确认扫描件后才考虑 OCR，不盲目重跑全量。"
    else:
        if metrics["document_read_status"] != "ok":
            flags.append("parsed_output_" + metrics["document_read_status"])
        if metrics["document_work_id_matches"] is False:
            flags.append("document_work_id_mismatch")
        if metrics["document_read_status"] == "ok" and metrics["document_schema"] == "af-fulltext-context-v1":
            flags.append("legacy_schema_v1")
        elif metrics["document_read_status"] == "ok" and metrics["document_schema"] != "af-fulltext-context-v2":
            flags.append("unexpected_document_schema")
        if metrics["document_read_status"] == "ok" and metrics["document_context_count"] != row.get("context_count"):
            flags.append("manifest_document_context_mismatch")
        if any(flag != "legacy_schema_v1" for flag in flags):
            priority, issue = "P0", "artifact_integrity"
            action = "先核对原文件、解析 JSON 与 work_id 的对应关系，解决缺失/格式/计数冲突后再判断正文。"
        elif metrics["extracted_characters"] < short_text_chars:
            priority, issue = "P0", "short_text_no_context"
            action = "优先打开原 PDF 核对：是否撤回/重复发布说明、封面、补充材料，或正文漏提取；保留证据后再处理。"
        elif "legacy_schema_v1" in flags:
            priority, issue = "P1", "legacy_schema"
            action = "旧版 JSON 需升级后才能用于当前模型输入脚本；优先复用已有 TEI，不重下载。旧格式本身不代表正文损坏。"
        else:
            priority, issue = "P2", "no_af_context"
            action = "核对正文与参考文献中的 AlphaFold/AFDB/ColabFold 等表述及引用链接；区分规则漏检与仅背景引用。"
        if metrics["matched_seed_reference_count"]:
            flags.append("seed_reference_without_context")
    observation = observations.get(row["work_id"], {})
    doi = row.get("doi") or ""
    doi_url = doi if doi.startswith("https://doi.org/") else f"https://doi.org/{doi}" if doi else None
    return {
        "review_id": "QA_" + row["work_id"], "work_id": row["work_id"],
        "priority": priority, "issue_category": issue, "flags": flags,
        "title": row.get("title"), "publication_year": row.get("publication_year"),
        "work_type": row.get("work_type"), "doi_url": doi_url,
        "fetched_source": row.get("fetched_source"), "fetched_format": row.get("fetched_format"),
        "fetch_status": row["fetch_status"], "parse_status": row["parse_status"],
        "manifest_context_count": row.get("context_count"), "parse_error": redact(row.get("parse_error")),
        "raw_path": row.get("local_path"), "parsed_document_path": row.get("parsed_document_path"),
        "raw_file_exists": raw["exists"], "raw_file_bytes": raw["bytes"],
        "raw_content_sha256_from_manifest": row.get("content_sha256"),
        "parsed_file_exists": parsed["exists"], **metrics,
        "recommended_action": action,
        "prior_observation": observation.get("observation"),
        "prior_observation_date": observation.get("observed_on"),
        "prior_observation_source": observation.get("source_path"),
        "review_status": "待复核", "quality_decision": "未决", "reviewer": None,
        "reviewed_on": None, "review_notes": None,
    }


def load_rows(db: Path, immutable: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not db.is_file():
        raise ValueError(f"Manifest not found: {db}")
    if immutable and any(Path(str(db) + suffix).exists() for suffix in ("-wal", "-journal")):
        raise ValueError("--immutable requires a stopped/checkpointed manifest without WAL or rollback journal")
    before = (db.stat().st_size, db.stat().st_mtime_ns)
    uri = db.resolve().as_uri() + "?mode=ro" + ("&immutable=1" if immutable else "")
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM works WHERE in_current_corpus=1 AND fetch_status='success' "
            "AND (parse_status='error' OR (parse_status='success' AND COALESCE(context_count,0)=0)) ORDER BY work_id"
        )]
        totals = dict(connection.execute(
            "SELECT COUNT(*) AS corpus_records, SUM(fetch_status='success') AS downloaded_records, "
            "SUM(fetch_status='success' AND parse_status='success') AS parsed_records "
            "FROM works WHERE in_current_corpus=1"
        ).fetchone())
        formats = [dict(row) for row in connection.execute(
            "SELECT fetched_format,parse_status,COUNT(*) AS count FROM works "
            "WHERE in_current_corpus=1 AND fetch_status='success' GROUP BY fetched_format,parse_status"
        )]
        connection.rollback()
    finally:
        connection.close()
    if immutable and (before != (db.stat().st_size, db.stat().st_mtime_ns) or
                      any(Path(str(db) + suffix).exists() for suffix in ("-wal", "-journal"))):
        raise ValueError("Manifest changed during immutable inspection; stop writers and try again")
    return rows, {"totals": totals, "format_counts": formats, "manifest_selection_sha256": digest(encode(rows).encode())}


def build_snapshot(db: Path, *, short_text_chars: int = 1000, immutable: bool = False,
                   observations_path: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if short_text_chars < 1:
        raise ValueError("--short-text-chars must be positive")
    rows, source = load_rows(db, immutable)
    observations = {}
    observation_digest = None
    if observations_path is not None:
        payload = observations_path.read_bytes()
        observations = json.loads(payload)
        if not isinstance(observations, dict) or any(not isinstance(value, dict) for value in observations.values()):
            raise ValueError("Observations must be an object keyed by work_id")
        observation_digest = digest(payload)
    records = [make_record(row, short_text_chars, observations) for row in rows]
    records.sort(key=lambda row: (row["priority"], row["extracted_characters"] if row["extracted_characters"] is not None else -1, row["work_id"]))
    if len({row["work_id"] for row in records}) != len(records):
        raise ValueError("Duplicate work IDs in QA snapshot")
    counts = {
        "review_records": len(records),
        "parse_errors": sum(row["parse_status"] == "error" for row in records),
        "zero_context_records": sum(row["parse_status"] == "success" for row in records),
        "short_text_records": sum(row["issue_category"] == "short_text_no_context" for row in records),
        "legacy_schema_records": sum(row["issue_category"] == "legacy_schema" for row in records),
        "priority_counts": dict(Counter(row["priority"] for row in records)),
        "issue_counts": dict(Counter(row["issue_category"] for row in records)),
        "flag_counts": dict(Counter(flag for row in records for flag in row["flags"])),
    }
    meta = {
        "schema_version": SCHEMA, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(db.resolve()), "immutable_read": immutable,
        "selection": "current corpus, downloaded successfully, parse error OR parse success with no manifest contexts",
        "scope_note": "Only the requested exception groups; not a full quality audit of all parsed papers.",
        "short_text_chars": short_text_chars,
        "character_definition": "Sum of Unicode character lengths of stripped, nonempty paragraph text; not tokens, words or file bytes.",
        "classification_note": "Priority is for technical QA only. No automatic exclusion, AF adoption label, OCR, download or model call.",
        "observations_path": str(observations_path.resolve()) if observations_path else None,
        "observations_sha256": observation_digest, **source, "counts": counts,
        "ordered_work_id_sha256": digest(("\n".join(row["work_id"] for row in records) + "\n").encode()),
    }
    return records, meta


def markdown_report(records: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    counts = meta["counts"]
    lines = ["# 全文解析质量复核清单", "", f"快照：{meta['created_at_utc']}", "",
             f"共 {len(records)} 篇：解析失败 {counts['parse_errors']} 篇；无 AF 片段 {counts['zero_context_records']} 篇，其中短文本 {counts['short_text_records']} 篇。", "",
             "## 复核顺序", "",
             "1. P0：短文本或文件/元数据对应异常。先核对正文身份与完整性，不自动将撤回说明、封面、补充材料当作研究全文。",
             "2. P1：解析失败或旧版 JSON。错误文件先检查 PDF 与转换日志；旧版 JSON 优先复用已有 TEI 升级，不把旧格式等同损坏。",
             "3. P2：有较长文本但未定位 AF 片段。检查关键词变体、参考文献和正文引用链接；无片段不等于未使用 AlphaFold。", "",
             "## 填写与边界", "",
             "- Excel 的 Review 工作表中填写复核状态、质量结论、复核人、日期和备注；其他列来自原始快照。",
             "- JSONL 为机器可读的初始快照，人工填写的 Excel 不会自动同步 JSONL 或回写 SQLite。",
             "- quality_decision 仅表示文件/解析质量，不是 R/E 级别、采用标签或自动纳入/排除决定。",
             "- 已有抽查观察单列保留来源，不自动把记录标为已完成。",
             "- 此清单不包含已有 AF 片段的其他记录，不能据此保证全部正文完整。",
             "- 质量复核完成后再生成新版 Pilot 输入；保留原 Pilot IDs、旧输入及评分键，不在此步骤覆盖它们。", "",
             "## 优先记录", "", "| 优先级 | work_id | 问题 | 段落字符数 | 原文件 |", "|---|---|---|---:|---|"]
    for row in records:
        if row["priority"] not in {"P0", "P1"}:
            continue
        path = row["raw_path"]
        link = f"[打开](<{path}>)" if path and row["raw_file_exists"] else "缺失"
        chars = row["extracted_characters"] if row["extracted_characters"] is not None else "未提取"
        lines.append(f"| {row['priority']} | {row['work_id']} | {row['issue_category']} | {chars} | {link} |")
    lines.extend(["", "来源：" + meta["manifest_path"], "", "完整复核对象见同目录 fulltext_qa_review.jsonl；汇总与校验哈希见 fulltext_qa_review.meta.json。", ""])
    return "\n".join(lines)


def write_snapshot(output_dir: Path, records: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    if any((output_dir / name).exists() for name in OUTPUT_NAMES):
        raise ValueError("QA snapshot already exists; use a new output directory to preserve earlier review work")
    content = "".join(encode(row) + "\n" for row in records)
    meta["jsonl_sha256"] = digest(content.encode())
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in ((OUTPUT_NAMES[0], content), (OUTPUT_NAMES[1], json.dumps(meta, ensure_ascii=False, indent=2) + "\n"),
                       (OUTPUT_NAMES[2], markdown_report(records, meta))):
        with (output_dir / name).open("x", encoding="utf-8") as handle:
            handle.write(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "fulltext/manifest/fulltext_manifest.sqlite")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "fulltext/qa" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--short-text-chars", type=int, default=1000)
    parser.add_argument("--observations", type=Path, help="Optional prior manual observations keyed by work_id, kept separate from decisions")
    parser.add_argument("--expected-record-count", type=int, help="Optional safety check for the selected cohort size")
    parser.add_argument("--immutable", action="store_true", help="Only for a stopped manifest without WAL/journal; never while other pipeline processes write")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    records, meta = build_snapshot(args.db, short_text_chars=args.short_text_chars, immutable=args.immutable, observations_path=args.observations)
    if args.expected_record_count is not None and len(records) != args.expected_record_count:
        raise SystemExit(f"Expected {args.expected_record_count} records, selected {len(records)}; no report written")
    print(json.dumps(meta["counts"], ensure_ascii=False, indent=2))
    if args.dry_run:
        print("Dry run: no files written; no manifest changes, provider requests or model calls.")
        return
    write_snapshot(args.output_dir, records, meta)
    print(f"QA snapshot written to {args.output_dir}")
    print("No manifest changes, provider requests, parsing, OCR or model calls were made.")


if __name__ == "__main__":
    main()
