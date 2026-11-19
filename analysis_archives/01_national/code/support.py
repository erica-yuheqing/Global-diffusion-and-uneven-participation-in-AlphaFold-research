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
    plt.rcParams.update({'font.family':'Arial','font.size':8,'axes.labelsize':8,'xtick.labelsize':8,'ytick.labelsize':8,
      'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'legend.fontsize':8,'lines.linewidth':1.1,'lines.markersize':3.4,
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
        rgb=im.convert('RGB');rgb.save(p,dpi=(600,600),icc_profile=profile)
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
    gini_pair(a,c,full=True);a.annotate('n=11',(2020,float(c.iloc[0].af_gini)),xytext=(8,-18),textcoords='offset points',fontsize=8);AFlegend(a,'lower right');a.set_xlabel('Publication year')
    m=load(out,'matching_summary');styles=[(GRAY,'o','-'),('#8C7D9E','s','--'),('#4C8E8C','^',':')]
    for spec,(col,mark,ls) in zip(SPECS,styles):
        x=m[m.spec.eq(spec)];interval_line(b,x.year,x.point,x.lower,x.upper,spec.replace('_',' '),col,mark,ls)
    b.axhline(0,c='#AAAAAA',lw=.6,ls='--');b.set_xticks(range(2021,2026));b.set_ylabel('Matched AF − non-AF Gini');b.set_ylim(-.003,.058);b.set_xlabel('Publication year');grid(b)
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

