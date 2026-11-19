"""Group slope contrasts, country influence, common-x support and new partners."""
from common import *
from model_math import design,diagnose,fit,m0_eligibility
from network_analysis import Bundle,context,aggregate,m0_values
from shared_weights import keys,weights_from_keys
def model_frame(outcome,name):
 kind='degree_partner' if name in ['M1_partner_sample','M2'] else 'degree_own';z=pd.read_parquet(D/f'network_records_{outcome}_{kind}.parquet')
 z=z[z.x_log.notna()&z.parent_field.notna()&z.country.notna()&z.V_i.notna()].sort_values('af_row').reset_index(drop=True)
 if name=='M1_without_high_leverage':
  high=pd.read_parquet(D/f'model_diagnostics_{outcome}_M1.parquet');bad=set(zip(high.loc[high.high_leverage,'study_id'],high.loc[high.high_leverage,'institution_id']));z=z[[(s,i) not in bad for s,i in zip(z.study_id,z.institution_id)]].reset_index(drop=True)
 return z
def slope(beta,names,group,reference):
 if beta is None or 'log_degree' not in names:return np.nan
 result=beta[...,names.index('log_degree')]
 if group!=reference:
  name='group_'+group+':log_degree'
  if name not in names:return np.full_like(result,np.nan)
  result=result+beta[...,names.index(name)]
 return result
def contrasts_and_country(outcome):
 if (T/f'network_adjusted_group_contrasts_{outcome}.csv').exists() and (T/f'network_adjusted_loco_{outcome}.csv').exists():return
 result=pd.read_csv(T/f'network_results_{outcome}.csv');extra=[];country=[];study=[];institutions=[]
 marker=json.loads((Q/f'network_models_{outcome}.json').read_text())
 for model in marker['adjusted_models']:
  name=model['name'];path=D/f'model_draws/{outcome}_{name}.npz';z=model_frame(outcome,name)
  X,names,coding=design(z,name=='M2');ref=coding['group_reference'];pointrows=result[result.model_id.eq(name)].set_index('coefficient');beta=np.array([pointrows.loc[k,'estimate'] for k in names],float)
  values=np.load(path)['values'] if path.exists() else np.empty((0,len(names)));good=np.isfinite(values).all(axis=1) if len(values) else np.array([],bool)
  for group in ['L','M','H']:
   block=z[z.group.eq(group)];gate=m0_eligibility(block) if len(block) else {'estimable':False,'reason':'no_group_support'};point=slope(beta,names,group,ref) if group in coding['present_groups'] else np.nan;v=slope(values[good],names,group,ref) if good.any() and group in coding['present_groups'] else np.array([])
   ci=np.quantile(v,[.025,.975]) if len(v)>=4750 and gate['estimable'] else [np.nan,np.nan]
   extra.append(dict(outcome=outcome,model_id=name,sample_id=name,group=group,coefficient='log_degree_slope',metric='journal_position' if outcome=='journal' else 'percentile_12m',estimate=point,lower=ci[0],upper=ci[1],n_institutions=block.institution_id.nunique(),n_model_institutions=z.institution_id.nunique(),n_AF_unique=block.study_id.nunique(),n_links=len(block),n_countries=block.country.nunique(),matrix_rank=model['diagnostic']['matrix_rank'],df_resid=model['diagnostic']['df_resid'],successful_replicates=int(good.sum()),scale='per_log1p_degree',status='completed' if np.isfinite(ci).all() else 'point_only_group_support_or_fit_failure',reason=gate['reason'],interval_type='conditional_shared_study_linear_coefficient_contrast'))
  # Exact leave-focal-country-out point diagnostics, keeping the network fixed.
  if name not in ['M1','M2'] or not model['diagnostic']['estimable']:continue
  diag=pd.read_parquet(D/f'model_diagnostics_{outcome}_{name}.parquet');yy=z[['study_id','institution_id']].merge(diag[['study_id','institution_id','observed_difference']],on=['study_id','institution_id'],validate='one_to_one').observed_difference.to_numpy(float)
  for omitted in sorted(z.country.unique()):
   keep=z.country.ne(omitted).to_numpy();b=z[keep].reset_index(drop=True);XX,nn,cc=design(b,name=='M2');ww=1/b.groupby('institution_id').study_id.transform('size').to_numpy(float)
   dd,bb,_=diagnose(XX,ww,yy[keep],b.institution_id.nunique(),b.study_id.nunique())
   for group in ['L','M','H']:
    estimate=slope(bb,nn,group,cc['group_reference']) if group in cc['present_groups'] else np.nan
    country.append(dict(outcome=outcome,model_id=name,group=group,omitted_country=omitted,estimate=estimate,n_institutions=b.loc[b.group.eq(group),'institution_id'].nunique(),n_model_institutions=b.institution_id.nunique(),status='point_only' if dd['estimable'] else 'not_estimable',network_fixed=True))
   if name=='M2':country.append(dict(outcome=outcome,model_id=name,group='all_supported',omitted_country=omitted,coefficient='partner_per10',estimate=bb[nn.index('partner_per10')] if bb is not None else np.nan,n_institutions=b.institution_id.nunique(),status='point_only' if dd['estimable'] else 'not_estimable',network_fixed=True))
  diag['weighted_abs_residual']=diag.institution_normalized_weight*diag.residual.abs()
  ss=diag.groupby('study_id').agg(n_focal_institutions=('institution_id','nunique'),n_links=('institution_id','size'),sum_leverage=('leverage','sum'),weighted_abs_residual=('weighted_abs_residual','sum')).reset_index();ss['model_id']=name;ss['outcome']=outcome;study.append(ss)
  ii=diag.groupby('institution_id').agg(n_AF=('study_id','nunique'),country=('country','first'),group=('group','first'),max_leverage=('leverage','max'),high_leverage_rows=('high_leverage','sum'),weighted_abs_residual=('weighted_abs_residual','sum')).reset_index();ii['model_id']=name;ii['outcome']=outcome;institutions.append(ii)
 table('network_adjusted_group_contrasts_'+outcome,pd.DataFrame(extra));table('network_adjusted_loco_'+outcome,pd.DataFrame(country));table('network_study_influence_'+outcome,pd.concat(study,ignore_index=True) if study else pd.DataFrame());table('network_institution_influence_'+outcome,pd.concat(institutions,ignore_index=True) if institutions else pd.DataFrame())
def overlap_and_new(outcome):
 target=T/f'network_overlap_{outcome}.csv'
 if target.exists() and (D/f'network_old_new_institutions_{outcome}.parquet').exists():return
 bundle=Bundle(outcome)
 if not target.exists():
  contexts=[];support=[]
  for kind in ['own','partner']:
   frame=pd.read_parquet(D/f'network_records_{outcome}_degree_{kind}.parquet');point=pd.read_parquet(D/f'network_points_{outcome}_degree_{kind}.parquet');spans=point.groupby('group').x.agg(['min','max'])
   lo=spans['min'].max() if len(spans)==3 else np.nan;hi=spans['max'].min() if len(spans)==3 else np.nan
   keep=point.loc[point.x.between(lo,hi),'institution_id'] if np.isfinite(lo) and np.isfinite(hi) and hi>lo else []
   ctx=context(bundle,frame[frame.institution_id.isin(keep)],'common_x_overlap_'+kind,kind);contexts.append(ctx)
   for group in ['L','M','H']:support.append(dict(outcome=outcome,kind=kind,group=group,overlap_low=lo,overlap_high=hi,institutions_before=point.loc[point.group.eq(group),'institution_id'].nunique(),institutions_after=ctx['frame'].loc[ctx['frame'].group.eq(group),'institution_id'].nunique(),status='observed_overlap' if len(keep) else 'no_three_group_overlap'))
  for start in range(0,B,16):
   n=min(16,B-start);w=weights_from_keys(bundle.k,start,n);aw,y,yb,ref=bundle.calculate(w,'default')
   for ctx in contexts:
    if not len(ctx['frame']):continue
    di,_,xi=aggregate(ctx,aw,y,yb,ref,rep=None)
    for group in ['L','M','H']:
     if not ctx['eligibility'][group]['estimable']:continue
     mask=ctx['meta'].group.eq(group).to_numpy();ctx['draws'][group].append(m0_values(xi[mask],di[mask],10 if ctx['kind']=='partner' else 1))
  rows=[]
  for ctx in contexts:
   for group in ['L','M','H']:
    pt=ctx['point'];pt=pt[pt.group.eq(group)] if len(pt) else pt;gate=ctx['eligibility'][group];values=np.concatenate(ctx['draws'][group]) if ctx['draws'][group] else np.empty((0,2));good=np.isfinite(values).all(axis=1) if len(values) else np.array([],bool);estimate=m0_values(pt.x.to_numpy(float)[:,None],pt.D_i.to_numpy(float)[:,None],10 if ctx['kind']=='partner' else 1)[0,1] if gate['estimable'] else np.nan;ci=np.quantile(values[good,1],[.025,.975]) if good.sum()>=4750 else [np.nan,np.nan]
    rows.append(dict(outcome=outcome,sample_id=ctx['name'],group=group,estimate=estimate,lower=ci[0],upper=ci[1],n_institutions=len(pt),successful_replicates=int(good.sum()),status='completed' if good.sum()>=4750 else 'not_estimable',reason=gate['reason']))
  table('network_overlap_'+outcome,pd.DataFrame(rows));table('network_overlap_support_'+outcome,pd.DataFrame(support))
 # Optional historical connection context: point-only, actual observed edges.
 c=con();view(c,'pairs',D/'partner_contributions_main.parquet');c.execute('CREATE TEMP TABLE history_context AS SELECT study_id,institution_id,sum(observed_baseline_connection::INT) old_n,count(*)-sum(observed_baseline_connection::INT) new_n FROM pairs GROUP BY 1,2')
 primary=pd.read_parquet(D/f'network_records_{outcome}_degree_partner.parquet');c.register('primary_records',primary)
 z=c.execute('SELECT p.*,h.old_n,h.new_n FROM primary_records p JOIN history_context h USING(study_id,institution_id)').df();z['history_context']=np.select([z.new_n.eq(0),z.old_n.eq(0)],['all_previously_observed','all_not_previously_observed'],default='mixed_observed_connections')
 z['difference']=bundle.point['default'][1][z.af_row.to_numpy(int),0];inst=z.groupby(['institution_id','group','history_context']).agg(D_i=('difference','mean'),AF_studies=('study_id','nunique')).reset_index();table('network_old_new_context_'+outcome,inst.groupby(['group','history_context']).agg(institutions=('institution_id','nunique'),mean_difference=('D_i','mean'),median_difference=('D_i','median'),AF_links=('AF_studies','sum')).reset_index());inst.to_parquet(D/f'network_old_new_institutions_{outcome}.parquet',index=False)
def main():
 for outcome in ['journal','citation']:contrasts_and_country(outcome);overlap_and_new(outcome)
 tables=[pd.read_csv(T/'T_SI9_network_models.csv')]+[pd.read_csv(T/f'network_adjusted_group_contrasts_{outcome}.csv') for outcome in ['journal','citation']]
 out=pd.concat(tables,ignore_index=True).drop_duplicates(['outcome','model_id','sample_id','group','coefficient','metric'],keep='last');table('T_SI9_network_models',out)
 dump(Q/'network_diagnostics_audit.json',{'group_slopes':'linear contrasts from same model coefficient draws','M1_M2_same_support':True,'country_leave_one':'exact point refits; fixed network, no bootstrap CI claimed','study_institution_influence':'leverage, observed shared-paper count, weighted residual diagnostics; not a full deletion jackknife','overlap':'same institutions within observed all-group x intersection; no extrapolation','new_old_partners':'historical observed edges only, descriptive point estimates'})
 print('GROUP CONTRASTS, OVERLAP, COUNTRY AND SHARED-STUDY DIAGNOSTICS COMPLETE',flush=True)
if __name__=='__main__':main()
