"""Publication-size, title-free panels drawn only from saved analysis tables."""
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from PIL import Image,ImageCms
from common import *
BLUE='#4865BC';GC={'L':'#97AACF','M':BLUE,'H':'#183B75'};AC=dict(zip(AUTH,['#183B75','#617FC0','#A7BEDD']))
SHORT=['Structures','Runs','Development','Evaluation']
META=[];EXT=[]
def setup():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7.5,'axes.labelsize':7.5,'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.65,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})
def lab(ax,s):ax.text(-.12,1.06,s,transform=ax.transAxes,fontsize=11,weight='bold',va='bottom')
def grid(ax,axis='x'):ax.grid(axis=axis,color='#E5E8EE',lw=.45);ax.set_axisbelow(True)
def export(fig,folder,name):
    dest=OUT/'figures'/folder;dest.mkdir(parents=True,exist_ok=True)
    for ax in fig.axes:
        lo,hi=sorted(ax.get_xlim());ax.set_xticks([v for v in ax.get_xticks() if lo<=v<=hi])
        lo,hi=sorted(ax.get_ylim());ax.set_yticks([v for v in ax.get_yticks() if lo<=v<=hi])
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    for text in fig.findobj(matplotlib.text.Text):
        if text.get_visible() and text.get_text():
            bb=text.get_window_extent(renderer).transformed(fig.transFigure.inverted());EXT.append(dict(figure=name,text=text.get_text(),x0=bb.x0,y0=bb.y0,x1=bb.x1,y1=bb.y1))
    for ext in ['pdf','svg']:fig.savefig(dest/(name+'.'+ext))
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    p=dest/(name+'_600dpi.png');fig.savefig(p,dpi=600)
    with Image.open(p) as im:
        rgb=im.convert('RGB');rgb.save(p,dpi=(600,600),icc_profile=profile)
        rgb.save(dest/(name+'_600dpi.tiff'),dpi=(600,600),icc_profile=profile,compression='tiff_lzw')
        preview=rgb.copy();preview.thumbnail((1750,2100));preview.save(dest/(name+'_preview.png'))
        META.append(dict(folder=folder,figure=name,pixels=list(rgb.size),width_mm=183,height_mm=fig.get_figheight()*25.4,dpi=600))
    # Independent grouped main panels use the union of their participating axes.
    if folder=='main':
        from matplotlib.transforms import Bbox
        for letter,axes in fig._panel_axes.items():
            bb=Bbox.union([a.get_tightbbox(renderer) for a in axes]).transformed(fig.dpi_scale_trans.inverted()).expanded(1.02,1.025)
            fig.savefig(dest/(name+'_panel_'+letter+'.pdf'),bbox_inches=bb)
            pp=dest/(name+'_panel_'+letter+'_600dpi.png');fig.savefig(pp,dpi=600,bbox_inches=bb)
            with Image.open(pp) as im:im.convert('RGB').save(pp,dpi=(600,600),icc_profile=profile)
    plt.close(fig)
def page(rows,cols,height=150):
    f,axes=plt.subplots(rows,cols,figsize=(183/25.4,height/25.4),squeeze=False)
    f.subplots_adjust(left=.22,right=.97,top=.88,bottom=.23,wspace=.8,hspace=.85)
    for i,ax in enumerate(axes.ravel()):lab(ax,chr(97+i))
    return f,axes
def repeat_plot(ax,d,groups=('All','L','M','H')):
    for i,g in enumerate(groups):
        row=d[d.size_group.eq(g)&d.cohort.eq('All')].iloc[0];c=GC.get(g,BLUE)
        ax.plot([i,i],[100*row.fraction,100*row.upper],ls=':',color='#7B818C',lw=1.5)
        ax.scatter(i,100*row.upper,marker='_',color='#7B818C',s=35)
        ax.scatter(i,100*row.fraction,color=c,s=25,zorder=3)
        ax.text(i,100*row.upper+2,f'{row.C}/{row.N}\nU={row.U}',ha='center',fontsize=6.5)
    ax.set(xticks=range(len(groups)),xticklabels=groups,xlim=(-.5,len(groups)-.45),ylim=(0,72),ylabel='Confirmed repeat publication (%)',xlabel='Baseline output group');grid(ax,'y')
def use_transition(ax,d):
    for i,m in enumerate(MODES):
        row=d[d.activity.eq(m)].iloc[0];left=-100*row.not_reestablished_rate;right=100*row.new_rate
        ax.barh(i,left,color='#C28B5B',height=.47);ax.barh(i,right,color=BLUE,height=.47)
        ax.text(left-.6,i,f'{row.n10}',ha='right',va='center',fontsize=6.5);ax.text(right+.6,i,f'{row.n01}',ha='left',va='center',fontsize=6.5)
        ax.text(20,i,f'N={row.N}\nChanged {100*row.change_rate:.1f}%\nΔ={row.net_change_pp:+.1f} pp',va='center',fontsize=6)
    ax.axvline(0,color='#777',lw=.6);ax.set(yticks=range(4),yticklabels=SHORT,ylim=(3.6,-.6),xlim=(-23,34),xticks=[-20,-10,0,10],xticklabels=['20','10','0','10'],xlabel='Not re-established ←  %  → Newly established');grid(ax)
def author_plot(ax,d):
    for i,k in enumerate(AUTH):
        row=d[d.author_group.eq(k)].iloc[0];v=100*row.fraction;ax.barh(i,v,color=AC[k],height=.5)
        ax.text(v+1,i,f'{row.n}/{row.N}\n{v:.1f}%',va='center',fontsize=6.5)
    ax.set(yticks=range(3),yticklabels=['Initial only','Initial + other','No initial overlap'],xlim=(0,100),ylim=(2.7,-.7),xlabel='Author-assessable institutions (%)');grid(ax)
def matrix(ax,d,value='change_rate',conditional=False,author_colors=False):
    vals=np.full((4,3),np.nan);counts={}
    for i,m in enumerate(MODES):
        for j,k in enumerate(AUTH):
            row=d[d.activity.eq(m)&d.author_group.eq(k)].iloc[0]
            N=row.retention_N if value=='retention' else row.new_N if value=='new_establishment' else row.N
            n=row.n11 if value=='retention' else row.n01 if value=='new_establishment' else row.n01+row.n10
            vals[i,j]=100*getattr(row,value);counts[i,j]=(int(n),int(N))
    if author_colors:
        from matplotlib.colors import to_rgb
        colors=np.array([[np.array(to_rgb(AC[k]))*.20+.80 for k in AUTH] for _ in MODES]);ax.imshow(colors,aspect='auto')
    else:ax.imshow(np.ma.masked_invalid(vals),vmin=0,vmax=100,cmap='Blues',aspect='auto')
    for i in range(4):
        for j in range(3):
            n,N=counts[i,j];v=vals[i,j];ax.text(j,i,f'{v:.1f}%\n{n}/{N}' if N else 'NA\nN=0',ha='center',va='center',fontsize=6.2,color='white' if v>58 and not author_colors else '#20242C')
    ax.set(xticks=range(3),xticklabels=['Initial\nonly','Initial +\nother','No initial\noverlap'],yticks=range(4),yticklabels=SHORT);ax.tick_params(length=0)
def mainfig():
    f=plt.figure(figsize=(183/25.4,224/25.4));gs=f.add_gridspec(3,2,left=.14,right=.97,top=.965,bottom=.10,height_ratios=[1.2,1,1.1],hspace=.75,wspace=.6)
    sub=gs[0,:].subgridspec(1,2,width_ratios=[1.3,1],wspace=.32);a=f.add_subplot(sub[0,0]);ac=f.add_subplot(sub[0,1]);lab(a,'a')
    data=load('Fig3a_entry_uses').query('cohort=="All"')
    for i,m in enumerate(MODES):
        for j,g in enumerate(['L','M','H']):
            row=data[data.activity.eq(m)&data.size_group.eq(g)].iloc[0];y=i+(j-1)*.23
            a.scatter(100*row.fraction,y,s=20,color=GC[g],marker=['o','s','^'][j]);a.text(104,y,f'{row.Y}/{row.D}',va='center',fontsize=6,color=GC[g])
            ac.scatter(100*row.coverage,y,s=20,color=GC[g],marker=['o','s','^'][j]);ac.text(104,y,f'{row.D}/{row.N}',va='center',fontsize=6,color=GC[g])
    a.set(yticks=range(4),yticklabels=SHORT,xlim=(0,145),xticks=[0,25,50,75,100],ylim=(3.6,-.6),xlabel='Supported among assessable (%)')
    ac.set(yticks=[],xlim=(0,153),xticks=[0,25,50,75,100],ylim=(3.6,-.6),xlabel='Assessable among entrants (%)')
    grid(a);grid(ac)
    f.legend(handles=[Line2D([],[],color=GC[g],marker=mk,lw=0,label=f'{g} (entrants N={n:,})') for g,mk,n in [('L','o',332),('M','s',972),('H','^',4695)]],ncol=3,frameon=False,loc='upper center',bbox_to_anchor=(.54,.718),fontsize=7)
    b=f.add_subplot(gs[1,0]);lab(b,'b');repeat_plot(b,load('Fig3b_repeat12'))
    c=f.add_subplot(gs[1,1]);lab(c,'c');use_transition(c,load('Fig3c_use_transitions').query('cohort=="All" and size_group=="All"'))
    d=f.add_subplot(gs[2,0]);lab(d,'d');author_plot(d,load('Fig3d_author_groups').query('cohort=="All" and size_group=="All"'))
    d.text(.5,-.26,'Assessable: 1,312 / 2,137 (61.4%)',transform=d.transAxes,ha='center',fontsize=7)
    ee=f.add_subplot(gs[2,1]);lab(ee,'e');matrix(ee,load('Fig3e_author_use'),author_colors=True);ee.set_xlabel('Use-state change: n / paired N',labelpad=10)
    for tick,k in zip(ee.get_xticklabels(),AUTH):tick.set_color(AC[k])
    f._panel_axes={'a':[a,ac],'b':[b],'c':[c],'d':[d],'e':[ee]};export(f,'main','Figure3_a_e')
def ed5():
    f,axs=page(1,3,102);f.subplots_adjust(left=.10,wspace=.65,bottom=.28)
    data=load('ED5_annual_cohort_output');colors={'Pre-AF2':'#183B75','AF2':BLUE,'AF3':'#AFC4E4','Unknown':'#D5D7DB'}
    for j,col in enumerate(['institution_study_count','share']):
        ax=axs[0,j];bottom=np.zeros(6)
        for co,c in colors.items():
            q=data[data.entry_cohort.eq(co)].sort_values('year');v=q[col].to_numpy()*(100 if col=='share' else 1);ax.bar(q.year,v,bottom=bottom,color=c,width=.7,hatch='///' if co=='Unknown' else '',edgecolor='white',lw=.3);bottom+=v
        ax.set(xlabel='Publication year',ylabel='Institution–study count' if j==0 else 'Annual output share (%)',xticks=range(2020,2026));ax.tick_params(axis='x',rotation=45)
    ax=axs[0,2];q=load('ED5_growth_contributions').query('end==2025')
    for i,co in enumerate(colors):
        v=q[q.cohort.eq(co)].change.iloc[0];ax.bar(i,v,color=colors[co],hatch='///' if co=='Unknown' else '');ax.text(i,v+300,f'{v:+,}',ha='center',fontsize=6.5)
    ax.axhline(0,color='#555',lw=.6);ax.set(xticks=range(4),xticklabels=['Pre-AF2','AF2','AF3','Unknown'],ylabel='2025 − 2021 output count');ax.tick_params(axis='x',rotation=45)
    f.legend(handles=[Patch(facecolor=c,label=co,hatch='///' if co=='Unknown' else '') for co,c in colors.items()],ncol=4,loc='lower center',frameon=False,bbox_to_anchor=(.5,.02));export(f,'ED5','Extended_Data_Figure5')
def ed6():
    f=plt.figure(figsize=(183/25.4,204/25.4));gs=f.add_gridspec(3,2,left=.13,right=.96,top=.95,bottom=.12,hspace=.95,wspace=.45)
    data=load('ED6a_era_entry_uses')
    for j,co in enumerate(['AF2','AF3']):
        ax=f.add_subplot(gs[0,j]);lab(ax,'a' if j==0 else '');ax.text(.5,1.05,co+'-era entrants',transform=ax.transAxes,ha='center',fontsize=7)
        for k,g in enumerate(['L','M','H']):
            q=data[data.cohort.eq(co)&data.size_group.eq(g)].set_index('activity').loc[MODES]
            yy=np.arange(4)+(k-1)*.23;ax.scatter(100*q.fraction,yy,color=GC[g],marker=['o','s','^'][k],s=16,label=g)
            for i,row in enumerate(q.itertuples()):ax.text(104,yy[i],f'{row.Y}/{row.D}; {100*row.coverage:.0f}%',va='center',fontsize=5.2,color=GC[g])
        ax.set(yticks=range(4),yticklabels=SHORT if j==0 else [],ylim=(3.65,-.65),xticks=[0,50,100],xlim=(0,196),xlabel='Supported (%) | n/N; assessability');grid(ax)
        ax.legend(frameon=False,ncol=3,loc='upper center',bbox_to_anchor=(.5,-.28),fontsize=6)
    ax=f.add_subplot(gs[1,:]);lab(ax,'b');data=load('ED6b_entry_use_repeat').query('cohort=="All" and size_group in ["L","M","H"]')
    for i,m in enumerate(MODES):
        for k,g in enumerate(['L','M','H']):
            for state,marker in [('0','o'),('1','s')]:
                q=data[data.activity.eq(m)&data.size_group.eq(g)&data.entry_state.eq(state)].iloc[0];xx=i+(k-1)*.23+(-.045 if state=='0' else .045)
                ax.plot([xx,xx],[100*q.fraction,100*q.upper],color=GC[g],ls=':',lw=.7);ax.scatter(xx,100*q.fraction,color=GC[g],marker=marker,s=20,facecolors='white' if state=='0' else GC[g])
    ax.set(xticks=range(4),xticklabels=SHORT,ylim=(0,75),ylabel='Confirmed repeat within 12m (%)');grid(ax,'y')
    ax.legend(handles=[Line2D([],[],marker='o',mfc='white',color='#444',lw=0,label='Initial evidence not established'),Line2D([],[],marker='s',color='#444',lw=0,label='Initial supported')],frameon=False,loc='upper left',ncol=2,fontsize=6.5)
    ax=f.add_subplot(gs[2,:]);lab(ax,'c');data=load('ED6c_partner_context').query('cohort=="All" and size_group=="L" and entry_state=="1"');colors=['#C3D4E9','#4865BC','#6B8D86','#D4D5D8'];kinds=['single_institution','confirmed_H_partner','complete_no_H_partner','partner_unknown']
    for i,m in enumerate(MODES):
        bottom=0
        for kind,color in zip(kinds,colors):
            q=data[data.activity.eq(m)&data.partner_class.eq(kind)].iloc[0];v=100*q.fraction;ax.barh(i,v,left=bottom,color=color,height=.55)
            if v>=13:ax.text(bottom+v/2,i,f'{q.n}/{q.N}',ha='center',va='center',fontsize=6.5,color='white' if kind=='confirmed_H_partner' else '#222')
            bottom+=v
    ax.set(yticks=range(4),yticklabels=SHORT,xlim=(0,100),ylim=(3.6,-.6),xlabel='L institutions: initial supported study (%)')
    ax.legend(handles=[Patch(facecolor=c,label=n) for c,n in zip(colors,['Observed complete single institution','Confirmed H partner','Complete, no H partner','Unknown partner context'])],frameon=False,ncol=2,loc='upper center',bbox_to_anchor=(.5,-.35),fontsize=6.3)
    export(f,'ED6','Extended_Data_Figure6')
def ed7():
    f=plt.figure(figsize=(183/25.4,170/25.4));gs=f.add_gridspec(2,2,left=.14,right=.97,top=.94,bottom=.14,hspace=.8,wspace=.55)
    a=f.add_subplot(gs[0,0]);lab(a,'a');matrix(a,load('ED7_conditionals'),'retention');a.set_xlabel('Retained / initial supported')
    b=f.add_subplot(gs[0,1]);lab(b,'b');matrix(b,load('ED7_conditionals'),'new_establishment');b.set_xlabel('Newly established / initial not established')
    ax=f.add_subplot(gs[1,:]);lab(ax,'c');data=load('standardized_estimates')
    specs=[('ED7c_1_entry_cohort','Retained; era-standardized','o'),('ED7c_0_entry_cohort','New; era-standardized','s')]
    for i,m in enumerate(MODES):
        for j,k in enumerate(AUTH):
            for zz,(setting,name,mk) in enumerate(specs):
                row=data[data.analysis.eq(setting)&data.activity.eq(m)&data.compared_group.eq(k)].iloc[0]
                if pd.notna(row.fraction):ax.scatter(i+(j-1)*.20+(zz-.5)*.055,100*row.fraction,color=AC[k],marker=mk,s=25,facecolors=AC[k] if zz==0 else 'white')
    ax.set(xticks=range(4),xticklabels=SHORT,ylim=(0,105),ylabel='Direct-standardized conditional share (%)');grid(ax,'y')
    ax.text(.5,.12,'New establishment and development:\ninsufficient common-era support',transform=ax.transAxes,ha='center',fontsize=6.5,color='#666')
    ax.legend(handles=[Line2D([],[],marker=mk,mfc=BLUE if j==0 else 'white',color=BLUE,lw=0,label=name) for j,(_,name,mk) in enumerate(specs)],frameon=False,ncol=2,loc='upper center',bbox_to_anchor=(.5,-.23))
    export(f,'ED7','Extended_Data_Figure7')
def supplementary():
    f,axs=page(1,2,110);a,b=axs.ravel();flow=load('S1_flow').query('cohort=="All" and size_group=="All"').set_index('stage').n
    keys=['entry','complete12','confirmed_repeat','author_available','four_uses_available'];names=['Resolved entry','Complete 12m','Confirmed repeat','Authors assessable','Four uses assessable']
    a.barh(range(5),[flow[k] for k in keys],color=BLUE);a.set(yticks=range(5),yticklabels=names,ylim=(4.6,-.6),xlabel='Institutions')
    for i,k in enumerate(keys):a.text(flow[k]+30,i,f'{flow[k]:,}',va='center',fontsize=6.5)
    a.set_xlim(0,7300)
    q=load('S1_state_missingness').query('cohort=="All" and size_group=="All" and branch=="entry"').set_index('activity').loc[MODES];b.barh(range(4),100*(q.supported+q.not_established)/q.N,color=BLUE);b.set(yticks=range(4),yticklabels=SHORT,xlim=(0,100),ylim=(3.6,-.6),xlabel='Initial-use assessability (%)');export(f,'S1','F3_S1_sample_and_coverage')
    f=plt.figure(figsize=(183/25.4,165/25.4));gs=f.add_gridspec(2,2,left=.17,right=.97,top=.90,bottom=.16,hspace=1.05,wspace=.65)
    a=f.add_subplot(gs[0,0]);b=f.add_subplot(gs[0,1]);cc=f.add_subplot(gs[1,:]);lab(a,'a');lab(b,'b');lab(cc,'c');q=load('S2_evidence_coverage').groupby(['action_source','state']).n.sum().unstack(fill_value=0)
    bottom=np.zeros(len(q));colors=['#183B75','#B0C6E2','#DADDE1','#B78A57','#7A7A7A']
    for j,col in enumerate(q.columns):v=q[col].to_numpy();a.bar(range(len(q)),v,bottom=bottom,color=colors[j%5],label=col);bottom+=v
    a.set(xticks=range(len(q)),xticklabels=[v.replace('accepted_action_overlay','Overlay').replace('legacy_ab_exact_consensus','Legacy AB').replace('legacy_adjudicated','Legacy adjudicated').replace('new_candidate_core_only_acceptance','New core only').replace('unassessed_event_version','Unassessed') for v in q.index],ylabel='Institution–use evidence records');a.tick_params(axis='x',rotation=35,labelsize=6);a.legend(frameon=False,fontsize=5.5)
    s=load('S2_single_institution_entry').query('cohort=="All" and size_group=="All"').set_index('activity').loc[MODES];b.scatter(range(4),100*s.fraction,color=BLUE);b.set(xticks=range(4),xticklabels=SHORT,ylim=(0,105),ylabel='Supported: observed single-institution (%)');b.tick_params(axis='x',rotation=30);b.text(.5,-.36,'Independent accuracy: not yet annotated',transform=b.transAxes,ha='center',fontsize=6)
    cross=load('S2_reference_action_crosscheck').query('cohort=="All" and size_group=="All"')
    specs=[('model_seed_recorded',True,BLUE,'o','Model seed recorded'),('model_seed_recorded',False,BLUE,'s','Model: no recorded match'),('database_seed_recorded',True,'#167B6A','^','Database seed recorded'),('database_seed_recorded',False,'#167B6A','D','Database: no recorded match')]
    for j,(proxy,recorded,color,mk,name) in enumerate(specs):
        part=cross[cross.proxy.eq(proxy)&cross.proxy_state.eq('recorded_seed_match' if recorded else 'no_recorded_seed_match_not_proven_absence')];values=[]
        for m in MODES:
            z=part[part.activity.eq(m)].set_index('evidence_state');yes=z.loc['supported','n'];denom=yes+z.loc['not_established','n'];values.append(100*ratio(yes,denom))
        cc.scatter(np.arange(4)+(j-1.5)*.16,values,color=color,marker=mk,s=22,facecolors=color if recorded else 'white',label=name)
    cc.set(xticks=range(4),xticklabels=SHORT,ylim=(0,105),ylabel='Supported among assessable (%)');grid(cc,'y');cc.legend(frameon=False,ncol=2,fontsize=6.3,loc='upper center',bbox_to_anchor=(.5,-.24))
    export(f,'S2','F3_S2_evidence_and_attribution')
    f,axs=page(1,2,105);a,b=axs.ravel();q=load('S3_cooccurrence');v=q.pivot(index='activity_a',columns='activity_b',values='fraction').loc[MODES,MODES];a.imshow(100*v,vmin=0,vmax=100,cmap='Blues')
    for i in range(4):
        for j in range(4):a.text(j,i,f'{100*v.iloc[i,j]:.1f}%',ha='center',va='center',fontsize=6,color='white' if v.iloc[i,j]>.55 else '#222')
    a.set(xticks=range(4),xticklabels=['S','R','D','E'],yticks=range(4),yticklabels=SHORT)
    z=load('S3_complete_combinations').sort_values('n',ascending=False).head(8);b.barh(range(len(z)),z.n,color=BLUE);b.set(yticks=range(len(z)),yticklabels=z.combination,ylim=(len(z)-.4,-.6),xlabel='Four-use-assessable entrants');export(f,'S3','F3_S3_nonexclusive_cooccurrence')
    f,axs=page(1,2,110);a,b=axs.ravel();q=load('S4_common_windows').query('cohort=="All"')
    for g in ['All','L','M','H']:
        z=q[q.size_group.eq(g)].sort_values('months');a.plot(z.months,100*z.fraction,marker='o',color=GC.get(g,'#777'),label=g)
    a.set(xticks=[3,6,12],ylim=(0,65),xlabel='Calendar-month follow-up',ylabel='Confirmed repeat (%)');a.legend(frameon=False);grid(a,'y')
    q=load('S4_delayed').query('size_group in ["L","M","H"]')
    b.bar(np.arange(3)-.14,q.known_no6_confirmed12,width=.27,color=BLUE,label='Known no event at 6m');b.bar(np.arange(3)+.14,q.unknown6_confirmed12,width=.27,color='#C28B5B',label='Unknown at 6m');b.set(xticks=range(3),xticklabels=q.size_group,ylabel='Newly confirmed by 12m');b.legend(frameon=False,fontsize=6);export(f,'S4','F3_S4_windows_and_uncertainty')
    f,axs=page(1,2,120);a,b=axs.ravel();q=load('S5_use_sensitivity').query('cohort=="All" and size_group=="All"')
    for j,(key,label) in enumerate([('primary','Primary'),('no_same_day_ties','No same-day ties'),('four_categories_complete','All four assessable'),('both_explicit_overlay','Both overlays'),('month_end','Month-end'),('co_initial_union_distinct_estimand','Co-initial union')]):
        z=q[q.setting.eq(key)].set_index('activity').loc[MODES];a.scatter(z.net_change_pp,np.arange(4)+(j-2.5)*.1,s=15,marker=['o','s','^','D','x','v'][j],label=label)
    a.axvline(0,color='#888',ls='--',lw=.6);a.set(yticks=range(4),yticklabels=SHORT,xlabel='Later − initial use (pp)');a.legend(frameon=False,fontsize=5.7,loc='upper center',bbox_to_anchor=(.5,-.18),ncol=2)
    q=load('S5_extreme_missing_bounds').query('cohort=="All" and size_group in ["L","M","H"]')
    for i,m in enumerate(MODES):
        for j,g in enumerate(['L','M','H']):
            row=q[q.activity.eq(m)&q.size_group.eq(g)].iloc[0];y=i+(j-1)*.19;b.plot([100*row.lower,100*row.upper],[y,y],color=GC[g],lw=1);b.scatter(100*row.lower,y,color=GC[g],s=12)
    b.set(yticks=range(4),yticklabels=SHORT,xlim=(0,100),ylim=(3.6,-.6),xlabel='Extreme unknown-use bounds (%)');export(f,'S5','F3_S5_pairing_and_missingness')
    f,axs=page(1,2,105);a,b=axs.ravel();q=load('S6_author_opportunity')
    a.bar(range(3),q.median_initial_authors,color=[AC[k] for k in q.author_group]);a.set(xticks=range(3),xticklabels=['Initial only','Mixed','No overlap'],ylabel='Median initial local author count');a.tick_params(axis='x',rotation=25)
    b.bar(range(3),q.median_gap_days,color=[AC[k] for k in q.author_group]);b.set(xticks=range(3),xticklabels=['Initial only','Mixed','No overlap'],ylabel='Median pair interval (days)');b.tick_params(axis='x',rotation=25);export(f,'S6','F3_S6_author_opportunity')
    f,axs=page(1,2,110);a,b=axs.ravel();q=load('S7_continuous_scale')
    for i,m in enumerate(MODES):
        z=q[q.activity.eq(m)].sort_values('scale_bin');a.plot(z.scale_bin,100*z.fraction,marker=['o','s','^','D'][i],label=SHORT[i])
    a.set(xticks=range(1,6),ylim=(0,105),xlabel='Domestic baseline-output percentile bin',ylabel='Initial supported use (%)');a.legend(frameon=False,fontsize=6)
    q=load('S7_dependency_components').component.value_counts().sort_values(ascending=False).head(10);b.bar(range(len(q)),q.to_numpy(),color=BLUE);b.set(xlabel='Largest dependency components (ordered)',ylabel='Institutions');export(f,'S7','F3_S7_scale_and_shared_studies')
def main():
    setup();mainfig();ed5();ed6();ed7();supplementary();dump(OUT/'provenance/figure_metadata.json',META);dump(OUT/'provenance/text_extents.json',EXT)
    print(f'Exported {len(META)} figure groups, vector and native 600dpi RGB/sRGB rasters',flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--package-root',type=Path);parser.add_argument('--output-root',type=Path);args=parser.parse_args()
    if args.package_root:
        import common as context
        source=args.package_root
        def load(name):return pd.read_parquet(source/'tables'/f'{name}.parquet')
    if args.output_root:OUT=args.output_root;(OUT/'provenance').mkdir(parents=True,exist_ok=True)
    main()
