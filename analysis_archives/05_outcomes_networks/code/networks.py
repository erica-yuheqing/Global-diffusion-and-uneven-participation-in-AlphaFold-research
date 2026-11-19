"""Observed baseline/lagged graphs. No outcome-period edges in baseline."""
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.stats import rankdata
from common import *
def graph_scores(node_ids,history,edges):
 ids=pd.Index(node_ids);u=ids.get_indexer(edges.institution_u);v=ids.get_indexer(edges.institution_v)
 require((u>=0).all() and (v>=0).all(),'Edge outside declared node universe')
 degree=np.bincount(np.r_[u,v],minlength=len(ids));strength=np.bincount(np.r_[u,v],weights=np.r_[edges.fractional_weight,edges.fractional_weight],minlength=len(ids))
 graph=coo_matrix((np.ones(len(u)*2),(np.r_[u,v],np.r_[v,u])),shape=(len(ids),len(ids))).tocsr();_,components=connected_components(graph,directed=False)
 valid=np.asarray(history)>0;percentile=np.full(len(ids),np.nan);sp=percentile.copy()
 if valid.any():percentile[valid]=(rankdata(degree[valid],method='average')-.5)/valid.sum()*100;sp[valid]=(rankdata(strength[valid],method='average')-.5)/valid.sum()*100
 return pd.DataFrame({'institution_id':ids,'degree':np.where(valid,degree,np.nan),'log_degree':np.where(valid,np.log1p(degree),np.nan),'degree_percentile':percentile,'fractional_strength':np.where(valid,strength,np.nan),'log_strength':np.where(valid,np.log1p(strength),np.nan),'strength_percentile':sp,'component_id':pd.array(np.where(valid,components,-1),dtype='Int64')}).assign(component_id=lambda x:x.component_id.mask(~valid))
def build(c,network_id,start,end,expanded=False,exclude_large=False,covered_only=False):
 out=D/'networks'/network_id;out.mkdir(parents=True,exist_ok=True)
 if (out/'audit.json').exists():return json.loads((out/'audit.json').read_text())
 filters=[f's.year BETWEEN {start} AND {end}']
 if not expanded:filters.append('s.B2_eligible')
 if exclude_large:filters.append('r.n_institutions<=20')
 if covered_only:filters.append('r.observed_author_roster_covered')
 c.execute('''CREATE OR REPLACE TEMP TABLE incidence AS SELECT s.study_id,s.institution_id,r.n_institutions m_all,r.observed_author_roster_covered
 FROM s JOIN r USING(study_id) WHERE '''+' AND '.join(filters))
 c.execute('''CREATE OR REPLACE TEMP TABLE sizes AS SELECT study_id,count(*) m_boundary FROM incidence GROUP BY 1''')
 estimate=c.execute('SELECT coalesce(sum(m_boundary*(m_boundary-1)/2),0)::BIGINT FROM sizes').fetchone()[0]
 print('Network',network_id,'pair-study rows',f'{estimate:,}',flush=True)
 parquet(c,'''SELECT a.institution_id institution_u,b.institution_id institution_v,true degree_edge,
 count(*) joint_study_count,sum(1.0/(z.m_boundary-1)) fractional_weight,
 'study_institutions_all.parquet + this network window/boundary filters' source_study_links
 FROM incidence a JOIN incidence b ON a.study_id=b.study_id AND a.institution_id<b.institution_id JOIN sizes z ON a.study_id=z.study_id
 GROUP BY 1,2''',out/'edges.parquet')
 hist=c.execute('''SELECT institution_id,count(*) baseline_n_studies,sum((m_boundary>=2)::INT) joint_study_n,sum(observed_author_roster_covered::INT) observed_roster_covered_n,
 avg(observed_author_roster_covered::INT) affiliation_coverage FROM incidence JOIN sizes USING(study_id) GROUP BY 1''').df()
 nodes=c.execute('SELECT institution_id,country,"group",V_i baseline_output,baseline_eligible B2_eligible FROM i WHERE baseline_eligible').df()
 if expanded:
  external=hist.loc[~hist.institution_id.isin(nodes.institution_id),['institution_id']];external['B2_eligible']=False;nodes=pd.concat([nodes,external],ignore_index=True)
 nodes=nodes.merge(hist,on='institution_id',how='left',validate='one_to_one');nodes['baseline_n_studies']=nodes.baseline_n_studies.fillna(0).astype(int)
 nodes=nodes.sort_values('institution_id').reset_index(drop=True)
 scores=graph_scores(nodes.institution_id,nodes.baseline_n_studies,pd.read_parquet(out/'edges.parquet'));nodes=nodes.merge(scores,on='institution_id',validate='one_to_one')
 valid=nodes.baseline_n_studies.gt(0);require(np.allclose(nodes.loc[valid,'fractional_strength'],nodes.loc[valid,'joint_study_n'],atol=1e-8),'Node-normalized fractional weights do not sum to coauthored-study count')
 nodes.loc[valid,'fractional_strength']=nodes.loc[valid,'joint_study_n'];nodes.loc[valid,'log_strength']=np.log1p(nodes.loc[valid,'joint_study_n']);nodes.loc[valid,'strength_percentile']=(rankdata(nodes.loc[valid,'joint_study_n'],method='average')-.5)/valid.sum()*100
 nodes['network_id']=network_id;nodes['start_year']=start;nodes['end_year']=end;nodes['baseline_record_status']=np.select([nodes.baseline_n_studies.eq(0),nodes.degree.eq(0)],['unassessable_history','observed_zero_in_boundary'],default='observed_connected')
 nodes['publisher_roster_completeness_certified']=False;nodes.to_parquet(out/'nodes.parquet',index=False)
 registry={'network_id':network_id,'start_year':start,'end_year':end,'boundary':'expanded_observed_historical' if expanded else 'B2_induced','exclude_large_network_studies':exclude_large,'covered_observed_authors_only':covered_only,'nodes':len(nodes),'valid_nodes':int(nodes.degree.notna().sum()),'observed_isolates':int(nodes.degree.eq(0).sum()),'unknown_nodes':int(nodes.degree.isna().sum()),'edges':len(pd.read_parquet(out/'edges.parquet',columns=['institution_u'])),'pair_study_rows':int(estimate),'source_rows':'source_data/study_institutions_all.parquet; window and filters above','publisher_completeness':'unverified, not filled true','fractional_m':'boundary nodes per study; full-team m separately retained','status':'completed_observed_network'}
 dump(out/'audit.json',registry);return registry
def main():
 c=con();view(c,'s',D/'study_institutions_all.parquet');view(c,'r',D/'study_roster_quality.parquet');view(c,'i',I/'institutions.parquet')
 tasks=[('baseline_B2',2015,2019,False,False,False),('baseline_expanded',2015,2019,True,False,False),('baseline_no_large',2015,2019,False,True,False),('baseline_observed_covered',2015,2019,False,False,True)]
 tasks += [(f'rolling_B2_{year}',year-3,year-1,False,False,False) for year in range(2020,2026)]
 registry=[build(c,*task) for task in tasks];table('T_SI8_network_registry',pd.DataFrame(registry));dump(Q/'network_audit.json',{'networks':registry,'outcome_coefficients_inspected_for_network_choice':False,'full_publisher_certified_network':'not_computable: flag not collected'})
 print('ALL BASELINE/ROLLING NETWORKS BUILT',len(registry),flush=True)
if __name__=='__main__':main()
