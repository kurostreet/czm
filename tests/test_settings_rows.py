"""Exercise the settings tab layout, last-row drawing and actual hit targets."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]


class SettingsRowsTests(unittest.TestCase):
    def test_last_game_setting_is_visible_and_all_three_choices_can_be_selected(self):
        source = Path(os.environ.get("CZM_SETTINGS_SOURCE", ROOT / "czm/menu/CzmSettings.cpp")).read_text()
        rows = source[source.index("enum ERowType"):source.index("void FillClipped(")]
        # The row definitions and sizing are production code; unrelated cvar
        # bindings are inert so this test runs without launching the engine.
        getters = set(re.findall(r"\b(Get\w+)\b", rows)) - {"GetDiagnostics"}
        setters = set(re.findall(r"\b(Set\w+)\b", rows)) - {"SetDiagnostics"}
        active = {"GyroAvailable", "GyroOn", "VoiceOn", "MicTestAvailable"}
        bindings = "\n".join("float %s(){return 0;}" % name for name in sorted(getters))
        bindings += "\n" + "\n".join("void %s(float){}" % name for name in sorted(setters))
        bindings += "\n" + "\n".join("bool %s(){return true;}" % name for name in sorted(active))
        bindings += "\n" + function(source, "float GetDiagnostics( void )")
        bindings += "\n" + function(source, "void SetDiagnostics( float v )")
        row_layout = source[source.index("\tstruct RowLayout"):source.index("\n\tvoid Layout(")]
        hit_enum = source[source.index("\tenum\n", source.index("class CCzmSettings")):source.index("\n\tstruct RowLayout")]
        draw = function(source, "void CCzmSettings::Draw()")
        draw = draw[:draw.index("\n\t// short notice")] + "\n}"
        program = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define UI_DIR "gfx/czm/ui/"
using HFont=int;
enum {CZM_TAB_CONTROLS,CZM_TAB_GRAPHICS,CZM_TAB_SOUND,CZM_TAB_GAME,CZM_TAB_HUD,CZM_TAB_PROFILE,CZM_TAB_ABOUT,CZM_TAB_COUNT};
#define CZM_CONTACT_URL "mailto:x"
#define CZM_GROUP_URL "https://t.me/x"
#define CZM_SITE_URL "https://x"
#define CZM_SOURCE_URL "https://github.com/x"
static int opened,rulesShown,consoles;
void CZM_RulesShow(){rulesShown++;}void CZM_OpenConsole(){consoles++;}
enum {CZMF_TILE_STATUS,CZMF_PANEL_TITLE,CZMF_SMALL,QM_CENTER=1,QM_TOP=2,ETF_NO_WRAP=4,ETF_FORCECOL=8};
const int CZM_XHAIR_COLORS=5,CZM_AVATAR_PHOTO=10,CZM_AVATAR_LOGO=11;
int ScreenWidth=1536,ScreenHeight=716,mode=1,changes=0,saves=0;
struct {int cursorX,cursorY,realTime;} uiStatic;
template<class T>T Q_min(T a,T b){return std::min(a,b);}template<class T>T Q_max(T a,T b){return std::max(a,b);}
struct CzmRect{int x=0,y=0,w=0,h=0;
 bool Contains(int px,int py)const{return px>=x&&px<x+w&&py>=y&&py<y+h;}
 bool HasCursor()const{return Contains(uiStatic.cursorX,uiStatic.cursorY);}
 CzmRect Grown(int d)const;
};
CzmRect CZM_Rect(int x,int y,int w,int h){CzmRect r;r.x=x;r.y=y;r.w=w;r.h=h;return r;}
CzmRect CzmRect::Grown(int d)const{return CZM_Rect(x-d,y-d,w+2*d,h+2*d);}
struct EngFuncs{static float GetCvarFloat(const char*){return 0;}static const char*GetCvarString(const char*){return "test";}
 static void ShellExecute(const char*,const char*,bool){opened++;}static double DoubleTime(){return 100;}
 static void CvarSetString(const char*,const char*){}static void ClientCmd(bool,const char*){saves++;}};
int CZM_DiagnosticsMode(){return mode;}void CZM_SetDiagnosticsMode(int v){mode=v;changes++;saves++;}
bool CZM_ColorPickerEvent(int&,int&,int&){return false;}bool CL_IsActive(){return false;}
int CZM_SprayCount(){return 5;}int AvatarCards(){return 12;}
void CZM_PlayClick(){}void CZM_SetTouchScheme(int,bool){}int CZM_TouchScheme(){return 1;}void CZM_TouchResetHud(){}
void CZM_OpenTouchEditor(){}void CZM_LayoutsShow(){}const char*CZM_OnlineKey(){return "test";}
void CZM_AccountShow(const char*,const char*){}void CZM_SetSpray(int){}void CZM_SetAvatar(int){}
void CZM_OnlineAvatarChanged(){}const char*CZM_AvatarPhoto(){return "";}int CZM_CurrentAvatar(){return 0;}void CZM_PickAvatarPhoto(){}
void CZM_CleanName(const char*in,char*out,size_t n){snprintf(out,n,"%s",in);}bool CZM_NickIsValid(const char*){return true;}
void CZM_ColorPickerShow(int,int,int){}
bool CZM_RulesAllow(void(*)()){return true;}void ChoosePhoto(){}
enum{CZM_LIMIT_TEXT,CZM_LIMIT_VOICE,CZM_LIMIT_PHOTO};static bool photoLimited;static int notices;
bool CZM_OnlineLimited(int k,char*t=nullptr,size_t n=0){if(k!=CZM_LIMIT_PHOTO||!photoLimited)return false;if(t&&n)snprintf(t,n,"%s","photo limited");return true;}
bool CZM_IsRussian(){return true;}void CZM_ShowNotice(const char*,const char*,const char* ="",bool=false){notices++;}
unsigned PackRGBA(int,int,int,int){return 0;}unsigned CZM_White(int=255){return 0;}unsigned CZM_Grey(){return 0;}
HFont CZM_Font(int n){return n;}int CZM_FontHeight(HFont){return ScreenHeight*.026f;}
int CZM_TextWidth(HFont,const char*s){return strlen(s)*ScreenHeight*.014f;}
const char*CZM_T(const char*s){return s;}
void UI_FillRect(int,int,int,int,unsigned){}void CZM_DrawImage(const char*,int,int,int,int,unsigned=0){}
std::vector<std::string> labels;
void CZM_DrawText(HFont,int,int,int,const char*s,unsigned,int=0){labels.emplace_back(s);}
void UI_DrawString(HFont,int,int,int,int,const char*s,unsigned,int,int,int){labels.emplace_back(s);}
void CZM_DrawPanel(const CzmRect&){}void CZM_DrawPill(const char*,int,int,int,int,unsigned=0){}
namespace UI{namespace Scissor{void PushScissor(int,int,int,int){}void PopScissor(){}}}
struct Edit{void End(){}void Begin(const char*,const CzmRect&){};} ;
''' + bindings + rows + r'''
class CCzmSettings{public:
''' + hit_enum + row_layout + r'''
 int m_iTab=CZM_TAB_GAME,m_iScroll=0,m_iMaxScroll=0,m_iPressed=0,m_iMicPing=0,m_iVersionTaps=0;double m_flVersionTap=0;
 bool m_bConfirm=false,m_bMicTest=false,m_bMicHeard=false;
 int W=0,H=0;CzmRect m_back,m_tabs[CZM_TAB_COUNT],m_panel,m_clip,m_confirmPanel,m_confirmNo,m_confirmYes;
 RowLayout m_rows[MAX_ROWS];Edit m_nick;std::vector<int> drawn;
 const CzmRow&Row(int i)const{return s_tabs[m_iTab].rows[i];}int RowCount()const{return s_tabs[m_iTab].count;}
 bool RowActive(int i)const{return !Row(i).active||Row(i).active();}
 bool IsPressed(int)const{return false;}void Toast(const char*){}void Hide(){}void OpenTab(int t){m_iTab=t;m_iScroll=0;}void StopMicTest(){}void Save(){saves++;}
 void Layout();int HitTest()const;void Activate(int);void Draw();void DrawChoice(int,const RowLayout&);
 void DrawTabs(){}void DrawRow(int i){drawn.push_back(i);if(Row(i).type==ROW_CHOICE)DrawChoice(i,m_rows[i]);}
};
''' + function(source, "static void CardGrid(") + "\n" + function(source, "void CCzmSettings::Layout(")
        program += "\n" + function(source, "int CCzmSettings::HitTest(")
        program += "\n" + function(source, "void CCzmSettings::Activate(")
        program += "\n" + function(source, "void CCzmSettings::DrawChoice(") + "\n" + draw
        program += r'''
int main(){
 for(auto size:{std::pair<int,int>{1536,716},{960,540},{1024,768},{1280,720},{640,360}}){
  ScreenWidth=size.first;ScreenHeight=size.second;CCzmSettings w;w.Layout();
  // Every tab has enough storage and lays out every last row.
  for(int tab=0;tab<CZM_TAB_COUNT;tab++){
   w.OpenTab(tab);assert(w.RowCount()<=MAX_ROWS);w.Layout();
   assert(w.m_rows[w.RowCount()-1].rect.h>0);
  }
  w.OpenTab(CZM_TAB_GAME);w.Layout();
  int last=w.RowCount()-1;assert(!strcmp(w.Row(last).label,"s_diagnostics"));
  assert(w.m_iMaxScroll>0);w.m_iScroll=w.m_iMaxScroll;w.Draw();
  assert(std::find(w.drawn.begin(),w.drawn.end(),last)!=w.drawn.end());
  const auto&r=w.m_rows[last];assert(r.numParts==3);
  assert(r.rect.y>=w.m_clip.y&&r.rect.y+r.rect.h<=w.m_clip.y+w.m_clip.h);
  for(int choice=0;choice<3;choice++){
   assert(std::find(labels.begin(),labels.end(),w.Row(last).options[choice])!=labels.end());
   const auto&p=r.parts[choice];assert(p.w>0&&p.h>0);
   assert(p.y>=w.m_clip.y&&p.y+p.h<=w.m_clip.y+w.m_clip.h);
   uiStatic.cursorX=p.x+p.w/2;uiStatic.cursorY=p.y+p.h/2;
   int hit=w.HitTest();assert(hit==w.HIT_ROW+last*20+1+choice);
   int before=changes,priorSaves=saves;w.Activate(hit);
   assert(mode==choice&&changes==before+1&&saves==priorSaves+1);
  }
 }
 // About: links open, the rules show, five taps on the version open the console, the rest is text
 {
  ScreenWidth=1536;ScreenHeight=716;CCzmSettings w;w.OpenTab(CZM_TAB_ABOUT);w.Layout();assert(w.RowCount()==8);
  for(int i=0;i<w.RowCount();i++){
   const auto&r=w.m_rows[i];assert(r.rect.h>0&&r.rect.y>=w.m_clip.y&&r.rect.y+r.rect.h<=w.m_clip.y+w.m_clip.h);
   uiStatic.cursorX=r.rect.x+r.rect.w/2;uiStatic.cursorY=r.rect.y+r.rect.h/2;
   const int hit=w.HitTest();
   if(i>5){assert(hit==w.HIT_NONE);continue;}
   assert(hit==w.HIT_ROW+i*20);
   for(int tap=0;tap<(i==5?5:1);tap++)w.Activate(hit);
  }
  assert(opened==4&&rulesShown==1&&consoles==1);
 }
 puts("SETTINGS_LAST_ROW_VISIBLE_AND_SELECTABLE_OK");
}
'''
        with tempfile.TemporaryDirectory(prefix="czm-settings-rows-") as temporary:
            path = Path(temporary)
            (path / "main.cpp").write_text(program)
            exe = path / "settings-rows"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", str(path / "main.cpp"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    unittest.main()
