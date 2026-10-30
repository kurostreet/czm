"""Exercise real chat hit testing, language hints, translation cache and wrapped geometry."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_social_menu import STUB,HARNESS
from test_tab_avatars import VECTOR,STRING
from test_loading_errors import function

ROOT=Path(__file__).resolve().parents[1]

class ChatTranslationTests(unittest.TestCase):
    def test_public_message_actions_language_switching_and_cache_isolation(self):
        source=(ROOT/'czm/menu/CzmChat.cpp').read_text()
        hits=re.search(r'enum EHit\n\t\{.*?\n\t\};',source,re.S).group()
        methods='\n'.join(function(source,name) for name in (
            'bool CCzmChat::DateBefore(', 'int CCzmChat::MessageHeight(',
            'int CCzmChat::RowHeight(', 'int CCzmChat::HitTest(', 'void CCzmChat::Activate('))
        harness=HARNESS+r'''
#include "CzmConversationStyle.h"
#include "CzmTextLanguage.h"
#define ROOMS 3
#define MAX_MESSAGES 100
struct CzmChatMessage{int id,player,time,place;char nick[100],avatar[24],text[1604],role[16],project[132];};
struct CzmChatRoom{CUtlVector<CzmChatMessage>messages;double nextPoll=0;};
static std::vector<std::pair<int,int>>profiles;
void CZM_OpenProfile(int id,int message){profiles.push_back({id,message});}
bool CZM_OnlineBan(void*,void*,void*){return false;}
class CCzmChat{public:
'''+hits+r'''
 bool m_bClosing=false,m_reportConfirm=false;int m_iPopup=-1,m_popupId=0,m_iRoom=0;
 float m_flScroll=0,m_flVelocity=0;int W=1536,H=716,reports=0;bool ended=false;
 CzmChatRoom m_rooms[ROOMS];
 CzmRect m_popup={},m_popupCopy={},m_popupAvatar={},m_popupMessage={},m_popupCancel={};
 CzmRect m_back={},m_handle={},m_sheet={},m_rooms_[ROOMS]={},m_send={},m_input={},m_clip={};
 void Hide(){}void BeginInput(){}void Send(){}void Toast(const char*){}void Report(bool avatar){assert(!avatar);reports++;}
 void EndInput(){ended=true;}
 bool DateBefore(int)const;int MessageHeight(CzmChatMessage&);int RowHeight(int);int HitTest()const;void Activate(int);
};
'''+methods+r'''
void point(const CzmRect&r){cursorX=uiStatic.cursorX=r.x+r.w/2;cursorY=uiStatic.cursorY=r.y+r.h/2;}
int main(){
 using namespace CzmTextLanguage;
 assert(Detect("Привет, заходи играть")==Russian);
 assert(Detect("Hello, join our game!")==English);
 assert(Detect("я на ze_minecraft_v3")==Russian);
 assert(Detect("gg wp 123 🎮")==Neutral);
 assert(Detect("ок")==Neutral&&Detect("OK!")==Neutral);
 assert(Detect("https://example.com/room 8.8.8.8:27015")==Neutral);
 assert(!Needs("Привет",true)&&Needs("Привет",false));
 assert(Needs("hello",true)&&!Needs("hello",false));
 assert(Needs("hi",true)&&Needs("да",false));
 assert(!Needs("czm:invite gs 8.8.8.8:27015 Server",true));
 CCzmChat chat;chat.m_sheet={0,0,1536,716};chat.m_clip={30,100,1000,500};
 for(int room=0;room<ROOMS;room++){
  CzmChatMessage message={};message.id=70+room;message.player=8+room;message.time=1792240000;
  strcpy(message.nick,"Friend");strcpy(message.text,"Hello, join our game!");chat.m_rooms[room].messages.AddToTail(message);chat.m_iRoom=room;
  const auto b=CzmConversation::Layout(chat.m_clip,chat.m_clip.y+chat.m_clip.h-chat.RowHeight(0)+CzmConversation::DateHeight(),message.text,message.nick,false);
  assert(b.canTranslate);point(b.body);assert(chat.HitTest()==chat.HIT_NONE);
  point(b.menu);assert(chat.HitTest()==chat.HIT_OPTIONS);chat.Activate(chat.HitTest());
  assert(chat.m_iPopup==0&&chat.m_popupId==message.id&&chat.ended&&!chat.m_reportConfirm);
  chat.Activate(chat.HIT_POPUP_MESSAGE);assert(chat.m_reportConfirm&&chat.reports==room);
  chat.Activate(chat.HIT_POPUP_MESSAGE);assert(chat.m_iPopup==-1&&chat.reports==room+1);
  point(b.avatar);assert(chat.HitTest()==chat.HIT_PROFILE);chat.Activate(chat.HitTest());assert(profiles.back()==std::make_pair(message.player,message.id));
  point(b.translate);assert(chat.HitTest()==chat.HIT_TRANSLATE);
 }
 const char*original="Hello, join our game!";
 auto before=requests.size();CZM_Translate(original);assert(requests.size()==before+1&&requests.back().url=="translation");
 const int first=requests.back().id;CZM_Translate(original);assert(requests.size()==before+1);
 assert(CZM_TranslationGet(original).state==1);
 replies[first]={200,"{\"text\":\"Привет, заходи к нам играть!\"}"};now+=.03;
 auto translated=CZM_TranslationGet(original);assert(translated.state==2&&translated.shown&&strstr(translated.text,"Привет"));
 CZM_Translate(original);assert(!CZM_TranslationGet(original).shown&&requests.size()==before+1);
 CZM_Translate(original);assert(CZM_TranslationGet(original).shown&&requests.size()==before+1);
 // A translation in flight cannot appear after another account signs in.
 CZM_Translate("A delayed old account message");const int abandoned=requests.back().id;identity++;
 assert(CZM_TranslationGet(original).state==0);replies[abandoned]={200,"{\"text\":\"old account secret\"}"};now+=.03;
 assert(CZM_TranslationGet("A delayed old account message").state==0);
 russian=false;assert(!CZM_CanTranslate(original)&&CZM_CanTranslate("Привет, друг!"));
 CZM_Translate("Привет, друг!");int failed=requests.back().id;replies[failed]={0,""};now+=.03;assert(CZM_TranslationGet("Привет, друг!").state==3);
 CZM_Translate("Привет, друг!");replies[requests.back().id]={499,""};now+=.03;assert(CZM_TranslationGet("Привет, друг!").state==0);
 russian=true;now+=.03;CZM_TranslationFrame();
 const auto pendingStart=requests.size();for(int i=0;i<5;i++){char text[80];snprintf(text,sizeof(text),"Message number %d",i);CZM_Translate(text);}
 assert(requests.size()==pendingStart+4);
 for(size_t i=pendingStart;i<requests.size();i++)replies[requests[i].id]={200,"{\"text\":\"Сообщение\"}"};now+=.03;CZM_TranslationFrame();
 for(int i=0;i<70;i++){char text[80];snprintf(text,sizeof(text),"Cached message number %d",i);CZM_Translate(text);replies[requests.back().id]={200,"{\"text\":\"Сообщение\"}"};now+=.03;CZM_TranslationFrame();}
 assert(CZM_TranslationGet("Cached message number 0").state==0&&CZM_TranslationGet("Cached message number 69").state==2);
 for(auto size:{std::pair<int,int>{640,320},{800,360},{960,540},{1536,716},{2960,1440}}){
  ScreenWidth=size.first;ScreenHeight=size.second;const CzmRect clip={20,30,ScreenWidth-40,ScreenHeight-60};
  for(bool mine:{false,true})for(const char*text:{"ок","Hello, friend!","Привет, как дела?","A long message with many words and line breaks\nAnother line with a longer explanation to wrap correctly"}){
   const auto b=CzmConversation::Layout(clip,40,text,mine?"Вы":"Friend",mine);
   assert(b.frame.x>=clip.x&&b.frame.x+b.frame.w<=clip.x+clip.w);
   assert(b.body.y>=b.header.y+b.header.h&&b.body.y+b.body.h<=b.frame.y+b.frame.h);
   assert(b.menu.x>=b.frame.x&&b.menu.x+b.menu.w<=b.frame.x+b.frame.w);
   assert(b.starts[b.originalLines]==(int)strlen(text));
   if(b.canTranslate)assert(b.translate.y+b.translate.h<=b.body.y);
  }
  const auto small=CzmConversation::Layout(clip,40,"ок","Вы",true);
  assert(small.frame.w<clip.w*.60f);
 }
}
'''
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            stub=STUB.replace('CZMF_NICK,QM_CENTER=1','CZMF_NICK,CZMF_TILE_STATUS,CZMF_UI_TITLE,CZMF_UI_ACTION,CZMF_UI_LABEL,CZMF_UI_META,CZMF_PROFILE_NAME,CZMF_PROFILE_TEXT,CZMF_CHAT_TEXT,QM_LEFT=0,QM_CENTER=1')
            stub=stub.replace('struct Cursor{int cursorY;}','struct Cursor{int cursorY,cursorX;}')
            stub=stub.replace('struct CzmRect {int x,y,w,h;','struct CzmRect {int x,y,w,h;bool Contains(int a,int b)const{return a>=x&&a<x+w&&b>=y&&b<y+h;}CzmRect Grown(int n)const{return{x-n,y-n,w+2*n,h+2*n};}')
            (p/'stub.h').write_text(stub)
            (p/'utlvector.h').write_text(VECTOR.replace('void RemoveAll(){v.clear();}','void RemoveAll(){v.clear();}void Remove(int n){v.erase(v.begin()+n);}'))
            (p/'utlstring.h').write_text(STRING.replace('void Set(const char *v)','void Clear(){s.clear();}void Set(const char *v)'))
            for name in ['extdll_menu.h','BaseMenu.h','CzmMenu.h','Scissor.h']:(p/name).write_text('#include "stub.h"\n')
            for name in ['CzmJson.h','CzmDesign.h','CzmTextLanguage.h','CzmTranslation.h','CzmTranslation.cpp','CzmConversationStyle.h']:(p/name).write_text((ROOT/'czm/menu'/name).read_text())
            (p/'main.cpp').write_text(harness)
            exe=p/'chat'
            subprocess.run(['g++','-std=c++11','-w','-I'+folder,str(p/'main.cpp'),str(p/'CzmTranslation.cpp'),str(ROOT/'czm/menu/CzmJson.cpp'),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)

if __name__=='__main__':unittest.main()
