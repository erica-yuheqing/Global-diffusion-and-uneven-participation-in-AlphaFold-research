"""Run the manuscript M8 numerical stages from frozen inputs into a fresh directory."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
STAGES=['metrics','rosters','build_comparisons','networks','partners','outcomes','strata','network_analysis','network_diagnostics','data_tables']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--through',choices=STAGES,default=STAGES[-1])
    args=parser.parse_args()
    output=args.output.resolve()
    source=ROOT/'analysis_archives/05_outcomes_networks'
    if not (source/'inputs/paper_base.parquet').is_file():
        parser.error('Install analysis_05_outcomes_networks first')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(source/'code',output/'code')
    (output/'inputs').symlink_to(source/'inputs',target_is_directory=True)
    for name in ['source_data','tables','qa','scratch','cases']:
        (output/name).mkdir()
    # The deposited historical case roster is also indexed under its Table SI7 name.
    shutil.copyfile(source/'tables/T_SI7.csv',output/'cases/candidates.csv')
    env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
    for stage in STAGES[:STAGES.index(args.through)+1]:
        with (output/(stage+'.log')).open('w') as log:
            subprocess.run([sys.executable,str(output/'code'/(stage+'.py'))],cwd=output,env=env,
                           stdout=log,stderr=subprocess.STDOUT,check=True)
        print(stage,'completed',flush=True)
if __name__=='__main__':
    main()
