"""Build the HUD's own Inter glyph atlas; Inter is shipped under its OFL."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
font=ImageFont.truetype(str(ROOT/'3rdparty/czm_project/gfx/fonts/czm/InterDisplay-Bold.otf'),44)
image=Image.new('RGBA',(1024,256))
draw=ImageDraw.Draw(image)
for i in range(64):
    ch=chr(32+i)
    x=(i%16)*64+32;y=(i//16)*64+32
    draw.text((x,y),ch,font=font,anchor='mm',fill='white')
image.save(ROOT/'3rdparty/czm_project/gfx/czm/hud_glyphs.tga',compression="tga_rle")
