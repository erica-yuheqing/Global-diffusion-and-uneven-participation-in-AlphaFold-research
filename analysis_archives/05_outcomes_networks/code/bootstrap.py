"""Joint positive whole-study multipliers, recomputed controls and institutions."""
from scipy.sparse import csr_matrix
from common import *
from shared_weights import keys as study_keys,weights_from_keys
KEY=['institution_id','year','subfield','work_type']
M=['journal_position','high_journal75','percentile_12m','high_citation90','high_journal90','high_citation95']
BINARY={'high_journal75','high_journal90','high_citation90','high_citation95','official_best_Q1','high_citation24_90'}
def engine(z,controls,name,metrics,extra_key=None,iterations=5000):
 keys=KEY+([extra_key] if extra_key else []);z=z.copy()
 if len(z)==0:return [],pd.DataFrame(),pd.DataFrame()
 cells=z[keys].drop_duplicates().reset_index(drop=True);cells['cell']=np.arange(len(cells))
 r=controls.merge(cells,on=keys,how='inner',validate='many_to_one');r=r[r[metrics].notna().any(axis=1)]
 z=z.merge(cells,on=keys,validate='many_to_one')
 inst=z[['institution_id','country','group']].drop_duplicates().sort_values('institution_id').reset_index(drop=True);inst['inst']=np.arange(len(inst))
 z=z.merge(inst,on=['institution_id','country','group'],validate='many_to_one');ids=pd.Index(sorted(set(z.study_id)|set(r.study_id)));ri=ids.get_indexer(r.study_id);ai=ids.get_indexer(z.study_id)
 A=csr_matrix((np.ones(len(z)),(z.inst,np.arange(len(z)))),shape=(len(inst),len(z)))
 matrices={};raw={}
 for m in metrics:
  good=r[m].notna();count=csr_matrix((np.ones(good.sum()),(r.loc[good,'cell'],ri[good])),shape=(len(cells),len(ids)))
  total=csr_matrix((r.loc[good,m].to_numpy(),(r.loc[good,'cell'],ri[good])),shape=count.shape)
  require(np.all(count.sum(axis=1).A1>0),'Metric-specific empty control cell: '+name+'/'+m)
  matrices[m]=(count,total);ref=(total@np.ones(len(ids)))/(count@np.ones(len(ids)));scale=100 if m in BINARY else 1
  z['AF_'+m]=z[m]*scale;z['REF_'+m]=ref[z.cell.to_numpy()]*scale;z['delta_'+m]=z['AF_'+m]-z['REF_'+m]
  raw[m]=z[m].to_numpy()
 inst_values=z.groupby('institution_id')[[p+m for m in metrics for p in ['AF_','REF_','delta_']]].mean().reset_index().merge(inst,on='institution_id',validate='one_to_one')
 inst_values['sample_id']=name;inst_values['n_AF_works']=inst_values.institution_id.map(z.groupby('institution_id').study_id.nunique())
 # Country/leave-one-country/paper/institution-year reweighting uses the SAME
 # multiplier draws and supports; it does not silently change the sample.
 country_weights={g:inst.loc[inst.group.eq(g),'country'].value_counts() for g in ['L','M','H']}
 rows=[];draw_records=[];weight_keys=study_keys(ids);ci=z.cell.to_numpy();idx=z.inst.to_numpy()
 paper_weight=1/z.groupby(['group','study_id']).study_id.transform('size').to_numpy()
 for start in range(0,iterations,16):
  n=min(16,iterations-start);w=weights_from_keys(weight_keys,start,n);aw=w[ai];iden=A@aw
  for m in metrics:
   C,Y=matrices[m];ref=(Y@w)/(C@w);scale=100 if m in BINARY else 1
   di=(A@(aw*(raw[m][:,None]-ref[ci])))/iden*scale
   for g in ['L','M','H']:
    mask=inst.group.eq(g).to_numpy()
    if not mask.any():continue
    dv=di[mask].mean(axis=0)
    cw=np.array([1/country_weights[g][v] for v in inst.loc[mask,'country']]);country_dv=np.average(di[mask],axis=0,weights=cw)
    gm=z.group.eq(g).to_numpy();pw=aw[gm]*paper_weight[gm,None]
    paper_dv=(pw*(raw[m][gm,None]-ref[ci[gm]])).sum(axis=0)/pw.sum(axis=0)*scale
    for j in range(n):draw_records.append(dict(sample_id=name,replicate=start+j,group=g,metric=m,delta=float(dv[j]),country_equal_delta=float(country_dv[j]),paper_equal_delta=float(paper_dv[j])))
  if start%1200==0:print('Bootstrap',name,start,'/',iterations,'unique papers',len(ids),flush=True)
 draws=pd.DataFrame(draw_records)
 for m in metrics:
  for g in ['L','M','H']:
   v=inst_values[inst_values.group.eq(g)];zz=z[z.group.eq(g)];rr=r[r.institution_id.isin(v.institution_id)&r[m].notna()]
   if not len(v):continue
   boot=draws[draws.group.eq(g)&draws.metric.eq(m)]
   lo,hi=np.quantile(boot.delta,[.025,.975]);clo,chi=np.quantile(boot.country_equal_delta,[.025,.975])
   plo,phi=np.quantile(boot.paper_equal_delta,[.025,.975])
   rows.append(dict(sample_id=name,group=g,metric=m,estimate=v['delta_'+m].mean(),lower=lo,upper=hi,AF_mean=v['AF_'+m].mean(),REF_mean=v['REF_'+m].mean(),unit='percentage_points' if m in BINARY else 'percentile_points',n_institutions=len(v),n_af_works=zz.study_id.nunique(),n_control_works=rr.study_id.nunique(),n_affiliation_links=len(zz),n_countries=v.country.nunique(),weighting='equal_institution_then_equal_AF_paper',interval_type='conditional_Exp1_whole_approved_study_5000',country_equal_estimate=v.groupby('country')['delta_'+m].mean().mean(),country_equal_lower=clo,country_equal_upper=chi,paper_equal_estimate=zz.groupby('study_id')['delta_'+m].mean().mean(),paper_equal_lower=plo,paper_equal_upper=phi,status='completed'))
 inst_values.to_parquet(D/('institutions_'+name+'.parquet'),index=False)
 draws.to_parquet(D/('draws_'+name+'.parquet'),index=False)
 return rows,inst_values,z
