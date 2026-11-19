"""Joint-study conditional network associations and all support-aware variants."""
from scipy.sparse import csr_matrix
from common import *
from shared_weights import keys,weights_from_keys
from model_math import design,diagnose,fit,m0_eligibility
KEY=['institution_id','year','subfield','work_type']
class Bundle:
 def __init__(self,outcome):
  self.outcome=outcome;self.metric='journal_position' if outcome=='journal' else 'percentile_12m';self.binary='high_journal75' if outcome=='journal' else 'high_citation90'
  a=pd.read_parquet(D/'matched_comparisons.parquet');a=a[a.journal_support if outcome=='journal' else (a.in_main_years&a.citation_support)].copy()
  self.a=a.sort_values(['institution_id','study_id']).reset_index(drop=True);self.a['af_row']=np.arange(len(a))
  r=pd.read_parquet(D/'control_links.parquet',columns=['study_id']+KEY+[self.metric,self.binary]);r=r[r[self.metric].notna()]
  cells=self.a[KEY].drop_duplicates().reset_index(drop=True);cells['cell']=np.arange(len(cells));self.a=self.a.merge(cells,on=KEY,validate='many_to_one').sort_values('af_row').reset_index(drop=True)
  self.r=r.merge(cells,on=KEY,how='inner',validate='many_to_one');self.ids=pd.Index(sorted(set(self.a.study_id)|set(self.r.study_id)));self.k=keys(self.ids);self.ai=self.ids.get_indexer(self.a.study_id);self.ri=self.ids.get_indexer(self.r.study_id);self.ci=self.a.cell.to_numpy(int)
  quality=pd.read_parquet(D/'study_roster_quality.parquet',columns=['study_id','n_institutions']).set_index('study_id').n_institutions
  self.r['m_all']=self.r.study_id.map(quality);self.matrices={}
  for name,mask in [('default',np.ones(len(self.r),bool)),('no_large',self.r.m_all.between(1,20).to_numpy())]:
   rr=self.r[mask];idx=self.ri[mask];shape=(len(cells),len(self.ids));C=csr_matrix((np.ones(len(rr)),(rr.cell,idx)),shape=shape)
   Y=csr_matrix((rr[self.metric].to_numpy(float),(rr.cell,idx)),shape=shape);Yb=csr_matrix((rr[self.binary].to_numpy(float),(rr.cell,idx)),shape=shape);self.matrices[name]=(C,Y,Yb,mask,C.sum(axis=1).A1>0)
  self.point={name:self.calculate(np.ones((len(self.ids),1)),name) for name in self.matrices}
  require(np.allclose(self.point['default'][1][:,0],self.a[self.metric]-self.a['ref_'+self.metric],atol=1e-8),'Control reconstruction mismatch: '+outcome)
 def calculate(self,w,reference):
  C,Y,Yb,_,valid=self.matrices[reference];den=C@w;den=np.where(den>0,den,np.nan);ref=(Y@w)/den;refb=(Yb@w)/den
  return w[self.ai],self.a[self.metric].to_numpy(float)[:,None]-ref[self.ci],100*(self.a[self.binary].to_numpy(float)[:,None]-refb[self.ci]),ref[self.ci]
 def control_count(self,frame,group,reference='default'):
  cells=set(frame.loc[frame.group.eq(group),'cell']);r=self.r[self.r.cell.isin(cells)&self.matrices[reference][3]];return r.study_id.nunique()
def context(bundle,frame,name,kind,reference='default'):
 keep=KEY+['study_id','work_id','country','group','parent_field','V_i','af_row','cell',bundle.metric,bundle.binary,'x_log','partner_mean_percentile','coverage','n_other_institutions','n_scored_partners','n_outside_boundary','n_unknown_baseline','m_all','network_id','focal_in_roster','observed_author_roster_covered','single_institution']
 frame=frame[list(dict.fromkeys(keep))].copy()
 if kind=='own':frame=frame[frame.x_log.notna()&frame.focal_in_roster].copy();predictor='x_log'
 elif kind=='partner':frame=frame[frame.partner_mean_percentile.notna()&frame.focal_in_roster].copy();predictor='partner_mean_percentile'
 else:frame=frame[frame.single_institution].copy();predictor='x_log'
 frame=frame[bundle.matrices[reference][4][frame.cell.to_numpy(int)]].sort_values('af_row').reset_index(drop=True)
 ids=pd.Index(sorted(frame.institution_id.unique()));code=ids.get_indexer(frame.institution_id);A=csr_matrix((np.ones(len(frame)),(code,np.arange(len(frame)))),shape=(len(ids),len(frame)))
 meta=frame.groupby('institution_id').agg(group=('group','first'),country=('country','first'),n_AF=('study_id','nunique')).reindex(ids);meta.index.name='institution_id';meta=meta.reset_index()
 rec={'name':name,'kind':kind,'reference':reference,'frame':frame,'ids':ids,'code':code,'A':A,'meta':meta,'predictor':predictor,'idx':frame.af_row.to_numpy(int),'draws':{g:[] for g in ['L','M','H']},'binary_draws':{g:[] for g in ['L','M','H']},'eligibility':{}}
 if len(frame):
  aw,y,yb,ref=bundle.point[reference];point=aggregate(rec,aw,y,yb,ref);rec['point']=point
  for group in ['L','M','H']:
   block=frame[frame.group.eq(group)];gate=m0_eligibility(block,predictor) if len(block) else {'estimable':False,'reason':'no_support','n_institutions':0,'n_AF_unique':0};rec['eligibility'][group]=gate
  point.to_parquet(D/('network_points_'+bundle.outcome+'_'+name+'.parquet'),index=False);frame.to_parquet(D/('network_records_'+bundle.outcome+'_'+name+'.parquet'),index=False)
 else:rec['point']=pd.DataFrame();rec['eligibility']={g:{'estimable':False,'reason':'no_support','n_institutions':0,'n_AF_unique':0} for g in ['L','M','H']}
 return rec
def aggregate(ctx,aw,y,yb,ref,rep=0):
 idx=ctx['idx'];A=ctx['A'];w=aw[idx];den=A@w
 di=(A@(w*y[idx]))/den;bi=(A@(w*yb[idx]))/den
 x=ctx['frame'][ctx['predictor']].to_numpy(float);xi=(A@(w*x[:,None]))/den
 if rep is None:return di,bi,xi
 point=ctx['meta'].copy();point['D_i']=di[:,rep];point['D_binary_pp']=bi[:,rep];point['x']=xi[:,rep]
 point['AF_mean']=(A@(w*(y[idx]+ref[idx]))/den)[:,rep];point['REF_mean']=(A@(w*ref[idx])/den)[:,rep];point['kind']=ctx['kind'];point['sample_id']=ctx['name'];return point
def m0_values(x,y,scale):
 x=x/scale;center=x-x.mean(axis=0);den=(center*center).sum(axis=0);slope=(center*(y-y.mean(axis=0))).sum(axis=0)/den;intercept=y.mean(axis=0)-slope*x.mean(axis=0);return np.c_[intercept,slope]
def prepare_contexts(bundle):
 a=bundle.a;institution=pd.read_parquet(I/'institutions.parquet')[['institution_id','V_i']];a=a.merge(institution,on='institution_id',validate='many_to_one');contexts=[];base=None
 for variant in ['degree','strength','expanded','network_no_large','observed_covered_network','rolling']:
  scores=pd.read_parquet(D/('partners_'+variant+'.parquet')).drop(columns=['year','country','group']);f=a.merge(scores,on=['study_id','institution_id'],validate='one_to_one')
  if variant=='degree':base=f
  contexts += [context(bundle,f,variant+'_own','own'),context(bundle,f,variant+'_partner','partner')]
  if variant=='network_no_large':contexts +=[context(bundle,f[f.m_all.between(1,20)],'both_no_large_own','own','no_large'),context(bundle,f[f.m_all.between(1,20)],'both_no_large_partner','partner','no_large')]
 contexts +=[context(bundle,base,'single_institution','single'),context(bundle,base[base.m_all.between(1,20)],'outcomes_no_large_own','own','no_large'),context(bundle,base[base.m_all.between(1,20)],'outcomes_no_large_partner','partner','no_large')]
 for name,col,mask in [('partial_any','partial_partner_mean_percentile',base.coverage.gt(0)),('partial80','partial_partner_mean_percentile',base.coverage.ge(.8)),('partner_max','partner_max_percentile',base.partner_mean_percentile.notna())]:
  z=base[mask&base.observed_author_roster_covered].copy();z['partner_mean_percentile']=z[col];contexts.append(context(bundle,z,name,'partner'))
 # Pure definition comparisons on fixed identical AF/control support.
 for other in list(contexts):
  if other['kind'] not in ['own','partner'] or other['name'].startswith(('degree','partial','partner_max','single')):continue
  original=next(v for v in contexts if v['name']=='degree_'+other['kind']);common_ids=set(other['frame'].af_row)&set(original['frame'].af_row)
  contexts.append(context(bundle,original['frame'][original['frame'].af_row.isin(common_ids)].copy(),other['name']+'_fixed_base',other['kind'],other['reference']))
  contexts.append(context(bundle,other['frame'][other['frame'].af_row.isin(common_ids)].copy(),other['name']+'_fixed_alt',other['kind'],other['reference']))
 return contexts,base
def prepare_models(bundle,contexts):
 core=next(x for x in contexts if x['name']=='degree_own')['frame'];partner=next(x for x in contexts if x['name']=='degree_partner')['frame'];models=[]
 for name,z,ispartner in [('M1',core,False),('M1_partner_sample',partner,False),('M2',partner,True)]:
  z=z[z.x_log.notna()&z.parent_field.notna()&z.country.notna()&z.V_i.notna()].copy().sort_values('af_row').reset_index(drop=True)
  X,names,coding=design(z,ispartner);ids=pd.Index(sorted(z.institution_id.unique()));codes=ids.get_indexer(z.institution_id);w=1/z.groupby('institution_id').study_id.transform('size').to_numpy(float);idx=z.af_row.to_numpy(int);y=bundle.point['default'][1][idx,0]
  diag,beta,h=diagnose(X,w,y,z.institution_id.nunique(),z.study_id.nunique());model={'name':name,'z':z,'idx':idx,'X':X,'names':names,'coding':coding,'inst_codes':codes,'n_inst':len(ids),'point':beta,'diagnostic':diag,'draws':[],'reference':'default'}
  if diag['estimable']:
   residual=z[['study_id','institution_id','country','group','year','x_log','partner_mean_percentile']].copy();residual['observed_difference']=y;residual['fitted_difference']=X@beta;residual['residual']=y-X@beta;residual['leverage']=h;residual['institution_normalized_weight']=w;residual['high_leverage']=h>2*diag['matrix_rank']/len(z);residual.to_parquet(D/('model_diagnostics_'+bundle.outcome+'_'+name+'.parquet'),index=False)
  models.append(model)
  dump(Q/('design_'+bundle.outcome+'_'+name+'.json'),{'model':name,'formula':'D_ip ~ group*log_degree + log_baseline_output + country + year + parent_field + document_type'+(' + partner_mean_percentile/10' if ispartner else ''),'columns':names,'coding':coding,**diag})
 # Prespecified high-leverage diagnostic, with the same complete formula.
 original=models[0]
 if original['diagnostic']['estimable']:
  keep=pd.read_parquet(D/('model_diagnostics_'+bundle.outcome+'_M1.parquet')).high_leverage.to_numpy()
  z=original['z'].loc[~keep].copy().reset_index(drop=True);X,names,coding=design(z,False);codes=pd.factorize(z.institution_id,sort=True)[0];w=1/z.groupby('institution_id').study_id.transform('size').to_numpy(float);idx=z.af_row.to_numpy(int);diag,beta,_=diagnose(X,w,bundle.point['default'][1][idx,0],z.institution_id.nunique(),z.study_id.nunique())
  models.append({'name':'M1_without_high_leverage','z':z,'idx':idx,'X':X,'names':names,'coding':coding,'inst_codes':codes,'n_inst':z.institution_id.nunique(),'point':beta,'diagnostic':diag,'draws':[],'reference':'default'})
 return models
def execute(outcome):
 marker=Q/('network_models_'+outcome+'.json')
 if marker.exists():return
 bundle=Bundle(outcome);contexts,base=prepare_contexts(bundle);models=prepare_models(bundle,contexts)
 require(models[1]['z'][['study_id','institution_id']].equals(models[2]['z'][['study_id','institution_id']]),'M1/M2 partner support differs')
 for start in range(0,B,16):
  n=min(16,B-start);w=weights_from_keys(bundle.k,start,n);calculated={ref:bundle.calculate(w,ref) for ref in ['default','no_large']}
  for ctx in contexts:
   if not len(ctx['frame']) or ctx['kind']=='single':continue
   aw,y,yb,refs=calculated[ctx['reference']];di,bi,xi=aggregate(ctx,aw,y,yb,refs,rep=None)
   for group in ['L','M','H']:
    if not ctx['eligibility'][group]['estimable']:continue
    mask=ctx['meta'].group.eq(group).to_numpy();scale=10 if ctx['kind']=='partner' else 1
    ctx['draws'][group].append(m0_values(xi[mask],di[mask],scale));ctx['binary_draws'][group].append(m0_values(xi[mask],bi[mask],scale))
  aw,y,_,_=calculated['default']
  for model in models:
   if not model['diagnostic']['estimable']:continue
   idx=model['idx'];code=model['inst_codes'];values=[]
   for j in range(n):
    total=np.bincount(code,weights=aw[idx,j],minlength=model['n_inst']);ww=aw[idx,j]/total[code]
    try:beta,_=fit(model['X'],ww,y[idx,j]);values.append(beta)
    except (np.linalg.LinAlgError,ValueError):values.append(np.full(len(model['names']),np.nan))
   model['draws'].append(np.asarray(values))
  if start%400==0:print('Network joint bootstrap',outcome,start,'/',B,'contexts',len(contexts),'adjusted models',sum(m['diagnostic']['estimable'] for m in models),flush=True)
 rows=[];support=[];loco=[];drawdir=D/'model_draws';drawdir.mkdir(exist_ok=True)
 for ctx in contexts:
  point=ctx['point']
  for group in ['L','M','H']:
   gate=ctx['eligibility'][group];support.append(dict(outcome=outcome,sample_id=ctx['name'],kind=ctx['kind'],group=group,**gate))
   z=ctx['frame'][ctx['frame'].group.eq(group)];pt=point[point.group.eq(group)] if len(point) else pd.DataFrame();common=dict(outcome=outcome,sample_id=ctx['name'],group=group,n_institutions=z.institution_id.nunique(),n_AF_unique=z.study_id.nunique(),n_links=len(z),n_countries=z.country.nunique(),n_controls_unique=bundle.control_count(z,group,ctx['reference']),network_id=','.join(sorted(z.network_id.unique())),reference_variant=ctx['reference'])
   if ctx['kind']=='single':
    rows.append(dict(**common,model_id='single_institution_descriptive',coefficient='mean_difference',estimate=pt.D_i.mean() if len(pt) else np.nan,lower=np.nan,upper=np.nan,successful_replicates=0,status='completed_point_only' if len(pt) else 'not_estimable',unit='percentile_points'));continue
   for metric,col,store in [(bundle.metric,'D_i','draws'),(bundle.binary,'D_binary_pp','binary_draws')]:
    values=np.concatenate(ctx[store][group]) if ctx[store][group] else np.empty((0,2));scale=10 if ctx['kind']=='partner' else 1
    est=m0_values(pt.x.to_numpy(float)[:,None],pt[col].to_numpy(float)[:,None],scale)[0] if gate['estimable'] else [np.nan,np.nan];good=np.isfinite(values).all(axis=1) if len(values) else np.array([],bool)
    if len(values):np.savez_compressed(drawdir/(outcome+'_'+ctx['name']+'_'+group+'_'+metric+'.npz'),values=values,columns=['intercept','slope'])
    for k,coefficient in enumerate(['intercept','slope']):
     ci=np.quantile(values[good,k],[.025,.975]) if good.sum()>=.95*B else [np.nan,np.nan]
     rows.append(dict(**common,metric=metric,model_id='M0_'+ctx['kind'],coefficient=coefficient,estimate=est[k],lower=ci[0],upper=ci[1],successful_replicates=int(good.sum()),interval_type='conditional_fixed_network_shared_study_Exp1_5000',status='completed' if good.sum()>=.95*B else 'not_estimable',reason=gate['reason'],unit=('percentage_points' if col=='D_binary_pp' else 'percentile_points')+('_per_10_partner_percentile' if ctx['kind']=='partner' else '_per_log1p_network_measure') if k else 'intercept'))
   if ctx['name'] in ['degree_own','degree_partner'] and gate['estimable']:
    for country in sorted(pt.country.unique()):
     block=pt[pt.country.ne(country)];valid=len(block)>=10 and block.x.nunique()>=3;coef=m0_values(block.x.to_numpy(float)[:,None],block.D_i.to_numpy(float)[:,None],10 if ctx['kind']=='partner' else 1)[0,1] if valid else np.nan
     loco.append(dict(outcome=outcome,sample_id=ctx['name'],group=group,omitted_country=country,n_institutions=len(block),slope=coef,status='point_only' if valid else 'not_estimable',network_fixed=True))
 for model in models:
  z=model['z'];diag=model['diagnostic'];values=np.concatenate(model['draws']) if model['draws'] else np.empty((0,len(model['names'])));good=np.isfinite(values).all(axis=1) if len(values) else np.array([],bool)
  if len(values):np.savez_compressed(drawdir/(outcome+'_'+model['name']+'.npz'),values=values,columns=model['names'])
  for k,name in enumerate(model['names']):
   ci=np.quantile(values[good,k],[.025,.975]) if good.sum()>=.95*B else [np.nan,np.nan]
   rows.append(dict(outcome=outcome,sample_id=model['name'],model_id=model['name'],group='all_supported',coefficient=name,metric=bundle.metric,estimate=model['point'][k] if model['point'] is not None else np.nan,lower=ci[0],upper=ci[1],n_institutions=z.institution_id.nunique(),n_AF_unique=z.study_id.nunique(),n_links=len(z),n_countries=z.country.nunique(),matrix_rank=diag['matrix_rank'],df_resid=diag['df_resid'],nominal_df_resid=diag['nominal_df_resid'],successful_replicates=int(good.sum()),status='completed' if good.sum()>=.95*B else 'not_estimable',reason='' if diag['estimable'] else 'rank_or_effective_df_failure',scale='per_10_partner_percentile' if name=='partner_per10' else 'per_log1p_degree' if 'degree' in name else 'model_coefficient',formula='D_ip ~ group*log_degree + log_baseline_output + country_FE + year_FE + parent_field_FE + type_FE'+(' + P_ip/10' if model['name']=='M2' else ''),interval_type='conditional_fixed_network_shared_study_Exp1_5000'))
 table('network_results_'+outcome,pd.DataFrame(rows));table('network_support_'+outcome,pd.DataFrame(support));table('network_loco_'+outcome,pd.DataFrame(loco))
 dump(marker,{'status':'executed_with_estimability_gates','outcome':outcome,'draws':B,'seed':SEED,'contexts':len(contexts),'adjusted_models':[{k:v for k,v in m.items() if k in ['name','diagnostic','coding']} for m in models],'M1_M2_same_partner_records':True,'publisher_roster_complete':False,'study_weights_shared_across_outcomes_and_all_models':True})
 print('NETWORK ASSOCIATION COMPLETE',outcome,len(rows),'rows',flush=True)
def main():
 for outcome in ['journal','citation']:execute(outcome)
 table('T_SI9_network_models',pd.concat([pd.read_csv(T/('network_results_'+x+'.csv')) for x in ['journal','citation']],ignore_index=True))
if __name__=='__main__':main()
