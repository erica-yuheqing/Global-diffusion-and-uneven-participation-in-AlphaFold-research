"""One-command reproduction of the approved plan; completed outputs never overwritten."""
import argparse
import subprocess
import sys
from support import *

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=OUT);a=p.parse_args();out=a.output_dir.resolve()
    require(not out.exists(),'Use a new absent version directory')
    subprocess.run([sys.executable,str(MODULE/'test_revision.py')],check=True)
    subprocess.run([sys.executable,str(MODULE/'prepare.py'),'--output-dir',str(out)],check=True)
    from benchmark import run
    run(out)
    from figures import run as draw
    draw(out)
    (out/'provenance/visual_review.md').write_text('# Visual review\n\nUnattended replay: author/assistant visual review pending. Numeric checks do not certify layout.\n')
    from finalize import finalize
    finalize(out)

if __name__=='__main__':main()
