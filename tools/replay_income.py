"""Reaggregate authorship draws and institution coverage by the frozen FY2020 groups."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
arch=ROOT/'analysis_archives'
source=arch/'06_income'
sys.path.insert(0,str(source))
import analyze_income_groups as analysis


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    (out/'inputs').symlink_to(source/'inputs',target_is_directory=True)
    (out/'tables').mkdir()
    analysis.OUT=out
    meta=json.loads((out/'inputs/original_feature_metadata.json').read_text())
    points=json.loads((out/'inputs/original_feature_points.json').read_text())
    e,n=meta['n_entities'],meta['n_countries']
    data={}
    with np.load(arch/'04_authorship/draws/strict_main_joint_pools.npz') as pools:
        for corpus in ('AF','reference'):
            key='standardized__'+corpus
            data['points_'+corpus]=np.asarray(points[key]).ravel()[:4*e].reshape(4,e)[:,:n]
            data['draws_'+corpus]=pools[key][:,:4*e].reshape(-1,4,e)[:,:,:n]
    mapping=analysis.read(source/'tables/country_income_mapping.csv')
    analysis.verify_authorship(meta,data,mapping)
    _,_,_,shares=analysis.authorship(mapping,data)
    support=analysis.support_counts(mapping)
    _,_,_,summary=analysis.institution_coverage(mapping)
    analysis.population_table(mapping,support,summary,shares)
    tables=sorted((out/'tables').glob('*.csv'))
    for path in tables:
        pd.testing.assert_frame_equal(pd.read_csv(path),pd.read_csv(source/'tables'/path.name),atol=1e-9,rtol=1e-10)
    print('Income reaggregation verified:',len(tables),'tables')
if __name__=='__main__':
    main()
