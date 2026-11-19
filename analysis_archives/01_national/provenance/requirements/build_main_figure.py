from pathlib import Path
import csv
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String, Line, Polygon, Circle, Rect, Group
from reportlab.graphics import renderSVG
from reportlab.lib.colors import HexColor, Color, white

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "inputs/source_data"
def read(name):
    with (INPUT / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
def values(rows, field):
    return [float(r[field]) for r in rows]
a = sorted(read("Figure1b_upper.csv"), key=lambda r: int(r["year"]))
r = sorted(read("Figure1b_lower.csv"), key=lambda r: int(r["year"]))
m = sorted([v for v in read("Figure1c.csv") if v["spec"] == "count_composition"], key=lambda r: int(r["year"]))
years = values(a, "year")
assert years == [2021, 2022, 2023, 2024, 2025]
assert years == values(r, "year") == values(m, "year")
for ai, ri, mi in zip(a, r, m):
    assert int(ai["country_count"]) == 227 and int(mi["replicates"]) == 2000
    assert abs(float(ri["delta_gini"]) - float(ai["af_gini"]) + float(ai["comparator_gini"])) < 1e-12
    assert abs(float(mi["point"]) - float(mi["AF_gini"]) + float(mi["matched_non_AF_mean"])) < 1e-12
for rows, value, lo, hi in [(a,"af_gini","af_lower","af_upper"),(a,"comparator_gini","comparator_lower","comparator_upper"),(r,"delta_gini","delta_lower","delta_upper"),(m,"point","lower","upper")]:
    assert all(float(row[lo]) <= float(row[value]) <= float(row[hi]) for row in rows)

W, H = 183*72/25.4, 92*72/25.4
D = Drawing(W,H)
D.add(Rect(0,0,W,H,fillColor=white,strokeColor=None))
blue, orange, gray, purple = [HexColor(s) for s in ["#245C86","#C87425","#666A70","#8057A3"]]
font = "Helvetica"
plots=[]
def text(x,y,s,size=8,color=None,anchor="start",angle=0,bold=False):
    item=String(0 if angle else x,0 if angle else y,s,fontName="Helvetica-Bold" if bold else font,fontSize=size,fillColor=color or HexColor("#222222"),textAnchor=anchor)
    if angle:
        group=Group();group.add(item);group.translate(x,y);group.rotate(angle);D.add(group)
    else:D.add(item)
def panel(px, py, pw, ph, ymin, ymax, steps, data, colours, ylabel, letter):
    sx=lambda v:px+(v-2020.8)/(2025.2-2020.8)*pw
    sy=lambda v:py+(v-ymin)/(ymax-ymin)*ph
    lp=LinePlot();lp.x=px;lp.y=py;lp.width=pw;lp.height=ph;lp.data=data
    lp.xValueAxis.valueMin=2020.8;lp.xValueAxis.valueMax=2025.2;lp.xValueAxis.valueSteps=years;lp.xValueAxis.labelTextFormat="%d"
    lp.yValueAxis.valueMin=ymin;lp.yValueAxis.valueMax=ymax;lp.yValueAxis.valueSteps=steps;lp.yValueAxis.labelTextFormat="%.2f"
    for ax in [lp.xValueAxis,lp.yValueAxis]:
        ax.labels.fontName=font;ax.labels.fontSize=8;ax.strokeWidth=0.65
    lp.xValueAxis.tickDown=3;lp.xValueAxis.tickUp=0
    lp.yValueAxis.tickLeft=3;lp.yValueAxis.tickRight=0
    lp.yValueAxis.labels.dx=-5
    lp.lines.strokeWidth=1.25
    for i,col in enumerate(colours):lp.lines[i].strokeColor=col
    for val in steps:
        D.add(Line(px,sy(val),px+pw,sy(val),strokeColor=HexColor("#E6E6E6"),strokeWidth=0.45))
    text(px+pw/2,py-31,"Publication year",anchor="middle")
    text(px-36,py+ph/2,ylabel,anchor="middle",angle=90)
    text(px-33,py+ph+30,letter,size=10,bold=True)
    return lp,sx,sy

def band(sx,sy,low,high,col):
    coords=[]
    for x,y in zip(years,low):coords.extend([sx(x),sy(y)])
    for x,y in zip(reversed(years),reversed(high)):coords.extend([sx(x),sy(y)])
    D.add(Polygon(coords,fillColor=Color(col.red,col.green,col.blue,alpha=0.13),strokeColor=None))
def legend(x,y,label,col,shape="circle",dashed=False):
    D.add(Line(x,y+2,x+17,y+2,strokeColor=col,strokeWidth=1.3,strokeDashArray=[3,2] if dashed else None))
    if shape=="square":D.add(Rect(x+7,y,3.6,3.6,fillColor=col,strokeColor=col,strokeWidth=0.5))
    else:D.add(Circle(x+8.5,y+2,1.9,fillColor=col,strokeColor=col,strokeWidth=0.5))
    text(x+22,y-1,label)

pa,sxa,sya=panel(49,50,185,162,0.89,0.96,[0.90,0.92,0.94,0.96],[list(zip(years,values(a,"af_gini"))),list(zip(years,values(a,"comparator_gini")))],[blue,orange],"Gini coefficient","a")
band(sxa,sya,values(a,"af_lower"),values(a,"af_upper"),blue)
band(sxa,sya,values(a,"comparator_lower"),values(a,"comparator_upper"),orange)
D.add(pa)
for x,af,non in zip(years,values(a,"af_gini"),values(a,"comparator_gini")):
    D.add(Circle(sxa(x),sya(af),1.8,fillColor=blue,strokeColor=blue,strokeWidth=0.5))
    D.add(Rect(sxa(x)-1.7,sya(non)-1.7,3.4,3.4,fillColor=orange,strokeColor=orange,strokeWidth=0.5))
legend(49,232,"AF",blue);legend(110,232,"non-AF",orange,"square")
text(sxa(2021)+2,sya(values(a,"af_gini")[0])+9,"0.9421",color=blue)
text(sxa(2025)-1,sya(values(a,"af_gini")[-1])+9,"0.9253",color=blue,anchor="end")

pb,sxb,syb=panel(317,50,185,162,-0.003,0.055,[0,0.01,0.02,0.03,0.04,0.05],[list(zip(years,values(r,"delta_gini"))),list(zip(years,values(m,"point")))],[gray,purple],"Gini difference (AF - non-AF)","b")
pb.lines[1].strokeDashArray=[3,2]
band(sxb,syb,values(r,"delta_lower"),values(r,"delta_upper"),gray)
D.add(pb)
D.add(Line(317,syb(0),502,syb(0),strokeColor=HexColor("#777777"),strokeWidth=0.7,strokeDashArray=[3,3]))
for x,raw,mat,lo,hi in zip(years,values(r,"delta_gini"),values(m,"point"),values(m,"lower"),values(m,"upper")):
    D.add(Circle(sxb(x),syb(raw),1.8,fillColor=gray,strokeColor=gray,strokeWidth=0.5))
    D.add(Line(sxb(x),syb(lo),sxb(x),syb(hi),strokeColor=purple,strokeWidth=0.8))
    for end in [lo,hi]:D.add(Line(sxb(x)-2,syb(end),sxb(x)+2,syb(end),strokeColor=purple,strokeWidth=0.8))
    D.add(Circle(sxb(x),syb(mat),1.8,fillColor=purple,strokeColor=purple,strokeWidth=0.5))
legend(317,232,"Raw gap",gray);legend(405,232,"Matched gap",purple,dashed=True)
text(sxb(2021)+3,syb(values(r,"delta_gini")[0])-13,"0.0415",color=gray)
text(sxb(2021)+3,syb(values(m,"point")[0])-14,"0.0168",color=purple)
text(sxb(2025)-1,syb(values(r,"delta_gini")[-1])+8,"0.0271",color=gray,anchor="end")
text(sxb(2025)-1,syb(values(m,"point")[-1])-14,"0.0194",color=purple,anchor="end")
renderSVG.drawToFile(D,str(ROOT/"Figure1_two_panel.svg"))
print("SVG rendered from frozen empirical summaries using ReportLab LinePlot; no re-estimation.")
