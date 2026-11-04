#!/usr/bin/env python3
"""Rebuild scalable graphite weapon cards and orange selection borders."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter
import random,sys
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'3rdparty/czm_project/gfx/czm/shop'

def frame(name,selected=False,button=False):
 w,h,cut=(640,128,25) if button else (640,360,28)
 points=[(cut,9),(w-cut-9,9),(w-9,cut),(w-9,h-cut-9),(w-cut-9,h-9),(9+cut,h-9),(9,h-cut-9),(9,cut)]
 mask=Image.new('L',(w,h));ImageDraw.Draw(mask).polygon(points,fill=255)
 rng=random.Random(47);base=Image.new('RGBA',(w,h));pixels=base.load()
 for y in range(h):
  for x in range(w):
   noise=rng.randrange(5);light=max(0,1-abs(x/w-.55)*1.5)*5;v=int(19+light+8*(1-y/h)+noise)
   warm=max(0,(y/h-.55)/.45)*(36 if selected else 3)
   pixels[x,y]=(int(v+warm),int(v+1+warm*.3),int(v+5),255)
 base.putalpha(mask);edge=Image.new('RGBA',(w,h));d=ImageDraw.Draw(edge)
 d.line(points+[points[0]],fill=(255,143,43,255) if selected else (123,135,151,175),width=3 if selected else 2)
 d.line([(cut+3,12),(w-cut-9,12)],fill=(255,224,177,240) if selected else (187,198,211,95),width=1)
 if not button:
  d.polygon([(cut+10,h-66),(w-125,h-66),(w-176,h-10),(cut+10,h-10)],fill=(0,0,0,40))
  for i in range(3):
   x=cut+12+i*12;d.polygon([(x+10,h-48),(x+16,h-48),(x+4,h-24),(x-2,h-24)],fill=(255,151,45,245))
  d.line([(w-177,h-12),(w-126,h-65),(w-12,h-65)],fill=(149,160,176,85),width=1)
 if selected:base=Image.alpha_composite(edge.filter(ImageFilter.GaussianBlur(7)),base)
 Image.alpha_composite(base,edge).save(OUT/name,optimize=True)
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True)
 frame('arsenal_card.png');frame('arsenal_selected.png',True);frame('arsenal_button.png',button=True);frame('arsenal_button_on.png',True,True)
