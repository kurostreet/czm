"""Execute the actual HUD painter and inspect geometry, including extreme values."""
from pathlib import Path
import os,shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
STUB=r'''
#pragma once
#include <cstdio>
#define TF_NOMIPMAP 1
#define TF_CLAMP 2
#define kRenderTransAlpha 1
#define TRI_QUADS 4
struct Hud {float m_flScale;};extern Hud gHUD;
extern int ScreenWidth,ScreenHeight,g_iXash;
struct Tri {void (*RenderMode)(int);void (*Color4f)(float,float,float,float);void (*Begin)(int);void (*TexCoord2f)(float,float);void (*Vertex3f)(float,float,float);void (*End)();};
struct Engine {float (*pfnGetCvarFloat)(const char *);const char *(*pfnGetCvarString)(const char *);Tri *pTriAPI;};extern Engine gEngfuncs;
struct Render {int (*GL_LoadTexture)(const char *,void *,int,int);void (*GL_SelectTexture)(int);void (*GL_Bind)(int,int);};extern Render gRenderAPI;
void FillRGBA(int,int,int,int,int,int,int,int);void FillRGBABlend(int,int,int,int,int,int,int,int);
'''
HARNESS=r'''
#include "hud.h"
#include "czm_hud.h"
#include <cstdlib>
#include <cstring>
#include <cmath>
Hud gHUD={1};int ScreenWidth,ScreenHeight,g_iXash=1,style;float requested=1;
void CZM_RadarVidInit(){}void CZM_AmmoReset(){}
float Float(const char *s){if(!strcmp(s,"czm_hud_style"))return style; if(strstr(s,"_hidden"))return 0; if(strstr(s,"_scale"))return requested;if(strstr(s,"_opacity"))return 1;int k=0;for(;k<CzmHud::COUNT;k++)if(strstr(s,CzmHud::keys[k]))break;if(k==CzmHud::COUNT)return 0;return CzmHud::defaults[k][strstr(s,"_y")?1:0];}
const char *String(const char *){return "1";}
void Mode(int){}void Color(float r,float g,float b,float a){printf("C %f %f %f %f\n",r,g,b,a);}void Begin(int){}void UV(float u,float v){printf("U %f %f\n",u,v);}void Vertex(float x,float y,float){printf("V %f %f\n",x,y);}void End(){puts("E");}
Tri tri={Mode,Color,Begin,UV,Vertex,End};Engine gEngfuncs={Float,String,&tri};
int Load(const char *,void *,int,int){return 1;}void Select(int){}void Bind(int,int){}Render gRenderAPI={Load,Select,Bind};
void FillRGBA(int x,int y,int w,int h,int r,int g,int b,int a){printf("R %d %d %d %d %d %d %d %d\n",x,y,w,h,r,g,b,a);}void FillRGBABlend(int x,int y,int w,int h,int r,int g,int b,int a){FillRGBA(x,y,w,h,r,g,b,a);}
int main(int argc,char **argv){style=atoi(argv[1]);ScreenWidth=atoi(argv[2]);ScreenHeight=atoi(argv[3]);requested=atof(argv[4]);CZM_HudVidInit();
 const char *values[]={"2904","100","2:38","16000","30 / 90"};for(int i=0;i<5;i++)CZM_HudDraw(i,argc>5?argv[5]:values[i],i==0&&argc>5);return 0;}
'''
class GameHudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('g++'):raise unittest.SkipTest('g++ required')
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        (cls.root/'hud.h').write_text(STUB)
        for name in ['cl_util.h','draw_util.h','triangleapi.h']:(cls.root/name).write_text('')
        (cls.root/'main.cpp').write_text(HARNESS);cls.exe=cls.root/'hud'
        subprocess.run(['g++','-std=c++11','-I'+str(cls.root),'-I'+str(ROOT/'cl_dll/hud'),str(cls.root/'main.cpp'),str(ROOT/'cl_dll/hud/czm_hud.cpp'),'-o',str(cls.exe)],check=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def render(self,style,w,h,scale,value=None):
        args=[str(self.exe),str(style),str(w),str(h),str(scale)]+([] if value is None else [value])
        return subprocess.check_output(args,text=True).splitlines()
    def test_all_styles_fit_screens_and_extreme_health(self):
        import math
        for style in range(3):
            for w,h in [(640,360),(1280,720),(2340,1080),(2400,1080)]:
                for size in [.65,1,1.6,100,float('nan')]:
                    for value in ['0','2904','2147483647','30 / 90 + 10']:
                        with self.subTest(style=style,w=w,size=size,value=value):
                            for line in self.render(style,w,h,size,value):
                                p=line.split()
                                if p[0]=='R':
                                    x,y,rw,rh=map(int,p[1:5]);self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0);self.assertLessEqual(x+rw,w+1);self.assertLessEqual(y+rh,h+1)
                                elif p[0]=='V':
                                    x,y=map(float,p[1:3]);self.assertTrue(math.isfinite(x+y));self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0);self.assertLessEqual(x,w+1);self.assertLessEqual(y,h+1)
    def test_optional_rendered_previews(self):
        folder=os.environ.get('CZM_HUD_PREVIEW_DIR')
        if not folder:return
        from PIL import Image,ImageDraw
        target=Path(folder);target.mkdir(parents=True,exist_ok=True);atlas=Image.open(ROOT/'3rdparty/cs16client-extras/gfx/czm/hud_glyphs.tga').convert('RGBA')
        for style in range(3):
            canvas=Image.new('RGBA',(1280,720),(32,42,52,255));color=(1,1,1,1);vertices=[];uv=[]
            for line in self.render(style,1280,720,1):
                p=line.split()
                if p[0]=='R':
                    x,y,w,h,r,g,b,a=map(int,p[1:]);layer=Image.new('RGBA',canvas.size);ImageDraw.Draw(layer).rectangle((x,y,x+w,y+h),fill=(r,g,b,a));canvas=Image.alpha_composite(canvas,layer)
                elif p[0]=='C':color=tuple(map(float,p[1:]))
                elif p[0]=='U':uv.append(tuple(map(float,p[1:])))
                elif p[0]=='V':vertices.append(tuple(map(float,p[1:])))
                elif p[0]=='E':
                    x,y=vertices[0];x2,y2=vertices[2];u,v=uv[0];u2,v2=uv[2];glyph=atlas.crop((round(u*1024),round(v*256),round(u2*1024),round(v2*256))).resize((max(1,round(x2-x)),max(1,round(y2-y))),Image.Resampling.LANCZOS);channels=list(glyph.split());channels=[channels[i].point(lambda x,c=color[i]:round(x*c)) for i in range(4)];glyph=Image.merge('RGBA',channels);canvas.alpha_composite(glyph,(round(x),round(y)));vertices=[];uv=[]
            canvas.convert('RGB').save(target/f'hud-{style}.png')
if __name__=='__main__':unittest.main()
