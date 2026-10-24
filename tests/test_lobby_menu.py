"""Exercise real native lobby drawing, hit regions and requests without Android."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_social_menu import STUB as SOCIAL_STUB
from test_tab_avatars import VECTOR, STRING

ROOT = Path(__file__).resolve().parents[1]
STUB = SOCIAL_STUB.replace(
    'CZMF_PANEL_TEXT,CZMF_LANG,CZMF_SMALL,CZMF_PANEL_TITLE,CZMF_NICK,',
    'CZMF_PANEL_TEXT,CZMF_LANG,CZMF_SMALL,CZMF_PANEL_TITLE,CZMF_NICK,CZMF_TILE_STATUS,CZMF_UI_TITLE,CZMF_UI_ACTION,CZMF_UI_LABEL,CZMF_UI_META,QM_LEFT=0,')
STUB = STUB.replace('using HFont=int;', 'using HFont=int;using HIMAGE=int;')
STUB = STUB.replace('char name[64];};', 'char name[64];char map[64];int players,maxplayers,ping;double answerTime;};')
STUB = STUB.replace('static double DoubleTime();', 'static double DoubleTime();template<class...T>static void ClientCmdF(bool,const char*,T...){}')
STUB += r'''
bool CZM_OnlinePlayAllowed();bool CZM_QuickPlayActive();void CZM_LobbyInviteFrame();
void CZM_LobbyVoiceStart(const char*,const char*);void CZM_LobbyVoiceStop();void CZM_LobbyVoiceMic(bool);
bool CZM_LobbyVoiceMicOn();bool CZM_LobbyVoiceSpeaking(int);int CZM_LobbyVoiceStatus();
void CZM_LobbyVoiceLocalMute(int,bool);bool CZM_LobbyVoiceIsMuted(int);
void CZM_LobbyServerPickerStart();void CZM_OpenFriends();void CZM_OpenProfile(int);
HIMAGE CZM_MapPreview(const char*);HIMAGE CZM_Image(const char*);const char*CZM_MapModeArt(const char*,const char*);
void CZM_DrawCover(HIMAGE,int,int,int,int);
'''
HARNESS = r'''
#include "stub.h"
#include <map>
#include <set>
#include <cassert>
int ScreenWidth=1536,ScreenHeight=716,cursorX,cursorY;Cursor uiStatic;Stack stack;
static bool russian=true,micOn=false,trace=false,drawSpeaking=false;
static int player=7,identity=1,nextRequest=0;static double now=100;
static std::set<int> muted;static std::string lastUrl,lastBody;
static std::map<std::string,std::string> vars;
static std::map<int,std::pair<int,std::string>> replies;
HFont CZM_Font(int id){return id;}
int CZM_FontHeight(HFont f){int h=f==CZMF_UI_TITLE?32:f==CZMF_UI_ACTION?26:f==CZMF_UI_LABEL?20:f==CZMF_UI_META?15:f==CZMF_SMALL?17:21;return std::max(1,h*ScreenHeight/768);}
int CZM_TextWidth(HFont f,const char*s){int n=0;for(;*s;s++)if((*s&0xc0)!=0x80)n++;return n*CZM_FontHeight(f)*56/100;}
void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){if(trace)printf("T\t%d\t%d\t%d\t%d\t%u\t%u\t%s\n",x,y,w,f,c,just,s);}
void UI_FillRect(int x,int y,int w,int h,unsigned c){assert(w>=0&&h>=0);if(trace)printf("R\t%d\t%d\t%d\t%d\t%u\n",x,y,w,h,c);}
void CZM_DrawSliced(const char*p,int x,int y,int w,int h,int border,int radius,unsigned c){assert(w>=0&&h>=0);if(trace)printf("S\t%d\t%d\t%d\t%d\t%u\t%d\n",x,y,w,h,c,radius);}
void CZM_DrawImage(const char*p,int x,int y,int w,int h,unsigned c){assert(w>=0&&h>=0);if(trace)printf("I\t%d\t%d\t%d\t%d\t%u\t%s\n",x,y,w,h,c,p);}
void CZM_DrawCover(HIMAGE,int x,int y,int w,int h){if(trace)printf("M\t%d\t%d\t%d\t%d\n",x,y,w,h);}
HIMAGE CZM_MapPreview(const char*){return 0;}HIMAGE CZM_Image(const char*){return 1;}
const char*CZM_MapModeArt(const char*,const char*){return "gfx/czm/maps/_zombie.png";}
void CZM_DrawPill(const char*,int x,int y,int w,int h,unsigned c){UI_FillRect(x,y,w,h,c);}
void CZM_DrawPanel(const CzmRect&r){UI_FillRect(r.x,r.y,r.w,r.h,0xffffffff);}
void CZM_DrawButton(const char*,const CzmRect&r,const char*,unsigned,bool,int){UI_FillRect(r.x,r.y,r.w,r.h,0xffffffff);}
void CZM_Init(){}bool CZM_IsRussian(){return russian;}unsigned CZM_White(){return 0xffffffff;}unsigned CZM_Grey(){return PackRGBA(155,166,184,255);}
const char*EngFuncs::GetCvarString(const char*k){return vars[k].c_str();}float EngFuncs::GetCvarFloat(const char*k){return atof(GetCvarString(k));}
void EngFuncs::CvarSetString(const char*k,const char*v){vars[k]=v;}void EngFuncs::CvarSetValue(const char*k,float v){vars[k]=std::to_string(v);}double EngFuncs::DoubleTime(){return now;}
void UI_EnableTextInput(bool){}bool CZM_OnlineReady(){return true;}bool CZM_OnlineAccount(){return true;}bool CZM_OnlinePlayAllowed(){return true;}bool CZM_QuickPlayActive(){return false;}
int CZM_OnlineIdentity(){return identity;}int CZM_OnlinePlayer(){return player;}const char*CZM_OnlineKey(){return "test";}const char*CZM_OnlineUrl(const char*p){return p;}
const char*CZM_AvatarFor(const char*,int){return "gfx/czm/ui/avatar.png";}
int CZM_NetRequest(const char*,const char*url,const char*,const char*body){lastUrl=url;lastBody=body;return ++nextRequest;}
bool CZM_NetPoll(int id,int*status,CUtlString&body){auto it=replies.find(id);if(it==replies.end())return false;*status=it->second.first;body.Set(it->second.second.c_str());replies.erase(it);return true;}
void CZM_NetNewKey(char*out,size_t n){Q_strncpy(out,"native-lobby-test-nonce-001",n);}
int CZM_ServerCount(){return 0;}CzmServer*CZM_Server(int){return nullptr;}void CZM_CleanName(const char*in,char*out,size_t n){Q_strncpy(out,in,n);}
void CZM_LobbyVoiceStart(const char*,const char*){}void CZM_LobbyVoiceStop(){micOn=false;}void CZM_LobbyVoiceMic(bool v){micOn=v;}
bool CZM_LobbyVoiceMicOn(){return micOn;}bool CZM_LobbyVoiceSpeaking(int id){return drawSpeaking&&id==8;}int CZM_LobbyVoiceStatus(){return 2;}
void CZM_LobbyVoiceLocalMute(int id,bool v){if(v)muted.insert(id);else muted.erase(id);}bool CZM_LobbyVoiceIsMuted(int id){return muted.count(id);}
void CZM_LobbyInviteFrame(){}void CZM_LobbyServerPickerStart(){}void CZM_OpenFriends(){}void CZM_OpenProfile(int){}
void CZM_AccountShow(const char*,const char*){}void CZM_PlayClick(){}
'''
SCENARIOS = r'''
static void clear(CCzmLobby&w){w.m_request=0;w.m_kind=0;w.m_busy=false;}
static bool inside(const CzmRect&a,const CzmRect&b){return a.x>=b.x&&a.y>=b.y&&a.w>0&&a.h>0&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h;}
static bool overlap(const CzmRect&a,const CzmRect&b){return a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;}
static int hit(CCzmLobby&w,const CzmRect&r){cursorX=r.x+r.w/2;cursorY=r.y+r.h/2;return w.Hit();}
static void populate(CCzmLobby&w){
 strcpy(w.m_room,"native-test-room");strcpy(w.m_roomTitle,"Zombie Team");strcpy(w.m_serverAddress,"203.0.113.5:27015");strcpy(w.m_pickedName,"Night Killers · Zombie Escape");strcpy(w.m_pickedMap,"ze_atix_panic_v1_fix");
 w.m_pickedPlayers=21;w.m_pickedSlots=32;w.m_owner=7;w.m_capacity=6;w.m_memberCount=3;
 for(int i=0;i<3;i++){auto&m=w.m_members[i];m.id=7+i;m.ready=i!=2;snprintf(m.nick,sizeof(m.nick),"%s",i==0?"Kuro":i==1?"Hunter":"Shadow");strcpy(m.avatar,"1");}
}
int main(int argc,char**argv){
 auto&w=*menu_czmlobby;populate(w);strcpy(w.m_title,"Zombie Team");
 for(auto resolution:{std::pair<int,int>{1536,716},{960,540},{800,360},{1024,768},{1280,720},{2960,1440},{640,320}}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;
  for(int lang=0;lang<2;lang++)for(int capacity=2;capacity<=6;capacity++)for(int stage=0;stage<3;stage++){
   russian=lang==0;w.m_stage=stage;w.m_capacity=capacity;w.m_memberCount=std::min(3,capacity);w.m_cardCount=0;w.m_selectedMemberId=0;w.Layout();
   assert(w.m_panel.x>0&&w.m_panel.y>=0);assert(w.m_panel.x+w.m_panel.w<ScreenWidth);assert(w.m_panel.y+w.m_panel.h<ScreenHeight);
   assert(inside(w.m_back,w.m_panel));
   if(stage==w.CREATE){
    assert(inside(w.m_titleRect,w.m_panel)&&inside(w.m_primary,w.m_panel));
    assert(inside(w.m_buttons[2],w.m_cardsRect[0]));
    for(int i=0;i<5;i++){assert(inside(w.m_capacityRect[i],w.m_panel));assert(hit(w,w.m_capacityRect[i])==w.CAPACITY+i);if(i)assert(!overlap(w.m_capacityRect[i-1],w.m_capacityRect[i]));}
    for(int i=0;i<2;i++){assert(hit(w,w.m_visibilityRect[i])==w.PUBLIC_ACCESS+i);assert(hit(w,w.m_languageRect[i])==w.LANGUAGE+i);}
   }else if(stage==w.SEARCH){
    for(int i=0;i<6;i++){assert(inside(w.m_filterRect[i],w.m_panel));assert(hit(w,w.m_filterRect[i])==(i<3?w.FILTER_MODE+i:w.FILTER_LANGUAGE+i-3));if(i)assert(!overlap(w.m_filterRect[i-1],w.m_filterRect[i]));}
    for(int i=0;i<4;i++)assert(hit(w,w.m_cardsRect[i])==w.NONE);
    assert(w.m_buttons[2].w==0);assert(hit(w,w.m_buttons[0])==w.NONE);
   }else{
    for(int i=0;i<capacity;i++){assert(inside(w.m_membersRect[i],w.m_panel));assert(w.m_membersRect[i].h>=20);for(int j=0;j<i;j++)assert(!overlap(w.m_membersRect[i],w.m_membersRect[j]));assert(!overlap(w.m_membersRect[i],w.m_chatRect));}
    assert(inside(w.m_textRect,w.m_chatRect)&&inside(w.m_sendRect,w.m_chatRect));
    assert(inside(w.m_micRect,w.m_chatRect));assert(!overlap(w.m_micRect,w.m_textRect));
    for(int i=0;i<5;i++){assert(inside(w.m_buttons[i],w.m_panel));assert(!overlap(w.m_buttons[i],w.m_chatRect));for(int j=0;j<i;j++)assert(!overlap(w.m_buttons[i],w.m_buttons[j]));}
   }
   w.Draw();
  }
 }
 ScreenWidth=1536;ScreenHeight=716;russian=true;clear(w);w.m_stage=w.CREATE;w.Action(w.CAPACITY+2);assert(w.m_capacity==4);w.Action(w.LANGUAGE+1);assert(w.m_language==1);w.Action(w.PRIVATE_ACCESS);assert(w.m_private);
 w.Action(w.MAKE);assert(lastBody.find("\"capacity\":4")!=std::string::npos&&lastBody.find("\"language\":\"en\"")!=std::string::npos&&lastBody.find("\"visibility\":\"private\"")!=std::string::npos);
 clear(w);w.m_open=true;w.m_stage=w.SEARCH;w.m_offset=8;w.Action(w.FILTER_MODE+1);assert(w.m_offset==0&&lastUrl.find("mode=ze")!=std::string::npos);
 clear(w);w.Action(w.FILTER_LANGUAGE+2);assert(lastUrl.find("language=en")!=std::string::npos);
 populate(w);w.m_stage=w.ROOM;clear(w);w.m_private=false;w.Layout();assert(hit(w,w.m_membersRect[4])==w.INVITE);
 player=8;assert(hit(w,w.m_membersRect[4])==w.NONE);w.Action(w.MEMBER);assert(w.m_selectedMemberId==7);w.Action(w.MODAL_LOCAL_MUTE);assert(muted.count(7));
 player=7;clear(w);w.m_selectedMemberId=0;assert(!w.CanStart());w.m_members[2].ready=true;assert(w.CanStart());
 w.Action(w.LAUNCH);assert(lastUrl.find("/launch")!=std::string::npos);clear(w);
 // Account changes clear the former room and voice state.
 micOn=true;w.ResetSession();assert(!w.HasRoom()&&!micOn);
 if(argc>1){
  std::string view=argv[1];populate(w);strcpy(w.m_title,"Zombie Team");w.m_private=false;w.m_cardCount=0;w.m_chatCount=0;w.m_filterMode=w.m_filterLanguage=0;w.m_next=-1;w.m_offset=0;w.m_stage=w.ROOM;w.m_selectedMemberId=0;w.m_notice[0]=0;trace=true;drawSpeaking=true;
  if(view=="create")w.m_stage=w.CREATE;
  if(view=="search"||view=="catalog")w.m_stage=w.SEARCH;
  if(view=="catalog"){
   w.m_cardCount=3;for(int i=0;i<3;i++){auto&r=w.m_cards[i];strcpy(r.title,i==0?"Ночной отряд":i==1?"Escape together":"Команда Kuro");strcpy(r.id,"test-room");strcpy(r.address,"203.0.113.5:27015");strcpy(r.language,i==1?"en":"ru");strcpy(r.map,i==2?"zm_alpha":"ze_atix_panic_v1_fix");r.count=i+2;r.capacity=6;}
  }
  if(view=="member")w.m_selectedMemberId=8;
  if(view=="solo")w.m_memberCount=1;
  w.Draw();
 }
 puts("NATIVE_LOBBY_OK");
}
'''

class LobbyNativeTests(unittest.TestCase):
    def test_layout_touch_requests_and_role_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            (p/'utlvector.h').write_text(VECTOR)
            (p/'utlstring.h').write_text(STRING)
            (p/'stub.h').write_text(STUB)
            for name in ['extdll_menu.h','BaseMenu.h','Utils.h','Framework.h','keydefs.h','CzmMenu.h']:
                (p/name).write_text('#include "stub.h"\n')
            for name in ['CzmJson.h','CzmDesign.h']:
                (p/name).write_text((ROOT/'czm/menu'/name).read_text())
            source=(ROOT/'czm/menu/CzmLobby.cpp').read_text().replace('private:\n    enum','public:\n    enum')
            (p/'main.cpp').write_text(HARNESS+source+SCENARIOS)
            exe=p/'lobby'
            subprocess.run(['g++','-std=c++11','-Wall','-I'+folder,str(p/'main.cpp'),str(ROOT/'czm/menu/CzmJson.cpp'),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
            out=os.environ.get('CZM_LOBBY_PREVIEW_DIR')
            if out:
                dest=Path(out);dest.mkdir(parents=True,exist_ok=True)
                for view in ['create','search','catalog','room','solo','member']:
                    r=subprocess.run([str(exe),view],capture_output=True,text=True,check=True)
                    (dest/(view+'.tsv')).write_text(r.stdout)

if __name__=='__main__':unittest.main()
