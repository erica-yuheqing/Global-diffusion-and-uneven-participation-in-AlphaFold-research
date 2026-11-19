"""Publication-size, source-table-only figures; no decorative/generated data."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from PIL import Image,ImageCms,ImageDraw
from support import *
from benchmark import ratio

BLUE='#4865BC'
COLORS={'L':'#6C86B3','M':'#4865BC','H':'#183B75','Low':'#6688B5','Middle':'#4865BC','High':'#183B75'}
MARKERS={'L':'o','M':'s','H':'^'}

def style():
    plt.rcParams.update({'font.family':'Arial','font.size':8,'axes.labelsize':8.5,
      'xtick.labelsize':7.5,'ytick.labelsize':8,'legend.fontsize':8,
      'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.65,
      'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})

def decorate(ax,grid='y'):
    ax.tick_params(length=3,width=.6)
    ax.set_axisbelow(True)
    if grid:ax.grid(axis=grid,color='#EAEDF1',lw=.6)

def label(fig,text,x,y):fig.text(x,y,text,fontsize=11,weight='bold',va='top')

def export(fig,directory,name,tiff=True):
    directory.mkdir(parents=True,exist_ok=True)
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    clipped=[];off_view=set()
    for ax in fig.axes:
        for t in ax.get_xticklabels():
            if not min(ax.get_xlim())<=t.get_position()[0]<=max(ax.get_xlim()):off_view.add(id(t))
        for t in ax.get_yticklabels():
            if not min(ax.get_ylim())<=t.get_position()[1]<=max(ax.get_ylim()):off_view.add(id(t))
    for t in fig.findobj(matplotlib.text.Text):
        if not t.get_visible() or not t.get_text():continue
        if id(t) in off_view:continue
        ax=t.axes
        if ax is not None:
            if t in ax.get_xticklabels() and not min(ax.get_xlim())<=t.get_position()[0]<=max(ax.get_xlim()):continue
            if t in ax.get_yticklabels() and not min(ax.get_ylim())<=t.get_position()[1]<=max(ax.get_ylim()):continue
        box=t.get_window_extent(renderer)
        if box.x0 < -2 or box.y0 < -2 or box.x1>fig.bbox.x1+2 or box.y1>fig.bbox.y1+2:clipped.append(t.get_text())
    require(not clipped,'Figure text beyond canvas: '+str(clipped))
    for fmt in ['pdf','svg']:fig.savefig(directory/(name+'.'+fmt),facecolor='white')
    fig.savefig(directory/(name+'.png'),dpi=600,facecolor='white')
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with Image.open(directory/(name+'.png')) as im:
        rgb=im.convert('RGB');rgb.save(directory/(name+'.png'),dpi=(600,600),icc_profile=profile)
        if tiff:rgb.save(directory/(name+'.tiff'),dpi=(600,600),icc_profile=profile,compression='tiff_lzw')
        pixels=rgb.size
    if directory.name=='extended_data':
        submission=directory/'submission_300dpi';submission.mkdir(exist_ok=True)
        fig.savefig(submission/(name+'.tiff'),dpi=300,facecolor='white',pil_kwargs={'compression':'tiff_lzw','icc_profile':profile})
        with Image.open(submission/(name+'.tiff')) as im:
            if im.mode!='RGB':im.convert('RGB').save(submission/(name+'.tiff'),dpi=(300,300),compression='tiff_lzw',icc_profile=profile)
    fig.savefig(directory/(name+'_preview.png'),dpi=220,facecolor='white')
    dump(directory/(name+'.metadata.json'),dict(size_mm=[fig.get_figwidth()*25.4,fig.get_figheight()*25.4],
        pixels=pixels,dpi=600,mode='RGB',profile='sRGB',native_render=True,vector_text=True,text_inside_canvas=True,
        publication_acceptance_certified=False))
    plt.close(fig)

def panel_a(fig,bounds,out):
    ax=fig.add_axes(bounds);q=load(out,'panel_a_source')
    for g,name in zip(GROUPS,['Lower baseline output','Middle baseline output','Higher baseline output']):
        x=q[q.group.eq(g)].sort_values('year')
        ax.plot(x.year,100*x.C,color=COLORS[g],marker=MARKERS[g],ms=3.3,lw=1.2,
            ls={'L':':','M':'--','H':'-'}[g],label=name)
    ax.set(xlim=(2018.85,2025.15),ylim=(0,max(2,100*q.C.max()*1.18)),xticks=range(2019,2026),
      xticklabels=['Pre-\n2020','2020','2021','2022','2023','2024','2025'])
    ax.set_ylabel('Cumulative observed AF coverage (%)')
    ax.set_xlabel('Publication year')
    ax.legend(frameon=False,loc='upper left',fontsize=7.2,handlelength=2.5)
    ax.text(.99,.98,f'{int(q.countries.iloc[0])} countries / regions\nEqual-country means',transform=ax.transAxes,
      ha='right',va='top',fontsize=7,color='#555D68')
    decorate(ax)

def panel_b(fig,left_bounds,right_bounds,out):
    q=load(out,'panel_b_source');ys=np.arange(3)
    for bounds,metric,xlabel in [(left_bounds,'R','Low / high\ncoverage ratio'),(right_bounds,'G','High − low coverage\n(percentage points)')]:
        ax=fig.add_axes(bounds)
        for i,c in enumerate(['High','Middle','Low']):
            x=q[q.context.eq(c)].set_index('year');a=x.loc[2021,metric];b=x.loc[2025,metric]
            if np.isfinite(a) and np.isfinite(b):ax.plot([a,b],[i,i],color=COLORS[c],lw=1.2)
            for year,v in [(2021,a),(2025,b)]:
                if np.isfinite(v):ax.scatter(v,i,s=26,facecolor='white' if year==2021 else COLORS[c],edgecolor=COLORS[c],lw=1,zorder=3)
                else:ax.text(.01,i,'Undefined',transform=ax.get_yaxis_transform(),va='center',fontsize=7)
        ax.set(yticks=ys,yticklabels=['High','Middle','Low'] if metric=='R' else [],ylim=(2.5,-.5),xlabel=xlabel)
        mx=max(.01,q[metric].max());ax.set_xlim(-.08*mx,mx*1.15)
        if metric=='R':ax.set_ylabel('National baseline publication base')
        decorate(ax,'x')
    handles=[Line2D([],[],marker='o',ls='none',color='#555D68',mfc='white',label='2021'),Line2D([],[],marker='o',ls='none',color='#555D68',label='2025')]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.765,.97),ncol=2,frameon=False,handletextpad=.4,columnspacing=1)

def panel_c(fig,bounds,out):
    ax=fig.add_axes(bounds);summary=load(out,'panel_c_source').iloc[0]
    draws=load(out,'benchmark_replicates').query('variant=="main" and setting=="main" and context=="All"').delta_G.to_numpy()
    density,edges=np.histogram(draws,bins=30,density=True)
    ax.stairs(density,edges,fill=True,color='#C7CCD3',alpha=.85,lw=.5)
    mu=summary.expected_delta_G;obs=summary.actual_delta_G
    ax.axvline(mu,color='#666D77',ls='--',lw=1.3,label='Expected')
    ax.axvline(obs,color='#17212F',lw=1.5,label='Observed')
    span=max(np.ptp(draws),abs(mu-obs),.1)
    ax.set_xlim(min(draws.min(),obs)-.12*span,max(draws.max(),obs)+.12*span)
    ax.set_ylim(0,max(density)*1.35)
    ax.set_xlabel('Change in high–low coverage gap\n2021–2025 (percentage points)')
    ax.set_ylabel('Conditional benchmark density')
    ax.text(.03,.97,f'Observed: {obs:+.2f} pp\nExpected: {mu:+.2f} pp\nExcess: {summary.excess:+.2f} pp',
      transform=ax.transAxes,va='top',fontsize=8,bbox=dict(facecolor='white',edgecolor='none',alpha=.9,pad=2))
    ax.text(.97,.97,r'$E=\Delta G_{\rm obs}-E_0(\Delta G)$',transform=ax.transAxes,ha='right',va='top',fontsize=8.5,
      bbox=dict(facecolor='white',edgecolor='none',alpha=.95,pad=2))
    ax.legend(frameon=False,loc='upper right',bbox_to_anchor=(1,.80),fontsize=7)
    decorate(ax)
    pd.DataFrame(dict(bin_left=edges[:-1],bin_right=edges[1:],density=density)).to_csv(out/'figure2_source_data/panel_c_density.csv',index=False)

def panel_d(fig,bounds,out,contrast=True):
    ax=fig.add_axes(bounds);q=load(out,'panel_d_source').set_index('context')
    extrema=[0.]
    for i,c in enumerate(['High','Middle','Low']):
        row=q.loc[c];ax.plot([row.centered_low,row.centered_high],[i,i],color='#9CA3AE',lw=3,solid_capstyle='butt')
        ax.scatter(row.excess,i,color=COLORS[c],marker='D',s=27,zorder=3)
        ax.annotate(f'{row.excess:+.2f}',(row.excess,i),xytext=(0,9),textcoords='offset points',ha='center',fontsize=7,color=COLORS[c])
        extrema.extend([row.excess,row.centered_low,row.centered_high])
    labels=['High','Middle','Low']
    if contrast:
        r=load(out,'context_contrasts').query('variant=="main" and setting=="main" and primary').iloc[0]
        i=3.5;ax.axhline(2.8,color='#E1E5EB',lw=.7)
        ax.plot([r.centered_low,r.centered_high],[i,i],color='#9CA3AE',lw=3)
        ax.scatter(r.observed_excess_difference,i,color='#17212F',marker='D',s=27)
        ax.annotate(f'{r.observed_excess_difference:+.2f}',(r.observed_excess_difference,i),xytext=(0,9),textcoords='offset points',ha='center',fontsize=7)
        extrema.extend([r.observed_excess_difference,r.centered_low,r.centered_high]);labels+=['Low − high']
    ax.axvline(0,color='#6D747F',ls='--',lw=.8)
    ax.set(yticks=[0,1,2,3.5] if contrast else [0,1,2],yticklabels=labels,ylim=(4.1,-.6) if contrast else (2.5,-.5))
    span=max(np.ptp(extrema),1);ax.set_xlim(min(extrema)-.14*span,max(extrema)+.14*span)
    ax.set_xlabel('Excess change in coverage gap (pp)')
    decorate(ax,'x')

def main_figure(out,full=False):
    include_d=json.loads((out/'provenance/panel_d_decision.json').read_text())['main_panel'] or full
    fig=plt.figure(figsize=(183/25.4,168/25.4))
    label(fig,'a',.025,.97);panel_a(fig,[.105,.60,.35,.30],out)
    label(fig,'b',.51,.97);panel_b(fig,[.635,.635,.115,.26],[.825,.635,.145,.26],out)
    label(fig,'c',.025,.45)
    if include_d:
        panel_c(fig,[.105,.16,.35,.25],out);label(fig,'d',.51,.45);panel_d(fig,[.64,.16,.33,.25],out)
    else:panel_c(fig,[.105,.16,.865,.25],out)
    fig.text(.105,.055,'Gray ranges: centered 95% conditional benchmark reference ranges, not confidence intervals.' if include_d else
      'National-context excess results are reported in Extended Data; the conditional benchmark is not a causal model.',fontsize=7,color='#555D68')
    export(fig,out/'figures/extended_data' if full else out/'figures','figure2_plan3_a_d' if full else 'figure2_plan3_main')

def extended(out):
    directory=out/'figures/extended_data'
    # d is always delivered, even if the prespecified main-panel gate is not met.
    fig=plt.figure(figsize=(130/25.4,90/25.4));panel_d(fig,[.23,.27,.71,.60],out)
    fig.text(.23,.07,'Gray: centered conditional reference range (not CI).',fontsize=7,color='#555D68')
    export(fig,directory,'ED_context_excess')
    ctx=load(out,'context_group_year').query('analysis=="N20"')
    fig,axes=plt.subplots(1,3,figsize=(183/25.4,72/25.4));fig.subplots_adjust(left=.09,right=.98,top=.87,bottom=.25,wspace=.32)
    for ax,c in zip(axes,['Low','Middle','High']):
        for g in GROUPS:
            x=ctx[(ctx.context==c)&(ctx.group==g)].sort_values('year')
            ax.plot(x.year,100*x.C,color=COLORS[g],marker=MARKERS[g],ms=2.5,ls={'L':':','M':'--','H':'-'}[g],lw=1,label=g)
        ax.text(.03,1.06,c+' national base',transform=ax.transAxes,fontsize=8)
        ax.set(xticks=[2019,2021,2023,2025],xticklabels=['Pre-2020','2021','2023','2025'],ylim=(0,100*ctx.C.max()*1.1),xlabel='Publication year')
        decorate(ax)
    axes[0].set_ylabel('Cumulative observed AF coverage (%)');axes[0].legend(frameon=False,fontsize=7)
    export(fig,directory,'ED_context_entry_trajectories')
    residual=load(out,'residual_heatmap').query('variant=="main" and setting=="main" and context!="All"')
    values=residual.pivot(index='context',columns='group',values='residual_change_pp').reindex(index=['High','Middle','Low'],columns=GROUPS)
    fig,ax=plt.subplots(figsize=(110/25.4,85/25.4));fig.subplots_adjust(left=.22,right=.80,bottom=.27,top=.91)
    lim=max(1,abs(values).to_numpy().max());im=ax.imshow(values,cmap='RdBu_r',vmin=-lim,vmax=lim,aspect='auto')
    ax.set(yticks=range(3),yticklabels=values.index,xticks=range(3),xticklabels=['Lower','Middle','Higher'],xlabel='Domestic baseline institution scale',ylabel='National baseline publication base')
    for i in range(3):
        for j in range(3):ax.text(j,i,f'{values.iloc[i,j]:+.2f}',ha='center',va='center',color='white' if abs(values.iloc[i,j])>.55*lim else '#17212F',fontsize=9)
    cax=fig.add_axes([.84,.27,.035,.64]);fig.colorbar(im,cax=cax,label='Observed − expected coverage change (pp)')
    export(fig,directory,'ED_coverage_change_residuals')
    # Every country is displayed, with common scales and no AF-based country selection.
    cells=load(out,'country_group_year').query('eligible_20 and year in [2021,2025]')
    totals=cells.groupby(['country','year']).first().reset_index()
    countries=sorted(cells.country.unique())
    global_R=[];global_G=[]
    for c,x in cells.groupby('country'):
        q=x.pivot(index='year',columns='group',values='A')
        global_R.extend(ratio(q.L.to_numpy(),q.H.to_numpy()).tolist())
        global_G.extend((100*(q.H-q.L)).tolist())
    max_R=max(v for v in global_R if np.isfinite(v));min_G=min(global_G);max_G=max(global_G)
    for page,start in enumerate(range(0,len(countries),24),1):
        selected=countries[start:start+24]
        fig,axes=plt.subplots(1,2,figsize=(150/25.4,160/25.4));fig.subplots_adjust(left=.12,right=.96,bottom=.13,top=.95,wspace=.35)
        for ci,c in enumerate(selected):
            x=cells[cells.country.eq(c)].pivot(index='year',columns='group',values='A')
            for ax,key in zip(axes,['R','G']):
                vals=[float(ratio(x.loc[y,'L'],x.loc[y,'H'])) if key=='R' else 100*(x.loc[y,'H']-x.loc[y,'L']) for y in [2021,2025]]
                if np.isfinite(vals).all():ax.plot(vals,[ci,ci],color='#AAB3C2',lw=.7)
                for year,v in zip([2021,2025],vals):
                    if np.isfinite(v):ax.scatter(v,ci,s=13,color=BLUE,facecolors='white' if year==2021 else BLUE,zorder=3)
        for ax in axes:ax.set(yticks=np.arange(len(selected)),yticklabels=selected,ylim=(len(selected)-.3,-.7));decorate(ax,'x')
        axes[0].set_xlim(-.04*max_R,1.06*max_R)
        axes[1].set_xlim(min(0,min_G)-.04*(max_G-min(0,min_G)),max_G*1.06)
        axes[0].set_xlabel('Low / high coverage ratio');axes[1].set_xlabel('High − low coverage (pp)')
        fig.text(.12,.04,'Open: 2021; filled: 2025. Undefined ratios omitted, never replaced by zero.',fontsize=7)
        export(fig,directory,f'ED_country_endpoints_{page}')
    # Sensitivity summary uses the original centered-null convention, not E-centered error bars.
    bm=load(out,'benchmark_summary').query('context=="All"')
    fig,ax=plt.subplots(figsize=(160/25.4,85/25.4));fig.subplots_adjust(left=.35,right=.97,bottom=.26,top=.93)
    for i,row in enumerate(bm.itertuples()):
        ax.plot([row.centered_low,row.centered_high],[i,i],color='#A6AEB9',lw=3)
        ax.scatter(row.excess,i,color=BLUE,marker='D',s=20)
    ax.axvline(0,color='#555D68',ls='--',lw=.7)
    ax.set(yticks=range(len(bm)),yticklabels=[f'{r.variant} / {r.setting}' for r in bm.itertuples()],ylim=(len(bm)-.5,-.6),xlabel='Overall excess gap change (pp)')
    decorate(ax,'x');export(fig,directory,'ED_benchmark_sensitivity')

def contact(out):
    previews=sorted((out/'figures/extended_data').glob('*_preview.png'))
    for number,start in enumerate(range(0,len(previews),3),1):
        panels=[]
        for p in previews[start:start+3]:
            with Image.open(p) as im:
                x=im.convert('RGB');x.thumbnail((1250,850))
                item=Image.new('RGB',(1290,x.height+38),'white');ImageDraw.Draw(item).text((12,8),p.stem,fill='black');item.paste(x,((1290-x.width)//2,32));panels.append(item)
        sheet=Image.new('RGB',(1290,sum(x.height for x in panels)),'white');y=0
        for item in panels:sheet.paste(item,(0,y));y+=item.height
        sheet.save(out/'provenance'/f'visual_contact_{number}.png')

def run(out):
    style();(out/'figure2_source_data').mkdir(exist_ok=True)
    for name,target in [('panel_a_source','panel_a'),('panel_b_source','panel_b'),('panel_c_source','panel_c'),('panel_d_source','panel_d'),('context_contrasts','direct_context_contrasts')]:
        load(out,name).to_csv(out/'figure2_source_data'/(target+'.csv'),index=False)
    main_figure(out);main_figure(out,full=True);extended(out);contact(out)

if __name__=='__main__':run(OUT)
