"""Continue explicitly authorized public-body retrieval into an independent archive."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile

import consolidate_public_evidence as previous
import fetch_public_evidence as e
from local_recall import MODULE, require, regular, sha, write_json, write_csv, destination

SOURCE = MODULE / 'public_evidence_v2'
OUTPUT = MODULE / 'public_evidence_v3'
BODY_FIELDS = {key for key in ('fulltext_status', 'fulltext_source', 'fulltext_access_class',
                               'fulltext_license', 'fulltext_document_path')}


def read_rows(directory):
    csv.field_size_limit(2_000_000)
    with regular(directory/'evidence_candidates_private.csv', MODULE).open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f, strict=True))
    require(len(rows) == 765 and len({r['work_id'] for r in rows}) == 765, 'Frozen scope differs')
    require(all(None not in r and None not in r.values() for r in rows), 'Nonrectangular evidence CSV')
    require(all(not r['af_use_label'] and not r['adoption_eligible'] for r in rows), 'Evidence cannot contain decisions')
    return rows


def plan(rows):
    selected = [r for r in rows if r['fulltext_status'] == 'advertised_deferred_request_cap']
    for row in selected:
        require(re.fullmatch(r'PMC\d+', row['pmcid']) and e.norm_doi(row['doi']) == row['lookup_doi'], 'Invalid planned identity')
        require(row['is_open_access'] == 'Y' or row['in_epmc'] == 'Y', 'No advertised body availability')
    return sorted(selected, key=lambda r: (int(r['publication_year']), r['publication_date'], r['work_id']))


def summary(rows, calls, historical):
    return {'candidate_works': len(rows), 'historical_http_sends': historical,
            'new_http_sends': len(calls), 'cumulative_http_sends': historical+len(calls),
            'paid_llm_calls': 0, 'old_database_writes': 0, 'label_decisions': 0,
            'verified_fulltext_bodies': sum(r['fulltext_status'] == 'verified_body' for r in rows),
            'fulltext_status_counts': dict(Counter(r['fulltext_status'] for r in rows)),
            'by_year': {str(year): {
                'candidate_works': sum(int(r['publication_year']) == year for r in rows),
                'verified_fulltext_bodies': sum(int(r['publication_year']) == year and r['fulltext_status'] == 'verified_body' for r in rows),
                'no_abstract_or_body': sum(int(r['publication_year']) == year and not (r['abstract'].strip() or r['public_abstract'] or r['fulltext_status'] == 'verified_body') for r in rows)
            } for year in sorted({int(r['publication_year']) for r in rows})},
            'semantic_review_complete': False, 'final_figure_ready': False}


def verify(directory):
    directory = Path(directory).absolute()
    m = json.loads(regular(directory/'run_manifest.json', MODULE).read_text())
    require(e.inventory(directory) == m['outputs'], 'Continuation output inventory differs')
    for pin in m['inputs']:
        p = Path(pin['path']); require(sha(regular(p, p.parent)) == pin['sha256'], 'Pinned source changed')
    old_summary = previous.verify(Path(m['source_directory']))
    old = {r['work_id']: r for r in read_rows(Path(m['source_directory']))}
    rows = read_rows(directory)
    planned = {r['work_id'] for r in plan(list(old.values()))}
    calls = [json.loads(p.read_text()) for p in sorted((directory/'new_raw').glob('*_request.json'))]
    require(len(calls) <= m['additional_http_cap'] <= 550, 'Additional cap exceeded')
    require(old_summary['historical_http_sends']+len(calls) <= 600, 'Cumulative cap exceeded')
    require([r['request_number'] for r in calls] == list(range(1, len(calls)+1)), 'Request sequence differs')
    for row in rows:
        prior = old[row['work_id']]
        changed = {key for key in row if row[key] != prior[key]}
        require(changed <= BODY_FIELDS, 'Original metadata/abstract/candidate changed')
        require(not changed or row['work_id'] in planned, 'Unplanned retrieval mutation')
        if row['fulltext_status'] == 'verified_body':
            doc = json.loads(regular(directory/row['fulltext_document_path'], directory).read_text())
            raw = regular(directory/doc['raw_response_path'], directory)
            rebuilt, status = e.jats_document(raw.read_bytes(), row['lookup_doi'], row['pmcid'])
            require(status == 'verified_body' and rebuilt['sections'] == doc['sections'] and sha(raw) == doc['raw_sha256'], 'Body reconstruction differs')
            require(doc['work_id'] == row['work_id'], 'Document work identity differs')
    result = summary(rows, calls, old_summary['historical_http_sends'])
    require(result == m['summary'] == json.loads((directory/'summary.json').read_text()), 'Summary reconstruction differs')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=SOURCE)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    parser.add_argument('--max-requests', type=int, default=550)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    a = parser.parse_args(argv)
    if a.verify_only:
        s = verify(a.output_dir); print(f'Public continuation reconstruction PASS: bodies {s["verified_fulltext_bodies"]}; cumulative sends {s["cumulative_http_sends"]}'); return 0
    require(1 <= a.max_requests <= 550, 'Additional requests 1–550')
    source = a.source_dir.absolute()
    old_summary = previous.verify(source)
    rows = read_rows(source); selected = plan(rows)
    require(old_summary['historical_http_sends'] == 50, 'Unexpected historical request budget')
    out = destination(a.output_dir)
    print(f'Already sent: 50; targeted advertised bodies: {len(selected)}; additional cap: {a.max_requests}')
    print('Serial public requests; no keys, LLM, labels, database writes or automatic sharing')
    if a.dry_run:
        print('Dry run: source bytes/identity/plan checked; no requests or files'); return 0
    stage = Path(tempfile.mkdtemp(prefix='.public-continuation-incomplete-', dir=MODULE)); stage.chmod(0o700)
    for folder in ('raw', 'documents'): shutil.copytree(source/folder, stage/folder)
    (stage/'new_raw').mkdir(mode=0o700)
    shutil.copy2(source/'matched_metadata_private.json', stage/'matched_metadata_private.json')
    print(f'Staging retained on interruption: {stage}', flush=True)
    downloader = e.CurlArchive(stage/'new_raw', a.max_requests, interval=1.0)
    for row in selected:
        if len(downloader.calls) >= a.max_requests: break
        oa = row['is_open_access'] == 'Y'
        endpoint = e.EPMC+f'/{row["pmcid"]}/fullTextXML' if oa else e.NCBI
        params = {} if oa else {'db':'pmc', 'id':row['pmcid'][3:], 'retmode':'xml', 'tool':'AFResearchEvidence'}
        request, raw = downloader.get(endpoint, params, 'jats')
        row.update(fulltext_source='europe_pmc_fulltext_xml' if oa else 'pmc_efetch_jats',
                   fulltext_access_class='oa_xml_license_as_reported' if oa else 'free_to_read_non_oa_not_redistributable_by_default')
        if request['curl_exit'] != 0 or request['http_status'] != '200':
            row['fulltext_status'] = 'transport_or_http_error'
        else:
            try:
                document, status = e.jats_document(raw.read_bytes(), row['lookup_doi'], row['pmcid'])
                row['fulltext_status'] = status
                if document:
                    license_parts = re.findall(r'<license[^>]*>(.*?)</license>', raw.read_text(), re.S)
                    if license_parts: row['fulltext_license'] = e.plain(' '.join(license_parts))
                    name = f'documents/{row["work_id"]}.json'
                    require(not (stage/name).exists(), 'Existing verified document cannot be replaced')
                    document.update(work_id=row['work_id'], source=row['fulltext_source'], access_class=row['fulltext_access_class'],
                                    license=row['fulltext_license'], raw_response_path=request['raw_path'], raw_sha256=request['sha256'])
                    write_json(stage/name, document); row['fulltext_document_path'] = name
            except (ValueError, RuntimeError, UnicodeError, e.JATS.InputError):
                row['fulltext_status'] = 'invalid_xml_or_identity_manual_review'
        # A checkpoint preserves every returned row without publishing a completed archive.
        checkpoint = stage/'checkpoint.json'
        with checkpoint.open('w', encoding='utf-8') as f:
            json.dump({'rows':rows, 'http_sends':len(downloader.calls), 'complete':False}, f, ensure_ascii=False, allow_nan=False)
        checkpoint.chmod(0o600)
        if len(downloader.calls) % 10 == 0:
            print(f'New sends {len(downloader.calls)}/{len(selected)}; bodies {sum(r["fulltext_status"] == "verified_body" for r in rows)}', flush=True)
    s = summary(rows, downloader.calls, 50)
    write_csv(stage/'evidence_candidates_private.csv', rows, list(rows[0]))
    write_json(stage/'summary.json', s)
    (stage/'README_zh.md').write_text(f'''# Figure 1 公开证据续取 v3

累计公开请求{s['cumulative_http_sends']}次（历史50 + 本轮{s['new_http_sends']}）；有核验正文{s['verified_fulltext_bodies']}篇。只请求有精确DOI及PMCID、公开来源已标明全文入口的候选。HTTP200无body不算正文，失败不等于未使用AF。

旧摘要、日期、标签、数据库和旧图均未改变。免费可读不等于允许再分发，正文及原始响应仅保存在本地操作档案，不自动进入对外阅读包。

- [证据操作清单](evidence_candidates_private.csv)
- [数量及逐年状态](summary.json)
- [新请求原始响应](new_raw/)
- [核验正文](documents/)
- [源文件及输出锁](run_manifest.json)

下一步语义审阅及版本关系复核；下载成功不等于确认使用。本档案不更新2026年4月3日所在周的OpenAlex引用快照。
''', encoding='utf-8')
    pins = [source/'run_manifest.json', source/'evidence_candidates_private.csv', Path(__file__), Path(e.__file__)]
    write_json(stage/'run_manifest.json', {'schema':'figure1-public-evidence-continuation-v3',
        'created_at_utc':datetime.now(timezone.utc).isoformat(), 'source_directory':str(source),
        'additional_http_cap':a.max_requests, 'summary':s,
        'inputs':[{'path':str(p.absolute()), 'sha256':sha(p)} for p in pins], 'outputs':e.inventory(stage)})
    verify(stage); stage.rename(out)
    print(f'Continuation export/reconstruction PASS: {out}; cumulative sends {s["cumulative_http_sends"]}; bodies {s["verified_fulltext_bodies"]}')
    return 0


if __name__ == '__main__': raise SystemExit(main())
