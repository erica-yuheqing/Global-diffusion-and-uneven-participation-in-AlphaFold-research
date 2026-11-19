"""Initial-mode adjusted probabilities with explicit estimation/inference gates."""
import sys
import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.optimize import minimize
from support import *

def design(d,quadratic=False):
    vals=[np.ones(len(d)),d.present.to_numpy(dtype=float),np.log1p(d.baseline_papers.to_numpy())]
    names=['Intercept','Initial activity present','log1p baseline papers']
    if quadratic:vals.append(vals[2]**2);names.append('log1p baseline papers squared')
    for col in ['baseline_country_model','entry_year','baseline_subfield_model']:
        for level in sorted(d[col].astype(str).unique())[1:]:
            vals.append(d[col].astype(str).eq(level).to_numpy(dtype=float));names.append(col+'='+str(level))
    raw=np.column_stack(vals)
    keep=[]
    # Deterministic rank screen, never outcome-based variable selection.
    for j in range(raw.shape[1]):
        trial=raw[:,keep+[j]]
        if np.linalg.matrix_rank(trial)>len(keep):keep.append(j)
    x=raw[:,keep];names=[names[j] for j in keep]
    require('Initial activity present' in names,'Initial activity has no comparison group')
    return x,names

def ridge_fit(X,y,penalty=1):
    center=X[:,1:].mean(axis=0);scale=X[:,1:].std(axis=0);require((scale>0).all(),'Constant ridge slope')
    z=np.column_stack([np.ones(len(X)),(X[:,1:]-center)/scale])
    def objective(b):
        eta=z@b;p=expit(eta)
        loss=np.logaddexp(0,eta).sum()-y@eta+penalty*np.sum(b[1:]**2)/2
        grad=z.T@(p-y);grad[1:]+=penalty*b[1:]
        return loss,grad
    start=np.zeros(X.shape[1]);start[0]=np.log((y.mean()+1e-6)/(1-y.mean()+1e-6))
    result=minimize(objective,start,jac=True,method='L-BFGS-B',options={'maxiter':1000,'ftol':1e-12,'gtol':1e-7})
    require(result.success and np.max(np.abs(result.jac))<.01,'Ridge did not converge reliably')
    b=result.x.copy();b[1:]/=scale;b[0]-=np.dot(center,b[1:])
    return b,dict(ridge_lambda=penalty,ridge_iterations=result.nit,gradient_max=float(np.max(np.abs(result.jac))))

def contrasts(X,b,term):
    low=X.copy();high=X.copy();low[:,term]=0;high[:,term]=1
    p0=expit(low@b);p1=expit(high@b)
    g0=np.mean((p0*(1-p0))[:,None]*low,axis=0)
    g1=np.mean((p1*(1-p1))[:,None]*high,axis=0)
    return float(p0.mean()),float(p1.mean()),g0,g1

def run(out):
    sys.path.insert(0,str(UP))
    sys.path.insert(0,str(OLD.parent))
    oldmodel=module('f3_checked_point_solver',OLD.parent/'models.py')
    data=oldcode()
    base=load(out,'institution_analysis_base');initial=load(out,'initial_activity_institution')
    relations=load(out,'af_initial_followup_relations')
    results=[];models=[];coefficients=[];members=[];assess=[]
    for mode in MODES:
        first=initial[initial.activity.eq(mode)]
        for state,g in first.groupby('initial_state'):
            assess.append(dict(activity=mode,initial_state=state,N=len(g),denominator=len(base),percentage=100*len(g)/len(base)))
        d=base.merge(first[['institution_id','initial_state']],on='institution_id',validate='one_to_one')
        d=d[d.initial_state.isin(['present','assessed_absent'])].copy();d['present']=d.initial_state.eq('present')
        for quadratic in [False,True]:
            variant='main_linear_log_scale' if not quadratic else 'quadratic_scale_sensitivity'
            X,names=design(d,quadratic);y=d.sustained.to_numpy(dtype=float);term=names.index('Initial activity present')
            cells=pd.crosstab(d.present,d.sustained).reindex(index=[False,True],columns=[False,True],fill_value=0)
            comp,dep=data.dependency(relations,d.institution_id)
            info=dict(activity=mode,variant=variant,N=len(d),present_N=int(d.present.sum()),absent_N=int((~d.present).sum()),
              events=int(y.sum()),design_columns=X.shape[1],min_initial_type_outcome_cell=int(cells.to_numpy().min()),
              shared_components=dep['components'],largest_component_fraction=dep['largest_fraction'],
              estimator='unpenalized_MLE',status='pending',failure_reason='',CI_status='not_computed')
            try:
                b,diagnostics,p,_=oldmodel.point_fit(X,y)
                info.update(diagnostics)
                info['status']='estimated_MLE'
            except oldmodel.engine().ModelFailure as failure:
                info.update(status='estimated_ridge_exploratory',estimator='ridge_lambda1',failure_reason=failure.reason)
                info.update({'MLE_failure_'+k:v for k,v in failure.diagnostics.items()})
                b,diagnostics=ridge_fit(X,y,1);info.update(diagnostics)
            low,high,g0,g1=contrasts(X,b,term)
            ci_ok=info['estimator']=='unpenalized_MLE' and dep['components']>=30 and dep['largest_fraction']<=.10 and int(cells.to_numpy().min())>=10
            covariance=None
            if info['estimator']=='unpenalized_MLE':
                fitted=expit(X@b);bread=X.T@((fitted*(1-fitted))[:,None]*X)
                condition=np.linalg.cond(bread);info['information_condition']=condition
                if condition<1e12:
                    cluster=comp.set_index('institution_id').loc[d.institution_id,'component_id'].to_numpy()
                    scores=pd.DataFrame((y-fitted)[:,None]*X).assign(component=cluster).groupby('component').sum().to_numpy()
                    inverse=np.linalg.inv(bread);G=len(scores);n,k=X.shape
                    correction=G/(G-1)*(n-1)/(n-k) if G>1 else np.nan
                    covariance=correction*inverse@(scores.T@scores)@inverse
                    ci_ok=ci_ok and np.isfinite(covariance).all() and np.linalg.eigvalsh(covariance).min()>-1e-9
                else:ci_ok=False
            info['CI_status']='released_component_cluster_95CI' if ci_ok else 'withheld_dependency_or_estimation_gate'
            info['adjusted_absent']=low;info['adjusted_present']=high;info['difference_pp']=100*(high-low)
            for comparison,prob,grad in [('assessed_absent',low,g0),('present',high,g1)]:
                ci_low=ci_high=diff_lo=diff_hi=np.nan
                if ci_ok:
                    se=np.sqrt(max(0,float(grad@covariance@grad)))
                    logit=np.log(prob/(1-prob));linkse=se/(prob*(1-prob))
                    ci_low,ci_high=expit(np.array([logit-1.96*linkse,logit+1.96*linkse]))
                    ds=100*np.sqrt(max(0,float((g1-g0)@covariance@(g1-g0))))
                    diff_lo=100*(high-low)-1.96*ds;diff_hi=100*(high-low)+1.96*ds
                results.append(dict(type=mode,variant=variant,comparison=comparison,N=len(d),
                  group_N=int(d.present.eq(comparison=='present').sum()),adjusted_probability=prob,
                  difference_pp=100*(high-low),CI_low=ci_low,CI_high=ci_high,
                  difference_CI_low=diff_lo,difference_CI_high=diff_hi,CI_status=info['CI_status'],estimator=info['estimator']))
            for name,value in zip(names,b):coefficients.append(dict(activity=mode,variant=variant,term=name,beta=value,estimator=info['estimator']))
            for i in d.institution_id:members.append(dict(activity=mode,variant=variant,institution_id=i))
            models.append(info)
            # Penalty sensitivity is defined before fitting and never selected by effect direction.
            if info['estimator']!='unpenalized_MLE' and not quadratic:
                for penalty in [.1,10]:
                    bb,diagnostics=ridge_fit(X,y,penalty);a,c,_,_=contrasts(X,bb,term)
                    models.append(dict(activity=mode,variant=f'ridge_lambda_{penalty}_sensitivity',N=len(d),
                      present_N=int(d.present.sum()),absent_N=int((~d.present).sum()),events=int(y.sum()),
                      status='estimated_ridge_exploratory',estimator=f'ridge_lambda{penalty}',CI_status='withheld_penalized_sensitivity',
                      adjusted_absent=a,adjusted_present=c,difference_pp=100*(c-a),**diagnostics))
    save(out,'panel_c_initial_use',pd.DataFrame(results))
    save(out,'initial_model_diagnostics',pd.DataFrame(models))
    save(out,'initial_model_coefficients',pd.DataFrame(coefficients))
    save(out,'initial_model_membership',pd.DataFrame(members),csv=False)
    save(out,'initial_activity_assessability',pd.DataFrame(assess))
    print('Initial-mode models: four activities × main/nonlinear designs; inference gates and failures retained',flush=True)

if __name__=='__main__':run(OUT)
