"""Draw S30 in the visual style of the updated Figure 2, without a figure title.

This script reads verified source tables only. No estimates or intervals are changed.
"""
from pathlib import Path
import string,shutil,json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'Supplementary_S30_final'
OUT=ROOT/'S30_updated_Figure2_style'
OUT.mkdir(exist_ok=True)
(OUT/'source_data').mkdir(exist_ok=True)

for name in ['S30a_d_coverage.csv','S30e_income_benchmark_summary.csv']:
    target=OUT/'source_data'/name
    if not target.exists():shutil.copyfile(SOURCE/'source_data'/name,target)
cov=pd.read_csv(OUT/'source_data/S30a_d_coverage.csv')
summary=pd.read_csv(OUT/'source_data/S30e_income_benchmark_summary.csv')
LABEL={'L':'Low income','LM':'Lower-middle income','UM':'Upper-middle income','H':'High income'}
INCOMES=['L','LM','UM','H']
# Exact solid colours sampled from the updated Figure 2 supplied by the user.
COLOR={'L':'#5b96c9','M':'#2f8b75','H':'#173f82'}
INK='#11151c'; MUTED='#657183'; REF='#b2bdcd'; AXIS='#9caabf'; GRID='#e9eef4'; BORDER='#b8c6d9'
plt.rcParams.update({'font.family':'Arial','font.size':8,'text.color':INK,'axes.labelcolor':INK,'axes.titlecolor':INK,'axes.titlesize':8.3,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7,'xtick.color':MUTED,'ytick.color':MUTED,'axes.edgecolor':AXIS,'axes.linewidth':.65,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':True,'xtick.major.width':.6,'ytick.major.width':.6,'pdf.fonttype':42,'svg.fonttype':'none','figure.facecolor':'white','axes.facecolor':'white'})

fig=plt.figure(figsize=(183/25.4,202/25.4))
grid=fig.add_gridspec(3,2,left=.105,right=.975,bottom=.085,top=.89,height_ratios=[1,1,.85],hspace=.57,wspace=.27)
axes=[fig.add_subplot(grid[i//2,i%2]) for i in range(4)]
insets=[]
for i,(ax,inc) in enumerate(zip(axes,INCOMES)):
    block=cov[cov.income_group.eq(inc)]
    n=int(block.countries.iloc[0])
    ax.text(-.12,1.10,string.ascii_lowercase[i],transform=ax.transAxes,fontsize=10.5,fontweight='bold',color=INK)
    ax.set_title(f'{LABEL[inc]} (n = {n})',loc='left',pad=11,fontweight='normal')
    for group,marker,label in [('L','o','Lower'),('M','s','Middle'),('H','^','Higher')]:
        v=block[block.institution_group.eq(group)].sort_values('year')
        ax.plot(v.year,v.equal_country_coverage_pct,color=COLOR[group],marker=marker,ms=3.5,lw=1.25,label=label,zorder=3)
        end=float(v.equal_country_coverage_pct.iloc[-1])
        # Separate adjacent endpoints in the two-country panel without moving the data.
        offset=-1.6 if inc=='L' and group=='L' else 1.7 if inc=='L' and group=='M' else 0
        ax.annotate(f'{end:.2f}%',xy=(2025,end),xytext=(2025.17,end+offset),fontsize=7,color=COLOR[group],va='center',arrowprops={'arrowstyle':'-','lw':.45,'color':COLOR[group]} if offset else None)
    ax.set_xlim(2019.85,2026.3);ax.set_ylim(0,48)
    ax.set_xticks(range(2020,2026));ax.set_yticks([0,10,20,30,40])
    ax.grid(axis='y',color=GRID,lw=.6);ax.set_axisbelow(True)
    ax.tick_params(length=2.8,pad=4)
    if i%2:ax.tick_params(labelleft=False)
    if i>=2:ax.set_xlabel('Year',labelpad=6)
    # Identical 0–5% scales permit comparison across income groups.
    # The upper-left placement avoids the higher-output trajectories in all four panels.
    box=FancyBboxPatch((.065,.615),.405,.345,boxstyle='round,pad=0.008,rounding_size=0.014',transform=ax.transAxes,facecolor='white',edgecolor=BORDER,linewidth=.65,zorder=5)
    ax.add_patch(box)
    ax.text(.077,.935,'Lower (0–5%)',transform=ax.transAxes,fontsize=6.2,va='top',color=INK,zorder=7)
    ins=ax.inset_axes([.113,.67,.325,.195],zorder=6)
    lower=block[block.institution_group.eq('L')].sort_values('year')
    ins.plot(lower.year,lower.equal_country_coverage_pct,color=COLOR['L'],marker='o',ms=2.3,lw=.9)
    ins.set_xlim(2019.85,2025.2);ins.set_ylim(0,5)
    ins.set_xticks([2020,2022,2025]);ins.set_yticks([0,2,4])
    ins.tick_params(labelsize=5.3,length=1.8,pad=1)
    ins.grid(axis='y',color=GRID,lw=.45);ins.set_axisbelow(True)
    for spine in ins.spines.values():spine.set_linewidth(.5)
    insets.append(ins)

fig.text(.105,.978,'Institutional groups · within-country output, 2015–2019',fontsize=8,ha='left',color=INK)
handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='upper left',bbox_to_anchor=(.102,.960),ncol=3,frameon=False,fontsize=7.8,columnspacing=2.1,handlelength=2.0,handletextpad=.7,borderaxespad=0)
fig.text(.022,.66,'Cumulative coverage (%)',rotation=90,va='center',fontsize=8)

ax=fig.add_subplot(grid[2,:])
pos=ax.get_position();ax.set_position([.23,pos.y0,.745,pos.height])
ax.text(-.224,1.13,'e',transform=ax.transAxes,fontsize=10.5,fontweight='bold',color=INK)
for i,inc in enumerate(INCOMES):
    row=summary[summary.income_group.eq(inc)].iloc[0]
    lo=float(row.centered_reference_low_pp);hi=float(row.centered_reference_high_pp)
    ax.hlines(i+.085,lo,hi,color=REF,lw=1.65,zorder=3)
    ax.vlines([lo,hi],i+.025,i+.145,color=MUTED,lw=.7,zorder=3)
    ax.plot(float(row.observed_minus_expected_pp),i-.095,'o',color=INK,ms=4,zorder=4)
ax.axvline(0,color=MUTED,lw=.9,ls=(0,(3,2)),zorder=2)
ax.spines['left'].set_visible(False)
ax.set_yticks(range(4),[LABEL[g] for g in INCOMES]);ax.set_ylim(3.43,-.43)
ax.set_xlim(-6,8.1);ax.set_xticks([-6,-4,-2,0,2,4,6,8]);ax.grid(axis='x',color=GRID,lw=.6);ax.set_axisbelow(True)
ax.tick_params(axis='y',length=0,pad=9);ax.tick_params(axis='x',length=2.8,pad=4)
ax.set_xlabel('Annual gap change, 2021–2025: observed − expected (pp)',labelpad=7)
legend_handles=[Line2D([],[],color=INK,marker='o',lw=0,ms=4,label='Observed − expected'),Line2D([],[],color=REF,lw=1.65,label='95% conditional reference range')]
ax.legend(handles=legend_handles,loc='lower center',bbox_to_anchor=(.5,1.06),ncol=2,frameon=False,fontsize=7.4,columnspacing=2,handlelength=2)

for ext in ['pdf','svg']:fig.savefig(OUT/f'Supplementary_Fig_S30.{ext}',facecolor='white')
fig.savefig(OUT/'Supplementary_Fig_S30.png',dpi=600,facecolor='white')
fig.savefig(OUT/'Supplementary_Fig_S30_preview.png',dpi=220,facecolor='white')
plt.close(fig)

caption_path=SOURCE/'Figure_legend_S30.txt'
if not caption_path.exists():caption_path=OUT/'Figure_legend_S30.txt'
caption=caption_path.read_text() if caption_path.exists() else ''
caption=caption.replace('Insets enlarge lower-output institutional coverage on a common 0–5% scale. ','')
caption=caption.replace('Curves are descriptive, with no confidence intervals.','Insets enlarge lower-output institutional coverage on a common 0–5% scale. Curves are descriptive, with no confidence intervals.').replace('Dark-blue circles','Black circles').replace('Light-blue horizontal ranges','Grey-blue horizontal ranges').replace(' Pale bands are visual guides.','')
(OUT/'Figure_legend_S30.txt').write_text(caption)
for name in ['Results_for_Note2.txt','Numerical_results.txt']:
    if (SOURCE/name).exists():shutil.copyfile(SOURCE/name,OUT/name)
print('Updated Figure 2 style; five-panel S30 with four common-scale insets:',OUT)
