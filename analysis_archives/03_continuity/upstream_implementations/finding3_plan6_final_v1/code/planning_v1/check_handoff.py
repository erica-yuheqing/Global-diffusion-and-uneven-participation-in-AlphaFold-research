"""Reproduce the supplied v6 descriptive handoff in a new planning folder."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import pandas as pd

HERE = Path(__file__).resolve().parent
PLAN = Path('/historical-workspace/projects/IGN/revision/finding3-revision-plan-v6')
SOURCE = HERE.parents[1] / 'revision_v9/finding3_plan5_final_v1/tables/institution_pairs.csv'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    dest = HERE / 'reproduced_handoff'
    assert not dest.exists(), 'Refusing to overwrite planning diagnostics'
    manifest = json.loads((PLAN/'现有数据核对/manifest.json').read_text())
    assert sha(SOURCE) == manifest['source_sha256']
    result = subprocess.run([sys.executable, str(PLAN/'核对现有数据.py'),
        '--source', str(SOURCE), '--out', str(dest)], capture_output=True, text=True, check=True)
    compared = []
    for p in sorted((PLAN/'现有数据核对').glob('*.csv')):
        pd.testing.assert_frame_equal(pd.read_csv(p), pd.read_csv(dest/p.name),
                                      check_exact=True)
        compared.append(dict(file=p.name, rows=len(pd.read_csv(p)), sha256=sha(p),
                             byte_identical=p.read_bytes()==(dest/p.name).read_bytes()))
    report = dict(status='PASS', source=str(SOURCE), source_sha256=sha(SOURCE),
        all_five_tables_exact=True, tables=compared,
        instruction_pins=[dict(path=str(p),sha256=sha(p)) for p in sorted(PLAN.rglob('*')) if p.is_file()],
        scope='Plan and descriptive handoff reproduction only; no new classification, standardization, figures, inference or API calls')
    (HERE/'handoff_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status='PASS', tables=len(compared),
        rows=sum(r['rows'] for r in compared), source_hash_matches=True,
        counts=json.loads((dest/'manifest.json').read_text())),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
