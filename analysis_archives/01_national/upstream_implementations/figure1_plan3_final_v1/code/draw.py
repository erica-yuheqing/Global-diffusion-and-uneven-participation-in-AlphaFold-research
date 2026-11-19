"""One main, two ED and six supplementary native scientific figures, panel letters only."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch,Patch,Rectangle
from matplotlib.colors import LinearSegmentedColormap,TwoSlopeNorm
from PIL import Image,ImageCms,ImageDraw
from common import *

CMAP=LinearSegmentedColormap.from_list('R',['#7B3294','#F7F7F7','#008B78'])
PALETTE=['#173873','#35558B','#4865BC','#6685BE','#8FAAD3','#C1C1C1']

def style():
    plt.rcParams.update({'font.family':'Arial','font.size':7.5,'axes.labelsize':7.5,'xtick.labelsize':7,'ytick.labelsize':7,
      'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'legend.fontsize':7,'lines.linewidth':1.1,'lines.markersize':3.4,
      'pdf.fonttype':42,'svg.fonttype':'none','figure.facecolor':'white','savefig.facecolor':'white','hatch.linewidth':.35})
def letter(fig,s,x,y):fig.text(x,y,s,fontsize=10,fontweight='bold',va='top')
def grid(ax,axis='y'):ax.set_axisbelow(True);ax.grid(axis=axis,color='#E5E8EC',lw=.4)
def AFlegend(ax,loc='best'):
    ax.legend(handles=[Line2D([],[],color=BLUE,marker='o',label='AF'),Line2D([],[],color=ORANGE,ls='--',marker='s',label='non-AF')],frameon=False,loc=loc)
def export(fig,out,name):
    folder=out/'figures';fig.canvas.draw();renderer=fig.canvas.get_renderer();skip=set()
    for ax in fig.axes:
        for axis in [ax.xaxis,ax.yaxis]:
            lo,hi=sorted(axis.get_view_interval())
            for tick in axis.get_major_ticks():
                if not lo-1e-8<=tick.get_loc()<=hi+1e-8:skip|={id(tick.label1),id(tick.label2)}
    bounds=[]
    for t in fig.findobj(matplotlib.text.Text):
        if t.get_visible() and t.get_text().strip() and id(t) not in skip:
            b=t.get_window_extent(renderer);bounds.append(dict(text=t.get_text(),x0=b.x0/fig.bbox.width,x1=b.x1/fig.bbox.width,y0=b.y0/fig.bbox.height,y1=b.y1/fig.bbox.height))
    dump(out/'provenance'/f'{name}_text_bounds.json',bounds)
    for ext in ['pdf','svg']:fig.savefig(folder/f'{name}.{ext}')
    fig.savefig(folder/f'{name}_preview.png',dpi=200)
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes();p=folder/f'{name}_600dpi.png';fig.savefig(p,dpi=600)
    with Image.open(p) as im:
        rgb=im.convert('RGB');rgb.save(p,dpi=(600,600),icc_profile=profile);rgb.save(folder/f'{name}_600dpi.tiff',dpi=(600,600),icc_profile=profile,compression='tiff_lzw')
    dump(out/'provenance'/f'{name}_render.json',dict(physical_mm=(fig.get_size_inches()*25.4).tolist(),DPI=600,native_render=True,RGB=True,panels='letters_only',statistics_in_caption=True))
    plt.close(fig)
def node(ax,x,y,w,h,title,text,size=7):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.006,rounding_size=0.01',facecolor='#F5F7FA',edgecolor='#B5BDCA',lw=.6))
    ax.text(x+w/2,y+h*.78,title,ha='center',va='center',fontsize=size,fontweight='bold')
    ax.text(x+w/2,y+h*.36,text,ha='center',va='center',fontsize=size-.4,linespacing=1.35)
def arrow(ax,a,b):ax.annotate('',b,a,arrowprops=dict(arrowstyle='-|>',color=GRAY,lw=.8))
def gini_pair(ax,c,full=False):
    for key,color,mark,ls in [('af',BLUE,'o','-'),('comparator',ORANGE,'s','--')]:
        ax.fill_between(c.year,c[key+'_lower'],c[key+'_upper'],color=color,alpha=.13,lw=0)
        ax.plot(c.year,c[key+'_gini'],color=color,marker=mark,ls=ls)
    ax.set_ylabel('Gini coefficient');ax.set_xticks(c.year);ax.set_ylim((0,1) if full else (.892,.958));grid(ax)
def interval_line(ax,x,point,low,high,label=None,color=GRAY,marker='o',ls='-'):
    ax.errorbar(x,point,yerr=[np.asarray(point)-low,np.asarray(high)-point],fmt=marker,ls=ls,color=color,lw=.9,elinewidth=.65,capsize=2,label=label)

def main(out):
    c=load(out,'concentration').query('year>=2021');m=load(out,'matching_summary').query('spec=="count_composition" and year>=2021');d=load(out,'figure1d_top10_endpoints')
    fig=plt.figure(figsize=(183/25.4,193/25.4));letter(fig,'a',.025,.982)
    flow=fig.add_axes([.065,.865,.90,.112]);flow.axis('off');flow.set_xlim(-.01,1.01)
    boxes=[('OpenAlex life-science\ncorpus','6,046,663 records\n22 subfields · 2015–2025'),('Candidate retrieval','Keywords + seed citations\n29,127 initial records'),('Evidence assessment','Further retrieval · AI review\nAbstracts / full texts\nTargeted human review'),('AF-use study cohort','16,414 studies\n2020–2025')]
    for i,(title,text) in enumerate(boxes):
        x=i*.255;node(flow,x,.05,.225,.88,title,text,6.8)
        if i<3:arrow(flow,(x+.227,.49),(x+.253,.49))
    letter(fig,'b',.025,.823);top=fig.add_axes([.12,.55,.345,.25]);bottom=fig.add_axes([.12,.19,.345,.255])
    gini_pair(top,c);top.tick_params(labelbottom=False);top.set_xlim(2020.8,2025.35);AFlegend(top,'upper right')
    for year,dx,dy in [(2021,6,7),(2025,-2,8)]:
        r=c[c.year.eq(year)].iloc[0];top.annotate(f'{r.af_gini:.4f}',(year,r.af_gini),xytext=(dx,dy),textcoords='offset points',ha='left' if year==2021 else 'right',fontsize=7.2,color=BLUE)
    interval_line(bottom,c.year,c.delta_gini,c.delta_lower,c.delta_upper);bottom.axhline(0,color='#A2A7AE',ls='--',lw=.6)
    bottom.set_xlim(top.get_xlim());bottom.set_ylim(-.003,.057);bottom.set_xticks(c.year);bottom.set_ylabel('AF − non-AF Gini');bottom.set_xlabel('Publication year');grid(bottom)
    bottom.text(.20,.90,'2021–2025 change: −0.0144',transform=bottom.transAxes,fontsize=6.8,color=GRAY)
    letter(fig,'c',.55,.823);match=fig.add_axes([.66,.655,.29,.145]);interval_line(match,m.year,m.point,m.lower,m.upper)
    match.axhline(0,color='#A2A7AE',ls='--',lw=.6);match.set_xticks(m.year);match.set_xlim(2020.8,2025.2);match.set_ylabel('Matched AF − non-AF Gini',labelpad=5);match.set_xlabel('Publication year');grid(match)
    letter(fig,'d',.55,.55);end=fig.add_axes([.66,.19,.29,.325]);end.axvline(1,color='#A2A7AE',lw=.7,ls='--');end.set_xscale('log',base=2)
    for i,code in enumerate(ORDER[:10]):
        x=d[d.country_code.eq(code)].set_index('year');r1=x.loc[2021,'R'];r5=x.loc[2025,'R']
        end.plot([r1,r5],[i,i],color='#B4BAC3',lw=.8);end.scatter(r1,i,s=20,facecolor='white',edgecolor=GRAY,lw=.9,zorder=3);end.scatter(r5,i,s=20,facecolor=GRAY,edgecolor=GRAY,lw=.7,zorder=4)
    end.set_yticks(range(10),ORDER[:10]);end.set_ylim(9.7,-.7);end.set_xlim(.25,4);end.set_xticks([.25,.5,1,2,4],['0.25','0.5','1','2','4']);end.minorticks_off();end.set_xlabel('Relative AF intensity (R; log2 scale)');grid(end,'x')
    end.legend(handles=[Line2D([],[],ls='',marker='o',mfc='white',mec=GRAY,label='2021'),Line2D([],[],ls='',marker='o',color=GRAY,label='2025')],loc='upper center',bbox_to_anchor=(.5,-.18),frameon=False,ncol=2)
    dump(out/'provenance/main_artist_contract.json',dict(panel_labels=['a','b','c','d'],titles=False,b_year_positions=top.transData.transform(np.c_[c.year,np.zeros(5)])[:,0],
      b_gap_positions=bottom.transData.transform(np.c_[c.year,np.zeros(5)])[:,0],non_AF_label='non-AF',main_matching_spec='count_composition',
      d_order=ORDER[:10],d_scale='log2 raw R ticks',d_year_symbols=['open2021','filled2025'],main_d_all_positive=True))
    export(fig,out,'Figure1_a_d')

def map_panel(ax,out):
    import geopandas as gpd
    world=gpd.read_file(out/'assets/ne_110m_admin_0_countries.zip');world=world[world.NAME.ne('Antarctica')]
    first=load(out,'first_observed_stage_map_source').set_index('country_code');registry=set(load(out,'annual_country_credits').country_code)
    palette=['#173873','#6685BE','#BBCDED'];colors=[palette[int(first.loc[c,'phase_index'])] if c in first.index else '#E4E4E4' if c in registry else '#F8F8F8' for c in world.ISO_A2_EH]
    world.plot(ax=ax,color=colors,edgecolor='white',linewidth=.2,aspect=1)
    locations=pd.read_csv(out/'assets/country_first_observed_locations.csv',keep_default_na=False).set_index('country_code')
    for code in first.index.difference(set(world.ISO_A2_EH)):
        if code not in locations.index or locations.loc[code,'longitude']=='':continue
        r=locations.loc[code];ax.scatter(float(r.longitude),float(r.latitude),s=6,color=palette[int(first.loc[code,'phase_index'])],edgecolor=GRAY,lw=.25)
    ax.set_xlim(-180,180);ax.set_ylim(-58,85);ax.set_aspect('equal');ax.axis('off')
    handles=[Patch(fc=v,label=k) for v,k in zip(palette,['Pre-AF2','AF2','AF3'])]+[Patch(fc='#E4E4E4',label='Not observed'),Patch(fc='#F8F8F8',ec='#BBBBBB',lw=.4,label='Outside code registry')]
    ax.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,-.03),ncol=5,frameon=False,fontsize=6.8,handlelength=1.1,columnspacing=1)

def ed1(out):
    fig=plt.figure(figsize=(183/25.4,158/25.4));letter(fig,'a',.025,.98);mapax=fig.add_axes([.055,.51,.91,.455]);map_panel(mapax,out)
    data=load(out,'monthly_diffusion');dates=pd.to_datetime(data.month);axes=[fig.add_axes([.12,.285,.82,.14]),fig.add_axes([.12,.12,.82,.10])]
    letter(fig,'b',.025,.44);letter(fig,'c',.025,.23)
    axes[0].step(dates,data.cumulative_countries,where='post',color=BLUE);axes[1].bar(dates,data.new_countries,width=24,color=BLUE)
    for ax in axes:
        for k,(left,right) in enumerate([('2020-01-01','2021-07-01'),('2021-07-01','2024-05-01'),('2024-05-01','2026-01-01')]):ax.axvspan(pd.Timestamp(left),pd.Timestamp(right),color=['#F0F2F7','#F8F7F2','#F8F3F5'][k],zorder=0)
        for date in ['2021-07-01','2024-05-01']:ax.axvline(pd.Timestamp(date),color='#8F959E',ls='--',lw=.6)
        ax.set_xlim(pd.Timestamp('2020-01-01'),pd.Timestamp('2025-12-31'));grid(ax)
    axes[0].tick_params(labelbottom=False);axes[0].set_ylabel('Cumulative countries / regions');axes[1].set_ylabel('Monthly new');axes[1].set_xlabel('Publication month')
    for date,n in [('2021-06-01',14),('2024-04-01',123),('2025-12-01',143)]:
        axes[0].annotate(str(n),(pd.Timestamp(date),n),xytext=(-6 if n==143 else 0,5),textcoords='offset points',ha='right' if n==143 else 'center',fontsize=7.5,color=BLUE)
    axes[0].set_ylim(0,167)
    for date,text,dx in [('2021-07-01','AF2 code + AFDB\nJuly 2021',-7),('2024-05-01','AF3 publication/server\nMay 2024',7)]:
        axes[0].annotate(text,(pd.Timestamp(date),165),xytext=(dx,5),textcoords='offset points',ha='right' if dx<0 else 'left',va='bottom',fontsize=6.5,color=MUTED)
    export(fig,out,'ED1_geographic_diffusion')

def ed2(out):
    fig=plt.figure(figsize=(183/25.4,85/25.4));a=fig.add_axes([.10,.28,.36,.63]);b=fig.add_axes([.61,.28,.34,.63]);letter(fig,'a',.025,.97);letter(fig,'b',.53,.97)
    x=load(out,'ed2a_attributed_composition');years=np.arange(2021,2026);bottom=np.zeros(5);codes=x.country_code.drop_duplicates().tolist()
    cols=plt.get_cmap('Blues')(np.linspace(.95,.22,10)).tolist()+['#C1C1C1']
    for i,code in enumerate(codes):
        v=x[x.country_code.eq(code)].set_index('year').reindex(years).attributed_fraction*100;a.bar(years,v,bottom=bottom,width=.7,color=cols[i],ec='white',lw=.2,label=code);bottom+=v.to_numpy()
    a.set_xticks(years);a.set_ylim(0,100);a.set_ylabel('Attributed AF output (%)');a.set_xlabel('Publication year')
    a.legend(frameon=False,loc='upper center',bbox_to_anchor=(.5,-.23),ncol=4,fontsize=6.2,columnspacing=.9,handlelength=1.2)
    c=load(out,'concentration').query('year>=2021')
    for field,col,mark,label in [('af_top5',BLUE,'o','Annual top five'),('af_top10','#8A6B9B','s','Annual top ten')]:b.plot(c.year,c[field]*100,color=col,marker=mark,label=label)
    b.set_xticks(years);b.set_ylim(0,100);b.set_ylabel('Attributed AF output (%)');b.set_xlabel('Publication year');grid(b);b.legend(frameon=False,loc='lower right')
    export(fig,out,'ED2_geographic_output')

def s1(out):
    fig=plt.figure(figsize=(183/25.4,150/25.4));axes=[fig.add_axes([.04,.70,.92,.25]),fig.add_axes([.04,.37,.92,.25]),fig.add_axes([.04,.06,.92,.23])]
    for ax in axes:ax.axis('off')
    for s,y in [('a',.98),('b',.65),('c',.32)]:letter(fig,s,.02,y)
    nodes=[('OpenAlex corpus','6,046,663 records\n2015–2025; 22 subfields'),('Eligible scope','4,686,896 works\nArticle / review / preprint'),('Approved study links','4,686,879 studies\n2 original + 15 revision removals')]
    for i,(title,text) in enumerate(nodes):
        node(axes[0],.02+i*.34,.15,.28,.65,title,text)
        if i<2:arrow(axes[0],(.30+i*.34,.48),(.36+i*.34,.48))
    nodes=[('Initial candidate branch','29,127 work records\nKeywords + four seed papers'),('Additional recall branch','826 leads → 765 eligible works\nExpanded keywords + AF1'),('Evidence review','556 A/B packets; C: 516\n28 insufficient + 2 oversize')]
    for i,(title,text) in enumerate(nodes):node(axes[1],.02+i*.34,.15,.28,.65,title,text)
    # No arrow implying all later candidates are a subset of initial candidates.
    axes[1].text(.50,.01,'Further retrieval is an additional branch, not a 29,127 → 16,414 funnel.',ha='center',fontsize=7,color=MUTED)
    nodes=[('Supplementary dispositions','74 use / 159 non-use\n1 platform / 531 uncertain\n765 work records'),('Study-level inclusion','Two yes labels + accepted links\n16,341 old + 70 + 3'),('Main analysis corpus','16,414 AF-use studies\n2,714,594 eligible studies\n2020–2025')]
    for i,(title,text) in enumerate(nodes):
        node(axes[2],.02+i*.34,.15,.28,.75,title,text)
        if i<2:arrow(axes[2],(.30+i*.34,.52),(.36+i*.34,.52))
    export(fig,out,'S1_corpus_selection')

def s2(out):
    fig=plt.figure(figsize=(183/25.4,150/25.4));a=fig.add_axes([.05,.69,.90,.26]);a.axis('off');letter(fig,'a',.02,.98)
    for i,(title,text) in enumerate([('Historical pilot','150 candidate works\nTwo reference annotations'),('Reference processing','109 adjudications\n41 reference agreements'),('Evaluation subset','122 determinate\n28 unresolved retained')]):
        node(a,.02+i*.34,.20,.28,.65,title,text)
        if i<2:arrow(a,(.30+i*.34,.52),(.36+i*.34,.52))
    a.text(.5,.02,'Author-confirmed pre-answer human judgement; not a certified independent held-out validation.',ha='center',fontsize=6.5,color=MUTED)
    letter(fig,'b',.02,.61);ax=fig.add_axes([.13,.19,.33,.32]);matrix=load(out,'pilot_confusion').query('system=="production"').pivot(index='reference',columns='prediction',values='n').reindex(index=['yes','no'],columns=['yes','no','uncertain/missing'])
    ax.imshow(matrix,cmap='Blues',vmin=0,vmax=100,aspect='auto')
    for i in range(2):
        for j in range(3):ax.text(j,i,str(matrix.iloc[i,j]),ha='center',va='center',fontsize=10,color='white' if matrix.iloc[i,j]>50 else '#202428')
    ax.set_xticks([0,1,2],['Use','Non-use','Unknown /\nmissing']);ax.set_yticks([0,1],['Use','Non-use']);ax.set_ylabel('Reference label');ax.set_xlabel('Production final labels on pilot overlap')
    v=load(out,'Table_S2_pilot_metrics').query('system=="production"').iloc[0]
    fig.text(.13,.55,f'Evaluated n = {int(v.evaluated_n)}\nPrecision = {v.precision:.3f}; recall = {v.recall:.3f}',fontsize=7)
    letter(fig,'c',.53,.61);ax=fig.add_axes([.72,.19,.23,.32]);states=load(out,'pilot_reference_states').groupby('reference_status').n.sum()
    labels=['Unresolved evidence\n(reference N=150)','Uncertain consensus\n(reference N=150)','Reference non-use /\nfinal use (N=122)','Final unknown\n(evaluated N=122)'];values=[int(states['unresolved_evidence']),int(states['uncertain_consensus']),int(v.FP),int(v.undecided_or_missing)]
    ax.barh([3,2,1,0],values,color=['#B0B8C4','#D7DDE5','#8D9BB2','#CAD1DD'],height=.55)
    for y,n in zip([3,2,1,0],values):ax.text(n+.4,y,str(n),va='center',fontsize=8)
    ax.set_yticks([3,2,1,0],labels,fontsize=6.3);ax.set_xlim(0,30);ax.set_xlabel('Works (row-specific denominator)');grid(ax,'x')
    fig.text(.12,.065,'Candidate-pilot recall is not retrieval recall for the OpenAlex corpus. Unknown predictions are not true negatives.',fontsize=6.6,color=MUTED)
    export(fig,out,'S2_identification_reference_comparison')

def s3(out):
    fig=plt.figure(figsize=(183/25.4,92/25.4));a=fig.add_axes([.10,.24,.34,.66]);b=fig.add_axes([.66,.24,.29,.66]);letter(fig,'a',.025,.97);letter(fig,'b',.50,.97)
    counts=load(out,'annual_counts').query('publication_year>=2020');a.bar(counts.publication_year,counts.confirmed_af,color=BLUE,width=.7)
    for r in counts.itertuples():a.text(r.publication_year,r.confirmed_af+65,f'{r.confirmed_af:,}',ha='center',fontsize=7)
    a.set_ylim(0,6500);a.set_xticks(counts.publication_year);a.set_ylabel('AF-use studies');a.set_xlabel('Publication year');grid(a)
    order=json.loads((out/'provenance/subfield_order.json').read_text());p=load(out,'subfield_period_top5_other').set_index('display_group').reindex(order)
    y=np.arange(6);b.barh(y-.16,p.AF_share*100,height=.30,color=BLUE,label='AF');b.barh(y+.16,p.eligible_share*100,height=.30,color='#BBC5D8',label='Eligible corpus')
    b.set_yticks(y,order,fontsize=6.6);b.invert_yaxis();b.set_xlabel('2020–2025 studies (%)');b.legend(frameon=False,loc='lower right',fontsize=6.5);grid(b,'x')
    export(fig,out,'S3_growth_disciplinary_composition')

def s4(out):
    fig=plt.figure(figsize=(183/25.4,95/25.4));a=fig.add_axes([.10,.30,.35,.60]);b=fig.add_axes([.62,.30,.33,.60]);letter(fig,'a',.025,.97);letter(fig,'b',.53,.97)
    x=load(out,'subfield_year_top5_other');order=json.loads((out/'provenance/subfield_order.json').read_text());years=np.arange(2020,2026);bottom=np.zeros(6)
    for code,color,mark,ls in zip(order,PALETTE,['o','s','^','D','v','x'],['-','--',':','-.','--',':']):
        v=x[x.display_group.eq(code)].set_index('year').reindex(years);a.bar(years,v.AF_share*100,bottom=bottom,color=color,width=.7,ec='white',lw=.25,label=code);bottom+=v.AF_share.to_numpy()*100
        b.plot(years,v.AF_rate*100,color=color,marker=mark,ls=ls,lw=.9,ms=2.8,label=code)
    a.set_ylim(0,100);a.set_ylabel('Annual AF studies (%)');b.set_ylabel('AF / eligible studies (%)')
    for ax in [a,b]:ax.set_xticks(years);ax.set_xlabel('Publication year')
    grid(b);fig.legend(*b.get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.53,.035),ncol=3,frameon=False,fontsize=6.5)
    export(fig,out,'S4_disciplinary_patterns')

def s5(out):
    x=load(out,'figure1_normalization_heatmap_source');fig=plt.figure(figsize=(115/25.4,150/25.4));letter(fig,'a',.025,.98);ax=fig.add_axes([.20,.20,.70,.70])
    values=x.set_index(['country_code','year']).reindex(pd.MultiIndex.from_product([ORDER+['Other'],range(2021,2026)])).colour_log2_R.to_numpy().reshape(21,5)
    im=ax.imshow(values,cmap=CMAP,norm=TwoSlopeNorm(vmin=-2,vcenter=0,vmax=2),aspect='auto',interpolation='nearest');ax.set_yticks(range(21),ORDER+['Other']);ax.set_xticks(range(5),range(2021,2026));ax.tick_params(top=True,labeltop=True,bottom=False,labelbottom=False,length=0)
    for sp in ax.spines.values():sp.set_visible(False)
    ax.axhline(19.5,c='white',lw=1.4);cax=fig.add_axes([.23,.115,.64,.018]);cb=fig.colorbar(im,cax=cax,orientation='horizontal',extend='both',ticks=[-2,-1,0,1,2]);cb.set_ticklabels(['≤0.25','0.5','1','2','≥4']);cb.set_label('Relative AF intensity (R)')
    fig.text(.55,.035,'1 = corpus-wide average',ha='center',fontsize=7,color=MUTED);export(fig,out,'S5_country_normalized_participation')

def s6(out):
    fig=plt.figure(figsize=(183/25.4,154/25.4));c=load(out,'concentration');a=fig.add_axes([.11,.62,.34,.28]);b=fig.add_axes([.63,.62,.32,.28]);letter(fig,'a',.025,.97);letter(fig,'b',.54,.97)
    gini_pair(a,c,full=True);AFlegend(a,'lower right');a.set_xlabel('Publication year')
    m=load(out,'matching_summary');styles=[(GRAY,'o','-'),('#8C7D9E','s','--'),('#4C8E8C','^',':')]
    for spec,(col,mark,ls) in zip(SPECS,styles):
        x=m[m.spec.eq(spec)];interval_line(b,x.year,x.point,x.lower,x.upper,spec.replace('_',' '),col,mark,ls)
    b.axhline(0,c='#AAAAAA',lw=.6,ls='--');b.set_xticks(range(2021,2026));b.set_ylabel('Matched AF − non-AF Gini');b.set_xlabel('Publication year');grid(b)
    b.legend(frameon=False,loc='upper center',bbox_to_anchor=(.5,-.27),fontsize=5.8)
    letter(fig,'c',.025,.43);cax=fig.add_axes([.28,.13,.22,.245]);ep=load(out,'matching_endpoint_changes')
    labels=[]
    for i,r in enumerate(ep.itertuples()):
        col=styles[SPECS.index(r.spec)][0];cax.plot([r.lower,r.upper],[i,i],c=col,lw=.9);cax.scatter(r.point,i,c=col,s=16);labels.append(r.spec.replace('count_composition_known_country','Composition, known').replace('count_composition','Count + composition').replace('count_only','Count only')+'\n'+str(r.start)+'–2025')
    cax.set_yticks(range(6),labels,fontsize=6);cax.set_ylim(5.7,-.7);cax.axvline(0,c='#AAAAAA',lw=.6,ls='--');cax.set_xlabel('Endpoint change');grid(cax,'x')
    letter(fig,'d',.54,.43);d=fig.add_axes([.66,.13,.29,.245]);coverage=load(out,'annual_source_coverage').query('year>=2020 and group in ["AF","C"]')
    for g,col,mark,ls,label in [('AF',BLUE,'o','-','AF'),('C',ORANGE,'s','--','non-AF')]:
        x=coverage[coverage.group.eq(g)];d.plot(x.year,x.coverage*100,color=col,marker=mark,ls=ls,label=label)
    d.set_ylim(0,100);d.set_xticks(range(2020,2026));d.set_ylabel('Country-attribution coverage (%)');d.set_xlabel('Publication year');grid(d);d.legend(frameon=False,fontsize=6.7,loc='lower right')
    export(fig,out,'S6_concentration_sensitivity')

def run(out):
    with plt.rc_context():
        style()
        for fn in [main,ed1,ed2,s1,s2,s3,s4,s5,s6]:fn(out);print('Rendered '+fn.__name__,flush=True)
    previews=sorted((out/'figures').glob('*_preview.png'))
    for page,start in enumerate(range(0,len(previews),4),1):
        sheet=Image.new('RGB',(1600,1800),'white');draw=ImageDraw.Draw(sheet)
        for i,p in enumerate(previews[start:start+4]):
            with Image.open(p) as im:
                im.thumbnail((780,840));xx=i%2*800;yy=i//2*900;draw.text((xx+8,yy+5),p.stem,fill='black');sheet.paste(im,(xx+(800-im.width)//2,yy+30))
        sheet.save(out/'provenance'/f'contact_sheet_{page}.png')

if __name__=='__main__':run(OUT)
