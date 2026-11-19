"""Prespecified model matrices and sparse weighted normal equations, no ridge."""
from scipy.sparse import csr_matrix,hstack
from scipy.linalg import cho_factor,cho_solve
from common import *
def design(frame,partner=False,exploratory=False):
 z=frame;groups=[g for g in ['L','M','H'] if g in set(z.group)];columns={'intercept':np.ones(len(z)),'log_degree':z.x_log.to_numpy(float),'log_baseline_output':np.log1p(z.V_i.to_numpy(float))};references={}
 for group in groups[1:]:columns['group_'+group]=z.group.eq(group).to_numpy(float);columns['group_'+group+':log_degree']=z.group.eq(group).to_numpy(float)*z.x_log.to_numpy(float)
 for field in ['country','year','parent_field','work_type']:
  levels=sorted(z[field].dropna().astype(str).unique());references[field]=levels[0] if levels else None
  for level in levels[1:]:columns[field+'='+level]=z[field].astype(str).eq(level).to_numpy(float)
 if partner:columns['partner_per10']=z.partner_mean_percentile.to_numpy(float)/10
 if exploratory:
  columns['log_team_institutions']=np.log1p(z.m_all.to_numpy(float));columns['international']=z.international.astype(float).to_numpy()
 names=list(columns);X=csr_matrix(np.column_stack(list(columns.values())));return X,names,{'group_reference':groups[0] if groups else None,'category_references':references,'present_groups':groups}
def fit(X,w,y):
 A=(X.T@X.multiply(w[:,None])).toarray();rhs=np.asarray(X.T@(w*y)).ravel()
 factor=cho_factor(A,check_finite=False);beta=cho_solve(factor,rhs,check_finite=False)
 if not np.isfinite(beta).all():raise np.linalg.LinAlgError('Nonfinite coefficient')
 return beta,A
def diagnose(X,w,y,ninst,nstudies):
 A=(X.T@X.multiply(w[:,None])).toarray();rank=int(np.linalg.matrix_rank(A));df=min(ninst,nstudies)-rank
 condition=float(np.linalg.cond(A));record={'matrix_rank':rank,'n_columns':X.shape[1],'nominal_df_resid':X.shape[0]-rank,'df_resid':df,'condition_number':condition if np.isfinite(condition) else None,'estimable':rank==X.shape[1] and df>=30}
 if record['estimable']:
  beta,_=fit(X,w,y);inv=np.linalg.inv(A);h=w*np.asarray(X.multiply(X@inv).sum(axis=1)).ravel();record['max_leverage']=float(h.max());record['high_leverage_n']=int((h>2*rank/len(w)).sum());record['residual_weighted_RMSE']=float(np.sqrt(np.average((y-X@beta)**2,weights=w)))
  return record,beta,h
 return record,None,np.full(len(w),np.nan)
def m0_eligibility(frame,xcol='x_log'):
 z=frame;inst=z.groupby('institution_id').agg(x=(xcol,'mean'),country=('country','first'));x=inst.x.to_numpy(float)
 unique_studies=z.study_id.nunique();largest=z.groupby('study_id').institution_id.nunique().max()/len(inst) if len(inst) else np.nan
 centered=x-x.mean() if len(x) else x;sxx=float(centered@centered);leverage=1/len(x)+centered**2/sxx if len(x) and sxx>0 else np.array([np.inf])
 reasons=[]
 if len(inst)<10:reasons.append('fewer_than_10_institutions')
 if len(np.unique(np.round(x,12)))<3:reasons.append('fewer_than_3_distinct_x')
 if unique_studies<10:reasons.append('fewer_than_10_unique_AF_studies')
 if sxx<=1e-12:reasons.append('no_x_variation')
 if largest>.5:reasons.append('single_study_involves_over_half_institutions')
 if leverage.max()>.5:reasons.append('max_institution_leverage_over_half')
 return {'estimable':not reasons,'reason':';'.join(reasons),'n_institutions':len(inst),'n_AF_unique':unique_studies,'distinct_x':len(np.unique(x)),'x_min':float(x.min()) if len(x) else None,'x_max':float(x.max()) if len(x) else None,'max_study_institution_share':float(largest) if len(inst) else None,'max_country_institution_share':float(inst.country.value_counts().max()/len(inst)) if len(inst) else None,'max_leverage':float(leverage.max()) if np.isfinite(leverage.max()) else None}
