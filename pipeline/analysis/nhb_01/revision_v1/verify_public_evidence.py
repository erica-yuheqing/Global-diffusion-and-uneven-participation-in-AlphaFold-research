"""Verify the bounded new public-evidence archive without network or writes."""
import argparse
from pathlib import Path
from fetch_public_evidence import MODULE, verify

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', type=Path, default=MODULE/'public_evidence_v1')
    a=p.parse_args(); s=verify(a.input_dir)
    print(f'Public evidence archive/reconstruction PASS; works: {s["candidate_works"]}; bodies: {s["verified_fulltext_bodies"]}')
    print('AF labels unchanged; evidence availability only; semantic review and final revised figure pending')
