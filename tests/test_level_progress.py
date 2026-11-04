"""Progress and tokens fit the HUD at all editor positions, scales and supported screen shapes."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include "czm_hud_overlay.h"
#include "czm_aim.h"
#include <cassert>
#include <algorithm>
#include <cmath>
#include <climits>
#include <initializer_list>
static float SW,SH;
static void Inside(float x,float y,float w,float h){assert(std::isfinite(x+y+w+h)&&w>=0&&h>=0&&x>=-1&&y>=-1&&x+w<=SW+1&&y+h<=SH+1);}
struct Check:CzmHud::Canvas {
 int lh;float glyphBottom=-1,barBottom=-1;Check(int h):lh(h){}
 void Blend(int x,int y,int w,int h,int r,int g,int b,int a)override{
  assert(a>=0&&a<=255);Inside(x,y,w,h);
  if(r==255&&g==255&&b==255){assert(glyphBottom<y);barBottom=y+h;}
 }
 void Glyphs(float x,float y,float h,const char *s,int,int,int,float)override{assert(h>0);Inside(x,y,CzmHud::GlyphWidth(s,h),h);glyphBottom=std::max(glyphBottom,y+h);}
 int LabelWidth(const char *s)override{int n=0;for(;*s;s++)if((*s&0xc0)!=0x80)n++;return n*lh/2;}
 int LabelHeight()override{return lh;}
 void Label(int x,int y,const char *s,int,int,int)override{assert(y>barBottom);Inside(x,y,LabelWidth(s),lh);}
 bool Avatar(int,int,int)override{return false;}
};
int main(){
 CzmHud::ProgressInfo normal={0,0,3,10,240,600};
 assert(fabs(CzmHud::ProgressFraction(normal)-.7f)<.001f);
 normal.killsLeft=10;assert(fabs(CzmHud::ProgressFraction(normal)-.6f)<.001f);
 CzmHud::ProgressInfo missing={0,0,0,0,0,0};assert(CzmHud::ProgressFraction(missing)==0);
 const float screens[][2]={{640,360},{1536,716},{2340,1080},{1024,768},{2000,1200}};
 const float places[]={-1,0,.5f,1,4,NAN},scales[]={0,.65f,1,1.6f,8,NAN};
 const CzmHud::ProgressInfo states[]={normal,missing,{INT_MAX,INT_MAX,10,10,600,600},{37,1000,-100,10,-1,600}};
 for(auto &screen:screens)for(float x:places)for(float scale:scales)for(int lh:{8,18,26,40})for(auto &state:states){
   SW=screen[0];SH=screen[1];Check c(lh);
   auto p=CzmHud::ProgressLayout(SW,SH,x,x,scale,.25f,lh);
   Inside(p.x,p.y,p.w,p.h);
   CzmHud::PaintProgress(c,p,state,true,0,255,255);
   CzmHud::PaintProgress(c,p,state,false,0,255,255);
 }
}
'''


class LevelProgressTests(unittest.TestCase):
    def test_client_receives_balance_and_progress_and_clears_them_on_reconnect(self):
        source = (ROOT/'cl_dll/hud/czm_tags.cpp').read_text()
        code = r'''
#include "czm_hud_overlay.h"
#include "czm_aim.h"
#include <cassert>
#include <algorithm>
#include <cstdint>
#define MAX_PLAYERS 32
static CzmHud::ProgressInfo s_progress;
static int s_tags[33],s_toasts[3];static bool s_have[33],s_aimShown,s_aimReceived;
static CzmAim::Target s_aim;
struct BufferReader {
 const unsigned char *p;
 BufferReader(const char *,void *buf,int):p((const unsigned char *)buf){}
 int32_t ReadLong(){int32_t n;memcpy(&n,p,4);p+=4;return n;}
};
'''
        code += function(source,'static int MsgFunc_CzmProgress(')
        code += function(source,'void CZM_TagsReset(')
        code += r'''
int main(){
 CZM_TagsReset();assert(s_progress.level<0);
 int32_t packet[]={37,123456789,3,10,240,600};
 MsgFunc_CzmProgress("CzmProgress",sizeof(packet),packet);
 assert(s_progress.level==37&&s_progress.tokens==123456789&&s_progress.killsLeft==3&&s_progress.killsStep==10);
 assert(s_progress.secondsLeft==240&&s_progress.secondsStep==600);
 packet[0]=0;MsgFunc_CzmProgress("CzmProgress",sizeof(packet),packet);assert(s_progress.level==0);
 packet[0]=99;MsgFunc_CzmProgress("CzmProgress",sizeof(packet)-1,packet);assert(s_progress.level==0);
 s_aimShown=true;CZM_TagsReset();assert(s_progress.level<0&&s_progress.tokens==0&&!s_aimShown);
}
'''
        with tempfile.TemporaryDirectory(prefix='czm-progress-wire-') as folder:
            path=Path(folder)
            (path/'check.cpp').write_text(code)
            subprocess.run(['g++','-std=c++11','-Wall','-I'+str(ROOT/'common'),str(path/'check.cpp'),'-o',str(path/'check')],check=True)
            subprocess.run([str(path/'check')],check=True)

    def test_progress_policy_and_paint_stay_inside_the_editor_block(self):
        with tempfile.TemporaryDirectory(prefix='czm-progress-') as folder:
            path = Path(folder)
            (path/'check.cpp').write_text(HARNESS)
            subprocess.run(['g++','-std=c++11','-Wall','-Wextra','-Werror','-I'+str(ROOT/'common'),str(path/'check.cpp'),'-o',str(path/'check')],check=True)
            subprocess.run([str(path/'check')],check=True)
