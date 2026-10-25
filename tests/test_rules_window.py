"""Run the native community rules window: layout, the agreement, the request and what follows it."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_lobby_menu import STUB as LOBBY_STUB
from test_tab_avatars import VECTOR, STRING
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
STUB = LOBBY_STUB.replace('unsigned CZM_White();', 'unsigned CZM_White(int=255);')
STUB = STUB.replace('static double DoubleTime();', 'static double DoubleTime();static void ShellExecute(const char*,const char*,bool);')
STUB += r'''
void CZM_WrapLine(const char*,const int*,int,char*,size_t);
void CZM_RulesSetState(int,bool,const char*);bool CZM_RulesAccepted();bool CZM_RulesConfirmed();void CZM_RulesFrame();
'''
HARNESS = r'''
#include "stub.h"
#include <map>
#include <cassert>
int ScreenWidth=1536,ScreenHeight=716,cursorX,cursorY;Cursor uiStatic;Stack stack;
static bool russian=true,trace=false;static int nextRequest,thenCalls;static double now=100;
static std::string lastUrl,lastBody,lastKey,opened;static std::map<int,std::pair<int,std::string>> replies;
static std::map<std::string,std::string> vars;
HFont CZM_Font(int id){return id;}
int CZM_FontHeight(HFont f){int h=f==CZMF_PANEL_TITLE?42:f==CZMF_UI_LABEL?20:f==CZMF_SMALL?17:21;return std::max(1,h*ScreenHeight/768);}
int CZM_TextWidth(HFont f,const char*s){int n=0;for(;*s;s++)if((*s&0xc0)!=0x80)n++;return n*CZM_FontHeight(f)*56/100;}
void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){if(trace)printf("T\t%d\t%d\t%d\t%d\t%u\t%u\t%s\n",x,y,w,CZM_FontHeight(f),c,just,s);}
void UI_FillRect(int x,int y,int w,int h,unsigned c){assert(w>=0&&h>=0);if(trace)printf("R\t%d\t%d\t%d\t%d\t%u\n",x,y,w,h,c);}
void CZM_DrawSliced(const char*,int x,int y,int w,int h,int,int radius,unsigned c){assert(w>=0&&h>=0);if(trace)printf("S\t%d\t%d\t%d\t%d\t%u\t%d\n",x,y,w,h,c,radius);}
void CZM_DrawImage(const char*p,int x,int y,int w,int h,unsigned c){assert(w>=0&&h>=0);if(trace)printf("I\t%d\t%d\t%d\t%d\t%u\t%s\n",x,y,w,h,c,p);}
void CZM_DrawPill(const char*p,int x,int y,int w,int h,unsigned c){CZM_DrawImage(p,x,y,w,h,c);}
void CZM_DrawCover(HIMAGE,int,int,int,int){}HIMAGE CZM_MapPreview(const char*){return 0;}HIMAGE CZM_Image(const char*){return 0;}
const char*CZM_MapModeArt(const char*,const char*){return "";}
void CZM_DrawPanel(const CzmRect&r){CZM_DrawSliced("panel",r.x,r.y,r.w,r.h,0,0,PackRGBA(12,18,27,250));}
void CZM_DrawButton(const char*,const CzmRect&,const char*,unsigned,bool,int){}
void CZM_Init(){}bool CZM_IsRussian(){return russian;}unsigned CZM_White(int a){return PackRGBA(255,255,255,a);}unsigned CZM_Grey(){return PackRGBA(155,166,184,255);}
const char*EngFuncs::GetCvarString(const char*k){return vars[k].c_str();}float EngFuncs::GetCvarFloat(const char*k){return atof(GetCvarString(k));}
void EngFuncs::CvarSetString(const char*k,const char*v){vars[k]=v;}void EngFuncs::CvarSetValue(const char*k,float v){vars[k]=std::to_string(v);}double EngFuncs::DoubleTime(){return now;}
void EngFuncs::ShellExecute(const char*url,const char*,bool){opened=url;}
static std::string key="player-session-key";
const char*CZM_OnlineKey(){return key.c_str();}const char*CZM_OnlineUrl(const char*p){return p;}
int CZM_NetRequest(const char*,const char*url,const char*k,const char*body){lastUrl=url;lastKey=k;lastBody=body;return ++nextRequest;}
bool CZM_NetPoll(int id,int*status,CUtlString&body){auto it=replies.find(id);if(it==replies.end())return false;*status=it->second.first;body.Set(it->second.second.c_str());replies.erase(it);return true;}
void CZM_PlayClick(){}
static void then(){thenCalls++;}
'''
SCENARIOS = r'''
static bool inside(const CzmRect&a,const CzmRect&b){return a.w>0&&a.h>0&&a.x>=b.x&&a.y>=b.y&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h;}
static bool overlap(const CzmRect&a,const CzmRect&b){return a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;}
static int hit(CCzmRules&w,const CzmRect&r){cursorX=uiStatic.cursorY=0;cursorX=r.x+r.w/2;cursorY=r.y+r.h/2;uiStatic.cursorY=cursorY;return w.Hit();}
static void tap(CCzmRules&w,const CzmRect&r){hit(w,r);w.KeyDown(1);w.KeyUp(1);}
int main(int argc,char**argv){
 auto&w=*menu_czmrules;
 // An older service does not ask: nothing opens, posts go on.
 CZM_RulesSetState(0,false,"");assert(CZM_RulesAccepted()&&!CZM_RulesConfirmed()&&CZM_RulesAllow(then)&&!w.m_open);
 CZM_RulesSetState(1,false,"https://counter-zombie.ru/rules");assert(!CZM_RulesAccepted());
 for(auto size:{std::pair<int,int>{1536,716},{960,540},{800,360},{1024,768},{1280,720},{2960,1440},{640,320}})
 for(int lang=0;lang<2;lang++)for(int readOnly=0;readOnly<2;readOnly++){
  ScreenWidth=size.first;ScreenHeight=size.second;russian=lang==0;w.Open(readOnly);w.Layout();
  assert(w.m_panel.x>0&&w.m_panel.y>0&&w.m_panel.x+w.m_panel.w<ScreenWidth&&w.m_panel.y+w.m_panel.h<ScreenHeight);
  assert(inside(w.m_clip,w.m_panel)&&inside(w.m_accept,w.m_panel)&&inside(w.m_check,w.m_panel));
  assert(w.m_lines>20&&w.m_clip.h>ScreenHeight/4);
  assert(!overlap(w.m_clip,w.m_accept)&&!overlap(w.m_clip,w.m_check));
  CzmRect second=readOnly?w.m_site:w.m_later;assert(inside(second,w.m_panel)&&!overlap(second,w.m_accept)&&!overlap(second,w.m_check));
  assert(w.m_accept.h>=36&&second.h==w.m_accept.h);
  if(!readOnly){
   // the agreement text fits next to its box
   const int text=CZM_TextWidth(CZM_Font(CZMF_PANEL_TEXT),russian?"Я прочитал и принимаю правила":"I have read and accept the rules");
   assert(w.m_check.w>=w.m_check.h*62/100+text);
   assert(hit(w,w.m_check)==w.CHECK&&hit(w,w.m_later)==w.LATER&&hit(w,w.m_accept)==w.ACCEPT);
  }else assert(hit(w,w.m_site)==w.SITE&&hit(w,w.m_accept)==w.ACCEPT&&w.m_later.w==0);
  // every line of every block stays inside the text column
  for(int i=1;i<w.m_lines;i++)assert(w.m_line[i].y>=w.m_line[i-1].y);
  w.Draw();w.Hide();
 }
 ScreenWidth=1536;ScreenHeight=716;russian=true;
 // A post opens the window; "Accept" needs the box.
 assert(!CZM_RulesAllow(then)&&w.m_open&&!w.m_readOnly&&stack.Current()==&w);
 w.Layout();int requests=nextRequest;tap(w,w.m_accept);assert(nextRequest==requests);
 tap(w,w.m_check);assert(w.m_checked);tap(w,w.m_check);assert(!w.m_checked);tap(w,w.m_check);
 tap(w,w.m_accept);assert(nextRequest==requests+1&&lastUrl=="/api/v1/rules/accept"&&lastBody=="{\"version\":1}"&&lastKey==key);
 // While the answer is on its way nothing closes the window or sends twice.
 w.KeyDown(27);assert(w.m_open);tap(w,w.m_accept);tap(w,w.m_later);assert(nextRequest==requests+1&&w.m_open);
 replies[w.m_request]={503,"{}"};w.Draw();assert(w.m_failed&&w.m_open&&!thenCalls&&w.m_checked);
 tap(w,w.m_accept);replies[w.m_request]={200,"{\"rules\":{\"version\":1,\"accepted\":true}}"};w.Draw();
 assert(thenCalls==1&&!w.m_open&&CZM_RulesAccepted()&&CZM_RulesConfirmed()&&CZM_RulesAllow(then));
 // "Not now" closes and forgets the post.
 CZM_RulesRefused(2,then);assert(w.m_open&&!CZM_RulesAccepted()&&!w.m_checked);w.Layout();tap(w,w.m_later);assert(!w.m_open);
 tap(w,w.m_check);assert(!w.m_checked); // closed: taps do nothing
 // An answer that comes after the game closed the window still counts.
 assert(!CZM_RulesAllow(then));w.Layout();tap(w,w.m_check);tap(w,w.m_accept);assert(lastBody=="{\"version\":2}");
 int pending=w.m_request;w.Hide();replies[pending]={200,"{\"rules\":{\"version\":2,\"accepted\":true}}"};CZM_RulesFrame();
 assert(thenCalls==2&&CZM_RulesAccepted()&&!w.m_open);
 // Read again from About: no agreement, a link to the full text.
 CZM_RulesShow();assert(w.m_open&&w.m_readOnly);w.Layout();tap(w,w.m_site);assert(opened=="https://counter-zombie.ru/rules");
 tap(w,w.m_accept);assert(!w.m_open);
 // The service does not know the session yet: the window says so instead of hanging.
 key="";CZM_RulesRefused(2,nullptr);w.Layout();tap(w,w.m_check);tap(w,w.m_accept);assert(w.m_failed&&!w.m_request);key="player-session-key";
 w.Hide();
 if(argc>1){
  std::string view=argv[1];trace=true;russian=view.find("en")==std::string::npos;
  if(view.rfind("read",0)==0){CZM_RulesSetState(1,true,"");CZM_RulesShow();}
  else{CZM_RulesSetState(1,false,"");CZM_RulesAllow(nullptr);if(view.find("checked")!=std::string::npos)w.m_checked=true;}
  w.Draw();
 }
 puts("RULES_WINDOW_OK");
}
'''


class RulesWindowTests(unittest.TestCase):
    def test_agreement_request_and_continuation(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "utlvector.h").write_text(VECTOR)
            (p / "utlstring.h").write_text(STRING)
            (p / "stub.h").write_text(STUB)
            for name in ["extdll_menu.h", "BaseMenu.h", "Utils.h", "Framework.h", "Scissor.h", "keydefs.h", "CzmMenu.h"]:
                (p / name).write_text('#include "stub.h"\n')
            for name in ["CzmJson.h", "CzmDesign.h"]:
                (p / name).write_text((ROOT / "czm/menu" / name).read_text())
            helpers = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
            wrapping = "\n".join(function(helpers, signature) for signature in
                                 ["static bool CZM_IsLineBreak(", "int CZM_WrapText(", "void CZM_WrapLine("])
            source = (ROOT / "czm/menu/CzmRules.cpp").read_text()
            (p / "main.cpp").write_text(HARNESS + wrapping + source + SCENARIOS)
            exe = p / "rules"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-I" + folder, str(p / "main.cpp"), str(ROOT / "czm/menu/CzmJson.cpp"), "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn("RULES_WINDOW_OK", result.stdout)
            out = os.environ.get("CZM_RULES_PREVIEW_DIR")
            if out:
                dest = Path(out); dest.mkdir(parents=True, exist_ok=True)
                for view in ["ask", "ask-checked", "ask-en", "read"]:
                    r = subprocess.run([str(exe), view], capture_output=True, text=True, check=True)
                    (dest / (view + ".tsv")).write_text(r.stdout)


if __name__ == "__main__":
    unittest.main()
