"""Complete observed partner sets are formed BEFORE boundary filtering."""
from common import *
def partner_summary(focal,roster,scores,node_ids,covered):
 roster=set(roster);present=focal in roster;others=roster-{focal};values=[scores[j] for j in others if j in scores and pd.notna(scores[j])]
 outside=sum(j not in node_ids for j in others);n=len(others);partial=float(np.mean(values)) if values else np.nan
 valid=bool(present and covered and n>0 and len(values)==n)
 status='valid_observed_roster_all_partners_scored' if valid else 'focal_not_in_roster' if not present else 'observed_author_affiliations_incomplete' if not covered else 'single_institution' if n==0 else 'outside_boundary' if outside else 'partner_baseline_unknown'
 return dict(n_other_institutions=n,n_scored_partners=len(values),n_outside_boundary=outside,n_unknown_baseline=n-len(values)-outside,
 partner_mean_percentile=partial if valid else np.nan,partner_max_percentile=max(values) if valid else np.nan,partial_partner_mean_percentile=partial,partial_partner_max_percentile=max(values) if values else np.nan,
 coverage=len(values)/n if n else np.nan,single_institution=bool(present and covered and n==0),observed_single_institution=bool(present and n==0),focal_in_roster=present,observed_author_roster_covered=bool(covered),status=status)
def main():
 c=con();view(c,'a',D/'matched_comparisons.parquet');view(c,'s',D/'study_institutions_all.parquet');view(c,'r',D/'study_roster_quality.parquet')
 roster=c.execute('''SELECT s.study_id,list(DISTINCT institution_id) roster FROM s SEMI JOIN a USING(study_id) GROUP BY 1''').df().set_index('study_id').roster.to_dict()
 a=pd.read_parquet(D/'matched_comparisons.parquet');quality=c.execute('SELECT r.* FROM r SEMI JOIN a USING(study_id)').df().set_index('study_id')
 configs=[('degree','baseline_B2','degree_percentile','log_degree'),('strength','baseline_B2','strength_percentile','log_strength'),('expanded','baseline_expanded','degree_percentile','log_degree'),('network_no_large','baseline_no_large','degree_percentile','log_degree'),('observed_covered_network','baseline_observed_covered','degree_percentile','log_degree'),('rolling','rolling','degree_percentile','log_degree')]
 for variant,network_id,scorecol,xcol in configs:
  target=D/('partners_'+variant+'.parquet')
  if target.exists():continue
  maps={}
  for year in (range(2020,2026) if variant=='rolling' else [0]):
   nid=f'rolling_B2_{year}' if variant=='rolling' else network_id;n=pd.read_parquet(D/'networks'/nid/'nodes.parquet').set_index('institution_id');maps[year]=(nid,n[scorecol].to_dict(),n[xcol].to_dict(),set(n.index))
  rows=[]
  for rec in a[['study_id','institution_id','year','country','group']].itertuples(index=False):
   nid,scores,xs,nodeids=maps[rec.year if variant=='rolling' else 0];q=quality.loc[rec.study_id]
   row=partner_summary(rec.institution_id,roster.get(rec.study_id,[]),scores,nodeids,q.observed_author_roster_covered)
   row.update(study_id=rec.study_id,institution_id=rec.institution_id,year=rec.year,country=rec.country,group=rec.group,network_id=nid,variant=variant,x_log=xs.get(rec.institution_id,np.nan),m_all=int(q.n_institutions),publisher_roster_completeness_certified=False)
   rows.append(row)
  pd.DataFrame(rows).to_parquet(target,index=False);print('Partner scoring',variant,len(rows),'focal records',flush=True)
 # Reproducible primary partner contributions and old/new observed links.
 primary=pd.read_parquet(D/'partners_degree.parquet');pairs=[]
 nodes=pd.read_parquet(D/'networks/baseline_B2/nodes.parquet').set_index('institution_id').degree_percentile.to_dict()
 for rec in primary.itertuples(index=False):
  for partner in set(roster.get(rec.study_id,[]))-{rec.institution_id}:pairs.append(dict(study_id=rec.study_id,institution_id=rec.institution_id,partner_id=partner,partner_percentile=nodes.get(partner,np.nan),u=min(rec.institution_id,partner),v=max(rec.institution_id,partner)))
 pairframe=pd.DataFrame(pairs);c.register('pairs',pairframe);view(c,'edge',D/'networks/baseline_B2/edges.parquet')
 parquet(c,'''SELECT pairs.*,edge.institution_u IS NOT NULL observed_baseline_connection FROM pairs LEFT JOIN edge ON pairs.u=edge.institution_u AND pairs.v=edge.institution_v''',D/'partner_contributions_main.parquet')
 for variant,_,_,_ in configs:
  z=pd.read_parquet(D/('partners_'+variant+'.parquet'))
  table('T_SI8_partner_'+variant,z.groupby(['country','group','year','status'],dropna=False).agg(AF_links=('study_id','size'),AF_studies=('study_id','nunique'),institutions=('institution_id','nunique'),scored_partners=('n_scored_partners','sum'),observed_partners=('n_other_institutions','sum')).reset_index())
 dump(Q/'partner_audit.json',{'variants':[v[0] for v in configs],'focal_excluded':True,'unscored_not_zero':True,'single_institution_separate':True,'all_observed_partners_before_boundary':True,'publisher_complete_roster_certified':False,'quality_gate':'all imported author IDs assigned, no missing author IDs; all observed partners scored','strict_publisher_certified_partner_branch':'not_computable'})
 print('PARTNER VARIANTS AND FULL-ROSTER AUDITS COMPLETE',flush=True)
if __name__=='__main__':main()
