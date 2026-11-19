"""Offline redraw from this package into a new directory, never overwrite."""
from pathlib import Path
import argparse,shutil
from figures import render
from verify import validate_outputs
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
source=Path(__file__).resolve().parent.parent
if a.output.exists():raise ValueError('Output must not exist')
shutil.copytree(source,a.output,ignore=shutil.ignore_patterns('figures','global_integration','__pycache__','contact_sheet_*.png'))
(a.output/'figures').mkdir();render(a.output)
# Linked global integration is presentation material; restore unchanged after redraw.
if (source/'manuscript/global_integration').exists():shutil.copytree(source/'manuscript/global_integration',a.output/'manuscript/global_integration')
print(validate_outputs(a.output)['status'])
