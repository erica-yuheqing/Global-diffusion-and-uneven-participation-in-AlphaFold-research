"""Publication-size vector figures from saved numeric tables; no empirical simulation."""
from common import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch,PathPatch
from matplotlib.path import Path as MPath
from matplotlib.lines import Line2D
from PIL import Image
BLUE='#4865BC';RED='#D66B72';GC=['#234D80','#669BB6','#ACCFD6','#B8BDC5'];SC=['#234D80','#6FA8B8','#BDC0C4','#D49565'];GL=['Higher','Middle','Lower','Outside']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':8,'legend.fontsize':7,'axes.linewidth':.6,'lines.linewidth':1,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})
REG=[]
def table(n):return pd.read_parquet(ROOT/'tables'/(n+'.parquet'))
def axis(a):a.spines[['top','right']].set_visible(False);a.tick_params(width=.6,length=3);return a
def letter(a,s):a.text(-.12,1.06,s,transform=a.transAxes,fontweight='bold',fontsize=10,va='top')
def export(fig,name,main=False):
    f=ROOT/'figures';fig.savefig(f/(name+'.pdf'));fig.savefig(f/(name+'.svg'));fig.savefig(f/(name+'_preview.png'),dpi=180)
    if main:
        fig.savefig(f/(name+'_600dpi.png'),dpi=600)
        with Image.open(f/(name+'_600dpi.png')) as im:rgb=im.convert('RGB')
        rgb.save(f/(name+'_600dpi.png'),dpi=(600,600));rgb.save(f/(name+'_600dpi.tiff'),compression='tiff_lzw',dpi=(600,600))
    REG.append(dict(figure_id=name,main=main,pages=1,pdf='figures/'+name+'.pdf',preview='figures/'+name+'_preview.png',panel_titles=False))
    plt.close(fig)
def multipage(figs,name):
    with PdfPages(ROOT/'figures'/(name+'.pdf')) as pdf:
      for i,fig in enumerate(figs,1):
        pdf.savefig(fig);fig.savefig(ROOT/'figures'/f'{name}_p{i:02d}_preview.png',dpi=120);fig.savefig(ROOT/'figures'/f'{name}_p{i:02d}.svg');plt.close(fig)
    REG.append(dict(figure_id=name,main=False,pages=len(figs),pdf='figures/'+name+'.pdf',preview='figures/'+name+'_p01_preview.png',panel_titles=False))
def error(a,x,y,lo,hi,color=BLUE,filled=True,marker='o',label=None):
    x,y,lo,hi=[np.asarray(z,float) for z in [x,y,lo,hi]];good=np.isfinite(x);ci=good&np.isfinite(lo)&np.isfinite(hi)
    a.hlines(y[ci],lo[ci],hi[ci],color=color,lw=.9);a.plot(x[good],y[good],ls='',marker=marker,ms=4,mec=color,mfc=color if filled else 'white',label=label)
def leg():return [Line2D([],[],color=BLUE,marker='o',ls='',label='AF'),Line2D([],[],color=RED,marker='o',mfc='white',ls='',label='Reference')]
def main4():
    z=table('strict_main_R');z=z[z.setting.eq('standardized')&z.entity_id.isin(['group:'+g for g in GROUPS[:3]])]
    fig,aa=plt.subplots(2,2,figsize=(183/25.4,122/25.4),sharex=True,sharey=True);fig.subplots_adjust(left=.23,right=.98,top=.88,bottom=.2,wspace=.16,hspace=.4)
    v=z[['ci_low','ci_high','R']].to_numpy();xmin=min(.5,np.nanmin(v)-.05);xmax=max(1.15,np.nanmax(v)+.05)
    for b,bench in enumerate(['country','author']):
      for j,role in enumerate(['first','last']):
        a=axis(aa[b,j]);letter(a,'abcd'[b*2+j]);a.axvline(1,color='#888',ls='--',lw=.7)
        for cp,col,dy in [('AF',BLUE,.08),('reference',RED,-.08)]:
          t=z[z.benchmark.eq(bench)&z.role.eq(role)&z.corpus.eq(cp)].set_index('entity_id').loc[['group:'+g for g in GROUPS[:3]]];error(a,t.R,np.arange(3)+dy,t.ci_low,t.ci_high,col,cp=='AF')
        a.set_yticks(range(3),GL[:3]);a.set_ylim(2.5,-.5);a.set_xlim(xmin,xmax)
        if b==1:a.set_xlabel('Authorship representation ratio, R')
        if b==0:a.text(.5,1.19,role.capitalize()+' author',transform=a.transAxes,ha='center')
      aa[b,0].text(-.55,.5,'Country participation' if b==0 else 'Author participation',transform=aa[b,0].transAxes,rotation=90,ha='center',va='center',fontsize=8)
    fig.legend(handles=leg(),loc='lower center',bbox_to_anchor=(.58,.065),ncol=2,frameon=False)
    fig.text(.23,.975,'Same strict sample: AF n = 5,087; reference n = 332,760; 173 supported cells',fontsize=7,va='top')
    export(fig,'Figure4',True);z.to_csv(ROOT/'source_data/Figure4_source_display.csv',index=False);table('strict_main_R').to_csv(ROOT/'source_data/Figure4_source_all.csv',index=False)
def alluvial(a,M):
    margins=[M.sum(axis=1),M.sum(axis=0)];gap=.045;scale=1-3*gap;bottoms=[]
    for side in range(2):
      top=1;bb=[]
      for k,v in enumerate(margins[side]):
        h=v*scale;b=top-h;bb.append(b);a.add_patch(plt.Rectangle((side*.87,b),.045,h,facecolor=GC[k],edgecolor='white',lw=.25));a.text(-.025 if side==0 else .94,b+h/2,GL[k],ha='right' if side==0 else 'left',va='center',fontsize=6.7);top=b-gap
      bottoms.append(np.array(bb))
    usedL=np.zeros(4);usedR=np.zeros(4)
    for i in range(4):
      for j in range(4):
        h=M[i,j]*scale;y0=bottoms[0][i]+usedL[i];y1=bottoms[1][j]+usedR[j];usedL[i]+=h;usedR[j]+=h
        verts=[(.045,y0),(.34,y0),(.57,y1),(.87,y1),(.87,y1+h),(.57,y1+h),(.34,y0+h),(.045,y0+h),(.045,y0)]
        codes=[MPath.MOVETO]+[MPath.CURVE4]*3+[MPath.LINETO]+[MPath.CURVE4]*3+[MPath.CLOSEPOLY]
        a.add_patch(PathPatch(MPath(verts,codes),facecolor=GC[i],edgecolor='none',alpha=.55))
    a.set(xlim=(-.21,1.13),ylim=(-.1,1.12));a.text(.02,1.04,'First author',ha='left',fontsize=7);a.text(.91,1.04,'Last author',ha='right',fontsize=7);a.axis('off')
def main5():
    pair=table('strict_main_pairings');pair=pair[pair.setting.eq('standardized')];s=table('strict_main_structure');s=s[s.setting.eq('standardized')&s.corpus.isin(CORPORA)]
    fig=plt.figure(figsize=(183/25.4,235/25.4))
    a=axis(fig.add_axes([.14,.855,.79,.11]));letter(a,'a');cats=json.loads((ROOT/'inputs/normalized/feature_metadata.json').read_text())['structure_categories']
    for k,cp in enumerate(CORPORA):
      t=s[s.corpus.eq(cp)].set_index('category').loc[cats];l=0
      for j,v in enumerate(t.share):
        a.barh(k,v*100,left=l,height=.45,color=SC[j],edgecolor='white',lw=.35)
        if v>.045:a.text(l+v*50,k,f'{v*100:.1f}%',ha='center',va='center',color='white' if j==0 else '#222',fontsize=7)
        l+=v*100
    a.set_yticks([0,1],['AF','Reference']);a.invert_yaxis();a.set_xlim(0,100);a.set_xlabel('Fractional first–last pairing credit (%)')
    fig.legend(handles=[Patch(color=SC[i],label=n) for i,n in enumerate(['Same country, same institution','Same country, different institutions','Same country, institution unresolved','Different countries'])],loc='center',bbox_to_anchor=(.55,.77),ncol=2,frameon=False,fontsize=6.5)
    fig.text(.14,.803,'Institution unresolved: AF 0.10%; reference 0.07% (gray segments retained)',fontsize=6.5)
    maxabs=pair[pair.corpus.isin(CORPORA)].observed_minus_expected_pp.abs().max();im=None
    for j,cp in enumerate(CORPORA):
      a=fig.add_axes([.075+j*.48,.455,.375,.255]);t=pair[pair.corpus.eq(cp)].set_index(['first_group','last_group']).reindex(pd.MultiIndex.from_product([GROUPS,GROUPS]));M=t.observed_share.to_numpy().reshape(4,4);alluvial(a,M)
      if j==0:letter(a,'b')
      a.text(.5,1.12,'AF' if cp=='AF' else 'Reference',transform=a.transAxes,ha='center',fontsize=8)
      a=fig.add_axes([.135+j*.48,.155,.29,.25]);v=t.observed_minus_expected_pp.to_numpy().reshape(4,4);im=a.imshow(v,cmap='RdBu_r',vmin=-maxabs,vmax=maxabs,aspect='equal')
      for x in range(4):
        for y in range(4):a.text(y,x,f'{v[x,y]:+.2f}',ha='center',va='center',fontsize=7,color='white' if abs(v[x,y])>.65*maxabs else '#222')
      a.set_xticks(range(4),GL,rotation=35,ha='right');a.set_yticks(range(4),GL);a.set_xlabel('Last-author country group');a.set_ylabel('First-author country group');a.text(.5,1.06,'AF' if cp=='AF' else 'Reference',transform=a.transAxes,ha='center',fontsize=8)
      if j==0:letter(a,'c')
    cb=fig.colorbar(im,cax=fig.add_axes([.29,.075,.44,.01]),orientation='horizontal');cb.set_label('Observed − team-composition expectation (percentage points)',fontsize=7)
    fig.text(.12,.016,'AF n = 5,087; reference n = 332,760; common-support reference ESS = 193,059.7\nAll three panels use identical study IDs and weights; outside-group credit is retained.',fontsize=6.6)
    export(fig,'Figure5',True)
def ed1():
    t=table('strict_annual_flow');team=read('team_size.csv');gr=table('strict_group_annual_retention');fig,aa=plt.subplots(2,2,figsize=(7.2,6.5));fig.subplots_adjust(hspace=.5,wspace=.45,bottom=.1,left=.11,right=.97,top=.95)
    for cp,col in [('AF',BLUE),('reference',RED)]:
      z=t[t.corpus.eq(cp)].sort_values('year');aa[0,0].plot(z.year,z.international_pct,'o-',color=col,label=cp.capitalize() if cp=='reference' else cp)
      for scope,ls in [('country_known','-'),('international','--')]:
        x=team[team.corpus.eq('non-AF' if cp=='reference' else cp)&team.scope.eq(scope)].sort_values('year');aa[0,1].plot(x.year,x['median'],ls,color=col,label=cp+' '+scope);aa[0,1].fill_between(x.year,x.q25,x.q75,color=col,alpha=.09)
      totals=[z.total.sum(),z.international_reconstructed.sum(),z.common_roles_strict.sum(),z.strict_complete.sum()];aa[1,0].plot(range(4),totals,'o-',color=col,label=cp)
    aa[0,0].text(.03,.05,'2020 AF: 9 country-known studies',transform=aa[0,0].transAxes,fontsize=6.5);aa[0,0].set_ylabel('International studies (%)');aa[0,0].legend(frameon=False)
    aa[0,1].set_ylabel('Observed authors: median and IQR');aa[0,1].legend(frameon=False,fontsize=5.8)
    aa[1,0].set_yscale('log');aa[1,0].set_ylabel('Studies (nested; logarithmic scale)');aa[1,0].set_xticks(range(4),['All','International','Roles','Strict complete'],rotation=25,ha='right')
    for g,col in zip(GROUPS,GC):
      z=gr[gr.corpus.eq('AF')&gr.national_group.eq(g)].sort_values('year');aa[1,1].plot(z.year,100*z.strict_complete_retention,'o-',color=col,label=g)
    aa[1,1].set_ylabel('AF author-complete retention (%)');aa[1,1].legend(frameon=False,fontsize=6)
    for a,s in zip(aa.ravel(),'abcd'):axis(a);letter(a,s)
    export(fig,'F4_ED1')
def country_pages():
    base=norm('country_groups.parquet').set_index('country_code');codes=read('country_registry.csv').country_code.tolist();codes=sorted(codes,key=lambda x:(-float(base.loc[x,'baseline_country_studies']) if x in base.index else 0,x))
    delta=table('strict_main_delta').query("setting == 'standardized' and level == 'country'");ch=table('strict_main_benchmark_change').query("setting == 'standardized' and level == 'country'");r=table('strict_main_R').query("setting == 'standardized' and level == 'country' and benchmark == 'author' and role == 'first'");figs=[]
    for start in range(0,len(codes),24):
      sel=codes[start:start+24];fig,aa=plt.subplots(1,4,figsize=(10,8),sharey=True);fig.subplots_adjust(left=.09,right=.98,top=.90,bottom=.1,wspace=.35);y=np.arange(len(sel))
      for k,bench in enumerate(['country','author']):
        for role,col,dy in [('first',BLUE,-.12),('last',RED,.12)]:
          z=delta[delta.benchmark.eq(bench)&delta.role.eq(role)].set_index('entity_id').reindex(sel);error(aa[k],z.delta,y+dy,z.ci_low,z.ci_high,col,True,'o' if role=='first' else '^')
        aa[k].axvline(0,color='#888',ls='--',lw=.6);aa[k].set_xlabel(bench.capitalize()+' benchmark ΔR')
      for role,col,dy in [('first',BLUE,-.12),('last',RED,.12)]:
        z=ch[ch.role.eq(role)].set_index('entity_id').reindex(sel);error(aa[2],z.C,y+dy,z.ci_low,z.ci_high,col,True,'o' if role=='first' else '^')
      aa[2].axvline(0,color='#888',ls='--',lw=.6);aa[2].set_xlabel('Paired benchmark change C')
      for cp,col,dy in [('AF',BLUE,-.12),('reference',RED,.12)]:
        z=r[r.corpus.eq(cp)].set_index('entity_id').reindex(sel);aa[3].plot(z.ESS,y+dy,'o',ms=3,color=col)
      aa[3].set_xscale('symlog',linthresh=1);aa[3].set_xlabel('Participation ESS')
      for a,s in zip(aa,'abcd'):axis(a);letter(a,s);a.set_yticks(y,sel);a.set_ylim(len(sel)-.5,-.5)
      fig.text(.09,.985,f'Registry countries {start+1}–{start+len(sel)} of {len(codes)}; blank = undefined, never zero-filled.',fontsize=8,va='top');fig.text(.09,.025,'a–c: circles First, triangles Last. d: blue AF, red Reference. Conditional whole-study ranges.',fontsize=7);figs.append(fig)
    multipage(figs,'F4_ED2')
def institution_summary():
    x=table('strict_institution_distribution');p=table('strict_institution_paired_summary');z=table('institution_zero_reference');fig,aa=plt.subplots(2,2,figsize=(7.2,6.5));fig.subplots_adjust(left=.12,right=.96,bottom=.15,top=.95,wspace=.45,hspace=.55);labels=[];ys=[];k=0
    for ct in ['US','CN','GB']:
      for group in ['high','middle','low']:
        labels.append(ct+' '+group[0].upper());ys.append(k)
        for cp,col,dy in [('AF',BLUE,-.1),('reference',RED,.1)]:
          t=x[x.country_code.eq(ct)&x.institution_group.eq(group)&x.corpus.eq(cp)&x.role.eq('first')&x.minimum_studies.eq(1)]
          if len(t):error(aa[0,0],t['median'],[k+dy],t.q25,t.q75,col,cp=='AF')
        t=p[p.country_code.eq(ct)&p.institution_group.eq(group)&p.role.eq('first')&p.minimum_studies.eq(1)]
        if len(t):error(aa[0,1],t['median'],[k],t.q25,t.q75)
        k+=1
    for a in aa[0]:a.set_yticks(ys,labels);a.invert_yaxis()
    aa[0,0].axvline(1,color='#999',ls='--',lw=.6);aa[0,0].set_xlabel('Domestic institution R: median / IQR');aa[0,1].axvline(0,color='#999',ls='--',lw=.6);aa[0,1].set_xlabel('Same-institution ΔR: median / IQR')
    entities=table('institution_zero_entities');bins=['1','2–4','5–9','10+'];draw=np.load(ROOT/'draws/conditional_reference.npz')['zero_counts'];views=pd.read_csv(ROOT/'tables/institution_zero_view_registry.csv',keep_default_na=False)
    for cp,col,dy in [('AF',BLUE,-.1),('reference',RED,.1)]:
      e=entities[entities.corpus.eq(cp)&entities.first_R_defined];rr=[]
      for bi in bins:
        t=e[e.paper_bin.eq(bi)];rr.append(100*t.first_hit.eq(0).mean());aa[1,0].text(bins.index(bi)+dy,100*t.first_hit.eq(0).mean()+3,f'n={len(t):,}',fontsize=5.4,color=col,rotation=40)
      aa[1,0].plot(range(4),rr,'o-',color=col,label=cp)
      v=views[views.corpus.eq(cp)].view_index.to_numpy();s=draw[:,v,0].sum(axis=1);lo,hi=np.quantile(s,[.025,.975]);n=len(e);actual=100*e.first_hit.eq(0).mean();expected=100*e.analytic_P0.mean();a=aa[1,1];xx=CORPORA.index(cp);a.plot(xx,actual,'o',color=col);a.vlines(xx+.17,100*lo/n,100*hi/n,color=col);a.plot(xx+.17,expected,'s',mfc='white',mec=col)
    aa[1,0].set_xticks(range(4),bins);aa[1,0].set_ylabel('Zero First credit (%)');aa[1,0].set_xlabel('Observed participating study count');aa[1,1].set_xticks([0,1],['AF','Reference']);aa[1,1].set_ylabel('Zero First credit (%)');fig.text(.56,.065,'● observed; □ conditional mean / reference range',fontsize=6)
    for a,s in zip(aa.ravel(),'abcd'):axis(a);letter(a,s)
    fig.text(.12,.017,'a–b: prespecified US/CN/GB examples; First positions shown. All roles/countries in S1/T4.\nIQR is not a confidence interval; the institutional opportunity cohort has additional ID restrictions.',fontsize=6.5)
    export(fig,'F4_ED3')
def structure_ed():
    fig,aa=plt.subplots(2,2,figsize=(7.2,6.4));fig.subplots_adjust(hspace=.6,wspace=.4,bottom=.15,left=.12,right=.94,top=.95)
    for k,name in enumerate(['strict_main','unique_role_country_institution']):
      z=table(name+'_structure').query("setting == 'standardized'")
      for y,cp in enumerate(CORPORA):
        t=z[z.corpus.eq(cp)];left=0
        for j,v in enumerate(t.share):aa[0,k].barh(y,100*v,left=left,color=SC[j],edgecolor='white',lw=.3);left+=100*v
      aa[0,k].set_yticks([0,1],['AF','Reference']);aa[0,k].invert_yaxis();aa[0,k].set(xlim=(0,100),xlabel='Fractional pairing credit (%)');aa[0,k].text(0,1.07,'Main' if k==0 else 'Unique country + institution',transform=aa[0,k].transAxes,fontsize=7)
    rr=table('strict_main_R').query("setting == 'standardized' and level == 'group' and benchmark == 'country'")
    for cp,col,dy in [('AF',BLUE,-.15),('reference',RED,.15)]:
      z=rr[rr.corpus.eq(cp)&rr.role.eq('first')].set_index('entity_id').loc[['group:'+g for g in GROUPS]];aa[1,0].bar(np.arange(4)+dy,100*div(z.role_credit,z.role_total),width=.28,color=col,label=cp)
    aa[1,0].set_xticks(range(4),GL,rotation=30);aa[1,0].set_ylabel('First-country credit (%)');aa[1,0].legend(frameon=False)
    aa[1,0].text(.02,1.07,'Unique subset raw coverage: AF 45.9%; reference 46.4%',transform=aa[1,0].transAxes,fontsize=6)
    z=table('domestic_institution_group_pairings');z=z[z.corpus.eq('AF')&z.country_code.isin(['US','CN','GB'])];M=z.pivot_table(index='first_institution_group',columns='last_institution_group',values='standardized_credit',aggfunc='sum',fill_value=0).reindex(index=['high','middle','low','unclassified'],columns=['high','middle','low','unclassified'],fill_value=0).to_numpy();M=100*M/M.sum();im=aa[1,1].imshow(M,cmap='Blues');aa[1,1].set_xticks(range(4),['H','M','L','Other']);aa[1,1].set_yticks(range(4),['H','M','L','Other']);aa[1,1].set_xlabel('Last domestic institution group');aa[1,1].set_ylabel('First domestic institution group');fig.colorbar(im,ax=aa[1,1],label='Conditional on known same-country pairs (%)',shrink=.75)
    for i in range(4):
      for j in range(4):aa[1,1].text(j,i,f'{M[i,j]:.1f}',ha='center',va='center',fontsize=6,color='white' if M[i,j]>.6*M.max() else 'black')
    for a,s in zip(aa.ravel(),'abcd'):axis(a);letter(a,s)
    fig.text(.12,.025,'b uses its own symmetric support; coverage is tabulated in T7. d is conditional on known within-country\nUS/CN/GB pairs; domestic H/M/L does not measure absolute cross-national institutional scale.',fontsize=6.5);export(fig,'F4_ED4')
def supplements():
    # S1 all registry-country domestic distributions, all roles and thresholds.
    v=table('strict_domestic_institution_R');p=table('strict_domestic_institution_paired');base=norm('country_groups.parquet').sort_values('baseline_country_studies',ascending=False);codes=base.country_code.tolist();codes+=sorted(set(read('country_registry.csv').country_code)-set(codes));figs=[]
    for start in range(0,len(codes),6):
      sel=codes[start:start+6];fig,aa=plt.subplots(len(sel),4,figsize=(11,2*len(sel)+.7),squeeze=False);fig.subplots_adjust(left=.09,right=.98,top=.91,bottom=.065,hspace=1.0,wspace=.7)
      for row,ct in enumerate(sel):
        ax=aa[row];t=v[v.country_code.eq(ct)&v.defined_flag];pp=p[p.country_code.eq(ct)&p.common_defined]
        for ci,(cp,col,dy) in enumerate([('AF',BLUE,-.1),('reference',RED,.1)]):
          for ri,role in enumerate(['first','last']):
            z=t[t.corpus.eq(cp)&t.role.eq(role)];error(ax[0],[z.R_inst.median()],[ri+dy],[z.R_inst.quantile(.25)],[z.R_inst.quantile(.75)],col,cp=='AF')
            med=[z.loc[z.n_papers.ge(n),'R_inst'].median() for n in [1,2,5,10]];ax[3].plot(range(4),med,'o-' if ri==0 else '^--',color=col,ms=2)
            bins=pd.cut(z.n_papers,[0,1,4,9,np.inf],labels=['1','2–4','5–9','10+']);zero=z.assign(bin=bins).groupby('bin',observed=False).role_credit.apply(lambda q:100*q.eq(0).mean());ax[2].plot(range(4),zero,'o-' if ri==0 else '^--',color=col,ms=2)
        for ri,role in enumerate(['first','last']):
          z=pp[pp.role.eq(role)].delta;error(ax[1],[z.median()],[ri],[z.quantile(.25)],[z.quantile(.75)],BLUE,True,'o' if ri==0 else '^')
        n_af=[len(t[t.corpus.eq('AF')&t.role.eq(r)]) for r in ['first','last']];n_ref=[len(t[t.corpus.eq('reference')&t.role.eq(r)]) for r in ['first','last']];ax[0].text(.02,1.04,f'AF n={n_af[0]:,}/{n_af[1]:,}\nRef n={n_ref[0]:,}/{n_ref[1]:,}',transform=ax[0].transAxes,fontsize=6,va='bottom')
        ax[0].set_yticks([0,1],['First','Last']);ax[1].set_yticks([0,1],['First','Last']);ax[0].axvline(1,color='#aaa',ls=':',lw=.6);ax[1].axvline(0,color='#aaa',ls=':',lw=.6)
        ax[0].set_xlabel('Domestic R: median / IQR');ax[1].set_xlabel('Paired ΔR: median / IQR');ax[2].set_xticks(range(4),['1','2–4','5–9','10+']);ax[2].set_ylabel('Zero credit (%)');ax[2].set_xlabel('Study-count bin');ax[3].set_xticks(range(4),['1','2','5','10']);ax[3].set_xlabel('Minimum study count');ax[3].set_ylabel('Median domestic R')
        ax[0].text(-.43,.6,ct,transform=ax[0].transAxes,fontweight='bold',fontsize=9)
        for a in ax:axis(a)
      fig.text(.09,.975,'All baseline countries; blue AF / red Reference; solid/circles First / dashed/triangles Last.',fontsize=8);fig.text(.09,.012,'Empty = undefined. Institutions have positive output unless explicitly listed as zero output in T4.\nIQR describes institutions, not estimate confidence. Both-corpus paired differences are computed institution by institution.',fontsize=7);figs.append(fig)
    multipage(figs,'F4_S1')
    # S2 all counting benchmarks/full-common-standardized including historical rules.
    z=table('strict_main_R');fig,aa=plt.subplots(2,2,figsize=(7.2,5.8));fig.subplots_adjust(hspace=.45,wspace=.4,left=.13,right=.97,bottom=.18,top=.95)
    for j,role in enumerate(['first','last']):
      for b,bench in enumerate(['country','author']):
        a=aa[b,j]
        for k,setting in enumerate(['raw_full','common_raw','standardized']):
          t=z[z.role.eq(role)&z.benchmark.eq(bench)&z.setting.eq(setting)&z.corpus.eq('AF')].set_index('entity_id').loc[['group:'+g for g in GROUPS]];a.plot(range(4),t.R,'o-',ms=3,label=setting,alpha=1-.15*k)
        a.set_xticks(range(4),GL,rotation=25);a.axhline(1,color='#aaa',ls='--',lw=.6);a.set_ylabel(bench+' '+role+' R');axis(a);letter(a,'abcd'[b*2+j])
    aa[0,0].legend(frameon=False,fontsize=6);fig.text(.13,.025,'Strict same-sample benchmarks above. Historical counting variants are on page 2 and in T5;\nthey retain different qualification/targets and are not same-sample adjustments.',fontsize=6.5);figs=[fig]
    fig,aa=plt.subplots(2,2,figsize=(7.2,6.4));fig.subplots_adjust(left=.14,right=.97,top=.93,bottom=.16,hspace=.45,wspace=.4)
    for i,(name,label) in enumerate([('main','Historical fractional countries'),('whole_country','Historical whole countries'),('full_role_affiliations','Historical complete role affiliations'),('author_fraction','Historical author participation')]):
      a=aa.ravel()[i];z=read(name+'_R.csv');z=z[z.setting.eq('standardized')&z.level.eq('group')];z['entity_id']=z.entity_id.replace({'group:high':'group:higher','group:low':'group:lower','group:outside_fixed_group':'group:outside'})
      for cp,col,dy in [('AF',BLUE,-.1),('non-AF',RED,.1)]:
       for role,mark,dd in [('first','o',-.04),('last','^',.04)]:
        t=z[z.corpus.eq(cp)&z.role.eq(role)].set_index('entity_id').reindex(['group:'+g for g in GROUPS]);error(a,pd.to_numeric(t.R,errors='coerce'),np.arange(4)+dy+dd,pd.to_numeric(t.ci_low,errors='coerce'),pd.to_numeric(t.ci_high,errors='coerce'),col,cp=='AF',mark)
      a.set_yticks(range(4),GL);a.invert_yaxis();a.axvline(1,color='#aaa',ls='--',lw=.6);a.set_xlabel('Historical R');a.text(.5,1.08,label,transform=a.transAxes,ha='center',fontsize=7);letter(a,'abcd'[i]);axis(a)
    fig.text(.14,.045,'Historical results retained unchanged: different populations/targets and original conditional ranges.\nBlue filled AF / red open Reference; circles First / triangles Last. See T5 sample/support records.',fontsize=6.5);figs.append(fig);multipage(figs,'F4_S2')
    # S3 new strict sensitivity estimates alongside historical role-specific sensitivity.
    names=['strict_main','strict_international','full_institution','unique_role_country_candidate_pool','support_ref_1','support_ref_10','support_ref_20'];fig,aa=plt.subplots(1,2,figsize=(7.2,5.2));fig.subplots_adjust(left=.35,right=.98,wspace=.28,bottom=.15,top=.93)
    for j,role in enumerate(['first','last']):
      a=aa[j]
      for k,n in enumerate(names):
        z=table(n+'_delta');t=z[z.setting.eq('standardized')&z.benchmark.eq('author')&z.role.eq(role)&z.entity_id.eq('group:lower')];error(a,t.delta,[k],t.ci_low,t.ci_high)
      a.set_yticks(range(len(names)),[n.replace('_',' ') for n in names] if j==0 else ['']*len(names));a.invert_yaxis();a.axvline(0,color='#888',ls='--',lw=.6);a.set_xlabel('Lower-group '+role+' ΔR');axis(a);letter(a,'ab'[j])
    fig.text(.35,.03,'Conditional ranges; sample/target changes are explicit in T5. Unknown contribution metadata unavailable.',fontsize=6);figs=[fig]
    fig,aa=plt.subplots(1,2,figsize=(7.2,5.2));fig.subplots_adjust(left=.35,right=.97,top=.93,bottom=.17,wspace=.3)
    hist=['main','first_separate','last_separate','single_country_roles','strict_international','singleton_inclusive'];labels=[x.replace('_',' ') for x in hist]
    for j,role in enumerate(['first','last']):
      for i,n in enumerate(hist):
        z=read(n+'_delta.csv');z=z[z.setting.eq('standardized')&z.entity_id.eq('group:low')&z.role.eq(role)]
        if len(z):error(aa[j],pd.to_numeric(z.delta,errors='coerce'),[i],pd.to_numeric(z.ci_low,errors='coerce'),pd.to_numeric(z.ci_high,errors='coerce'))
      aa[j].set_yticks(range(len(hist)),labels if j==0 else ['']*len(hist));aa[j].invert_yaxis();aa[j].axvline(0,color='#aaa',ls='--',lw=.6);aa[j].set_xlabel('Historical lower-group '+role+' ΔR');axis(aa[j]);letter(aa[j],'ab'[j])
    fig.text(.35,.035,'Historical role-specific/qualification populations, not strict new common-cohort adjustments.\nA role-specific analysis has no estimate for the other role; blanks are intentional.',fontsize=6.5);figs.append(fig);multipage(figs,'F4_S3')
    # S4 direct disjoint-period changes, both benchmarks, no marginal-CI reasoning.
    z=table('period_direct_changes');fig,aa=plt.subplots(1,2,figsize=(7.2,4.8));fig.subplots_adjust(left=.2,right=.98,wspace=.35,bottom=.15,top=.95)
    for j,role in enumerate(['first','last']):
      for bench,col,dy in [('country',BLUE,-.1),('author',RED,.1)]:
        t=z[z.outcome.eq('R_difference_change')&z.role.eq(role)&z.benchmark.eq(bench)].set_index('group').loc[GROUPS];supported=t.display_supported.fillna(False);y=np.arange(4)+dy;error(aa[j],t.estimate.where(supported),y,t.ci_low.where(supported),t.ci_high.where(supported),col)
      aa[j].set_yticks(range(4),GL);aa[j].invert_yaxis();aa[j].axvline(0,color='#888',ls='--',lw=.6);aa[j].set_xlabel('AF3 − AF2 change in '+role+' ΔR');axis(aa[j]);letter(aa[j],'ab'[j])
    fig.text(.2,.03,'Blue: country benchmark; red: author benchmark. Unsupported groups are not displayed.\nBoth periods share the pooled AF field/type target; actual counts, ESS and gates are in T5.',fontsize=6.5);export(fig,'F4_S4')
    # S5 full group observation, expectation, deviation and direct contrast; all cells.
    z=table('strict_main_pairings');z=z[z.setting.eq('standardized')];fig,aa=plt.subplots(2,3,figsize=(9,6));fig.subplots_adjust(left=.1,right=.97,bottom=.15,top=.94,wspace=.45,hspace=.55)
    vmax_dev=z[z.corpus.isin(CORPORA)].observed_minus_expected_pp.abs().max()
    for i,cp in enumerate(CORPORA):
      t=z[z.corpus.eq(cp)].set_index(['first_group','last_group']).reindex(pd.MultiIndex.from_product([GROUPS,GROUPS]));
      for j,key in enumerate(['observed_share','expected_share','observed_minus_expected_pp']):
        v=t[key].to_numpy().reshape(4,4);v=v*100 if j<2 else v;im=aa[i,j].imshow(v,cmap='Blues' if j<2 else 'RdBu_r',vmin=0 if j<2 else -vmax_dev,vmax=100 if j<2 else vmax_dev);aa[i,j].set_xticks(range(4),['H','M','L','O']);aa[i,j].set_yticks(range(4),['H','M','L','O']);aa[i,j].set_xlabel(['Observed (%)','Exact expected (%)','O − E (pp)'][j]);aa[i,j].set_ylabel(cp+' First');letter(aa[i,j],'abcdef'[i*3+j]);fig.colorbar(im,ax=aa[i,j],shrink=.65)
        for ri in range(4):
          for cj in range(4):aa[i,j].text(cj,ri,f'{v[ri,cj]:.1f}' if j<2 else f'{v[ri,cj]:+.2f}',ha='center',va='center',fontsize=6,color='white' if (v[ri,cj]>65 if j<2 else abs(v[ri,cj])>.65*vmax_dev) else '#222')
    fig.text(.1,.03,'Complete country-pair grid: T6; exact expectations use two distinct observed team authors.\nConditional endpoint reference ranges are supplied separately from whole-study bootstrap intervals.',fontsize=7);export(fig,'F4_S5')
    # S6 independent estimands in separate panels.
    fig,aa=plt.subplots(1,2,figsize=(7.2,4.8));fig.subplots_adjust(left=.12,right=.97,bottom=.2,top=.95,wspace=.45);z=table('strict_main_benchmark_change').query("setting == 'standardized' and level == 'group'")
    for role,col,dy in [('first',BLUE,-.1),('last',RED,.1)]:
      t=z[z.role.eq(role)].set_index('entity_id').loc[['group:'+g for g in GROUPS]];error(aa[0],t.C,np.arange(4)+dy,t.ci_low,t.ci_high,col,True,'o' if role=='first' else '^')
    aa[0].set_yticks(range(4),GL);aa[0].invert_yaxis();aa[0].axvline(0,color='#888',ls='--',lw=.6);aa[0].set_xlabel('Paired benchmark change C')
    e=table('institution_zero_entities');
    for cp,col in [('AF',BLUE),('reference',RED)]:
      t=e[e.corpus.eq(cp)&e.first_R_defined];g=t.groupby('paper_bin',observed=True).agg(expected=('analytic_P0','mean'),observed=('first_hit',lambda x:x.eq(0).mean()));g=g.reindex(['1','2–4','5–9','10+']);aa[1].plot(range(4),100*g.observed,'o-',color=col,label=cp+' observed');aa[1].plot(range(4),100*g.expected,'s--',color=col,label=cp+' conditional mean')
    aa[1].set_xticks(range(4),['1','2–4','5–9','10+']);aa[1].set_xlabel('Participating study count');aa[1].set_ylabel('Zero First credit (%)');aa[1].legend(frameon=False,fontsize=5.7)
    for a,s in zip(aa,'ab'):axis(a);letter(a,s)
    fig.text(.12,.05,'a: conditional bootstrap, shared within-study multiplicities across both benchmarks.\nb: analytic endpoint opportunity reference, not adjustment for contributions or cross-study dependence.',fontsize=6.6);export(fig,'F4_S6')
def main():
    for f in ['strict_main_bootstrap_complete','N06_complete','conditional_reference_complete','ancillary_complete','unique_role_country_institution_bootstrap_complete']:require((ROOT/'provenance'/(f+'.json')).exists(),'Missing '+f)
    main4();main5();ed1();country_pages();institution_summary();structure_ed();supplements();dump(ROOT/'provenance/figure_registry.json',REG);print('Exported',len(REG),'figure groups',sum(r['pages'] for r in REG),'pages',flush=True)
if __name__=='__main__':main()
