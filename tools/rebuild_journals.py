"""Reconstruct the two annual ranking inputs from separately acquired SCImago exports."""
import argparse
import csv
import hashlib
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pipeline/analysis/nhb_05/historical_journals_v1'))
from annual_positions import annual_bridge, category_positions
from import_scimago import parse


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ranking-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with (ROOT/'manifests/source_fingerprints.csv').open() as f:
        pins={r['filename']:r['sha256'] for r in csv.DictReader(f) if r['source'].startswith('SCImago')}
    metadata=pd.read_parquet(ROOT/'data/source_metadata/source_metadata.parquet')
    args.output.mkdir(parents=True,exist_ok=False)
    all_rows=[]
    bridges=[]
    for year in range(2015,2026):
        p=args.ranking_dir/f'scimagojr {year}.csv'
        with p.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=pins[p.name]:
                raise ValueError(f'Annual export differs from manuscript snapshot: {p.name}')
        records, categories, _, _ = parse(p,year)
        long,positions=category_positions(records,categories)
        all_rows.append(long)
        bridges.append(annual_bridge(metadata,records,positions,year))
        print(year,len(long),len(bridges[-1]),flush=True)
    for rows,filename in [(all_rows,'journal_category_positions.parquet'),(bridges,'journal_year_positions.parquet')]:
        pd.concat(rows,ignore_index=True).to_parquet(args.output/filename,index=False)
if __name__=='__main__':
    main()
