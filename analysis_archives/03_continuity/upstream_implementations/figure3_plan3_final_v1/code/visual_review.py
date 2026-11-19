"""Local contact sheets for reviewing every new Extended Data display."""
from PIL import Image,ImageDraw
from support import *

def run(out):
    previews=sorted((out/'figures/extended_data').glob('*_preview.png'))
    for page,start in enumerate(range(0,len(previews),3),1):
        pieces=[]
        for p in previews[start:start+3]:
            with Image.open(p) as im:
                picture=im.convert('RGB');picture.thumbnail((1300,800))
                piece=Image.new('RGB',(1340,picture.height+45),'white')
                ImageDraw.Draw(piece).text((15,10),p.stem,fill='black')
                piece.paste(picture,((1340-picture.width)//2,35));pieces.append(piece)
        contact=Image.new('RGB',(1340,sum(p.height for p in pieces)),'white');y=0
        for p in pieces:contact.paste(p,(0,y));y+=p.height
        contact.save(out/'provenance'/f'visual_review_sheet_{page}.png')

if __name__=='__main__':run(OUT)
