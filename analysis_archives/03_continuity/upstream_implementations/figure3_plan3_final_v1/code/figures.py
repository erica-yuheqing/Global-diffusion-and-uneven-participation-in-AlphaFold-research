"""Native vector/raster figures drawn only from saved plan-3 source tables."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Patch
from matplotlib.lines import Line2D
from PIL import Image,ImageCms
from support import *

BLUE='#4865BC';ORANGE='#C47C40';GRAY='#AAB1BB'
STATE_COLORS=['#4865BC','#98B8D8','#4C9A8B','#B6BBC4']
AUTHOR_COLORS=['#4865BC','#4C9A8B','#C4C9D1','#D9A136']
CAT=['Linked-only','Mixed','Unlinked-only','Unresolved']
SHORT=['Precomputed\nstructures','Prediction runs','Method / tool\ndevelopment','Evaluation /\nvalidation']

def decorate(ax):
    ax.spines[['top','right']].set_visible(False)
    ax.tick_params(labelsize=7,length=2.5,width=.6,pad=2)
    for s in ['left','bottom']:ax.spines[s].set_linewidth(.6)
    ax.set_axisbelow(True);ax.grid(axis='y',color='#E9ECF0',lw=.5)

def label(fig,text,x,y):fig.text(x,y,text,fontsize=11,weight='bold',va='top')

def save(fig,out,name,full=True):
    out.mkdir(parents=True,exist_ok=True)
    fig.canvas.draw();renderer=fig.canvas.get_renderer();canvas=fig.bbox
    off_view=set()
    for axis in fig.axes:
        for t in axis.get_xticklabels():
            if not min(axis.get_xlim())<=t.get_position()[0]<=max(axis.get_xlim()):off_view.add(id(t))
        for t in axis.get_yticklabels():
            if not min(axis.get_ylim())<=t.get_position()[1]<=max(axis.get_ylim()):off_view.add(id(t))
    clipped=[]
    for text in fig.findobj(matplotlib.text.Text):
        if not text.get_visible() or not text.get_text():continue
        if id(text) in off_view:continue
        ax=text.axes
        if ax is not None:
            if text in ax.get_xticklabels() and not min(ax.get_xlim())<=text.get_position()[0]<=max(ax.get_xlim()):continue
            if text in ax.get_yticklabels() and not min(ax.get_ylim())<=text.get_position()[1]<=max(ax.get_ylim()):continue
        box=text.get_window_extent(renderer)
        if box.x0<canvas.x0-2 or box.y0<canvas.y0-2 or box.x1>canvas.x1+2 or box.y1>canvas.y1+2:clipped.append(text.get_text())
    require(not clipped,'Figure text outside canvas: '+str(clipped))
    for fmt in ['pdf','svg']:fig.savefig(out/(name+'.'+fmt),facecolor='white')
    fig.savefig(out/(name+'.png'),dpi=600,facecolor='white')
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with Image.open(out/(name+'.png')) as im:
        rgb=im.convert('RGB');rgb.save(out/(name+'.png'),dpi=(600,600),icc_profile=profile)
        if full:rgb.save(out/(name+'.tiff'),dpi=(600,600),compression='tiff_lzw',icc_profile=profile)
        pixels=rgb.size
    fig.savefig(out/(name+'_preview.png'),dpi=220,facecolor='white')
    dump(out/(name+'.metadata.json'),dict(size_mm=[fig.get_figwidth()*25.4,fig.get_figheight()*25.4],
      pixels=pixels,dpi=600,RGB=True,icc='sRGB',vector_text=True,canvas_text_clipping=False,
      journal_acceptance_certified=False))
    plt.close(fig)

def panel_a(fig,bounds,a):
    ax=fig.add_axes(bounds);q=a.set_index('status');N=int(a.denominator.iloc[0])
    both=int(q.loc['both_intervals','N']);first=int(q.loc['first_only','N']);second=int(q.loc['second_only','N']);neither=int(q.loc['no_later_study','N'])
    left=(both+second)/N
    cells=[(0,second/(both+second),left,both/(both+second),'Both windows',both,0),
      (0,0,left,second/(both+second),'Second only',second,2),
      (left,neither/(first+neither),1-left,first/(first+neither),'First only',first,1),
      (left,0,1-left,neither/(first+neither),'Neither window',neither,3)]
    for x,y,w,h,text,n,color in cells:
        ax.add_patch(Rectangle((x,y),w,h,facecolor=STATE_COLORS[color],lw=0))
        ax.text(x+w/2,y+h/2,f'{text}\n{n:,} ({100*n/N:.1f}%)',ha='center',va='center',fontsize=7,
          color='white' if color in [0,2] else '#152334',weight='bold',linespacing=1.4)
    ax.set(xlim=(0,1),ylim=(0,1),xticks=[],yticks=[])
    for spine in ax.spines.values():spine.set_visible(False)
    ax.text(.5,1.055,'Second 12-month window',ha='center',va='bottom',transform=ax.transAxes,fontsize=7.5)
    ax.text(-.12,.5,'First 12-month window',rotation=90,ha='center',va='center',transform=ax.transAxes,fontsize=7.5)
    ax.text(0,1.16,f'N = {N:,} institutions',transform=ax.transAxes,fontsize=7.5)
    ax.text(0,-.11,f'≥1 later AF study: {both+first+second:,}/{N:,} ({100*(both+first+second)/N:.1f}%)',
      transform=ax.transAxes,fontsize=7.5,ha='left',va='top')
    return ax

def panel_b(fig,region,b):
    l,bottom,w,h=region
    upper=fig.add_axes([l,bottom+h*.40,w,h*.60]);lower=fig.add_axes([l,bottom,w,h*.25],sharex=upper)
    q=b.sort_values('quintile')
    upper.plot(q.quintile,100*q.observed,color=BLUE,marker='o',ms=4,lw=1.2,label='Observed')
    upper.plot(q.quintile,100*q.expected,color=ORANGE,ls='--',marker='o',mfc='white',mec=ORANGE,ms=4,lw=1.2,label='Opportunity benchmark')
    upper.set(ylim=(0,65),yticks=[0,20,40,60],xlim=(.8,5.2));upper.tick_params(labelbottom=False)
    upper.set_ylabel('Both-window participation (%)',fontsize=7.5)
    upper.legend(frameon=False,fontsize=7,loc='upper left',handlelength=2)
    lower.axhline(0,color='#777777',ls='--',lw=.65)
    lower.plot(q.quintile,q.difference_pp,color=BLUE,marker='o',ms=3,lw=1)
    lower.set(xticks=range(1,6),xticklabels=[f'Q{i}\nn={n}' for i,n in zip(q.quintile,q.N)],ylim=(-16,10),yticks=[-10,0,10])
    lower.set_ylabel('Observed −\nexpected (pp)',fontsize=7.1)
    lower.set_xlabel('Baseline paper quintile',fontsize=7.5)
    for ax in [upper,lower]:decorate(ax)
    return upper,lower

def panel_c(fig,bounds,c,compact=False):
    ax=fig.add_axes(bounds)
    c=c[c.variant.eq('main_linear_log_scale')]
    labels=SHORT if compact else LABELS
    for i,m in enumerate(MODES):
        q=c[c.type.eq(m)].set_index('comparison');lo=q.loc['assessed_absent'];hi=q.loc['present']
        ax.plot([100*lo.adjusted_probability,100*hi.adjusted_probability],[i,i],color='#ABB2BE',lw=1)
        ax.scatter(100*lo.adjusted_probability,i,s=24,facecolor='white',edgecolor=BLUE,zorder=3)
        ax.scatter(100*hi.adjusted_probability,i,s=24,color=BLUE,zorder=3)
        if hi.CI_status=='released_component_cluster_95CI':
            for r in [lo,hi]:ax.plot([100*r.CI_low,100*r.CI_high],[i,i],color=BLUE,lw=.7)
        ax.text(.99,i,f'{hi.difference_pp:+.1f} pp\nN={int(hi.N):,}',transform=ax.get_yaxis_transform(),ha='right',va='center',fontsize=6.6,color='#555C66')
    ax.set(yticks=range(4),yticklabels=labels,ylim=(3.6,-.6),xlim=(0,45),xticks=[0,10,20,30,40])
    ax.set_xlabel('Adjusted participation probability (%)',fontsize=7.5)
    decorate(ax);ax.grid(axis='y',visible=False);ax.grid(axis='x',color='#E9ECF0',lw=.5)
    handles=[Line2D([],[],color=BLUE,marker='o',ls='none',mfc='white',label='Assessed absent'),Line2D([],[],color=BLUE,marker='o',ls='none',label='Present')]
    ax.legend(handles=handles,frameon=False,fontsize=7,loc='upper left',bbox_to_anchor=(0,1.25),ncol=2,handletextpad=.2,columnspacing=1)
    return ax

def panel_d(fig,bounds,d):
    ax=fig.add_axes(bounds);groups=['All','1','2','3','4','5'];bottom=np.zeros(6)
    for j,cat in enumerate(CAT):
        q=d[d.variant.eq('primary')&d.category.eq(cat)].set_index('quintile').reindex(groups)
        ax.bar(np.arange(6),q.percentage,bottom=bottom,color=AUTHOR_COLORS[j],edgecolor='white',linewidth=.4,width=.72,label=cat)
        for k,value in enumerate(q.percentage):
            if value>=12:ax.text(k,bottom[k]+value/2,f'{value:.0f}%',ha='center',va='center',fontsize=6.5,color='white' if j in [0,1] else '#2D3440')
        bottom+=q.percentage.to_numpy()
    denominators=d[(d.variant.eq('primary'))].groupby('quintile').denominator.first().reindex(groups)
    for k,n in enumerate(denominators):ax.text(k,102,f'n={int(n):,}',ha='center',va='bottom',fontsize=6.4)
    ax.set(xticks=range(6),xticklabels=['All','Q1','Q2','Q3','Q4','Q5'],ylim=(0,113),yticks=[0,25,50,75,100],xlim=(-.6,5.6))
    ax.set_xlabel('Baseline paper quintile',fontsize=7.5);ax.set_ylabel('Repeat-publication institutions (%)',fontsize=7.3)
    decorate(ax)
    ax.legend(frameon=False,ncol=2,fontsize=6.5,loc='upper center',bbox_to_anchor=(.5,-.21),columnspacing=1,handletextpad=.4)
    return ax

def run(out):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7.5,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none'})
    a=load(out,'panel_a_participation');b=load(out,'panel_b_observed_expected');c=load(out,'panel_c_initial_use');d=load(out,'panel_d_group_shares')
    target=out/'figures';ed=target/'extended_data'
    fig=plt.figure(figsize=(183/25.4,108/25.4));label(fig,'a',.015,.985);label(fig,'b',.525,.985)
    panel_a(fig,(.085,.27,.36,.54),a);panel_b(fig,(.61,.20,.35,.68),b)
    save(fig,target,'figure3_core_a_b')
    fig=plt.figure(figsize=(183/25.4,200/25.4))
    for text,x,y in [('a',.015,.985),('b',.525,.985),('c',.015,.49),('d',.525,.49)]:label(fig,text,x,y)
    panel_a(fig,(.085,.61,.36,.29),a);panel_b(fig,(.61,.565,.35,.36),b)
    panel_c(fig,(.22,.15,.27,.25),c,True);panel_d(fig,(.61,.15,.35,.28),d)
    fig.text(.075,.46,'Exploratory ridge estimates; 95% CI withheld',fontsize=6.7,color='#8D5F2A')
    fig.text(.07,.035,'Reading layout: a–b core; c exploratory extension; d descriptive extension.',fontsize=7,color='#555C66')
    save(fig,target,'figure3_a_d_reading_not_full_inference')
    fig=plt.figure(figsize=(183/25.4,86/25.4));label(fig,'c',.015,.97)
    panel_c(fig,(.29,.2,.66,.58),c)
    fig.text(.29,.035,'Exploratory penalized estimates; no reliable dependence-aware 95% CI.',fontsize=7,color='#8D5F2A')
    save(fig,ed,'figure3c_initial_use_exploratory')
    fig=plt.figure(figsize=(183/25.4,100/25.4));label(fig,'d',.015,.97)
    panel_d(fig,(.11,.28,.84,.59),d);save(fig,ed,'figure3d_author_continuity')
    # Alternative reference definitions: show all, including direction changes.
    q=load(out,'benchmark_gradient_comparison')
    names={'main':'Entered-cohort reference','leave_institution_and_shared_papers_out':'Leave institution + shared studies out',
      'sparse_min50':'Sparse threshold 50','sparse_min200':'Sparse threshold 200','year_only':'Calendar year only',
      'subfield_two_year_bins':'Subfield × two-year bins','all_corpus_reference':'Whole-corpus reference',
      'unknown_lower':'Unknown-label lower bound','unknown_upper':'Unknown-label upper bound'}
    fig,ax=plt.subplots(figsize=(183/25.4,100/25.4));ax.axvline(0,color='#777777',ls='--',lw=.7)
    ax.scatter(q.residual_gradient_pp,np.arange(len(q)),color=BLUE,s=20)
    ax.set(yticks=range(len(q)),yticklabels=[names[x] for x in q.variant],ylim=(len(q)-.3,-.7),xlim=(-20,5))
    ax.set_xlabel('Residual high−low gradient (percentage points)',fontsize=8);decorate(ax);ax.grid(axis='y',visible=False)
    fig.subplots_adjust(left=.43,right=.97,top=.95,bottom=.17);save(fig,ed,'ED01_opportunity_reference_sensitivity',False)
    raw=load(out,'supplement_raw_scale_gradients');fig,axes=plt.subplots(1,3,figsize=(183/25.4,75/25.4),sharey=True)
    for ax,measure,title in zip(axes,['baseline_papers','known_linked_author_ids','observed_partner_ids'],['Papers','Active authors','General partners']):
        x=raw[raw.measure.eq(measure)].sort_values('quintile');ax.plot(x.quintile,100*x.rate,marker='o',ms=3,color=BLUE)
        ax.set(xticks=range(1,6),xticklabels=['Q1','Q2','Q3','Q4','Q5'],ylim=(0,55),xlabel='Measure-specific quintile')
        ax.text(.5,1.035,title,ha='center',transform=ax.transAxes,fontsize=8);decorate(ax)
    axes[0].set_ylabel('Both-window participation (%)',fontsize=8)
    fig.subplots_adjust(left=.1,right=.97,bottom=.24,top=.87,wspace=.23);save(fig,ed,'ED02_raw_scale_gradients',False)
    assess=load(out,'initial_activity_assessability');fig,ax=plt.subplots(figsize=(183/25.4,80/25.4));left=np.zeros(4)
    for state,color in [('present',BLUE),('assessed_absent','#B6C6DF'),('unassessable','#D9A136')]:
        x=assess[assess.initial_state.eq(state)].set_index('activity').reindex(MODES)
        ax.barh(range(4),x.percentage,left=left,color=color,edgecolor='white',height=.62,label=state.replace('_',' ').title())
        for i,v in enumerate(x.percentage):
            if v>=8:ax.text(left[i]+v/2,i,f'{v:.1f}%',ha='center',va='center',fontsize=7,color='white' if state=='present' else '#2D3440')
        left+=x.percentage.to_numpy()
    ax.set(yticks=range(4),yticklabels=LABELS,ylim=(3.6,-.6),xlim=(0,100),xlabel='Complete-follow-up institutions (%)')
    decorate(ax);ax.grid(axis='y',visible=False);ax.legend(loc='upper center',bbox_to_anchor=(.5,-.22),ncol=3,frameon=False,fontsize=7)
    fig.subplots_adjust(left=.32,right=.97,top=.95,bottom=.28);save(fig,ed,'ED03_initial_activity_assessability',False)
    fixed=load(out,'author_fixed_count_sensitivity');common=fixed[fixed.scope.eq('common_at_least5')&fixed.quintile.eq('All')&fixed.category.eq('Mixed')]
    strict=d[d.quintile.eq('All')];fig,axes=plt.subplots(1,2,figsize=(183/25.4,85/25.4))
    ax=axes[0];ax.plot(common.later_papers_sampled,common.exact_expected_percentage,marker='o',color=BLUE,lw=1.1)
    ax.set(xticks=[2,3,5],xlabel='Later studies sampled per institution',ylabel='Expected mixed institutions (%)',ylim=(0,65))
    ax.text(.03,.96,f'Same {int(common.N_eligible.iloc[0])} institutions\nwith ≥5 later studies',transform=ax.transAxes,va='top',fontsize=7);decorate(ax)
    ax=axes[1];xx=np.arange(4)
    for j,(variant,title,color) in enumerate([('primary','Positive overlap sufficient',BLUE),('require_complete_for_positive_overlap','Complete metadata required','#A3B4D3')]):
        vals=strict[strict.variant.eq(variant)].set_index('category').reindex(CAT).percentage
        ax.bar(xx+(j-.5)*.33,vals,width=.33,color=color,label=title)
    ax.set(xticks=xx,xticklabels=['Linked-\nonly','Mixed','Unlinked-\nonly','Unresolved'],ylim=(0,65),ylabel='Repeat institutions (%)');decorate(ax)
    ax.legend(frameon=False,fontsize=6.3,loc='upper left')
    fig.subplots_adjust(left=.1,right=.98,top=.96,bottom=.22,wspace=.32);save(fig,ed,'ED04_author_opportunity_and_completeness',False)
    # Exact month/day-policy comparisons are transparent even where membership changes.
    win=load(out,'window_policy_sensitivity');fig,ax=plt.subplots(figsize=(183/25.4,65/25.4));bottom=np.zeros(2)
    policies=['day_primary','all_month_precision_sensitivity'];states=['both_intervals','first_only','second_only','no_later_study']
    for j,state in enumerate(states):
        vals=win[win.state.eq(state)].set_index('policy').reindex(policies).percent
        ax.bar(range(2),vals,bottom=bottom,color=STATE_COLORS[j],edgecolor='white',width=.55,label=state.replace('_',' '))
        for k,v in enumerate(vals):ax.text(k,bottom[k]+v/2,f'{v:.1f}%',ha='center',va='center',fontsize=7,color='white' if j in [0,2] else '#2D3440')
        bottom+=vals.to_numpy()
    ns=win.groupby('policy').denominator.first()
    ax.set(xticks=[0,1],xticklabels=[f'Observed day dates\nN={int(ns[policies[0]]):,}',f'All-month sensitivity\nN={int(ns[policies[1]]):,}'],ylim=(0,100),ylabel='Institutions (%)');decorate(ax)
    ax.legend(frameon=False,ncol=2,fontsize=6.8,loc='center left',bbox_to_anchor=(1.02,.5))
    fig.subplots_adjust(left=.1,right=.65,bottom=.24,top=.95);save(fig,ed,'ED05_window_precision_sensitivity',False)
    print('Figures: core a–b, separate c/d and clearly marked a–d reading layout; five Extended Data displays',flush=True)

if __name__=='__main__':run(OUT)
