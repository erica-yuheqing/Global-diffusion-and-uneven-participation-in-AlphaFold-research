"""Offline portable replay; explicit input root and never-overwrite output root."""
from common import *
from prepare import prepare
from analytic_check import check_analytic
from documents import write_documents
from draw import draw
from validate import validate
import argparse,shutil

def run(source,out,redraw_only):
 require(source.is_dir(),'Package root absent');require(not out.exists(),'Output must not exist')
 out.mkdir(parents=True)
 for folder in ['inputs','provenance','code','tables']:shutil.copytree(source/folder,out/folder,ignore=shutil.ignore_patterns('__pycache__'))
 (out/'quality').mkdir();(out/'source_data').mkdir();(out/'manuscript').mkdir()
 for folder in ['main','extended','supplementary']:(out/'figures'/folder).mkdir(parents=True)
 shutil.copy2(source/'analysis_config.json',out/'analysis_config.json')
 if not redraw_only:prepare(out);check_analytic(out)
 else:
  for p in source.glob('quality/*.json'):shutil.copy2(p,out/'quality'/p.name)
 write_documents(out);draw(out)
 # Visual statements record the source's actual review, not an invented fresh human review.
 if (source/'quality/visual_review.md').is_file():shutil.copy2(source/'quality/visual_review.md',out/'quality/visual_review.md')
 require((out/'quality/visual_review.md').is_file(),'A source visual review record is required; inspect before release')
 report=validate(out)
 dump(out/'quality/replay_scope.json',{'status':'PASS','redraw_only':redraw_only,'new_simulations':0,'fresh_human_visual_review':False,'source_review_retained':True})
 print('Portable replay PASS:',report['check_count'],'checks',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--package-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--redraw-only',action='store_true');a=p.parse_args();run(a.package_root.resolve(),a.output_root.resolve(),a.redraw_only)
