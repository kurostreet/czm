"""Run the native social window against delayed HTTPS replies and account changes."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_tab_avatars import VECTOR, STRING

ROOT = Path(__file__).resolve().parents[1]
STUB = r'''
#pragma once
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include "utlvector.h"
#include "utlstring.h"
using HFont=int;
enum{CZMF_PANEL_TEXT,CZMF_LANG,CZMF_SMALL,CZMF_PANEL_TITLE,CZMF_NICK,QM_CENTER=1,QM_RIGHT=2,CZM_TAB_PROFILE=5,K_MWHEELUP=30,K_MWHEELDOWN=31};
template<class T> T Q_min(T a,T b){return std::min(a,b);}template<class T>T Q_max(T a,T b){return std::max(a,b);}
template<class T>T bound(T a,T b,T c){return std::max(a,std::min(b,c));}
inline void Q_strncpy(char*a,const char*b,size_t n){if(a!=b){strncpy(a,b,n);a[n-1]=0;}}
inline unsigned PackRGBA(int r,int g,int b,int a){return (unsigned)r|((unsigned)g<<8)|((unsigned)b<<16)|((unsigned)a<<24);}
extern int ScreenWidth,ScreenHeight,cursorX,cursorY;
struct CzmRect {int x,y,w,h;bool HasCursor()const{return cursorX>=x&&cursorX<x+w&&cursorY>=y&&cursorY<y+h;}};
inline CzmRect CZM_Rect(int x,int y,int w,int h){return{x,y,w,h};}
struct Stack{void*current=nullptr;void*Current(){return current;}};extern Stack stack;
class CMenuFramework{public:CMenuFramework(const char*){m_pStack=&stack;}virtual~CMenuFramework(){}virtual void Show(){stack.current=this;}virtual void Hide(){if(stack.current==this)stack.current=nullptr;}
virtual void Draw(){}virtual bool IsRoot()const{return false;}virtual bool KeyDown(int){return false;}virtual bool KeyUp(int){return false;}virtual bool MouseMove(int,int){return false;}virtual void Char(int){}protected:Stack*m_pStack;};
#define ADD_MENU3(cmd,type,fn) static type*cmd=new type();void fn()
namespace UI{namespace Key{inline bool IsBackspace(int k){return k==8;}inline bool IsEnter(int k){return k==13;}inline bool IsEscape(int k){return k==27;}inline bool IsLeftMouse(int k){return k==1;}}
namespace Scissor{inline void PushScissor(int,int,int,int){}inline void PopScissor(){}}}
struct Cursor{int cursorY;} ;extern Cursor uiStatic;
struct EngFuncs{static const char*GetCvarString(const char*);static float GetCvarFloat(const char*);static void CvarSetString(const char*,const char*);static void CvarSetValue(const char*,float);static double DoubleTime();static void SetTextInputRect(int,int,int,int){}};
inline bool CL_IsActive(){return false;}
void UI_EnableTextInput(bool);void CZM_Init();bool CZM_IsRussian();unsigned CZM_White();unsigned CZM_Grey();
HFont CZM_Font(int);int CZM_FontHeight(HFont);int CZM_TextWidth(HFont,const char*);int CZM_WrapText(HFont,const char*,int,int*,int);void CZM_WrapLine(const char*,const int*,int,char*,size_t);
void CZM_DrawText(HFont,int,int,int,const char*,unsigned,unsigned=0);void UI_FillRect(int,int,int,int,unsigned);
void CZM_DrawImage(const char*,int,int,int,int,unsigned=0xffffffff);void CZM_DrawPill(const char*,int,int,int,int,unsigned=0xffffffff);void CZM_DrawButton(const char*,const CzmRect&,const char*,unsigned,bool,int);void CZM_DrawPanel(const CzmRect&);
int CZM_CountBadgeWidth(int,int);void CZM_DrawCountBadge(const CzmRect&,int);
int CZM_ChatUnread(int room=-1);int CZM_SocialNotifications();void CZM_ChatMarkRead(int,int);
bool CZM_OnlineReady();bool CZM_OnlineAccount();int CZM_OnlineIdentity();const char*CZM_OnlineKey();int CZM_OnlinePlayer();const char*CZM_OnlineUrl(const char*);const char*CZM_AvatarFor(const char*,int);
int CZM_NetRequest(const char*,const char*,const char*,const char*);bool CZM_NetPoll(int,int*,CUtlString&);void CZM_NetNewKey(char*,size_t);
void CZM_OpenSettings(int);void CZM_AccountShow(const char*,const char*);bool CZM_CopyText(const char*);void CZM_JoinAddress(const char*);void CZM_PlayClick();
bool CZM_LobbyCanInvite();
void CZM_LobbyInviteFriend(int);
void CZM_OpenLobbyById(const char*);
void CZM_DrawMapPreview(const char*,int,int,int,int,const char*);
struct CzmServer{char address[64];char prot[8];char name[64];};int CZM_ServerCount();CzmServer *CZM_Server(int);void CZM_CleanName(const char*,char*,size_t);void CZM_DrawSliced(const char*,int,int,int,int,int,int,unsigned=0xffffffff);
'''
HARNESS = r'''
#include "stub.h"
#include <map>
#include <cassert>
int ScreenWidth=1536,ScreenHeight=716,cursorX,cursorY;Cursor uiStatic;Stack stack;
static double now=100;static std::string key="legacy-device-key";static int me=7,ids,logins,lastButtonFont,identity=1;static bool authenticated=true,drawTrace;static bool russian=true;
static std::map<std::string,std::string> vars;static std::map<int,std::pair<int,std::string>> replies;
struct Request{int id;std::string url,body;};static std::vector<Request> requests;
const char*EngFuncs::GetCvarString(const char*k){return vars[k].c_str();}float EngFuncs::GetCvarFloat(const char*k){return atof(GetCvarString(k));}void EngFuncs::CvarSetString(const char*k,const char*v){vars[k]=v;}void EngFuncs::CvarSetValue(const char*k,float v){vars[k]=std::to_string(v);}double EngFuncs::DoubleTime(){return now;}
void UI_EnableTextInput(bool){}void CZM_Init(){}bool CZM_IsRussian(){return russian;}unsigned CZM_White(){return 0xffffffff;}unsigned CZM_Grey(){return PackRGBA(150,164,184,255);}
HFont CZM_Font(int i){return i;}int CZM_FontHeight(HFont f){return (f==CZMF_PANEL_TITLE?42:f==CZMF_NICK?29:f==CZMF_LANG?24:f==CZMF_SMALL?17:21)*ScreenHeight/768;}
int CZM_TextWidth(HFont f,const char*s){int n=0;for(;*s;s++)if((*s&0xc0)!=0x80)n++;return n*CZM_FontHeight(f)*62/100;}
int CZM_WrapText(HFont f,const char*s,int w,int*starts,int max){int lines=0,i=0,last=0;starts[0]=0;for(;s[i]&&lines<max;){int from=i,n=0;while(s[i]&&(n*CZM_FontHeight(f)/2<w||!n)){i++;while((s[i]&0xc0)==0x80)i++;n++;}if(i==from)break;lines++;starts[lines]=i;last=i;}return lines;}
void CZM_WrapLine(const char*s,const int*starts,int n,char*out,size_t size){int len=std::min((int)size-1,starts[n+1]-starts[n]);memcpy(out,s+starts[n],len);out[len]=0;}
void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){if(drawTrace){printf("T\t%d\t%d\t%d\t%d\t%u\t%u\t%s\n",x,y,w,CZM_FontHeight(f),c,just,s);}}
void UI_FillRect(int x,int y,int w,int h,unsigned c){if(drawTrace)printf("R\t%d\t%d\t%d\t%d\t%u\n",x,y,w,h,c);}
void CZM_DrawImage(const char*p,int x,int y,int w,int h,unsigned c){if(drawTrace)printf("I\t%d\t%d\t%d\t%d\t%s\n",x,y,w,h,p);}
void CZM_DrawPill(const char*,int x,int y,int w,int h,unsigned c){UI_FillRect(x,y,w,h,c);}
void CZM_DrawPanel(const CzmRect&r){UI_FillRect(r.x,r.y,r.w,r.h,PackRGBA(10,17,26,250));}
void CZM_DrawButton(const char*p,const CzmRect&r,const char*s,unsigned c,bool,int font){lastButtonFont=font;UI_FillRect(r.x,r.y,r.w,r.h,strstr(p,"primary")?PackRGBA(210,34,55,255):PackRGBA(31,43,59,255));CZM_DrawText(font,r.x+r.h/4,r.y+(r.h-CZM_FontHeight(font))/2,r.w-r.h/2,s,c,QM_CENTER);}
bool CZM_OnlineReady(){return true;}bool CZM_OnlineAccount(){return authenticated;}int CZM_OnlineIdentity(){return identity;}const char*CZM_OnlineKey(){return key.c_str();}int CZM_OnlinePlayer(){return me;}const char*CZM_OnlineUrl(const char*p){return p;}const char*CZM_AvatarFor(const char*,int){return "gfx/czm/ui/avatar.png";}
int CZM_NetRequest(const char*,const char*url,const char*,const char*body){requests.push_back({++ids,url,body});return ids;}
bool CZM_NetPoll(int id,int*status,CUtlString&body){auto i=replies.find(id);if(i==replies.end())return false;*status=i->second.first;body.Set(i->second.second.c_str());replies.erase(i);return true;}
void CZM_NetNewKey(char*out,size_t size){Q_strncpy(out,"0123456789abcdef0123456789abcdef",size);}int CZM_ServerCount(){return 0;}CzmServer *CZM_Server(int){return 0;}void CZM_CleanName(const char*in,char*out,size_t size){Q_strncpy(out,in,size);}void CZM_DrawSliced(const char*,int x,int y,int w,int h,int,int,unsigned c){UI_FillRect(x,y,w,h,c);}void CZM_OpenSettings(int){}void CZM_AccountShow(const char*,const char*){logins++;}bool CZM_CopyText(const char*){return true;}void CZM_JoinAddress(const char*){}void CZM_PlayClick(){}
bool CZM_LobbyCanInvite(){return false;}
void CZM_LobbyInviteFriend(int){}
void CZM_OpenLobbyById(const char*){}
void CZM_DrawMapPreview(const char*,int,int,int,int,const char*){}
'''
SCENARIOS = r'''
int main(int argc,char**argv){
 CZM_SocialFrame();CZM_OpenFriends();auto&w=*menu_czmsocial;w.Frame();assert(w.m_read);
 int old=w.m_read;w.m_tab=1;w.Navigate(w.LIST);replies[old]={200,"{\"people\":[{\"id\":99,\"nick\":\"stale\"}]}"};w.Frame();assert(w.m_people.Count()==0);
 CzmJson j;assert(j.Parse("{\"profile\":{\"id\":8,\"nick\":\"Hunter\",\"account\":true,\"relation\":\"friend\",\"online\":true,\"status\":\"Выживаем вместе\",\"created\":1792240000,\"counts\":{\"friends\":234,\"followers\":47}},\"can_send\":true,\"messages\":[{\"id\":1,\"p\":8,\"t\":\"Привет! Заходи играть\",\"ts\":1792240000}]}"));
 w.m_target=8;w.Navigate(w.DIALOG);w.Read(j,w.READ_DIALOG);assert(w.m_canSend&&w.m_messages.Count()==1);
 strcpy(w.m_input,"Hello friend");w.Send();int send=w.m_write;auto payload=requests.back().body;replies[send]={0,""};w.Frame();assert(!w.m_write&&!strcmp(w.m_input,"Hello friend"));
 w.Send();assert(requests.back().body==payload);replies[w.m_write]={200,"{\"message\":{\"id\":2}}"};w.Frame();assert(!*w.m_input);
 // A read follower list must not start a mark-seen/refetch request loop.
 w.m_tab=2;w.Navigate(w.LIST);CzmJson followers;assert(followers.Parse("{\"people\":[],\"counts\":{\"requests\":0},\"next\":-1}"));
 w.Read(followers,w.READ_LIST);assert(w.m_write==0);
 // A reply sent before logout cannot populate another account's window.
 int pending=w.m_read;identity++;me=9;CZM_SocialFrame();assert(!w.m_open&&w.m_messages.Count()==0);
 if(pending)replies[pending]={200,"{\"messages\":[{\"id\":55,\"t\":\"private old account\"}]}"};CZM_SocialFrame();assert(w.m_messages.Count()==0);
 authenticated=false;identity++;CZM_SocialFrame();CZM_OpenFriends();w.Layout();cursorX=w.m_prev.x+1;cursorY=w.m_prev.y+1;assert(w.Hit()==w.LOGIN);w.Activate(w.LOGIN);assert(logins==1);
 Button(CZM_Rect(0,0,ScreenHeight*.18f,ScreenHeight*.07f),"Отправить");assert(lastButtonFont!=CZMF_LANG);
 // Profiles remain compact with reachable, non-overlapping controls.
 authenticated=true;identity++;CZM_SocialFrame();CZM_OpenFriends();
 for(auto resolution:{std::pair<int,int>{1536,716},{960,540},{1024,768},{1280,720}}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;
  for(int variant=0;variant<8;variant++){
   russian=variant%2==0;
   w.OpenProfile(8,false);w.Read(j,w.READ_PROFILE);
   if(variant==1){strcpy(w.m_profile.server,"203.0.113.10:27015");strcpy(w.m_profile.map,"zm_survival");}
   if(variant==2){w.m_profile.id=me;strcpy(w.m_profile.relation,"self");}
   if(variant==3){w.m_profile.account=false;strcpy(w.m_profile.relation,"none");}
   if(variant==4){w.m_profile.id=me;strcpy(w.m_profile.relation,"self");w.m_editStatus=true;}
   if(variant==5)strcpy(w.m_profile.relation,"blocked");
   if(variant==6)strcpy(w.m_profile.relation,"unavailable");
   if(variant==7){memset(w.m_profile.status,'W',100);w.m_profile.status[100]=0;}
   w.Draw();assert(w.m_panel.y>0&&w.m_panel.x>0);
   assert(w.m_panel.w*w.m_panel.h<ScreenWidth*ScreenHeight*.5f);
   assert(w.m_panel.y+w.m_panel.h<ScreenHeight);
   CzmRect*buttons[]={&w.m_primary,&w.m_secondary,&w.m_edit,&w.m_settings,&w.m_report,&w.m_block,&w.m_join,&w.m_copy};
   for(auto r:buttons)if(r->w){
    assert(r->x>=w.m_panel.x&&r->y>=w.m_panel.y);
    assert(r->x+r->w<=w.m_panel.x+w.m_panel.w&&r->y+r->h<=w.m_panel.y+w.m_panel.h);
    cursorX=r->x+r->w/2;cursorY=uiStatic.cursorY=r->y+r->h/2;assert(w.Hit());
    for(auto other:buttons)if(r!=other&&other->w)assert(r->x+r->w<=other->x||other->x+other->w<=r->x||r->y+r->h<=other->y||other->y+other->h<=r->y);
   }
  }
 }
 // Native account state is public metadata: the legacy key never contains the session.
 assert(Account()&&key=="legacy-device-key");
 w.OpenProfile(me,false);w.Read(j,w.READ_PROFILE);w.m_profile.id=me;w.Layout();
 cursorX=w.m_profileStatus.x+2;cursorY=uiStatic.cursorY=w.m_profileStatus.y+2;
 assert(w.Hit()==w.EDIT);w.KeyDown(1);w.KeyUp(1);assert(w.m_editStatus);
 w.Activate(w.CANCEL);w.Layout();
 // Interior taps stay in the card; an exterior tap closes and is consumed.
 cursorX=w.m_panel.x+w.m_panel.w/2;cursorY=uiStatic.cursorY=w.m_panel.y+w.m_panel.h/2;assert(w.Hit()!=w.BACKDROP);
 cursorX=w.m_panel.x-2;cursorY=uiStatic.cursorY=w.m_panel.y+2;
 assert(w.Hit()==w.BACKDROP);assert(w.KeyDown(1));assert(w.KeyUp(1));assert(!w.m_open);
 russian=true;
 // Adding from a player card uses the account ID, then exposes the dialog for a friend.
 w.OpenProfile(8,true,71);w.Read(j,w.READ_PROFILE);strcpy(w.m_profile.relation,"none");w.Layout();
 cursorX=w.m_primary.x+2;cursorY=uiStatic.cursorY=w.m_primary.y+2;assert(w.Hit()==w.PRIMARY);
 w.KeyDown(1);w.KeyUp(1);assert(requests.back().url=="/api/v1/social/action"&&requests.back().body=="{\"target\":8,\"action\":\"follow\"}");
 replies[w.m_write]={200,"{}"};w.Frame();w.Read(j,w.READ_PROFILE);
 w.Activate(w.PRIMARY);assert(w.m_mode==w.DIALOG&&w.m_chatMessage==0);
 // Reporting from chat preserves the message, with a separate profile complaint.
 w.OpenProfile(8,true,71);w.Read(j,w.READ_PROFILE);w.Activate(w.REPORT);w.Layout();assert(!strcmp(w.m_confirm,"report_choice"));
 cursorX=w.m_reportChat.x+2;cursorY=uiStatic.cursorY=w.m_reportChat.y+2;assert(w.Hit()==w.REPORT_CHAT);
 w.Activate(w.REPORT_CHAT);assert(requests.back().url=="/api/v1/report"&&requests.back().body=="{\"message\":71}");replies[w.m_write]={200,"{}"};w.Frame();
 w.OpenProfile(8,true,72);w.Read(j,w.READ_PROFILE);w.Activate(w.REPORT);w.Layout();w.Activate(w.CONFIRM);assert(requests.back().body=="{\"player\":8}");replies[w.m_write]={200,"{}"};w.Frame();
 w.OpenProfile(10,true);w.Read(j,w.READ_PROFILE);w.Activate(w.REPORT);assert(!strcmp(w.m_confirm,"profile_report")&&w.m_chatMessage==0);w.Activate(w.CANCEL);
 // Guest cards explain the unavailable friendship instead of hiding the action.
 w.m_profile.account=false;w.Layout();auto count=requests.size();assert(w.m_primary.w&&w.m_report.w&&!w.m_block.w);w.Activate(w.PRIMARY);assert(requests.size()==count&&*w.m_notice);
 // Counts distinguish totals from unread events and reject older responses.
 CzmJson notices;assert(notices.Parse("{\"counts\":{\"revision\":100,\"friends\":11,\"unread\":3,\"requests\":1,\"new_friends\":2,\"following_updates\":4,\"chat_global\":5,\"chat_ru\":1}}"));Counts(notices);
 assert(CZM_SocialNotifications()==10&&CZM_ChatUnread()==6&&s_friends==11);
 CzmJson stale;assert(stale.Parse("{\"counts\":{\"revision\":99,\"unread\":99}}"));Counts(stale);assert(s_unread==3);
 w.m_tab=0;w.m_mode=w.LIST;w.m_ack=0;
 CzmJson listNotices;assert(listNotices.Parse("{\"people\":[{\"id\":8,\"notice\":41},{\"id\":9,\"notice\":42}],\"counts\":{\"revision\":101,\"new_friends\":2}}"));
 w.Read(listNotices,w.READ_LIST);assert(w.m_ack&&requests.back().url=="/api/v1/social/notifications/read"&&requests.back().body=="{\"kind\":\"friends\",\"ids\":[41,42]}");
 // An acknowledgement does not optimistically clear counters before success.
 assert(s_newFriends==2);replies[w.m_ack]={200,"{\"counts\":{\"revision\":102,\"new_friends\":0}}"};w.Frame();assert(s_newFriends==0);
 Counts(notices);assert(s_newFriends==0); // an older heartbeat cannot resurrect the badge
 identity++;CZM_SocialFrame();assert(CZM_SocialNotifications()==0&&CZM_ChatUnread()==0);
 ScreenWidth=1536;ScreenHeight=716;
 if(argc>1){drawTrace=true;if(strcmp(argv[1],"dialog")){
  w.OpenProfile(8,false);w.Read(j,w.READ_PROFILE);
  if(!strcmp(argv[1],"own")){w.m_profile.id=me;strcpy(w.m_profile.nick,"Kuro");strcpy(w.m_profile.status,"");}
  if(!strcmp(argv[1],"guest")){w.m_profile.account=false;strcpy(w.m_profile.relation,"none");strcpy(w.m_profile.status,"");}
  if(!strcmp(argv[1],"join")){strcpy(w.m_profile.server,"203.0.113.10:27015");strcpy(w.m_profile.map,"zm_survival");}
  if(!strcmp(argv[1],"report")){w.m_chatMessage=71;w.Activate(w.REPORT);}
 }else{w.m_target=8;w.Navigate(w.DIALOG);w.Read(j,w.READ_DIALOG);}w.Draw();}
}
'''


class SocialMenuTests(unittest.TestCase):
    def test_delayed_replies_retry_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            vector = VECTOR.replace("void RemoveAll(){v.clear();}", "void RemoveAll(){v.clear();} void Remove(int n){v.erase(v.begin()+n);} T&Tail(){return v.back();}")
            (p / "utlvector.h").write_text(vector)
            (p / "utlstring.h").write_text(STRING.replace("void Set(const char *v)", "void Clear(){s.clear();}void Set(const char *v)"))
            (p / "stub.h").write_text(STUB)
            for name in ["extdll_menu.h", "BaseMenu.h", "Utils.h", "Framework.h", "Scissor.h", "keydefs.h", "CzmMenu.h"]:
                (p / name).write_text('#include "stub.h"\n')
            (p / "CzmJson.h").write_text((ROOT / "czm/menu/CzmJson.h").read_text())
            source = (ROOT / "czm/menu/CzmSocial.cpp").read_text().replace('#include "../../common/czm_tab.h"', '#include "czm_tab.h"').replace("private:\n\tenum", "public:\n\tenum")
            from test_loading_errors import function
            shared=(ROOT/'czm/menu/CzmMenu.cpp').read_text()
            badges=function(shared,'int CZM_CountBadgeWidth(')+'\n'+function(shared,'void CZM_DrawCountBadge(')
            (p / "main.cpp").write_text(HARNESS + badges + source + SCENARIOS)
            exe = p / "social"
            subprocess.run(["g++", "-std=c++11", "-w", "-I"+folder, "-I"+str(ROOT/"common"), str(p/"main.cpp"), str(ROOT/"czm/menu/CzmJson.cpp"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
            preview = os.environ.get("CZM_SOCIAL_PREVIEW_DIR")
            if preview:
                output = Path(preview); output.mkdir(parents=True, exist_ok=True)
                for view in ["profile", "own", "guest", "join", "report", "dialog"]:
                    result = subprocess.run([str(exe), view], check=True, capture_output=True, text=True)
                    (output/(view+".tsv")).write_text(result.stdout)

    def test_chat_opens_the_same_card_with_message_context_in_every_room(self):
        import re
        source = (ROOT / "czm/menu/CzmChat.cpp").read_text()
        hits = re.search(r"enum EHit\n\t\{.*?\n\t\};", source, re.S).group()
        activate = re.search(r"void CCzmChat::Activate\( int hit \)\n\{.*?\n\}", source, re.S).group()
        harness = r'''
#include <cassert>
#include <vector>
#include <utility>
#include <cstddef>
struct Message{int player,id;};
struct Messages:std::vector<Message>{int Count()const{return size();}};
struct Room{Messages messages;double nextPoll;};
using CzmChatRoom=Room;
struct EngFuncs{static void CvarSetValue(const char*,float){}};
static std::vector<std::pair<int,int>> opened;
void CZM_OpenProfile(int player,int message){opened.push_back({player,message});}
bool CZM_OnlineBan(void*,void*,void*){return false;}void CZM_PlayClick(){}
#define ROOMS 3
class CCzmChat{public:
''' + hits + r'''
 bool m_bClosing=false;int m_iPopup=-1,m_iRoom=0;float m_flScroll=0,m_flVelocity=0;
 Room m_rooms[ROOMS];bool inputEnded=false;
 void Hide(){}void BeginInput(){}void Send(){}void Report(bool){}
 void EndInput(){inputEnded=true;}void Activate(int);
};
''' + activate + r'''
int main(){
 CCzmChat chat;
 for(int room=0;room<ROOMS;room++){
  chat.m_rooms[room].messages.push_back({8+room,70+room});chat.m_iRoom=room;
  for(int hit:{chat.HIT_PROFILE,chat.HIT_MESSAGE}){
   chat.inputEnded=false;chat.Activate(hit);
   assert(opened.back()==std::make_pair(8+room,70+room));
   assert(chat.inputEnded&&chat.m_iPopup==-1);
  }
 }
 auto count=opened.size();chat.m_bClosing=true;chat.Activate(chat.HIT_MESSAGE);assert(opened.size()==count);
}
'''
        with tempfile.TemporaryDirectory() as folder:
            cpp=Path(folder)/"chat.cpp";exe=Path(folder)/"chat"
            cpp.write_text(harness)
            subprocess.run(["g++","-std=c++11",str(cpp),"-o",str(exe)],check=True)
            subprocess.run([str(exe)],check=True)


if __name__ == "__main__": unittest.main()
