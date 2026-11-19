"""Independent current-output checks, including actual plotted coordinates and links."""
from pathlib import Path
import csv,json,math,re,hashlib
from PIL import Image
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
def rows(p):
    with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def main():
    checks={}
    def ck(k,v):
        checks[k]=bool(v)
        if not v:raise ValueError(k)
    old=json.loads((ROOT/'provenance/verification_report.json').read_text());linkage=json.loads((ROOT/'provenance/linkage_review.json').read_text());pdf=json.loads((ROOT/'provenance/pdf_qa.json').read_text())
    ck('fresh inherited arithmetic checks',old['status']=='PASS' and old['checks']==old['passed']==161 and not old['independent_semantic_validation'])
    ck('new ID/group audit',linkage['status']=='PASS' and linkage['Finding2_date_N']-linkage['Finding3_entry_N']==linkage['excluded_Pre_AF2_N']==41 and not linkage['baseline_mismatches'])
    ck('native PDF QA',pdf['status']=='PASS' and pdf['minimum_font_size']>=6 and pdf['outside_page_text_count']==0)
    mapping=rows(ROOT/'source_data/panel_source_map.csv');ck('three figures nine panels',len(mapping)==9 and len({r['figure'] for r in mapping})==3)
    source=[]
    for r in mapping:
        p=ROOT/r['source_data'];data=rows(p);original=rows(ROOT/r['frozen_plot_source'])
        if r['figure']=='S_fixed_windows':original=[x for x in original if x['size_group']==dict(zip('abcd',['All','L','M','H']))[r['panel']]]
        ck('direct source '+r['figure']+r['panel'],data==original and len(data)==int(r['rows']) and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']);source+=data
    # Current plotting tables must match all selected frozen source rows, not only manuscript anchors.
    a=rows(ROOT/'source_inputs/tables/Fig3a_entry_uses.csv');b=rows(ROOT/'source_inputs/tables/Fig3b_repeat12.csv');c=rows(ROOT/'source_inputs/tables/Fig3d_author_groups.csv');ed=rows(ROOT/'source_inputs/tables/Fig3c_use_transitions.csv')
    for name,raw,key,cols in [('Figure3a.csv',a,['size_group','activity'],['N','D','Y','not_established','unknown']),('Figure3b.csv',b,['size_group'],['N','C','U','known_no_event']),('Figure3c.csv',c,['author_group'],['N','n','repeat_N']),('ED_use_transitions.csv',ed,['activity'],['N','n00','n01','n10','n11'])]:
        for r in rows(ROOT/'plot_data'/name):
            oldrow=next(x for x in raw if x['cohort']=='All' and (name!='Figure3c.csv' or x['size_group']=='All') and (name!='ED_use_transitions.csv' or x['size_group']=='All') and all(x[k]==r[k] for k in key))
            ck('selected frozen counts '+name+' '+' '.join(r[k] for k in key),all(int(oldrow[k])==int(r[k]) for k in cols))
    records=json.loads((ROOT/'provenance/plotted_records.json').read_text());ck('all nine panels actually plotted',len({x['panel'] for x in records})==9)
    ck('59 actual plotted marks',len(records)==59)
    def match_record(r):
        p=r['panel'];kind=r['kind']
        if p=='Figure3a':
            x=next(x for x in rows(ROOT/'plot_data/Figure3a.csv') if x['size_group']==r['group'] and x['activity']==r['activity']);return int(x['Y']),int(x['D'])
        if p=='Figure3b':
            x=next(x for x in rows(ROOT/'plot_data/Figure3b.csv') if x['size_group']==r['group']);return int(x['C'])+(int(x['U']) if kind=='recorded_upper' else 0),int(x['N'])
        if p=='Figure3c':
            x=next(x for x in rows(ROOT/'plot_data/Figure3c.csv') if x['author_group']==r['group']);return int(x['n']),int(x['N'])
        if p=='ED_use_transitions_a':
            x=next(x for x in rows(ROOT/'plot_data/ED_use_transitions.csv') if x['activity']==r['activity']);return int(x['n10' if kind=='not_reestablished' else 'n01']),int(x['N'])
        if p=='ED_use_transitions_b':
            x=next(x for x in rows(ROOT/'plot_data/ED_development_cells.csv') if int(x['initial_evidence'])==r['initial'] and int(x['followup_evidence'])==r['followup']);return int(x['n']),int(x['N'])
        x=next(x for x in rows(ROOT/'plot_data/S_fixed_windows.csv') if x['size_group']==r['group'] and int(x['months'])==r['months']);return int(x['C'])+(int(x['U']) if kind=='recorded_upper' else 0),int(x['N'])
    for n,r in enumerate(records):
        numerator,denominator=match_record(r);expected=100*numerator/denominator
        ck('plotted value '+str(n),(r['numerator'],r['denominator'])==(numerator,denominator) and math.isclose(r['value_pct'],expected,abs_tol=1e-10))
        if 'x0' in r and 'y0' not in r:
            value=expected*r.get('direction',1);px=r['x0']+(value-r['vmin'])/(r['vmax']-r['vmin'])*(r['x1']-r['x0']);ck('plotted x position '+str(n),math.isclose(r['x'],px,abs_tol=1e-10))
        if 'y0' in r:
            px=r['x0']+(r['months']-3)/9*(r['x1']-r['x0']);py=r['y0']+expected/60*(r['y1']-r['y0']);ck('true month spacing and y '+str(n),math.isclose(r['x'],px,abs_tol=1e-10) and math.isclose(r['y'],py,abs_tol=1e-10))
        if r['kind']=='recorded_upper':ck('open circle and not CI '+str(n),r['open_endpoint_shape']=='circle')
    forbidden=['Activities reported at entry','Repeat publication within 12 months','Authors on the first follow-up study','Changes in reported activity evidence','Method or tool development: all paired evidence states','Repeat publication over fixed follow-up windows']
    for name in ['Figure3_review','ED_use_transitions_review','S_fixed_windows_review']:
        pdftext=PdfReader(ROOT/'figures'/f'{name}.pdf').pages[0].extract_text()
        ck('letters without long titles '+name,not any(t in pdftext for t in forbidden))
        ck('review state current '+name,'REVIEW DRAFT | Independent activity-label validation pending' in pdftext)
        with Image.open(ROOT/'figures'/f'{name}_600dpi.png') as im:
            im.load();ck('PNG RGB sRGB 600dpi '+name,im.mode=='RGB' and min(im.info['dpi'])>=599 and bool(im.info.get('icc_profile')));png=im.copy()
        with Image.open(ROOT/'figures'/f'{name}_600dpi.tiff') as im:
            im.load();ck('TIFF RGB sRGB LZW 600dpi '+name,im.mode=='RGB' and im.info.get('compression')=='tiff_lzw' and min(im.info['dpi'])>=599 and bool(im.info.get('icc_profile')))
            ck('TIFF PNG exact pixels '+name,im.size==png.size and im.tobytes()==png.tobytes())
    ck('English received text unchanged',(ROOT/'results_en.md').read_bytes()==(ROOT/'manuscript/final_received.txt').read_bytes())
    # These two files are the validator's own outputs; do not claim PASS before the link audit.
    (ROOT/'provenance/release_checks.json').write_text(json.dumps({'status':'CHECKING_LINKS'})+'\n')
    links=[]
    for p in ROOT.rglob('*.md'):
        if 'historical' in p.relative_to(ROOT).parts:continue
        for raw in re.findall(r'!?\[[^\]]*\]\(([^\n]+?)\)',p.read_text()):
            target=raw.strip().strip('<>')
            if target.startswith(('http:','https:','mailto:','#')):continue
            target=target.split('#')[0];dest=(p.parent/target).resolve()
            ck('relative link '+str(p.relative_to(ROOT))+' '+target,not target.startswith('/') and dest.is_relative_to(ROOT.resolve()) and dest.exists());links.append(dict(file=str(p.relative_to(ROOT)),target=target))
    result=dict(status='PASS',check_count=len(checks),checks=checks,active_relative_links=len(links),inherited_arithmetic_checks=161,linkage_checks=linkage['check_count'],actual_plot_records=len(records),independent_activity_semantic_validation=False,new_models=0,new_inferential_tests=0,API_calls=0,LLM_calls=0)
    (ROOT/'provenance/release_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');(ROOT/'provenance/link_audit.json').write_text(json.dumps(dict(status='PASS',links=links),ensure_ascii=False,indent=2)+'\n')
    print('New release checks PASS:',len(checks),'checks;',len(links),'relative links',flush=True)
if __name__=='__main__':main()
