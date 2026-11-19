#!/usr/bin/env python3
"""Reproducible vector chart drafts from aggregate data; no statistical inference.
Dependencies: reportlab, Pillow. Raster output additionally uses pdftoppm.
"""
from pathlib import Path
import argparse,csv,json,shutil,subprocess,sys,platform,importlib.metadata
import reportlab
from reportlab.graphics.shapes import Drawing,String,Line,Rect,Circle,Polygon
from reportlab.graphics import renderPDF,renderSVG
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor,Color,white
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'figures';DATA=ROOT/'plot_data';PROV=ROOT/'provenance'
MM=72/25.4
W=180*MM
COLORS={'L':'#56B4E9','M':'#009E73','H':'#0072B2','All':'#5E6670'}
DARK='#263A4A';GRID='#E1E5E9';MID='#5E6670';NEW='#4E79A7';NOT='#BC8359'
GROUP_LABEL={'All':'All','L':'Lower','M':'Middle','H':'Higher'}
ACT_LABELS=['Precomputed\nstructures','Prediction\nruns','Method or tool\ndevelopment','Prediction evaluation /\nvalidation']
TEXT_BOUNDS=[]
PLOT_RECORDS=[]
FONT='Helvetica';BOLD='Helvetica-Bold'
for regular,bold in [(Path('/System/Library/Fonts/Supplemental/Arial.ttf'),Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')),(Path('/Library/Fonts/Arial.ttf'),Path('/Library/Fonts/Arial Bold.ttf'))]:
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont('Arial',str(regular)));pdfmetrics.registerFont(TTFont('Arial-Bold',str(bold)))
        FONT='Arial';BOLD='Arial-Bold';break

def read(name):
    with (DATA/name).open(newline='') as f:return list(csv.DictReader(f))
def num(r,k):return float(r[k])
def integer(r,k):return int(r[k])
def color(c):return HexColor(c) if isinstance(c,str) else c
def text(d,x,y,value,size=7.5,fill=DARK,bold=False,anchor='start',max_width=None):
    value=str(value);face=BOLD if bold else FONT
    width=pdfmetrics.stringWidth(value,face,size)
    if max_width and width>max_width:
        size=size*max_width/width;width=max_width
        if size<6.0:raise ValueError(f'Text below 6pt: {value} ({size:.2f})')
    d.add(String(x,y,value,fontName=face,fontSize=size,fillColor=color(fill),textAnchor=anchor))
    left=x if anchor=='start' else x-width/2 if anchor=='middle' else x-width
    TEXT_BOUNDS.append(dict(figure=d._chart_name,text=value,x=left,y=y,width=width,font_size=size,page_width=d.width,page_height=d.height))

def multiline(d,x,y,value,size=7.5,fill=DARK,bold=False,leading=9,anchor='start',max_width=None):
    lines=value.split('\n');top=y+(len(lines)-1)*leading/2
    for i,v in enumerate(lines):text(d,x,top-i*leading,v,size,fill,bold,anchor,max_width)

def line(d,x1,y1,x2,y2,stroke=MID,width=.6,dash=None):
    d.add(Line(x1,y1,x2,y2,strokeColor=color(stroke),strokeWidth=width,strokeDashArray=dash))
def rect(d,x,y,w,h,fill,stroke=None,stroke_width=.5):
    d.add(Rect(x,y,w,h,fillColor=color(fill),strokeColor=color(stroke) if stroke else None,strokeWidth=stroke_width))
def mark(d,x,y,g,filled=True,r=2.6,stroke=None):
    c=color(stroke or COLORS.get(g,DARK));fc=c if filled else white
    if g=='M':s=Rect(x-r,y-r,2*r,2*r,fillColor=fc,strokeColor=c,strokeWidth=.8)
    elif g=='H':s=Polygon([x,y+r*1.2,x-r*1.12,y-r,x+r*1.12,y-r],fillColor=fc,strokeColor=c,strokeWidth=.8)
    else:s=Circle(x,y,r,fillColor=fc,strokeColor=c,strokeWidth=.8)
    d.add(s)

def canvas(name,height):
    d=Drawing(W,height*MM);d._chart_name=name;rect(d,0,0,W,d.height,'#FFFFFF');return d

def footer(d):
    text(d,5,5,'REVIEW DRAFT | Independent activity-label validation pending',6.1,fill=MID)

def axis_x(d,x0,x1,y,vmin,vmax,ticks,label,grid_top=None,label_y=None):
    line(d,x0,y,x1,y,DARK,.6)
    for v in ticks:
        x=x0+(v-vmin)/(vmax-vmin)*(x1-x0)
        if grid_top:line(d,x,y,x,grid_top,GRID,.4)
        line(d,x,y,x,y-3,DARK,.5)
        text(d,x,y-11,f'{v:g}',6.5,anchor='middle')
    text(d,(x0+x1)/2,label_y if label_y is not None else y-24,label,7.1,anchor='middle')

def figure3():
    d=canvas('Figure3_review',190)
    text(d,5,519,'a',11,bold=True)
    for g,x,n in [('L',140,332),('M',257,972),('H',374,4695)]:
        mark(d,x,497,g);text(d,x+8,494,f'{GROUP_LABEL[g]} (N={n:,})',7.1)
    text(d,209,475,'Supported among assessable',7.2,anchor='middle',max_width=145)
    text(d,337,475,'Evidence / assessable',7.2,anchor='middle',max_width=104)
    text(d,453,475,'Assessable / entrants',7.2,anchor='middle',max_width=108)
    x0,x1=141,278;yaxis=267
    axis_x(d,x0,x1,yaxis,0,100,[0,25,50,75,100],'Supported among assessable (%)',grid_top=462,label_y=242)
    rows=read('Figure3a.csv')
    acts=[]
    for r in rows:
        if r['activity'] not in acts:acts.append(r['activity'])
    for i,(act,ylab) in enumerate(zip(acts,ACT_LABELS)):
        yc=440-i*49
        multiline(d,5,yc,ylab,7.5,max_width=125)
        for g,dy in [('L',12),('M',0),('H',-12)]:
            r=next(r for r in rows if r['activity']==act and r['size_group']==g);y=yc+dy
            mark(d,x0+num(r,'supported_pct')/100*(x1-x0),y,g)
            PLOT_RECORDS.append(dict(panel='Figure3a',kind='supported',group=g,activity=act,numerator=integer(r,'Y'),denominator=integer(r,'D'),value_pct=num(r,'supported_pct'),x=x0+num(r,'supported_pct')/100*(x1-x0),x0=x0,x1=x1,vmin=0,vmax=100))
            text(d,337,y-2.4,f"{num(r,'supported_pct'):.2f}% ({integer(r,'Y'):,}/{integer(r,'D'):,})",6.7,anchor='middle',max_width=107)
            text(d,453,y-2.4,f"{num(r,'assessable_pct'):.2f}% ({integer(r,'D'):,}/{integer(r,'N'):,})",6.7,anchor='middle',max_width=108)
    text(d,5,224,'Activities overlap; proportions use category-specific assessable samples.',7.0)
    line(d,5,215,W-5,215,GRID,.6)
    # Panel b: point at confirmed rate, dotted extension to recorded-event endpoint.
    text(d,5,200,'b',11,bold=True)
    b=read('Figure3b.csv');x0,x1=61,158;by=57
    axis_x(d,x0,x1,by,0,60,[0,20,40,60],'',grid_top=184,label_y=34)
    multiline(d,(x0+x1)/2,35,'Confirmed repeat publication\nwithin 12 months (%)',6.9,leading=8,anchor='middle')
    for r,y in zip(b,[174,143,112,81]):
        g=r['size_group'];text(d,5,y-2.5,GROUP_LABEL[g],7.3)
        lo=x0+num(r,'confirmed_pct')/60*(x1-x0);hi=x0+num(r,'recorded_event_upper_pct')/60*(x1-x0)
        line(d,lo,y,hi,y,COLORS[g],1.0,[1.6,1.8]);mark(d,hi,y,'All',filled=False,r=2.2,stroke=COLORS[g]);mark(d,lo,y,g,r=2.7)
        for kind,nn,xx in [('confirmed',integer(r,'C'),lo),('recorded_upper',integer(r,'C')+integer(r,'U'),hi)]:
            PLOT_RECORDS.append(dict(panel='Figure3b',kind=kind,group=g,numerator=nn,denominator=integer(r,'N'),value_pct=100*nn/integer(r,'N'),x=xx,x0=x0,x1=x1,vmin=0,vmax=60,open_endpoint_shape='circle' if kind=='recorded_upper' else None))
        text(d,168,y+1,f"{integer(r,'C'):,}/{integer(r,'N'):,}",6.9)
        text(d,247,y+1,f"{num(r,'confirmed_pct'):.2f}%",6.9,anchor='end')
        text(d,168,y-9,f"Unresolved: {integer(r,'U'):,}",6.1,fill=MID)
    line(d,5,20,19,20,MID,.7,[1.6,1.8]);text(d,23,17,'Dotted extensions: unresolved recorded events; not CIs',6.2,max_width=220)
    # Panel c: its denominator is author-assessable repeaters, not all repeaters.
    text(d,270,200,'c',11,bold=True)
    text(d,270,184,'Author overlap assessable: 1,312/2,137 (61.39%)',6.6,max_width=235)
    c=read('Figure3c.csv');x0,x1=367,447
    axis_x(d,x0,x1,by,0,70,[0,35,70],'Assessable institutions (%)',grid_top=171,label_y=34)
    labs=['Initial authors\nonly','Initial + other\nauthors','No initial-author\noverlap']
    for r,y,lab in zip(c,[156,119,82],labs):
        multiline(d,270,y,lab,7.0,max_width=91)
        rect(d,x0,y-5,num(r,'percent')/70*(x1-x0),10,DARK)
        PLOT_RECORDS.append(dict(panel='Figure3c',kind='author_bar',group=r['author_group'],numerator=integer(r,'n'),denominator=integer(r,'N'),value_pct=num(r,'percent'),x=x0+num(r,'percent')/70*(x1-x0),x0=x0,x1=x1,vmin=0,vmax=70))
        text(d,507,y+1,f"{num(r,'percent'):.2f}%",6.9,anchor='end')
        text(d,507,y-9,f"{integer(r,'n'):,}/{integer(r,'N'):,}",6.4,fill=MID,anchor='end')
    text(d,270,17,'825/2,137 unavailable; excluded from the three bars.',6.2,max_width=236)
    footer(d);return d

def transitions():
    d=canvas('ED_use_transitions_review',155)
    text(d,5,421,'a',11,bold=True)
    rect(d,222,405,9,6,NOT);text(d,236,404,'Not re-established',7)
    rect(d,359,405,9,6,NEW);text(d,373,404,'Newly established',7)
    rows=read('ED_use_transitions.csv');x0,x1=145,335;mid=(x0+x1)/2;scale=(x1-x0)/40
    axis_x(d,x0,x1,by:=180,-20,20,[-20,-10,0,10,20],'Paired institutions (%)',grid_top=390,label_y=154)
    line(d,mid,by,mid,390,DARK,.7)
    for r,y,lab in zip(rows,[369,320,271,222],ACT_LABELS):
        multiline(d,5,y,lab,7.5,max_width=130)
        l=num(r,'not_reestablished_pct')*scale;rr=num(r,'newly_established_pct')*scale
        rect(d,mid-l,y-8,l,16,NOT);rect(d,mid,y-8,rr,16,NEW)
        for kind,n,xx in [('not_reestablished',integer(r,'n10'),mid-l),('newly_established',integer(r,'n01'),mid+rr)]:
            PLOT_RECORDS.append(dict(panel='ED_use_transitions_a',kind=kind,activity=r['activity'],numerator=n,denominator=integer(r,'N'),value_pct=100*n/integer(r,'N'),x=xx,x0=x0,x1=x1,vmin=-20,vmax=20,direction=-1 if kind=='not_reestablished' else 1))
        text(d,mid-l/2,y-2.5,r['n10'],7.5,fill='#FFFFFF',bold=True,anchor='middle')
        text(d,mid+rr/2,y-2.5,r['n01'],7.5,fill='#FFFFFF',bold=True,anchor='middle')
        text(d,351,y+8,f"N={integer(r,'N'):,}; changed {num(r,'changed_pct'):.2f}%",7.0,max_width=153)
        net=num(r,'net_change_pp');label=f'{net:+.2f}' if net else '0.00'
        text(d,351,y-6,f'Net change: {label} pp',7.0)
    text(d,5,136,'b',11,bold=True)
    # Complete 2 x 2 evidence table.
    left=142;cw=170;bottom=30;rh=33
    text(d,left+cw,120,'First follow-up study',7.5,bold=True,anchor='middle')
    text(d,left+cw/2,106,'Not established',7.0,anchor='middle')
    text(d,left+cw*1.5,106,'Supported',7.0,anchor='middle')
    text(d,5,89,'Initial study',7.1,bold=True)
    cells=read('ED_development_cells.csv')
    for i,lab in [(0,'Not established'),(1,'Supported')]:
        y=bottom+(1-i)*rh
        text(d,20,y+14,lab,7.0)
        for j in [0,1]:
            r=next(r for r in cells if int(r['initial_evidence'])==i and int(r['followup_evidence'])==j)
            fill='#F2F4F6' if i==j else '#E8EFF6' if (i,j)==(0,1) else '#F6EEE7'
            rect(d,left+j*cw,y,cw,rh,fill,stroke='#FFFFFF',stroke_width=1.5)
            text(d,left+j*cw+cw/2,y+13,f"{r['n']} ({num(r,'percent'):.2f}%)",8,bold=True,anchor='middle')
            PLOT_RECORDS.append(dict(panel='ED_use_transitions_b',kind='development_cell',initial=i,followup=j,numerator=integer(r,'n'),denominator=integer(r,'N'),value_pct=num(r,'percent')))
    text(d,5,17,'Development: 44/220 changed (20.00%); net change 0.00 pp. Not established is not confirmed non-use.',6.8,max_width=500)
    footer(d);return d

def fixed_windows():
    d=canvas('S_fixed_windows_review',145)
    text(d,5,376,'Same complete-12-month cohort at every window; dotted extensions are not confidence intervals.',7.1,max_width=500)
    text(d,5,362,'Labels give confirmed counts C/N; open symbols include unresolved recorded events.',7.0,max_width=500)
    rows=read('S_fixed_windows.csv')
    for g,letter,left,base in [('All','a',0,224),('L','b',262,224),('M','c',0,57),('H','d',262,57)]:
        rr=sorted([r for r in rows if r['size_group']==g],key=lambda r:int(r['months']))
        x0,x1=left+31,left+223;y0,y1=base,base+106
        text(d,left+5,y1+17,letter,10,bold=True)
        text(d,left+21,y1+17,f"{GROUP_LABEL[g]} (N={integer(rr[0],'N'):,})",8.3,bold=True)
        for v in [0,20,40,60]:
            y=y0+v/60*(y1-y0);line(d,x0,y,x1,y,GRID,.45);text(d,x0-6,y-2.2,str(v),6.5,anchor='end')
        line(d,x0,y0,x1,y0,DARK,.6);line(d,x0,y0,x0,y1,DARK,.5)
        last=None
        for r in rr:
            x=x0+(int(r['months'])-3)/9*(x1-x0);y=y0+num(r,'confirmed_pct')/60*(y1-y0);upper=y0+num(r,'recorded_event_upper_pct')/60*(y1-y0)
            if last:line(d,*last,x,y,COLORS[g],1.1)
            line(d,x,y,x,upper,COLORS[g],.8,[1.5,1.5]);mark(d,x,upper,'All',False,2.2,stroke=COLORS[g]);mark(d,x,y,g,True,2.6)
            for kind,n,yy in [('confirmed',integer(r,'C'),y),('recorded_upper',integer(r,'C')+integer(r,'U'),upper)]:
                PLOT_RECORDS.append(dict(panel='S_fixed_windows_'+g,kind=kind,group=g,months=integer(r,'months'),numerator=n,denominator=integer(r,'N'),value_pct=100*n/integer(r,'N'),x=x,x0=x0,x1=x1,y=yy,y0=y0,y1=y1,vmin=0,vmax=60,open_endpoint_shape='circle' if kind=='recorded_upper' else None))
            text(d,x,upper+8,f"{integer(r,'C'):,}/{integer(r,'N'):,}",6.3,anchor='middle')
            text(d,x,y0-12,r['months'],6.6,anchor='middle')
            last=(x,y)
        text(d,(x0+x1)/2,y0-25,'Months after first AF publication',7,anchor='middle')
    text(d,5,17,'Y axes: confirmed repeat publication (%). All includes institutions with unclassified baseline output.',6.8,max_width=500)
    footer(d);return d

def main():
    p=argparse.ArgumentParser();p.add_argument('--vector-only',action='store_true');p.add_argument('--pdftoppm');args=p.parse_args()
    OUT.mkdir(exist_ok=True);PROV.mkdir(exist_ok=True)
    rasterizer=args.pdftoppm or shutil.which('pdftoppm')
    if not args.vector_only and not rasterizer:raise SystemExit('pdftoppm unavailable; specify --pdftoppm or --vector-only')
    drawings=[figure3(),transitions(),fixed_windows()]
    for d in drawings:
        name=d._chart_name;renderPDF.drawToFile(d,str(OUT/(name+'.pdf')));renderSVG.drawToFile(d,str(OUT/(name+'.svg')))
        if not args.vector_only:
            subprocess.run([rasterizer,'-r','250','-png','-singlefile',str(OUT/(name+'.pdf')),str(OUT/name)],check=True,capture_output=True)
            subprocess.run([rasterizer,'-r','600','-png','-singlefile',str(OUT/(name+'.pdf')),str(OUT/(name+'_600dpi'))],check=True,capture_output=True)
            from PIL import Image,ImageCms
            profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
            with Image.open(OUT/(name+'_600dpi.png')) as im:rgb=im.convert('RGB')
            rgb.save(OUT/(name+'_600dpi.png'),dpi=(600,600),icc_profile=profile)
            rgb.save(OUT/(name+'_600dpi.tiff'),compression='tiff_lzw',dpi=(600,600),icc_profile=profile)
        print('Rendered',name)
    outside=[r for r in TEXT_BOUNDS if r['x']<-.5 or r['x']+r['width']>r['page_width']+.5 or r['y']<1 or r['y']+r['font_size']>r['page_height']+1]
    (PROV/'text_geometry.json').write_text(json.dumps(dict(text_count=len(TEXT_BOUNDS),outside_page=outside,minimum_font_size=min(r['font_size'] for r in TEXT_BOUNDS),font=FONT,bounds=TEXT_BOUNDS),indent=2)+'\n')
    (PROV/'plotted_records.json').write_text(json.dumps(PLOT_RECORDS,indent=2)+'\n')
    (PROV/'software.json').write_text(json.dumps(dict(python=sys.version,executable=sys.executable,platform=platform.platform(),reportlab=reportlab.Version,Pillow=importlib.metadata.version('Pillow'),pypdf=importlib.metadata.version('pypdf'),font=FONT,pdftoppm=rasterizer,render_method='ReportLab vector graphics from exact aggregate counts; Poppler rasterization',no_inferential_statistics=True),indent=2)+'\n')
    if outside:raise SystemExit(f'{len(outside)} text items outside page; see text_geometry.json')
if __name__=='__main__':main()
