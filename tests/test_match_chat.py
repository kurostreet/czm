"""Run native match-chat geometry, touch/keyboard state and its real cvar bridge."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
STUB = r'''
#pragma once
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>
using HFont=int;using HIMAGE=int;
enum{CZMF_UI_ACTION,CZMF_UI_LABEL,CZMF_UI_META,CZMF_SMALL,CZMF_CHAT_TEXT,QM_LEFT=0,QM_CENTER=1,KEY_MENU=4,KEY_GAME=5,KEY_MESSAGE=6,QMF_CLOSING=1,K_MWHEELUP=30,K_MWHEELDOWN=31};
#define FBitSet(value,flag) ((value)&(flag))
template<class T>T Q_min(T a,T b){return std::min(a,b);}template<class T>T Q_max(T a,T b){return std::max(a,b);}
unsigned PackRGBA(int r,int g,int b,int a){return(unsigned)r|((unsigned)g<<8)|((unsigned)b<<16)|((unsigned)a<<24);}
extern int ScreenWidth,ScreenHeight;
extern bool drawTrace;
class CMenuBaseClientWindow;using CMenuBaseWindow=CMenuBaseClientWindow;
struct Stack{CMenuBaseWindow*current=nullptr;CMenuBaseWindow*Current(){return current;}bool IsActive(){return current!=nullptr;}int Count(){return current?1:0;}bool IsVisible(void*p){return current==p;}};extern Stack stack;
struct Cursor{int cursorX=0,cursorY=0;Stack&client=stack;Stack menu;};extern Cursor uiStatic;
struct CzmRect{int x,y,w,h;bool Contains(int a,int b)const{return w>0&&h>0&&a>=x&&b>=y&&a<x+w&&b<y+h;}};
inline CzmRect CZM_Rect(int x,int y,int w,int h){return{x,y,w,h};}
class CMenuBaseClientWindow{public:int iFlags=0;CMenuBaseClientWindow(const char*){m_pStack=&stack;}virtual~CMenuBaseClientWindow(){}virtual void Show(){stack.current=this;}virtual void Hide(){if(stack.current==this)stack.current=nullptr;}virtual void Draw(){}virtual bool KeyDown(int){return false;}virtual bool KeyUp(int){return false;}virtual bool MouseMove(int x,int y){uiStatic.cursorX=x;uiStatic.cursorY=y;return false;}virtual void Char(int){}void DisableTransition(){}protected:Stack*m_pStack;};
#define ADD_MENU3(cmd,type,fn) static type*cmd=new type();void fn()
namespace UI{namespace Key{bool IsEscape(int k){return k==27;}bool IsEnter(int k){return k==13;}bool IsBackspace(int k){return k==127;}bool IsLeftMouse(int k){return k==1;}}namespace Scissor{void PushScissor(int x,int y,int w,int h){if(drawTrace)printf("Q\t%d\t%d\t%d\t%d\n",x,y,w,h);}void PopScissor(){if(drawTrace)puts("E");}}}
struct EngFuncs{static const char*GetCvarString(const char*);static float GetCvarFloat(const char*);static void CvarSetValue(const char*,float);static void ClientCmd(bool,const char*);static void KEY_SetDest(int);static double DoubleTime();};
bool CL_IsActive();bool CZM_IsRussian();void UI_EnableTextInput(bool);void CZM_KeepClientMenu(CMenuBaseClientWindow*);void CZM_CloseClientMenuSoon(CMenuBaseClientWindow*);
void CZM_PlayClick();void CZM_MatchKeyHaptic();
void UI_CloseClientMenu();void CZM_ClientMenuFrame();void CZM_MatchChatAfterClientMenuFrame(bool);
HFont CZM_Font(int);int CZM_FontHeight(HFont);int CZM_TextWidth(HFont,const char*);
void CZM_DrawText(HFont,int,int,int,const char*,unsigned,unsigned=0);void UI_FillRect(int,int,int,int,unsigned);
void CZM_DrawSliced(const char*,int,int,int,int,int,int,unsigned);void CZM_DrawImage(const char*,int,int,int,int,unsigned=0xffffffff);void CZM_DrawPill(const char*,int,int,int,int,unsigned=0xffffffff);
int CZM_WrapText(HFont,const char*,int,int*,int);void CZM_WrapLine(const char*,const int*,int,char*,size_t);
HIMAGE CZM_MapPreview(const char*);HIMAGE CZM_Image(const char*);const char*CZM_MapModeArt(const char*,const char*);void CZM_DrawCover(HIMAGE,int,int,int,int);
'''
HARNESS = r'''
#include "stub.h"
int ScreenWidth=1536,ScreenHeight=716;Cursor uiStatic;Stack stack;
bool drawTrace=false;
static std::map<std::string,std::string> vars;
static std::vector<std::string> commands,texts;static std::vector<unsigned> colors;static std::vector<CzmRect> surfaces;
static int keyClicks,keyHaptics;
static double now=100;static bool active=true;static int imeCalls,imeEnables,keyDest,closes;
static CMenuBaseWindow*s_closeSoon;static bool s_clientWasActive;
const char*EngFuncs::GetCvarString(const char*k){return vars[k].c_str();}float EngFuncs::GetCvarFloat(const char*k){return atof(GetCvarString(k));}
void EngFuncs::CvarSetValue(const char*k,float v){vars[k]=std::to_string(v);}void EngFuncs::ClientCmd(bool,const char*c){commands.emplace_back(c);if(!strncmp(c,"czm_match_chat_ime ",19)){vars["czm_match_chat_ime_pending"]="0";keyDest=KEY_MESSAGE;imeEnables++;}}void EngFuncs::KEY_SetDest(int k){keyDest=k;}double EngFuncs::DoubleTime(){return now;}
bool CL_IsActive(){return active;}bool CZM_IsRussian(){return true;}void UI_EnableTextInput(bool on){imeCalls++;imeEnables+=on;}
void CZM_PlayClick(){keyClicks++;}void CZM_MatchKeyHaptic(){keyHaptics++;}
void CZM_KeepClientMenu(CMenuBaseClientWindow*p){if(s_closeSoon==p)s_closeSoon=nullptr;}void CZM_CloseClientMenuSoon(CMenuBaseClientWindow*p){closes++;s_closeSoon=p;}
void UI_CloseClientMenu(){stack.current=nullptr;EngFuncs::KEY_SetDest(KEY_GAME);}
HFont CZM_Font(int f){return f;}int CZM_FontHeight(HFont f){return std::max(8,(f==CZMF_UI_ACTION?26:f==CZMF_UI_META?15:f==CZMF_CHAT_TEXT?23:f==CZMF_SMALL?17:20)*ScreenHeight/768);}
int CZM_TextWidth(HFont f,const char*s){int n=0;for(;*s;s++)if((*s&0xc0)!=0x80)n++;return n*CZM_FontHeight(f)*3/5;}
void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned justify){assert(x>=0&&y>=0&&w>0&&x+w<=ScreenWidth);texts.emplace_back(s);colors.push_back(c);if(drawTrace)printf("T\t%d\t%d\t%d\t%d\t%u\t%u\t%s\n",x,y,w,CZM_FontHeight(f),c,justify,s);}
void CheckRect(int x,int y,int w,int h){assert(x>=0&&y>=0&&w>=0&&h>=0&&x+w<=ScreenWidth&&y+h<=ScreenHeight);}
void UI_FillRect(int x,int y,int w,int h,unsigned c){CheckRect(x,y,w,h);if(drawTrace)printf("R\t%d\t%d\t%d\t%d\t%u\n",x,y,w,h,c);}
void CZM_DrawSliced(const char*,int x,int y,int w,int h,int,int radius,unsigned c){CheckRect(x,y,w,h);surfaces.push_back(CZM_Rect(x,y,w,h));if(drawTrace)printf("S\t%d\t%d\t%d\t%d\t%u\t%d\n",x,y,w,h,c,radius);}
void CZM_DrawImage(const char*p,int x,int y,int w,int h,unsigned c){CheckRect(x,y,w,h);if(drawTrace)printf("I\t%d\t%d\t%d\t%d\t%u\t%s\n",x,y,w,h,c,p);}void CZM_DrawPill(const char*p,int x,int y,int w,int h,unsigned c){CZM_DrawImage(p,x,y,w,h,c);}
'''
SCENARIOS = r'''
static bool inside(MC::Rect a,MC::Rect b){return a.w>0&&a.h>0&&a.x>=b.x&&a.y>=b.y&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h;}
static bool overlap(MC::Rect a,MC::Rect b){return a.x<b.x+b.w&&b.x<a.x+a.w&&a.y<b.y+b.h&&b.y<a.y+a.h;}
static void cursor(MC::Rect r){uiStatic.cursorX=r.x+r.w/2;uiStatic.cursorY=r.y+r.h/2;}
static void tap(CCzmMatchChat&w,MC::Rect r){cursor(r);assert(w.KeyDown(1));assert(w.KeyUp(1));}
static int key(CCzmMatchChat&w,MC::Action action,const char*text=nullptr){for(int i=0;i<w.m_layout.count;i++)if(w.m_layout.keys[i].action==action&&(!text||!strcmp(w.m_layout.keys[i].text,text)))return i;assert(false);return-1;}
static void press(CCzmMatchChat&w,MC::Action action,const char*text=nullptr){w.Layout();tap(w,w.m_layout.keys[key(w,action,text)].rect);w.Layout();}
static int sends(){int n=0;for(auto&c:commands)n+=c.find("czm_match_chat_send ")==0;return n;}
static void publish(unsigned seq,const char*text){char hex[2048],value[2200],name[32];MC::Encode(text,hex);snprintf(value,sizeof(value),"%u 69b0ff 8 %s",seq,hex);snprintf(name,sizeof(name),"czm_mc_line%u",seq%32);vars[name]=value;vars["czm_mc_head"]=std::to_string(seq);}
static void request(unsigned serial,bool team=false){vars["czm_match_chat_request"]=std::to_string(serial)+(team?" 1":" 0");vars["czm_match_chat_active"]="1";}
int main(int argc,char**argv){
 auto&w=*menu_czmmatchchat;
 vars["czm_match_chat"]="1";vars["czm_match_chat_ru"]="-1";vars["czm_match_chat_haptic"]="1";vars["vibration_enable"]="1";vars["czm_match_chat_epoch"]="3";vars["czm_mc_epoch"]="7";vars["czm_connect_adr"]="203.0.113.4:27015";
 request(1);w.Frame();assert(w.m_shown&&w.m_model.state==MC::Typing&&keyDest==KEY_MENU&&!imeEnables);
 if(argc>1){
  std::string view=argv[1];if(view.find("compact")!=std::string::npos){ScreenWidth=640;ScreenHeight=360;}
  publish(1,"\7FFBB66[LVL 40] \3Kuro : \1Всем привет!");
  publish(2,"\7D082FFHunter : \1Держим проход, зомби рядом");
  publish(3,"\4[Сервер] \1Следующая волна через 10 секунд");
  publish(4,"\3Shadow : \1Я прикрываю справа");
  publish(5,"\7FF8F66Player : \1Нужны патроны у выхода");w.Frame();
  w.m_model.state=view.find("history")!=std::string::npos?MC::History:MC::Typing;
  MC::Append(w.m_model.draft,"Прикрывайте проход, иду справа");
  if(view.find("press")!=std::string::npos){w.Layout();cursor(w.m_layout.keys[key(w,MC::Letter,"п")].rect);w.KeyDown(1);}
  drawTrace=true;w.Draw();return 0;
 }
 for(auto size:{std::pair<int,int>{1536,716},{640,320},{800,360},{960,540},{1024,768},{2340,1080},{2960,1440}})
 for(int state=1;state<=2;state++)for(int lang=0;lang<2;lang++)for(int number=0;number<2;number++){
  ScreenWidth=size.first;ScreenHeight=size.second;w.m_model.state=(MC::State)state;w.m_model.russian=lang==0;w.m_model.numbers=number;w.Layout();
  auto&l=w.m_layout;MC::Rect screen={0,0,ScreenWidth,ScreenHeight};assert(inside(l.history,screen)&&inside(l.composer,screen));assert(l.history.y+l.history.h<l.composer.y);
  for(auto r:{l.channel,l.field,l.send,l.close})assert(inside(r,l.composer));
  assert(!overlap(l.channel,l.field)&&!overlap(l.field,l.send)&&!overlap(l.send,l.close));
  if(state==MC::Typing){assert(inside(l.keyboard,screen)&&l.composer.y+l.composer.h<l.keyboard.y);assert(l.count>=34&&l.count<MC::MaxKeys);
   for(int i=0;i<l.count;i++){
    assert(inside(l.keys[i].rect,l.keyboard)&&l.keys[i].rect.h>=26);
    const char*p=l.keys[i].text;while(*p){int n=MC::Utf8Length(p);assert(n>0);p+=n;}
    if(l.keys[i].action==MC::Space)assert(!strcmp(l.keys[i].text,lang==0?"Пробел":"Space"));
    auto pop=MC::FeedbackRect(l.keys[i].rect,l.keyboard,l.gap,1);assert(inside(pop,l.keyboard)&&inside(l.keys[i].rect,pop));
    assert(pop.w>=l.keys[i].rect.w&&pop.h>l.keys[i].rect.h);
    for(int j=0;j<l.count;j++)if(j!=i){assert(!overlap(l.keys[i].rect,l.keys[j].rect));assert(!overlap(pop,l.keys[j].rect));}
   }
  }else assert(!l.count&&!l.keyboard.w);
  w.Draw();
 }
 ScreenWidth=1536;ScreenHeight=716;w.m_model.state=MC::Typing;w.m_model.russian=true;w.m_model.numbers=false;w.Layout();
 // A touch draws its pop immediately, keeps a fixed hit target and commits on
 // release once. A duplicate held-down event cannot retrigger sound or haptics.
 const int first=key(w,MC::Letter,"й");const auto target=w.m_layout.keys[first].rect;cursor(target);int clicks=keyClicks,haptics=keyHaptics;
 w.KeyDown(1);assert(!w.m_model.draft[0]&&w.m_feedback.held&&w.m_feedback.Amount(now)==1&&keyClicks==clicks+1&&keyHaptics==haptics+1);
 const auto pop=MC::FeedbackRect(target,w.m_layout.keyboard,w.m_layout.gap,1);surfaces.clear();w.Draw();bool drawnPop=false;
 for(auto&r:surfaces){drawnPop|=r.x==pop.x&&r.y==pop.y&&r.w==pop.w&&r.h==pop.h;}assert(drawnPop);
 uiStatic.cursorX=target.x-1;uiStatic.cursorY=target.y+target.h/2;assert(w.Hit()!=w.HitKey+first);cursor(target);assert(w.Hit()==w.HitKey+first);
 w.KeyDown(1);assert(keyClicks==clicks+1&&keyHaptics==haptics+1&&!w.m_model.draft[0]);w.KeyUp(1);assert(!strcmp(w.m_model.draft,"й")&&!w.m_feedback.held&&w.m_feedback.Amount(now)>0);
 now+=.045;assert(w.m_feedback.Amount(now)>.4f&&w.m_feedback.Amount(now)<.6f);now+=.06;assert(w.m_feedback.Amount(now)==0);
 // Each real touch observes both haptic switches. Sound is the normal CZM UI
 // tap, while the platform helper retains OS permission/settings checks.
 vars["czm_match_chat_haptic"]="0";press(w,MC::Letter,"ц");assert(keyHaptics==haptics+1);
 vars["czm_match_chat_haptic"]="1";vars["vibration_enable"]="0";press(w,MC::Letter,"у");assert(keyHaptics==haptics+1);vars["vibration_enable"]="1";
 press(w,MC::Language);assert(w.m_feedback.key.action==MC::Language&&!strcmp(w.m_feedback.key.text,"RU")&&!w.m_model.russian);
 press(w,MC::Language);w.ClearPress();w.m_model.ResetDraft();assert(w.m_feedback.Amount(now)==0);
 cursor(w.m_layout.keys[key(w,MC::Letter,"й")].rect);w.KeyDown(1);w.MouseMove(ScreenWidth-2,2);assert(w.m_feedback.Amount(now)==0);w.KeyUp(1);assert(!w.m_model.draft[0]);
 press(w,MC::Letter,"й");assert(!strcmp(w.m_model.draft,"й"));press(w,MC::Shift);press(w,MC::Letter,"ц");assert(!strcmp(w.m_model.draft,"йЦ")&&!w.m_model.shift);
 press(w,MC::Shift);now+=.1;press(w,MC::Shift);assert(w.m_model.caps);press(w,MC::Letter,"я");assert(strstr(w.m_model.draft,"Я"));press(w,MC::Shift);assert(!w.m_model.caps);
 press(w,MC::Language);assert(!w.m_model.russian&&vars["czm_match_chat_ru"]=="0.000000");press(w,MC::Letter,"q");press(w,MC::Numbers);press(w,MC::Letter,"1");assert(strstr(w.m_model.draft,"q1"));
 int del=key(w,MC::Backspace);cursor(w.m_layout.keys[del].rect);size_t before=strlen(w.m_model.draft);w.KeyDown(1);assert(strlen(w.m_model.draft)==before-1);clicks=keyClicks;haptics=keyHaptics;now+=.43;w.Frame();assert(strlen(w.m_model.draft)==before-2&&keyClicks==clicks&&keyHaptics==haptics&&w.m_feedback.held);w.KeyUp(1);assert(strlen(w.m_model.draft)==before-2);
 // Back is staged, preserving the draft, with one serial-protected close.
 std::string draft=w.m_model.draft;w.KeyDown(27);assert(w.m_shown&&w.m_model.state==MC::History&&!strcmp(w.m_model.draft,draft.c_str())&&w.m_feedback.Amount(now)==0);
 int closed=closes;w.KeyDown(27);assert(!w.m_shown&&closes==closed+1&&commands.back()=="czm_match_chat_close 1\n");
 request(2,true);w.Frame();assert(w.m_model.team&&w.m_model.state==MC::Typing&&!strcmp(w.m_model.draft,draft.c_str()));
 // The opening and closing taps cannot escape to the game's fire controls.
 cursor({ScreenWidth-10,10,1,1});assert(w.KeyDown(1)&&w.KeyUp(1));assert(w.m_model.state==MC::History&&w.m_shown);
 cursor(w.m_layout.field);w.KeyDown(1);cursor({ScreenWidth-10,10,1,1});w.KeyUp(1);assert(w.m_shown&&w.m_model.state==MC::History);
 w.Layout();tap(w,w.m_layout.field);assert(w.m_model.state==MC::Typing);
 // Char arrives as UTF-8 bytes on Android: retain incomplete characters outside the draft.
 w.m_model.ResetDraft();w.Char(0xd0);assert(!*w.m_model.draft);w.Char(0xaf);assert(!strcmp(w.m_model.draft,"Я"));w.Char(0x80);assert(!strcmp(w.m_model.draft,"Я"));
 w.Char('"');w.Char(';');w.Char('\\');w.Char('\n');assert(!strcmp(w.m_model.draft,"Я"));w.Char(0x1f600);assert(!strcmp(w.m_model.draft,"Я😀"));w.KeyDown(127);assert(!strcmp(w.m_model.draft,"Я"));
 w.m_model.ResetDraft();for(int i=0;i<95;i++)MC::Append(w.m_model.draft,"Я");assert(MC::Characters(w.m_model.draft)==95&&strlen(w.m_model.draft)==190);assert(!MC::Append(w.m_model.draft,"😀"));MC::Delete(w.m_model.draft);assert(strlen(w.m_model.draft)==188);MC::Delete(w.m_model.draft);assert(MC::Append(w.m_model.draft,"😀")&&strlen(w.m_model.draft)==190);
 char cleaned[MC::MaxBytes+1]={};MC::Append(cleaned,"  hello\";\\\nworld  ");MC::Trim(cleaned);assert(!strcmp(cleaned,"helloworld"));
 // Native server colours survive transport, wrapping and rendering.
 publish(1,"\3Kuro : \1Hi \4green \7ff20aaRGB");w.Frame();assert(w.m_model.count==1);assert(!strcmp(w.m_model.messages[0].text,"\3Kuro : \1Hi \4green \7ff20aaRGB"));
 colors.clear();w.Draw();assert(std::find(colors.begin(),colors.end(),PackRGBA(255,32,170,255))!=colors.end());assert(std::find(colors.begin(),colors.end(),PackRGBA(105,176,255,255))!=colors.end());assert(std::find(colors.begin(),colors.end(),PackRGBA(0,255,0,255))!=colors.end());
 publish(2,"\2Kuro : body");w.Frame();w.m_model.messages[1].nameLength=5;texts.clear();colors.clear();w.Draw();bool nickColor=false,bodyColor=false;for(size_t i=0;i<texts.size();i++){if(texts[i]=="K")nickColor|=colors[i]==PackRGBA(105,176,255,255);if(texts[i]=="b")bodyColor|=colors[i]==PackRGBA(255,178,0,255);}assert(nickColor&&bodyColor);
 MC::Message bad;assert(!MC::ParseMessage("2 ff00zz 0 41",bad));assert(!MC::ParseMessage("2 ffffff 0 4",bad));assert(!MC::ParseMessage("2 ffffff 0 00",bad));
 for(unsigned i=3;i<40;i++){publish(i,"line");}w.Frame();assert(w.m_model.count==32&&w.m_model.messages[0].seq==8&&w.m_model.messages[31].seq==39);
 // Send once, all/team stays in the dedicated engine command, no user command text.
 w.m_model.ResetDraft();MC::Append(w.m_model.draft,"  Привет  ");vars["czm_match_chat_keep_open"]="1";int sent=sends();clicks=keyClicks;haptics=keyHaptics;w.KeyDown(13);w.KeyDown(13);w.KeyUp(13);assert(sends()==sent+1&&w.m_shown&&!w.m_model.draft[0]&&clicks==keyClicks&&haptics==keyHaptics);
 char hex[381];MC::Encode("Привет",hex);assert(commands[commands.size()-1]==std::string("czm_match_chat_send 1 3 ")+hex+"\n");
 MC::Append(w.m_model.draft,"next");vars["czm_match_chat_keep_open"]="0";w.Layout();tap(w,w.m_layout.send);assert(sends()==sent+2&&!w.m_shown);w.KeyUp(1);assert(sends()==sent+2);
 // Focus change clears draft but keeps same-server history; map/server reset clears both.
 request(3);w.Frame();MC::Append(w.m_model.draft,"secret draft");cursor(w.m_layout.keys[key(w,MC::Letter,"1")].rect);w.KeyDown(1);vars["czm_match_chat_epoch"]="4";w.Frame();assert(!w.m_shown&&!w.m_model.draft[0]&&w.m_model.count==32&&w.m_feedback.Amount(now)==0);
 request(4);w.Frame();assert(w.m_shown);MC::Append(w.m_model.draft,"other draft");vars["czm_mc_epoch"]="8";vars["czm_mc_head"]="0";w.Frame();assert(!w.m_shown&&!w.m_model.draft[0]&&!w.m_model.count);
 request(5);w.Frame();MC::Append(w.m_model.draft,"server A");vars["czm_connect_adr"]="203.0.113.5:27015";w.Frame();assert(!w.m_shown&&!w.m_model.draft[0]);
 request(6);w.Frame();publish(40,"next server");w.Frame();MC::Append(w.m_model.draft,"bye");active=false;w.Frame();assert(!w.m_shown&&!w.m_model.count&&!w.m_model.draft[0]);
 assert(imeCalls>0&&!imeEnables);CZM_ClientMenuFrame();
 // A request cancelled before the first UI frame cannot open on focus return,
 // even if the request string itself remains in an older engine build.
 active=true;request(7);vars["czm_match_chat_active"]="0";vars["czm_match_chat_epoch"]="5";w.Frame();assert(!w.m_shown&&w.m_model.request==7);CZM_ClientMenuFrame();assert(!stack.IsActive());
 // Coupled real Frame + real client-stack closure: intentional OS IME starts
 // AFTER UI_CloseClientMenu's KEY_GAME and the shared touch/key restoration.
 request(8,true);w.Frame();CZM_ClientMenuFrame();assert(w.m_shown&&stack.IsActive()&&keyDest==KEY_MENU);
 vars["czm_match_chat_active"]="0";vars["czm_match_chat_ime_pending"]="2";w.Frame();assert(!w.m_shown&&stack.IsActive());
 CZM_ClientMenuFrame();assert(!stack.IsActive()&&keyDest==KEY_MESSAGE&&vars["czm_match_chat_ime_pending"]=="0");
 int enabled=imeEnables;CZM_ClientMenuFrame();assert(imeEnables==enabled&&keyDest==KEY_MESSAGE);
 // Pending IME without a drawn overlay also gets exactly one safe handoff.
 vars["czm_match_chat_ime_pending"]="1";CZM_ClientMenuFrame();assert(imeEnables==enabled+1&&keyDest==KEY_MESSAGE);
 puts("MATCH_CHAT_OK");
}
'''


class MatchChatTests(unittest.TestCase):
    def test_native_keyboard_history_lifecycle_and_geometry(self):
        with tempfile.TemporaryDirectory(prefix="czm-match-chat-") as folder:
            p = Path(folder)
            (p / "stub.h").write_text(STUB)
            for name in ["extdll_menu.h", "BaseMenu.h", "Utils.h", "BaseClientWindow.h", "Scissor.h", "keydefs.h", "CzmMenu.h"]:
                (p / name).write_text('#include "stub.h"\n')
            for name in ["CzmDesign.h", "CzmMatchChatModel.h"]:
                (p / name).write_text((ROOT / "czm/menu" / name).read_text())
            source = (ROOT / "czm/menu/CzmMatchChat.cpp").read_text().replace("private:", "public:")
            shared_close = function((ROOT / "czm/menu/CzmMenu.cpp").read_text(), "void CZM_ClientMenuFrame(")
            (p / "main.cpp").write_text(HARNESS + source + shared_close + SCENARIOS)
            exe = p / "chat"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-I" + folder, str(p / "main.cpp"), "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn("MATCH_CHAT_OK", result.stdout)
            preview = os.environ.get("CZM_MATCH_CHAT_PREVIEW_DIR")
            if preview:
                dest = Path(preview)
                dest.mkdir(parents=True, exist_ok=True)
                for view in ["typing-ru", "typing-press-ru", "history-draft", "compact-typing-ru", "compact-typing-press-ru", "compact-history-draft"]:
                    trace = subprocess.run([str(exe), view], check=True, capture_output=True, text=True)
                    (dest / (view + ".tsv")).write_text(trace.stdout)


if __name__ == "__main__":
    unittest.main()
