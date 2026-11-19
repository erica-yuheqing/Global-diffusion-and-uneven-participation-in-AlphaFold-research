"""ID-level cross-section and inherited group checks; no label/date reconstruction."""
from pathlib import Path
import csv,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def rows(p):
    with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def truth(s):return str(s).lower()=='true'
def write(p,rr):
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
def main():
    root=ROOT/'source_inputs/cohort_linkage';checks={}
    def ck(k,v):
        checks[k]=bool(v)
        if not v:raise ValueError(k)
    for pin in json.loads((ROOT/'provenance/local_linkage_pins.json').read_text()):ck('copied linkage hash '+pin['copy'],hashlib.sha256((ROOT/pin['copy']).read_bytes()).hexdigest()==pin['sha256'])
    f2={r['institution_id']:r for r in rows(root/'F2_date_registry.csv')};f3={r['institution_id']:r for r in rows(root/'F3_entry_registry.csv')}
    b2={r['institution_id']:r for r in rows(root/'F2_baseline_registry.csv')};b3={r['institution_id']:r for r in rows(root/'F3_baseline_registry.csv')}
    ck('baseline 52098 same unique IDs',len(b2)==len(b3)==52098 and set(b2)==set(b3))
    fields=['V_i','baseline_country_count','country','baseline_country_set','group','group_eligible','cut_LM','cut_MH','context','eligible_10','eligible_20','eligible_30','qualification']
    mismatches=[{'institution_id':i,'field':f,'Finding2':b2[i][f],'Finding3':b3[i][f]} for i in sorted(b2) for f in fields if b2[i][f]!=b3[i][f]]
    ck('inherited baseline fields and cutpoints identical',not mismatches)
    ck('F3 6328 subset F2 6369',len(f2)==6369 and len(f3)==6328 and set(f3)<=set(f2))
    removed=sorted(set(f2)-set(f3));ck('exact 41 Pre-AF2 exclusions',len(removed)==41 and all(f2[i]['phase']=='Pre-AF2' for i in removed))
    ck('shared dates and eras identical',all(f2[i]['first_date_identifiable_AF_publication']==f3[i]['entry_date'] and f2[i]['phase']==f3[i]['entry_cohort'] for i in f3))
    ck('only AF2 AF3 retained',{r['entry_cohort'] for r in f3.values()}=={'AF2','AF3'})
    ck('entry group inherits N20',all(r['size_group']==(b3[i]['group'] if truth(b3[i]['eligible_20']) else 'Unclassified') for i,r in f3.items()))
    for cohort in ['All','AF2','AF3']:
        for g in ['All','L','M','H','Unclassified']:
            selected=[r for r in f3.values() if (cohort=='All' or r['entry_cohort']==cohort) and (g=='All' or r['size_group']==g)]
            for source in rows(ROOT/'source_inputs/tables/Fig3a_entry_uses.csv'):
                if source['cohort']!=cohort or source['size_group']!=g:continue
                act=source['activity'];states=[r['entry_'+act] for r in selected]
                yy=sum(s in ['1','1.0'] for s in states);dd=sum(s in ['0','0.0','1','1.0'] for s in states)
                ck(f'entry institution audit {cohort} {g} {act}',(len(selected),dd,yy)==tuple(int(source[k]) for k in ['N','D','Y']))
    audit=[]
    for i in sorted(f2):
        a=f2[i];b=f3.get(i);audit.append(dict(institution_id=i,Finding2_date=a['first_date_identifiable_AF_publication'],Finding2_phase=a['phase'],in_Finding3=b is not None,Finding3_date=b['entry_date'] if b else '',Finding3_phase=b['entry_cohort'] if b else '',Finding3_size_group=b['size_group'] if b else '',disposition='retained_AF2_AF3' if b else 'excluded_Pre_AF2'))
    write(ROOT/'tables/cross_section_ID_audit.csv',audit)
    write(ROOT/'tables/Pre_AF2_excluded_41.csv',[r for r in audit if not r['in_Finding3']])
    group_counts=[dict(cohort=c,size_group=g,n=sum((c=='All' or r['entry_cohort']==c) and (g=='All' or r['size_group']==g) for r in f3.values())) for c in ['All','AF2','AF3'] for g in ['All','L','M','H','Unclassified']]
    write(ROOT/'tables/entry_group_ID_counts.csv',group_counts)
    report=dict(status='PASS',check_count=len(checks),checks=checks,baseline_institutions=52098,baseline_fields_compared=fields,baseline_mismatches=mismatches,Finding2_date_N=6369,Finding3_entry_N=6328,excluded_Pre_AF2_N=41,date_mismatches=0,phase_mismatches=0,scope='Inherited IDs/group fields and frozen institution-state counts; not raw-article evidence, earliest-date identification or semantic validation')
    (ROOT/'provenance/linkage_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Cross-section ID/group audit PASS:',len(checks),'checks; 41 Pre-AF2 exclusions',flush=True)
if __name__=='__main__':main()
