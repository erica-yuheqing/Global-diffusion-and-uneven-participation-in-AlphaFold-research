"""Predeclared natural restricted cubic spline binomial model, SciPy/NumPy only."""
from common import *
from scipy.special import expit
from scipy.linalg import solve

def rcs(x,knots):
    x=np.asarray(x,float);t=np.unique(knots);require(len(t)>=2,'Insufficient unique spline knots')
    cols=[x]
    if len(t)>2:
        last,pen=t[-1],t[-2];scale=(last-t[0])**2
        for k in t[:-2]:
            cols.append((np.maximum(x-k,0)**3-np.maximum(x-pen,0)**3*(last-k)/(last-pen)+np.maximum(x-last,0)**3*(pen-k)/(last-pen))/scale)
    return np.column_stack(cols)

def objective(beta,X,y,penalty=0):
    eta=X@beta
    val=np.logaddexp(0,eta).sum()-y@eta+penalty*(beta@beta)/2
    grad=X.T@(expit(eta)-y)+penalty*beta
    return float(val),grad

def fit_newton(X,y,start,penalty=0):
    beta=start.copy();history=[];n=len(y)
    for it in range(100):
        val,g=objective(beta,X,y,penalty);p=expit(X@beta);w=p*(1-p)
        score=float(abs(g).max()/n);history.append({'iteration':it,'negative_loglik_penalized':val,'normalized_score':score,'max_abs_coefficient':float(abs(beta).max())})
        if score<1e-9:return beta,{'converged':True,'iterations':it,'score':score,'history':history}
        h=X.T@(w[:,None]*X)+np.eye(X.shape[1])*penalty
        try:step=solve(h,g,assume_a='pos',check_finite=True)
        except Exception as e:return beta,{'converged':False,'reason':'information_matrix: '+str(e),'history':history}
        alpha=1.
        while alpha>=2**-25:
            trial=beta-alpha*step;nv,_=objective(trial,X,y,penalty)
            if np.isfinite(nv) and nv<=val-1e-4*alpha*(g@step):break
            alpha/=2
        if alpha<2**-25:return beta,{'converged':False,'reason':'line_search','history':history}
        beta=trial
        if abs(beta).max()>40 and penalty==0:return beta,{'converged':False,'reason':'separation_or_extreme_coefficients','history':history}
    return beta,{'converged':False,'reason':'iteration_limit','history':history}

def continuous(out,base):
    b=base.loc[truth(base.eligible_20)].copy();require(len(b)==48010 and b.country.nunique()==68,'Model B2 sample')
    b['percentile']=(b.groupby('country').V_i.rank(method='average')-.5)/b.groupby('country').institution_id.transform('size')
    b['y']=number(b.first_pool_AF_year).le(2025).astype(int)
    knots=np.unique(np.quantile(b.percentile,[.05,.35,.65,.95],method='linear'))
    countries=sorted(b.country.unique());cc=pd.Categorical(b.country,categories=countries).codes
    basis=rcs(b.percentile,knots);mean=basis.mean(0);sd=basis.std(0);require((sd>0).all(),'Degenerate spline basis')
    X=np.column_stack([np.eye(68)[cc],(basis-mean)/sd]);y=b.y.to_numpy(float)
    rank=np.linalg.matrix_rank(X);start=np.zeros(X.shape[1])
    for i,c in enumerate(countries):
        yi=y[cc==i];start[i]=np.log((yi.sum()+.5)/(len(yi)-yi.sum()+.5))
    # This pseudo-count is an optimizer starting value only, not an outcome modification.
    # Independently compare an analytic score component with finite differences before fitting.
    h=1e-5;grad=objective(start,X,y)[1];gradient_errors=[]
    for j in [0,33,67,68,X.shape[1]-1]:
        v=np.zeros_like(start);v[j]=h
        fd=(objective(start+v,X,y)[0]-objective(start-v,X,y)[0])/(2*h)
        gradient_errors.append(abs(fd-grad[j]))
    require(max(gradient_errors)<1e-4,'Binomial score finite difference mismatch')
    primary={'converged':False,'reason':'rank_deficient'}
    if rank==X.shape[1]:beta,primary=fit_newton(X,y,start,0)
    fallback=False;penalty=0
    if not primary['converged']:
        fallback=True;penalty=1e-6;beta,active=fit_newton(X,y,start,penalty)
    else:active=primary
    require(active['converged'],'Continuous model failed primary and predeclared fallback')
    grid=np.linspace(float(b.percentile.min()),float(b.percentile.max()),201)
    sb=(rcs(grid,knots)-mean)/sd
    pred=expit(beta[:68,None]+(sb@beta[68:])[None,:])
    support=b.groupby('country').percentile.agg(['min','max']).reindex(countries)
    n_supported=((grid[None,:]>=support['min'].to_numpy()[:,None])&(grid[None,:]<=support['max'].to_numpy()[:,None])).sum(0)
    model='country_FE_logit_RCS'+('_ridge_1e-6' if fallback else '')
    output=pd.DataFrame({'percentile':grid,'year':2025,'predicted_coverage':pred.mean(0),'weighting':'equal_country_standardized','model':model,'interval_type':'none_descriptive_point_estimates','lower':np.nan,'upper':np.nan,'countries':68,'institutions':48010,'countries_with_observed_percentile_support':n_supported,'any_country_extrapolation':n_supported<68,'source_hash':sha(out/'inputs/frozen/institution_baseline_and_first_participation.csv')})
    save(out,'new_continuous_scale_predictions.csv',output)
    save(out,'new_continuous_country_predictions.csv',pd.DataFrame({'country':np.repeat(countries,len(grid)),'percentile':np.tile(grid,68),'predicted_coverage':pred.ravel(),'year':2025}))
    b['bin']=np.ceil(b.percentile*10).clip(1,10).astype(int)
    bins=b.groupby(['country','bin']).agg(fixed_N=('y','size'),AF_N=('y','sum'),min_V=('V_i','min'),max_V=('V_i','max'),percentile_min=('percentile','min'),percentile_max=('percentile','max')).reindex(pd.MultiIndex.from_product([countries,range(1,11)],names=['country','bin'])).reset_index()
    bins[['fixed_N','AF_N']]=bins[['fixed_N','AF_N']].fillna(0).astype(int);bins['coverage']=bins.AF_N/bins.fixed_N.replace(0,np.nan);bins['empty']=bins.fixed_N.eq(0)
    save(out,'new_continuous_scale_bins.csv',bins)
    summ=bins.groupby('bin').agg(coverage=('coverage','mean'),effective_countries=('coverage','count'),fixed_N=('fixed_N','sum'),AF_N=('AF_N','sum')).reset_index();summ['percentile']=(summ.bin-.5)/10
    summ['target']='mean among countries with nonempty bin; composition may vary';save(out,'new_continuous_bin_summary.csv',summ)
    coef=pd.DataFrame({'term':['country_'+c for c in countries]+['spline_'+str(i+1) for i in range(basis.shape[1])],'coefficient':beta});save(out,'new_continuous_model_coefficients.csv',coef)
    fitted=expit(X@beta)
    dump(out/'quality/continuous_model.json',{'model':model,'knots':knots,'basis_center':mean,'basis_scale':sd,'rank':rank,'columns':X.shape[1],'n':len(y),'positive':y.sum(),'countries':68,'penalty':penalty,'fallback_used':fallback,'primary':primary,'active':active,'gradient_fd_max_abs_error':max(gradient_errors),'Brier_score':np.mean((fitted-y)**2),'probability_range':[fitted.min(),fitted.max()],'coefficient_max_abs':abs(beta).max(),'condition_number':np.linalg.cond(X),'uncertainty':'no_inference_intervals','standardization':'68 countries equally weighted; fitting likelihood one per institution','prediction_support_range':[int(n_supported.min()),int(n_supported.max())]})
    save(out,'new_continuous_institution_design.csv',b[['institution_id','country','V_i','percentile','bin','y']])
    print('Continuous model:',model,'converged;',len(y),'institutions;',int(y.sum()),'observed AF',flush=True)
