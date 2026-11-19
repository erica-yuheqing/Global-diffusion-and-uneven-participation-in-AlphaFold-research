#!/usr/bin/env python3
"""Parse JATS/TEI full text and extract auditable AlphaFold evidence windows.

PDFs are converted to TEI through a user-supplied GROBID service. The script does
not silently fall back to plain PDF text for citation-only records because that
would lose the bibliography-to-inline-citation links needed for validation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests
from lxml import etree
from tqdm import tqdm

from fulltext_pipeline.common import (
    DEFAULT_DB_PATH,
    DEFAULT_FULLTEXT_ROOT,
    PROJECT_ROOT,
    canonical_text,
    connect_db,
    json_dumps,
    make_user_agent,
    normalize_doi,
    raise_for_status_redacted,
    redact_sensitive_text,
    safe_work_id,
    utc_now,
)


XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s<>\"']+", re.I)
BRACKETED_CITATION_RE = re.compile(r"\[([^\]]{1,100})\]")
DEFAULT_SEED_FILE = PROJECT_ROOT / "config" / "alphafold_seed_works.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--root", type=Path, default=DEFAULT_FULLTEXT_ROOT)
    parser.add_argument("--seed-file", type=Path, default=DEFAULT_SEED_FILE)
    limit_group = parser.add_mutually_exclusive_group()
    limit_group.add_argument("--limit", type=int, default=20, help="Default safety limit: 20")
    limit_group.add_argument("--all", action="store_true")
    limit_group.add_argument(
        "--work-id",
        help="Parse one exact OpenAlex work ID (use with --force to replace a success)",
    )
    retry_group = parser.add_mutually_exclusive_group()
    retry_group.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry parse errors and PDFs previously deferred for GROBID",
    )
    retry_group.add_argument(
        "--force",
        action="store_true",
        help="Re-parse every selected row; PDFs are sent to GROBID again",
    )
    retry_group.add_argument(
        "--reindex-contexts",
        action="store_true",
        help=(
            "Rebuild successful context records with the current match rules; "
            "PDFs reuse cached GROBID TEI and never call GROBID"
        ),
    )
    parser.add_argument("--priority-max", type=int, default=100)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--grobid-url",
        default=os.getenv("GROBID_URL"),
        help="For example http://localhost:8070; defaults to GROBID_URL",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("CONTACT_EMAIL") or os.getenv("UNPAYWALL_EMAIL"),
    )
    parser.add_argument(
        "--combined-jsonl",
        type=Path,
        help="Optionally export all successfully parsed documents to one JSONL file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the selected rows and cached-TEI readiness without writing files",
    )
    return parser.parse_args()


def normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.lower().split())


def clean_doi_candidate(value: str) -> str | None:
    return normalize_doi(value.rstrip(".,;:)]}"))


def load_seed_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not config.get("seeds"):
        raise ValueError(f"No seeds configured in {path}")
    config["compiled_mentions"] = [
        re.compile(pattern, re.I) for pattern in config.get("mention_patterns", [])
    ]
    for seed in config["seeds"]:
        seed["normalized_dois"] = {
            doi for value in seed.get("dois", []) if (doi := normalize_doi(value))
        }
        seed["normalized_titles"] = [
            normalize_match_text(value) for value in seed.get("title_patterns", [])
        ]
    return config


def element_text(element: etree._Element | None) -> str:
    if element is None:
        return ""
    return canonical_text(" ".join(element.itertext()))


def element_id(element: etree._Element) -> str | None:
    return element.get("id") or element.get(XML_ID)


def section_title(element: etree._Element) -> str:
    for ancestor in [element, *element.iterancestors()]:
        local = etree.QName(ancestor).localname.lower()
        if local == "abstract":
            return "Abstract"
        if local in {"fig", "figure"}:
            return "Figure caption"
        if local not in {"sec", "div"}:
            continue
        for child in ancestor:
            child_local = etree.QName(child).localname.lower()
            if child_local in {"title", "head"}:
                title = element_text(child)
                if title:
                    return title
    return "Unlabeled section"


def seed_matches(reference_text: str, seed_config: dict[str, Any]) -> list[str]:
    normalized_text = normalize_match_text(reference_text)
    found_dois = {
        doi for match in DOI_RE.findall(reference_text) if (doi := clean_doi_candidate(match))
    }
    matches: list[str] = []
    for seed in seed_config["seeds"]:
        doi_match = bool(found_dois & seed["normalized_dois"])
        title_match = any(title and title in normalized_text for title in seed["normalized_titles"])
        if doi_match or title_match:
            matches.append(seed["seed_id"])
    return matches


def bibliography_nodes(tree: etree._ElementTree) -> list[etree._Element]:
    nodes = tree.xpath(
        "//*[local-name()='ref-list']/*[local-name()='ref']"
        " | //*[local-name()='listBibl']/*[local-name()='biblStruct' or local-name()='bibl']"
    )
    return [node for node in nodes if isinstance(node, etree._Element)]


def matched_bibliography(
    tree: etree._ElementTree, seed_config: dict[str, Any]
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    matched_ids: dict[str, list[str]] = {}
    records: list[dict[str, Any]] = []
    for node in bibliography_nodes(tree):
        reference_id = element_id(node)
        reference_text = element_text(node)
        matches = seed_matches(reference_text, seed_config)
        if reference_id and matches:
            normalized_id = reference_id.lstrip("#")
            citation_labels = {
                value
                for label in node.xpath("./*[local-name()='label']")
                for value in re.findall(r"\d+", element_text(label))
            }
            grobid_index = re.fullmatch(r"b(\d+)", normalized_id, re.I)
            if not citation_labels and grobid_index:
                citation_labels.add(str(int(grobid_index.group(1)) + 1))
            matched_ids[normalized_id] = matches
            records.append(
                {
                    "reference_id": normalized_id,
                    "citation_labels": sorted(citation_labels, key=int),
                    "seed_ids": matches,
                    "reference_text": reference_text,
                }
            )
    return matched_ids, records


def inline_reference_ids(paragraph: etree._Element) -> set[str]:
    ids: set[str] = set()
    for node in paragraph.xpath(".//*[local-name()='xref' or local-name()='ref']"):
        local = etree.QName(node).localname.lower()
        ref_type = (node.get("ref-type") or node.get("type") or "").lower()
        if local == "xref" and ref_type != "bibr":
            continue
        if local == "ref" and ref_type not in {"bibr", "bib", "citation"}:
            continue
        target = node.get("rid") or node.get("target") or ""
        for value in re.split(r"[\s,;]+", target):
            value = value.strip().lstrip("#")
            if value:
                ids.add(value)
    return ids


def paragraph_nodes(tree: etree._ElementTree) -> list[etree._Element]:
    nodes = tree.xpath(
        "//*[local-name()='abstract']//*[local-name()='p']"
        " | //*[local-name()='body']//*[local-name()='p']"
        " | //*[local-name()='fig']//*[local-name()='caption']"
        "[not(.//*[local-name()='p'])]"
        " | //*[local-name()='figure']/*[local-name()='figDesc']"
        " | //*[local-name()='tr' or local-name()='row']"
        "[not(.//*[local-name()='p'])]"
        " | //*[local-name()='list-item' or local-name()='item']"
        "[not(.//*[local-name()='p'])]"
    )
    if not tree.xpath("//*[local-name()='body']//*[local-name()='p']"):
        nodes = tree.xpath(
            "//*[local-name()='abstract']//*[local-name()='p']"
            " | //*[local-name()='text']//*[local-name()='p']"
            " | //*[local-name()='figure']/*[local-name()='figDesc']"
            " | //*[local-name()='row'][not(.//*[local-name()='p'])]"
            " | //*[local-name()='item'][not(.//*[local-name()='p'])]"
        )
    unique_nodes: list[etree._Element] = []
    seen: set[int] = set()
    for node in nodes:
        if isinstance(node, etree._Element) and id(node) not in seen:
            seen.add(id(node))
            unique_nodes.append(node)
    return unique_nodes


def block_type(element: etree._Element) -> str:
    local = etree.QName(element).localname.lower()
    if local in {"caption", "figdesc"}:
        return "figure_caption"
    if local in {"tr", "row"}:
        return "table_row"
    if local in {"list-item", "item"}:
        return "list_item"
    return "paragraph"


def parse_structured_xml(
    xml_path: Path,
    *,
    work_id: str,
    source: str,
    document_title: str | None,
    seed_config: dict[str, Any],
) -> dict[str, Any]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=True)
    tree = etree.parse(str(xml_path), parser)
    matched_ids, matched_references = matched_bibliography(tree, seed_config)
    paragraphs = paragraph_nodes(tree)
    paragraph_records: list[dict[str, Any]] = []
    triggers_by_index: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    if document_title and canonical_text(document_title):
        title_text = canonical_text(document_title)
        paragraph_records.append(
            {
                "index": 0,
                "section": "Title",
                "block_type": "title",
                "text": title_text,
            }
        )
        for pattern in seed_config["compiled_mentions"]:
            for match in pattern.finditer(title_text):
                triggers_by_index[0]["direct_mention"].add(match.group(0))

    label_to_seeds: dict[str, set[str]] = defaultdict(set)
    for reference in matched_references:
        for label in reference.get("citation_labels", []):
            label_to_seeds[label].update(reference["seed_ids"])

    for paragraph in paragraphs:
        text = element_text(paragraph)
        if not text:
            continue
        index = len(paragraph_records)
        paragraph_records.append(
            {
                "index": index,
                "section": section_title(paragraph),
                "block_type": block_type(paragraph),
                "text": text,
            }
        )
        for pattern in seed_config["compiled_mentions"]:
            for match in pattern.finditer(text):
                triggers_by_index[index]["direct_mention"].add(match.group(0))
        cited_ids = inline_reference_ids(paragraph)
        matched_cited_ids = cited_ids & set(matched_ids)
        for cited_id in sorted(matched_cited_ids):
            triggers_by_index[index]["seed_citation"].update(matched_ids[cited_id])
        if not matched_cited_ids and label_to_seeds:
            bracketed_numbers = {
                number
                for bracket in BRACKETED_CITATION_RE.findall(text)
                for number in re.findall(r"\d+", bracket)
            }
            for label in sorted(bracketed_numbers & set(label_to_seeds), key=int):
                triggers_by_index[index]["seed_citation_numeric_fallback"].update(
                    label_to_seeds[label]
                )

    by_index = {record["index"]: record for record in paragraph_records}
    contexts: list[dict[str, Any]] = []
    for index in sorted(triggers_by_index):
        record = by_index.get(index)
        if not record:
            continue
        previous = by_index.get(index - 1)
        following = by_index.get(index + 1)
        triggers = {
            trigger_type: sorted(values)
            for trigger_type, values in triggers_by_index[index].items()
        }
        contexts.append(
            {
                "paragraph_index": index,
                "section": record["section"],
                "block_type": record["block_type"],
                "trigger_types": sorted(triggers),
                "matched_values": triggers,
                "previous_text": previous["text"] if previous else None,
                "evidence_text": record["text"],
                "next_text": following["text"] if following else None,
            }
        )

    return {
        "schema_version": "af-fulltext-context-v2",
        "work_id": safe_work_id(work_id),
        "source": source,
        "raw_path": str(xml_path.resolve()),
        "parsed_at": utc_now(),
        "matched_seed_references": matched_references,
        "paragraphs": paragraph_records,
        "evidence_contexts": contexts,
        "quality": {
            "paragraph_count": len(paragraph_records),
            "matched_seed_reference_count": len(matched_references),
            "evidence_context_count": len(contexts),
            "has_direct_mention": any(
                "direct_mention" in item["trigger_types"] for item in contexts
            ),
            "has_seed_citation_context": any(
                bool(
                    {"seed_citation", "seed_citation_numeric_fallback"}
                    & set(item["trigger_types"])
                )
                for item in contexts
            ),
        },
    }


def parsed_xml_path(root: Path, work_id: str) -> Path:
    short_id = safe_work_id(work_id)
    digits = short_id[1:]
    return root / "parsed" / "grobid" / f"W{digits[:2]}" / (digits[2:4] or "00") / f"{short_id}.tei.xml"


def document_output_path(root: Path, work_id: str) -> Path:
    short_id = safe_work_id(work_id)
    digits = short_id[1:]
    return root / "extracted" / f"W{digits[:2]}" / (digits[2:4] or "00") / f"{short_id}.json"


def grobid_pdf(
    pdf_path: Path,
    *,
    work_id: str,
    root: Path,
    grobid_url: str,
    contact_email: str | None,
    force: bool,
) -> Path:
    output = parsed_xml_path(root, work_id)
    if not force and output.exists() and output.stat().st_size > 0:
        return output
    endpoint = grobid_url.rstrip("/") + "/api/processFulltextDocument"
    session = requests.Session()
    session.headers["User-Agent"] = make_user_agent(contact_email)
    with pdf_path.open("rb") as handle:
        response = session.post(
            endpoint,
            files={"input": (pdf_path.name, handle, "application/pdf")},
            data={
                "consolidateHeader": "0",
                "consolidateCitations": "0",
                "includeRawCitations": "1",
                "includeRawAffiliations": "0",
            },
            timeout=(30.0, 600.0),
        )
    raise_for_status_redacted(response, "GROBID")
    payload = response.content
    response.close()
    if b"<TEI" not in payload[:2000] and b":TEI" not in payload[:2000]:
        raise ValueError("GROBID response does not appear to be TEI XML")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    temporary.write_bytes(payload)
    temporary.replace(output)
    return output


def extract_one(
    row: dict[str, Any],
    *,
    root: Path,
    grobid_url: str | None,
    contact_email: str | None,
    seed_config: dict[str, Any],
    force: bool,
    reindex_contexts: bool = False,
) -> dict[str, Any]:
    work_id = row["work_id"]
    raw_path = Path(row["local_path"])
    try:
        if not raw_path.exists():
            raise FileNotFoundError(raw_path)
        source = row["fetched_source"] or "unknown"
        if row["fetched_format"] == "pdf":
            if reindex_contexts:
                xml_path = parsed_xml_path(root, work_id)
                if not xml_path.exists() or xml_path.stat().st_size == 0:
                    raise FileNotFoundError(
                        f"cached GROBID TEI missing for local context reindex: {xml_path}"
                    )
            elif not grobid_url:
                return {
                    "work_id": work_id,
                    "status": "needs_grobid",
                    "error": "PDF requires --grobid-url or GROBID_URL",
                }
            else:
                xml_path = grobid_pdf(
                    raw_path,
                    work_id=work_id,
                    root=root,
                    grobid_url=grobid_url,
                    contact_email=contact_email,
                    force=force,
                )
            source = f"{source}+grobid"
        else:
            xml_path = raw_path
        document = parse_structured_xml(
            xml_path,
            work_id=work_id,
            source=source,
            document_title=row.get("title"),
            seed_config=seed_config,
        )
        output = document_output_path(root, work_id)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".part")
        temporary.write_text(json_dumps(document) + "\n", encoding="utf-8")
        temporary.replace(output)
        return {
            "work_id": work_id,
            "status": "success",
            "parsed_at": document["parsed_at"],
            "parsed_document_path": str(output.resolve()),
            "context_path": str(output.resolve()),
            "context_count": len(document["evidence_contexts"]),
        }
    except (OSError, ValueError, etree.XMLSyntaxError, requests.RequestException) as exc:
        return {
            "work_id": work_id,
            "status": "error",
            "error": redact_sensitive_text(exc),
        }


def select_rows(
    connection: sqlite3.Connection,
    limit: int | None,
    work_id: str | None,
    force: bool,
    retry_failed: bool,
    priority_max: int,
    reindex_contexts: bool = False,
) -> list[dict[str, Any]]:
    clauses = [
        "in_current_corpus=1",
        "fetch_status='success'",
        "local_path IS NOT NULL",
        "priority <= ?",
    ]
    params: list[Any] = [priority_max]
    if work_id:
        clauses.append("work_id = ?")
        params.append(work_id)
    if reindex_contexts:
        clauses.append("parse_status = 'success'")
    elif force:
        pass
    elif retry_failed:
        clauses.append("parse_status <> 'success'")
    else:
        clauses.append("parse_status = 'pending'")
    sql = "SELECT * FROM works WHERE " + " AND ".join(clauses) + " ORDER BY priority, work_id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def print_dry_run(rows: list[dict[str, Any]], root: Path, reindex_contexts: bool) -> None:
    formats = Counter((row.get("fetched_format") or "unknown") for row in rows)
    print(f"Eligible rows: {len(rows):,}")
    print(f"Fetched formats: {dict(formats)}")
    print(f"Local context reindex: {reindex_contexts}")
    if reindex_contexts:
        pdf_rows = [row for row in rows if row.get("fetched_format") == "pdf"]
        cached = sum(
            1
            for row in pdf_rows
            if (path := parsed_xml_path(root, row["work_id"])).exists()
            and path.stat().st_size > 0
        )
        print(f"PDF rows with cached GROBID TEI: {cached:,}/{len(pdf_rows):,}")
        print("GROBID requests: 0")
    print("Dry run: no context files or manifest rows were changed")


def record_parse_result(connection: sqlite3.Connection, result: dict[str, Any]) -> None:
    connection.execute(
        """
        UPDATE works SET
            parse_status=?, parsed_at=?, parsed_document_path=?, context_path=?,
            context_count=?, parse_error=?, updated_at=?
        WHERE work_id=?
        """,
        (
            result["status"],
            result.get("parsed_at"),
            result.get("parsed_document_path"),
            result.get("context_path"),
            result.get("context_count"),
            result.get("error"),
            utc_now(),
            result["work_id"],
        ),
    )


def export_combined_jsonl(
    connection: sqlite3.Connection,
    output: Path,
    priority_max: int,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = connection.execute(
        """
        SELECT parsed_document_path FROM works
        WHERE in_current_corpus=1
          AND parse_status='success' AND parsed_document_path IS NOT NULL
          AND priority <= ?
        ORDER BY priority, work_id
        """,
        (priority_max,),
    ).fetchall()
    temporary = output.with_suffix(output.suffix + ".part")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            document_path = Path(row["parsed_document_path"])
            if document_path.exists():
                handle.write(document_path.read_text(encoding="utf-8").strip() + "\n")
    temporary.replace(output)
    print(f"Combined JSONL written to {output}")


def main() -> None:
    args = parse_args()
    limit = None if args.all or args.work_id else args.limit
    seed_config = load_seed_config(args.seed_file)
    connection = connect_db(args.db)
    try:
        rows = select_rows(
            connection,
            limit,
            args.work_id,
            args.force,
            args.retry_failed,
            args.priority_max,
            args.reindex_contexts,
        )
        if args.dry_run:
            print_dry_run(rows, args.root, args.reindex_contexts)
            return
        worker = lambda row: extract_one(  # noqa: E731
            row,
            root=args.root,
            grobid_url=args.grobid_url,
            contact_email=args.email,
            seed_config=seed_config,
            force=args.force,
            reindex_contexts=args.reindex_contexts,
        )
        successes = 0
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            results = executor.map(worker, rows)
            for result in tqdm(results, total=len(rows), desc="Context extraction", unit="work"):
                record_parse_result(connection, result)
                connection.commit()
                successes += int(result["status"] == "success")
        print(f"Parsed successfully: {successes:,}/{len(rows):,}")
        if args.combined_jsonl:
            export_combined_jsonl(connection, args.combined_jsonl, args.priority_max)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
