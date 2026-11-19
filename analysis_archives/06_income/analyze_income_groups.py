"""Reaggregate frozen AF analyses by World Bank FY2020 income classification.

No AF labels, studies, support cells, weights, or domestic institution groups change.
Country bootstrap credits are summed within income groups BEFORE calculating ratios.
"""
from pathlib import Path
import sys, json, hashlib, shutil, html, platform, zipfile
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import duckdb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

OUT = Path(__file__).resolve().parent
F4 = Path('/historical-workspace/Desktop/Findings_figures/Findings/v7/finding4_v7_final_v1')
F2 = Path('/historical-workspace/Desktop/NHB_peer review/Results_methods_response_20261102/data/F2/tables')
WB_URL = 'https://ddh-openapi.worldbank.org/resources/DR0095334/download'
WB_CONTEXT = 'https://blogs.worldbank.org/en/opendata/new-country-classifications-income-level-2019-2020'
INCOMES = ['L', 'LM', 'UM', 'H']
LABELS = {'L':'Low income', 'LM':'Lower-middle income', 'UM':'Upper-middle income', 'H':'High income', 'outside':'Outside classification scope'}
INST_LABELS = {'L':'Lower output', 'M':'Middle output', 'H':'Higher output'}
INST_COLORS = {'L':'#6da9c4', 'M':'#32957d', 'H':'#294c7c'}
assertions = []

def check(name, condition, detail=None):
    if not bool(condition):
        raise AssertionError(f'{name}: {detail}')
    assertions.append({'check': name, 'passed': True, 'detail': detail})

def read(path):
    return pd.read_csv(path, keep_default_na=False, low_memory=False)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def save(name, df):
    df.to_csv(OUT/'tables'/f'{name}.csv', index=False)
    return df

def bounds(x):
    x=np.asarray(x,float); v=x[np.isfinite(x)]
    if len(v) < .95 * len(x):
        return np.nan, np.nan, len(v)
    return *np.quantile(v,[.025,.975]).tolist(), len(v)

def divide(a,b):
    a,b=np.broadcast_arrays(np.asarray(a,float),np.asarray(b,float))
    return np.divide(a,b,out=np.full(a.shape,np.nan),where=b>0)

def setup():
    for name in ['tables','figures','inputs','provenance']:
        (OUT/name).mkdir(exist_ok=True)
    wb=OUT/'inputs/worldbank_income_history.xlsx'
    if not wb.exists():
        shutil.copyfile('/tmp/af_income_worldbank_history.xlsx',wb)
    # Freeze the country component of the original shared whole-study draws.
    cache=OUT/'inputs/country_credits_and_joint_bootstrap.npz'
    for source,destination in [(F4/'inputs/normalized/feature_metadata.json',OUT/'inputs/original_feature_metadata.json'),(F4/'draws/strict_main_points.json',OUT/'inputs/original_feature_points.json')]:
        if not destination.exists():shutil.copyfile(source,destination)
    meta=json.loads((OUT/'inputs/original_feature_metadata.json').read_text())
    if not cache.exists():
        pools=np.load(F4/'draws/strict_main_joint_pools.npz')
        points=json.loads((F4/'draws/strict_main_points.json').read_text())
        values={}; e=meta['n_entities']; n=meta['n_countries']
        for corpus in ['AF','reference']:
            key='standardized__'+corpus
            values['points_'+corpus]=np.asarray(points[key]).reshape(-1)[:4*e].reshape(4,e)[:,:n]
            values['draws_'+corpus]=pools[key][:,:4*e].reshape(-1,4,e)[:,:,:n]
        np.savez_compressed(cache,**values)
        (OUT/'inputs/country_order.json').write_text(json.dumps(meta['countries']))
        for filename in ['country_context.csv','country_group_year_primary.csv','institution_baseline_and_first_participation.csv','Fig2a_cumulative.csv']:
            shutil.copyfile(F2/filename,OUT/'inputs'/filename)
        shutil.copyfile(F4/'source_data/country_groups.csv',OUT/'inputs/original_country_groups.csv')
        shutil.copyfile(F4/'tables/strict_main_R.csv',OUT/'inputs/original_authorship_R.csv')
    return meta

def country_mapping():
    import pycountry
    h=pd.read_excel(OUT/'inputs/worldbank_income_history.xlsx',sheet_name='Country Analytical History',header=None,keep_default_na=False)
    col=h.iloc[4].tolist().index('FY20')
    check('Income column is FY20 based on calendar-year 2018 GNI', h.iloc[5,col]==2018)
    history={row[0]:(str(row[1]).strip(),str(row[col]).strip()) for row in h.iloc[6:].itertuples(index=False,name=None) if len(str(row[0]))==3}
    codes=json.loads((OUT/'inputs/country_order.json').read_text())
    original=read(OUT/'inputs/original_country_groups.csv')
    context=read(OUT/'inputs/country_context.csv').rename(columns={'country':'country_code'})
    rows=[]
    for code in codes:
        iso=pycountry.countries.get(alpha_2=code)
        iso3=iso.alpha_3 if iso else {'XK':'XKX'}.get(code,'')
        wb_name, inc=history.get(iso3,('', ''))
        valid=inc in INCOMES
        rows.append(dict(country_code=code,iso3=iso3,country_name=wb_name or (iso.name if iso else code),wb_fy2020=inc,income_group=inc if valid else 'unclassified',income_label=LABELS[inc] if valid else 'Unclassified',mapping_status='ISO3_match' if valid and iso else ('explicit_XK_to_XKX' if valid else 'no_FY2020_classification'),classification_fiscal_year='FY2020',classification_start='2019-07-01',classification_end='2020-06-30',underlying_GNI_year=2018))
    mapping=pd.DataFrame(rows).merge(original[['country_code','baseline_group']],on='country_code',how='left',validate='one_to_one')
    mapping['baseline_group']=mapping.baseline_group.fillna('outside')
    mapping=mapping.merge(context[['country_code','baseline_country_studies','eligible_20']],on='country_code',how='left',validate='one_to_one')
    mapping['original_68_country_sample']=mapping.eligible_20.eq(True)
    check('227 original geographic units preserved',len(mapping)==227 and mapping.country_code.is_unique)
    check('Original 68-country classification preserved',mapping.original_68_country_sample.sum()==68)
    check('All original 68 countries have FY2020 income groups',mapping.loc[mapping.original_68_country_sample,'income_group'].isin(INCOMES).all())
    check('National baseline groups coincide with institutional eligible countries',set(mapping.loc[mapping.baseline_group.ne('outside'),'country_code'])==set(mapping.loc[mapping.original_68_country_sample,'country_code']))
    save('country_income_mapping',mapping)
    cross=pd.crosstab(mapping.baseline_group,mapping.income_label).reindex(index=['lower','middle','higher','outside'],columns=[LABELS[g] for g in INCOMES]+['Unclassified'],fill_value=0).reset_index()
    save('income_output_crosswalk',cross)
    return mapping

def verify_authorship(meta, data, mapping):
    e=meta['n_entities']; n=meta['n_countries']
    original_points=json.loads((OUT/'inputs/original_feature_points.json').read_text())
    reference=read(OUT/'inputs/original_authorship_R.csv')
    reference=reference[reference.setting.eq('standardized') & reference.level.eq('group')]
    max_point_error=0.; max_interval_error=0.
    for gi,group in enumerate(['higher','middle','lower','outside']):
        mask=mapping.baseline_group.eq(group).to_numpy()
        for corpus in ['AF','reference']:
            p=data['points_'+corpus][:,mask].sum(axis=1)
            d=data['draws_'+corpus][:,:,mask].sum(axis=2)
            expected=np.asarray(original_points['standardized__'+corpus])[:4*e].reshape(4,e)[:,n+gi]
            max_point_error=max(max_point_error,float(np.max(np.abs(p-expected))))
            for bench,bi in [('country',0),('author',1)]:
                for role,ri in [('first',2),('last',3)]:
                    row=reference[reference.corpus.eq(corpus)&reference.entity_id.eq('group:'+group)&reference.benchmark.eq(bench)&reference.role.eq(role)].iloc[0]
                    r=p[ri]/p[bi]; lo,hi,_=bounds(divide(d[:,ri],d[:,bi]))
                    max_point_error=max(max_point_error,abs(r-float(row.R)))
                    max_interval_error=max(max_interval_error,abs(lo-float(row.ci_low)),abs(hi-float(row.ci_high)))
    check('Original country-group pooled credits and R reproduced',max_point_error<1e-8,{'maximum_error':max_point_error})
    check('Original 2000-replicate group R intervals reproduced',max_interval_error<1e-8,{'maximum_error':max_interval_error})
    print('Original authorship points and intervals reproduced:',max_point_error,max_interval_error,flush=True)

def authorship(mapping, data):
    ratios=[]; differences=[]; changes=[]; shares=[]
    codes=list(mapping.country_code)
    for scope in ['original_68','all_classified']:
        group_for=[]
        for row in mapping.itertuples():
            included=row.original_68_country_sample if scope=='original_68' else True
            group_for.append(row.income_group if included and row.income_group in INCOMES else 'outside')
        for group in INCOMES+['outside']:
            mask=np.asarray(group_for)==group
            results={}
            for corpus in ['AF','reference']:
                p=data['points_'+corpus][:,mask].sum(axis=1)
                d=data['draws_'+corpus][:,:,mask].sum(axis=2)
                totals=data['points_'+corpus].sum(axis=1)
                check(f'Credit mass conserved {scope} {group} {corpus}',np.allclose(totals,5087.,atol=1e-7))
                sh=p/totals
                shares.append(dict(scope=scope,income_group=group,income_label=LABELS[group],corpus=corpus,country_participation_pct=100*sh[0],author_participation_pct=100*sh[1],first_author_pct=100*sh[2],last_author_pct=100*sh[3],countries=int(mask.sum()),country_codes=','.join(np.array(codes)[mask])))
                for bench,bi in [('country',0),('author',1)]:
                    for role,ri in [('first',2),('last',3)]:
                        r=float(divide(sh[ri],sh[bi])); draws=divide(d[:,ri],d[:,bi]);lo,hi,valid=bounds(draws)
                        ratios.append(dict(scope=scope,income_group=group,income_label=LABELS[group],corpus=corpus,benchmark=bench,role=role,R=r,ci_low=lo,ci_high=hi,valid_replicates=valid,participation_credit=p[bi],role_credit=p[ri],global_credit=5087.,interval_type='conditional stratified whole-study bootstrap; original 2000 joint replicates',countries=int(mask.sum())))
                        results[corpus,bench,role]=(r,draws)
            for role in ['first','last']:
                ds={}
                for bench in ['country','author']:
                    a,ad=results['AF',bench,role];r,rd=results['reference',bench,role]; delta=a-r;draws=ad-rd;lo,hi,valid=bounds(draws)
                    differences.append(dict(scope=scope,income_group=group,income_label=LABELS[group],benchmark=bench,role=role,R_AF=a,R_reference=r,delta_R=delta,ci_low=lo,ci_high=hi,valid_replicates=valid))
                    ds[bench]=(delta,draws)
                c=ds['author'][0]-ds['country'][0]; cd=ds['author'][1]-ds['country'][1];lo,hi,valid=bounds(cd)
                b=abs(ds['country'][0])-abs(ds['author'][0]);bd=np.abs(ds['country'][1])-np.abs(ds['author'][1]);bl,bh,bv=bounds(bd)
                changes.append(dict(scope=scope,income_group=group,income_label=LABELS[group],role=role,C=c,ci_low=lo,ci_high=hi,valid_replicates=valid,B_absolute_reduction=b,B_ci_low=bl,B_ci_high=bh,B_valid_replicates=bv))
    return save('authorship_representation',pd.DataFrame(ratios)),save('authorship_AF_minus_reference',pd.DataFrame(differences)),save('authorship_benchmark_change',pd.DataFrame(changes)),save('authorship_credit_shares',pd.DataFrame(shares))

def support_counts(mapping):
    cached=OUT/'inputs/authorship_support_by_country_and_income.csv'
    if cached.exists():
        support=read(cached)
    else:
        con=duckdb.connect(); con.execute('SET threads=2')
        con.read_parquet(str(F4/'inputs/normalized/analysis_members.parquet')).filter('supported').create_view('members')
        con.read_parquet(str(F4/'inputs/normalized/credit.parquet')).filter("channel='country_output'").create_view('credits')
        ids=mapping[['country_code','income_group','original_68_country_sample']].copy();con.register('mapping',ids)
        support=con.execute('''WITH linked AS (SELECT m.study_id,m.corpus,m.weight,c.country_code,z.income_group,z.original_68_country_sample FROM members m JOIN credits c USING(study_id) JOIN mapping z USING(country_code))
            SELECT 'country' AS scope,country_code AS entity,corpus,count(DISTINCT study_id) AS distinct_studies,sum(weight) AS study_weight FROM linked GROUP BY 1,2,3
            UNION ALL SELECT 'original_68' AS scope,CASE WHEN original_68_country_sample AND income_group!='unclassified' THEN income_group ELSE 'outside' END AS entity,corpus,count(DISTINCT study_id),sum(weight) FROM (SELECT DISTINCT study_id,corpus,weight,original_68_country_sample,income_group FROM linked) GROUP BY 1,2,3
            UNION ALL SELECT 'all_classified' AS scope,CASE WHEN income_group!='unclassified' THEN income_group ELSE 'outside' END AS entity,corpus,count(DISTINCT study_id),sum(weight) FROM (SELECT DISTINCT study_id,corpus,weight,income_group FROM linked) GROUP BY 1,2,3''').df()
        # Raw country-level link weights can count countries more than once within a group.
        # Only distinct_studies is used for group support; weighted credit is from the pooled matrices.
        support=support.drop(columns='study_weight')
        support.to_csv(cached,index=False);con.close()
    return save('authorship_sample_support',support)

def institution_coverage(mapping):
    inst=read(OUT/'inputs/institution_baseline_and_first_participation.csv')
    inst=inst[inst.eligible_20.eq(True)&inst.baseline_country_count.eq(1)].copy()
    check('Fixed institutional population is 48010',len(inst)==48010 and inst.institution_id.is_unique)
    inst=inst.merge(mapping[['country_code','income_group','country_name']],left_on='country',right_on='country_code',validate='many_to_one')
    inst['first_year']=pd.to_numeric(inst.first_confirmed_year,errors='coerce')
    rows=[]
    for (country,group),v in inst.groupby(['country','group']):
        for year in range(2020,2026):
            num=int(v.first_year.le(year).sum())
            rows.append(dict(country=country,country_name=v.country_name.iloc[0],income_group=v.income_group.iloc[0],institution_group=group,year=year,baseline_institutions=len(v),AF_institutions=num,coverage_pct=100*num/len(v)))
    cells=pd.DataFrame(rows)
    frozen=read(OUT/'inputs/country_group_year_primary.csv');z=cells.merge(frozen,on=['country','year'],suffixes=('','_frozen'));z=z[z.institution_group.eq(z.group)]
    check('All 1224 country-group-year counts independently reproduced',len(z)==68*3*6 and (z.AF_institutions==z.cumulative_N).all() and (z.baseline_institutions==z.fixed_N).all())
    expected=read(OUT/'inputs/Fig2a_cumulative.csv')
    original=cells.groupby(['institution_group','year']).coverage_pct.mean().reset_index().merge(expected,left_on=['institution_group','year'],right_on=['group','year'])
    max_error=np.max(np.abs(original.coverage_pct-100*original.C))
    check('Published country-equal institutional coverage reproduced',max_error<1e-8,{'maximum_error_percentage_points':float(max_error)})
    check('7654 institutions covered by 2025',cells[cells.year.eq(2025)].AF_institutions.sum()==7654)
    save('coverage_country_institution_group_year',cells)
    agg=cells.groupby(['income_group','institution_group','year'],sort=False).agg(countries=('country','nunique'),baseline_institutions=('baseline_institutions','sum'),AF_institutions=('AF_institutions','sum'),equal_country_coverage_pct=('coverage_pct','mean'),country_min_pct=('coverage_pct','min'),country_max_pct=('coverage_pct','max')).reset_index()
    agg['pooled_institution_coverage_pct']=100*agg.AF_institutions/agg.baseline_institutions
    agg['income_label']=agg.income_group.map(LABELS)
    agg['weighting']='equal country within each income group; pooled rate supplied separately'
    save('coverage_by_income_group',agg)
    save('coverage_2025',agg[agg.year.eq(2025)].copy())
    # Paired country contrasts avoid conflating unequal country weights or different country sets.
    piv=cells.pivot(index=['country','country_name','income_group','year'],columns='institution_group',values='coverage_pct').reset_index()
    piv['higher_minus_lower_pp']=piv.H-piv.L
    piv['lower_to_higher_ratio']=divide(piv.L,piv.H)
    save('coverage_country_gradients',piv)
    grad=piv.groupby(['income_group','year']).agg(countries=('country','nunique'),countries_higher_gt_lower=('higher_minus_lower_pp',lambda x:int((x>0).sum())),mean_higher_minus_lower_pp=('higher_minus_lower_pp','mean')).reset_index()
    save('coverage_income_gradients',grad)
    selected=inst.groupby('income_group').agg(baseline_institutions=('institution_id','size'),countries=('country','nunique'),AF_institutions_2025=('first_year',lambda x:int(x.le(2025).sum()))).reset_index()
    return cells,agg,grad,selected

def population_table(mapping, support, inst_summary, shares):
    rows=[]
    for g in INCOMES:
        allcountries=mapping[mapping.income_group.eq(g)];main=allcountries[allcountries.original_68_country_sample]
        ir=inst_summary[inst_summary.income_group.eq(g)].iloc[0]
        row=dict(income_group=g,income_label=LABELS[g],countries_in_227_unit_roster=len(allcountries),countries_in_original_68=len(main),original_68_country_codes=','.join(main.country_code),baseline_institutions=int(ir.baseline_institutions),AF_institutions_2025=int(ir.AF_institutions_2025))
        for scope in ['original_68','all_classified']:
            for corpus in ['AF','reference']:
                s=support[support.scope.eq(scope)&support.entity.eq(g)&support.corpus.eq(corpus)]
                row[f'{scope}_{corpus}_authorship_studies']=int(s.distinct_studies.iloc[0]) if len(s) else 0
        rows.append(row)
    return save('income_group_sample_summary',pd.DataFrame(rows))

def export_figure(fig,name):
    for ext in ['png','pdf','svg']:
        fig.savefig(OUT/'figures'/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
    plt.close(fig)

def make_figures(mapping,differences,coverage,summary):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#222222','text.color':'#222222','svg.fonttype':'none','pdf.fonttype':42})
    cross=pd.crosstab(mapping.loc[mapping.original_68_country_sample,'baseline_group'],mapping.loc[mapping.original_68_country_sample,'income_group']).reindex(index=['lower','middle','higher'],columns=INCOMES,fill_value=0)
    fig,ax=plt.subplots(figsize=(8,3.2));ax.imshow(cross.values,cmap='Blues',vmin=0,vmax=max(1,cross.values.max()),aspect='auto')
    ax.set_xticks(range(4),[LABELS[g].replace(' income','\nincome') for g in INCOMES]);ax.set_yticks(range(3),['Lower output','Middle output','Higher output']);ax.set_ylabel('National baseline output group')
    for i in range(3):
        for j in range(4):ax.text(j,i,str(cross.iloc[i,j]),ha='center',va='center',color='white' if cross.iloc[i,j]>cross.values.max()*.55 else '#202020',fontsize=13)
    ax.set_title('National output and income classifications\n68 countries and regions; World Bank FY2020',loc='left',pad=16)
    ax.tick_params(length=0);export_figure(fig,'income_output_crosswalk')
    # Same study cohorts and weights in both scope rows; only country assignment changes.
    fig,axes=plt.subplots(2,2,figsize=(11.8,7.4),sharey=True,sharex=True)
    grouporder=INCOMES; ys=np.arange(4)
    for row,scope in enumerate(['original_68','all_classified']):
        for col,role in enumerate(['first','last']):
            ax=axes[row,col];x=differences[differences.scope.eq(scope)&differences.role.eq(role)]
            for b,bench,color,marker,offset in [(0,'country','#294c7c','o',-.11),(1,'author','#559aa5','D',.11)]:
                z=x[x.benchmark.eq(bench)].set_index('income_group').reindex(grouporder)
                ax.errorbar(z.delta_R,ys+offset,xerr=[z.delta_R-z.ci_low,z.ci_high-z.delta_R],fmt=marker,color=color,markersize=5,capsize=2,label='Country participation' if b==0 else 'Team-author participation')
            ax.axvline(0,color='#888888',lw=.8,ls='--');ax.set_yticks(ys,[LABELS[g] if g!='outside' else 'Outside scope' for g in grouporder]);ax.invert_yaxis() if row==0 and col==0 else None
            ax.grid(axis='x',alpha=.15);ax.set_title(('Original 68 countries' if scope=='original_68' else 'All income-classified countries')+'\n'+role.capitalize()+' authorship',loc='left',fontsize=11)
            ax.set_xlabel('AF minus reference representation ratio')
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,frameon=False,fontsize=9,loc='lower left',bbox_to_anchor=(.025,-.035),ncol=2)
    fig.suptitle('Authorship representation under two participation benchmarks',x=.03,ha='left',fontsize=14,y=1.02)
    fig.text(.03,-.075,'Conditional 95% whole-study bootstrap intervals (2,000 shared replicates).\nOutside-scope credit remains in all global denominators and is reported in the tables.',fontsize=9)
    fig.tight_layout(h_pad=2.6,w_pad=2.8);export_figure(fig,'authorship_by_income')
    fig,axes=plt.subplots(2,2,figsize=(11.4,7.4),sharex=True,sharey=True)
    for ax,g in zip(axes.flat,INCOMES):
        n=int(summary.loc[summary.income_group.eq(g),'countries_in_original_68'].iloc[0]);ax.set_title(f'{LABELS[g]} ({n} countries)',loc='left',fontsize=11)
        for group in ['L','M','H']:
            z=coverage[coverage.income_group.eq(g)&coverage.institution_group.eq(group)].sort_values('year')
            ax.plot(z.year,z.equal_country_coverage_pct,color=INST_COLORS[group],marker={'L':'o','M':'s','H':'^'}[group],ms=4,lw=1.7,label=INST_LABELS[group])
            ax.annotate(f'{z.equal_country_coverage_pct.iloc[-1]:.2f}%',(2025,z.equal_country_coverage_pct.iloc[-1]),xytext=(7,{'L':-9,'M':9 if g=='L' else 2,'H':0}[group]),textcoords='offset points',color=INST_COLORS[group],fontsize=9)
        ax.set_xlim(2019.8,2026.1);ax.set_xticks(range(2020,2026));ax.grid(axis='y',alpha=.18);ax.yaxis.set_major_locator(MaxNLocator(5));ax.set_ylabel('Cumulative institutional coverage (%)')
        if g=='L':ax.text(.03,.91,'Ethiopia and Uganda only',transform=ax.transAxes,fontsize=9,color='#666666')
    axes[0,0].legend(frameon=False,loc='upper left',bbox_to_anchor=(0,.82),fontsize=9)
    axes[0,0].set_ylim(0,float(coverage.equal_country_coverage_pct.max())*1.13)
    fig.suptitle('Institutional AF coverage by national income group',x=.03,ha='left',fontsize=14,y=1.02)
    fig.text(.03,-.025,'Fixed domestic output groups; all 48,010 baseline institutions retained.\nCountry coverage rates averaged equally within each income group. Descriptive estimates; no confidence intervals.',fontsize=9)
    fig.tight_layout(h_pad=2.8,w_pad=2.5);export_figure(fig,'institutional_coverage_by_income')

def reporting(summary,shares,differences,changes,coverage,grad,mapping):
    s=summary.set_index('income_group');end=coverage[coverage.year.eq(2025)]
    lines=['Income group analysis','',
        'Classification: World Bank FY2020, effective 1 July 2019 to 30 June 2020, based on 2018 Atlas GNI per capita. Membership is fixed across 2020–2025.','',
        'Samples: authorship uses the original 5,087 AF and 332,760 reference studies and original 173 comparison cells. Both corpora have standardized weight 5,087. Institutional coverage uses the original 48,010 institutions and 68 countries, including nonparticipants.','',
        'The original 68-country sample contains 2 low-income countries (Ethiopia and Uganda), 12 lower-middle-income countries, 20 upper-middle-income countries and 34 high-income countries. This limitation applies particularly to the interpretation of low-income institutional coverage.','',
        '2025 cumulative coverage (country-equal percentages):']
    for g in INCOMES:
        z=end[end.income_group.eq(g)].set_index('institution_group')
        lines.append(f"{LABELS[g]}: lower {z.loc['L','equal_country_coverage_pct']:.2f}%; middle {z.loc['M','equal_country_coverage_pct']:.2f}%; higher {z.loc['H','equal_country_coverage_pct']:.2f}%. Baseline institutions: {int(s.loc[g,'baseline_institutions']):,}.")
    lines+=['','Authorship results: R is role-credit share divided by participation-credit share. Ratios are calculated after pooling credits within income groups; country ratios are never averaged. All out-of-scope credit remains in global denominators.']
    for scope in ['original_68','all_classified']:
        lines.append('\nScope: '+scope)
        for g in INCOMES:
            for role in ['first','last']:
                z=differences[differences.scope.eq(scope)&differences.income_group.eq(g)&differences.role.eq(role)].set_index('benchmark')
                c=changes[changes.scope.eq(scope)&changes.income_group.eq(g)&changes.role.eq(role)].iloc[0]
                def fmt(r):return f"{r.delta_R:+.3f} [{r.ci_low:+.3f}, {r.ci_high:+.3f}]"
                lines.append(f"{LABELS[g]}, {role}: country delta {fmt(z.loc['country'])}; author delta {fmt(z.loc['author'])}; paired benchmark shift C={c.C:+.3f} [{c.ci_low:+.3f}, {c.ci_high:+.3f}].")
    lines+=['','Interpretation notes:',
        'The original_68 analysis changes only the grouping of the original 68 classified countries. Other countries remain outside scope, even when a World Bank income class is known.',
        'The all_classified analysis is a separately labeled scope check using the same publications and weights. It assigns every mapped country to its FY2020 income group; unclassified geographic units remain outside scope.',
        'Institutional results do not expand beyond the original 68-country denominator. They cannot describe low-income countries absent from that sample.',
        'The country-equal rates differ from pooled institution rates; both are supplied in the coverage table.',
        'Authorship intervals are recalculated by aggregating country credits in each of the original 2,000 shared whole-study bootstrap replicates. They condition on the original sample, weights and classifications. No new random draws or simulations were run.',
        'Income grouping measures national economic context and does not directly measure institutional resources or quality.',
        'A signed benchmark shift C need not reduce the absolute AF-reference difference. The B absolute-reduction contrast is supplied separately.',
        'Unique authorship-study support counts can overlap across income groups because international studies may involve several groups. They must not be added as disjoint counts.',
        'No income group was merged because of its results. No claim of equivalence follows from an interval spanning zero.',
        'All bootstrap intervals are pointwise; no adjustment for multiple comparisons was applied.',
        '',f'World Bank source: {WB_URL}',f'Classification context: {WB_CONTEXT}']
    text='\n'.join(lines)+'\n';(OUT/'results_and_methods.txt').write_text(text)
    # Publication prose is written after inspecting results; numerical sections remain directly reproducible.
    title='Income classification and AF participation'
    assets=''.join(f'<figure><img src="figures/{name}.svg" alt="{html.escape(label)}"><figcaption>{html.escape(label)}</figcaption></figure>' for name,label in [('income_output_crosswalk','Correspondence between original national output groups and World Bank FY2020 income groups.'),('authorship_by_income','Authorship contrasts, preserving both participation benchmarks and the original shared bootstrap.'),('institutional_coverage_by_income','Institutional coverage within each national income group, retaining domestic output groups.')])
    supportview=summary[['income_label','countries_in_original_68','baseline_institutions','AF_institutions_2025','original_68_AF_authorship_studies','all_classified_AF_authorship_studies']].rename(columns={'income_label':'Income group','countries_in_original_68':'Countries in main sample','baseline_institutions':'Baseline institutions','AF_institutions_2025':'AF institutions by 2025','original_68_AF_authorship_studies':'AF authorship studies, original scope','all_classified_AF_authorship_studies':'AF authorship studies, expanded scope'})
    links=''.join(f'<li><a href="tables/{name}.csv">{html.escape(label)}</a></li>' for name,label in [('country_income_mapping','Country mapping and scope'),('income_output_crosswalk','Output–income crosswalk'),('income_group_sample_summary','Sample sizes'),('authorship_representation','Authorship ratios'),('authorship_AF_minus_reference','AF–reference contrasts'),('authorship_benchmark_change','Paired benchmark changes'),('authorship_credit_shares','Participation and authorship shares'),('coverage_2025','2025 institutional coverage'),('coverage_by_income_group','Coverage trajectories'),('coverage_country_institution_group_year','Country-level source data')])
    report=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>{title}</title><style>body{{font-family:Arial,sans-serif;max-width:1120px;margin:48px auto;padding:0 30px;color:#242424;line-height:1.55}}h1{{font-size:30px}}h2{{font-size:21px;margin-top:35px}}p{{max-width:960px}}figure{{margin:36px 0}}img{{width:100%;height:auto}}figcaption{{font-size:13px;color:#555}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #ddd;padding:9px;text-align:right}}th:first-child,td:first-child{{text-align:left}}th{{background:#edf2f5}}pre{{white-space:pre-wrap;font:14px/1.55 Arial,sans-serif}}a{{color:#245b82}}</style><h1>{title}</h1><p>World Bank FY2020 classification, fixed across 2020–2025. The analysis retains the original publication samples, comparison weights and domestic institutional output groups.</p><p><strong>Sample limit:</strong> only Ethiopia and Uganda represent the low-income group in the 68-country institutional sample. The authorship figure separately shows a broader country-classification scope using the same studies.</p><h2>Sample coverage</h2>{supportview.to_html(index=False,border=0)}{assets}<h2>Methods and numerical results</h2><pre>{html.escape(text)}</pre><h2>Tables</h2><ul>{links}</ul><p><a href="supplementary_note2_addendum.txt">English text for Supplementary Note 2</a></p><p>Sources: <a href="{WB_URL}">World Bank historical classifications</a>; <a href="{WB_CONTEXT}">FY2020 classification explanation</a>.</p></html>'''
    (OUT/'report.html').write_text(report)

def provenance():
    import pycountry
    files=[F4/'draws/strict_main_joint_pools.npz',F4/'draws/strict_main_points.json',F4/'inputs/normalized/feature_metadata.json',F4/'inputs/normalized/credit.parquet',F4/'inputs/normalized/analysis_members.parquet',F4/'tables/strict_main_R.csv',F2/'country_context.csv',F2/'country_group_year_primary.csv',F2/'institution_baseline_and_first_participation.csv',F2/'Fig2a_cumulative.csv',OUT/'inputs/worldbank_income_history.xlsx']
    manifest=OUT/'provenance/input_manifest.json'
    if not manifest.exists():
        pins=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
        manifest.write_text(json.dumps(pins,indent=2))
    (OUT/'provenance/validation.json').write_text(json.dumps({'checks':assertions,'new_simulations':0,'original_bootstrap_replicates':2000,'authorship_seed':20262038,'classification':'WB FY2020; underlying calendar-year GNI 2018','python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'matplotlib':matplotlib.__version__,'duckdb':duckdb.__version__,'pycountry':pycountry.__version__},indent=2))
    (OUT/'requirements.txt').write_text('numpy\npandas\nopenpyxl\nmatplotlib\nduckdb\npycountry\n')

def main():
    meta=setup();mapping=country_mapping();data=np.load(OUT/'inputs/country_credits_and_joint_bootstrap.npz')
    verify_authorship(meta,data,mapping)
    ratios,differences,changes,shares=authorship(mapping,data)
    support=support_counts(mapping)
    cells,coverage,grad,inst_summary=institution_coverage(mapping)
    summary=population_table(mapping,support,inst_summary,shares)
    make_figures(mapping,differences,coverage,summary)
    reporting(summary,shares,differences,changes,coverage,grad,mapping)
    provenance()
    print('\nSAMPLE SUMMARY\n'+summary.to_string(index=False),flush=True)
    print('\n2025 COVERAGE\n'+coverage[coverage.year.eq(2025)].to_string(index=False),flush=True)
    print('\nAUTHORSHIP CONTRASTS\n'+differences.to_string(index=False),flush=True)
    print('\nALL CHECKS PASSED',len(assertions),flush=True)

if __name__=='__main__':
    main()
