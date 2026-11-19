from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import json
import numpy as np
import pandas as pd
O = Path(__file__).resolve().parent
B = 2000
KEY = ['publication_year', 'primary_subfield_id', 'work_type']
GROUPS = ['Lower', 'Middle', 'Higher', 'Other']

def main():
    f = np.load(O / 'study_features.npz')
    cohort = pd.read_csv(O / 'cohort_audit.csv.gz')
    cohort = cohort.loc[cohort.analysis_included].sort_values('sid').reset_index(drop=True)
    assert np.array_equal(cohort.study_id.to_numpy(), f['study_id'])
    q = f['q'].reshape(-1, 16)
    rng = np.random.default_rng(20261118)
    boot = {}
    points = {}
    for corpus in ['AF', 'reference']:
        subset = cohort.loc[cohort.corpus.eq(corpus)]
        sums = np.zeros((B, 16))
        totw = subset.analysis_weight.sum()
        for _, sub in subset.groupby(KEY, sort=True):
            ids = sub.index.to_numpy()
            unique, counts = np.unique(q[ids], axis=0, return_counts=True)
            w = sub.analysis_weight.to_numpy()
            assert np.allclose(w, w[0])
            if len(unique) == 1:
                sums += len(sub) * w[0] * unique[0]
            else:
                draws = rng.multinomial(len(sub), counts / counts.sum(), size=B)
                sums += draws @ unique * w[0]
        boot[corpus] = sums.reshape(B, 4, 4) / totw
        points[corpus] = np.einsum('i,ijk->jk', subset.analysis_weight.to_numpy(), f['q'][subset.index]) / totw
        print(corpus, 'bootstrap completed', flush=True)
    rows = []
    for measure in ['unordered_link_share', 'partner_composition']:
        d = {}
        p = {}
        for corpus in ['AF', 'reference']:
            if measure == 'partner_composition':
                d[corpus] = boot[corpus] / boot[corpus].sum(axis=2, keepdims=True) * 100
                p[corpus] = points[corpus] / points[corpus].sum(axis=1, keepdims=True) * 100
            else:
                mult = np.ones((4, 4)) * 2
                np.fill_diagonal(mult, 1)
                d[corpus] = boot[corpus] * mult * 100
                p[corpus] = points[corpus] * mult * 100
        for g in range(4):
            for h in range(4):
                if measure == 'unordered_link_share' and h < g:
                    continue
                for c in ['AF', 'reference', 'AF - non-AF']:
                    dist = d[c][:, g, h] if c in d else d['AF'][:, g, h] - d['reference'][:, g, h]
                    point = p[c][g, h] if c in p else p['AF'][g, h] - p['reference'][g, h]
                    lo, hi = np.quantile(dist, [0.025, 0.975])
                    rows.append(dict(measure=measure, corpus=c, focal_group=GROUPS[g], partner_group=GROUPS[h], estimate=point, ci_low=lo, ci_high=hi))
    pd.DataFrame(rows).to_csv(O / 'estimates_with_intervals.csv', index=False)
    np.savez_compressed(O / 'bootstrap_group_matrices.npz', AF=boot['AF'], reference=boot['reference'])
    print(pd.DataFrame(rows).query('measure=="partner_composition" and partner_group=="Higher"').to_string(index=False))
    p = json.loads((O / 'analysis_provenance.json').read_text())
    p['uncertainty'] = {'replicates': B, 'seed': 20261118, 'scheme': 'Independent whole-study resampling within corpus/year/subfield/document-type cells, with fixed common support and cell weights; exact multinomial resampling of identical study feature patterns. Percentile intervals conditional on observed studies, affiliation records, group assignments and comparison design.', 'coverage': 'Does not account for all retrieval, affiliation, database or dependence errors.'}
    (O / 'analysis_provenance.json').write_text(json.dumps(p, indent=2, ensure_ascii=False))
if __name__ == '__main__':
    main()
