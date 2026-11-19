"""Recollect one of the 22 original OpenAlex primary subfields in a private destination."""
from pathlib import Path
import argparse,csv,fcntl,json,os,time,urllib.parse,urllib.request,urllib.error
SCOPE=Path(__file__).resolve().parent/'config/subfields.csv'
FIELDS='id,doi,display_name,publication_year,publication_date,cited_by_count,referenced_works,abstract_inverted_index,authorships,concepts,primary_location,primary_topic,topics,type'
def convert(work,sid,label):
 index=work.get('abstract_inverted_index') or {}
 positions=sorted((i,word) for word,indices in index.items() for i in indices)
 result={k:work.get(k) for k in FIELDS.split(',') if k not in {'abstract_inverted_index','display_name'}}
 result.update(title=work.get('display_name'),abstract=' '.join(word for _,word in positions),domain_label=label,domain_subfield_ids=[f'https://openalex.org/subfields/{sid}'],normalized_subfield_ids=[sid])
 return result
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--list',action='store_true');p.add_argument('--subfield');p.add_argument('--destination',type=Path);p.add_argument('--page-size',type=int,default=100,choices=range(1,101),metavar='1..100');a=p.parse_args()
 with SCOPE.open() as f:scope={r['subfield'].split('/')[-1]:r['subfield_name'] for r in csv.DictReader(f)}
 if a.list:print(json.dumps(scope,indent=2));return
 if a.subfield not in scope or not a.destination:p.error('Provide one listed subfield and a private destination.')
 key=os.environ.get('OPENALEX_API_KEY')
 if not key:p.error('Set OPENALEX_API_KEY locally for live recollection.')
 folder=a.destination.resolve()/a.subfield;folder.mkdir(parents=True,exist_ok=True)
 query=f'primary_topic.subfield.id:{a.subfield},from_publication_date:2015-01-01,to_publication_date:2025-12-31'
 label=scope[a.subfield].lower().replace(' ','_')
 statefile=folder/'checkpoint.json';path=folder/('domain_'+label+'_2015_2025.jsonl')
 with (folder/'writer.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  state=json.loads(statefile.read_text()) if statefile.exists() else dict(cursor='*',offset=0,records=0,query=query)
  if state['query']!=query:raise ValueError('Checkpoint filter differs')
  if not statefile.exists() and path.exists() and path.stat().st_size:raise ValueError('Orphan output without checkpoint; choose a fresh directory')
  if not statefile.exists():
   temp=folder/'checkpoint.tmp'
   temp.write_text(json.dumps(state))
   os.replace(temp,statefile)
  if state['offset']>(path.stat().st_size if path.exists() else 0):raise ValueError('Output shorter than the saved checkpoint')
  if state['cursor'] is None:return
  with path.open('ab') as f:
   f.truncate(state['offset'])
   while state['cursor'] is not None:
    params=dict(filter=query,select=FIELDS,cursor=state['cursor'],api_key=key);params['per_page']=a.page_size
    url='https://api.openalex.org/works?'+urllib.parse.urlencode(params)
    for retry in range(5):
     try:
      with urllib.request.urlopen(url,timeout=60) as response:page=json.load(response)
      break
     except urllib.error.HTTPError as error:
      if error.code not in (429,500,502,503,504) or retry==4:raise SystemExit(f'OpenAlex returned HTTP {error.code}; checkpoint retained.') from None
      time.sleep(2**retry)
     except (TimeoutError,urllib.error.URLError):
      if retry==4:raise SystemExit('Connection failed; resume from checkpoint.') from None
      time.sleep(2**retry)
    rows=page['results'];next_cursor=page['meta']['next_cursor']
    if next_cursor==state['cursor']:raise ValueError('Provider returned the same cursor')
    for work in rows:f.write((json.dumps(convert(work,a.subfield,label),ensure_ascii=False)+'\n').encode())
    f.flush();os.fsync(f.fileno())
    state.update(cursor=next_cursor,records=state['records']+len(rows),offset=f.tell())
    temp=folder/'checkpoint.tmp';temp.write_text(json.dumps(state));os.replace(temp,statefile)
    print(state['records'],flush=True)
if __name__=='__main__':main()
