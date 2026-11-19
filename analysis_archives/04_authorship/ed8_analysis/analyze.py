from pathlib import Path
import json, hashlib, sys
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path('/historical-workspace/Desktop/Findings_figures/Findings/v7/finding4_v7_final_v1')
OUT = Path(__file__).resolve().parent
GROUPS = ['Lower', 'Middle', 'Higher', 'Other']
KEY = ['publication_year', 'primary_subfield_id', 'work_type']
SEED = 20261118

def log(*args): print(*args, flush=True)
def read(name, cols=None): return pd.read_parquet(ROOT/'inputs/normalized'/name, columns=cols)
def main():
    studies = read('pairing_studies.parquet', ['study_id','corpus','supported','weight','observed_author_count',*KEY])
    studies = studies.loc[studies.supported].copy().sort_values('study_id').reset_index(drop=True)
    assert studies.groupby('corpus').size().to_dict() == {'AF':5087, 'reference':332760}
    studies['sid'] = np.arange(len(studies))
    baseline = read('institution_groups.parquet')
    keep = (baseline.eligible_20 & baseline.group_eligible & baseline.baseline_country_count.eq(1) & baseline.group.isin(['L','M','H']))
    assert keep.sum() == 48010
    group_map = baseline.loc[keep].set_index('institution_id')['group'].map({'L':0,'M':1,'H':2}).to_dict()
    log('Reading observed author-institution affiliations...')
    links = pq.read_table(ROOT/'inputs/normalized/authors_institutions.parquet', columns=['study_id','author_index','institution_id'])
    links = links.filter(pc.is_in(links['study_id'], value_set=pa.array(studies.study_id)))
    df = links.to_pandas().drop_duplicates()
    del links
    df['sid'] = df.study_id.map(studies.set_index('study_id').sid).astype('int32')
    df['g'] = df.institution_id.map(group_map).fillna(3).astype('int8')
    df = df.drop(columns='study_id')
    covered = df.groupby('sid').author_index.nunique()
    studies['mapped_authors'] = studies.sid.map(covered).fillna(0).astype(int)
    studies['all_authors_have_institution'] = studies.mapped_authors.eq(studies.observed_author_count)
    # Each institutional node is one institution ID, regardless of repeated authors/affiliations.
    inst = df.groupby(['sid','institution_id'],sort=False).agg(g=('g','first'),na=('author_index','size'),sole_author=('author_index','first')).reset_index()
    n = pd.crosstab(inst.sid,inst.g).reindex(index=studies.sid,columns=range(4),fill_value=0).to_numpy(dtype='int64')
    counts = n[:,:,None]*n[:,None,:]
    for g in range(4): counts[:,g,g] -= n[:,g]
    # A pair supported only by one author with both affiliations is not counted as collaboration.
    singleton = inst.loc[inst.na.eq(1)]
    solo = singleton.groupby(['sid','sole_author','g']).size().unstack(fill_value=0).reindex(columns=range(4),fill_value=0)
    invalid = np.zeros_like(counts)
    a = solo.to_numpy(dtype='int64')
    sid = solo.index.get_level_values('sid').to_numpy(dtype=int)
    for g in range(4):
        for h in range(4):
            v = a[:,g]*a[:,h] - (a[:,g] if g==h else 0)
            np.add.at(invalid[:,g,h],sid,v)
    counts -= invalid
    assert counts.min() >= 0
    assert np.array_equal(counts,counts.transpose(0,2,1))
    total = counts.sum(axis=(1,2))
    studies['n_institutions'] = n.sum(axis=1)
    studies['valid_undirected_pairs'] = total//2
    studies['excluded_single_author_pairs'] = invalid.sum(axis=(1,2))//2
    studies['link_eligible'] = studies.all_authors_have_institution & (total>0)
    # Rebuild common support and weights within the affiliation-complete collaboration subset.
    eligible = studies.loc[studies.link_eligible]
    support = eligible.groupby(KEY+['corpus']).size().unstack(fill_value=0).reindex(columns=['AF','reference'],fill_value=0).reset_index()
    support['retained'] = (support.AF>=1)&(support.reference>=5)
    support['reference_weight'] = support.AF/support.reference.replace(0,np.nan)
    support.to_csv(OUT/'common_support.csv',index=False)
    studies = studies.merge(support[KEY+['retained','reference_weight']],on=KEY,how='left',validate='many_to_one').sort_values('sid').reset_index(drop=True)
    studies['analysis_included'] = studies.link_eligible & studies.retained.fillna(False).astype(bool)
    studies['analysis_weight'] = np.where(studies.analysis_included,np.where(studies.corpus.eq('AF'),1.,studies.reference_weight),0.)
    q = np.divide(counts,total[:,None,None],out=np.zeros_like(counts,dtype=float),where=total[:,None,None]>0)
    assert np.allclose(q[total>0].sum(axis=(1,2)),1)
    analysis = studies.loc[studies.analysis_included].copy()
    log('Analysis counts:', analysis.groupby('corpus').size().to_dict())
    log('Author-institution complete:', studies.groupby('corpus').all_authors_have_institution.sum().to_dict())
    log('Common cells:', int(support.retained.sum()))
    matrices = {}; rows=[]; partner_rows=[]; summary={}
    included_sids = set(analysis.sid)
    inst_analysis = inst[inst.sid.isin(included_sids)]
    for corpus,sub in analysis.groupby('corpus',sort=False):
        pos = sub.sid.to_numpy()
        w = sub.analysis_weight.to_numpy()
        matrix = np.einsum('i,ijk->jk', w,q[pos])/w.sum()
        partner = matrix/matrix.sum(axis=1,keepdims=True)
        matrices[corpus] = matrix
        for g in range(4):
            for h in range(g,4):
                rows.append({'corpus':corpus,'group_1':GROUPS[g],'group_2':GROUPS[h],'share_pct':100*matrix[g,h]*(1 if g==h else 2)})
            for h in range(4):
                partner_rows.append({'corpus':corpus,'focal_group':GROUPS[g],'partner_group':GROUPS[h],'share_pct':100*partner[g,h]})
        ins = inst_analysis[inst_analysis.sid.isin(pos)]
        summary[corpus] = {'studies':len(sub),'weighted_studies':float(w.sum()),'unique_institutions':int(ins.institution_id.nunique()),'institutions_by_group':{GROUPS[g]:int(ins.loc[ins.g.eq(g),'institution_id'].nunique()) for g in range(4)},'institution_study_counts':{GROUPS[g]:int((n[pos,g]>0).sum()) for g in range(4)},'median_institutions_per_study':float(sub.n_institutions.median()),'studies_with_excluded_single_author_pairs':int(sub.excluded_single_author_pairs.gt(0).sum())}
    pd.DataFrame(rows).to_csv(OUT/'collaboration_group_shares.csv',index=False)
    pd.DataFrame(partner_rows).to_csv(OUT/'partner_composition.csv',index=False)
    studies.to_csv(OUT/'cohort_audit.csv.gz',index=False,compression='gzip')
    baseline.loc[keep,['institution_id','country','group','V_i']].to_csv(OUT/'baseline_groups.csv.gz',index=False,compression='gzip')
    # Save fixed study features for offline audit and conditional whole-study resampling.
    np.savez_compressed(OUT/'study_features.npz',sid=analysis.sid.to_numpy(),q=q[analysis.sid.to_numpy()],weights=analysis.analysis_weight.to_numpy(),corpus=analysis.corpus.to_numpy(dtype=str),study_id=analysis.study_id.to_numpy(dtype=str))
    flow=[]
    for corpus,sub in studies.groupby('corpus'):
        for stage,mask in [('Parent authorship cohort',np.ones(len(sub),bool)),('All authors linked to an institution',sub.all_authors_have_institution),('At least one distinct-author institutional pair',sub.link_eligible),('Rebuilt common support',sub.analysis_included)]:
            flow.append({'corpus':corpus,'stage':stage,'n':int(np.sum(mask))})
    pd.DataFrame(flow).to_csv(OUT/'sample_flow.csv',index=False)
    # Compare restandardized primary estimates with the original parent weights on the same subset.
    sens=[]
    for corpus,sub in analysis.groupby('corpus'):
        pos=sub.sid.to_numpy()
        for label,col in [('Rebuilt common support','analysis_weight'),('Parent weights on same subset','weight')]:
            w=sub[col].to_numpy();m=np.einsum('i,ijk->jk',w,q[pos])/w.sum();p=m/m.sum(axis=1,keepdims=True)
            for g in range(4):sens.append({'corpus':corpus,'specification':label,'focal_group':GROUPS[g],'higher_partner_pct':float(100*p[g,2])})
    pd.DataFrame(sens).to_csv(OUT/'weighting_sensitivity.csv',index=False)
    source_paths=[ROOT/'inputs/normalized'/s for s in ['pairing_studies.parquet','authors_institutions.parquet','institution_groups.parquet']]
    provenance={'source_files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in source_paths],'summary':summary,'groups':GROUPS,'retained_cells':int(support.retained.sum()),'parent_counts':{'AF':5087,'reference':332760},'main_baseline_institutions':48010,'analysis_period':'2020–2025','seed':SEED,'definition':'Undirected co-publication pairs of distinct institution IDs supported by two distinct observed authors; one unit of pair credit per study divided equally among valid pairs. Group matrices retain Other. Partner composition uses pooled fractional link endpoints, not institution-equal averaging or unique-partner counts. All observed authors must have at least one valid institution link. Matching rebuilt within publication-year/subfield/document-type cells with >=1 AF and >=5 screen-negative studies.','validation':{'symmetric_counts':True,'nonnegative_counts':True,'study_credit_sums_to_one':True,'each_corpus_group_shares_sum_to_100':True}}
    for corpus in matrices:
        assert abs(sum(r['share_pct'] for r in rows if r['corpus']==corpus)-100)<1e-9
    (OUT/'analysis_provenance.json').write_text(json.dumps(provenance,indent=2,ensure_ascii=False))
    log('GROUP SHARES\n',pd.DataFrame(rows).to_string(index=False))
    log('PARTNER COMPOSITION\n',pd.DataFrame(partner_rows).to_string(index=False))
    log('SUMMARY',summary)

if __name__=='__main__':main()
