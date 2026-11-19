"""Additional prespecified unique-affiliation subcohort and probability diagnostics."""
from common import *
from bootstrap import fit,group_only
from sensitivity import weighted
from scipy import sparse
def main():
    m=norm('analysis_members.parquet');st=norm('study_structure.parquet').set_index('study_id').loc[m.study_id];meta=json.loads((ROOT/'inputs/normalized/feature_metadata.json').read_text());X,gm=group_only(sparse.load_npz(ROOT/'inputs/normalized/feature_matrix.npz'),meta)
    mask=(st.unresolved_cells.eq(0)&st.first_countries.eq(1)&st.last_countries.eq(1)&st.first_institutions.eq(1)&st.last_institutions.eq(1)).to_numpy();mm=weighted(m[mask].reset_index(drop=True));fit('unique_role_country_institution',mm,X[mask],gm,40)
    # ED4 is a three-category observed-structure sensitivity, not the unique-country
    # conditional-endpoint reference; its expected-pair columns retain unrestricted teams.
    cov=[]
    for cp in CORPORA:
      p=m[m.corpus.eq(cp)];v=mm[mm.corpus.eq(cp)];w=v.weight.to_numpy();cov.append(dict(corpus=cp,main_raw=len(p),unique_role_country_institution_raw=len(v),retained_fraction=len(v)/len(p),supported=int(v.supported.sum()),support_retention=v.supported.mean(),ESS=div(w.sum()**2,(w*w).sum()).item(),purpose='ED4 observed structure; separate country-only pool sensitivity for endpoint inference'))
    save('unique_institution_coverage',pd.DataFrame(cov))
    c=connect();d=ROOT/'inputs/normalized'
    for n in ['authors_institutions','conditional_reference_studies','authors','institution_zero_entities']:
      c.execute(f'CREATE VIEW {n} AS SELECT * FROM read_parquet({q(d/(n+".parquet"))})')
    # Historical institutional role definition: equal ID share, then ID country share.
    qv=c.execute('''WITH pairs AS (SELECT DISTINCT i.study_id,i.author_id,i.institution_id,i.institution_country FROM authors_institutions i JOIN conditional_reference_studies s USING(study_id) WHERE s.inst_eligible),
      ni AS (SELECT study_id,author_id,count(DISTINCT institution_id) AS ni FROM pairs GROUP BY 1,2),
      nc AS (SELECT study_id,author_id,institution_id,count(*) AS nc FROM pairs GROUP BY 1,2,3),
      na AS (SELECT a.study_id,count(*) AS A FROM authors a JOIN conditional_reference_studies s USING(study_id) WHERE s.inst_eligible GROUP BY 1),
      qs AS (SELECT p.study_id,p.institution_id,p.institution_country,sum(1.0/(ni.ni*nc.nc*na.A)) AS q FROM pairs p JOIN ni USING(study_id,author_id) JOIN nc USING(study_id,author_id,institution_id) JOIN na USING(study_id) GROUP BY 1,2,3)
      SELECT e.eidx,sum(qs.q) AS expected_fractional_role_credit FROM qs JOIN conditional_reference_studies s USING(study_id) JOIN institution_zero_entities e ON e.corpus=s.corpus AND e.country_code=qs.institution_country AND e.institution_id=qs.institution_id GROUP BY 1''').df()
    er=pd.read_parquet(ROOT/'tables/institution_zero_entities.parquet').merge(qv,on='eidx',how='left',validate='one_to_one');er['probability_credit_distinction']='P0 uses pi, not fractional q';save('institution_zero_entities',er);c.close()
    # Historical comparison matches shared AF/ref studies but does not relabel old CIs.
    rows=[];new= pd.read_parquet(ROOT/'tables/strict_main_R.parquet')
    for bench,file in [('country','country_fraction_author_same_sample_R.csv'),('author','author_fraction_R.csv')]:
      old=read(file);old['corpus']=old.corpus.replace({'non-AF':'reference'});old['entity_id']=old.entity_id.replace({'group:high':'group:higher','group:low':'group:lower','group:outside_fixed_group':'group:outside'});old=old[old.setting.eq('standardized')&old.level.eq('group')];nn=new[new.benchmark.eq(bench)&new.setting.eq('standardized')&new.level.eq('group')];t=nn.merge(old[['corpus','role','entity_id','R','ci_low','ci_high']],on=['corpus','role','entity_id'],suffixes=('_strict','_legacy'),validate='one_to_one');t['point_change']=t.R_strict-t.R_legacy;rows.append(t)
    save('Figure4_legacy_strict_comparison',pd.concat(rows,ignore_index=True))
    dump(ROOT/'provenance/refinements_complete.json',dict(status='PASS',unique_affiliation_sample=True,institution_fractional_q_not_P0=True,historical_comparison=True,legacy_intervals='kept distinct from new bootstrap; no claimed interval difference test'))
if __name__=='__main__':main()
