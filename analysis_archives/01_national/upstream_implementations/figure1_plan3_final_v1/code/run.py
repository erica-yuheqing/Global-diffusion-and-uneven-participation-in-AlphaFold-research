"""Replay original project preparation or finish/verify a visually reviewed output."""
import argparse
from common import *
def main():
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group();mode.add_argument('--finish',action='store_true');mode.add_argument('--verify-only',action='store_true');a=parser.parse_args()
    if a.finish:
        from verify import finish
        finish(OUT);return
    if a.verify_only:
        from verify import verify
        verify(OUT);return
    from prepare import run as prep
    from matching import run as match
    from enrich import run as enrich
    from import_handoff import run as handoff
    from draw import run as draw
    from report import run as report
    prep(OUT);match(OUT);enrich(OUT);handoff(OUT);draw(OUT);report(OUT)
    print('Prepared; inspect actual figures and record provenance/visual_review_zh.md before --finish. Existing outputs are not overwritten.')
if __name__=='__main__':main()
