"""Finish local format/billing audit after the existing C writer closes.

No inference, retries, semantic acceptance, label merges or figure changes.
"""
import json
import subprocess
import sys
import time
from closure_execution_v3 import OUT
from finish_closure_execution_v3 import REPORT
from local_recall import MODULE, require


def main():
    print('Local completion chain waiting for C archive and coordinator report; no extra inference.', flush=True)
    deadline = time.monotonic() + 3 * 3600
    while time.monotonic() < deadline:
        manifests = list((OUT / 'model_c_closure_v3.artifacts').glob('*/run_manifest.json'))
        complete = bool(manifests) and all(json.loads(p.read_text()).get('status') in
            ('completed', 'completed_with_failures') for p in manifests)
        if complete and (REPORT / 'run_manifest.json').is_file():
            break
        time.sleep(10)
    else:
        raise ValueError('No final C/report archive before deadline; nothing accepted or merged')
    for name in ('recover_closure_quotes_v1.py', 'audit_closure_final_budget_v1.py'):
        subprocess.run([sys.executable, str(MODULE / name)], check=True)
    require((MODULE / 'evidence_closure_local_candidates_v1/run_manifest.json').is_file(),
            'Local candidate archive missing')
    print('API/archive + offline format + cost chain completed. All new labels/versions remain pending user confirmation.', flush=True)


if __name__ == '__main__':
    main()
