"""Read-only rendering of bilingual notes, captions and all figures to a PDF."""
from pathlib import Path
import re,sys,html
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Image
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
P=Path(__file__).resolve().parents[1]
def main():
 font=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
 if not font.exists():raise RuntimeError('Set local unicode font in render_supplement.py before PDF reproduction')
 pdfmetrics.registerFont(TTFont('ArialUnicode',str(font)))
 styles=getSampleStyleSheet();styles.add(ParagraphStyle('BodyCJK',fontName='ArialUnicode',fontSize=8,leading=12,wordWrap='CJK',spaceAfter=7));styles.add(ParagraphStyle('HeadCJK',fontName='ArialUnicode',fontSize=12,leading=17,spaceAfter=10));flow=[]
 def text(value):
  for raw in value.split('\n\n'):
   s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1',raw).replace('**','').replace('`','');head=s.startswith('#');s=s.lstrip('# ').replace('\n','<br/>');flow.append(Paragraph(html.escape(s).replace('&lt;br/&gt;','<br/>'),styles['HeadCJK' if head else 'BodyCJK']))
 text('# Scientific Influence v2.0\n\nSupplementary methods, evidence and figures / 补充说明与图表\n\nFull editable vector figures and per-panel data are supplied separately. This PDF is a reading copy; conditional intervals do not certify causal or measurement validity.')
 for f in sorted((P/'supplementary').glob('N_SI*.md')):flow.append(PageBreak());text(f.read_text())
 for level in ['main','extended','supplementary']:
  for f in sorted((P/'figures'/level).glob('*.png')):
   flow.append(PageBreak());text('# '+f.stem)
   from PIL import Image as PI
   with PI.open(f) as im:w,h=im.size
   scale=min(465/w,650/h);flow.append(Image(str(f),width=w*scale,height=h*scale));flow.append(Spacer(1,8));text('Source coordinates and counts: source_data/panels/. Full definitions: captions/captions_en.md and manuscript/methods_en.md. Conditional uncertainty; observed-network/roster measurement held fixed.')
 flow.append(PageBreak());text((P/'captions/captions_en.md').read_text())
 target=P/'supplementary/supplementary_v2.0.pdf';SimpleDocTemplate(str(target),pagesize=(595.276,841.89),leftMargin=48,rightMargin=48,topMargin=42,bottomMargin=42,title='Scientific Influence v2.0 supplementary evidence',author='Research analysis working materials').build(flow,canvasmaker=lambda *a,**kw:canvas.Canvas(*a,**(kw|{'initialFontName':'ArialUnicode'})))
 print('Supplementary PDF exported:',target,flush=True)
if __name__=='__main__':main()
