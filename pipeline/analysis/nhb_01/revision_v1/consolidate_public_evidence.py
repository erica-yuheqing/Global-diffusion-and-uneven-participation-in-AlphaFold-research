"""Offline exact-DOI recovery from already archived complete API pages; no requests."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile

import fetch_public_evidence as e


def metadata_recovery(source):
    records=[]; complete=set(); unresolved=set(); batches=[]
    for p in sorted((source/'raw').glob('*_request.json')):
        request=json.loads(p.read_text())
        if request['kind']!='metadata':continue
        query=request['params']['query']
        wanted={e.norm_doi(d) for d in re.findall(r'DOI:"([^"]+)"',query)}
        raw=source/request['raw_path']
        if request['curl_exit']!=0 or request['http_status']!='200':continue
        payload=json.loads(raw.read_text())
        page=e.PAGINATE._europepmc_parse(payload,request['params']['cursorMark'])
        e.require(payload.get('request',{}).get('queryString')==query,'Query echo differs')
        # Current first batch has one complete page per request. Reject unexpected
        # pagination rather than silently publishing a partial hit list.
        e.require(page.total==len(page.records) and len(page.records)<=1000,'Page is incomplete')
        e.require(len({(r.get('source'),r.get('id')) for r in page.records})==len(page.records),'Duplicate identities')
        accepted=[r for r in page.records if e.norm_doi(r.get('doi')) in wanted]
        unlinked=[r for r in page.records if not e.norm_doi(r.get('doi')) or e.norm_doi(r.get('doi')) not in wanted]
        if unlinked:unresolved.update(wanted)
        records.extend(accepted); complete.update(wanted)
        batches.append({'request_number':request['request_number'],'requested_dois':len(wanted),
                        'expected_records':page.total,'retrieved_records':len(page.records),
                        'exact_doi_records_retained':len(accepted),'unidentifiable_or_other_doi_records':len(unlinked),
                        'transport_count_reconciliation_complete':True,'identity_complete':not unlinked})
    return records,complete,unresolved,batches


def reconstruct(source):
    e.verify(source)
    pins=json.loads((source/'run_manifest.json').read_text())['inputs']
    rows=e.candidate_rows(Path(pins[0]['path']).parent)
    records,complete,unresolved,batches=metadata_recovery(source)
    new=e.assemble_evidence(rows,records,complete)
    with (source/'evidence_candidates_private.csv').open(newline='',encoding='utf-8') as f:
        old={r['work_id']:r for r in csv.DictReader(f)}
    for row in new:
        prior=old[row['work_id']]
        if row['metadata_status']=='no_exact_match_in_europe_pmc' and row['lookup_doi'] in unresolved:
            row['metadata_status']='no_exact_match_unidentifiable_hit_in_batch_manual_lookup'
        if prior['metadata_status']=='unique_exact_doi_match_identity_review_pending':
            e.require(row['epmc_source']==prior['epmc_source'] and row['epmc_id']==prior['epmc_id'], 'Metadata selection changed')
            for key in row:
                if key.startswith('fulltext_'):row[key]=prior[key]
    calls=[json.loads(p.read_text()) for p in sorted((source/'raw').glob('*_request.json'))]
    summary=e.compute_summary(new,calls,batches)
    summary.update(new_http_sends=0, historical_http_sends=len(calls),
                   retained_unidentifiable_source_rows=sum(b['unidentifiable_or_other_doi_records'] for b in batches),
                   lookup_incomplete_works_reprocessed=sum(r['metadata_status']=='lookup_incomplete' for r in old.values())-
                       sum(r['metadata_status']=='lookup_incomplete' for r in new))
    summary['by_year']={year:{
        'candidate_works':sum(r['publication_year']==year for r in new),
        'existing_local_abstracts':sum(r['publication_year']==year and bool(r['abstract'].strip()) for r in new),
        'public_abstracts':sum(r['publication_year']==year and bool(r['public_abstract']) for r in new),
        'public_abstracts_new_to_local':sum(r['publication_year']==year and bool(r['public_abstract']) and not r['abstract'].strip() for r in new),
        'verified_fulltext_bodies':sum(r['publication_year']==year and r['fulltext_status']=='verified_body' for r in new),
        'no_nonempty_abstract_or_body':sum(r['publication_year']==year and not(r['public_abstract'] or r['abstract'].strip() or r['fulltext_status']=='verified_body') for r in new)
        } for year in sorted({r['publication_year'] for r in new})}
    summary['no_nonempty_abstract_or_body']=sum(v['no_nonempty_abstract_or_body'] for v in summary['by_year'].values())
    return new,records,summary


def verify(directory):
    directory=Path(directory).absolute()
    m=json.loads(e.regular(directory/'run_manifest.json',e.MODULE).read_text())
    e.require(e.inventory(directory)==m['outputs'],'Consolidated inventory differs')
    for pin in m['inputs']:
        p=Path(pin['path']);e.require(e.sha(e.regular(p,p.parent))==pin['sha256'],'Consolidation source changed')
    rows,records,summary=reconstruct(Path(m['source_directory']))
    with (directory/'evidence_candidates_private.csv').open(newline='',encoding='utf-8') as f:actual=list(csv.DictReader(f))
    e.require(actual==[{k:str(v) for k,v in r.items()} for r in rows],'Consolidated reconstruction differs')
    e.require(json.loads((directory/'matched_metadata_private.json').read_text())==records,'Metadata exact recovery differs')
    e.require(summary==m['summary'] and summary==json.loads((directory/'summary.json').read_text()),'Consolidated summary differs')
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir',type=Path,default=e.MODULE/'public_evidence_v1')
    p.add_argument('--output-dir',type=Path,default=e.MODULE/'public_evidence_v2')
    p.add_argument('--verify-only',action='store_true')
    a=p.parse_args()
    if a.verify_only:
        s=verify(a.output_dir);print(f'Offline evidence consolidation PASS: {s["candidate_works"]} works; public abstracts {s["public_abstracts"]}; bodies {s["verified_fulltext_bodies"]}');return 0
    rows,records,s=reconstruct(a.source_dir)
    out=e.destination(a.output_dir)
    stage=Path(tempfile.mkdtemp(prefix='.evidence-consolidation-incomplete-',dir=e.MODULE))
    stage.chmod(0o700)
    for folder in ('raw','documents'):shutil.copytree(a.source_dir/folder,stage/folder)
    e.write_csv(stage/'evidence_candidates_private.csv',rows,list(rows[0]))
    e.write_json(stage/'matched_metadata_private.json',records)
    e.write_json(stage/'summary.json',s)
    years='\n'.join(f'| {year} | {v["candidate_works"]} | {v["existing_local_abstracts"]} | {v["public_abstracts_new_to_local"]} | {v["verified_fulltext_bodies"]} | {v["no_nonempty_abstract_or_body"]} |' for year,v in s['by_year'].items())
    text=e.readme(s)+f'''\n## 离线恢复 v2

两个批次各有1条未返回DOI的来源记录。v1保守隔离了整个批次；v2重新核对完整响应，保留其中精确DOI匹配，不按标题猜测那2条的归属。没有增加请求，也没有修改v1。含不明记录的批次内无匹配候选标记为需定向核对，而非确定无摘要。

## 逐年证据覆盖

| 年份 | 新候选 | 原本摘要非空 | 新补到摘要 | 已核验正文 | 仍无非空摘要或已核验正文 |
| --- | ---: | ---: | ---: | ---: | ---: |
{years}

两种摘要重叠，不能直接相加。正文列仅为本轮有DOI及PMCID匹配的body，不包含尚未请求的广告全文。无证据候选{ s['no_nonempty_abstract_or_body'] }篇仍须保留待补，不应自动判no。

按照用户选择，公开访问停止在累计50次；后续仅离线恢复与验证。下一步先核对本目录状态，再决定是否扩展公开正文请求，或开始已有证据候选的审阅；任何付费LLM调用都须另行确认。
'''
    (stage/'README_zh.md').write_text(text,encoding='utf-8')
    inputs=[a.source_dir/'run_manifest.json',Path(__file__),Path(e.__file__)]
    e.write_json(stage/'run_manifest.json',{'schema':'af-public-evidence-consolidated-v2',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_directory':str(a.source_dir.absolute()),
        'summary':s,'inputs':[{'path':str(p.absolute()),'sha256':e.sha(p)} for p in inputs],
        'outputs':e.inventory(stage)})
    stage.rename(out);verify(out)
    print(f'Offline exact-DOI recovery PASS: {out}')
    print(f'Public abstracts {s["public_abstracts"]}; new-to-local {s["public_abstracts_new_to_local"]}; bodies {s["verified_fulltext_bodies"]}; new requests 0')
    return 0

if __name__=='__main__':raise SystemExit(main())
