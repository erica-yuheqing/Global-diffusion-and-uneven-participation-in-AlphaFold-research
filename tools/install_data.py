"""Verify and install the selected Zenodo archives beside the analysis scripts."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-dir', type=Path, required=True)
    parser.add_argument('--bundle', nargs='+', help='Archive stems. The default installs all archives.')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'manifests/data_archives.json').read_text())
    by_name = {Path(row['archive']).stem: row for row in manifest}
    requested = args.bundle or list(by_name)
    if set(requested) - by_name.keys():
        parser.error('Available bundles: ' + ', '.join(by_name))
    with (ROOT / 'manifests/data_files.csv').open() as f:
        rows = list(csv.DictReader(f))
    for stem in requested:
        meta = by_name[stem]
        path = args.from_dir / meta['archive']
        if path.stat().st_size != meta['bytes'] or digest(path) != meta['sha256']:
            raise ValueError(f'Download checksum mismatch: {path.name}')
        members = {r['path']:r for r in rows if r['archive'] == path.name}
        with zipfile.ZipFile(path) as z:
            if len(z.namelist()) != len(members) or set(z.namelist()) != set(members):
                raise ValueError(f'Archive member list differs: {path.name}')
            for member, row in members.items():
                rel = PurePosixPath(member)
                dest = ROOT.joinpath(*rel.parts)
                if rel.is_absolute() or '..' in rel.parts or dest.resolve() != dest:
                    raise ValueError(f'Unexpected path: {member}')
                if dest.exists():
                    if not dest.is_file() or digest(dest) != row['sha256']:
                        raise ValueError(f'Existing file differs: {dest}')
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as f:
                    temp = Path(f.name)
                try:
                    with z.open(member) as source, temp.open('wb') as output:
                        shutil.copyfileobj(source, output, length=1024*1024)
                    if temp.stat().st_size != int(row['bytes']) or digest(temp) != row['sha256']:
                        raise ValueError(f'Data member differs: {member}')
                    os.replace(temp,dest)
                finally:
                    temp.unlink(missing_ok=True)
        print(f'{stem}: {len(members)} verified files', flush=True)


if __name__ == '__main__':
    main()
