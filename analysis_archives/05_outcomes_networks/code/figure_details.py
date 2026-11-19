"""Readable companion views for dense multivariate registered panels."""
from figures import *
from matplotlib.patches import Rectangle
def keep_source(fid,panel,data,paths,note):
 dest=D/'panels'/(fid+'_'+panel);data.to_csv(dest/'detail_coordinates.csv',index=False)
 info=json.loads((dest/'lineage.json').read_text());info['companion_coordinates']='detail_coordinates.csv';info['companion_note']=note;info['additional_inputs']=[{'path':os.path.relpath(P/p,dest),'sha256':sha(P/p)} for p in paths];dump(dest/'lineage.json',info)
def main():
 # Replace ED4's illegible pooled absolute-outcome cloud with outcome-specific axes.
 fig=plt.figure(figsize=(180/25.4,215/25.4));pp={};allrecords=[]
 ax=fig.add_axes([.19,.77,.58,.17]);nax=fig.add_axes([.81,.77,.16,.17]);nax.set(xlim=(-.5,2.5),ylim=(5.6,-.7));nax.axis('off');pp['a']=[ax,nax];node=pd.read_parquet(D/'networks/baseline_B2/nodes.parquet');a=pd.read_parquet(D/'matched_comparisons.parquet')
 stages=[('B2',set(node.institution_id)),('AF participant',set(a.institution_id)),('Journal matched',set(a.loc[a.journal_support,'institution_id'])),('Citation matched',set(a.loc[a.citation_support&a.in_main_years,'institution_id'])),('Journal own network',set(pd.read_parquet(D/'network_points_journal_degree_own.parquet').institution_id)),('Citation own network',set(pd.read_parquet(D/'network_points_citation_degree_own.parquet').institution_id))]
 for y,(name,ids) in enumerate(stages):
  for j,g in enumerate(COL):
   z=node[node.group.eq(g)&node.institution_id.isin(ids)&node.log_degree.notna()];v=z.log_degree;pos=y+(j-1)*.28;q=v.quantile([.25,.5,.75]);ax.plot([q.iloc[0],q.iloc[2]],[pos,pos],c=COL[g],lw=1);ax.plot(q.iloc[1],pos,MARK[g],c=COL[g],ms=3);nax.text(j,y,f'{len(v):,}',fontsize=5.2,va='center',ha='center');allrecords.append(z.assign(stage=name,coordinate_type='distribution_records'))
 [nax.text(j,-.6,g,ha='center',fontsize=6,color=COL[g]) for j,g in enumerate(COL)];ax.set(yticks=range(6),yticklabels=[x[0].replace('Journal own network','Journal network').replace('Citation own network','Citation network') for x in stages],ylim=(5.6,-.7),xlabel='Baseline log(1 + degree): median / IQR');ax.tick_params(axis='y',labelsize=6)
 axes=[];records=[]
 for j,outcome in enumerate(['journal','citation']):
  ax=fig.add_axes([.12+j*.45,.51,.34,.17]);axes.append(ax);z=pd.read_parquet(D/f'network_points_{outcome}_degree_own.parquet');z['outcome']=outcome
  for g in COL:
   b=z[z.group.eq(g)]
   for series,marker in [('AF_mean','o'),('REF_mean','x')]:ax.scatter(b.x,b[series],s=3,marker=marker,c=COL[g],alpha=.14 if g=='H' else .40)
  ax.set(xlabel='Baseline log(1 + degree)',ylabel=('Journal' if j==0 else '12m citation')+' percentile',ylim=(0,100));ax.text(0,-.32,'Circle: AF; cross: reference',transform=ax.transAxes,fontsize=5.6);records.append(z)
 pp['b']=axes
 axes=[];modeldata=[]
 for j,outcome in enumerate(['journal','citation']):
  ax=fig.add_axes([.12+j*.45,.285,.34,.125]);axes.append(ax);z=read('network_adjusted_group_contrasts_'+outcome);m=slope_rows(outcome,['degree_own']);m['model_id']='M0';z=pd.concat([z,m],ignore_index=True);z['sample_id']=z.model_id;metric='journal_position' if j==0 else 'percentile_12m';compare(ax,z,metric,['M0','M1','M1_partner_sample','M2'],['M0 own','M1','M1 same partner set','M2 + partners']);ax.set_xlabel(('Journal' if j==0 else 'Citation')+' own slope / log1p degree');modeldata.append(z)
 pp['c']=axes
 ax=fig.add_axes([.12,.055,.34,.11]);ax2=fig.add_axes([.64,.055,.30,.11]);pp['d']=[ax,ax2];rows=[]
 for j,o in enumerate(['journal','citation']):
  z=slope_rows(o,['degree_partner']);z=z[z.group.isin(['M','H'])];rows.append(z)
  for y,g in enumerate(['M','H']):error(ax,z[z.group.eq(g)].iloc[0],y+(j-.5)*.15,g,bool(j))
 ax.set(yticks=[0,1],yticklabels=['M','H'],ylim=(1.5,-.5),xlabel='Partner slope / 10 percentile points');ax.axvline(0,c='.5',ls='--',lw=.6)
 support=read('T_SI8_partner_degree');counts=support.groupby(['group','status']).AF_links.sum().unstack(fill_value=0).reindex(list(COL));left=np.zeros(3);colors=plt.cm.tab20(np.linspace(0,1,len(counts.columns)))
 for k,name in enumerate(counts.columns):v=100*counts[name]/counts.sum(axis=1);ax2.barh(range(3),v,left=left,color=colors[k],height=.6,label={'valid_observed_roster_all_partners_scored':'Observed roster + scores covered','outside_boundary':'Outside boundary','observed_author_affiliations_incomplete':'Observed author roster incomplete','single_institution':'Single institution','focal_not_in_roster':'Focal not in roster'}[name]);left+=v
 ax2.set(yticks=range(3),yticklabels=list(COL),xlabel='All observed AF links by context (%)',xlim=(0,100));ax2.invert_yaxis();ax2.legend(fontsize=4.8,loc='lower center',bbox_to_anchor=(.45,1.12),ncol=2,frameon=False)
 for l in pp:label(fig,l,pp[l])
 source('ED_SI4','a',pd.concat(allrecords,ignore_index=True),['source_data/networks/baseline_B2/nodes.parquet','source_data/matched_comparisons.parquet'],note='Complete empirical distributions retained; plotted points are medians, bars IQR, not CI. Unknown baseline excluded from distribution and explicitly counted in support tables.')
 source('ED_SI4','b',pd.concat(records,ignore_index=True),['source_data/network_points_journal_degree_own.parquet','source_data/network_points_citation_degree_own.parquet'],note='Journal and citation shown separately on exactly their own Fig7a institution sets; absolute percentile starts at0.')
 source('ED_SI4','c',pd.concat(modeldata,ignore_index=True),['tables/T_SI9_network_models.csv'],note='Outcome-specific adjusted group slopes; same-partner M1/M2. Pooled partner term retained in T-SI9, not interpreted as L-specific.')
 source('ED_SI4','d',pd.concat(rows,ignore_index=True),['tables/T_SI8_partner_degree.csv','tables/T_SI9_network_models.csv'],note='Filled journal/open citation; context bars use all2020–2025 AF links and stages are mutually exclusive; raw partner status counts in linked table.')
 keep_source('ED_SI4','d',support,['tables/T_SI8_partner_degree.csv'],'Context counts are AF relation counts, not unique studies.');save(fig,'ED_SI4',pp,'extended')
 # S1a/d and S5c/S6c companions expose all required diagnostics without tiny insets.
 fig,pp=layout('S_SI1_details','abcd',170,left=.23);flow=read('T_SI1_global_flow');a=pd.read_parquet(D/'matched_comparisons.parquet');ax=pp['a'][0];ax.axis('off')
 text='Approved study bridge\n'+'\n'.join(f'{r.stage}: {r["count"]:,}' for _,r in flow.iterrows())+'\nAF with observed B2 affiliation: '+f'{a.study_id.nunique():,}'
 ax.text(0,1,text,va='top',fontsize=6);keep_source('S_SI1','a',flow,['tables/T_SI1_global_flow.csv'],'Companion shows full parallel-window counts and B2 mapping; not a single sequential attrition chain.')
 f=read('T_SI1');f=f[f.window.eq('2020_2024')];ax=pp['b'][0]
 for j,g in enumerate(COL):
  z=f[f.group.eq(g)];names=['AF_participants','journal_matched','citation_matched','common'];v=[z[z.sample_id.eq(n)].n_institutions.iloc[0] for n in names];ax.plot(range(4),v,MARK[g]+'-',c=COL[g],ms=3,lw=.7)
 ax.set(xticks=range(4),xticklabels=['AF','Journal','Citation','Common'],ylabel='Institutions (same2020–24 window)',yscale='log')
 ax=pp['c'][0]
 for j,g in enumerate(COL):
  b=a[a.group.eq(g)].groupby('institution_id').n_journal_position.median().dropna();v=np.sort(b);ax.step(v,np.arange(1,len(v)+1)/max(1,len(v)),color=COL[g],lw=.8)
 ax.set(xlabel='Institution median journal-control count',ylabel='Cumulative institution share',xscale='log',ylim=(0,1))
 ax=pp['d'][0]
 for j,g in enumerate(COL):
  b=a[a.group.eq(g)&a.in_main_years].groupby('institution_id').n_percentile_12m.median().dropna();v=np.sort(b);v=v[v>0];ax.step(v,np.arange(1,len(v)+1)/max(1,len(v)),color=COL[g],lw=.8)
 ax.set(xlabel='Institution median citation-control count',ylabel='Cumulative institution share',xscale='log',ylim=(0,1));keep_source('S_SI1','d',a.groupby(['institution_id','group']).agg(AF_studies=('study_id','nunique'),journal_controls=('n_journal_position','median'),citation_controls=('n_percentile_12m','median')).reset_index(),['source_data/matched_comparisons.parquet'],'Control count distributions; all eligible counts remain, displayed log axes omit only count0 (no reference support).');save(fig,'S_SI1_details',pp,'supplementary')
 fig,pp=layout('S_SI5_activity_year_details','ab',82,left=.17);opp=pd.read_parquet(D/'institution_opportunity.parquet')
 for l,col,lab in [('a','first_AF_year','First observed AF publication year'),('b','observed_AF_years','Observed active AF years')]:
  ax=pp[l][0]
  for g in COL:
   v=opp.loc[opp.group.eq(g),col].value_counts(normalize=True).sort_index();ax.plot(v.index,v*100,MARK[g]+'-',c=COL[g],ms=3,lw=.7)
  ax.set(xlabel=lab,ylabel='AF-participant institutions (%)',ylim=(0,None))
 keep_source('S_SI5','c',opp,['source_data/institution_opportunity.parquet'],'Companion separates entry-year and observed active-year distributions; not survival or cessation.');save(fig,'S_SI5_activity_year_details',pp,'supplementary')
 hist=pd.read_parquet(D/'new_source_with_history_status.parquet');fig,pp=layout('S_SI6_history_details','abcd',150,left=.19);records=[]
 h=hist.drop_duplicates(['institution_id','group','subfield','work_type']);
 for l,col,lab in [('a','history_n','Comparable historical study count'),('b','history_years','Comparable historical publication years')]:
  ax=pp[l][0]
  for g in COL:
   v=np.sort(h.loc[h.group.eq(g),col].dropna());ax.step(v,np.arange(1,len(v)+1)/max(1,len(v)),color=COL[g],lw=.8)
  ax.set(xlabel=lab,ylabel='Cumulative institution-field-type share',ylim=(0,1))
  if col=='history_n':ax.set_xscale('symlog',linthresh=1)
 ax=pp['c'][0];z=h.groupby('group').history_n.apply(lambda v:100*(v.isna()|v.eq(0)).mean()).reindex(list(COL));ax.bar(list(COL),z,color=list(COL.values()));ax.set(ylabel='No comparable historical support (%)',ylim=(0,100))
 ax=pp['d'][0];z=hist.groupby('group').journal_position.apply(lambda v:100*v.notna().mean()).reindex(list(COL));ax.bar(list(COL),z,color=list(COL.values()));ax.set(ylabel='Current AF journal-position coverage (%)',ylim=(0,100));keep_source('S_SI6','c',h,['source_data/new_source_with_history_status.parquet'],'Institution×subfield×type historical support, not whole-institution mixed-field history; observed zero/no support explicit.');save(fig,'S_SI6_history_details',pp,'supplementary')
 # Model diagnostics: all group slopes, country influence ranges and common-x support.
 fig,pp=layout('S_SI8_model_details','abcd',175,left=.22);allrows=[]
 for o in ['journal','citation']:
  z=read('network_adjusted_group_contrasts_'+o);z=z[z.model_id.isin(['M1','M1_without_high_leverage'])];z['sample_id']=z.model_id;allrows.append(z)
 z=pd.concat(allrows,ignore_index=True);paired(pp['a'][0],z,['M1','M1_without_high_leverage'],['M1 complete formula','Remove high leverage']);pp['a'][0].set_xlabel('Own slope (points / log1p degree)')
 loco=pd.concat([read('network_adjusted_loco_'+o).assign(outcome=o) for o in ['journal','citation']],ignore_index=True);ax=pp['b'][0]
 for j,g in enumerate(COL):
  for k,o in enumerate(['journal','citation']):
   b=loco[loco.group.eq(g)&loco.outcome.eq(o)&loco.model_id.eq('M1')];ax.scatter(b.estimate,np.repeat(j+(k-.5)*.15,len(b)),s=8,facecolors=COL[g] if k==0 else 'white',edgecolors=COL[g],marker=MARK[g],alpha=.65)
 ax.set(yticks=range(3),yticklabels=list(COL),xlabel='Leave-one-country M1 own slopes');ax.axvline(0,c='.5',ls='--',lw=.6)
 overlap=pd.concat([read('network_overlap_'+o).assign(metric='journal_position' if o=='journal' else 'percentile_12m') for o in ['journal','citation']],ignore_index=True);paired(pp['c'][0],overlap,['common_x_overlap_own','common_x_overlap_partner'],['Observed three-group own overlap','Observed three-group partner overlap']);pp['c'][0].set_xlabel('Slope: own / log1p degree;\npartner / 10 percentile points')
 ax=pp['d'][0];context=read('T_SI8_context_correlations');v=context[context.outcome.eq('journal')&context.method.eq('spearman')&context.group.eq('L')].pivot(index='x',columns='y',values='correlation');im=ax.imshow(v,vmin=-1,vmax=1,cmap='RdBu_r');labels=[x.replace('log_baseline_output','Baseline output').replace('log_degree','Degree').replace('international_share','International share').replace('mean_team_size','Team size').replace('partner_mean','Partner score') for x in v.columns];ax.set(xticks=range(len(v)),xticklabels=labels,yticks=range(len(v)),yticklabels=labels);plt.setp(ax.get_xticklabels(),rotation=45,ha='right',fontsize=5);ax.tick_params(axis='y',labelsize=5);cb=fig.colorbar(im,ax=ax,fraction=.05,ticks=[-1,0,1]);cb.ax.yaxis.set_ticks_position('left')
 keep_source('S_SI8','d',pd.concat([z,overlap],ignore_index=True),['tables/network_adjusted_loco_journal.csv','tables/network_adjusted_loco_citation.csv','tables/network_overlap_support_journal.csv','tables/network_overlap_support_citation.csv','tables/T_SI8_context_correlations.csv'],'Companion includes all high-leverage group estimates, exact point leave-country refits, common-x overlap and correlations. All groups/outcomes correlations in T-SI8.');save(fig,'S_SI8_model_details',pp,'supplementary')
 print('READABLE DIAGNOSTIC COMPANIONS AND ED4 REFINE COMPLETE',flush=True)
if __name__=='__main__':main()
