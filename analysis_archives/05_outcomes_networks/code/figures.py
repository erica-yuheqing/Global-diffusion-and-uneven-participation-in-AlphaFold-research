"""All v2 registered panels, plotted directly from audited numerical outputs."""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.transforms import Bbox
from common import *
COL={'L':'#56B4E9','M':'#009E73','H':'#0072B2'};MARK={'L':'o','M':'s','H':'^'}
plt.rcParams.update({'font.family':'Arial','font.size':7,'axes.labelsize':7,'xtick.labelsize':6,'ytick.labelsize':6,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})
REG=[];CURRENT=[]
def read(name):return pd.read_csv(T/(name+'.csv'))
EST=None
def source(fid,panel,data,paths,status='completed',note=''):
 dest=D/'panels'/(fid+'_'+panel);dest.mkdir(parents=True,exist_ok=True)
 data=data.copy();data['figure_id']=fid;data['panel_id']=panel
 data.to_csv(dest/'coordinates.csv',index=False)
 fields=json.loads((P/'specification/config/input_data_contract.json').read_text())['source_summary_fields']
 summary=data.copy()
 if 'estimate' not in summary and len(data):
  groupcols=[k for k in ['group','outcome','series','stage','coordinate_type','sample_id'] if k in data and data[k].notna().any()]
  if not groupcols:groupcols=['figure_id','panel_id']
  output=[]
  for key,b in data.groupby(groupcols,dropna=False):
   key=key if isinstance(key,tuple) else (key,);row=dict(zip(groupcols,key));row['n_records']=len(b);row['status']=status;row['interval_type']='empirical_distribution_not_confidence_interval'
   if 'institution_id' in b:row['n_institutions']=b.institution_id.nunique()
   if 'study_id' in b:row['n_AF_unique']=b.study_id.nunique()
   if 'country' in b:row['n_countries']=b.country.nunique()
   candidates=[k for k in ['y','x','D_i','log_degree','retention','percent','AF_studies','mean_difference'] if k in b]+[k for k in b if k.startswith('delta_')]
   for col in dict.fromkeys(candidates):
    v=pd.to_numeric(b[col],errors='coerce').dropna()
    if len(v):
     for suffix,val in [('mean',v.mean()),('median',v.median()),('q25',v.quantile(.25)),('q75',v.quantile(.75)),('min',v.min()),('max',v.max())]:row[col+'_'+suffix]=val
   row['metric']='empirical_plot_data; see coordinate variables';output.append(row)
  summary=pd.DataFrame(output);summary['figure_id']=fid;summary['panel_id']=panel
 for old,new in [('n_af_works','n_AF_unique'),('n_control_works','n_controls_unique'),('n_controls_unique','n_controls_unique'),('n_links','n_affiliation_links')]:
  if old in summary and new not in summary:summary[new]=summary[old]
 if 'status' not in summary:summary['status']=status
 for k in fields:
  if k not in summary:summary[k]=np.nan
 summary[fields+[k for k in summary if k not in fields]].to_csv(dest/'summary.csv',index=False)
 links=[]
 for path in sorted(set(paths)):
  path=P/path;require(path.exists(),'Panel input missing: '+str(path));links.append({'role':'traceable_analytical_records_or_summary','path':os.path.relpath(path,dest),'sha256':sha(path)})
 pd.DataFrame(links).to_csv(dest/'records_index.csv',index=False)
 dump(dest/'lineage.json',{'figure_id':fid,'panel_id':panel,'inputs':links,'coordinates':'coordinates.csv','summary':'summary.csv','status':status,'note':note,'no_manual_numeric_edits':True,'null_summary_fields':'not applicable or recorded in linked row-level sources; not zero'})
 REG.append({'figure_id':fid,'panel_id':panel,'status':status,'reason':note,'source_data':str(dest.relative_to(P))})
def save(fig,fid,panels,level):
 folder=P/'figures'/level;folder.mkdir(parents=True,exist_ok=True)
 fig.legend([Line2D([],[],color=COL[g],marker=MARK[g],ls='none',ms=4) for g in COL],list(COL),loc='upper center',ncol=3,frameon=False,fontsize=7,bbox_to_anchor=(.53,1.0))
 fig.canvas.draw();renderer=fig.canvas.get_renderer()
 for ext in ['pdf','svg','png']:fig.savefig(folder/(fid+'.'+ext),dpi=300,facecolor='white')
 sub=folder/'panels';sub.mkdir(exist_ok=True)
 for letter,axes in panels.items():
  boxes=[a.get_tightbbox(renderer) for a in axes]+[t.get_window_extent(renderer) for t in fig.texts if t.get_text()==letter]
  box=Bbox.union(boxes).transformed(fig.dpi_scale_trans.inverted()).expanded(1.08,1.12)
  for ext in ['pdf','svg','png']:fig.savefig(sub/(fid+'_'+letter+'.'+ext),dpi=300,bbox_inches=box,facecolor='white')
 plt.close(fig);print('Exported',fid,flush=True)
def label(fig,letter,axes):
 x=min(a.get_position().x0 for a in axes);y=max(a.get_position().y1 for a in axes);fig.text(max(.012,x-.065),y+.018,letter,weight='bold',size=8)
def layout(fid,letters,height=145,left=.18):
 n=len(letters);rows=(n+1)//2;fig,axs=plt.subplots(rows,2,figsize=(180/25.4,height/25.4),squeeze=False)
 fig.subplots_adjust(left=left,right=.97,bottom=.10,top=.94,hspace=.75,wspace=.64)
 panels={l:[a] for l,a in zip(letters,axs.flat)}
 for l,axes in panels.items():label(fig,l,axes)
 for a in list(axs.flat)[n:]:a.remove()
 return fig,panels
def error(ax,r,y,g,open=False):
 if not np.isfinite(r.get('estimate',np.nan)):return
 lo,hi=r.get('lower',np.nan),r.get('upper',np.nan);v=r['estimate']
 ax.plot(v,y,MARK[g],color=COL[g],mfc='white' if open else COL[g],ms=3.2)
 if np.isfinite(lo) and np.isfinite(hi):ax.plot([lo,hi],[y,y],color=COL[g],lw=.85)
def forest(ax,rows,metric,unit,annotate=False):
 z=rows[rows.metric.eq(metric)];bounds=[0.]
 for y,g in enumerate(COL):
  zz=z[z.group.eq(g)]
  if zz.empty:continue
  r=zz.iloc[0];error(ax,r,y,g)
  bounds.extend([v for v in [r.estimate,r.lower,r.upper] if np.isfinite(v)])
  n=int(r.get('n_institutions',0));af=r.get('n_af_works',r.get('n_AF_unique',0))
  if annotate:ax.text(.98,y+.31,f'n={n:,} inst.; {int(af) if np.isfinite(af) else 0:,} AF',transform=ax.get_yaxis_transform(),ha='right',fontsize=5.6)
 ax.axvline(0,color='.55',ls='--',lw=.6);span=max(max(bounds)-min(bounds),3)
 ax.set(yticks=range(3),yticklabels=list(COL),ylim=(2.65,-.55),xlim=(min(bounds)-.12*span,max(bounds)+.12*span),xlabel=unit)
def compare(ax,rows,metric,names=None,labels=None):
 z=rows[rows.metric.eq(metric)].copy();names=names or list(z.sample_id.drop_duplicates());labels=labels or [n.replace('_',' ') for n in names]
 for y,name in enumerate(names):
  for j,g in enumerate(COL):
   b=z[z.sample_id.eq(name)&z.group.eq(g)]
   if len(b):error(ax,b.iloc[0],y+(j-1)*.19,g)
 ax.set(yticks=range(len(names)),yticklabels=labels,ylim=(len(names)-.45,-.65),xlabel='AF − reference (points)');ax.axvline(0,color='.5',ls='--',lw=.6);ax.tick_params(axis='y',labelsize=5.5)
 return z[z.sample_id.isin(names)]
def paired(ax,rows,names,labels=None):
 out=[]
 for k,metric in enumerate(['journal_position','percentile_12m']):
  z=rows[rows.metric.eq(metric)&rows.sample_id.isin(names)].copy();out.append(z)
  for y,name in enumerate(names):
   for j,g in enumerate(COL):
    b=z[z.sample_id.eq(name)&z.group.eq(g)]
    if len(b):error(ax,b.iloc[0],y+(j-1)*.18+(k-.5)*.07,g,open=k==1)
 ax.set(yticks=range(len(names)),yticklabels=labels or names,ylim=(len(names)-.4,-.65),xlabel='AF − reference (percentile points)');ax.axvline(0,c='.5',ls='--',lw=.6);ax.tick_params(axis='y',labelsize=5.3);ax.text(0,-.32,'Filled: journal; open: 12m citation',transform=ax.transAxes,fontsize=5.5)
 return pd.concat(out,ignore_index=True)
def ecdf(ax,sample,metric):
 z=pd.read_parquet(D/('institutions_'+sample+'.parquet'));out=[]
 for g in COL:
  for prefix,ls in [('AF_','-'),('REF_','--')]:
   b=z[z.group.eq(g)][['institution_id',prefix+metric]].dropna().sort_values(prefix+metric).copy();b['x']=b[prefix+metric];b['weight']=1/max(1,len(b));b['y']=np.arange(1,len(b)+1)/max(1,len(b));b['series']=prefix[:-1];b['group']=g;out.append(b)
   ax.step(b.x,b.y,where='post',color=COL[g],ls=ls,lw=.8)
 ax.set(xlim=(0,100),ylim=(0,1),xlabel='Institution mean percentile',ylabel='Cumulative institution share');ax.text(0,-.30,'Solid: AF; dashed: reference',transform=ax.transAxes,fontsize=5.5)
 return pd.concat(out,ignore_index=True)
def distrib(ax,sample,metric):
 z=pd.read_parquet(D/('institutions_'+sample+'.parquet'));records=[]
 for y,g in enumerate(COL):
  v=z.loc[z.group.eq(g),'delta_'+metric].dropna().to_numpy()
  if len(v)>1:
   body=ax.violinplot(v,positions=[y],vert=False,showextrema=False)['bodies'][0];body.set_facecolor(COL[g]);body.set_alpha(.25)
  if len(v):q=np.quantile(v,[.25,.5,.75]);ax.plot(q[[0,2]],[y,y],c=COL[g],lw=2);ax.plot(q[1],y,MARK[g],color=COL[g],ms=3);ax.text(.98,y+.3,f'n={len(v):,}',ha='right',transform=ax.get_yaxis_transform(),fontsize=6)
 ax.set(yticks=range(3),yticklabels=list(COL),ylim=(2.6,-.6),xlabel='Institution difference (percentile points)');ax.axvline(0,c='.5',ls='--',lw=.6)
 return z
def slope_rows(outcome,names,kind='own'):
 z=read('network_results_'+outcome);return z[z.sample_id.isin(names)&z.coefficient.eq('slope')&z.metric.eq('journal_position' if outcome=='journal' else 'percentile_12m')]
def network_compare(ax,names,labels=None,group=None):
 rows=[]
 for outcome,k in [('journal',0),('citation',1)]:
  z=slope_rows(outcome,names);z=z[z.group.eq(group)] if group else z;rows.append(z)
  for y,name in enumerate(names):
   for j,g in enumerate(COL):
    b=z[z.sample_id.eq(name)&z.group.eq(g)]
    if len(b):error(ax,b.iloc[0],y+(j-1)*.18+(k-.5)*.07,g,open=bool(k))
 ax.set(yticks=range(len(names)),yticklabels=labels or names,ylim=(len(names)-.4,-.7),xlabel='Difference slope (see scales in caption)');ax.axvline(0,c='.5',lw=.6,ls='--');ax.tick_params(axis='y',labelsize=5.3);ax.text(0,-.32,'Filled: journal; open: citation',transform=ax.transAxes,fontsize=5.5)
 return pd.concat(rows,ignore_index=True)
def main_figures():
 pri=read('primary_estimates');fig=plt.figure(figsize=(180/25.4,145/25.4));panels={}
 for l,y,sample,metrics,labels in [('a',.73,'journal_full2025',['journal_position','high_journal75'],['Journal percentile difference\n(percentile points)','Journal ≥75 difference\n(percentage points)']),('b',.42,'citation_max',['percentile_12m','high_citation90'],['12m citation percentile difference\n(percentile points)','Citation ≥90 difference\n(percentage points)'])]:
  axes=[fig.add_axes([.09,y,.37,.19]),fig.add_axes([.59,y,.37,.19])];panels[l]=axes
  for ax,m,lab in zip(axes,metrics,labels):forest(ax,pri[pri.sample_id.eq(sample)],m,lab,True)
  label(fig,l,axes);source('Fig6',l,pri[pri.sample_id.eq(sample)&pri.metric.isin(metrics)],[f'source_data/AF_records_{sample}.parquet',f'source_data/institutions_{sample}.parquet',f'tables/estimates/{sample}.csv'])
 cov=read('coverage_summary_2024');axes=[];coords=[]
 for j,(ev,lab) in enumerate([('af','≥1 AF study'),('venue','≥1 AF journal ≥75'),('citation','≥1 AF citation ≥90')]):
  ax=fig.add_axes([.09+j*.305,.11,.24,.18]);axes.append(ax)
  for y,g in enumerate(COL):
   r=cov[cov.group.eq(g)].iloc[0];lo,hi=r[ev+'_lower'],r[ev+'_upper'];ax.plot([lo,hi],[y,y],c=COL[g],lw=.8);ax.plot(lo,y,MARK[g],c=COL[g],ms=3);ax.plot(hi,y,MARK[g],mfc='white',mec=COL[g],ms=3);coords.append(dict(group=g,event=ev,estimate=lo,lower=lo,upper=hi,unit='percent',interval_type='confirmed_possible_record_bounds_not_CI',baseline_institutions={'L':17602,'M':14720,'H':15688}[g],n_countries=68,publication_window='2020–2024'))
  ax.set(xlim=(0,max(1,cov[ev+'_upper'].max()*1.12)),ylim=(2.5,-.5),yticks=range(3),yticklabels=list(COL),xlabel=lab+'\nInstitutional coverage (%)')
 label(fig,'c',axes);panels['c']=axes;source('Fig6','c',pd.DataFrame(coords),['source_data/coverage_events_2024.parquet','tables/coverage_country_group_2024.csv']);save(fig,'Fig6',panels,'main')
 fig=plt.figure(figsize=(180/25.4,200/25.4));panels={'a':[],'b':[]};coords={'a':[],'b':[]};paths={'a':[],'b':[]}
 for col,outcome in enumerate(['journal','citation']):
  metric='journal_position' if outcome=='journal' else 'percentile_12m'
  for kind,groups,ys,height,l in [('own',list(COL),[.755,.555,.355],.15,'a'),('partner',['L'],[.09],.17,'b')]:
   name='degree_'+kind;pt=pd.read_parquet(D/f'network_points_{outcome}_{name}.parquet');rows=slope_rows(outcome,[name]);raw=pd.read_parquet(D/f'network_records_{outcome}_{name}.parquet')
   # Main scatter provenance retains exact paper sets, counts and observed roster coverage.
   cc=con();cc.register('focal',raw);view(cc,'r',D/'control_links.parquet');nctrl=cc.execute('SELECT f.institution_id,count(DISTINCT r.study_id) n_control FROM focal f JOIN r USING(institution_id,year,subfield,work_type) WHERE r.'+metric+' IS NOT NULL GROUP BY 1').df();cc.close()
   pt=pt.merge(nctrl,on='institution_id',validate='one_to_one');pt['partner_coverage']=pt.institution_id.map(raw.groupby('institution_id').coverage.mean());pt['outcome']=outcome;pt['coordinate_type']='institution';coords[l].append(pt.rename(columns={'D_i':'y'}));paths[l]+=[f'source_data/network_records_{outcome}_{name}.parquet',f'source_data/network_points_{outcome}_{name}.parquet']
   for y,g in zip(ys,groups):
    ax=fig.add_axes([.11+col*.47,y,.36,height]);panels[l].append(ax);z=pt[pt.group.eq(g)];ax.scatter(z.x,z.D_i,s=8 if g!='H' else 5,c=COL[g],marker=MARK[g],alpha=.55 if g!='H' else .20,edgecolors='none',rasterized=False);ax.axhline(0,c='.55',ls='--',lw=.6)
    slope=rows[rows.group.eq(g)];nAF=raw.loc[raw.group.eq(g),'study_id'].nunique();ax.text(.02,.97,f'{g} · n={len(z):,} inst.; {nAF:,} AF',transform=ax.transAxes,va='top',fontsize=6)
    file=D/f'model_draws/{outcome}_{name}_{g}_{metric}.npz'
    if file.exists() and len(slope) and slope.iloc[0].status=='completed':
     values=np.load(file)['values'];values=values[np.isfinite(values).all(axis=1)];coef=read('network_results_'+outcome);b0=coef[coef.sample_id.eq(name)&coef.group.eq(g)&coef.metric.eq(metric)&coef.coefficient.eq('intercept')].estimate.iloc[0];b1=slope.estimate.iloc[0];xs=np.sort(z.x.unique());cuts=np.where(np.diff(xs)>max((xs[-1]-xs[0])*.15,1e-9))[0]+1
     for segment in np.split(xs,cuts):
      if len(segment)<2:continue
      xx=np.linspace(segment[0],segment[-1],80);scale=10 if kind=='partner' else 1;yy=b0+b1*xx/scale;vv=values[:,0,None]+values[:,1,None]*xx[None,:]/scale;lo,hi=np.quantile(vv,[.025,.975],axis=0);ax.fill_between(xx,lo,hi,color=COL[g],alpha=.16,lw=0);ax.plot(xx,yy,c=COL[g],lw=1)
      coords[l].append(pd.DataFrame({'outcome':outcome,'group':g,'coordinate_type':'conditional_M0_curve','x':xx,'y':yy,'lower':lo,'upper':hi,'interval_type':'pointwise_conditional_fixed_network_5000'}))
    ax.set(xlabel='Own baseline log(1 + degree)' if kind=='own' else 'AF partners’ baseline degree percentile',ylabel=('Journal' if outcome=='journal' else '12m citation')+' difference\n(percentile points)');ax.tick_params(labelsize=6)
 for l in panels:label(fig,l,panels[l]);source('Fig7',l,pd.concat(coords[l],ignore_index=True),paths[l],note='Equal-institution M0; pointwise conditional band, broken across x gaps >15% observed range. Partner main is L only; all observed partners scored and observed author roster covered, not publisher-certified completeness. Single-institution comparator in ED/S tables; never assigned partner=0.')
 save(fig,'Fig7',panels,'main')
def extended():
 for fid,sample,metric in [('ED_SI1','journal_full2025','journal_position'),('ED_SI2','citation_max','percentile_12m')]:
  fig,pp=layout(fid,'abcd',left=.16)
  z=ecdf(pp['a'][0],sample,metric);source(fid,'a',z,[f'source_data/institutions_{sample}.parquet'])
  z=distrib(pp['b'][0],sample,metric);source(fid,'b',z,[f'source_data/institutions_{sample}.parquet'],note='Violin = full institution distribution; bars = IQR, not confidence interval.')
  if fid=='ED_SI1':
   z=compare(pp['c'][0],EST,metric,['history_min1'],['History ≥1; common start']);paths=['source_data/historical_control_links.parquet','source_data/AF_records_history_min1.parquet'];names=['journal_max2024','common','journal_full2025'];labels=['2020–24 maximum','2020–24 common','2020–25 maximum']
  else:
   z=EST[EST.sample_id.eq('paired_12_24')&EST.metric.isin(['percentile_12m','percentile_24m'])].copy();z['sample_id']=z.metric;z['metric']='percentile_12m';compare(pp['c'][0],z,'percentile_12m',['percentile_12m','percentile_24m'],['12 months, same support','24 months, same support']);paths=['source_data/AF_records_paired_12_24.parquet'];names=['citation_max','common'];labels=['2020–24 maximum','2020–24 common']
  source(fid,'c',z,paths);z=compare(pp['d'][0],EST,metric,names,labels);source(fid,'d',z,['tables/T_SI3_estimates.csv']);save(fig,fid,pp,'extended')
 fig,pp=layout('ED_SI3','abcd',165,left=.20)
 ar=read('stable_author_estimates');z=paired(pp['a'][0],ar,['stable_authors'],['Stable authors (H only)']);pp['a'][0].text(0,.98,'L/M: no common support\nH: 453 authors / 288 inst. / 380 AF',transform=pp['a'][0].transAxes,va='top',fontsize=6);source('ED_SI3','a',z,['source_data/author_metrics.parquet','tables/stable_author_estimates.csv'])
 z=EST[EST.group.eq('L')&EST.sample_id.str.contains('_position_')].copy();z['sample_id']=z.sample_id.str.replace('journal_','',regex=False).str.replace('citation_','',regex=False);names=['position_any_first_last_corresponding','position_other_observed_positions'];z=paired(pp['b'][0],z,names,['Any first / last / corr.','Other known positions']);source('ED_SI3','b',z,['source_data/stratified_AF_links.parquet'])
 z=EST[EST.sample_id.str.contains('_cooperation_')].copy();z['sample_id']=z.sample_id.str.replace('journal_','',regex=False).str.replace('citation_','',regex=False);names=['cooperation_domestic_single','cooperation_domestic_multi','cooperation_international'];z=paired(pp['c'][0],z,names,['Domestic, single','Domestic, multiple','International']);source('ED_SI3','c',z,['source_data/stratified_AF_links.parquet'])
 z=pd.concat([read('ED_SI3_support_'+o) for o in ['journal','citation']],ignore_index=True);ax=pp['d'][0]
 for k,o in enumerate(['journal','citation']):
  b=z[z.outcome.eq(o)];ax.scatter(100*b.institutions_after/b.institutions_before,np.arange(len(b))+(k-.5)*.15,s=7,facecolors=[COL[g] for g in b.group] if k==0 else 'none',edgecolors=[COL[g] for g in b.group])
 ax.set(yticks=range(len(b)),yticklabels=[r.group+' '+r.stratum.replace('any_first_last_corresponding','role-any').replace('other_observed_positions','role-other').replace('domestic_','dom. ') for _,r in b.iterrows()],xlabel='Common-support institution retention (%)',xlim=(0,105));ax.tick_params(axis='y',labelsize=4.7);source('ED_SI3','d',z,['tables/ED_SI3_support_journal.csv','tables/ED_SI3_support_citation.csv']);save(fig,'ED_SI3',pp,'extended')
 fig,pp=layout('ED_SI4','abcd',175,left=.18);records=[];node=pd.read_parquet(D/'networks/baseline_B2/nodes.parquet');part=pd.read_parquet(D/'matched_comparisons.parquet')
 masks=[('B2 valid',node.institution_id),('AF participant',part.institution_id),('Journal matched',pd.read_parquet(D/'AF_records_journal_full2025.parquet').institution_id),('Citation matched',pd.read_parquet(D/'AF_records_citation_max.parquet').institution_id),('Journal network',pd.read_parquet(D/'network_points_journal_degree_own.parquet').institution_id),('Citation network',pd.read_parquet(D/'network_points_citation_degree_own.parquet').institution_id)]
 for k,(name,ids) in enumerate(masks):
  for g in COL:
   b=node[node.institution_id.isin(ids)&node.group.eq(g)&node.log_degree.notna()].copy();b=b.sort_values('log_degree');b['y']=np.arange(1,len(b)+1)/max(1,len(b));b['stage']=name;records.append(b);pp['a'][0].step(b.log_degree,b.y,color=COL[g],lw=.65,alpha=.3+.12*k,ls=['-',':','--','-.','-',':'][k])
 pp['a'][0].set(xlabel='Baseline log(1 + degree)',ylabel='Cumulative valid-node share');source('ED_SI4','a',pd.concat(records,ignore_index=True),['source_data/networks/baseline_B2/nodes.parquet','source_data/matched_comparisons.parquet'],note='Stage and group curves in coordinates; unknown baseline excluded from distribution but retained in support tables.')
 records=[]
 for outcome,k in [('journal',0),('citation',1)]:
  z=pd.read_parquet(D/f'network_points_{outcome}_degree_own.parquet');z['outcome']=outcome
  for series,marker in [('AF_mean','o'),('REF_mean','x')]:
   for g in COL:
    b=z[z.group.eq(g)];pp['b'][0].scatter(b.x,b[series],s=3,marker=marker,color=COL[g],alpha=.12 if g=='H' else .4)
  records.append(z)
 pp['b'][0].set(xlabel='Baseline log(1 + degree)',ylabel='Absolute institutional percentile');pp['b'][0].text(0,-.29,'Circle: AF; cross: reference; both outcomes',transform=pp['b'][0].transAxes,fontsize=5.2);source('ED_SI4','b',pd.concat(records,ignore_index=True),['source_data/network_points_journal_degree_own.parquet','source_data/network_points_citation_degree_own.parquet'])
 rows=[]
 for outcome in ['journal','citation']:
  z=read('network_adjusted_group_contrasts_'+outcome);m=slope_rows(outcome,['degree_own','degree_partner']);m=m.assign(model_id=m.sample_id);rows.append(pd.concat([z,m],ignore_index=True).assign(outcome=outcome))
 allm=pd.concat(rows,ignore_index=True);allm['sample_id']=allm.model_id;z=paired(pp['c'][0],allm,['degree_own','M1','M1_partner_sample','M2'],['M0 own','M1 adjusted','M1 partner sample','M2 + partner']);source('ED_SI4','c',z,['tables/T_SI9_network_models.csv'],note='Own slopes per log1p degree; group contrasts, not interaction coefficients. M1 partner sample and M2 identical records. Pooled partner coefficients in T-SI9, not mislabelled low-group effects.')
 z=network_compare(pp['d'][0],['degree_partner'],['Partner score / 10 percentile']);z=z[z.group.isin(['M','H'])];source('ED_SI4','d',z,['tables/T_SI8_partner_degree.csv','tables/network_results_journal.csv','tables/network_results_citation.csv'],note='All-group context/coverage in linked support table; main Fig7b restricts to L, M/H slopes retained here.');save(fig,'ED_SI4',pp,'extended')
def supplementary():
 # Shared helper retains unabridged panel inputs and plots actual estimates.
 def finish(fid,fig,pp):save(fig,fid,pp,'supplementary')
 fig,pp=layout('S_SI1','abcd',170,left=.20);flow=read('T_SI1_global_flow');ax=pp['a'][0];ax.axis('off');text='\n↓\n'.join(f'{r.stage.replace("_"," ")}: {r["count"]:,}' for _,r in flow.iloc[:4].iterrows());ax.text(0,1,text+'\n\nParallel outcome branches:\nJournal 2020–25 / citation 2020–24\nCommon = same-window intersection',va='top',fontsize=6.3);source('S_SI1','a',flow,['tables/T_SI1_global_flow.csv','inputs/approved_crosswalk.parquet','inputs/institutions.parquet'])
 f=read('T_SI1');z=f[f.window.eq('2020_2024')];names=['AF_participants','journal_matched','citation_matched','common']
 for j,g in enumerate(COL):pp['b'][0].plot(range(4),[z[z.group.eq(g)&z.sample_id.eq(n)].retention_percent.iloc[0] for n in names],MARK[g]+'-',c=COL[g],lw=.7,ms=3)
 pp['b'][0].set(xticks=range(4),xticklabels=['AF','Journal','Citation','Common'],ylabel='Fixed institution retention (%)',ylim=(0,None));source('S_SI1','b',f,['tables/T_SI1_country_group.csv'])
 z=read('T_SI1_overlapping_missingness');zz=z[z.window.eq('2020_2025')].pivot(index='reason',columns='group',values='percent').reindex(columns=list(COL));im=pp['c'][0].imshow(zz,aspect='auto',vmin=0,vmax=100,cmap='Blues');pp['c'][0].set(xticks=range(3),xticklabels=list(COL),yticks=range(len(zz)),yticklabels=[s.replace('_',' ') for s in zz.index]);pp['c'][0].tick_params(axis='y',labelsize=4.7);fig.colorbar(im,ax=pp['c'][0],fraction=.06,label='AF links (%)');source('S_SI1','c',z,['tables/T_SI1_overlapping_missingness.csv'])
 a=pd.read_parquet(D/'matched_comparisons.parquet');one=a.groupby(['institution_id','group']).study_id.nunique().reset_index(name='AF_n');z=one.groupby('group').AF_n.apply(lambda x:100*x.eq(1).mean()).reindex(list(COL));pp['d'][0].bar(list(COL),z,color=list(COL.values()));pp['d'][0].set(ylabel='Single-AF institutions (%)',ylim=(0,100));records=one.copy();records['median_journal_controls']=records.institution_id.map(a.groupby('institution_id').n_journal_position.median());records['median_citation_controls']=records.institution_id.map(a.groupby('institution_id').n_percentile_12m.median());source('S_SI1','d',records,['source_data/matched_comparisons.parquet','tables/T_SI4_control_reuse_journal.csv','tables/T_SI4_control_reuse_citation.csv'],note='Control-number distributions supplied in source records and T-SI4; no one-paper exclusion.');finish('S_SI1',fig,pp)
 fig,pp=layout('S_SI2','abcd',165,left=.19)
 for l,mode in zip('abcd',['precomputed_structure_use','prediction_run','method_or_tool_development','prediction_evaluation_or_validation']):
  z=EST[EST.sample_id.str.endswith('_activity_'+mode)].copy();z['sample_id']='activity';z=paired(pp[l][0],z,['activity'],[mode.replace('_','\n')]);source('S_SI2',l,z,['source_data/stratified_AF_links.parquet','tables/activity_assessability.csv'],note='Multi-label activities overlap. Unknown is not negative; independent activity-label validation not completed. Fewer than 10 institutions: point only.')
 finish('S_SI2',fig,pp)
 fig,pp=layout('S_SI3','abcd',180,left=.23);w=read('outcome_weighting');r=pd.concat([EST,w],ignore_index=True);names=['journal_full2025','journal_full2025_country_equal','journal_full2025_paper_equal','journal_institution_year','citation_max','citation_max_country_equal','citation_max_paper_equal','citation_institution_year'];z=paired(pp['a'][0],r,names,['J institution','J country','J study','J institution-year','C institution','C country','C study','C institution-year']);source('S_SI3','a',z,['tables/outcome_weighting.csv','tables/T_SI3_estimates.csv'])
 names=[o+s for o in ['journal','citation'] for s in ['_min5','_pub_quarter','_month']];z=paired(pp['b'][0],EST,names,['J ≥5 controls','J quarter','J month','C ≥5 controls','C quarter','C month']);source('S_SI3','b',z,['tables/T_SI3_estimates.csv'],note='Changed support, not pure reweighting; baseline and retained n in exact estimate rows.')
 z=paired(pp['c'][0],EST,['journal_max2024','citation_max','common','journal_full2025'],['J max 2020–24','C max 2020–24','Common 2020–24','J max 2020–25']);source('S_SI3','c',z,['tables/T_SI3_estimates.csv'])
 z=read('T_SI6_common_composition');ax=pp['d'][0]
 for j,o in enumerate(['journal','citation']):
  for k,series in enumerate(['AF_mean','REF_mean']):
   b=z[z.outcome.eq(o)].set_index('group').reindex(list(COL));ax.plot(np.arange(3)+(j-.5)*.13,b[series],'-' if k==0 else '--',color='.35',lw=.7);ax.scatter(np.arange(3)+(j-.5)*.13,b[series],s=12,facecolors=list(COL.values()) if k==0 else 'white',edgecolors=list(COL.values()))
 ax.set(xticks=range(3),xticklabels=list(COL),ylabel='Common-composition percentile',ylim=(0,100));ax.text(0,-.29,'Point only; solid AF, dashed reference\nJournal / citation slightly offset',transform=ax.transAxes,fontsize=5.2);source('S_SI3','d',z,['tables/T_SI6_group_gaps.csv','tables/T_SI6_common_composition.csv']);finish('S_SI3',fig,pp)
 fig,pp=layout('S_SI4','abc',170,left=.20)
 z=EST[(EST.sample_id.eq('journal_full2025')&EST.metric.isin(['high_journal75','high_journal90']))|EST.sample_id.eq('journal_official_Q1')].copy();z['sample_id']=z.metric;z['metric']='threshold';compare(pp['a'][0],z,'threshold',['high_journal75','high_journal90','official_best_Q1'],['Mean category ≥75','Mean category ≥90','Supplier best-category Q1']);source('S_SI4','a',z,['tables/T_SI3_estimates.csv'])
 z=EST[((EST.sample_id.eq('citation_max'))&EST.metric.isin(['high_citation90','high_citation95']))|EST.sample_id.isin(['citation_reference_min50','citation_reference_min200'])].copy();z['original_sample']=z.sample_id;z['sample_id']=z.sample_id+':'+z.metric;z=z[z.metric.isin(['high_citation90','high_citation95'])];z['metric']='threshold';compare(pp['b'][0],z,'threshold');source('S_SI4','b',z,['tables/reference_cells_min50.csv','tables/reference_cells_min200.csv','tables/T_SI3_estimates.csv'])
 z=compare(pp['c'][0],EST,'journal_position',['journal_full2025','journal_exclude_multidisciplinary'],['Primary journal','Exclude Multidisciplinary']);source('S_SI4','c',z,['source_data/AF_records_journal_exclude_multidisciplinary.parquet']);source('S_SI4','d',pd.DataFrame(columns=['estimate']),['inputs/citation_edges.parquet'],status='not_computable',note='No certified complete citing/cited author lists; no independent second historical journal metric source. No panel image or invented zeros.');finish('S_SI4',fig,pp)
 fig,pp=layout('S_SI5','abcdef',210,left=.19)
 for l,o in [('a','journal'),('b','citation')]:
  metric='journal_position' if o=='journal' else 'percentile_12m';z=EST[EST.sample_id.str.startswith(o+'_annual_')&EST.metric.eq(metric)].copy();z['year']=z.sample_id.str[-4:].astype(int)
  for g in COL:
   b=z[z.group.eq(g)].sort_values('year');ax=pp[l][0];ax.errorbar(b.year,b.estimate,yerr=[b.estimate-b.lower,b.upper-b.estimate],fmt=MARK[g]+'-',c=COL[g],ms=3,lw=.7,capsize=1)
  ax.axhline(0,c='.5',ls='--',lw=.6);ax.set(xticks=range(2020,2026),xlabel='Publication year',ylabel='AF − reference (percentile points)');source('S_SI5',l,z,['tables/T_SI3_estimates.csv'],note='Missing/low-support intervals remain missing; 2025 citation not mature, never plotted as zero.')
 opp=pd.read_parquet(D/'institution_opportunity.parquet');ax=pp['c'][0]
 for j,g in enumerate(COL):
  b=opp[opp.group.eq(g)];counts=b.first_AF_year.value_counts(normalize=True).sort_index();ax.plot(counts.index,counts*100,MARK[g]+'-',c=COL[g],ms=3,lw=.7)
 ax.set(xticks=range(2020,2026),xlabel='First observed AF year',ylabel='AF-participant institutions (%)',ylim=(0,None));source('S_SI5','c',opp,['source_data/institution_opportunity.parquet'],note='Active-year count distribution also retained in these complete institution records; no later observed study does not establish cessation.')
 ax=pp['d'][0];vals=[opp.loc[opp.group.eq(g),'AF_studies'] for g in COL];ax.boxplot(vals,positions=range(3),showfliers=True,flierprops={'markersize':1.4},widths=.45);ax.set(xticks=range(3),xticklabels=list(COL),ylabel='AF studies per institution',yscale='log');source('S_SI5','d',opp,['source_data/institution_opportunity.parquet'],note='Box: median/IQR; whiskers 1.5 IQR; every extreme shown, log count axis.')
 z=read('entry_opportunity_summary');ax=pp['e'][0]
 for j,g in enumerate(COL):
  for k,event in enumerate(['venue','citation']):
   b=z[z.group.eq(g)].sort_values('followup_months');x=b.followup_months+(j-1)*.6+(k-.5)*.2;ax.plot(x,100*b[event+'_confirmed'],MARK[g]+'-',c=COL[g],ms=3,lw=.7);ax.scatter(x,100*b[event+'_possible'],marker=MARK[g],s=10,facecolors='white',edgecolors=COL[g]);
 ax.set(xticks=[12,24],xlabel='Months since first observed AF',ylabel='Same-entrant outcome coverage (%)',ylim=(0,100));source('S_SI5','e',z,['source_data/entry_opportunity.parquet'],note='Same mature entry cohort; first date +36m ≤ citing cutoff. Filled confirmed, open possible bounds; venue and citation offset.')
 z=read('coverage_summary');ax=pp['f'][0]
 for j,g in enumerate(COL):
  for k,ev in enumerate(['af','venue']):
   b=z[z.group.eq(g)].sort_values('publication_end_year');x=b.publication_end_year+(j-1)*.05+(k-.5)*.02;ax.plot(x,b[ev+'_lower'],MARK[g]+'-',c=COL[g],ms=3,lw=.7);ax.scatter(x,b[ev+'_upper'],s=10,marker=MARK[g],facecolors='white',edgecolors=COL[g])
 ax.set(xticks=[2024,2025],xlabel='Window end year (from 2020)',ylabel='Fixed-population coverage (%)',ylim=(0,None));source('S_SI5','f',z,['source_data/coverage_events_2024.parquet','source_data/coverage_events_2025.parquet'],note='Only AF and venue events; no 2025 immature citation event. Filled confirmed/open possible; full country tables resolve overplotted classes.');finish('S_SI5',fig,pp)
 fig,pp=layout('S_SI6','abcd',170,left=.20);z=read('new_source_share')
 for g in COL:
  b=z[z.group.eq(g)];pp['a'][0].plot(b.year,100*b.mean_new_source_share,MARK[g]+'-',c=COL[g],ms=3,lw=.7)
 pp['a'][0].set(xlabel='Publication year',ylabel='Baseline-unseen source share (%)',ylim=(0,100));source('S_SI6','a',z,['source_data/new_source_with_history_status.parquet'])
 z=read('new_source_positions')
 for g in COL:
  for new,ls in [(True,'-'),(False,'--')]:
   b=z[z.group.eq(g)&z.source_not_observed_in_baseline.eq(new)];pp['b'][0].plot(b.year,b.journal_position,MARK[g]+ls,c=COL[g],ms=3,lw=.7)
 pp['b'][0].set(xlabel='Publication year',ylabel='Annual journal percentile',ylim=(0,100));source('S_SI6','b',z,['source_data/new_source_with_history_status.parquet'],note='Solid unseen source; dashed previously seen; does not establish genuinely first-ever publication in venue.')
 z=read('history_support');ax=pp['c'][0]
 for g in COL:
  b=z[z.group.eq(g)&z.history_status.eq('observed_support')];ax.plot(b.year,b.median_history_papers,MARK[g]+'-',c=COL[g],lw=.7,ms=3)
 ax.set(xlabel='Publication year',ylabel='Median comparable historical studies',ylim=(0,None));source('S_SI6','c',z,['source_data/new_source_with_history_status.parquet'],note='Historical years, metric coverage and no-support rows retained in source table; no history never substituted by another field/type.')
 z=compare(pp['d'][0],EST,'journal_position',['history_min1','history_min3','history_min5','history_min10'],['History ≥1','History ≥3','History ≥5','History ≥10']);source('S_SI6','d',z,['source_data/historical_control_links.parquet'],note='Original common-sample start. L n=23/7/1/0; n<10 points without stable intervals.');finish('S_SI6',fig,pp)
 fig,pp=layout('S_SI7','abcd',190,left=.25)
 specs=[('a',['degree_own','strength_own','strength_own_fixed_base','strength_own_fixed_alt'],['Degree','Fractional strength','Intersection: degree','Intersection: strength']),('b',['degree_own','rolling_own','rolling_own_fixed_base','rolling_own_fixed_alt'],['2015–19 baseline','3-year lagged','Intersection: baseline','Intersection: rolling']),('c',['degree_own','expanded_own','observed_covered_network_own','expanded_own_fixed_base','expanded_own_fixed_alt'],['B2 boundary','Expanded boundary','Observed-roster covered','Intersection: B2','Intersection: expanded']),('d',['degree_own','network_no_large_own','outcomes_no_large_own','both_no_large_own'],['Primary','Network excludes m>20','AF + controls exclude m>20','Both exclude m>20'])]
 for l,names,labels in specs:
  z=network_compare(pp[l][0],names,labels);source('S_SI7',l,z,['tables/network_results_journal.csv','tables/network_results_citation.csv','tables/T_SI8_network_registry.csv'],note='Own slopes per log1p network measure. All companion partner models and fixed-intersection versions in linked T-SI9; m>20 based on full observed roster, fractional m based on network boundary.')
 finish('S_SI7',fig,pp)
 fig,pp=layout('S_SI8','abcde',220,left=.23);a=pd.read_parquet(D/'matched_comparisons.parquet');rows=[]
 for o in ['journal','citation']:
  start=a[a.journal_support if o=='journal' else a.in_main_years&a.citation_support]
  for kind in ['own','partner']:
   z=pd.read_parquet(D/f'network_records_{o}_degree_{kind}.parquet');b=start.groupby(['country','group']).institution_id.nunique().rename('matched_institutions').reset_index();nn=z.groupby(['country','group']).institution_id.nunique().rename('network_institutions').reset_index();b=b.merge(nn,how='left',on=['country','group']).fillna({'network_institutions':0});b['outcome']=o;b['kind']=kind;b['retention']=100*b.network_institutions/b.matched_institutions;rows.append(b)
 z=pd.concat(rows,ignore_index=True);ax=pp['a'][0]
 for j,g in enumerate(COL):b=z[z.group.eq(g)];ax.scatter(b.retention,np.repeat(j,len(b)),c=COL[g],marker=MARK[g],s=9,alpha=.4)
 ax.set(yticks=range(3),yticklabels=list(COL),xlabel='Country/group outcome-to-network retention (%)',xlim=(0,105));source('S_SI8','a',z,['tables/T_SI8_partner_degree.csv','tables/network_support_journal.csv','tables/network_support_citation.csv'])
 records=[];ax=pp['b'][0]
 for o in ['journal','citation']:
  z=pd.read_parquet(D/f'network_records_{o}_degree_partner.parquet');b=z.groupby(['institution_id','group']).agg(V_i=('V_i','first'),log_degree=('x_log','first'),mean_team=('m_all','mean'),partner_mean=('partner_mean_percentile','mean')).reset_index();b['outcome']=o;records.append(b)
  for g in COL:
   v=b[b.group.eq(g)];ax.scatter(np.log1p(v.V_i),v.log_degree,c=COL[g],marker=MARK[g],s=4,alpha=.15)
 ax.set(xlabel='log(1 + baseline output)',ylabel='log(1 + baseline degree)');z=pd.concat(records,ignore_index=True);source('S_SI8','b',z,['source_data/network_records_journal_degree_partner.parquet','source_data/network_records_citation_degree_partner.parquet','tables/T_SI8_context.csv','tables/T_SI8_context_correlations.csv'],note='Baseline output/degree shown. Team/partner contextual distributions and correlations in T-SI8 context tables. Observed international-country proportion is computed separately, not inferred from partner count.')
 z=network_compare(pp['c'][0],['degree_partner','partial_any','partial80','partner_max'],['Complete observed partners','Scored-partners mean','Coverage ≥80%','Complete-partners maximum']);source('S_SI8','c',z,['source_data/partners_degree.parquet','tables/T_SI9_network_models.csv'],note='Slopes per 10 degree-percentile points. Partial support differs; outside-boundary partners never zero.')
 records=[];ax=pp['d'][0]
 for o in ['journal','citation']:
  z=pd.read_parquet(D/f'model_diagnostics_{o}_M1.parquet');z['outcome']=o;records.append(z)
  for g in COL:
   v=z[z.group.eq(g)];ax.scatter(v.fitted_difference,v.residual,c=COL[g],marker=MARK[g],s=3,alpha=.12)
 ax.axhline(0,c='.5',ls='--',lw=.6);ax.set(xlabel='M1 fitted difference',ylabel='Study–institution residual');source('S_SI8','d',pd.concat(records,ignore_index=True),['tables/network_adjusted_loco_journal.csv','tables/network_adjusted_loco_citation.csv','tables/network_overlap_journal.csv','tables/network_overlap_citation.csv','tables/T_SI9_network_models.csv'],note='High-leverage removal, exact leave-country point refits, shared-study/institution leverage, common-x overlap and fit ranks accompany residual plot; not a full deletion jackknife.')
 z=pd.concat([read('network_old_new_context_'+o).assign(outcome=o) for o in ['journal','citation']],ignore_index=True);ax=pp['e'][0];names=list(z.history_context.unique())
 for j,g in enumerate(COL):
  for k,o in enumerate(['journal','citation']):
   b=z[z.group.eq(g)&z.outcome.eq(o)].set_index('history_context').reindex(names);ax.scatter(b.mean_difference,np.arange(len(names))+(j-1)*.18+(k-.5)*.07,c=COL[g],marker=MARK[g],s=12)
 ax.set(yticks=range(len(names)),yticklabels=[n.replace('_','\n') for n in names],xlabel='Mean institution difference (points)');ax.axvline(0,c='.5',ls='--',lw=.6);source('S_SI8','e',z,['source_data/partner_contributions_main.parquet','source_data/network_old_new_institutions_journal.parquet','source_data/network_old_new_institutions_citation.parquet'],note='Point-only optional context; missing historical link does not prove first-ever cooperation.');finish('S_SI8',fig,pp)
def main():
 global EST
 EST=read('T_SI3_estimates');main_figures();extended();supplementary()
 registry=pd.read_csv(P/'specification/registry/panel_registry.csv',encoding='utf-8-sig');done=pd.DataFrame(REG);require(set(zip(registry.figure_id,registry.panel_id))==set(zip(done.figure_id,done.panel_id)),'Panel registry coverage differs');table('T_SI5_panel_status',done);dump(Q/'panel_status.json',REG)
if __name__=='__main__':main()
