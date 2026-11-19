"""Freeze core-review inputs; no public retrieval or paid model calls."""
import argparse
import json
from pathlib import Path
import tempfile
from evidence_closure_api_v1 import assemble, INPUTS, verify_inputs
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, write_json


def write_jsonl(path, rows):
    with path.open('x') as handle:
        for row in rows: handle.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    path.chmod(0o600)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry-run',action='store_true');p.add_argument('--verify-only',action='store_true')
    a=p.parse_args()
    if a.verify_only:
        print('API input freeze: PASS;',json.dumps(verify_inputs()['summary'],ensure_ascii=False));return
    packets,private,ids,summary,pins=assemble()
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if a.dry_run: print('No requests, files, approvals or merges');return
    out=destination(INPUTS)
    stage=Path(tempfile.mkdtemp(prefix='.closure-api-inputs-',dir=MODULE));stage.chmod(0o700)
    write_jsonl(stage/'closure586_model_inputs.jsonl',packets)
    by_id={p['work_id']:p for p in packets}
    write_jsonl(stage/'smoke20_model_inputs.jsonl',[by_id[wid] for wid in ids])
    write_json(stage/'smoke20_ids.json',ids);write_json(stage/'provenance_private.json',private)
    write_json(stage/'summary.json',summary)
    write_json(stage/'run_manifest.json',{'schema':'figure1-closure-api-input-freeze-v1','inputs':pins,'summary':summary,'outputs':inventory(stage)})
    verify_inputs(stage);stage.rename(out)
    print('Frozen + verified:',out,'; all model semantics still pending')


if __name__=='__main__': main()
