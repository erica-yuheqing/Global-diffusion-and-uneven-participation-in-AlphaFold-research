"""Follow archived bioRxiv JATS links, separate from metadata v4; no bypass."""
from collections import Counter
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
import fetch_closure_public_v4 as base
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, require, pin, sha, write_json

OUT=MODULE/'evidence_closure_public_bodies_v5'
META=MODULE/'evidence_closure_public_v4'

def allow_body(url):
    u=urlsplit(url)
    return (u.scheme=='https' and u.hostname in ('www.biorxiv.org','www.medrxiv.org') and
       not u.username and not u.password and u.port in (None,443) and
       u.path.startswith('/content/') and u.path.endswith(('/source.xml','.source.xml')))

def main():
    while not (META/'run_manifest.json').is_file(): time.sleep(20)
    m=json.loads((META/'run_manifest.json').read_text()); require(inventory(META)==m['outputs'],'Metadata source changed')
    records=json.loads((META/'results_private.json').read_text())
    targets=[r for r in records if r.get('source')=='biorxiv' and r.get('status')=='exact_doi_metadata' and (r.get('title_similarity') or 0)>=.8]
    destination(OUT).mkdir(mode=0o700); (OUT/'raw').mkdir(mode=0o700); (OUT/'documents').mkdir(mode=0o700)
    # Reuse identical bounded curl transport; only the prevalidated .source.xml
    # spelling and versioned output location differ. No redirection bypass.
    base.allowed=allow_body; base.OUT=OUT
    archive=base.Archive(); results=[]; consecutive_denied=0
    for r in targets:
        chosen=next(e for e in r['versions'] if e.get('version')==r['selected_version'])
        url=chosen.get('jatsxml') or ''
        result={'work_id':r['work_id'],'doi':r['doi'],'selected_version':r['selected_version'],
           'source_date':r['source_date'],'license':r.get('license'),'metadata_title':r['metadata_title'],
           'title_similarity':r['title_similarity'],'body_path':None,'status':'link_not_available'}
        if allow_body(url):
            if consecutive_denied>=5:
                result['status']='deferred_after_five_consecutive_access_denials_no_bypass'
            else:
                raw,req=archive.get(url,r['work_id'],'body'); result['request']=req
                consecutive_denied=consecutive_denied+1 if req.get('http_status') in ('403','429') else 0
                if raw:
                    try:
                        doc,status=base.parse_body(raw,r['doi'],r['work_id']); result['status']=status
                        if doc:
                            dst=OUT/'documents'/(r['work_id']+'.json'); write_json(dst,doc)
                            result.update(body_path=str(dst),body_sha256=sha(dst))
                    except (ValueError,RuntimeError,KeyError) as e: result.update(status='parse_or_identity_failure',error=str(e)[:300])
                else: result['status']='http_or_transport_failure'
        results.append(result)
        if len(results)%10==0: print(f'Public JATS links: {len(results)}/{len(targets)}; sends {len(archive.calls)}; bodies {sum(bool(r["body_path"]) for r in results)}',flush=True)
    write_json(OUT/'results_private.json',results)
    summary={'targets':len(targets),'http_sends':len(archive.calls),'bodies':sum(bool(r['body_path']) for r in results),
       'statuses':dict(Counter(r['status'] for r in results)),'paid_calls':0,'semantic_decisions':0}
    write_json(OUT/'summary.json',summary)
    write_json(OUT/'run_manifest.json',{'schema':'closure-preprint-body-followup-v5','inputs':[pin(META/'run_manifest.json'),pin(Path(__file__)),pin(Path(base.__file__))],
       'summary':summary,'outputs':inventory(OUT)})
    print('Public JATS follow-up finished:',summary,flush=True)

if __name__=='__main__': main()
