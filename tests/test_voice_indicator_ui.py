"""Compile and execute the real in-match microphone drawing and placement code."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]


def run(scenario):
    text = (ROOT / "czm/menu/CzmCombat.cpp").read_text()
    code = "\n".join(function(text, signature) for signature in (
        "static void FittedText(", "static CzmRect MicrophoneMeterRect(",
        "static void DrawMicrophoneIndicator(", "void CZM_DrawCombatControls()"))
    with tempfile.TemporaryDirectory(prefix="czm-mic-ui-") as folder:
        path = Path(folder)
        (path / "main.cpp").write_text(STUB + code + scenario)
        subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra",
                        "-I" + str(ROOT / "common"), str(path / "main.cpp"),
                        "-o", str(path / "check")], check=True)
        subprocess.run([str(path / "check")], check=True)


class VoiceIndicatorUiTests(unittest.TestCase):
    def test_pcm_level_silence_release_and_repeated_holds(self):
        run(r'''
int main(){
SetMic(700,500,760,560);Capture();assert(paints.empty());
floats["czm_voice_held"]=1;floats["czm_voice_recording"]=1;
for(int repeat=0;repeat<30;repeat++){
 floats["czm_voice_held"]=1;floats["czm_voice_level"]=0;Capture();
 assert(!paints.empty()&&LitBars()==0&&labels[0]=="Микрофон включён");
 floats["czm_voice_level"]=.5f;Capture();assert(LitBars()==6);
 floats["czm_voice_level"]=1;Capture();assert(LitBars()==12);
 floats["czm_voice_level"]=0;Capture();assert(LitBars()==0); // no stale waveform
 floats["czm_voice_held"]=0;Capture();assert(paints.empty()&&labels.empty());
}
return 0;}
''')

    def test_unavailable_capture_never_displays_a_voice_level(self):
        run(r'''
int main(){
SetMic(700,500,760,560);floats["czm_voice_held"]=1;
floats["czm_voice_level"]=1;floats["czm_voice_recording"]=0;Capture();
assert(LitBars()==0&&labels.size()==1&&labels[0]=="Микрофон недоступен");
assert(paints[0].kind=="image"&&paints[0].color==PackRGBA(255,153,103,80));
russian=false;Capture();assert(labels[0]=="Mic unavailable");
floats["czm_voice_recording"]=1;Capture();assert(labels[0]=="Microphone on"&&LitBars()==12);
assert(paints[0].color==PackRGBA(89,230,175,80));
floats["czm_voice_held"]=0;Capture();assert(paints.empty());
return 0;}
''')

    def test_meter_tracks_moved_button_and_stays_on_screen(self):
        run(r'''
int main(){
floats["czm_voice_held"]=floats["czm_voice_recording"]=1;floats["czm_voice_level"]=.8f;
for(auto size:std::vector<std::pair<int,int>>{{1536,716},{2400,1080},{1920,1200},{720,1280},{320,240},{64,40},{16,12},{2,2},{1,1}}){
 ScreenWidth=size.first;ScreenHeight=size.second;
 const int mw=Q_max(1,Q_min(60,ScreenWidth/8)),mh=Q_max(1,Q_min(60,ScreenHeight/8));
 for(int mx:{0,(ScreenWidth-mw)/2,ScreenWidth-mw})for(int my:{0,(ScreenHeight-mh)/2,ScreenHeight-mh}){
  SetMic(mx,my,mx+mw,my+mh);Capture();assert(!paints.empty());
  assert(paints[0].kind=="image"&&paints[0].rect.x==mx&&paints[0].rect.y==my);
  CzmRect frame=paints[1].rect;
  if(ScreenWidth>=64&&ScreenHeight>=40)
   assert(frame.x+frame.w<=mx||frame.x>=mx+mw||frame.y+frame.h<=my||frame.y>=my+mh);
 }
}
ScreenWidth=1536;ScreenHeight=716;
SetMic(700,500,760,560);Capture();CzmRect first=paints[1].rect;
SetMic(900,300,960,360);Capture();CzmRect moved=paints[1].rect;
assert(moved.x-first.x==200&&moved.y-first.y==-200);
SetMic(700,0,760,60);Capture();assert(paints[1].rect.y>=60); // top edge uses space below
SetMic(0,-50,60,50);Capture();assert(paints[0].rect.y==0&&paints[0].rect.h==50);
SetMic(100,0,160,716);Capture();assert(paints[1].rect.x>=160); // full-height button uses side
return 0;}
''')

    def test_visibility_lifecycle_and_old_ability_anchor_format(self):
        run(r'''
int main(){
SetMic(700,500,760,560);floats["czm_voice_held"]=floats["czm_voice_recording"]=1;
for(int state=0;state<3;state++){
 active=state!=0;uiStatic.menu.active=state==1;uiStatic.client.active=state==2;
 Capture();assert(paints.empty());
}
active=true;uiStatic.menu.active=uiStatic.client.active=false;Capture();assert(!paints.empty());
floats["czm_voice_held"]=0;Capture();assert(paints.empty());
SetMic(0,0,0,0);floats["czm_voice_held"]=1;Capture();assert(paints.empty());
values["czm_touch_anchors"]="malformed";Capture();assert(paints.empty());
values["czm_touch_anchors"]="100 100 160 160 0 0 0 0 0 0 0 0";
values["czm_skill_state"]="1 0 20 0 0 0";Capture();
assert(labels.size()==2&&labels[0]=="2"&&labels[1]=="Ускорение");
const size_t abilityPaints=paints.size();
values["czm_touch_anchors"]+=" 700 500 760 560";
floats["czm_voice_held"]=0;Capture();assert(paints.size()==abilityPaints&&labels.size()==2);
return 0;}
''')

    def test_invalid_and_out_of_range_levels_are_safely_bounded(self):
        run(r'''
int main(){
SetMic(700,500,760,560);floats["czm_voice_held"]=floats["czm_voice_recording"]=1;
for(float level:{-1.f,0.f,std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity()}){
 floats["czm_voice_level"]=level;Capture();assert(LitBars()==0);
}
floats["czm_voice_level"]=100;Capture();assert(LitBars()==12);
floats["czm_voice_held"]=std::numeric_limits<float>::quiet_NaN();Capture();assert(paints.empty());
return 0;}
''')


STUB = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <limits>
#include <map>
#include <string>
#include <vector>
#include "czm_combat.h"
#define UI_DIR "gfx/czm/ui/"
#define Q_max(a,b) ((a)>(b)?(a):(b))
#define Q_min(a,b) ((a)<(b)?(a):(b))
#define bound(lo,x,hi) ((x)<(lo)?(lo):(x)>(hi)?(hi):(x))
enum {CZMF_SMALL,CZMF_PANEL_TITLE,CZMF_TINY,QM_CENTER,QM_TOP,ETF_NO_WRAP,ETF_FORCECOL};
typedef int HFont;
int ScreenWidth=1536,ScreenHeight=716;bool active=true,russian=true;
struct Active{bool active=false;bool IsActive(){return active;}};
struct {Active menu,client;}uiStatic;
std::map<std::string,std::string> values;
std::map<std::string,float> floats;
namespace EngFuncs{
const char *GetCvarString(const char *name){return values[name].c_str();}
float GetCvarFloat(const char *name){return floats[name];}
}
bool CL_IsActive(){return active;}bool CZM_IsRussian(){return russian;}
unsigned PackRGBA(int r,int g,int b,int a){return (unsigned)r|((unsigned)g<<8)|((unsigned)b<<16)|((unsigned)a<<24);}
unsigned CZM_White(){return PackRGBA(255,255,255,255);}
struct CzmRect{int x,y,w,h;};
CzmRect CZM_Rect(int x,int y,int w,int h){return{x,y,w,h};}
struct Paint{std::string kind;CzmRect rect;unsigned color;};
std::vector<Paint> paints;std::vector<std::string>labels;
void PaintRect(const char *kind,int x,int y,int w,int h,unsigned color){
 assert(x>=0&&y>=0&&w>0&&h>0&&x+w<=ScreenWidth&&y+h<=ScreenHeight);
 paints.push_back({kind,{x,y,w,h},color});
}
void UI_FillRect(int x,int y,int w,int h,unsigned color){PaintRect("fill",x,y,w,h,color);}
void CZM_DrawImage(const char*,int x,int y,int w,int h,unsigned color){PaintRect("image",x,y,w,h,color);}
int CZM_Font(int id){return id;}int CZM_FontHeight(int){return 14;}
int CZM_TextWidth(int,const char *text){return strlen(text)*7;}
void UI_DrawString(int,int x,int y,int w,int h,const char *text,unsigned color,int,int,int){
 PaintRect("text",x,y,w,h,color);labels.push_back(text);
}
void CZM_DrawCombatControls();
void SetMic(int x1,int y1,int x2,int y2){
 char buffer[256];snprintf(buffer,sizeof(buffer),"0 0 0 0 0 0 0 0 0 0 0 0 %d %d %d %d",x1,y1,x2,y2);
 values["czm_touch_anchors"]=buffer;values["czm_skill_state"]="0 0 0 0 0 0";
}
void Capture(){paints.clear();labels.clear();CZM_DrawCombatControls();}
int LitBars(){int count=0;for(auto p:paints)if(p.kind=="fill"&&p.color==PackRGBA(89,230,175,255))count++;return count;}
'''


if __name__ == "__main__":
    unittest.main()
