"""Budgeted, resumable dated incoming-citation acquisition. No LLM calls.

SQLite keeps citing metadata once; pages are committed with their cursor.
Completion of a query is distinct from literal citation-link resolution.
"""
import argparse,concurrent.futures,datetime,gzip,hashlib,json,os,sqlite3,threading,time,urllib.parse,urllib.request,urllib.error,fcntl
import requests
from pathlib import Path
from prepare_inputs import HERE,sha,require,dump
PLAN=HERE/'citation_acquisition_plan_v1';DEFAULT=HERE/'citation_collection_v1'
def short(v):return str(v).rsplit('/',1)[-1]
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def compact(v):return json.dumps(v,separators=(',',':'),ensure_ascii=False)
class Halt(RuntimeError):pass
class Collector:
 def __init__(self,path,key,max_usd=16,max_bytes=2*1024**3):
  self.path=Path(path);self.path.mkdir(exist_ok=True);self.key=key;self.cap=max_usd;self.max_bytes=max_bytes
  self.writer_lock=(self.path/'writer.lock').open('a')
  try:fcntl.flock(self.writer_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise Halt('Another writer is active') from None
  self.lock=threading.Lock();self.db_lock=threading.Lock();self.stop=threading.Event();self.next_send=0.;self.cooldown_until=0.;self.sent=0;self.connections=threading.local()
  self.db=sqlite3.connect(self.path/'records.sqlite',check_same_thread=False)
  self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
  CREATE TABLE IF NOT EXISTS batch(id TEXT PRIMARY KEY,status TEXT,cursor TEXT,identity_done INTEGER DEFAULT 0,raw_rows INTEGER DEFAULT 0,initial_count INTEGER,unresolved INTEGER DEFAULT 0,updated TEXT);
  CREATE TABLE IF NOT EXISTS alias(batch_id TEXT,original TEXT,current TEXT,status TEXT,PRIMARY KEY(batch_id,original));
  CREATE TABLE IF NOT EXISTS citing(id TEXT PRIMARY KEY,date TEXT,doi TEXT,authors BLOB,author_status TEXT);
  CREATE TABLE IF NOT EXISTS edge(citing TEXT,cited_original TEXT,PRIMARY KEY(citing,cited_original)) WITHOUT ROWID;
  CREATE TABLE IF NOT EXISTS unresolved(batch_id TEXT,citing TEXT,refs BLOB,PRIMARY KEY(batch_id,citing));
  CREATE TABLE IF NOT EXISTS page(batch_id TEXT,cursor_in TEXT,cursor_out TEXT,n INTEGER,count_total INTEGER,sha256 TEXT,at TEXT,PRIMARY KEY(batch_id,cursor_in));
  CREATE TABLE IF NOT EXISTS request(n INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,batch_id TEXT,url_hash TEXT,nominal_usd REAL,status TEXT,at TEXT);
  CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);''');self.db.commit()
  self.used=float(self.db.execute("SELECT coalesce(sum(nominal_usd),0) FROM request").fetchone()[0]);self.sent=self.db.execute('SELECT count(*) FROM request').fetchone()[0];self.check_budget()
 def usage(self):return self.used
 def size(self):return sum(p.stat().st_size for p in self.path.rglob('*') if p.is_file())
 def check_budget(self):
  d=self.http('https://api.openalex.org/rate-limit','rate_check','',0)
  rate=d.get('rate_limit',{});available=rate.get('daily_remaining_usd',0)+rate.get('prepaid_remaining_usd',0)
  if rate.get('endpoint_costs_usd',{}).get('list')!=.0001:raise Halt('Provider list price changed')
  if available<.02:raise Halt('Provider balance reserve reached')
  with self.db_lock:
   self.db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('last_rate_limit',compact({'at':utc(),'rate_limit':rate})));self.db.commit()
 def http(self,url,kind,batch,price=.0001,_attempt=0):
  # Reserve before every attempt, including uncertain network failures. Retries
  # use fresh reservations. No credentials in URLs, logs or errors.
  with self.lock:
   if self.stop.is_set():raise Halt('Collection paused')
   with self.db_lock:
    if self.usage()+price>self.cap-1e-8 and price:raise Halt('Total nominal usage cap reached')
    if self.size()>self.max_bytes-8*1024**2:raise Halt('Collection storage reserve reached')
    if self.sent>=300000:raise Halt('HTTP send cap reached')
    cur=self.db.execute('INSERT INTO request(kind,batch_id,url_hash,nominal_usd,status,at) VALUES(?,?,?,?,?,?)',(kind,batch,hashlib.sha256(url.encode()).hexdigest(),price,'reserved',utc()));rid=cur.lastrowid;self.db.commit();self.used+=price
   self.sent+=1
  # A transient provider outage cools down all workers, including requests
  # already queued for dispatch. Recheck after waiting; no ledger reset.
  while True:
   with self.lock:
    cooldown=max(0,max(self.cooldown_until,self.next_send)-time.monotonic())
    if not cooldown:self.next_send=time.monotonic()+.25;break
   if self.stop.wait(min(cooldown,10)):raise Halt('Collection paused')
  if self.stop.is_set():raise Halt('Collection paused')
  status='unknown_network_failure'
  try:
   session=getattr(self.connections,'session',None)
   if session is None:
    session=requests.Session();self.connections.session=session
   with session.get(url,headers={'Authorization':'Bearer '+self.key,'User-Agent':'ScientificInfluenceCitationCollection/1.0'},timeout=(15,60)) as r:
    status='http_'+str(r.status_code)
    if r.status_code==404 and kind=='identity_singleton':return {'id':None}
    if r.status_code in (429,500,502,503,504) and _attempt<2:
     with self.lock:self.cooldown_until=max(self.cooldown_until,time.monotonic()+60*(2**_attempt))
     print('Transient '+status+'; shared cooldown '+str(60*(2**_attempt))+'s; retry '+str(_attempt+1)+'/2',flush=True)
     return Collector.http(self,url,kind,batch,price,_attempt+1)
    if r.status_code!=200:raise Halt('Provider '+status+'; checkpoint retained')
    data=r.json()
   return data
  except urllib.error.HTTPError as e:
   status='http_'+str(e.code)
   if e.code==404 and kind=='identity_singleton':return {'id':None}
   raise Halt('Provider '+status+'; checkpoint retained') from None
  except (OSError,ValueError,requests.RequestException):
   status=status+'_network_or_json_failure'
   if _attempt<2 and not self.stop.is_set():
    time.sleep(3*(2**_attempt))
    return Collector.http(self,url,kind,batch,price,_attempt+1)
   raise Halt('Network/JSON failure after at most 3 attempts; checkpoint retained') from None
  finally:
   with self.db_lock:self.db.execute('UPDATE request SET status=? WHERE n=?',(status,rid));self.db.commit()
 def query(self,params,kind,bid):return self.http('https://api.openalex.org/works?'+urllib.parse.urlencode(params),kind,bid)
 def identity(self,b):
  bid=b['batch_id'];ids=b['work_ids']
  data=self.query({'filter':'openalex:'+'|'.join(ids),'select':'id','per_page':100},'identity_batch',bid)
  require(isinstance(data.get('results'),list),'Invalid identity response')
  found={short(x['id']) for x in data['results']};mapped=[]
  for original in ids:
   current=original;status='same_id'
   if original not in found:
    result=self.http('https://api.openalex.org/works/'+original+'?select=id','identity_singleton',bid,0)
    current=short(result['id']) if result.get('id') else None;status='not_found_unknown' if current is None else ('provider_redirect' if current!=original else 'singleton_confirmed')
   mapped.append((bid,original,current,status))
  with self.db_lock:
   self.db.executemany('INSERT OR REPLACE INTO alias VALUES(?,?,?,?)',mapped)
   self.db.execute('UPDATE batch SET identity_done=1,updated=? WHERE id=?',(utc(),bid));self.db.commit()
 def consume(self,b,cursor,data):
  bid=b['batch_id'];meta=data.get('meta',{});rows=data.get('results')
  require(isinstance(rows,list) and isinstance(meta.get('count'),int),'Invalid works response')
  nxt=meta.get('next_cursor');require(nxt!=cursor or not rows,'Repeated cursor')
  if not rows and nxt:raise Halt('Empty page with next cursor; completeness unresolved')
  with self.db_lock:
   lookup={}
   for orig,now in self.db.execute('SELECT original,current FROM alias WHERE batch_id=?',(bid,)):
    lookup.setdefault(orig,set()).add(orig)
    if now:lookup.setdefault(now,set()).add(orig)
   edges=[];unresolved=[];citers=[]
   for w in rows:
    wid=short(w['id']);refs=w.get('referenced_works');require(isinstance(refs,list),'Missing reference list')
    hits=set()
    for ref in refs:hits.update(lookup.get(short(ref),()))
    authors=w.get('authorships');aids=sorted({short(a['author']['id']) for a in (authors or []) if (a.get('author') or {}).get('id')})
    status='observed_IDs_completeness_not_certified' if authors else 'missing_or_empty'
    citers.append((wid,w.get('publication_date'),w.get('doi'),gzip.compress(compact(aids).encode()),status))
    edges.extend((wid,target) for target in hits)
    if not hits:unresolved.append((bid,wid,gzip.compress(compact(refs).encode())))
   self.db.executemany('INSERT OR IGNORE INTO citing VALUES(?,?,?,?,?)',citers)
   self.db.executemany('INSERT OR IGNORE INTO edge VALUES(?,?)',edges)
   self.db.executemany('INSERT OR REPLACE INTO unresolved VALUES(?,?,?)',unresolved)
   self.db.execute('INSERT INTO page VALUES(?,?,?,?,?,?,?)',(bid,cursor,nxt,len(rows),meta['count'],hashlib.sha256(compact(data).encode()).hexdigest(),utc()))
   self.db.execute('UPDATE batch SET status=?,cursor=?,raw_rows=raw_rows+?,initial_count=coalesce(initial_count,?),unresolved=unresolved+?,updated=? WHERE id=?',('query_complete' if not nxt else 'partial',nxt,len(rows),meta['count'],len(unresolved),utc(),bid));self.db.commit()
  return nxt
 def batch(self,b):
  bid=b['batch_id']
  with self.db_lock:
   self.db.execute("INSERT OR IGNORE INTO batch(id,status,cursor,updated) VALUES(?,'pending','*',?)",(bid,utc()));self.db.commit()
   status,cursor,identity=self.db.execute('SELECT status,cursor,identity_done FROM batch WHERE id=?',(bid,)).fetchone()
  if status=='query_complete':return
  if not identity:self.identity(b)
  while cursor:
   data=self.query({'filter':b['filter'],'select':b['select'],'per_page':100,'cursor':cursor},'incoming_page',bid)
   cursor=self.consume(b,cursor,data)
 def snapshot(self,status):
  with self.db_lock:
   self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
   out={'status':status,'updated_utc':utc(),'nominal_usage_reserved_usd':self.usage(),'usage_hard_cap_usd':self.cap,'storage_hard_cap_bytes':self.max_bytes,'storage_bytes':self.size(),'batch_counts':dict(self.db.execute('SELECT status,count(*) FROM batch GROUP BY 1').fetchall()),'unique_citing_records':self.db.execute('SELECT count(*) FROM citing').fetchone()[0],'unique_literal_edges':self.db.execute('SELECT count(*) FROM edge').fetchone()[0],'unresolved_record_occurrences':self.db.execute('SELECT count(*) FROM unresolved').fetchone()[0],'fixed_window_analysis_ready':False,'note':'query completion and literal reference-link resolution are distinct; final global version dedup and exact windows pending'}
  dump(self.path/'progress.json',out);return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=DEFAULT);ap.add_argument('--workers',type=int,default=4);ap.add_argument('--max-usd',type=float,default=16);ap.add_argument('--max-batches',type=int,default=0);a=ap.parse_args()
 require(1<=a.workers<=8 and 0<a.max_usd<=16,'Allowed workers 1–8; nominal use cap <=16 USD')
 key=os.environ.get('OPENALEX_API_KEY');require(bool(key),'Missing key')
 batches=[json.loads(line) for line in (PLAN/'batches.jsonl').open()]
 if a.max_batches:batches=batches[:a.max_batches]
 job=Collector(a.output,key,a.max_usd)
 code=Path(__file__).read_bytes();code_hash=hashlib.sha256(code).hexdigest();(job.path/'code').mkdir(exist_ok=True)
 code_path=job.path/'code'/(code_hash+'.py')
 if not code_path.exists():code_path.write_bytes(code)
 auth={'user_authorization':'User topped up and reported 16 USD; continue existing authorized acquisition, total nominal usage cap 16 USD','date':'2026-10-30','input_batch_sha256':sha(PLAN/'batches.jsonl'),'max_usd':a.max_usd,'storage_bytes':job.max_bytes,'not_final_analysis':True}
 path=job.path/'execution_policy.json'
 if path.exists():require(json.loads(path.read_text())['input_batch_sha256']==auth['input_batch_sha256'],'Plan changed on resume')
 else:dump(path,auth)
 with job.db_lock:
  job.db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('execution_'+utc(),compact({'at':utc(),'collector_sha256':sha(Path(__file__)),'effective_usage_cap_usd':a.max_usd,'workers':a.workers,'selected_batch_limit':a.max_batches})));job.db.commit()
 def work(b):
  try:job.batch(b)
  except Exception as e:
   job.stop.set();return str(e) if isinstance(e,Halt) else 'Data validation exception: '+type(e).__name__
  return None
 status='completed';last=time.monotonic()
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
   todo=iter(batches);pending={pool.submit(work,b) for b in [next(todo,None) for _ in range(a.workers)] if b is not None}
   while pending:
    done,pending=concurrent.futures.wait(pending,timeout=10,return_when=concurrent.futures.FIRST_COMPLETED)
    problems=[f.result() for f in done];problems=[p for p in problems if p]
    if problems:job.stop.set();print('PAUSE:',problems,flush=True);status='paused';break
    if time.monotonic()-last>=30:
     print(compact(job.snapshot('running')),flush=True)
     try:job.check_budget()
     except Exception:job.stop.set();raise
     last=time.monotonic()
    for _ in done:
     b=next(todo,None)
     if b is not None:pending.add(pool.submit(work,b))
 except KeyboardInterrupt:job.stop.set();status='interrupted'
 except Halt as e:job.stop.set();print(str(e),flush=True);status='paused'
 print(compact(job.snapshot(status)),flush=True);job.db.close();job.writer_lock.close()
if __name__=='__main__':main()
