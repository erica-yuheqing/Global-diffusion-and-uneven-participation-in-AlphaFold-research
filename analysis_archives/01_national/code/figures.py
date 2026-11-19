"""Finding1 v7: two-panel main figure, three ED and six supplementary figures."""
from common import *
from support import plt, matplotlib, Line2D, Patch, Image, ImageDraw, export, letter, grid, node, arrow, map_panel, style
import support

NAMES=['Figure1_a_b','ED1_identification','ED2_geographic_diffusion','ED3_country_patterns',
       'S1_corpus_selection','S2_identification_reference_comparison','S3_growth_disciplinary_composition',
       'S4_disciplinary_patterns','S5_country_normalized_participation','S6_concentration_sensitivity']

def main(out):
    a=load(out,'source_data/Figure1b_upper.csv');r=load(out,'source_data/Figure1b_lower.csv');m=load(out,'source_data/Figure1c.csv')
    fig=plt.figure(figsize=(183/25.4,92/25.4))
    ax=fig.add_axes([.105,.195,.347,.62]);bx=fig.add_axes([.638,.195,.347,.62])
    letter(fig,'a',.025,.98);letter(fig,'b',.547,.98)
    for key,col,mark,label in [('af',BLUE,'o','AF'),('comparator',ORANGE,'s','non-AF')]:
        ax.fill_between(a.year,a[key+'_lower'],a[key+'_upper'],color=col,alpha=.13,lw=0)
        ax.plot(a.year,a[key+'_gini'],color=col,marker=mark,ls='-',label=label,zorder=3)
    ax.set_ylim(.89,.96);ax.set_yticks([.90,.92,.94,.96]);ax.set_ylabel('Gini coefficient');grid(ax)
    ax.legend(frameon=False,loc='lower center',bbox_to_anchor=(.50,1.11),ncol=2,columnspacing=1.5)
    for yr,ha,dx in [(2021,'left',2),(2025,'right',-2)]:
        v=float(a.loc[a.year.eq(yr),'af_gini'].iloc[0]);ax.annotate(f'{v:.4f}',(yr,v),xytext=(dx,7),textcoords='offset points',ha=ha,color=BLUE,fontsize=8)
    bx.fill_between(r.year,r.delta_lower,r.delta_upper,color=GRAY,alpha=.13,lw=0)
    bx.plot(r.year,r.delta_gini,color=GRAY,marker='D',ls='-',label='Raw gap',zorder=3)
    bx.errorbar(m.year,m.point,yerr=[m.point-m.lower,m.upper-m.point],color=PURPLE,marker='o',ls='--',capsize=2,elinewidth=.8,label='Matched gap',zorder=4)
    bx.axhline(0,color='#777777',lw=.7,ls=(0,(4,3)));bx.set_ylim(-.003,.055);bx.set_yticks(np.arange(0,.051,.01))
    bx.set_ylabel('Gini difference (AF − non-AF)');grid(bx)
    bx.legend(frameon=False,loc='lower center',bbox_to_anchor=(.5,1.11),ncol=2,columnspacing=1.0,handlelength=1.8)
    for data,col,key,dy in [(r,GRAY,'delta_gini',7),(m,PURPLE,'point',-16)]:
        for yr,ha,dx in [(2021,'left',3),(2025,'right',-2)]:
            val=float(data.loc[data.year.eq(yr),key].iloc[0]);bx.annotate(f'{val:.4f}',(yr,val),xytext=(dx,dy if not (yr==2021 and key=='delta_gini') else -14),textcoords='offset points',ha=ha,color=col,fontsize=8)
    for axis in [ax,bx]:axis.set_xticks(range(2021,2026));axis.set_xlim(2020.8,2025.2);axis.set_xlabel('Publication year')
    dump(out/'provenance/main_artist_contract.json',{'panels':['a','b'],'titles':False,'years':list(a.year),'a_ylim':ax.get_ylim(),'b_ylim':bx.get_ylim(),
        'a_markers':['o','s'],'a_lines':['-','-'],'b_markers':['D','o'],'b_lines':['-','--'],'raw_uncertainty':'conditional 95% whole-study bootstrap; 1000 replicates',
        'matched_uncertainty':'AF-fixed central 95% matched range; 2000 replicates','matching_spec':'count_composition','secondary_axes':False,'smoothing':False})
    export(fig,out,NAMES[0])

def identification(out):
    fig=plt.figure(figsize=(183/25.4,122/25.4));ax=fig.add_axes([.055,.04,.89,.93]);ax.axis('off');ax.set_xlim(0,1);ax.set_ylim(0,1)
    node(ax,.17,.80,.66,.17,'OpenAlex life-science corpus','6,046,663 publication records · 2015–2025\n22 eligible primary subfields',8)
    node(ax,.01,.52,.45,.18,'Initial candidate retrieval','Keywords + AF2 / Multimer / AFDB / AF3 citations\n29,127 candidate work records',8)
    node(ax,.54,.52,.45,.18,'Supplementary retrieval','826 additional work-record leads\n765 eligible candidate works · expanded terms + AF1',8)
    arrow(ax,(.36,.80),(.23,.705));arrow(ax,(.66,.80),(.77,.705))
    node(ax,.14,.24,.72,.21,'Evidence assessment: the study’s own AF use','Abstract / full-text evidence · A/B model review\nRouted C review + targeted human adjudication\nCitation / background / future plans alone: not sufficient\nInsufficient evidence retained as unknown',8)
    arrow(ax,(.23,.52),(.33,.455));arrow(ax,(.77,.52),(.67,.455))
    node(ax,.14,.015,.72,.15,'Approved study consolidation and inclusion','16,414 AF-use studies · 2020–2025\nMain eligible scope: 2,714,594 studies',8)
    arrow(ax,(.50,.24),(.50,.17))
    export(fig,out,NAMES[1])

def diffusion(out):
    fig=plt.figure(figsize=(183/25.4,166/25.4));letter(fig,'a',.025,.98)
    ma=fig.add_axes([.045,.51,.92,.46]);map_panel(ma,out)
    data=load(out,'monthly_diffusion');dates=pd.to_datetime(data.month)
    a=fig.add_axes([.135,.28,.815,.145]);b=fig.add_axes([.135,.10,.815,.105]);letter(fig,'b',.025,.45);letter(fig,'c',.025,.235)
    a.step(dates,data.cumulative_countries,where='post',color=BLUE);b.bar(dates,data.new_countries,width=24,color=BLUE)
    for ax in [a,b]:
        for i,(l,r) in enumerate([('2020-01-01','2021-07-01'),('2021-07-01','2024-05-01'),('2024-05-01','2026-01-01')]):ax.axvspan(pd.Timestamp(l),pd.Timestamp(r),color=['#F0F2F7','#F8F7F2','#F8F3F5'][i],zorder=0)
        for date in ['2021-07-01','2024-05-01']:ax.axvline(pd.Timestamp(date),color='#8F959E',ls='--',lw=.6)
        ax.set_xlim(pd.Timestamp('2020-01-01'),pd.Timestamp('2025-12-31'));grid(ax)
        ax.set_xticks(pd.to_datetime([f'{y}-01-01' for y in range(2020,2026)]),range(2020,2026))
    a.tick_params(labelbottom=False);a.set_ylabel('Cumulative countries / regions');b.set_ylabel('Monthly new');b.set_xlabel('Publication month');b.set_yticks([0,5,10]);a.set_ylim(0,165)
    for date,n in [('2021-06-01',14),('2024-04-01',123),('2025-12-01',143)]:a.annotate(str(n),(pd.Timestamp(date),n),xytext=(-4 if n==143 else 0,6),textcoords='offset points',ha='right' if n==143 else 'center',color=BLUE)
    for date,label,dx in [('2021-07-01','AF2 code + AFDB\nJuly 2021',-6),('2024-05-01','AF3 publication/server\nMay 2024',6)]:a.annotate(label,(pd.Timestamp(date),165),xytext=(dx,7),textcoords='offset points',ha='right' if dx<0 else 'left',va='bottom',fontsize=7,color=MUTED)
    export(fig,out,NAMES[2])

def countries(out):
    fig=plt.figure(figsize=(183/25.4,156/25.4));a=fig.add_axes([.10,.25,.30,.67]);b=fig.add_axes([.57,.64,.38,.28]);c=fig.add_axes([.57,.25,.38,.27])
    letter(fig,'a',.025,.98);letter(fig,'b',.47,.98);letter(fig,'c',.47,.58)
    d=load(out,'figure1d_top10_endpoints');a.axvline(1,color='#969BA2',lw=.7,ls='--');a.set_xscale('log',base=2)
    for i,code in enumerate(ORDER[:10]):
        x=d[d.country_code.eq(code)].set_index('year');v1=float(x.loc[2021,'R']);v5=float(x.loc[2025,'R'])
        a.plot([v1,v5],[i,i],color='#AFB5BE',lw=.9);a.scatter(v1,i,s=25,facecolor='white',edgecolor=BLUE,lw=.9,zorder=3);a.scatter(v5,i,s=25,facecolor=BLUE,edgecolor=BLUE,lw=.7,zorder=4)
        if code in ['CN','GB']:a.annotate(f'{v1:.2f} → {v5:.2f}',(max(v1,v5),i),xytext=(2,9),textcoords='offset points',ha='right',fontsize=7,color=BLUE)
    a.set_yticks(range(10),ORDER[:10]);a.set_ylim(9.7,-.7);a.set_xlim(.25,4);a.set_xticks([.25,.5,1,2,4],['0.25','0.5','1','2','4']);a.minorticks_off();a.set_xlabel('Relative AF intensity (R; log2 scale)');grid(a,'x')
    a.legend(handles=[Line2D([],[],ls='',marker='o',mfc='white',mec=BLUE,label='2021'),Line2D([],[],ls='',marker='o',color=BLUE,label='2025')],frameon=False,ncol=2,loc='upper center',bbox_to_anchor=(.5,-.13))
    top=load(out,'source_data/ED2b.csv')
    for field,col,mark,label in [('top5_percent',BLUE,'o','Annual top five'),('top10_percent',PURPLE,'s','Annual top ten')]:b.plot(top.year,top[field],color=col,marker=mark,label=label)
    b.set_ylim(0,100);b.set_ylabel('Attributed AF output (%)');b.set_xlabel('Publication year');b.set_xticks(range(2021,2026));grid(b);b.legend(frameon=False,loc='lower right',fontsize=7)
    x=load(out,'ed2a_attributed_composition');years=np.arange(2021,2026);bottom=np.zeros(5);codes=['US','CN','DE','GB','FR','JP','CA','IT','ES','IN','Other']
    names=['United States','China','Germany','United Kingdom','France','Japan','Canada','Italy','Spain','India','Other']
    colors=plt.get_cmap('Blues')(np.linspace(.95,.23,10)).tolist()+['#C1C1C1']
    for code,name,col in zip(codes,names,colors):
        v=x[x.country_code.eq(code)].set_index('year').reindex(years).attributed_fraction.to_numpy()*100
        c.bar(years,v,bottom=bottom,width=.7,color=col,ec='white',lw=.25,label=f'{code}: {name}' if code!='Other' else name);bottom+=v
    c.set_ylim(0,100);c.set_xticks(years);c.set_ylabel('Attributed AF output (%)');c.set_xlabel('Publication year')
    c.legend(frameon=False,loc='upper center',bbox_to_anchor=(.40,-.28),ncol=3,fontsize=6.8,columnspacing=.8,handlelength=1.1)
    export(fig,out,NAMES[3])

def audit_flow(out):
    fig=plt.figure(figsize=(183/25.4,235/25.4));axes=[fig.add_axes([.05,.735,.90,.23]),fig.add_axes([.05,.375,.90,.29]),fig.add_axes([.05,.035,.90,.275])]
    for ax in axes:ax.axis('off');ax.set_xlim(0,1);ax.set_ylim(0,1)
    for lab,y in [('a',.985),('b',.69),('c',.335)]:letter(fig,lab,.02,y)
    a,b,c=axes
    # Stage counts are read from frozen sources; no false candidate-to-study subtraction.
    descriptions=[('Raw corpus','6,046,663 publication records\n2015–2025 · 22 subfields'),('Eligible foundations','4,686,896 work records\nArticle / review / preprint'),('Original approved links','4,686,894 study units\nTwo original duplicate removals'),('Revision approved links','4,686,879 study units\n15 further duplicate removals'),('Main eligible scope','2,714,594 studies\n2020–2025')]
    positions=[(.01,.59),(.36,.59),(.71,.59),(.71,.08),(.36,.08)]
    for (title,text),(x,y) in zip(descriptions,positions):node(a,x,y,.28,.34,title,text,7.6)
    for fr,to in [((.30,.76),(.355,.76)),((.65,.76),(.705,.76)),((.85,.59),(.85,.43)),((.71,.25),(.645,.25))]:arrow(a,fr,to)
    node(b,.01,.73,.44,.24,'Initial candidate branch','29,127 candidate work records\nKeywords + four initial seeds',7.8)
    node(b,.56,.73,.43,.24,'Additional retrieval','826 work-record leads\n2015–2025 source pool · AF1 / expanded terms',7.5)
    node(b,.56,.43,.43,.22,'Eligible supplementary works','765 works; 61 outside eligible types\n2020–2025 AF-use target',7.7);arrow(b,(.77,.73),(.77,.655))
    node(b,.01,.12,.28,.23,'Earlier decisive review','179 works\n71 use / 107 non-use / 1 platform',7.5)
    node(b,.36,.12,.29,.23,'Remaining review','586 works\n28 insufficient / 2 oversize\n556 A/B-eligible',7.5)
    node(b,.71,.12,.28,.23,'Submitted / routed','556 works per A/B\n154 full-text + 402 abstract\n516 C reviews',7.5)
    arrow(b,(.69,.43),(.15,.355));arrow(b,(.78,.43),(.50,.355));arrow(b,(.655,.235),(.705,.235))
    b.text(.23,.59,'Independent retrieval branches\nconverge at evidence assessment;\nnot a sequential exclusion funnel.',ha='center',va='center',fontsize=7.6,color=MUTED)
    for i,(title,text) in enumerate([('Accepted use','74 work records'),('Accepted non-use','159 work records'),('Platform excluded','1 work record'),('Unknown retained','531 work records')]):node(c,.01+i*.253,.67,.225,.22,title,text+'\n765 supplementary works in total',7.1)
    c.text(.5,.96,'Supplementary evidence dispositions · 2020–2025 target',ha='center',fontsize=8)
    for i,(title,text) in enumerate([('Old main AF','16,341 studies'),('Initial net addition','70 studies\n71 positive works − 1 duplicate'),('Latest net addition','3 studies'),('Final main AF','16,414 studies\n2020–2025')]):
        node(c,.01+i*.253,.10,.225,.29,title,text,7.5)
        if i<3:arrow(c,(.237+i*.253,.245),(.258+i*.253,.245))
    c.text(.5,.51,'74 positive works = 73 net additional studies; accepted version links applied.',ha='center',fontsize=7.7,color=MUTED)
    export(fig,out,NAMES[4])

def render(out):
    with plt.rc_context():
        style()
        for fn in [main,identification,diffusion,countries,audit_flow,support.s2,support.s3,support.s4,support.s5,support.s6]:
            fn(out);print('Rendered '+fn.__name__,flush=True)
    for page,start in enumerate(range(0,len(NAMES),4),1):
        sheet=Image.new('RGB',(1800,1900),'white');pen=ImageDraw.Draw(sheet)
        for i,name in enumerate(NAMES[start:start+4]):
            with Image.open(out/'figures'/f'{name}_preview.png') as im:
                im.thumbnail((880,890));x=i%2*900;y=i//2*950;pen.text((x+12,y+8),name,fill='black');sheet.paste(im,(x+(900-im.width)//2,y+35))
        sheet.save(out/'provenance'/f'contact_sheet_{page}.png')

if __name__=='__main__':
    import sys
    render(Path(sys.argv[1]))
