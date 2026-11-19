"""Bounded exact-identity public supplement. No labels, LLM calls or old writes."""
from collections import Counter
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import quote, urlsplit
from fetch_public_evidence import JATS, MAX_BYTES, norm_doi, plain, inventory, load_module, SKILL
from local_recall import MODULE, destination, require, pin, sha, write_json
from prepare_evidence_closure import OUT as SOURCE, verify

OUT=MODULE/'evidence_closure_public_v4'
CAP=1000

def allowed(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443): return False
    if u.hostname=='api.crossref.org': return u.path.startswith('/works/')
    if u.hostname=='api.biorxiv.org': return u.path.startswith('/details/biorxiv/')
    if u.hostname in ('www.biorxiv.org','www.medrxiv.org'): return u.path.startswith('/content/') and u.path.endswith('/source.xml')
    if u.hostname=='export.arxiv.org': return u.path=='/api/query'
    return False

class Archive:
    def __init__(self): self.calls=[]; self.last=0
    def get(self,url,wid,kind,params=None):
        require(allowed(url),'URL not allowlisted')
        require(len(self.calls)<CAP,'Public cap reached')
        interval=3.1 if urlsplit(url).hostname=='export.arxiv.org' else 1.0
        time.sleep(max(0,interval-(time.monotonic()-self.last)))
        n=len(self.calls)+1; path=OUT/'raw'/f'{n:04d}_{wid}_{kind}.response'
        info={'number':n,'work_id':wid,'kind':kind,'url':url,'params':params or {},
              'time_utc':datetime.now(timezone.utc).isoformat(),'raw_path':str(path), 'status':'dispatching'}
        self.calls.append(info)
        write_json(OUT/'raw'/f'{n:04d}_dispatch.json',info)
        cmd=['curl','--disable','--silent','--show-error','--globoff','--proto','=https','--connect-timeout','10',
             '--max-time','25','--max-filesize',str(MAX_BYTES),'--retry','0','--max-redirs','0',
             '--user-agent','AFResearch-identity-supplement/1.0','--output',str(path),'--write-out','%{http_code}','--get',url]
        for k,v in (params or {}).items(): cmd+=['--data-urlencode',f'{k}={v}']
        try:
            r=subprocess.run(cmd,capture_output=True,timeout=30)
            info.update(status='finished',curl_exit=r.returncode,http_status=r.stdout.decode().strip())
        except subprocess.TimeoutExpired: info.update(status='finished',curl_exit=-1,http_status='000')
        self.last=time.monotonic()
        if path.is_file(): path.chmod(0o600); info.update(sha256=sha(path),size_bytes=path.stat().st_size)
        write_json(OUT/'raw'/f'{n:04d}_finished.json',info)
        return path if info.get('http_status')=='200' and info.get('curl_exit')==0 else None, info

def parse_body(path,doi,wid):
    xml=path.read_text()
    require('<!ENTITY' not in xml.upper(),'XML entity rejected')
    article=JATS.find_article(JATS.parse(xml)); meta=JATS.extract_metadata(article)
    require(norm_doi(meta.get('doi'))==doi,'JATS exact DOI mismatch')
    body=article.find('body')
    if body is None: return None,'metadata_only_no_body'
    sections=JATS.collect_sections(body)
    require(any(s['text'].strip() for s in sections),'Empty body')
    for refs in article.findall('.//back/ref-list'):
        text=JATS.element_text(refs)
        if text: sections.append({'title':'References','text':text,'sec_type':'references'})
    doc={'work_id':wid,'full_text_available':True,'metadata':meta,'sections':sections,
         'raw_source_sha256':sha(path),'raw_source_path':str(path),
         'limitation':'Section text may omit tables, formulas and supplements; exact bibliography retained separately.'}
    return doc,'verified_body'

def title_sim(a,b):
    norm=lambda x:' '.join(re.sub(r'<[^>]+>',' ',x or '').lower().split())
    return difflib.SequenceMatcher(None,norm(a),norm(b),autojunk=False).ratio()

def main():
    verify(SOURCE)
    rows=json.loads((SOURCE/'packets_private.json').read_text())
    initial=json.loads((MODULE/'evidence_closure_lookup_plan_v1/all_priority_targets_private.json').read_text())
    chosen={r['work_id'] for r in rows if not r['body_document_path']}
    chosen.update(r['work_id'] for r in initial)
    targets=[r for r in rows if r['work_id'] in chosen]
    targets.sort(key=lambda r:(any(a['quality']['structural_status']=='usable' for a in r['abstract_variants']),r['publication_year'],r['review_id']))
    destination(OUT).mkdir(mode=0o700); (OUT/'raw').mkdir(mode=0o700); (OUT/'documents').mkdir(mode=0o700); (OUT/'records').mkdir(mode=0o700)
    write_json(OUT/'authorization_and_plan.json',{'sample_count':586,'targets':len(targets),'http_cap':CAP,
       'serial':True,'implicit_retries':0,'implicit_redirects':0,'paid_calls':0,
       'selection':'missing body or priority missing-abstract/early-preprint targets',
       'biorxiv_version':'earliest returned version; dates/links archived, no old publication date replacement',
       'source':pin(SOURCE/'packets_private.json'),'authorization':pin(MODULE/'evidence_closure_execution_authorization_v3.json')})
    archive=Archive(); results=[]
    for i,row in enumerate(targets):
        wid=row['work_id']; doi=norm_doi(row['doi'])
        result={'work_id':wid,'doi':doi,'abstract':None,'body_path':None,'status':'not_sent',
                'semantic_acceptance':False,'metadata_title':None,'title_similarity':None}
        try:
            if not doi: result['status']='no_valid_doi'
            elif doi.startswith('10.1101/'):
                path,req=archive.get('https://api.biorxiv.org/details/biorxiv/'+quote(doi,safe='/')+'/na/json',wid,'metadata')
                result['source']='biorxiv'; result['metadata_request']=req
                if not path: result['status']='transport_or_http_failure'
                else:
                    p=json.loads(path.read_text()); entries=p.get('collection',[])
                    require(isinstance(entries,list) and all(norm_doi(e.get('doi'))==doi for e in entries),'bioRxiv identity mismatch')
                    result['versions']=entries; result['endpoint_exposes_total']=False
                    if not entries: result['status']='no_exact_match_in_biorxiv_not_global_absence'
                    else:
                        e=min(entries,key=lambda e:(int(e.get('version') or 9999),e.get('date') or ''))
                        result.update(metadata_title=plain(e.get('title') or ''),abstract=plain(e.get('abstract') or ''),
                           selected_version=e.get('version'),source_date=e.get('date'),license=e.get('license'),
                           published_version_doi=norm_doi(e.get('published')),status='exact_doi_metadata')
                        result['title_similarity']=title_sim(row['title'],result['metadata_title'])
                        url=e.get('jatsxml') or ''
                        if not row['body_document_path'] and url and allowed(url) and result['title_similarity']>=.8:
                            raw,body_req=archive.get(url,wid,'body'); result['body_request']=body_req
                            if raw:
                                doc,status=parse_body(raw,doi,wid); result['body_status']=status
                                if doc:
                                    dst=OUT/'documents'/f'{wid}.json'; write_json(dst,doc)
                                    result.update(body_path=str(dst),body_sha256=sha(dst),access_class='public_preprint_license_retained')
                            else: result['body_status']='transport_or_http_failure'
            elif doi.startswith('10.48550/arxiv.'):
                aid=doi.split('arxiv.',1)[1]
                require(re.fullmatch(r'\d{4}\.\d{4,5}(?:v\d+)?',aid),'Invalid arXiv ID')
                path,req=archive.get('https://export.arxiv.org/api/query',wid,'atom',{'id_list':aid,'max_results':'1'})
                result.update(source='arxiv',metadata_request=req)
                if path:
                    parsed=subprocess.run([sys.executable,str(SKILL/'arxiv_atom.py'),str(path)],capture_output=True,timeout=10)
                    require(parsed.returncode==0,'arXiv parser refused response')
                    p=json.loads(parsed.stdout); entries=p['entries']; result['parsed_atom']=p
                    if len(entries)==1:
                        e=entries[0]; require(e['arxiv_id']==re.sub(r'v\d+$','',aid),'arXiv ID mismatch')
                        result.update(status='exact_arxiv_metadata_latest_version_separate',abstract=e['abstract'],metadata_title=e['title'],source_date=e['published'])
                        result['title_similarity']=title_sim(row['title'],e['title'])
                    else: result['status']='no_exact_match_in_arxiv'
                else: result['status']='transport_or_http_failure'
            else:
                path,req=archive.get('https://api.crossref.org/works/'+quote(doi,safe=''),wid,'metadata')
                result.update(source='crossref',metadata_request=req)
                if path:
                    p=json.loads(path.read_text()); e=p.get('message')
                    require(p.get('status')=='ok' and isinstance(e,dict) and norm_doi(e.get('DOI'))==doi,'Crossref envelope/DOI mismatch')
                    result.update(status='exact_doi_metadata',abstract=plain(e.get('abstract') or ''),
                        metadata_title=plain(' '.join(e.get('title') or [])),relations=e.get('relation'),
                        source_dates={k:e.get(k) for k in ('published','posted','issued','published-online')},
                        reference_metadata=e.get('reference',[]),fulltext_links=e.get('link',[]),license=e.get('license',[]))
                    result['title_similarity']=title_sim(row['title'],result['metadata_title'])
                    result['body_status']='links_archived_not_body; publisher_access_not_assumed'
                else: result['status']='transport_or_http_failure_or_not_registered_here'
        except (ValueError,KeyError,TypeError,RuntimeError) as e:
            result.update(status='identity_or_parse_failure',error=str(e)[:300])
        results.append(result); write_json(OUT/'records'/f'{wid}.json',result)
        if i%10==0 or i+1==len(targets):
            print(f'Public supplement: {i+1}/{len(targets)}; HTTP sends {len(archive.calls)}; bodies {sum(bool(r["body_path"]) for r in results)}; abstracts {sum(bool(r["abstract"]) for r in results)}',flush=True)
    write_json(OUT/'results_private.json',results)
    summary={'targets':len(targets),'http_sends':len(archive.calls),'paid_calls':0,
       'bodies':sum(bool(r['body_path']) for r in results),'abstracts':sum(bool(r['abstract']) for r in results),
       'statuses':dict(Counter(r['status'] for r in results)),'af_labels_changed':0,'old_database_changed':False}
    write_json(OUT/'summary.json',summary)
    write_json(OUT/'run_manifest.json',{'schema':'figure1-closure-public-supplement-v4','inputs':[pin(SOURCE/'packets_private.json'),pin(Path(__file__))],
       'summary':summary,'outputs':inventory(OUT)})
    print('Public supplement finished:',summary,flush=True)

if __name__=='__main__': main()
