"""Draw S31 from unchanged estimates, matching the updated Figure 2 and S30."""
from pathlib import Path
import hashlib,json,shutil,string,zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'S31_updated_style'
OUT.mkdir(exist_ok=True)
(OUT/'source_data').mkdir(exist_ok=True)
source=ROOT/'tables/authorship_AF_minus_reference.csv'
target=OUT/'source_data/S31_authorship_AF_minus_reference.csv'
if source.exists():shutil.copyfile(source,target)
d=pd.read_csv(target)
d=d[d.income_group.isin(['L','LM','UM','H'])].copy()
assert len(d)==32 and not d.duplicated(['scope','role','benchmark','income_group']).any()
assert ((d.ci_low<=d.delta_R)&(d.delta_R<=d.ci_high)).all()
INK='#11151c';MUTED='#657183';AXIS='#9caabf';GRID='#e9eef4'
COLORS={'country':'#173f82','author':'#5b96c9'}
plt.rcParams.update({'font.family':'Arial','font.size':8,'text.color':INK,'axes.labelcolor':INK,'axes.titlecolor':INK,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7.5,'xtick.color':MUTED,'ytick.color':MUTED,'axes.edgecolor':AXIS,'axes.linewidth':.65,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,'xtick.major.width':.6,'pdf.fonttype':42,'svg.fonttype':'none','figure.facecolor':'white','axes.facecolor':'white'})
fig,axes=plt.subplots(2,2,figsize=(183/25.4,145/25.4),sharex=True,sharey=True)
fig.subplots_adjust(left=.205,right=.98,bottom=.115,top=.805,hspace=.47,wspace=.23)
incomes=['H','UM','LM','L'];y=np.arange(4)
labels=['High income','Upper-middle\nincome','Lower-middle\nincome','Low income']
for row,scope in enumerate(['original_68','all_classified']):
    for col,role in enumerate(['first','last']):
        ax=axes[row,col]
        block=d[d.scope.eq(scope)&d.role.eq(role)]
        for benchmark,marker,offset in [('country','o',-.09),('author','D',.09)]:
            v=block[block.benchmark.eq(benchmark)].set_index('income_group').reindex(incomes)
            ax.errorbar(v.delta_R,y+offset,xerr=[v.delta_R-v.ci_low,v.ci_high-v.delta_R],fmt=marker,color=COLORS[benchmark],markerfacecolor=COLORS[benchmark] if benchmark=='country' else 'white',markeredgewidth=.8,ms=3.9,capsize=2,elinewidth=.9,capthick=.8,zorder=3)
        ax.text(-.12,1.12,string.ascii_lowercase[row*2+col],transform=ax.transAxes,fontsize=10.5,fontweight='bold')
        ax.text(0,1.19,f'{role.capitalize()} authorship',transform=ax.transAxes,fontsize=8.8,va='bottom')
        scope_label='Original scope · 68 countries' if row==0 else 'Expanded scope · 213 countries and regions'
        ax.text(0,1.035,scope_label,transform=ax.transAxes,fontsize=7,color=MUTED,va='bottom')
        ax.axvline(0,color=MUTED,lw=.9,ls=(0,(3,2)),zorder=2)
        ax.grid(axis='x',color=GRID,lw=.6);ax.set_axisbelow(True)
        ax.set_yticks(y,labels);ax.set_ylim(3.43,-.43)
        ax.set_xlim(-.59,.59);ax.set_xticks([-.4,-.2,0,.2,.4])
        ax.tick_params(axis='y',length=0,pad=8)
        ax.tick_params(axis='x',length=2.8,pad=4)
fig.text(.205,.977,'Participation benchmark',fontsize=8,ha='left')
handles=[Line2D([],[],color=COLORS['country'],marker='o',lw=.9,ms=4,label='Country participation'),Line2D([],[],color=COLORS['author'],marker='D',markerfacecolor='white',markeredgewidth=.8,lw=.9,ms=4,label='Team authors')]
fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.201,.956),ncol=2,frameon=False,fontsize=7.7,columnspacing=1.8,handlelength=1.8,handletextpad=.7,borderaxespad=0)
fig.text(.59,.034,'AF − non-AF difference in R (ΔR)',ha='center',fontsize=8)
for ext in ['pdf','svg']:fig.savefig(OUT/f'Supplementary_Fig_S31.{ext}',facecolor='white')
fig.savefig(OUT/'Supplementary_Fig_S31.png',dpi=600,facecolor='white')
fig.savefig(OUT/'Supplementary_Fig_S31_preview.png',dpi=220,facecolor='white')
plt.close(fig)
caption='''Supplementary Fig. S31 | Authorship representation by national income group.
a,b, AF-minus-non-AF differences in first- and last-author representation within the original 68-country sample. c,d, Corresponding differences across 213 income-classified countries and regions. Income groups follow the World Bank FY2020 classification. Representation is the pooled authorship-credit share divided by the pooled participation-credit share, using country participation (filled circles) or team authors (open diamonds). All panels retain the same 5,087 AF and 332,760 non-AF studies and the original year, subfield and document-type standardization. Outside-scope credit remains in global denominators. Bars show pointwise 95% intervals from 2,000 shared whole-study bootstrap replicates; dashed lines mark zero difference. The original-scope low-income group includes only Ethiopia and Uganda.
'''
(OUT/'Figure_legend_S31.txt').write_text(caption)
verification={'source_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'source_unchanged':not source.exists() or target.read_bytes()==source.read_bytes(),'estimate_rows':len(d),'panels':4,'income_order_top_to_bottom':incomes,'estimates_and_intervals':'Unchanged','font':'Arial','dimensions_mm':[183,145]}
(OUT/'verification.json').write_text(json.dumps(verification,indent=2))
print(OUT)
