"""Run the native social window against delayed HTTPS replies and account changes."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from native_community_stub import STUB as COMMUNITY_STUB, HARNESS as COMMUNITY_HARNESS
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
// mainui Utils.h defines this macro before the profile presentation header.
#define Alpha(x) (((x) & 0xFF000000) >> 24)
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
const char*CZM_CurrentAvatarImage();void CZM_OpenSettings(int);void CZM_AccountShow(const char*,const char*);bool CZM_CopyText(const char*);void CZM_JoinAddress(const char*);void CZM_PlayClick();
bool CZM_LobbyCanInvite();
void CZM_LobbyInviteFriend(int);
void CZM_OpenLobbyById(const char*);
void CZM_DrawMapPreview(const char*,int,int,int,int,const char*);
bool CZM_RulesAllow(void(*)()=nullptr);void CZM_RulesRefused(int,void(*)()=nullptr);void CZM_ChatHidePlayer(int);
using HIMAGE=int;HIMAGE CZM_MapPreview(const char*);HIMAGE CZM_Image(const char*);const char*CZM_MapModeArt(const char*,const char*);void CZM_DrawCover(HIMAGE,int,int,int,int);
enum{CZM_LIMIT_TEXT,CZM_LIMIT_VOICE,CZM_LIMIT_PHOTO,CZM_LIMIT_COUNT};bool CZM_OnlineSupport();int CZM_SupportTagWidth(int);int CZM_DrawSupportTag(int,int,int);
bool CZM_OnlineLimited(int,char* =nullptr,size_t=0);void CZM_ModerationOpen();
unsigned CZM_TopColor(int);const char*CZM_TopCrown(int);int CZM_TopTagWidth(int,int);int CZM_DrawTopTag(int,int,int,int);void CZM_FormatPlaytime(int,char*,size_t);void CZM_ModerationTarget(int,const char*,int=0,int=0,const char* ="");
struct CzmServer{char address[64];char prot[8];char name[64];};int CZM_ServerCount();CzmServer *CZM_Server(int);void CZM_CleanName(const char*,char*,size_t);void CZM_DrawSliced(const char*,int,int,int,int,int,int,unsigned=0xffffffff);
'''
STUB += COMMUNITY_STUB + '\nbool CZM_ServerBlocked(const char*);\n'
HARNESS = r'''
#include "stub.h"
#include <map>
#include <cassert>
int ScreenWidth=1536,ScreenHeight=716,cursorX,cursorY;Cursor uiStatic;Stack stack;
static double now=100;static std::string key="legacy-device-key";static int me=7,ids,logins,lastButtonFont,identity=1;static bool authenticated=true,drawTrace;static bool russian=true;
static std::map<std::string,std::string> vars;static std::map<int,std::pair<int,std::string>> replies;
static std::vector<std::string> drawnLabels;
struct Request{int id;std::string url,body;};static std::vector<Request> requests;
const char*EngFuncs::GetCvarString(const char*k){return vars[k].c_str();}float EngFuncs::GetCvarFloat(const char*k){return atof(GetCvarString(k));}void EngFuncs::CvarSetString(const char*k,const char*v){vars[k]=v;}void EngFuncs::CvarSetValue(const char*k,float v){vars[k]=std::to_string(v);}double EngFuncs::DoubleTime(){return now;}
void UI_EnableTextInput(bool){}void CZM_Init(){}bool CZM_IsRussian(){return russian;}unsigned CZM_White(){return 0xffffffff;}unsigned CZM_Grey(){return PackRGBA(150,164,184,255);}
static std::map<int,std::string> loadedArt;
HIMAGE CZM_MapPreview(const char*){return 0;}const char*CZM_MapModeArt(const char*,const char*){return "gfx/czm/maps/_zombie.png";}
HIMAGE CZM_Image(const char*path){int id=(int)loadedArt.size()+1;loadedArt[id]=path;return id;}
void CZM_DrawCover(HIMAGE image,int x,int y,int w,int h){if(drawTrace)printf("C\t%d\t%d\t%d\t%d\t%s\n",x,y,w,h,loadedArt[image].c_str());}
HFont CZM_Font(int i){return i;}int CZM_FontHeight(HFont f){return (f==CZMF_PANEL_TITLE?42:f==CZMF_NICK?29:f==CZMF_LANG?24:f==CZMF_SMALL?17:f==CZMF_UI_TITLE?32:f==CZMF_UI_META?15:f==CZMF_UI_LABEL?20:f==CZMF_PROFILE_NAME?40:f==CZMF_PROFILE_TEXT?24:f==CZMF_CHAT_TEXT?23:21)*ScreenHeight/768;}
int CZM_TextWidth(HFont f,const char*s){int n=0;for(;*s;s++)if((*s&0xc0)!=0x80)n++;return n*CZM_FontHeight(f)*62/100;}
int CZM_WrapText(HFont f,const char*s,int w,int*starts,int max){int lines=0,i=0,last=0;starts[0]=0;for(;s[i]&&lines<max;){int from=i,n=0;while(s[i]&&(n*CZM_FontHeight(f)/2<w||!n)){i++;while((s[i]&0xc0)==0x80)i++;n++;}if(i==from)break;lines++;starts[lines]=i;last=i;}return lines;}
void CZM_WrapLine(const char*s,const int*starts,int n,char*out,size_t size){int len=std::min((int)size-1,starts[n+1]-starts[n]);memcpy(out,s+starts[n],len);out[len]=0;}
void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){drawnLabels.emplace_back(s);if(drawTrace){printf("T\t%d\t%d\t%d\t%d\t%u\t%u\t%s\n",x,y,w,CZM_FontHeight(f),c,just,s);}}
void UI_FillRect(int x,int y,int w,int h,unsigned c){if(drawTrace)printf("R\t%d\t%d\t%d\t%d\t%u\n",x,y,w,h,c);}
void CZM_DrawImage(const char*p,int x,int y,int w,int h,unsigned c){if(drawTrace)printf("I\t%d\t%d\t%d\t%d\t%u\t%s\n",x,y,w,h,c,p);}
void CZM_DrawPill(const char*,int x,int y,int w,int h,unsigned c){UI_FillRect(x,y,w,h,c);}
void CZM_DrawPanel(const CzmRect&r){UI_FillRect(r.x,r.y,r.w,r.h,PackRGBA(10,17,26,250));}
void CZM_DrawButton(const char*p,const CzmRect&r,const char*s,unsigned c,bool,int font){lastButtonFont=font;UI_FillRect(r.x,r.y,r.w,r.h,strstr(p,"primary")?PackRGBA(210,34,55,255):PackRGBA(31,43,59,255));CZM_DrawText(font,r.x+r.h/4,r.y+(r.h-CZM_FontHeight(font))/2,r.w-r.h/2,s,c,QM_CENTER);}
bool CZM_OnlineReady(){return true;}bool CZM_OnlineAccount(){return authenticated;}int CZM_OnlineIdentity(){return identity;}const char*CZM_OnlineKey(){return key.c_str();}int CZM_OnlinePlayer(){return me;}const char*CZM_OnlineUrl(const char*p){return p;}const char*CZM_AvatarFor(const char*,int){return "gfx/czm/ui/avatar.png";}
int CZM_NetRequest(const char*,const char*url,const char*,const char*body){requests.push_back({++ids,url,body});return ids;}
bool CZM_NetPoll(int id,int*status,CUtlString&body){auto i=replies.find(id);if(i==replies.end())return false;*status=i->second.first;body.Set(i->second.second.c_str());replies.erase(i);return true;}
void CZM_NetNewKey(char*out,size_t size){Q_strncpy(out,"0123456789abcdef0123456789abcdef",size);}int CZM_ServerCount(){return 0;}CzmServer *CZM_Server(int){return 0;}void CZM_CleanName(const char*in,char*out,size_t size){Q_strncpy(out,in,size);}void CZM_DrawSliced(const char*,int x,int y,int w,int h,int,int radius,unsigned c){if(drawTrace)printf("S\t%d\t%d\t%d\t%d\t%u\t%d\n",x,y,w,h,c,radius);}const char*CZM_CurrentAvatarImage(){return "gfx/czm/ui/avatar.png";}bool CZM_TranslationAvailable(){return true;}int CZM_TranslationStart(const char*t,bool){requests.push_back({++ids,"translation",t});return ids;}void CZM_OpenSettings(int){}void CZM_AccountShow(const char*,const char*){logins++;}bool CZM_CopyText(const char*){return true;}static std::string joinedCommunityServer;void CZM_JoinAddress(const char*address){joinedCommunityServer=address;}void CZM_PlayClick(){}
bool CZM_LobbyCanInvite(){return false;}
void CZM_LobbyInviteFriend(int){}
void CZM_OpenLobbyById(const char*){}
void CZM_DrawMapPreview(const char*,int,int,int,int,const char*){}
static bool rulesOk=true;static void(*rulesThen)()=nullptr;static int hiddenPlayer;
bool CZM_RulesAllow(void(*then)()){if(rulesOk)return true;rulesThen=then;return false;}
void CZM_RulesRefused(int,void(*then)()){rulesOk=false;rulesThen=then;}
void CZM_ChatHidePlayer(int id){hiddenPlayer=id;}
static bool support,textLimited;static int moderationOpened,moderationTarget,moderationMessage,supportTags;
bool CZM_OnlineSupport(){return support;}int CZM_SupportTagWidth(int h){return h*4;}
int CZM_DrawSupportTag(int x,int y,int h){supportTags++;UI_FillRect(x,y,h*4,h,PackRGBA(196,150,62,255));return h*4;}
bool CZM_OnlineLimited(int k,char*t,size_t n){if(k!=CZM_LIMIT_TEXT||!textLimited)return false;if(t&&n)Q_strncpy(t,"Чат ограничен модератором до 01.11 12:00. Спам",n);return true;}
void CZM_ModerationOpen(){moderationOpened++;}
static int topTags;unsigned CZM_TopColor(int place){return place<=100?PackRGBA(231,187,96,255):PackRGBA(150,150,150,255);}
const char*CZM_TopCrown(int){return "gfx/czm/ui/icon_crown_top.png";}
int CZM_TopTagWidth(int place,int h){return place>=1&&place<=100?h*4:0;}
int CZM_DrawTopTag(int x,int y,int h,int place){if(place<1||place>100)return 0;topTags++;UI_FillRect(x,y,h*4,h,CZM_TopColor(place));return h*4;}
void CZM_FormatPlaytime(int seconds,char*out,size_t n){snprintf(out,n,"%d ч %d мин",seconds/3600,seconds/60%60);}void CZM_ModerationTarget(int id,const char*,int message,int,const char*){moderationTarget=id;moderationMessage=message;}
'''
HARNESS += COMMUNITY_HARNESS + r'''
static std::string communityBlocked;bool CZM_ServerBlocked(const char*address){return communityBlocked==address;}
'''
SCENARIOS = r'''
int main(int argc,char**argv){
 CZM_SocialFrame();CZM_OpenFriends();auto&w=*menu_czmsocial;w.Frame();assert(w.m_read);
 int old=w.m_read;w.m_tab=1;w.Navigate(w.LIST);replies[old]={200,"{\"people\":[{\"id\":99,\"nick\":\"stale\"}]}"};w.Frame();assert(w.m_people.Count()==0);
 CzmJson j;assert(j.Parse("{\"profile\":{\"id\":8,\"nick\":\"Hunter\",\"account\":true,\"relation\":\"friend\",\"online\":true,\"status\":\"Выживаем вместе\",\"created\":1792240000,\"counts\":{\"friends\":234,\"followers\":47}},\"can_send\":true,\"messages\":[{\"id\":1,\"p\":8,\"t\":\"Привет! Заходи играть\",\"ts\":1792240000}]}"));
 w.m_target=8;w.Navigate(w.DIALOG);w.Read(j,w.READ_DIALOG);assert(w.m_canSend&&w.m_messages.Count()==1);
 strcpy(w.m_input,"Hello friend");w.Send();int send=w.m_write;auto payload=requests.back().body;replies[send]={0,""};w.Frame();assert(!w.m_write&&!strcmp(w.m_input,"Hello friend"));
 w.Send();assert(requests.back().body==payload);replies[w.m_write]={200,"{\"message\":{\"id\":2}}"};w.Frame();assert(!*w.m_input);
 // The rules come first; the typed message waits and goes after acceptance.
 strcpy(w.m_input,"After rules");rulesOk=false;size_t before=requests.size();w.Activate(w.SEND);assert(requests.size()==before&&rulesThen);
 rulesOk=true;rulesThen();rulesThen=nullptr;assert(requests.size()==before+1&&requests.back().body.find("After rules")!=std::string::npos);
 replies[w.m_write]={403,"{\"error\":\"rules\",\"version\":1}"};w.Frame();assert(!rulesOk&&rulesThen&&w.m_canSend&&!strcmp(w.m_input,"After rules"));
 rulesOk=true;rulesThen=nullptr;w.m_input[0]=0;
 // Blocking someone removes his messages from the public chat at once.
 w.m_target=8;w.Follow("block");replies[w.m_write]={200,"{\"profile\":{\"id\":8}}"};w.Frame();assert(hiddenPlayer==8);
 // A read follower list must not start a mark-seen/refetch request loop.
 w.m_tab=2;w.Navigate(w.LIST);CzmJson followers;assert(followers.Parse("{\"people\":[],\"counts\":{\"requests\":0},\"next\":-1}"));
 w.Read(followers,w.READ_LIST);assert(w.m_write==0);
 // A reply sent before logout cannot populate another account's window.
 int pending=w.m_read;identity++;me=9;CZM_SocialFrame();assert(!w.m_open&&w.m_messages.Count()==0);
 if(pending)replies[pending]={200,"{\"messages\":[{\"id\":55,\"t\":\"private old account\"}]}"};CZM_SocialFrame();assert(w.m_messages.Count()==0);
 authenticated=false;identity++;CZM_SocialFrame();CZM_OpenFriends();w.Layout();cursorX=w.m_prev.x+1;cursorY=w.m_prev.y+1;assert(w.Hit()==w.LOGIN);w.Activate(w.LOGIN);assert(logins==1);
 SocialButton(CZM_Rect(0,0,ScreenHeight*.18f,ScreenHeight*.07f),"Отправить");assert(lastButtonFont!=CZMF_LANG);
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
   assert(w.m_panel.w*w.m_panel.h<ScreenWidth*ScreenHeight*.9f);
   assert(w.m_panel.y+w.m_panel.h<ScreenHeight);
   CzmRect*buttons[]={&w.m_primary,&w.m_secondary,&w.m_edit,&w.m_settings,&w.m_report,&w.m_block,&w.m_join,&w.m_copy,&w.m_more,&w.m_back};
   // the own counters open the lists; nothing of the card leaves it or covers the header
   for(int i=0;i<3;i++){const CzmRect&r=w.m_profileCounts[i];assert(r.x>=w.m_panel.x&&r.x+r.w<=w.m_panel.x+w.m_panel.w&&r.y>w.m_back.y+w.m_back.h);
    cursorX=r.x+r.w/2;cursorY=uiStatic.cursorY=r.y+r.h/2;if(w.m_profile.id==me&&!w.m_editStatus)assert(w.Hit()==w.COUNT+i);}
   for(auto r:buttons)if(r->w){
    assert(r->x>=w.m_panel.x&&r->y>=w.m_panel.y);
    assert(r->x+r->w<=w.m_panel.x+w.m_panel.w&&r->y+r->h<=w.m_panel.y+w.m_panel.h);
    cursorX=r->x+r->w/2;cursorY=uiStatic.cursorY=r->y+r->h/2;assert(w.Hit());
    for(auto other:buttons)if(r!=other&&other->w)assert(r->x+r->w<=other->x||other->x+other->w<=r->x||r->y+r->h<=other->y||other->y+other->h<=r->y);
   }
  }
 }

 // Role cards keep project rows reachable; ordinary cards alone can show Telegram.
 for(auto resolution:{std::pair<int,int>{640,320},{800,360},{960,540},{1536,716},{2960,1440}}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;
  for(const char*role:{"support","moderator","tester","server_owner"})for(bool self:{false,true}){
   w.OpenProfile(8,true);w.Read(j,w.READ_PROFILE);strcpy(w.m_profile.role,role);w.m_profile.support=!strcmp(role,"support");
   strcpy(w.m_profile.telegram,"https://t.me/CzmPlayer");
   if(self){w.m_profile.id=me;strcpy(w.m_profile.relation,"self");}
   if(!strcmp(role,"server_owner")){
    w.m_profile.serverOwner=true;w.m_profile.ownedCount=5;strcpy(w.m_profile.project,"Project CZM");
    for(int i=0;i<5;i++){snprintf(w.m_profile.owned[i].address,64,"8.8.8.8:%d",27015+i);snprintf(w.m_profile.owned[i].name,388,"Project server %d",i+1);}
   }
   w.Draw();assert(w.m_panel.x>=0&&w.m_panel.y>=0&&w.m_panel.y+w.m_panel.h<=ScreenHeight);
   assert(!w.m_telegram.w);
   for(int i=0;i<w.m_profile.ownedCount;i++){
    const CzmRect&r=w.m_projectRows[i];assert(r.w>0&&r.h>=24);
    assert(r.x>=w.m_projectPanel.x&&r.x+r.w<=w.m_projectPanel.x+w.m_projectPanel.w);
    assert(r.y>w.m_back.y+w.m_back.h&&r.y+r.h<=w.m_panel.y+w.m_panel.h);
    cursorX=r.x+r.w/2;cursorY=uiStatic.cursorY=r.y+r.h/2;assert(w.Hit()==w.PROJECT+i);
    if(w.m_projectManage.w)assert(r.y+r.h<=w.m_projectManage.y);
   }
  }
 }
 ScreenWidth=1536;ScreenHeight=716;w.OpenProfile(8,true);w.Read(j,w.READ_PROFILE);
 strcpy(w.m_profile.telegram,"https://t.me/CzmPlayer");w.Draw();assert(w.m_telegram.w);
 cursorX=w.m_telegram.x+w.m_telegram.w/2;cursorY=uiStatic.cursorY=w.m_telegram.y+w.m_telegram.h/2;assert(w.Hit()==w.TELEGRAM);
 w.Activate(w.TELEGRAM);assert(communityMode=="telegram"&&communityPlayer==8);
 w.m_profile.telegram[0]=0;w.m_profile.serverOwner=true;w.m_profile.ownedCount=1;
 strcpy(w.m_profile.owned[0].address,"8.8.8.8:27015");w.Draw();
 communityBlocked="8.8.8.8:27015";joinedCommunityServer.clear();w.Activate(w.PROJECT);assert(joinedCommunityServer.empty()&&w.m_open);
 communityBlocked.clear();w.Activate(w.PROJECT);assert(joinedCommunityServer=="8.8.8.8:27015");

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
 w.m_profile.account=false;w.Layout();auto count=requests.size();assert(w.m_primary.w&&w.m_more.w&&!w.m_block.w);w.Activate(w.PRIMARY);assert(requests.size()==count&&*w.m_notice);
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
 // A muted player learns why and until when; without the details the plain words remain.
 assert(strstr(SocialError("muted"),"модератором")&&!strstr(SocialError("muted"),"01.11"));
 textLimited=true;assert(strstr(SocialError("muted"),"до 01.11 12:00"));textLimited=false;
 // SUPPORT: the tag shows on the official account; only a SUPPORT viewer gets the shield.
 CzmJson staff;assert(staff.Parse("{\"profile\":{\"id\":12,\"nick\":\"Support\",\"account\":true,\"relation\":\"none\",\"role\":\"support\",\"created\":1792240000}}"));
 w.OpenProfile(12,true);w.Read(staff,w.READ_PROFILE);assert(w.m_profile.support&&me!=12);drawnLabels.clear();w.Draw();assert(std::count(drawnLabels.begin(),drawnLabels.end(),"SUPPORT")==1&&!w.m_moderate.w);
 w.OpenProfile(8,true,71);w.Read(j,w.READ_PROFILE);assert(!w.m_profile.support);w.Layout();assert(!w.m_moderate.w);
 support=true;w.Layout();assert(w.m_moderate.w&&w.m_moderate.x+w.m_moderate.w<=w.m_panel.x+w.m_panel.w&&w.m_peer.x+w.m_peer.w<=w.m_moderate.x&&!w.m_settings.w);
 cursorX=w.m_moderate.x+2;cursorY=uiStatic.cursorY=w.m_moderate.y+2;assert(w.Hit()==w.MODERATE);w.KeyDown(1);w.KeyUp(1);
 assert(moderationTarget==8&&moderationMessage==71);
 w.OpenProfile(me,false);w.Read(j,w.READ_PROFILE);w.m_profile.id=me;w.Layout();
 // the own card: the shield next to the gear, each with its own action
 assert(w.m_moderate.w&&w.m_settings.w&&w.m_moderate.x+w.m_moderate.w<=w.m_settings.x&&w.m_peer.x+w.m_peer.w<=w.m_moderate.x);
 w.Activate(w.MODERATE);assert(moderationOpened==1);
 actorAdmin=true;w.Layout();assert(w.m_moderate.w>w.m_moderate.h);
 assert(w.m_peer.x+w.m_peer.w<=w.m_moderate.x&&w.m_moderate.x+w.m_moderate.w<=w.m_settings.x);
 communityMode.clear();w.Activate(w.MODERATE);assert(communityMode=="admin");w.Draw();actorAdmin=false;
 // another staff member has no actions: the service refuses them anyway
 w.OpenProfile(12,true);w.Read(staff,w.READ_PROFILE);w.Layout();assert(!w.m_moderate.w);
 support=false;
 // ⋯ on another player's card: report, block, end the friendship; Escape or a tap outside closes it
 w.OpenProfile(8,true,71);w.Read(j,w.READ_PROFILE);w.Layout();assert(w.m_more.w&&!w.m_report.w&&!w.m_secondary.w);
 cursorX=w.m_more.x+2;cursorY=uiStatic.cursorY=w.m_more.y+2;assert(w.Hit()==w.MORE);w.KeyDown(1);w.KeyUp(1);assert(w.m_moreOpen);
 w.Layout();assert(w.m_moreCount==4&&w.m_moreKind[0]==w.BLOCK&&w.m_moreKind[1]==w.SECONDARY&&w.m_moreKind[2]==w.REPORT&&w.m_moreKind[3]==w.CANCEL);
 for(int i=0;i<w.m_moreCount;i++){const CzmRect&r=w.m_moreRows[i];assert(r.x>=w.m_moreSheet.x&&r.y>=w.m_moreSheet.y&&r.x+r.w<=w.m_moreSheet.x+w.m_moreSheet.w&&r.y+r.h<=w.m_moreSheet.y+w.m_moreSheet.h);
  cursorX=r.x+2;cursorY=uiStatic.cursorY=r.y+2;assert(w.Hit()==w.MORE_ROW+i);}
 w.Draw();cursorX=1;cursorY=uiStatic.cursorY=1;assert(w.Hit()==w.MORE_CLOSE);w.KeyDown(1);w.KeyUp(1);assert(!w.m_moreOpen&&w.m_open);
 w.Activate(w.MORE);w.KeyDown(27);assert(!w.m_moreOpen&&w.m_open);
 w.Activate(w.MORE);w.Layout();w.Activate(w.MORE_ROW+2);assert(!w.m_moreOpen&&!strcmp(w.m_confirm,"report_choice"));w.Activate(w.CANCEL);
 w.Activate(w.MORE);w.Layout();w.Activate(w.MORE_ROW+0);assert(!strcmp(w.m_confirm,"block"));w.Activate(w.CANCEL);
 w.Activate(w.MORE);w.Layout();w.Activate(w.MORE_ROW+1);assert(!strcmp(w.m_confirm,"unfollow"));w.Activate(w.CANCEL);
 // a blocked player: unblocking is on the card, the menu keeps the report
 strcpy(w.m_profile.relation,"blocked");w.Layout();assert(w.m_block.w&&!w.m_primary.w&&w.m_more.w);
 w.Activate(w.MORE);w.Layout();assert(w.m_moreCount==2&&w.m_moreKind[0]==w.REPORT);w.Activate(w.MORE_CLOSE);
 // the own card: the counters open the lists, the status row edits, the gear opens the profile settings
 w.OpenProfile(me,false);w.Read(j,w.READ_PROFILE);w.m_profile.id=me;w.Layout();assert(!w.m_more.w&&!w.m_primary.w&&w.m_settings.w);
 w.Activate(w.COUNT+1);assert(w.m_mode==w.LIST&&w.m_tab==2);
 w.OpenProfile(me,false);w.Read(j,w.READ_PROFILE);w.m_profile.id=me;w.Layout();w.Activate(w.COUNT+2);assert(w.m_tab==3);
 // Every role and the Top tier remain readable; themes never grant roles.
 for(auto resolution:{std::pair<int,int>{640,320},{960,540},{1536,716},{1024,768}}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;
  for(int theme=0;theme<4;theme++){
   w.OpenProfile(me,true);w.Read(j,w.READ_PROFILE);w.m_profile.id=me;
   strcpy(w.m_profile.role,"support");w.m_profile.support=true;w.m_profile.roleFlags=15;
   w.m_profile.serverOwner=true;w.m_profile.topPlace=5;w.m_profile.ownedCount=5;
   strcpy(w.m_profile.theme,CzmProfileStyle::ThemeKey(theme));w.m_appear=0;
   drawnLabels.clear();w.Draw();
   for(const char*label:{"SUPPORT","MODERATOR","OFFICIAL TESTER CZM","SERVER OWNER","TOP 10"})assert(std::count(drawnLabels.begin(),drawnLabels.end(),label)==1);
   assert(w.m_panel.y>=0&&w.m_panel.y+w.m_panel.h<=ScreenHeight);
   assert(w.m_theme.w&&w.m_nickEdit.w);
   w.Activate(w.THEME);w.Layout();assert(w.m_themeOpen);
   assert(w.m_themePanel.y>=0&&w.m_themePanel.y+w.m_themePanel.h<=ScreenHeight);
   for(int i=0;i<4;i++){
    const auto&r=w.m_themeOptions[i];assert(r.x>=w.m_themePanel.x&&r.x+r.w<=w.m_themePanel.x+w.m_themePanel.w);
    assert(r.y>=w.m_themePanel.y&&r.y+r.h<=w.m_themeCancel.y);
    cursorX=r.x+r.w/2;cursorY=uiStatic.cursorY=r.y+r.h/2;assert(w.Hit()==w.THEME_PICK+i);
   }
   w.Activate(w.THEME_CANCEL);assert(!w.m_themeOpen);
  }
 }
 ScreenWidth=1536;ScreenHeight=716;w.OpenProfile(me,true);w.Read(j,w.READ_PROFILE);w.m_profile.id=me;w.Layout();
 w.Activate(w.THEME);w.Activate(w.THEME_PICK+1);w.Activate(w.THEME_SAVE);
 assert(requests.back().url=="/api/v1/social/theme"&&requests.back().body=="{\"theme\":\"frost\"}");
 replies[w.m_write]={200,"{\"profile\":{\"id\":"+std::to_string(me)+",\"nick\":\"Kuro\",\"account\":true,\"relation\":\"self\",\"theme\":\"frost\"}}"};
 w.Frame();assert(!w.m_themeOpen&&!strcmp(w.m_profile.theme,"frost"));
 // The card rises into place; no callback changes another account's card.
 w.OpenProfile(8,false);w.Read(j,w.READ_PROFILE);assert(w.m_appear>0);
 w.m_appear=0;w.Layout();const int risen=w.m_panel.y;
 w.m_appear=EngFuncs::DoubleTime();w.Layout();assert(w.m_panel.y>risen);w.m_appear=0;

 // A body tap is inert; separate message actions keep the original report target.
 w.m_target=8;w.Navigate(w.DIALOG);w.Read(j,w.READ_DIALOG);strcpy(w.m_messages[0].text,"Hello, join our game!");
 for(auto resolution:{std::pair<int,int>{640,320},{800,360},{960,540},{1536,716},{2960,1440}}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;w.Layout();
  const int top=w.m_clip.y+w.m_clip.h-w.DialogRowHeight(0)+CzmConversation::DateHeight();
  auto b=w.MessageBubble(0,top);assert(b.canTranslate);
  cursorX=b.body.x+b.body.w/2;cursorY=uiStatic.cursorY=b.body.y+b.body.h/2;assert(w.Hit()==0);
  cursorX=b.menu.x+b.menu.w/2;cursorY=uiStatic.cursorY=b.menu.y+b.menu.h/2;assert(w.Hit()==w.MESSAGE_MENU);
  w.Activate(w.Hit());assert(w.m_messageMenu==1&&w.m_messageRows==3);
  w.Activate(w.MSG_REPORT);assert(!strcmp(w.m_confirm,"report:1")&&!strcmp(w.m_reportQuote,"Hello, join our game!"));w.Activate(w.CANCEL);
  w.m_messages[0].player=me;w.Activate(w.MESSAGE_MENU);assert(w.m_messageRows==2&&w.m_messageKinds[0]==w.MSG_COPY&&w.m_messageKinds[1]==w.MSG_CLOSE);w.Activate(w.MSG_CLOSE);w.m_messages[0].player=8;
  russian=false;b=w.MessageBubble(0,top);assert(!b.canTranslate);russian=true;
 }
 ScreenWidth=1536;ScreenHeight=716;w.Layout();w.Activate(w.MESSAGE_MENU);w.Activate(w.MSG_REPORT);w.m_write=0;w.Activate(w.CONFIRM);
 assert(requests.back().body=="{\"private_message\":1}");replies[w.m_write]={200,"{}"};w.Frame();
 w.m_messages[0].deleted=true;w.Activate(w.MESSAGE_MENU);assert(!w.m_messageMenu);w.m_messages[0].deleted=false;
 ScreenWidth=1536;ScreenHeight=716;
 if(argc>1){drawTrace=true;if(strcmp(argv[1],"dialog")&&strcmp(argv[1],"translated")&&strcmp(argv[1],"friends")){
  w.OpenProfile(8,false);w.Read(j,w.READ_PROFILE);
  if(!strncmp(argv[1],"own",3)||!strcmp(argv[1],"themes")){w.m_profile.id=me;strcpy(w.m_profile.nick,"Kuro");strcpy(w.m_profile.status,"Help Support");strcpy(w.m_profile.role,"support");w.m_profile.support=true;w.m_profile.topPlace=5;w.m_profile.topSeconds=780;support=actorAdmin=true;}
  if(!strcmp(argv[1],"own_frost"))strcpy(w.m_profile.theme,"frost");
  if(!strcmp(argv[1],"themes")){w.Layout();w.Activate(w.THEME);}
  if(!strcmp(argv[1],"add"))strcpy(w.m_profile.relation,"none");
  if(!strcmp(argv[1],"guest")){w.m_profile.account=false;strcpy(w.m_profile.relation,"none");strcpy(w.m_profile.status,"");}
  if(!strcmp(argv[1],"join")){strcpy(w.m_profile.server,"203.0.113.10:27015");strcpy(w.m_profile.map,"zm_survival");}
  if(!strcmp(argv[1],"report")){w.m_chatMessage=71;w.Activate(w.REPORT);}
  if(!strcmp(argv[1],"more")){strcpy(w.m_profile.relation,"friend");w.Activate(w.MORE);}
  if(!strcmp(argv[1],"edit")){w.m_profile.id=me;w.m_editStatus=true;strcpy(w.m_input,"Выживаем до рассвета");}
 }else if(!strcmp(argv[1],"friends")){
  w.Navigate(w.LIST);w.m_tab=0;w.m_loaded=true;s_friends=3;s_onlineFriends=2;
  for(int i=0;i<3;i++){Person person={};person.id=20+i;person.account=true;person.online=i<2;strcpy(person.relation,"friend");strcpy(person.nick,i==0?"NK — Azaro":i==1?"свага":"DedSad");person.lastSeen=1792240000;
   if(i==0){person.playing=true;strcpy(person.server,"8.8.8.8:27015");strcpy(person.map,"ze_minecraft");person.togetherCount=3;person.togetherSize=6;}w.m_people.AddToTail(person);}
 }else{
  w.m_target=8;w.Navigate(w.DIALOG);w.Read(j,w.READ_DIALOG);strcpy(w.m_profile.nick,"свага");w.m_messages.RemoveAll();
  const char*texts[]={"Привет! Сегодня играем?","Да, чуть позже зайду","Can you help me on this map?","Да, присоединяйся ко мне","Хорошо, сейчас зайду"};
  for(int i=0;i<5;i++){Message message={};message.id=100+i;message.player=i%2?me:8;message.time=1792240000+i*60;strcpy(message.text,texts[i]);w.m_messages.AddToTail(message);}
  if(!strcmp(argv[1],"translated")){CZM_Translate(texts[2]);replies[requests.back().id]={200,"{\"text\":\"Можешь помочь мне на этой карте?\"}"};now+=.03;CZM_TranslationFrame();}
 }w.m_appear=0;w.Draw();}
}
'''


class SocialMenuTests(unittest.TestCase):
    def test_delayed_replies_retry_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            vector = VECTOR.replace("void RemoveAll(){v.clear();}", "void RemoveAll(){v.clear();} void Remove(int n){v.erase(v.begin()+n);} T&Tail(){return v.back();}")
            (p / "utlvector.h").write_text(vector)
            (p / "utlstring.h").write_text(STRING.replace("void Set(const char *v)", "void Clear(){s.clear();}void Set(const char *v)"))
            # the profile card draws with the shared CZM surfaces and their fonts
            (p / "stub.h").write_text(STUB.replace("CZMF_NICK,QM_CENTER=1", "CZMF_NICK,CZMF_TILE_STATUS,CZMF_UI_TITLE,CZMF_UI_ACTION,CZMF_UI_LABEL,CZMF_UI_META,CZMF_PROFILE_NAME,CZMF_PROFILE_TEXT,CZMF_CHAT_TEXT,QM_LEFT=0,QM_CENTER=1"))
            for name in ["extdll_menu.h", "BaseMenu.h", "Utils.h", "Framework.h", "Scissor.h", "keydefs.h", "CzmMenu.h"]:
                (p / name).write_text('#include "stub.h"\n')
            (p / "CzmJson.h").write_text((ROOT / "czm/menu/CzmJson.h").read_text())
            (p / "CzmDesign.h").write_text((ROOT / "czm/menu/CzmDesign.h").read_text())
            (p / "CzmProfileStyle.h").write_text((ROOT / "czm/menu/CzmProfileStyle.h").read_text())
            for name in ["CzmConversationStyle.h", "CzmTranslation.h", "CzmTextLanguage.h", "CzmTranslation.cpp"]:
                (p / name).write_text((ROOT / "czm/menu" / name).read_text())
            source = (ROOT / "czm/menu/CzmSocial.cpp").read_text().replace('#include "../../common/czm_tab.h"', '#include "czm_tab.h"').replace("private:\n\tenum", "public:\n\tenum")
            from test_loading_errors import function
            shared=(ROOT/'czm/menu/CzmMenu.cpp').read_text()
            badges=function(shared,'int CZM_CountBadgeWidth(')+'\n'+function(shared,'void CZM_DrawCountBadge(')
            (p / "main.cpp").write_text(HARNESS + badges + source + SCENARIOS)
            exe = p / "social"
            subprocess.run(["g++", "-std=c++11", "-w", "-I"+folder, "-I"+str(ROOT/"common"), str(p/"main.cpp"), str(p/"CzmTranslation.cpp"), str(ROOT/"czm/menu/CzmJson.cpp"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
            preview = os.environ.get("CZM_SOCIAL_PREVIEW_DIR")
            if preview:
                output = Path(preview); output.mkdir(parents=True, exist_ok=True)
                for view in ["profile", "own", "own_frost", "themes", "add", "guest", "join", "report", "dialog", "translated", "friends", "more", "edit"]:
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
struct Message{int player,id;char text[1604];};using CzmChatMessage=Message;
struct Messages:std::vector<Message>{int Count()const{return size();}};
struct Room{Messages messages;double nextPoll;};
using CzmChatRoom=Room;
struct EngFuncs{static void CvarSetValue(const char*,float){}};
static std::vector<std::pair<int,int>> opened;
void CZM_OpenProfile(int player,int message){opened.push_back({player,message});}
bool CZM_OnlineBan(void*,void*,void*){return false;}void CZM_PlayClick(){}bool CZM_CopyText(const char*){return true;}void CZM_Translate(const char*){}bool CZM_IsRussian(){return true;}
#define ROOMS 3
#define MAX_MESSAGES 100
class CCzmChat{public:
''' + hits + r'''
 bool m_bClosing=false,m_reportConfirm=false;int m_popupId=0,m_iPopup=-1,m_iRoom=0;float m_flScroll=0,m_flVelocity=0;
 Room m_rooms[ROOMS];bool inputEnded=false;
 void Toast(const char*){}void Hide(){}void BeginInput(){}void Send(){}void Report(bool){}
 void EndInput(){inputEnded=true;}void Activate(int);
};
''' + activate + r'''
int main(){
 CCzmChat chat;
 for(int room=0;room<ROOMS;room++){
  chat.m_rooms[room].messages.push_back({8+room,70+room});chat.m_iRoom=room;
  for(int hit:{chat.HIT_PROFILE}){
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
