"""One-command local replay into a new version; never overwrites a completed run."""
import argparse
import subprocess
import sys
from support import *

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();out=a.output_dir.resolve()
    require(not out.exists(),'A replay requires a new, nonexistent destination')
    stages={n:module('plan3_replay_'+n,MODULE/(n+'.py')) for n in ['prepare','benchmark','authors','initial_models','figures','visual_review']}
    source=pins();out.mkdir();(out/'tables').mkdir();(out/'provenance').mkdir();(out/'scratch').mkdir()
    dump(out/'provenance/input_pins.json',source)
    stages['prepare'].build(out)
    dump(out/'provenance/prepare_complete.json',dict(status='PASS',input_pins_unchanged=source==pins()))
    for name in ['benchmark','authors','initial_models','figures','visual_review']:stages[name].run(out)
    subprocess.run([sys.executable,str(MODULE/'finalize.py'),'--output-dir',str(out)],cwd=ROOT,check=True)

if __name__=='__main__':main()
