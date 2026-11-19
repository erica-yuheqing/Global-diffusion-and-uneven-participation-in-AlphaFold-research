from pathlib import Path
import json,hashlib,datetime
import duckdb,pandas as pd,numpy as np
P=Path(__file__).resolve().parents[1]
if P.name=='finding5_plan_v8':P=P/'Scientific_Influence_analysis_v2.0'
I=P/'inputs';D=P/'source_data';T=P/'tables';Q=P/'qa'
SEED=20261029;B=5000
def require(ok,message):
 if not ok:raise ValueError(message)
def dump(path,value):
 Path(path).parent.mkdir(parents=True,exist_ok=True)
 Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+'\n')
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
def lit(path):return "'"+str(path).replace("'","''")+"'"
def con():return duckdb.connect(config={'threads':2,'memory_limit':'3GiB','preserve_insertion_order':False,'temp_directory':str(P/'scratch'),'max_temp_directory_size':'8GiB'})
def view(c,name,path):c.execute(f'CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet({lit(path)})')
def parquet(c,sql,path):
 Path(path).parent.mkdir(parents=True,exist_ok=True);c.execute(f'COPY ({sql}) TO {lit(path)} (FORMAT PARQUET,COMPRESSION ZSTD)')
def table(name,frame):frame.to_csv(T/(name+'.csv'),index=False)
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
