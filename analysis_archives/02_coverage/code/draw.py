"""Six v7 figures, 21 panels, native vectors and 600dpi RGB/sRGB rasters."""
from common import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from PIL import Image,ImageCms,ImageDraw

FIGURES={'Figure2_a_e':'main','ED3_a_b':'extended','ED4_a_b':'extended','S8_a_d':'supplementary','S9_a_d':'supplementary','S10_a_d':'supplementary'}
def style():return plt.rc_context({'font.family':'Arial','font.size':8,'axes.labelsize':8,'xtick.labelsize':7.5,'ytick.labelsize':7.5,'legend.fontsize':7.5,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'lines.linewidth':1.2,'lines.markersize':3.5,'pdf.fonttype':42,'svg.fonttype':'none','figure.facecolor':'white','savefig.facecolor':'white'})
def letter(fig,s,x,y):fig.text(x,y,s,weight='bold',fontsize=10,va='top')
def grid(ax,axis='y'):ax.set_axisbelow(True);ax.grid(axis=axis,color='#E3E6E9',lw=.4)
def export(fig,out,name):
    folder=out/'figures'/FIGURES[name];fig.canvas.draw();renderer=fig.canvas.get_renderer();skip=set()
    for ax in fig.axes:
        for axis in [ax.xaxis,ax.yaxis]:
            lo,hi=sorted(axis.get_view_interval())
            for tick in axis.get_major_ticks():
                if not lo-1e-8<=tick.get_loc()<=hi+1e-8:skip|={id(tick.label1),id(tick.label2)}
    bounds=[]
    for t in fig.findobj(matplotlib.text.Text):
        if t.get_visible() and t.get_text().strip() and id(t) not in skip:
            b=t.get_window_extent(renderer);bounds.append({'text':t.get_text(),'x0':b.x0/fig.bbox.width,'x1':b.x1/fig.bbox.width,'y0':b.y0/fig.bbox.height,'y1':b.y1/fig.bbox.height})
    dump(out/'quality'/f'{name}_text_extents.json',bounds)
    for ext in ['pdf','svg']:fig.savefig(folder/(name+'.'+ext),dpi=600)
    p=folder/(name+'_600dpi.png');fig.savefig(p,dpi=600)
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with Image.open(p) as im:
        rgb=im.convert('RGB');rgb.save(p,dpi=(600,600),icc_profile=icc);rgb.save(folder/(name+'_600dpi.tiff'),dpi=(600,600),icc_profile=icc,compression='tiff_lzw')
        prev=rgb.resize((1550,round(rgb.height*1550/rgb.width)),Image.Resampling.LANCZOS);prev.save(folder/(name+'_preview.png'))
        dump(out/'quality'/f'{name}_metadata.json',{'physical_mm':fig.get_size_inches()*25.4,'pixels':rgb.size,'dpi':600,'mode':'RGB','sRGB':True,'native_render':True,'panels':'letters_only'})
    plt.close(fig)

def main(out):
    a=read(out,'Fig2a_cumulative.csv','ready');b=read(out,'Fig2b_ratio.csv','ready');c=read(out,'Fig2c_gap.csv','ready');draws=read(out,'Fig2d_benchmark_draws.csv','ready');summ=read(out,'Fig2d_benchmark_summary.csv','ready').iloc[0];e=read(out,'Fig2e_growth_components.csv','ready').set_index('group')
    fig=plt.figure(figsize=(183/25.4,215/25.4));gs=fig.add_gridspec(3,2,left=.105,right=.98,bottom=.11,top=.97,wspace=.48,hspace=.63,height_ratios=[1.05,1,1])
    ax=fig.add_subplot(gs[0,:]);letter(fig,'a',.025,.992)
    for g in GROUPS:
        v=a.loc[a.group==g].sort_values('year');ax.plot(v.year,v.coverage_pct,color=INST[g],marker=MARK[g],label=LABEL[g]);ax.annotate(f'{v.iloc[-1].coverage_pct:.2f}%',(2025,v.iloc[-1].coverage_pct),xytext=(7,0),textcoords='offset points',color=INST[g],va='center',fontsize=8)
    ax.set(xlim=(2019.9,2025.75),ylim=(0,43),xticks=range(2020,2026),xlabel='Publication year',ylabel='Cumulative AF coverage (%)');grid(ax);ax.legend(frameon=False,loc='upper left')
    ax=fig.add_subplot(gs[1,0]);letter(fig,'b',.025,.674);ax.plot(b.year,b.R,color=CTX['All'],marker='o');ax.set(xlim=(2020.85,2025.2),ylim=(0,.05),xticks=range(2021,2026),xlabel='Publication year',ylabel='Lower-to-higher annual\ncoverage ratio');grid(ax)
    for i,offset in [(0,(3,8)),(-1,(-2,-14))]:r=b.iloc[i];ax.annotate(f'{r.R:.4f}',(r.year,r.R),xytext=offset,textcoords='offset points',ha='left' if i==0 else 'right',fontsize=8)
    ax=fig.add_subplot(gs[1,1]);letter(fig,'c',.54,.674);ax.plot(c.year,c.G_pp,color=CTX['All'],marker='s');ax.set(xlim=(2020.85,2025.2),ylim=(0,28),xticks=range(2021,2026),xlabel='Publication year',ylabel='Annual coverage gap\n(percentage points)');grid(ax)
    for i,offset in [(0,(3,8)),(-1,(-2,8))]:r=c.iloc[i];ax.annotate(f'{r.G_pp:.2f}',(r.year,r.G_pp),xytext=offset,textcoords='offset points',ha='left' if i==0 else 'right',fontsize=8)
    ax=fig.add_subplot(gs[2,0]);letter(fig,'d',.025,.36);ax.hist(draws.delta_G_pp,bins=38,density=True,color='#D9DDE3',edgecolor='white',lw=.25)
    ax.axvline(summ.actual_delta_G,color=INST['M'],lw=1.5,label=f'Observed {summ.actual_delta_G:.2f}')
    ax.axvline(summ.expected_delta_G,color='#73777D',ls='--',lw=1.3,label=f'Expected {summ.expected_delta_G:.2f}')
    ax.text(.09,.98,f'{-summ.excess:.2f} pp less widening',ha='left',va='top',transform=ax.transAxes,fontsize=8,color=INST['M'])
    ax.set(xlabel='2021–2025 change in annual gap (pp)',ylabel='Conditional benchmark density');ax.legend(loc='upper left',frameon=False,fontsize=7,bbox_to_anchor=(.06,.85))
    ax=fig.add_subplot(gs[2,1]);letter(fig,'e',.54,.36)
    for y,g in [(1,'H'),(0,'L')]:
        r=e.loc[g];obs=r.observed_growth_pp;expected=r.analytic_expected_growth_pp;col=INST[g]
        ax.plot([obs,expected],[y,y],color=col,lw=1);ax.scatter(obs,y,s=26,marker=MARK[g],color=col,zorder=3);ax.scatter(expected,y,s=26,marker=MARK[g],facecolor='white',edgecolor=col,zorder=3)
        ax.annotate(f'{obs:.2f}',(obs,y),xytext=(0,9),textcoords='offset points',ha='right' if g=='H' else 'left',color=col,fontsize=7)
        ax.annotate(f'{expected:.2f}',(expected,y),xytext=(0,-13),textcoords='offset points',ha='left',color=col,fontsize=7)
        ax.text(30,y,f'{r.r_pp:+.2f}',ha='center',va='center',color=col,fontsize=7.5)
    ax.text(30,1.57,'Obs − exp\n(pp)',ha='center',va='center',fontsize=6.5,color='#555555')
    ax.set(yticks=[1,0],yticklabels=['Higher output','Lower output'],ylim=(-.7,1.9),xlim=(0,35),xlabel='2021–2025 increase in\nannual coverage (pp)');grid(ax,'x')
    fig.legend(handles=[Line2D([],[],ls='',marker='o',color='#444',label='Observed'),Line2D([],[],ls='',marker='o',mfc='white',mec='#444',label='Expected')],frameon=False,fontsize=7,loc='lower center',bbox_to_anchor=(.80,.012),ncol=2)
    dump(out/'quality/main_artist_contract.json',{'panels':list('abcde'),'a_years':list(range(2020,2026)),'bc_years':list(range(2021,2026)),'annual_not_entry_rate':True,'a_weighting':'equal_country','formal_expectation':summ.expected_delta_G,'draws':len(draws),'no_secondary_axis':True,'e_identity':'rH - rL = D','no_titles':True})
    export(fig,out,'Figure2_a_e')

def ed3(out):
    fig=plt.figure(figsize=(183/25.4,112/25.4));letter(fig,'a',.025,.98);letter(fig,'b',.57,.98)
    flow=fig.add_axes([.04,.10,.48,.84]);flow.axis('off');flow.set_xlim(0,1);flow.set_ylim(0,1)
    rows=read(out,'ED3a_sample_flow.csv','ready');labels=['Baseline framework','Unique baseline country','Valid domestic tertiles','Main sample · 68 countries']
    reasons=['1,727\nUnknown / multiple\nbaseline countries','100\nCollapsed / empty\ntertiles (42 countries)','2,261\nGroup below 20\n(111 countries)']
    for i,(r,label) in enumerate(zip(rows.itertuples(),labels)):
        y=.80-i*.235;flow.add_patch(FancyBboxPatch((.01,y),.64,.16,boxstyle='round,pad=.008',fc='#F5F7FA',ec='#B6BFCA',lw=.6));flow.text(.33,y+.115,f'{int(r.institutions):,}',ha='center',va='center',fontsize=9,weight='bold');flow.text(.33,y+.05,label,ha='center',va='center',fontsize=6.8)
        if i<3:
            flow.annotate('',(.33,y-.065),(.33,y),arrowprops={'arrowstyle':'-|>','lw':.7,'color':'#727980'})
            flow.annotate('',(.71,y+.08),(.65,y+.08),arrowprops={'arrowstyle':'-|>','lw':.7,'color':'#727980'});flow.text(.72,y+.08,reasons[i],ha='left',va='center',fontsize=6.2,color='#555')
    a=fig.add_axes([.655,.21,.325,.68]);d=read(out,'ED3b_first_entries.csv','ready');a.bar(d.year,d.new_institutions,color=INST['M'],width=.65)
    for r in d.itertuples():a.annotate(f'{int(r.new_institutions):,}',(r.year,r.new_institutions),xytext=(0,4),textcoords='offset points',ha='center',fontsize=7)
    a.set(xticks=range(2020,2026),ylim=(0,2000),xlabel='First observed publication year',ylabel='Date-resolved first institutions');grid(a)
    export(fig,out,'ED3_a_b')

def ed4(out):
    d=read(out,'ED4_country_endpoints.csv','ready');d['R']=number(d.R);order=d[['country','plot_order','context']].drop_duplicates().sort_values('plot_order')
    fig,axs=plt.subplots(1,2,figsize=(183/25.4,260/25.4));fig.subplots_adjust(left=.11,right=.975,top=.965,bottom=.085,wspace=.37);letter(fig,'a',.025,.99);letter(fig,'b',.53,.99)
    for ax,metric in zip(axs,['R','G_pp']):
        for i,r in enumerate(order.itertuples()):
            q=d.loc[d.country==r.country].set_index('year');values=q.loc[[2021,2025],metric].to_numpy(float);col=CTX[r.context]
            if np.isfinite(values).all():ax.plot(values,[i,i],c=col,lw=.6)
            for j,value in enumerate(values):
                if np.isfinite(value):ax.scatter(value,i,s=12,marker='o',facecolor='white' if j==0 else col,edgecolor=col,lw=.65,zorder=3)
                else:ax.text(.99,i,'NA 2021',transform=ax.get_yaxis_transform(),ha='right',va='center',fontsize=6,color='#777')
        ax.set_ylim(68,-1);ax.set_yticks(range(68),order.country,fontsize=6.5);ax.set_xlim(0,float(d[metric].max())*(1.42 if metric=='R' else 1.10));grid(ax,'x')
        ax.set_xlabel('Lower-to-higher annual\ncoverage ratio' if metric=='R' else 'Gap in annual coverage (pp)')
        for edge in [22.5,44.5]:ax.axhline(edge,c='#999',lw=.6,ls=':')
    handles=[Line2D([],[],c=CTX[c],lw=2,label=c) for c in ['High','Middle','Low']]+[Line2D([],[],ls='',marker='o',mfc='white',mec='#555',label='2021'),Line2D([],[],ls='',marker='o',c='#555',label='2025')]
    fig.legend(handles=handles,title='National publication base',loc='lower center',ncol=5,frameon=False,bbox_to_anchor=(.52,.008),fontsize=7,title_fontsize=7.5)
    dump(out/'quality/ED4_country_order.json',{'country_order':order.country.tolist(),'undefined2021':d.loc[(d.year==2021)&d.R.isna(),'country'].tolist(),'NA_never_zero':True})
    export(fig,out,'ED4_a_b')

def s8(out):
    d=read(out,'S8_alternative_trajectories.csv','ready');fig,axs=plt.subplots(2,2,figsize=(183/25.4,165/25.4));fig.subplots_adjust(left=.11,right=.98,top=.94,bottom=.14,wspace=.28,hspace=.60)
    limit=max(45,np.ceil(d.coverage_pct.max()/5)*5+5)
    for i,(ax,metric,sample) in enumerate(zip(axs.ravel(),['authors','partners','authors','partners'],['metric_valid','metric_valid','common_valid','common_valid'])):
        letter(fig,'abcd'[i],.025 if i%2==0 else .54,.99 if i<2 else .52)
        x=d.loc[(d.metric==metric)&(d['sample']==sample)]
        for g in GROUPS:
            q=x.loc[x.alternative_group==g];ax.plot(q.year,q.coverage_pct,color=INST[g],marker=MARK[g],label=LABEL[g])
        q=x.loc[x.year==2025];kind='Linked authors' if metric=='authors' else 'Institutional partners';scope='Metric-specific' if sample=='metric_valid' else 'Same fixed institutions'
        ax.text(.03,.97,f'{kind} · {scope}\n{int(q.countries.iloc[0])} countries; N={int(q.fixed_institutions.sum()):,}',transform=ax.transAxes,ha='left',va='top',fontsize=7)
        ax.set(xticks=range(2020,2026),ylim=(0,limit),xlabel='Publication year',ylabel='Cumulative AF coverage (%)' if i%2==0 else '');grid(ax)
    fig.legend(*axs[0,0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.54,.025),ncol=3,frameon=False,fontsize=7)
    export(fig,out,'S8_a_d')

def s9(out):
    d=read(out,'S9_annual_benchmark_gaps.csv','ready');fig,axs=plt.subplots(2,2,figsize=(183/25.4,165/25.4));fig.subplots_adjust(left=.11,right=.98,top=.94,bottom=.145,wspace=.33,hspace=.57)
    ymax=np.ceil(max(d.reference_high_pp.max(),d.observed_G_pp.max())/5)*5
    for i,(ax,ctx) in enumerate(zip(axs.ravel(),CONTEXTS)):
        letter(fig,'abcd'[i],.025 if i%2==0 else .54,.99 if i<2 else .52);q=d.loc[d.context==ctx]
        ax.fill_between(q.year,q.reference_low_pp,q.reference_high_pp,color='#D9DDE3',lw=0)
        ax.plot(q.year,q.analytic_expected_G_pp,color='#777C82',ls='--',marker='o',mfc='white',ms=3,label='Analytic expectation');ax.plot(q.year,q.observed_G_pp,color=CTX[ctx],marker='o',label='Observed')
        ax.text(.02,.97,'All countries' if ctx=='All' else ctx+' national publication base',transform=ax.transAxes,va='top',fontsize=7.5)
        ax.set(xticks=range(2021,2026),ylim=(0,ymax),xlabel='Publication year',ylabel='Annual coverage gap (pp)' if i%2==0 else '');grid(ax)
    fig.legend(handles=[Line2D([],[],c='#363C43',marker='o',label='Observed'),Line2D([],[],c='#777C82',ls='--',marker='o',mfc='white',label='Analytic expectation'),Line2D([],[],c='#D9DDE3',lw=5,label='95% conditional reference range')],loc='lower center',bbox_to_anchor=(.52,.02),ncol=2,frameon=False,fontsize=7)
    export(fig,out,'S9_a_d')

def paired(ax,x,labels,colors):
    for i,(r,label,col) in enumerate(zip(x.itertuples(),labels,colors)):
        obs=r.actual_delta_G;exp=r.expected_delta_G;ax.plot([obs,exp],[i,i],c=col,lw=1);ax.scatter(obs,i,s=22,c=col,zorder=3);ax.scatter(exp,i,s=22,facecolor='white',edgecolor=col,zorder=3)
        ax.text(1.01,i,f'D={r.excess:+.2f}',transform=ax.get_yaxis_transform(),ha='left',va='center',fontsize=6.5)
    ax.set_yticks(range(len(x)),labels,fontsize=7);ax.set_ylim(len(x)-.45,-.55);ax.set_xlim(0,max(x.expected_delta_G.max(),x.actual_delta_G.max())*1.12);ax.set_xlabel('2021–2025 gap change (pp)');grid(ax,'x')

def s10(out):
    fig=plt.figure(figsize=(183/25.4,175/25.4));a=fig.add_axes([.15,.61,.28,.29]);b=fig.add_axes([.65,.61,.32,.29]);c=fig.add_axes([.20,.16,.23,.29]);d=fig.add_axes([.65,.16,.32,.29])
    for s,x,y in [('a',.025,.98),('b',.54,.98),('c',.025,.52),('d',.54,.52)]:letter(fig,s,x,y)
    x=read(out,'S10a_historical_thresholds.csv','ready').set_index('setting').loc[['N10','main','N30']].reset_index();paired(a,x,['N10 · 91 countries','N20 · 68 countries','N30 · 57 countries'],['#535C66']*3)
    w=table(out,'new_weighting_disparities.csv').query('year>=2021')
    for weight,col,mark,ls,label in [('equal_country',CTX['All'],'o','-','Equal country'),('pooled_institution',INST['M'],'s','--','Pooled institution')]:
        q=w.loc[w.weighting==weight];b.plot(q.year,q.G_pp,c=col,marker=mark,ls=ls,label=label)
    b.set(xticks=range(2021,2026),ylim=(0,max(w.G_pp)*1.2),xlabel='Publication year',ylabel='Annual coverage gap (pp)');grid(b);b.legend(frameon=False,loc='upper left',fontsize=6.8)
    x=read(out,'S10c_historical_benchmark_specs.csv','ready').set_index('variant').loc[['main','document_type','team_size']].reset_index();paired(c,x,['Primary','+ Document type','+ Frozen team bin'],['#535C66']*3)
    q=table(out,'new_continuous_scale_predictions.csv');q['supported']=q.countries_with_observed_percentile_support.eq(68)
    # Keep the standardization population fixed; dashed portions identify any out-of-country-range prediction.
    d.plot(q.percentile*100,q.predicted_coverage*100,c=INST['H'],lw=1.1,ls='--')
    y=np.where(q.supported,q.predicted_coverage*100,np.nan);d.plot(q.percentile*100,y,c=INST['H'],lw=1.4,label='68-country standardized')
    bins=table(out,'new_continuous_bin_summary.csv');d.scatter(bins.percentile*100,bins.coverage*100,s=18,facecolor='white',edgecolor='#7B8793',zorder=3,label='Observed bins*')
    for r in bins.itertuples():d.annotate(str(r.effective_countries),(r.percentile*100,r.coverage*100),xytext=(0,5),textcoords='offset points',ha='center',fontsize=6,color='#7B8793')
    d.set(xlim=(0,100),ylim=(0,min(100,max(q.predicted_coverage.max(),bins.coverage.max())*120)),xlabel='Within-country baseline\npublication percentile',ylabel='Cumulative AF coverage by 2025 (%)');grid(d);d.legend(frameon=False,fontsize=6.1,loc='upper left')
    fig.text(.65,.04,'* Bin labels = available countries.\nComposition varies; dashed curve includes\nout-of-country-rank-range predictions.',fontsize=6.0,color='#626970',ha='left')
    fig.legend(handles=[Line2D([],[],ls='',marker='o',c='#555',label='Observed'),Line2D([],[],ls='',marker='o',mfc='white',mec='#555',label='Analytic expected')],loc='lower left',bbox_to_anchor=(.08,.015),frameon=False,ncol=1,fontsize=7)
    export(fig,out,'S10_a_d')

def draw(out):
    with style():
        for fn in [main,ed3,ed4,s8,s9,s10]:fn(out);print('Rendered',fn.__name__,flush=True)
    sheet=Image.new('RGB',(1800,2300),'white');pen=ImageDraw.Draw(sheet)
    for i,(name,folder) in enumerate(FIGURES.items()):
        with Image.open(out/'figures'/folder/(name+'_preview.png')) as image:
            image.thumbnail((870,710));x=(i%2)*900;y=(i//2)*765;sheet.paste(image,(x+(900-image.width)//2,y+30));pen.text((x+10,y+8),name,fill='black')
    sheet.save(out/'quality/contact_sheet.png')
if __name__=='__main__':
    import sys
    draw(Path(sys.argv[1]))
