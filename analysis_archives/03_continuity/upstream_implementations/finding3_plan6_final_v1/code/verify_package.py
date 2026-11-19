"""Offline byte-integrity and relative-link verification; no original data required."""
from pathlib import Path
import sys,json,hashlib
from audit import links

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for v in iter(lambda:f.read(2**20),b''):h.update(v)
    return h.hexdigest()
def verify(root):
    root=Path(root);m=json.loads((root/'run_manifest.json').read_text())
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='run_manifest.json' and '__pycache__' not in p.parts}
    if actual!=set(m['outputs']):raise ValueError('File inventory differs')
    for name,pin in m['outputs'].items():
        p=root/name
        if p.is_symlink() or p.stat().st_size!=pin['bytes'] or sha(p)!=pin['sha256']:raise ValueError('File differs: '+name)
    refs=links(root)
    return dict(status='PASS',files=len(actual),links=len(refs))
if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1])),ensure_ascii=False))
