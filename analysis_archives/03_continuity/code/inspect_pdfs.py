#!/usr/bin/env python3
"""Inspect delivered vector pages, actual text fonts, and raster resolution."""
from pathlib import Path
import json,sys
from pypdf import PdfReader
from pypdf.generic import ContentStream
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'Figure3_review':(180,190),'ED_use_transitions_review':(180,155),'S_fixed_windows_review':(180,145)}
required={'Figure3_review':['86.39%','90.23%','42.48%','30.27%','43.13%','10.80%','20.32%','48.63%','27.29%','9.07%','63.64%','61.39%'],'ED_use_transitions_review':['24.90%','13.46%','20.00%','17.72%','44/220','96','80'],'S_fixed_windows_review':['760/4,955','1,339/4,955','2,137/4,955','19/176']}
reports=[]
for name,(w,h) in EXPECTED.items():
    pdf=ROOT/'figures'/(name+'.pdf');r=PdfReader(pdf);page=r.pages[0]
    width=float(page.mediabox.width);height=float(page.mediabox.height)
    text=page.extract_text()
    resources=page['/Resources']['/Font'];used=set();active=None
    for operands,op in ContentStream(page.get_contents(),r).operations:
        if op==b'Tf':active=str(operands[0])
        elif op in [b'Tj',b'TJ',b"'",b'"'] and active:used.add(active)
    font_rows=[]
    for key in used:
        font=resources[key].get_object();desc=font.get('/FontDescriptor')
        if desc is None and font.get('/DescendantFonts'):desc=font['/DescendantFonts'][0].get_object().get('/FontDescriptor')
        desc=desc.get_object() if desc else {}
        embedded=any(k in desc for k in ['/FontFile','/FontFile2','/FontFile3'])
        font_rows.append(dict(resource=key,base_font=str(font.get('/BaseFont')),embedded=embedded))
    svg=(ROOT/'figures'/(name+'.svg')).read_text()
    with Image.open(ROOT/'figures'/(name+'_600dpi.png')) as image:png_size=image.size
    with Image.open(ROOT/'figures'/(name+'_600dpi.tiff')) as image:tiff_size=image.size;tiff_dpi=[float(v) for v in image.info.get('dpi',[])]
    expected_size=(round(w/25.4*600),round(h/25.4*600))
    missing=[v for v in required[name] if v not in text]
    checks=dict(single_page=len(r.pages)==1,correct_page_size=abs(width-w*72/25.4)<.01 and abs(height-h*72/25.4)<.01,used_fonts_embedded=all(x['embedded'] for x in font_rows),required_text_present=not missing,svg_text_editable='<text' in svg,raster_size_correct=all(abs(a-b)<=1 for a,b in zip(png_size,expected_size)),tiff_matches_png=tiff_size==png_size,review_status_marked='REVIEW DRAFT' in text)
    reports.append(dict(figure=name,checks=checks,page_points=[width,height],used_fonts=font_rows,missing_text=missing,png_600dpi_size=png_size,tiff_dpi=tiff_dpi))
geometry=json.loads((ROOT/'provenance/text_geometry.json').read_text())
status='PASS' if all(all(x['checks'].values()) for x in reports) and not geometry['outside_page'] else 'FAIL'
report=dict(status=status,figures=reports,outside_page_text_count=len(geometry['outside_page']),minimum_font_size=geometry['minimum_font_size'],semantic_validation=False)
(ROOT/'provenance/pdf_qa.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if status!='PASS':sys.exit(1)
