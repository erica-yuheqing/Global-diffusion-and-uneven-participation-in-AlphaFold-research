#!/usr/bin/env python3
"""Prepare manuscript-aligned plotting tables from frozen aggregate snapshots only."""
from pathlib import Path
import csv
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source_inputs/tables';OUT=ROOT/'plot_data'
ACTIVITIES=[('precomputed_structure_use','Precomputed structures'),('prediction_run','Prediction runs'),('method_or_tool_development','Method or tool development'),('prediction_evaluation_or_validation','Prediction evaluation / validation')]
GROUPS=['L','M','H']
def read(name):
    with (SRC/name).open(newline='') as f:return list(csv.DictReader(f))
def write(name,rows):
    if not rows:raise ValueError(name)
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def pct(n,d):return 100*int(n)/int(d)
def select(rows,**kw):return next(r for r in rows if all(r[k]==str(v) for k,v in kw.items()))
def main():
    OUT.mkdir(exist_ok=True)
    initial=read('Fig3a_entry_uses.csv');repeat=read('Fig3b_repeat12.csv');authors=read('Fig3d_author_groups.csv');paired=read('Fig3c_use_transitions.csv');windows=read('S4_common_windows.csv')
    a=[]
    for rank,(act,label) in enumerate(ACTIVITIES):
        for g in GROUPS:
            r=select(initial,cohort='All',size_group=g,activity=act)
            a.append(dict(panel_id='Fig3a',source_table='Fig3a_entry_uses.csv',cohort='All',size_group=g,activity=act,activity_label=label,activity_order=rank+1,N=int(r['N']),D=int(r['D']),Y=int(r['Y']),not_established=int(r['not_established']),unknown=int(r['unknown']),supported_pct=pct(r['Y'],r['D']),assessable_pct=pct(r['D'],r['N'])))
    write('Figure3a.csv',a)
    b=[]
    for g in ['All']+GROUPS:
        r=select(repeat,cohort='All',size_group=g)
        b.append(dict(panel_id='Fig3b',source_table='Fig3b_repeat12.csv',cohort='All',size_group=g,months=12,N=int(r['N']),C=int(r['C']),U=int(r['U']),known_no_event=int(r['known_no_event']),confirmed_pct=pct(r['C'],r['N']),recorded_event_upper_pct=pct(int(r['C'])+int(r['U']),r['N'])))
    write('Figure3b.csv',b)
    c=[]
    for g,label in [('initial_only','Initial authors only'),('mixed','Initial + other authors'),('no_initial_overlap','No initial-author overlap')]:
        r=select(authors,cohort='All',size_group='All',author_group=g)
        c.append(dict(panel_id='Fig3c',source_table='Fig3d_author_groups.csv',cohort='All',size_group='All',author_group=g,author_label=label,n=int(r['n']),N=int(r['N']),repeat_N=int(r['repeat_N']),percent=pct(r['n'],r['N'])))
    write('Figure3c.csv',c)
    write('author_availability.csv',[dict(panel_id='Fig3c',assessable_N=c[0]['N'],repeat_N=c[0]['repeat_N'],unassessable_N=c[0]['repeat_N']-c[0]['N'],assessable_pct=pct(c[0]['N'],c[0]['repeat_N']))])
    ed=[]
    for act,label in ACTIVITIES:
        r=select(paired,cohort='All',size_group='All',activity=act)
        n={k:int(r[k]) for k in ['N','n00','n01','n10','n11']}
        ed.append(dict(panel_id='ED_use_transitions_a',source_table='Fig3c_use_transitions.csv',cohort='All',size_group='All',activity=act,activity_label=label,**n,newly_established_pct=pct(n['n01'],n['N']),not_reestablished_pct=pct(n['n10'],n['N']),changed_pct=pct(n['n01']+n['n10'],n['N']),net_change_pp=100*(n['n01']-n['n10'])/n['N']))
    write('ED_use_transitions.csv',ed)
    d=next(r for r in ed if r['activity']=='method_or_tool_development')
    cells=[]
    for initial,followup,key in [(0,0,'n00'),(0,1,'n01'),(1,0,'n10'),(1,1,'n11')]:
        cells.append(dict(panel_id='ED_use_transitions_b',initial_evidence=initial,followup_evidence=followup,cell=key,n=d[key],N=d['N'],percent=pct(d[key],d['N'])))
    write('ED_development_cells.csv',cells)
    s=[]
    for g in ['All']+GROUPS:
        for m in [3,6,12]:
            r=select(windows,cohort='All',size_group=g,months=m)
            s.append(dict(panel_id='S_fixed_windows_'+g,source_table='S4_common_windows.csv',cohort='All',size_group=g,months=m,N=int(r['N']),C=int(r['C']),U=int(r['U']),known_no_event=int(r['known_no_event']),confirmed_pct=pct(r['C'],r['N']),recorded_event_upper_pct=pct(int(r['C'])+int(r['U']),r['N'])))
    write('S_fixed_windows.csv',s)
    write('panel_map.csv',[dict(old_panel=o,current_panel=n,source_table=t,disposition=d) for o,n,t,d in [('Fig3a','Fig3a','Fig3a_entry_uses.csv','main'),('Fig3b','Fig3b','Fig3b_repeat12.csv','main'),('Fig3c','ED_use_transitions','Fig3c_use_transitions.csv','extended_data'),('Fig3d','Fig3c','Fig3d_author_groups.csv','main'),('Fig3e','not_used','Fig3e_author_use.csv','not_in_final_text'),('S4','S_fixed_windows','S4_common_windows.csv','supplementary')]])
    claims=[]
    def add(key,panel,n,den,expected,table,meaning):
        claims.append(dict(claim_id=key,panel=panel,numerator=n,denominator=den,recomputed_pct=pct(n,den),manuscript_pct=expected,source_table=table,meaning=meaning))
    for g,act,e in [('L','prediction_run','86.39'),('H','prediction_run','90.23'),('L','method_or_tool_development','42.48'),('H','method_or_tool_development','30.27')]:
        r=select(a,size_group=g,activity=act);add(g+'_'+act,'Fig3a',r['Y'],r['D'],e,r['source_table'],'supported among activity-assessable entrants')
    for g,e in [('All','43.13'),('L','10.80'),('M','20.32'),('H','48.63')]:
        r=select(b,size_group=g);add('repeat_'+g,'Fig3b',r['C'],r['N'],e,r['source_table'],'confirmed repeat publication within 12 calendar months')
    r=b[0];add('recorded_upper_All','Fig3b',r['C']+r['U'],r['N'],'49.32',r['source_table'],'recorded-event upper endpoint, not CI')
    add('author_assessable','Fig3c',1312,2137,'61.39','Fig3d_author_groups.csv','author-overlap assessability among confirmed repeating institutions')
    for r,e in zip(c,['27.29','9.07','63.64']):add(r['author_group'],'Fig3c',r['n'],r['N'],e,r['source_table'],'author composition among assessable repeating institutions')
    for r,e in zip(ed,['24.90','13.46','20.00','17.72']):add('changed_'+r['activity'],'ED_use_transitions',r['n01']+r['n10'],r['N'],e,r['source_table'],'paired evidence-state change, category-specific denominator')
    write('manuscript_claims.csv',claims)
    print('Prepared 9 plot/source-data CSV files; no new statistical models.')
if __name__=='__main__':main()
