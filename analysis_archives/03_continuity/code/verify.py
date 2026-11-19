#!/usr/bin/env python3
"""Verify frozen provenance, manuscript counts, denominators and cross-figure links."""
from pathlib import Path
import csv,json,hashlib,math,sys
ROOT=Path(__file__).resolve().parents[1]
CHECKS=[]
def check(name,condition,detail=''):
    CHECKS.append(dict(check=name,passed=bool(condition),detail=detail))
def rows(name,folder='plot_data'):
    with (ROOT/folder/name).open(newline='') as f:return list(csv.DictReader(f))
def I(r,k):return int(r[k])
def F(r,k):return float(r[k])
def one(data,**kw):return next(r for r in data if all(r[k]==str(v) for k,v in kw.items()))
def near(a,b):return math.isclose(a,b,abs_tol=1e-9)
def main():
    for r in json.loads((ROOT/'provenance/input_manifest.json').read_text()):
        p=ROOT/r['snapshot_path'];check('snapshot_hash:'+r['snapshot_path'],p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'])
    a=rows('Figure3a.csv');b=rows('Figure3b.csv');c=rows('Figure3c.csv');ed=rows('ED_use_transitions.csv');cells=rows('ED_development_cells.csv');s=rows('S_fixed_windows.csv')
    check('3a_exactly_12_rows',len(a)==12)
    for r in a:
        k=r['size_group']+':'+r['activity']
        check('3a_counts:'+k,I(r,'D')==I(r,'Y')+I(r,'not_established') and I(r,'N')==I(r,'D')+I(r,'unknown'))
        check('3a_supported_denominator:'+k,near(F(r,'supported_pct'),100*I(r,'Y')/I(r,'D')))
        check('3a_assessability_denominator:'+k,near(F(r,'assessable_pct'),100*I(r,'D')/I(r,'N')))
    for g,act,y,den in [('L','prediction_run',127,147),('H','prediction_run',1848,2048),('L','method_or_tool_development',48,113),('H','method_or_tool_development',386,1275)]:
        r=one(a,size_group=g,activity=act);check('manuscript_entry_counts:'+g+':'+act,(I(r,'Y'),I(r,'D'))==(y,den))
    for g,n in [('L',332),('M',972),('H',4695)]:check('entry_group_N:'+g,all(I(r,'N')==n for r in a if r['size_group']==g))
    for r in b:
        g=r['size_group'];check('repeat_partition:'+g,I(r,'N')==I(r,'C')+I(r,'U')+I(r,'known_no_event'))
        check('repeat_point:'+g,near(F(r,'confirmed_pct'),100*I(r,'C')/I(r,'N')))
        check('recorded_upper:'+g,near(F(r,'recorded_event_upper_pct'),100*(I(r,'C')+I(r,'U'))/I(r,'N')))
    # These literals lock the received manuscript's denominators, not source-generated expectations.
    expected={'All':(4955,2137,307),'L':(176,19,6),'M':(630,128,30),'H':(3903,1898,259)}
    for g,counts in expected.items():
        r=one(b,size_group=g);check('manuscript_repeat_counts:'+g,tuple(I(r,k) for k in ['N','C','U'])==counts)
    check('author_counts_lock',[(r['author_group'],I(r,'n'),I(r,'N')) for r in c]==[('initial_only',358,1312),('mixed',119,1312),('no_initial_overlap',835,1312)])
    check('author_partition',sum(I(r,'n') for r in c)==1312 and all(I(r,'repeat_N')==2137 for r in c))
    avail=rows('author_availability.csv')[0]
    check('author_unknown_kept_separate',I(avail,'unassessable_N')==825 and I(avail,'assessable_N')+825==2137)
    check('author_denominator_not_2137',all(I(r,'N')==1312 and near(F(r,'percent'),100*I(r,'n')/1312) for r in c))
    for r in ed:
        k=r['activity'];N=I(r,'N')
        check('paired_four_cells:'+k,sum(I(r,x) for x in ['n00','n01','n10','n11'])==N)
        check('paired_changed:'+k,near(F(r,'changed_pct'),100*(I(r,'n01')+I(r,'n10'))/N))
        check('paired_net:'+k,near(F(r,'net_change_pp'),100*(I(r,'n01')-I(r,'n10'))/N))
    d=one(ed,activity='method_or_tool_development')
    check('development_four_cell_lock',tuple(I(d,k) for k in ['N','n00','n01','n10','n11'])==(220,96,22,22,80))
    check('development_20percent_and_zero_net',near(F(d,'changed_pct'),20) and near(F(d,'net_change_pp'),0))
    check('development_cell_export',sum(I(r,'n') for r in cells)==220 and sorted(I(r,'n') for r in cells)==[22,22,80,96])
    for g in expected:
        rr=sorted([r for r in s if r['size_group']==g],key=lambda r:I(r,'months'))
        check('fixed_N:'+g,len(rr)==3 and {I(r,'N') for r in rr}=={expected[g][0]} and [I(r,'months') for r in rr]==[3,6,12])
        check('cumulative_confirmed_monotonic:'+g,all(I(rr[i],'C')<=I(rr[i+1],'C') for i in range(2)))
        br=one(b,size_group=g)
        check('12month_same_as_3b:'+g,all(rr[-1][k]==br[k] for k in ['N','C','U','known_no_event','confirmed_pct','recorded_event_upper_pct']))
    check('3month_not_wrong_independent_cohort',I(one(s,size_group='All',months=3),'C')==760)
    check('6month_counts',I(one(s,size_group='All',months=6),'C')==1339)
    # Cross-group sums retain unclassified institutions in all source tables.
    for source,keys in [('Fig3b_repeat12.csv',['N','C','U']),('Fig3d_author_groups.csv',['n'])]:
        data=rows(source,'source_inputs/tables')
        for key in keys:
            if source.startswith('Fig3b'):
                total=I(one(data,cohort='All',size_group='All'),key)
                subtotal=sum(I(one(data,cohort='All',size_group=g),key) for g in ['L','M','H','Unclassified'])
                check('unclassified_retained:'+source+':'+key,total==subtotal)
            else:
                for ag in ['initial_only','mixed','no_initial_overlap']:
                    total=I(one(data,cohort='All',size_group='All',author_group=ag),key)
                    subtotal=sum(I(one(data,cohort='All',size_group=g,author_group=ag),key) for g in ['L','M','H','Unclassified'])
                    check('unclassified_retained:'+source+':'+ag,total==subtotal)
    claims=rows('manuscript_claims.csv');manuscript=(ROOT/'manuscript/final_received.txt').read_text()
    for r in claims:
        check('manuscript_percentage:'+r['claim_id'],f"{F(r,'recomputed_pct'):.2f}"==r['manuscript_pct'])
        # The manuscript reports only range endpoints for two activities.
        if r['claim_id'] not in ['changed_precomputed_structure_use','changed_prediction_run','changed_prediction_evaluation_or_validation']:
            check('percentage_present_in_frozen_text:'+r['claim_id'],r['manuscript_pct']+'%' in manuscript)
    mapping=rows('panel_map.csv')
    check('old_3d_becomes_current_3c',one(mapping,old_panel='Fig3d')['current_panel']=='Fig3c')
    check('old_3c_becomes_ED',one(mapping,old_panel='Fig3c')['current_panel']=='ED_use_transitions')
    validation=json.loads((ROOT/'source_inputs/provenance/independent_validation_status.json').read_text())
    check('pending_validation_not_claimed_complete',validation['status']=='designed_not_independently_annotated' and validation['accuracy_estimated'] is False)
    for f in ['01_图表总方案.md','02_逐面板绘图规格.md','03_统计口径与数据字典.md','04_英文图注与补充说明.md','05_编号映射与正文核对.md','06_验收与待办.md','07_交给绘图人员的执行说明.txt']:
        check('handoff_file_exists:'+f,(ROOT/f).exists())
    report=dict(status='PASS' if all(r['passed'] for r in CHECKS) else 'FAIL',checks=len(CHECKS),passed=sum(r['passed'] for r in CHECKS),failed=[r for r in CHECKS if not r['passed']],independent_semantic_validation=False,new_inferential_tests=False,items=CHECKS)
    (ROOT/'provenance/verification_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','checks','passed','failed']},ensure_ascii=False))
    if report['status']!='PASS':sys.exit(1)
if __name__=='__main__':main()
