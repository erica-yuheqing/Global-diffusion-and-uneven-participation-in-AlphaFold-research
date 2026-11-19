"""Versioned publication-month Figure1 layout; no analysis or label decisions."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

BLUE='#0072B2';ORANGE='#D55E00'
COLORS=['#0072B2','#E69F00','#009E73','#D55E00','#CC79A7','#56B4E9','#332288','#882255','#44AA99','#999933']

def fixed_labels(ax,part,leaders):
    """Deterministic axis-relative displacement, with leaders, no significance selection."""
    rows=part[part.country_code.isin(leaders)].sort_values(['domestic_local_af_percent','country_code'])
    placed=[];xspan=ax.get_xlim()[1];yspan=ax.get_ylim()[1]
    for row in rows.itertuples():
        x=row.global_known_af_percent/xspan;y=row.domestic_local_af_percent/yspan
        tx=min(.92,max(.06,x+.035));ty=min(.94,max(.08,y+.055))
        # Bound displacement near the data; do not stack labels across most of
        # the y axis, which makes their apparent positions misleading.
        candidates=[(tx+dx,ty+dy) for dy in [0,.055,.11,.165] for dx in [0,.08,-.08,.16,-.16]]
        valid=[(min(.93,max(.07,a)),min(.93,max(.07,b))) for a,b in candidates]
        tx,ty=min(valid,key=lambda z:sum(abs(z[0]-a)<.11 and abs(z[1]-b)<.065 for a,b in placed))
        placed.append((tx,ty))
        ax.annotate(row.country_code,(row.global_known_af_percent,row.domestic_local_af_percent),
            xytext=(tx,ty),textcoords='axes fraction',fontsize=5.5,
            arrowprops={'arrowstyle':'-','color':'#666666','lw':.35},ha='center',va='center')

def save(fig,directory,name):
    for ext in ['pdf','png','svg']:fig.savefig(directory/f'{name}.{ext}',dpi=300,facecolor='white')
    plt.close(fig)

def render(tables,leaders,protocol,directory,diagnostic=False):
    directory.mkdir()
    style={'font.size':7,'axes.spines.top':False,'axes.spines.right':False,
        'pdf.fonttype':42,'svg.fonttype':'none','axes.titleweight':'normal'}
    with plt.rc_context(style):
        fig=plt.figure(figsize=(180/25.4,215/25.4),layout='constrained')
        grid=fig.add_gridspec(4,6,height_ratios=[1,.4,1.45,2.15])
        m=tables['monthly_diffusion'];dates=pd.to_datetime(m.month)
        ax=fig.add_subplot(grid[0,:]);new=fig.add_subplot(grid[1,:],sharex=ax)
        ax.plot(dates,m.cumulative_countries,color=BLUE,lw=1.4)
        ax.set(ylabel='Cumulative countries / regions',title='a  First observed geographic participation')
        ax.set_ylim(bottom=0);ax.tick_params(labelbottom=False)
        new.bar(dates,m.new_countries,width=23,color='#56B4E9',linewidth=0)
        new.set(ylabel='Monthly new',xlabel='Publication month',ylim=(0,max(1,m.new_countries.max()*1.15)))
        for boundary,label in [('2021-07-01','AF2 code + AFDB'),('2024-05-01','AF3')]:
            for target in [ax,new]:target.axvline(pd.Timestamp(boundary),color='#666666',ls='--',lw=.65)
            ax.text(pd.Timestamp(boundary),.98,label,transform=ax.get_xaxis_transform(),ha='left',va='top',fontsize=6.5)
        ax.text(.01,.06,f'Pre-2020 observed: {int(m.pre2020_countries.iloc[0])}',transform=ax.transAxes,fontsize=6.5)
        p=tables['country_period_profiles'];included=p[p.scatter_included]
        xmax=max(1,float(included.global_known_af_percent.max())*1.12)
        ymax=max(.01,float(included.domestic_local_af_percent.max())*1.16)
        for i,period in enumerate(protocol['periods']):
            target=fig.add_subplot(grid[2,2*i:2*i+2])
            q=included[included.period_name.eq(period['name'])]
            total=tables['period_counts'].set_index('period_name').loc[period['name']]
            target.scatter(q.global_known_af_percent,q.domestic_local_af_percent,s=11,color=BLUE,edgecolor='white',linewidth=.25)
            target.set(xlim=(0,xmax),ylim=(0,ymax),xlabel='Global known AF credit (%)')
            zoom=q[q.global_known_af_percent.le(10) & q.domestic_local_af_percent.le(3.5)]
            fixed_labels(target,q[~q.index.isin(zoom.index)],leaders)
            target.set_title(('b  ' if i==0 else '')+period['name']+f'\nn={int(total.af_studies):,}; countries={len(q)}',fontsize=7)
            if i==0:target.set_ylabel('AF / local domestic research (%)')
            inset=target.inset_axes([.39,.45,.58,.50])
            inset.scatter(zoom.global_known_af_percent,zoom.domestic_local_af_percent,s=9,color=BLUE,edgecolor='white',linewidth=.2)
            inset.set(xlim=(0,10),ylim=(0,3.5));inset.set_xticks([0,5,10]);inset.set_yticks([0,1,2,3])
            inset.tick_params(labelsize=4.5,pad=1)
            inset.set_title('Shared linear zoom',fontsize=5.5,pad=2)
            fixed_labels(inset,zoom,leaders)
            for spine in inset.spines.values():spine.set_visible(True);spine.set_color('#777777');spine.set_linewidth(.5)
            target.add_patch(plt.Rectangle((0,0),10,3.5,fill=False,edgecolor='#777777',lw=.5,ls=':'))
        left=grid[3,:3].subgridspec(2,1,height_ratios=[.65,2])
        volume=fig.add_subplot(left[0]);stack=fig.add_subplot(left[1],sharex=volume)
        annual=tables['annual_counts'].set_index('publication_year').reindex(range(2020,2026))
        volume.bar(range(2020,2026),annual.confirmed_af,color=BLUE)
        for year,n in annual.confirmed_af.items():volume.text(year,n+max(annual.confirmed_af)*.025,f'{int(n):,}',ha='center',fontsize=5.8)
        volume.set_title('c  Annual volume and fixed-country composition',fontsize=7)
        volume.set_ylabel('AF studies');volume.tick_params(labelbottom=False);volume.set_ylim(0,max(annual.confirmed_af)*1.22)
        shares=tables['fixed_ten_composition'];bottom=np.zeros(6)
        for code,color in zip(leaders+['Other','Unknown'],COLORS+['#BEBEBE','#FFFFFF']):
            q=shares[shares.country_code.eq(code)].set_index('year').reindex(range(2020,2026))
            heights=q.fraction.to_numpy()*100
            stack.bar(range(2020,2026),heights,bottom=bottom,color=color,label=code,
                edgecolor='#555555' if code=='Unknown' else 'white',linewidth=.2,hatch='///' if code=='Unknown' else None)
            bottom+=np.nan_to_num(heights)
        stack.set(ylim=(0,100),ylabel='All AF study credit (%)',xlabel='Publication year')
        stack.legend(ncol=4,fontsize=5.6,loc='upper center',bbox_to_anchor=(.5,-.2),frameon=False)
        right=grid[3,3:].subgridspec(2,1,height_ratios=[2,1])
        gini=fig.add_subplot(right[0]);delta=fig.add_subplot(right[1],sharex=gini)
        d=tables['concentration'];years=d.year.to_numpy()
        for prefix,label,color,mark in [('af','AF',BLUE,'o'),('comparator','Screen-negative background',ORANGE,'s')]:
            y=d[prefix+'_gini'].to_numpy(float);lo=d[prefix+'_lower'].to_numpy(float);hi=d[prefix+'_upper'].to_numpy(float)
            gini.plot(years,y,marker=mark,color=color,lw=1,ms=3,label=label)
            gini.fill_between(years,lo,hi,color=color,alpha=.15)
        gini.set_title('d  Country concentration and relative gap',fontsize=7)
        finite=np.concatenate([d.af_lower,d.af_upper,d.comparator_lower,d.comparator_upper]).astype(float)
        low=max(0,np.nanmin(finite)-.01);high=min(1,np.nanmax(finite)+.01)
        gini.set(ylim=(low,high),ylabel='Gini (fixed 227 countries)');gini.tick_params(labelbottom=False)
        gini.legend(frameon=False,fontsize=6,loc='lower left')
        delta.axhline(0,color='#666666',lw=.65,ls='--')
        delta.errorbar(years,d.delta_gini,yerr=np.array([d.delta_gini-d.delta_lower,d.delta_upper-d.delta_gini]),
            color=BLUE,marker='o',lw=.7,ms=3,capsize=2)
        delta.set(ylabel='AF − background',xlabel='Publication year')
        if diagnostic:fig.suptitle('DIAGNOSTIC — OLD LABELS; candidate decisions pending',fontsize=9,color='#9B2226')
        save(fig,directory,'figure1_revised_a_d'+('_diagnostic' if diagnostic else ''))
        fig,ax=plt.subplots(figsize=(180/25.4,80/25.4),layout='constrained')
        for prefix,label,color in [('af','AF',BLUE),('comparator','Background',ORANGE)]:
            ax.plot(years,d[prefix+'_gini'],label=label,color=color,marker='o',ms=3)
            ax.fill_between(years,d[prefix+'_lower'],d[prefix+'_upper'],alpha=.15,color=color)
        ax.set(ylim=(0,1),ylabel='Gini — full 0–1 axis',xlabel='Publication year');ax.legend(frameon=False)
        save(fig,directory,'supplement_gini_full_axis')
        a=tables['annual_diffusion_counts']
        fig,axs=plt.subplots(3,1,figsize=(180/25.4,140/25.4),sharex=True,layout='constrained')
        for ax,column,label,color in zip(axs,['active_countries','new_countries','cumulative_countries'],
            ['Annually active','Newly observed','Cumulative observed'],[BLUE,'#56B4E9',ORANGE]):
            ax.bar(a.year,a[column],color=color)
            for row in a.itertuples():ax.text(row.year,getattr(row,column),str(getattr(row,column)),ha='center',va='bottom',fontsize=6)
            ax.set_ylim(0,max(1,a[column].max()*1.18));ax.set_ylabel(label+' countries')
        axs[-1].set_xlabel('Publication year');fig.suptitle('Annual geographic coverage — distinct definitions',fontsize=9)
        save(fig,directory,'supplement_annual_country_diffusion')
        heat=tables['paired_domestic_heatmaps'];codes=sorted(heat.country_code.unique())
        all_values=heat[['raw_common_AF_fraction','matched_AF_mix_fraction']].to_numpy(float)*100
        shared_max=max(.001,float(np.nanmax(all_values))) if np.isfinite(all_values).any() else 1
        with PdfPages(directory/'supplement_paired_domestic_all_countries.pdf') as pdf:
            for start in range(0,len(codes),55):
                page=codes[start:start+55];fig,axs=plt.subplots(1,2,figsize=(180/25.4,250/25.4),layout='constrained')
                values=[]
                for col in ['raw_common_AF_fraction','matched_AF_mix_fraction']:
                    values.append(100*heat.pivot(index='country_code',columns='year',values=col).reindex(page).to_numpy(float))
                vmax=shared_max
                cmap=plt.get_cmap('cividis').copy();cmap.set_bad('#D8D8D8')
                for target,value,title in zip(axs,values,['Raw — common support','Matched AF composition — same support']):
                    im=target.imshow(np.ma.masked_invalid(value),aspect='auto',cmap=cmap,vmin=0,vmax=vmax)
                    target.set_xticks(range(6),range(2020,2026),rotation=90);target.set_yticks(range(len(page)),page,fontsize=5.5)
                    target.set_title(title,fontsize=7)
                fig.colorbar(im,ax=axs,label='AF / observed or matched domestic credit (%)',fraction=.035)
                fig.suptitle(f'Common year × type × subfield support; codes {start+1}–{start+len(page)}; grey = unavailable',fontsize=7)
                pdf.savefig(fig);plt.close(fig)
        raw=tables['raw_domestic_heatmap']
        values=100*raw.pivot(index='country_code',columns='year',values='af_fraction').reindex(codes)
        vmax=max(.001,float(np.nanmax(values.to_numpy(float))))
        with PdfPages(directory/'supplement_raw_domestic_all_countries.pdf') as pdf:
            for start in range(0,len(codes),55):
                page=codes[start:start+55];fig,ax=plt.subplots(figsize=(110/25.4,250/25.4),layout='constrained')
                cmap=plt.get_cmap('cividis').copy();cmap.set_bad('#D8D8D8')
                im=ax.imshow(np.ma.masked_invalid(values.reindex(page).to_numpy(float)),aspect='auto',cmap=cmap,vmin=0,vmax=vmax)
                ax.set_xticks(range(6),range(2020,2026),rotation=90);ax.set_yticks(range(len(page)),page,fontsize=6)
                ax.set_title('Raw AF / all eligible local domestic credit',fontsize=8)
                fig.colorbar(im,ax=ax,label='AF / domestic credit (%)',fraction=.035)
                fig.suptitle('All observed strata; shared color scale\nGrey = no denominator',fontsize=7)
                pdf.savefig(fig);plt.close(fig)
