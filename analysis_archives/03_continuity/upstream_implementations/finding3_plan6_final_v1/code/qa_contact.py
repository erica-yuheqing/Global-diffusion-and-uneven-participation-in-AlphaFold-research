"""QA contact sheet of actual saved supplementary previews."""
from common import OUT
from PIL import Image,ImageDraw
paths=[next((OUT/'figures'/f'S{i}').glob('*_preview.png')) for i in range(1,8)]
page=Image.new('RGB',(1650,1500),'white');draw=ImageDraw.Draw(page)
for i,p in enumerate(paths):
    with Image.open(p) as image:
        thumb=image.convert('RGB');thumb.thumbnail((530,450))
    x=(i%3)*550;y=(i//3)*500
    draw.text((x+8,y+5),f'S{i+1}',fill='black');page.paste(thumb,(x+(550-thumb.width)//2,y+25))
page.save(OUT/'provenance/supplementary_contact.png')
