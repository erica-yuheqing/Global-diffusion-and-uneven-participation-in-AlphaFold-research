"""Rebuild N01 in a new output and compare complete normalized relations."""
from pathlib import Path
import argparse, json, shutil, sys, subprocess
import duckdb
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--output',required=True,type=Path)
 args=parser.parse_args()
 root=Path(__file__).resolve().parents[1]; dest=args.output.resolve()
 src=root/'analysis_archives/04_authorship'; upstream=root/'data/author_inputs'
 if dest.exists():raise SystemExit('Choose a new output directory')
 pins=json.loads((upstream/'source_pins.json').read_text())
 by_filename={Path(r['path']).name:str(root/r['path']) for r in pins}
 original=json.loads((src/'provenance/input_catalog.json').read_text())
 catalog={k:([by_filename[Path(v).name] for v in val] if isinstance(val,list) else by_filename[Path(val).name]) for k,val in original.items()}
 for folder in ['inputs/normalized','tables','provenance','scratch']:(dest/folder).mkdir(parents=True,exist_ok=True)
 for name in ['local','handoff']:(dest/'inputs'/name).symlink_to(src/'inputs'/name,target_is_directory=True)
 shutil.copytree(src/'code',dest/'code')
 (dest/'provenance/input_catalog.json').write_text(json.dumps(catalog))
 subprocess.run([sys.executable,str(dest/'code/prepare.py')],check=True)
 conn=duckdb.connect(config={'threads':1,'memory_limit':'2GB','temp_directory':str(dest/'scratch')})
 checked={}
 for p in sorted((dest/'inputs/normalized').glob('*.parquet')):
  old=src/'inputs/normalized'/p.name
  # A bidirectional multiset comparison, irrespective of row order.
  conn.read_parquet(str(p)).create_view('regenerated',replace=True)
  conn.read_parquet(str(old)).create_view('frozen',replace=True)
  diff=conn.execute('SELECT count(*) FROM ((FROM regenerated EXCEPT ALL FROM frozen) UNION ALL (FROM frozen EXCEPT ALL FROM regenerated))').fetchone()[0]
  checked[p.name]=diff
 (dest/'differences.json').write_text(json.dumps(checked,indent=2))
 if not checked or any(checked.values()):raise SystemExit('N01 comparison differs; inspect differences.json')
 print('Exact normalized relation comparison passed:',len(checked))
if __name__=='__main__':main()
