"""Bounded public DOI evidence acquisition; new archive only, no AF decisions."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from local_recall import MODULE, regular, require, sha, write_csv, write_json, destination
from verify_recall import verify as verify_recall

SKILL = Path('/historical-workspace/.codex/skills/paper-lookup/scripts')
EPMC = 'https://www.ebi.ac.uk/europepmc/webservices/rest'
NCBI = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
MAX_BYTES = 32 * 1024**2
DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"<>]+', re.I)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


# Reuse the skill's tested response parser and its metadata-only JATS refusal.
PAGINATE = load_module('paper_lookup_paginate', SKILL/'paginate.py')
JATS = load_module('paper_lookup_jats', SKILL/'jats_to_text.py')


def norm_doi(value):
    value = str(value or '').strip().lower()
    for prefix in ('https://doi.org/', 'http://doi.org/', 'https://dx.doi.org/', 'doi:'):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value if DOI_RE.fullmatch(value) and len(value) <= 250 else ''


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3'): self.parts.append(' ')
    def handle_endtag(self, tag):
        if tag in ('p', 'div', 'h1', 'h2', 'h3'): self.parts.append(' ')


def plain(value):
    require(isinstance(value, str) and len(value) <= 2_000_000, 'Oversized/invalid text field')
    parser = PlainHTML(); parser.feed(value)
    return ' '.join(''.join(parser.parts).split())


def abstract_check(text, title):
    if not text: return 'missing'
    if len(text) < 80: return 'short_needs_review'
    if text.casefold() == title.casefold(): return 'title_only'
    return 'nonempty_structural_screen_pass_semantics_pending'


def candidate_rows(directory):
    summary = verify_recall(directory)
    with (directory/'candidate_review_private.csv').open(newline='', encoding='utf-8') as f:
        rows = [r for r in csv.DictReader(f) if r['document_eligible'] == 'True']
    require(len(rows) == summary['new_candidates_eligible'] <= 1000, 'Candidate scope differs/cap exceeded')
    for r in rows:
        require(re.fullmatch(r'W\d+', r['work_id']) and not r['af_use_label'] and
                not r['adoption_eligible'], 'Invalid identity or nonblank decisions')
    return sorted(rows, key=lambda r: (r['publication_year'], r['publication_date'], r['work_id']))


class CurlArchive:
    def __init__(self, directory, cap, interval=1.0):
        self.directory = directory; self.cap = cap; self.interval = interval
        self.calls = []; self.last = 0.0

    def get(self, endpoint, params, kind):
        require(len(self.calls) < self.cap, 'Hard HTTP-send cap reached')
        require(endpoint == EPMC+'/search' or endpoint == NCBI or
                re.fullmatch(re.escape(EPMC)+r'/PMC\d+/fullTextXML', endpoint), 'Endpoint not allowlisted')
        time.sleep(max(0, self.interval - (time.monotonic()-self.last)))
        number = len(self.calls)+1
        path = self.directory/f'{number:03d}_{kind}.response'
        record = {'request_number': number, 'endpoint': endpoint, 'params': params,
                  'kind': kind, 'requested_at_utc': datetime.now(timezone.utc).isoformat(),
                  'raw_path': str(path.relative_to(self.directory.parent))}
        self.calls.append(record)
        cmd = ['curl', '--disable', '--silent', '--show-error', '--globoff', '--proto', '=https',
               '--connect-timeout', '15', '--max-time', '60', '--max-filesize', str(MAX_BYTES),
               '--retry', '0', '--max-redirs', '0', '--user-agent', 'AFResearch-public-evidence/1.0',
               '--output', str(path), '--write-out', '%{http_code}', '--get', endpoint]
        for key, value in params.items(): cmd += ['--data-urlencode', f'{key}={value}']
        # No shell, no credentials, no redirects/retries hidden from the call cap.
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=70, check=False)
            record.update(curl_exit=result.returncode, http_status=result.stdout.decode().strip())
        except subprocess.TimeoutExpired:
            record.update(curl_exit=-1, http_status='000')
        self.last = time.monotonic()
        if path.exists():
            path.chmod(0o600)
            record.update(sha256=sha(path), size_bytes=path.stat().st_size)
        write_json(self.directory/f'{number:03d}_request.json', record)
        return record, path


def parse_search(payload, query, requested, cursor):
    page = PAGINATE._europepmc_parse(payload, cursor)
    require(isinstance(page.total, int) and page.total >= 0, 'Missing search total')
    require(isinstance(page.records, list), 'Invalid search record list')
    echoed = (payload.get('request') or {}).get('queryString', '')
    require(echoed == query, 'Server query differs; do not trust partial/mangled query')
    require(all(isinstance(r, dict) and norm_doi(r.get('doi')) in requested for r in page.records),
            'Returned DOI outside exact requested set')
    require(len({(r.get('source'), r.get('id')) for r in page.records}) == len(page.records),
            'Duplicate source/id entries on page')
    return page


def jats_document(raw, expected_doi, pmcid):
    require(len(raw) <= MAX_BYTES, 'XML cap exceeded')
    xml = raw.decode('utf-8')
    # Do not expand internal entities from third-party XML. Ordinary external JATS
    # declarations are ignored by ElementTree, which never resolves external DTDs.
    require('<!ENTITY' not in xml.upper(), 'XML entity declaration rejected')
    article = JATS.find_article(JATS.parse(xml))
    metadata = JATS.extract_metadata(article)
    require(norm_doi(metadata.get('doi')) == expected_doi, 'JATS DOI mismatch/missing')
    actual = str(metadata.get('pmcid') or '')
    require(actual.removeprefix('PMC') == pmcid.removeprefix('PMC'), 'JATS PMCID mismatch/missing')
    body = article.find('body')
    if body is None: return None, 'metadata_only_no_body'
    sections = JATS.collect_sections(body)
    require(sections and any(s['text'].strip() for s in sections), 'Body has no extractable sections')
    return {'full_text_available': True, 'metadata': metadata, 'sections': sections,
            'section_count': len(sections), 'word_count': sum(len(s['text'].split()) for s in sections)}, 'verified_body'


def assemble_evidence(rows, records, complete_dois):
    indexed = {}
    for record in records:
        indexed.setdefault(norm_doi(record.get('doi')), []).append(record)
    results = []
    for source in rows:
        row = dict(source); doi = norm_doi(source['doi']); matches = indexed.get(doi, []) if doi else []
        row.update(lookup_doi=doi, metadata_status='no_valid_doi' if not doi else
                   ('no_exact_match_in_europe_pmc' if doi in complete_dois else 'lookup_incomplete'),
                   epmc_record_count=len(matches), epmc_source='', epmc_id='', pmcid='',
                   public_abstract='', public_abstract_source='', public_abstract_quality='missing',
                   metadata_title='', metadata_year='', metadata_date='', is_open_access='', in_epmc='',
                   fulltext_status='not_advertised_in_this_source', fulltext_source='',
                   fulltext_access_class='', fulltext_license='', fulltext_document_path='',
                   review_status='pending_evidence_review')
        if len(matches) == 1:
            record = matches[0]
            row.update(metadata_status='unique_exact_doi_match_identity_review_pending',
                       epmc_source=record.get('source', ''), epmc_id=record.get('id', ''),
                       pmcid=record.get('pmcid', ''), metadata_title=plain(record.get('title') or ''),
                       metadata_year=record.get('pubYear', ''), metadata_date=record.get('firstPublicationDate', ''),
                       is_open_access=record.get('isOpenAccess', ''), in_epmc=record.get('inEPMC', ''),
                       public_abstract=plain(record.get('abstractText') or ''),
                       public_abstract_source='europe_pmc_rest_core' if record.get('abstractText') else '',
                       fulltext_license=record.get('license') or '')
            row['public_abstract_quality'] = abstract_check(row['public_abstract'], row['metadata_title'])
            if re.fullmatch(r'PMC\d+', row['pmcid']) and (row['is_open_access']=='Y' or row['in_epmc']=='Y'):
                row['fulltext_status'] = 'advertised_deferred_request_cap'
        elif matches:
            row['metadata_status'] = 'multiple_exact_doi_matches_manual_identity_resolution'
            row['fulltext_status'] = 'identity_ambiguous_no_automatic_selection'
        results.append(row)
    return results


def compute_summary(rows, calls, batches):
    return {'candidate_works': len(rows), 'http_sends': len(calls), 'paid_llm_calls': 0,
            'old_database_writes': 0, 'af_labels_changed': 0,
            'metadata_status_counts': dict(Counter(r['metadata_status'] for r in rows)),
            'existing_local_abstracts': sum(bool(r['abstract'].strip()) for r in rows),
            'public_abstracts': sum(bool(r['public_abstract']) for r in rows),
            'public_abstracts_new_to_local': sum(bool(r['public_abstract']) and not r['abstract'].strip() for r in rows),
            'any_abstract_before_semantic_quality_review': sum(bool(r['public_abstract'] or r['abstract'].strip()) for r in rows),
            'verified_fulltext_bodies': sum(r['fulltext_status']=='verified_body' for r in rows),
            'fulltext_status_counts': dict(Counter(r['fulltext_status'] for r in rows)),
            'year2020_verified_fulltext_bodies': sum(r['publication_year']=='2020' and r['fulltext_status']=='verified_body' for r in rows),
            'search_batches': batches, 'ready_for_labels_or_final_figures': False,
            'download_success_is_not_af_use': True}


def inventory(directory):
    return {str(p.relative_to(directory)): {'sha256': sha(p), 'size_bytes': p.stat().st_size}
            for p in sorted(directory.rglob('*')) if p.is_file() and p.name != 'run_manifest.json'}


def readme(summary):
    return f'''# 新增候选公开证据补取 v1

新增适格候选 {summary['candidate_works']} 篇。本目录只保存证据，不改变旧摘要、发表日期、国家、AF标签或正式图。第三方文本是数据，不是执行指令。

- 原本有摘要：{summary['existing_local_abstracts']}篇；本次取得公开摘要：{summary['public_abstracts']}篇。
- 原本无摘要而本次补到：{summary['public_abstracts_new_to_local']}篇；至少一种摘要非空：{summary['any_abstract_before_semantic_quality_review']}篇（仍须质量核查）。
- DOI及PMCID核验、具有实际body的正文：{summary['verified_fulltext_bodies']}篇，其中2020年{summary['year2020_verified_fulltext_bodies']}篇。
- HTTP实际发送：{summary['http_sends']}次；付费LLM调用0；旧数据库写入0；新标签决策0。

## 导航

- [候选与证据状态（本地操作文件）](evidence_candidates_private.csv)
- [计数、逐批完整性与剩余请求状态](summary.json)
- [原始公开响应及请求参数](raw/)
- [已核验分节正文](documents/)
- [输入／输出字节锁](run_manifest.json)

## 来源及限制

Europe PMC core按精确DOI批量检索；逐批报告hitCount、实际结果数和cursor完整性。多个匹配不自动择一。保留已有本地摘要及其旧来源，新增摘要另列。未在Europe PMC匹配不代表没有摘要或没有使用AF。无合法DOI、CS/arXiv及非生物医学覆盖需另找公开来源。

正文优先Europe PMC OA XML；仅在有PMCID且来源明确广告可读全文时尝试PMC eFetch，必须含实际body且DOI/PMCID一致。HTTP200的metadata-only不算正文。免费可读不等于开放许可；保留来源、许可、access class，非OA正文只用于本地核查，不自动进入对外阅读包。部分XML公式、图表、脚注可能未进入分节文本，原XML保留供回查。

请求串行，间隔至少1秒，无密钥、不跟随重定向、无隐藏重试，硬上限50次。达到上限的advertised_deferred_request_cap与真实获取失败分开。摘要非空或正文获取成功都不自动赋yes/no。

检索时间是本轮取证时间；旧OpenAlex下载基准仍为2026年4月3日所在周。本目录不更新旧引用快照，也不自动更改旧发表日期。

使用paper-lookup的Europe PMC解析器及JATS分节/缺body保护；流程软件参考：[Kassis等，Scientific Agent Skills (2026)](https://doi.org/10.48550/arXiv.2609.00065)。
'''


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', type=Path, default=MODULE/'recall_audit_v1')
    p.add_argument('--output-dir', type=Path, default=MODULE/'public_evidence_v1')
    p.add_argument('--max-requests', type=int, default=50)
    p.add_argument('--batch-size', type=int, default=40)
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args(argv)
    require(1 <= a.max_requests <= 50 and 1 <= a.batch_size <= 40, 'Calls 1–50; batch size 1–40')
    rows = candidate_rows(a.input_dir.absolute())
    dois = sorted({norm_doi(r['doi']) for r in rows if norm_doi(r['doi'])})
    batches = [dois[i:i+a.batch_size] for i in range(0, len(dois), a.batch_size)]
    out = destination(a.output_dir)
    print(f'Public evidence scope: {len(rows)} works; valid unique DOIs: {len(dois)}; metadata batches: {len(batches)}')
    print(f'Hard send cap: {a.max_requests}; serial curl; new directory only; no keys/LLM/labels')
    if a.dry_run:
        print('Dry run: frozen recall/source checks complete; no requests or files'); return 0
    stage = Path(tempfile.mkdtemp(prefix='.public-evidence-incomplete-', dir=MODULE)); stage.chmod(0o700)
    for name in ('raw', 'documents'): (stage/name).mkdir(mode=0o700)
    print(f'Staging retained on failure: {stage}', flush=True)
    downloader = CurlArchive(stage/'raw', a.max_requests)
    records = []; complete = set(); reconciliations = []
    try:
        for index, batch in enumerate(batches):
            query = ' OR '.join(f'DOI:"{doi}"' for doi in batch)
            cursor = '*'; found = []; total = None; reason = ''
            while len(downloader.calls) < a.max_requests:
                request, path = downloader.get(EPMC+'/search', {'query': query, 'format':'json',
                    'resultType':'core', 'pageSize':'1000', 'cursorMark':cursor}, 'metadata')
                if request['curl_exit'] != 0 or request['http_status'] != '200':
                    reason = 'transport_or_http_error'; break
                try:
                    payload = json.loads(path.read_text()); page = parse_search(payload, query, set(batch), cursor)
                except (ValueError, RuntimeError, KeyError, TypeError):
                    reason = 'invalid_response_or_query_or_exact_identity'; break
                if total is None: total = page.total
                if total != page.total: reason = 'changing_hit_count'; break
                found.extend(page.records)
                if len(found) >= total or page.next_state is None: break
                cursor = page.next_state
            count_ok = total is not None and len(found)==total and not reason
            if count_ok: complete.update(batch); records.extend(found)
            reconciliations.append({'batch':index+1, 'requested_dois':len(batch), 'expected_records':total,
                                    'retrieved_records':len(found), 'complete':count_ok,
                                    'reason':reason or ('' if count_ok else 'request_cap')})
            print(f'Metadata batches: {index+1}/{len(batches)}; reconciled: {count_ok}; sends: {len(downloader.calls)}', flush=True)
            if len(downloader.calls) >= a.max_requests: break
        write_json(stage/'matched_metadata_private.json', records)
        evidence = assemble_evidence(rows, records, complete)
        for i, row in enumerate(evidence):
            if row['fulltext_status'] != 'advertised_deferred_request_cap': continue
            if len(downloader.calls) >= a.max_requests: break
            pmcid = row['pmcid']; doi = row['lookup_doi']
            oa = row['is_open_access']=='Y'
            endpoint = EPMC+f'/{pmcid}/fullTextXML' if oa else NCBI
            params = {} if oa else {'db':'pmc', 'id':pmcid[3:], 'retmode':'xml', 'tool':'AFResearchEvidence'}
            request, raw = downloader.get(endpoint, params, 'jats')
            row.update(fulltext_source='europe_pmc_fulltext_xml' if oa else 'pmc_efetch_jats',
                       fulltext_access_class='oa_xml_license_as_reported' if oa else 'free_to_read_non_oa_not_redistributable_by_default')
            if request['curl_exit'] != 0 or request['http_status'] != '200':
                row['fulltext_status'] = 'transport_or_http_error'; continue
            try:
                doc, status = jats_document(raw.read_bytes(), doi, pmcid)
                row['fulltext_status'] = status
                if doc:
                    licenses = re.findall(r'<license[^>]*>(.*?)</license>', raw.read_text(), re.S)
                    if licenses: row['fulltext_license'] = plain(' '.join(licenses))
                    name = f'documents/{row["work_id"]}.json'
                    doc.update(work_id=row['work_id'], source=row['fulltext_source'],
                               access_class=row['fulltext_access_class'], license=row['fulltext_license'],
                               raw_response_path=request['raw_path'], raw_sha256=request['sha256'])
                    write_json(stage/name, doc); row['fulltext_document_path'] = name
            except (ValueError, RuntimeError, UnicodeError, JATS.InputError):
                row['fulltext_status'] = 'invalid_xml_or_identity_manual_review'
            if len(downloader.calls)%5==0:
                print(f'Public evidence sends: {len(downloader.calls)}/{a.max_requests}; verified bodies: {sum(r["fulltext_status"]=="verified_body" for r in evidence)}', flush=True)
        summary = compute_summary(evidence, downloader.calls, reconciliations)
        write_csv(stage/'evidence_candidates_private.csv', evidence, list(evidence[0]))
        write_json(stage/'summary.json', summary)
        (stage/'README_zh.md').write_text(readme(summary), encoding='utf-8')
        inputs = [a.input_dir/'run_manifest.json', a.input_dir/'candidate_review_private.csv',
                  Path(__file__), SKILL/'paginate.py', SKILL/'jats_to_text.py', SKILL/'_common.py']
        manifest = {'schema':'af-recall-public-evidence-v1', 'created_at_utc':datetime.now(timezone.utc).isoformat(),
                    'status':'bounded_evidence_acquisition_not_label_approval', 'summary':summary,
                    'hard_http_send_cap':a.max_requests, 'inputs':[{'path':str(p.absolute()), 'sha256':sha(p)} for p in inputs],
                    'outputs':inventory(stage)}
        write_json(stage/'run_manifest.json', manifest)
        stage.rename(out)
        verify(out)
        print(f'Public evidence archive PASS: {out}')
        print(f'Public abstracts: {summary["public_abstracts"]}; new-to-local: {summary["public_abstracts_new_to_local"]}; verified bodies: {summary["verified_fulltext_bodies"]}')
        print('No AF decisions or old database writes; incomplete and deferred evidence kept separate')
        return 0
    except BaseException:
        print(f'INCOMPLETE archive retained: {stage}', flush=True); raise


def verify(directory):
    directory = Path(directory).absolute()
    regular(directory/'run_manifest.json', MODULE)
    manifest = json.loads((directory/'run_manifest.json').read_text())
    require(inventory(directory)==manifest['outputs'], 'Evidence archive bytes/inventory differ')
    for pin in manifest['inputs']:
        path = Path(pin['path']); require(sha(regular(path, path.parent))==pin['sha256'], 'Source changed')
    with (directory/'evidence_candidates_private.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    source = candidate_rows(Path(manifest['inputs'][0]['path']).parent)
    require({r['work_id'] for r in rows}=={r['work_id'] for r in source}, 'Candidate coverage differs')
    source_map = {r['work_id']:r for r in source}
    for row in rows:
        require(all(row[key]==value for key,value in source_map[row['work_id']].items()), 'Old candidate fields changed')
        if row['fulltext_status']=='verified_body':
            path = regular(directory/row['fulltext_document_path'], directory)
            doc = json.loads(path.read_text())
            require(doc['full_text_available'] is True and doc['work_id']==row['work_id'] and
                    norm_doi(doc['metadata']['doi'])==row['lookup_doi'], 'Body identity/state differs')
            raw = regular(directory/doc['raw_response_path'], directory)
            rebuilt, status = jats_document(raw.read_bytes(), row['lookup_doi'], row['pmcid'])
            require(status=='verified_body' and rebuilt['sections']==doc['sections'] and sha(raw)==doc['raw_sha256'], 'Body reconstruction differs')
    calls = [json.loads(p.read_text()) for p in sorted((directory/'raw').glob('*_request.json'))]
    require(len(calls)<=manifest['hard_http_send_cap']<=50, 'Send cap differs')
    summary = compute_summary(rows, calls, manifest['summary']['search_batches'])
    require(summary==manifest['summary'] and summary==json.loads((directory/'summary.json').read_text()), 'Evidence count reconstruction differs')
    return summary


if __name__=='__main__': raise SystemExit(main())
