"""Draw numbered supplementary figures from the verified income-analysis tables."""
from pathlib import Path
import string
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'Supplementary_S30_S31_refined'
OUT.mkdir(exist_ok=True)
BLUE='#35527d'
BAND='#f6f9fd'
GRID='#e4edf7'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':8,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7.5,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,'axes.edgecolor':'#8399b4','axes.linewidth':.65,'xtick.major.width':.65,'ytick.major.width':0,'xtick.color':BLUE,'ytick.color':BLUE,'axes.titlecolor':BLUE,'pdf.fonttype':42,'svg.fonttype':'none'})
INCOMES=['L','LM','UM','H']
LABELS={'L':'Low income','LM':'Lower-middle income','UM':'Upper-middle income','H':'High income'}
COLORS={'L':'#5899d1','M':'#2b927d','H':'#173f86'}

def save(fig,name):
    for ext in ['pdf','svg']:
        fig.savefig(OUT/f'{name}.{ext}',facecolor='white')
    fig.savefig(OUT/f'{name}.png',dpi=600,facecolor='white')
    fig.savefig(OUT/f'{name}_preview.png',dpi=220,facecolor='white')
    plt.close(fig)

cov=pd.read_csv(ROOT/'tables/coverage_by_income_group.csv')
fig,axes=plt.subplots(2,2,figsize=(183/25.4,139/25.4),sharex=True,sharey=True)
fig.subplots_adjust(left=.105,right=.98,bottom=.115,top=.84,hspace=.38,wspace=.25)
for i,(ax,g) in enumerate(zip(axes.flat,INCOMES)):
    z=cov[cov.income_group.eq(g)]
    n=int(z.countries.iloc[0])
    ax.text(-.12,1.075,string.ascii_lowercase[i],transform=ax.transAxes,fontsize=10,fontweight='bold',color='#111820')
    ax.set_title(f'{LABELS[g]} (n = {n})',loc='left',pad=11,fontweight='normal')
    for low in [0,20,40]:ax.axhspan(low,low+10,color=BAND,zorder=0,lw=0)
    for inst,marker,label in [('L','o','Lower'),('M','s','Middle'),('H','^','Higher')]:
        v=z[z.institution_group.eq(inst)].sort_values('year')
        ax.plot(v.year,v.equal_country_coverage_pct,color=COLORS[inst],marker=marker,lw=1.05,ms=3.5,label=label,zorder=3)
        end=float(v.equal_country_coverage_pct.iloc[-1])
        label_y=end
        if g=='L' and inst=='L':label_y=end-1.45
        if g=='L' and inst=='M':label_y=end+1.75
        ax.annotate(f'{end:.2f}%',xy=(2025,end),xytext=(2025.15,label_y),color=COLORS[inst],fontsize=7,va='center',arrowprops={'arrowstyle':'-','color':COLORS[inst],'lw':.45} if label_y!=end else None)
    if g=='L':ax.text(.02,.94,'Ethiopia and Uganda',transform=ax.transAxes,fontsize=6.8,color=BLUE,va='top')
    ax.set_xlim(2019.85,2026.3);ax.set_ylim(0,48);ax.set_xticks(range(2020,2026));ax.set_yticks([0,10,20,30,40]);ax.set_axisbelow(True);ax.grid(axis='x',color=GRID,lw=.45);ax.tick_params(axis='x',length=3);ax.tick_params(axis='y',length=0,pad=6)
fig.text(.54,.972,'Institutional groups · within-country baseline output',fontsize=7.5,ha='center',color=BLUE)
fig.text(.025,.48,'Cumulative institutional coverage (%)',rotation=90,va='center',fontsize=8)
fig.text(.54,.035,'Publication year',ha='center',fontsize=8)
handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='center',bbox_to_anchor=(.54,.933),ncol=3,frameon=False,fontsize=7.5,columnspacing=2,handlelength=0,numpoints=1)
save(fig,'Supplementary_Fig_S30')

d=pd.read_csv(ROOT/'tables/authorship_AF_minus_reference.csv')
fig,axes=plt.subplots(2,2,figsize=(183/25.4,145/25.4),sharex=True,sharey=True)
fig.subplots_adjust(left=.205,right=.98,bottom=.12,top=.81,hspace=.47,wspace=.23)
y=np.arange(4)
for row,scope in enumerate(['original_68','all_classified']):
    for col,role in enumerate(['first','last']):
        ax=axes[row,col];x=d[d.scope.eq(scope)&d.role.eq(role)]
        for yy in y:ax.axhspan(yy-.39,yy+.39,color=BAND,zorder=0,lw=0)
        for bench,color,marker,offset,label in [('country',COLORS['H'],'o',-.085,'Country participation'),('author',COLORS['L'],'D',.085,'Team-author participation')]:
            v=x[x.benchmark.eq(bench)].set_index('income_group').reindex(INCOMES)
            ax.errorbar(v.delta_R,y+offset,xerr=[v.delta_R-v.ci_low,v.ci_high-v.delta_R],fmt=marker,color=color,ms=3.8,capsize=1.6,elinewidth=.75,capthick=.75,label=label,zorder=3)
        letter=string.ascii_lowercase[row*2+col]
        ax.text(-.12,1.12,letter,transform=ax.transAxes,fontsize=10,fontweight='bold',color='#111820')
        ax.set_title(f'{role.capitalize()} authorship',loc='left',pad=24,fontweight='normal')
        ax.text(0,1.025,'Original 68-country scope' if row==0 else 'Expanded classification scope',transform=ax.transAxes,fontsize=7,color=BLUE,va='bottom')
        ax.axvline(0,color='#c2cddb',ls='--',lw=.9,zorder=2);ax.set_axisbelow(True);ax.grid(axis='x',color=GRID,lw=.45)
        ax.set_yticks(y,['Low income','Lower-middle\nincome','Upper-middle\nincome','High income']);ax.set_xticks([-.4,-.2,0,.2,.4]);ax.set_xlim(-.59,.59);ax.set_ylim(3.43,-.43);ax.tick_params(axis='x',length=3);ax.tick_params(axis='y',length=0,pad=8)
fig.text(.56,.975,'Participation benchmark',fontsize=7.5,ha='center',color=BLUE)
fig.text(.59,.035,'AF − non-AF representation ratio (ΔR)',ha='center',fontsize=8)
handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='center',bbox_to_anchor=(.56,.937),ncol=2,frameon=False,fontsize=7.5,handlelength=1.8,columnspacing=2.5)
save(fig,'Supplementary_Fig_S31')

caption='''Supplementary Fig. S30 | Institutional AF coverage by national income group.
a–d, Cumulative coverage of at least one confirmed AF publication during 2020–2025 in low-, lower-middle-, upper-middle- and high-income countries and regions, respectively. Income groups follow the fixed World Bank FY2020 classification. Institutions retain their within-country groups based on 2015–2019 publication output. Rates are calculated within country and institutional group and then averaged equally across countries in each income group. The fixed population includes all 48,010 baseline institutions, including those without confirmed AF publications. Country counts are shown in panel labels. The low-income panel contains Ethiopia and Uganda only and should not be generalized to low-income countries as a whole. End labels give 2025 coverage. Lines show descriptive estimates, without confidence intervals. Pale background bands are visual guides and do not indicate uncertainty.

Supplementary Fig. S31 | Authorship representation by national income group.
a,b, AF-minus-reference differences in first- and last-author representation among the original 68 classified countries. c,d, Corresponding differences after assigning all 213 income-classified units in the original 227-unit geographic roster to their World Bank FY2020 groups. All panels retain the same 5,087 AF and 332,760 reference studies and the original publication-year, subfield and document-type standardization weights. Representation is the pooled authorship-credit share divided by the pooled participation-credit share, using either country participation (circles) or team-author participation (diamonds). Outside-scope credit remains in global denominators. Points and bars show estimates and pointwise conditional 95% intervals obtained by pooling country credits within each of the original 2,000 shared whole-study bootstrap replicates. The dashed line denotes no AF–reference difference. Intervals spanning zero do not establish equivalence; no adjustment for multiple comparisons was applied. The original-scope low-income group contains Ethiopia and Uganda and contributes 19 AF studies; the expanded-scope low-income group contributes 99 AF studies. The broader authorship scope does not expand the institutional coverage population in S30.
'''
(OUT/'Figure_legends_S30_S31.txt').write_text(caption)
print('Saved S30, S31, previews and figure legends to',OUT)
