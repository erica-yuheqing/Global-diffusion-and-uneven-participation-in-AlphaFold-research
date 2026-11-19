"""Never-overwrite offline aggregate rebuild in a new directory."""
from pathlib import Path
import argparse,shutil,subprocess,sys,json
def main():
    p=argparse.ArgumentParser();p.add_argument('--package-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--pdftoppm',required=True);a=p.parse_args()
    source=a.package_root.resolve();out=a.output_root.resolve()
    if out.exists() or not source.is_dir():raise ValueError('Source must exist and output must not exist')
    out.mkdir(parents=True)
    for name in ['code','source_inputs','manuscript','provenance']:shutil.copytree(source/name,out/name,ignore=shutil.ignore_patterns('__pycache__'))
    for f in source.iterdir():
        if f.is_file() and f.suffix in ['.md','.txt','.json']:shutil.copy2(f,out/f.name)
    for name in ['plot_data','source_data','tables','figures']:(out/name).mkdir()
    for script in ['prepare_plot_data.py','verify.py','prepare_linkage.py','write_documents.py','render_figures.py','inspect_pdfs.py','verify_release.py']:
        cmd=[sys.executable,str(out/'code'/script)]
        if script=='render_figures.py':cmd+=['--pdftoppm',a.pdftoppm]
        subprocess.run(cmd,check=True,cwd=out)
    (out/'provenance/replay_status.json').write_text(json.dumps({'status':'PASS','scope':'actual offline aggregate and linkage rebuild, then three-figure redraw','fresh_independent_human_review':False,'source_visual_review_retained':True,'API_calls':0,'LLM_calls':0},indent=2)+'\n')
    print('Offline rebuild PASS:',out,flush=True)
if __name__=='__main__':main()
