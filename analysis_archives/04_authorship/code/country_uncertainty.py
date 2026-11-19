"""Complete country-pair joint O/E bootstrap, fixed support, without dense study grids."""
from common import *
from scipy import sparse
from bootstrap import compression
def interval_columns(x):
    finite=np.isfinite(x);valid=finite.sum(axis=0);low,high=np.nanquantile(x,[.025,.975],axis=0);deg=np.nanmax(x,axis=0)-np.nanmin(x,axis=0)<1e-14;ok=(valid>=.95*B)&~deg
    return np.where(ok,low,np.nan),np.where(ok,high,np.nan),valid,deg
def main():
    marker=ROOT/'provenance/country_pair_bootstrap_complete.json'
    if marker.exists():print('Retain committed country-pair ranges');return
    m=norm('analysis_members.parquet');c=connect();c.register('m',m[['study_id','row_index']]);d=ROOT/'inputs/normalized'
    for name in ['country_pair_credit','country_pair_expected']:c.execute(f'CREATE VIEW {name} AS SELECT z.*,m.row_index FROM read_parquet({q(d/(name+".parquet"))}) z JOIN m USING(study_id)')
    pairs=c.execute('''SELECT first_country,last_country FROM country_pair_expected UNION SELECT first_country,last_country FROM country_pair_credit ORDER BY 1,2''').df();pairs['pair_index']=np.arange(len(pairs));c.register('pairs',pairs);rr=[];cc=[];vv=[];K=len(pairs)
    for k,name in enumerate(['country_pair_credit','country_pair_expected']):
      z=c.execute(f'SELECT z.row_index,p.pair_index,z.credit FROM {name} z JOIN pairs p USING(first_country,last_country)').df();rr.append(z.row_index.to_numpy());cc.append(z.pair_index.to_numpy()+K*k);vv.append(z.credit.to_numpy())
    Y=sparse.coo_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(len(m),2*K)).tocsr();Y.sum_duplicates();Y.eliminate_zeros();Y.sort_indices();c.close();del z,rr,cc,vv
    require(np.allclose(np.asarray(Y[:,:K].sum(axis=1)).ravel(),1) and np.allclose(np.asarray(Y[:,K:].sum(axis=1)).ravel(),1),'Country-pair input mass')
    sparse.save_npz(d/'country_pair_feature_matrix.npz',Y);pairs.to_parquet(d/'country_pair_index.parquet',index=False);g,A=compression(m,Y,'country_pair_all_cells');seed=SEED+90090;maps={};points={}
    for k,cp in enumerate(CORPORA):
      gi=np.flatnonzero(g.corpus.eq(cp));h=g.iloc[gi].reset_index(drop=True);Z=A[gi].tocsr();counts=h.n.to_numpy('int64');strata=list(h.groupby(KEY,sort=True,dropna=False).indices.values());rng=np.random.default_rng(np.random.SeedSequence([seed,k]));factors={'raw_full':np.ones(len(h)),'standardized':h.weight.to_numpy(float)}
      for setting,f in factors.items():
        p=np.asarray(Z.T@(counts*f)).ravel();points[setting,cp]=p/np.r_[np.full(K,p[:K].sum()),np.full(K,p[K:].sum())];maps[setting,cp]=np.lib.format.open_memmap(ROOT/'scratch'/f'country_draws_{cp}_{setting}.npy',mode='w+',dtype='float64',shape=(B,2*K))
      for start in range(0,B,25):
        n=min(25,B-start);w=np.empty((len(h),n))
        for idx in strata:w[idx]=rng.multinomial(int(counts[idx].sum()),counts[idx]/counts[idx].sum(),size=n).T
        for setting,f in factors.items():
          v=np.asarray(Z.T@(w*f[:,None])).T;v[:,:K]/=v[:,:K].sum(axis=1,keepdims=True);v[:,K:]/=v[:,K:].sum(axis=1,keepdims=True);maps[setting,cp][start:start+n]=v
        if (start+n)%500==0:print('All-country-pair joint bootstrap',cp,start+n,'/',B,flush=True)
      for setting in factors:maps[setting,cp].flush()
    # Summarize cell chunks so interval calculation has a bounded memory footprint.
    out=[]
    for setting in ['raw_full','standardized']:
      for start in range(0,K,256):
        end=min(start+256,K);key=pairs.iloc[start:end][['first_country','last_country']];dev={}
        for cp in CORPORA:
          a=np.asarray(maps[setting,cp][:,start:end]);e=np.asarray(maps[setting,cp][:,K+start:K+end]);v=100*(a-e);dev[cp]=v;ps=points[setting,cp];z=key.copy();z['setting']=setting;z['corpus']=cp
          for stem,xx in [('observed',a),('expected',e),('deviation',v)]:
            lo,hi,valid,deg=interval_columns(xx);z[stem+'_ci_low']=lo;z[stem+'_ci_high']=hi;z[stem+'_valid_replicates']=valid;z[stem+'_degenerate']=deg
          z['bootstrap_seed']=seed;out.append(z)
        z=key.copy();z['setting']=setting;z['corpus']='AF_minus_reference';lo,hi,valid,deg=interval_columns(dev['AF']-dev['reference']);z['deviation_ci_low']=lo;z['deviation_ci_high']=hi;z['deviation_valid_replicates']=valid;z['deviation_degenerate']=deg;z['bootstrap_seed']=seed;out.append(z)
    ci=pd.concat(out,ignore_index=True);base=pd.read_parquet(ROOT/'tables/full_country_pair_matrices.parquet');base=base.drop(columns=['cell_interval_status'],errors='ignore');base=base.merge(ci,on=['setting','corpus','first_country','last_country'],how='left',validate='one_to_one')
    # Cells absent from every observed team have structural zero O/E under this
    # conditional universe. Their point is 0; a degenerate range is not printed as CI.
    absent=base.bootstrap_seed.isna();base['bootstrap_seed']=base.bootstrap_seed.fillna(seed).astype('int64')
    for stem in ['observed','expected','deviation']:
      valid=stem+'_valid_replicates';deg=stem+'_degenerate';mask=absent & (base.corpus.ne('AF_minus_reference') if stem!='deviation' else True);base.loc[mask,valid]=B;base.loc[mask,deg]=True
    base['cell_interval_status']=np.where(absent,'structural_zero_conditional_degenerate',np.where(base.deviation_degenerate.fillna(True),'conditional_degenerate','conditional_whole_study_bootstrap'));base.to_parquet(ROOT/'tables/full_country_pair_matrices.parquet',index=False);base.to_csv(ROOT/'tables/full_country_pair_matrices.csv.gz',index=False,compression='gzip')
    ci.to_parquet(ROOT/'tables/country_pair_uncertainty.parquet',index=False)
    np.savez_compressed(ROOT/'draws/country_pair_full_points.npz',**{s+'__'+cp:p for (s,cp),p in points.items()})
    # The entire output draw arrays are retained compressed, not discarded.
    for (setting,cp),arr in maps.items():np.savez_compressed(ROOT/'draws'/f'country_pair_{cp}_{setting}.npz',joint_country_O_E=arr)
    dump(marker,dict(status='PASS',seed=seed,replicates=B,all_country_cells=True,registry=227,active_pair_cells=K,full_grid_rows=len(base),joint_observed_expected=True,raw_and_standardized=True,direct_corpus_deviation=True,unit='O/E shares 0..1; deviation pp',strata='corpus/year/type/subfield',interval_type='conditional_whole_study_bootstrap',zero_cells='structural or empirical degenerate; no false point-interval precision',draw_format='compressed float64 arrays with country_pair_index and observed K / expected K columns'))
    print('Complete country-pair conditional ranges PASS',len(base),'rows',flush=True)
if __name__=='__main__':main()
