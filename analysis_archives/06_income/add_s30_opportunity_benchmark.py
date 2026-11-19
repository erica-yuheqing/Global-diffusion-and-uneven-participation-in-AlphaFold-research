"""Reproduce study-level allocations and add the income-specific opportunity benchmark.

Annual coverage gaps (not cumulative gaps), 2025 minus 2021.
Each simulated study label is shared by all of its institutional memberships.
Reference ranges are centered at the analytic expectation; they are not effect CIs.
"""
from pathlib import Path
import hashlib,json,time,math,string,shutil,sys
import numpy as np
import pandas as pd
import duckdb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
SRC=Path('/historical-workspace/Desktop/Findings_figures/Findings/v7/finding2_v7_final_v1')
OLD=Path('/historical-workspace/Desktop/Findings_figures/past_version_figures/figure2_plan3_final_v1')
OUT=ROOT/'Supplementary_S30_final'
SEED=20261024; B=5000; YEARS=[2021,2025]; GROUPS=['L','M','H']; INCOME=['L','LM','UM','H']
LABELS={'L':'Low income','LM':'Lower-middle income','UM':'Upper-middle income','H':'High income'}
BLUE='#35527d'; BAND='#f6f9fd'; GRID='#e4edf7'; COLORS={'L':'#5899d1','M':'#2b927d','H':'#173f86'}
for d in [OUT,OUT/'source_data',OUT/'provenance']:d.mkdir(exist_ok=True)
checks=[]

def read(p):return pd.read_csv(p,keep_default_na=False)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def check(name,ok,detail=None):
    if not bool(ok):raise AssertionError((name,detail))
    checks.append(dict(check=name,passed=True,detail=detail))

def simulate(reg,country):
    cache=OUT/'source_data/country_endpoint_allocations.npz'
    if cache.exists():return np.load(cache)['annual_coverage']
    t=time.monotonic();c=duckdb.connect();c.execute("SET threads=1;SET preserve_insertion_order=true;SET memory_limit='3GB'")
    path=str(SRC/'inputs/raw/opportunity_studies.parquet').replace("'","''")
    c.execute(f"CREATE TABLE papers AS SELECT row_number() OVER ()-1 AS paper_index,study_id,year,field,country_set,z FROM read_parquet('{path}')")
    p=c.execute('SELECT paper_index,year,field,country_set,z FROM papers ORDER BY paper_index').df()
    check('2200061 global studies and 15961 AF labels',len(p)==2200061 and p.z.sum()==15961)
    codes,levels=pd.factorize(pd.MultiIndex.from_frame(p[['field','year','country_set']]),sort=True)
    sizes=np.bincount(codes); k=np.bincount(codes,weights=p.z.to_numpy(),minlength=len(sizes)).astype(np.int64)
    order=np.argsort(codes,kind='stable'); starts=np.r_[0,np.cumsum(sizes)]
    mutable=np.flatnonzero((k>0)&(k<sizes))
    fixed=np.flatnonzero(p.z.to_numpy() & (k[codes]==sizes[codes]))
    blocks=[order[starts[h]:starts[h+1]] for h in mutable];draw_k=k[mutable]
    check('194625 strata and 3620 mutable strata',len(sizes)==194625 and len(mutable)==3620)
    check('14524 mutable AF labels',int(draw_k.sum())==14524)
    reg=reg.copy().reset_index(drop=True);reg['inst_index']=np.arange(len(reg),dtype=np.int32)
    cc=country.country.tolist()
    cell=pd.Categorical(reg.country,categories=cc).codes.astype(np.int64)*3+pd.Categorical(reg.group,categories=GROUPS).codes
    denominator=np.bincount(cell,minlength=len(cc)*3).reshape(len(cc),3)
    check('All 204 domestic groups retained',len(reg)==48010 and (denominator>=20).all())
    c.register('registry',reg[['institution_id','inst_index']])
    memberpath=str(SRC/'inputs/raw/opportunity_memberships.parquet').replace("'","''")
    links=c.execute(f"SELECT p.paper_index,r.inst_index,p.year FROM read_parquet('{memberpath}') m JOIN papers p USING(study_id) JOIN registry r USING(institution_id) WHERE p.year IN (2021,2025) ORDER BY p.paper_index,r.inst_index").df()
    idx=links.paper_index.to_numpy(dtype=np.int64)
    indptr=np.r_[0,np.cumsum(np.bincount(idx,minlength=len(p)))]
    endpoints=(links.inst_index.to_numpy(dtype=np.int32)*2+(links.year.to_numpy()==2025)).astype(np.int32)
    check('Sorted links and adjacency lengths',indptr[-1]==len(endpoints) and np.all(idx[:-1]<=idx[1:]))
    def coverage(selected):
        counts=np.diff(indptr)[selected];total=int(counts.sum());offsets=np.repeat(indptr[selected],counts)+np.arange(total)-np.repeat(np.cumsum(counts)-counts,counts)
        active=np.unique(endpoints[offsets]);encoded=cell[active//2]*2+active%2
        n=np.bincount(encoded,minlength=len(cc)*3*2).reshape(len(cc),3,2)
        return n/denominator[:,:,None]
    observed=coverage(np.flatnonzero(p.z.to_numpy()))
    frozen=read(ROOT/'inputs/country_group_year_primary.csv');frozen=frozen[frozen.eligible_20.eq(True)&frozen.year.isin(YEARS)]
    frozen=frozen.set_index(['country','group','year']).A.reindex(pd.MultiIndex.from_product([cc,GROUPS,YEARS])).to_numpy().reshape(len(cc),3,2)
    check('Raw observed annual coverage equals frozen 408 cells',np.allclose(observed,frozen,atol=1e-14))
    rng=np.random.default_rng(SEED);draws=np.empty((B,len(cc),3,2),dtype=np.float64)
    for b in range(B):
        selected=np.concatenate([fixed]+[rng.choice(block,int(ki),replace=False) for block,ki in zip(blocks,draw_k)])
        check_k=np.bincount(codes[selected],minlength=len(sizes))
        if not np.array_equal(check_k,k):raise AssertionError('Stratum AF counts changed')
        draws[b]=coverage(selected)
        if b==0 or (b+1)%500==0:print(f'Allocation {b+1}/{B}; elapsed {time.monotonic()-t:.1f}s',flush=True)
    c.close()
    np.savez_compressed(cache,annual_coverage=draws,countries=np.array(cc),groups=np.array(GROUPS),years=np.array(YEARS),seed=np.array(SEED))
    print('Saved per-country allocations',draws.shape,flush=True)
    return draws

def prepare():
    mapping=read(ROOT/'tables/country_income_mapping.csv')
    country=read(ROOT/'inputs/country_context.csv');country=country[country.eligible_20.eq(True)].sort_values('country').reset_index(drop=True)
    country=country.merge(mapping[['country_code','income_group']],left_on='country',right_on='country_code',validate='one_to_one')
    reg=read(ROOT/'inputs/institution_baseline_and_first_participation.csv');reg=reg[reg.eligible_20.eq(True)].sort_values('institution_id').reset_index(drop=True)
    check('Main population unchanged',len(reg)==48010 and len(country)==68)
    pin=SRC/'inputs/raw/historical_audits/run_manifest.json';manifest=json.loads(pin.read_text())
    for name in ['opportunity_studies.parquet','opportunity_memberships.parquet']:
        path=SRC/'inputs/raw'/name
        check('Original raw bytes preserved: '+name,sha(path)==manifest['outputs']['tables/'+name]['sha256'])
    analytic_file=OUT/'source_data/country_analytic_expectation.csv'
    if not analytic_file.exists():shutil.copyfile(OLD/'tables/analytic_expectation_check.csv',analytic_file)
    check('Historical country analytic expectations match recorded hash',sha(analytic_file)==manifest['outputs']['tables/analytic_expectation_check.csv']['sha256'])
    expectation=read(analytic_file);expectation=expectation[expectation.year.isin(YEARS)&expectation.country.isin(country.country)]
    index=pd.MultiIndex.from_product([country.country.tolist(),GROUPS,YEARS],names=['country','group','year'])
    exact=expectation.set_index(['country','group','year']).analytic_A.reindex(index).to_numpy().reshape(68,3,2)
    observed=read(ROOT/'inputs/country_group_year_primary.csv');observed=observed[observed.eligible_20.eq(True)&observed.year.isin(YEARS)]
    obs=observed.set_index(['country','group','year']).A.reindex(index).to_numpy().reshape(68,3,2)
    check('All analytic and observed endpoints available',np.isfinite(exact).all() and np.isfinite(obs).all())
    draws=simulate(reg,country)
    # Reproduce original output-group endpoint distributions before regrouping by income.
    archived=duckdb.connect().read_parquet(str(SRC/'inputs/raw/benchmark_replicates.parquet')).df()
    archived=archived[archived.variant.eq('main')&archived.setting.eq('main')]
    oldsummary=read(SRC/'inputs/frozen/Table_SY_b_benchmark.csv')
    errors=[]
    for context in ['All','Low','Middle','High']:
        mask=np.ones(68,dtype=bool) if context=='All' else country.context.eq(context).to_numpy()
        got=100*(draws[:,mask,2,:].mean(axis=1)-draws[:,mask,0,:].mean(axis=1));delta=got[:,1]-got[:,0]
        orig=archived[archived.context.eq(context)].sort_values('replicate')
        err=float(np.max(np.abs(delta-orig.delta_G.to_numpy())));errors.append(err)
        expected=100*((exact[mask,2,1].mean()-exact[mask,0,1].mean())-(exact[mask,2,0].mean()-exact[mask,0,0].mean()))
        target=oldsummary[oldsummary.context.eq(context)].iloc[0]
        check('Original analytic gap change reproduced: '+context,abs(expected-float(target.expected_delta_G))<1e-8)
    exact_replay=max(errors)<1e-9
    check('Original 5000 allocation endpoint draws reproduced',exact_replay,{'maximum_absolute_error_pp':max(errors)})
    rows=[];detail=[]
    for inc in INCOME:
        mask=country.income_group.eq(inc).to_numpy();n=int(mask.sum())
        a=obs[mask].mean(axis=0);e=exact[mask].mean(axis=0);sim=draws[:,mask].mean(axis=1)
        ag=100*(a[2]-a[0]);eg=100*(e[2]-e[0]);sg=100*(sim[:,2,:]-sim[:,0,:]);dg=sg[:,1]-sg[:,0]
        actual=float(ag[1]-ag[0]);expected=float(eg[1]-eg[0]);residual=actual-expected
        centered=dg-expected;lo,hi=np.quantile(centered,[.025,.975]);mcse=float(dg.std(ddof=1)/np.sqrt(B))
        meanerr=float(dg.mean()-expected)
        check('Income-group simulation mean agrees with analytic expectation: '+inc,abs(meanerr)<5*mcse+1e-6,{'error_pp':meanerr,'MCSE_pp':mcse})
        rows.append(dict(income_group=inc,income_label=LABELS[inc],countries=n,observed_gap_2021_pp=ag[0],observed_gap_2025_pp=ag[1],observed_gap_change_pp=actual,expected_gap_2021_pp=eg[0],expected_gap_2025_pp=eg[1],expected_gap_change_pp=expected,observed_minus_expected_pp=residual,centered_reference_low_pp=lo,centered_reference_high_pp=hi,unshifted_reference_low_pp=float(np.quantile(dg,.025)),unshifted_reference_high_pp=float(np.quantile(dg,.975)),simulated_mean_change_pp=float(dg.mean()),MCSE_mean_pp=mcse,mean_check_error_pp=meanerr,reference_outside=bool(residual<lo-1e-9 or residual>hi+1e-9),replicates=B,seed=SEED,interval_type='pointwise centered conditional allocation reference range around zero; not a confidence interval for the observed residual',higher_group_observed_minus_expected_change_pp=100*((a[2,1]-a[2,0])-(e[2,1]-e[2,0])),lower_group_observed_minus_expected_change_pp=100*((a[0,1]-a[0,0])-(e[0,1]-e[0,0]))))
        for b in range(B):detail.append(dict(replicate=b+1,income_group=inc,simulated_gap_change_pp=dg[b],centered_gap_change_pp=centered[b]))
    summary=pd.DataFrame(rows);summary.to_csv(OUT/'source_data/S30e_income_benchmark_summary.csv',index=False);pd.DataFrame(detail).to_csv(OUT/'source_data/S30e_income_benchmark_replicates.csv',index=False)
    country[['country','context','income_group']].to_csv(OUT/'source_data/country_order_and_groups.csv',index=False)
    cov=read(ROOT/'tables/coverage_by_income_group.csv');cov.to_csv(OUT/'source_data/S30a_d_coverage.csv',index=False)
    pd.DataFrame(checks).to_json(OUT/'provenance/numerical_checks.json',orient='records',indent=2)
    pins=[]
    for p in [pin,SRC/'inputs/raw/opportunity_studies.parquet',SRC/'inputs/raw/opportunity_memberships.parquet',analytic_file,ROOT/'tables/country_income_mapping.csv',ROOT/'inputs/country_group_year_primary.csv']:
        pins.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
    (OUT/'provenance/input_manifest.json').write_text(json.dumps(pins,indent=2))
    print(summary.to_string(index=False),flush=True)
    return cov,summary

def draw(cov,s):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':8,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7.5,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,'axes.edgecolor':'#8399b4','axes.linewidth':.65,'xtick.major.width':.65,'ytick.major.width':0,'xtick.color':BLUE,'ytick.color':BLUE,'axes.titlecolor':BLUE,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig=plt.figure(figsize=(183/25.4,203/25.4))
    grid=fig.add_gridspec(3,2,left=.11,right=.98,bottom=.09,top=.90,height_ratios=[1,1,.88],hspace=.55,wspace=.25)
    axes=[fig.add_subplot(grid[i//2,i%2]) for i in range(4)]
    for i,(ax,g) in enumerate(zip(axes,INCOME)):
        z=cov[cov.income_group.eq(g)];n=int(z.countries.iloc[0]);ax.text(-.12,1.075,string.ascii_lowercase[i],transform=ax.transAxes,fontsize=10,fontweight='bold',color='#111820');ax.set_title(f'{LABELS[g]} (n = {n})',loc='left',pad=10)
        for low in [0,20,40]:ax.axhspan(low,low+10,color=BAND,lw=0,zorder=0)
        for inst,marker,label in [('L','o','Lower'),('M','s','Middle'),('H','^','Higher')]:
            v=z[z.institution_group.eq(inst)].sort_values('year');ax.plot(v.year,v.equal_country_coverage_pct,color=COLORS[inst],marker=marker,lw=1.05,ms=3.2,label=label,zorder=3)
            end=float(v.equal_country_coverage_pct.iloc[-1]);label_y=end+({'L':-1.5,'M':1.8}.get(inst,0) if g=='L' else 0)
            ax.annotate(f'{end:.2f}%',xy=(2025,end),xytext=(2025.15,label_y),color=COLORS[inst],fontsize=7,va='center',arrowprops={'arrowstyle':'-','color':COLORS[inst],'lw':.45} if label_y!=end else None)
        if g=='L':ax.text(.02,.94,'Ethiopia and Uganda',transform=ax.transAxes,fontsize=6.5,color=BLUE,va='top')
        ax.set_xlim(2019.85,2026.3);ax.set_ylim(0,48);ax.set_xticks(range(2020,2026));ax.set_yticks([0,10,20,30,40]);ax.set_axisbelow(True);ax.grid(axis='x',color=GRID,lw=.45);ax.tick_params(axis='x',length=3);ax.tick_params(axis='y',length=0,pad=6)
        if i%2:ax.tick_params(labelleft=False)
        if i>=2:ax.set_xlabel('Publication year',labelpad=6)
    fig.text(.54,.979,'Institutional groups · within-country baseline output',fontsize=7.5,ha='center',color=BLUE)
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='center',bbox_to_anchor=(.54,.953),ncol=3,frameon=False,fontsize=7.5,columnspacing=2,handlelength=0,numpoints=1)
    fig.text(.023,.665,'Cumulative institutional coverage (%)',rotation=90,va='center',fontsize=8)
    ax=fig.add_subplot(grid[2,:]);ax.text(-.22,1.12,'e',transform=ax.transAxes,fontsize=10,fontweight='bold',color='#111820')
    y=np.arange(4)
    for yy in y:ax.axhspan(yy-.38,yy+.38,color=BAND,lw=0,zorder=0)
    for i,g in enumerate(INCOME):
        v=s[s.income_group.eq(g)].iloc[0];lo=float(v.centered_reference_low_pp);hi=float(v.centered_reference_high_pp)
        ax.hlines(i+.08,lo,hi,color=COLORS['L'],lw=1.2,zorder=3,label='95% conditional reference range' if i==0 else None)
        ax.vlines([lo,hi],i+.025,i+.135,color=COLORS['L'],lw=.8,zorder=3)
        ax.plot(float(v.observed_minus_expected_pp),i-.09,'o',color=COLORS['H'],ms=4,zorder=4,label='Observed − expected' if i==0 else None)
    ax.axvline(0,color='#b0bdcf',lw=.9,ls='--',zorder=2);ax.set_yticks(y,[LABELS[g] for g in INCOME]);ax.set_ylim(3.43,-.43);ax.set_xlim(min(-6,float(s.centered_reference_low_pp.min())-1),max(4,float(s.centered_reference_high_pp.max())+1));ax.grid(axis='x',color=GRID,lw=.45);ax.set_axisbelow(True);ax.tick_params(axis='y',length=0,pad=8);ax.tick_params(axis='x',length=3)
    ax.set_xlabel('Change in annual coverage gap, 2021–2025: observed − expected (pp)',labelpad=7)
    ax.legend(frameon=False,fontsize=7,loc='lower center',bbox_to_anchor=(.5,1.06),ncol=2,columnspacing=2)
    # Increase left padding for the long income labels in the lower, full-width panel.
    pos=ax.get_position();ax.set_position([.23,pos.y0,.75,pos.height])
    for ext in ['pdf','svg']:fig.savefig(OUT/f'Supplementary_Fig_S30.{ext}',facecolor='white')
    fig.savefig(OUT/'Supplementary_Fig_S30.png',dpi=600,facecolor='white');fig.savefig(OUT/'Supplementary_Fig_S30_preview.png',dpi=220,facecolor='white');plt.close(fig)

def text(s):
    caption='''Supplementary Fig. S30 | Institutional AF coverage and publication-opportunity references by national income group.
a–d, Cumulative coverage of at least one confirmed AF publication during 2020–2025 in low-, lower-middle-, upper-middle- and high-income countries and regions, respectively. National income groups use the fixed World Bank FY2020 classification. Institutions retain their within-country groups based on 2015–2019 publication output. Country-specific rates are averaged equally within each income group. All 48,010 baseline institutions in the original 68-country sample are retained, including nonparticipants. Country counts are shown in panel labels. The low-income group contains Ethiopia and Uganda only. End labels give 2025 coverage. Curves are descriptive, with no confidence intervals.
e, Observed-minus-expected changes in the annual higher-minus-lower institutional coverage gap between 2021 and 2025, in percentage points. Annual gaps differ from the cumulative coverage shown in a–d. Dark-blue circles show observed changes minus exact analytic expectations. Light-blue horizontal ranges show the central 95% of conditional allocation changes after subtracting the same analytic expectation; these ranges are centered near zero and are not confidence intervals around the observed residuals. The dashed line marks zero. Five thousand whole-study AF-label allocations preserve AF counts within publication-year, primary-subfield and complete-country-set strata, with each study's label shared by all its institutions. The original seed and raw inputs were used, and the original allocation endpoint distributions were verified before regrouping by income. Rates are averaged equally across countries within each income group. Reference ranges are pointwise and unadjusted for multiple comparisons. Negative residuals indicate less gap widening than expected under the reference, not a causal reduction in inequality or above-reference gains among lower-output institutions. Pale bands are visual guides.
'''
    (OUT/'Figure_legend_S30.txt').write_text(caption)
    lines=['Income-group opportunity benchmark for S30e','']
    for v in s.itertuples():
        lines.append(f'{v.income_label} (n={v.countries}): observed annual gap change {v.observed_gap_change_pp:.3f} pp; exact expected {v.expected_gap_change_pp:.3f} pp; residual {v.observed_minus_expected_pp:+.3f} pp; centered 95% reference range [{v.centered_reference_low_pp:+.3f}, {v.centered_reference_high_pp:+.3f}] pp.')
    lines+=['','Ranges describe variation under the conditional study-label allocation, not sampling confidence intervals for the observed residual. The low-income sample contains only Ethiopia and Uganda.']
    (OUT/'Numerical_results.txt').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    if '--redraw' in sys.argv:
        cov=read(OUT/'source_data/S30a_d_coverage.csv');s=read(OUT/'source_data/S30e_income_benchmark_summary.csv')
    else:
        cov,s=prepare()
    draw(cov,s);text(s);print('Saved updated five-panel S30',OUT,flush=True)
