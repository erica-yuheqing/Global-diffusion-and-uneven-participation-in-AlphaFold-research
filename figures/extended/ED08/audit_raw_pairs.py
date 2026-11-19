from release_support import release_addfont, release_font_path, release_font_family, release_executable
"""Independent explicit enumeration of the source co-publication pairs."""
from pathlib import Path
from itertools import combinations
from collections import defaultdict
import hashlib
import json
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
O = Path(__file__).resolve().parent
provenance = json.loads((O / 'analysis_provenance.json').read_text())
paths = {Path(s['path']).name: Path(s['path']) for s in provenance['source_files']}
for src in provenance['source_files']:
    assert hashlib.sha256(Path(src['path']).read_bytes()).hexdigest() == src['sha256']
groups = pd.read_parquet(paths['institution_groups.parquet'])
keep = groups.eligible_20 & groups.group_eligible & groups.baseline_country_count.eq(1) & groups.group.isin(['L', 'M', 'H'])
assert keep.sum() == 48010
lookup = groups.loc[keep].set_index('institution_id').group.map({'L': 0, 'M': 1, 'H': 2}).to_dict()
studies = pd.read_parquet(paths['pairing_studies.parquet'])
studies = studies[studies.supported].copy()
keys = ['publication_year', 'primary_subfield_id', 'work_type']
meta = {r.study_id: (r.corpus, r.observed_author_count, (r.publication_year, r.primary_subfield_id, r.work_type)) for r in studies.itertuples()}
table = pq.read_table(paths['authors_institutions.parquet'], columns=['study_id', 'author_index', 'institution_id'])
table = table.filter(pc.is_in(table['study_id'], value_set=pa.array(studies.study_id)))
links = table.to_pandas().drop_duplicates()
del table
pair_types = list(combinations(range(4), 2)) + [(g, g) for g in range(4)]
index = {pair: k for k, pair in enumerate(pair_types)}
sums = defaultdict(lambda: np.zeros(10))
sizes = defaultdict(int)
valid_pairs = 0
excluded_pairs = 0
processed = 0
for study, rows in links.groupby('study_id', sort=False):
    corpus, expected_authors, cell = meta[study]
    if rows.author_index.nunique() != expected_authors:
        continue
    inst_authors = defaultdict(set)
    for author, inst in rows[['author_index', 'institution_id']].itertuples(index=False, name=None):
        inst_authors[inst].add(author)
    features = np.zeros(10)
    for inst1, inst2 in combinations(inst_authors, 2):
        if len(inst_authors[inst1] | inst_authors[inst2]) < 2:
            excluded_pairs += 1
            continue
        g1, g2 = sorted((lookup.get(inst1, 3), lookup.get(inst2, 3)))
        features[index[g1, g2]] += 1
    n = features.sum()
    if n == 0:
        continue
    valid_pairs += int(n)
    sums[corpus, cell] += features / n
    sizes[corpus, cell] += 1
    processed += 1
    if processed % 60000 == 0:
        print('Independently enumerated', processed, 'studies', flush=True)
cells = {cell for corpus, cell in sizes if sizes['AF', cell] >= 1 and sizes['reference', cell] >= 5}
counts = {corpus: sum((sizes[corpus, cell] for cell in cells)) for corpus in ['AF', 'reference']}
total_af = counts['AF']
estimates = {'AF': sum((sums['AF', cell] for cell in cells), start=np.zeros(10)) / total_af * 100, 'reference': sum((sums['reference', cell] * sizes['AF', cell] / sizes['reference', cell] for cell in cells), start=np.zeros(10)) / total_af * 100}
names = ['Lower', 'Middle', 'Higher', 'Other']
old = pd.read_csv(O / 'collaboration_group_shares.csv')
rows = []
max_err = 0.0
for corpus, est in estimates.items():
    for pair, k in index.items():
        g, h = (names[p] for p in pair)
        original = float(old[(old.corpus == corpus) & (old.group_1 == g) & (old.group_2 == h)].share_pct.iloc[0])
        err = abs(original - est[k])
        max_err = max(max_err, err)
        rows.append({'corpus': corpus, 'group_1': g, 'group_2': h, 'source_recomputed_share': float(est[k]), 'plotted_share': original, 'absolute_difference': float(err)})
assert counts == {'AF': 5055, 'reference': 331101}, counts
assert len(cells) == 173
assert max_err < 1e-09, max_err
pd.DataFrame(rows).to_csv(O / 'independent_raw_pair_audit.csv', index=False)
report = {'source_hashes_match': True, 'cohort_counts': counts, 'retained_cells': len(cells), 'independently_enumerated_studies': processed, 'valid_unordered_pairs_before_weighting': valid_pairs, 'excluded_single_author_dual_affiliation_pairs': excluded_pairs, 'max_absolute_error_percentage_points': max_err, 'passed': True}
(O / 'independent_raw_pair_audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
