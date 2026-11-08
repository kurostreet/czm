"""Run the real community feed, touch actions and delayed replies at mobile sizes."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

from test_social_menu import STUB, HARNESS
from test_tab_avatars import VECTOR, STRING
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]

EXTRA = r'''
namespace UI{namespace Scissor{
void PushScissor(int x,int y,int w,int h){if(drawTrace)printf("Q\t%d\t%d\t%d\t%d\n",x,y,w,h);}
void PopScissor(){if(drawTrace)printf("E\n");}
}}
static std::vector<std::pair<int,int>> openedProfiles, readRooms;
void CZM_OpenProfile(int player,int message){openedProfiles.push_back({player,message});}
void CZM_ChatMarkRead(int room,int message){readRooms.push_back({room,message});}
int CZM_ChatUnread(int){return 0;}int CZM_SocialNotifications(){return 0;}
int CZM_CountBadgeWidth(int,int h){return h;}void CZM_DrawCountBadge(const CzmRect&,int){}
bool CZM_NetAvailable(){return true;}
bool CZM_OnlineBan(int*,bool*,const char**){return false;}
void CZM_OnlineReadBan(CzmJson&,int){}void CZM_OnlineSetLimit(int,CzmJson&,int){}
void CZM_ShowNotice(const char*,const char*){}
const char*CZM_T(const char*key){
 if(!strcmp(key,"chat_placeholder"))return "Message in %s…";
 if(!strcmp(key,"chat_rules"))return "Be respectful. Report through the message menu.";
 return key;
}
'''

SCENARIOS = r'''
static bool inside(const CzmRect&r,const CzmRect&parent){return r.x>=parent.x&&r.y>=parent.y&&r.x+r.w<=parent.x+parent.w&&r.y+r.h<=parent.y+parent.h;}
static bool overlaps(const CzmRect&a,const CzmRect&b){return a.w&&a.h&&b.w&&b.h&&a.x<b.x+b.w&&b.x<a.x+a.w&&a.y<b.y+b.h&&b.y<a.y+a.h;}
static void point(const CzmRect&r){cursorX=uiStatic.cursorX=r.x+r.w/2;cursorY=uiStatic.cursorY=r.y+r.h/2;}
static CzmCommunityChat::Row rowAt(CCzmChat&w,int index){
 int y=w.m_clip.y+Q_min(w.ContentHeight(),w.m_clip.h)+(int)w.m_flScroll;
 auto&room=w.m_rooms[w.m_iRoom];for(int i=room.messages.Count()-1;i>=index;i--)y-=w.RowHeight(i);
 auto&m=room.messages[index];return CzmCommunityChat::Layout(w.m_clip,y+(w.DateBefore(index)?CzmCommunityChat::DateHeight():0),m.text,m.nick,w.Grouped(index),m.role,m.project,m.place);
}
static CzmChatMessage message(int id,int player,const char*text="gg"){
 CzmChatMessage m={};m.id=id;m.player=player;m.time=1792240000+id;strcpy(m.nick,"Hunter");strcpy(m.avatar,"default");Q_strncpy(m.text,text,sizeof(m.text));return m;
}
int main(int argc,char**argv){
 CCzmChat w;w.Show();w.m_flOpen=1;w.Layout();
 if(argc>1){
  const std::string mode=argv[1];if(mode=="compact"){ScreenWidth=640;ScreenHeight=360;w.Layout();}
  auto&room=w.m_rooms[0];room.loaded=true;room.nextPoll=now+100;
  const char*names[]={"NK - Azaro","MONSTER","MONSTER","Cobra","Kuro","Raven","Alex","Frost","Nova","Kuro"};
  const char*texts[]={"why me play alone here?","Я тоже здесь. Собираем Survival?","Кто с нами?","Я зайду через минуту.","Заходим на наш Survival.","Какой сервер выбираем?","CZM | Survival, ждём вас.","Кнопки способностей теперь удобные.","После раунда ещё одну?","Да, остаёмся."};
  for(int i=0;i<10;i++){
   auto m=message(i+1,i==2?101:100+i,texts[i]);strcpy(m.nick,names[i]);
   if(i==0)m.place=2;if(i==1||i==2)m.place=10;if(i==4)strcpy(m.nickColor,"#66CCAA");
   room.messages.AddToTail(m);
  }
  if(mode=="long"){
   strcpy(room.messages[2].text,"Собираемся на Survival.\nСначала дождёмся остальных игроков, выберем карту и проверим команды.\nЕсли подключение оборвётся, вернёмся на тот же сервер и продолжим вместе.");
   CZM_Translate(room.messages[0].text);replies[requests.back().id]={200,"{\"text\":\"Почему я играю здесь один? Кто-нибудь присоединится?\"}"};now+=.03;
  }
  strcpy(w.m_szInput,"Привет!");drawTrace=true;w.Draw();return 0;
 }
 for(auto size:{std::pair<int,int>{640,360},{800,360},{960,540},{1536,716},{2960,1440}}){
  ScreenWidth=size.first;ScreenHeight=size.second;w.Layout();
  assert(w.m_sheet.w>=ScreenWidth*.93&&w.m_sheet.h>=ScreenHeight*.93);
  assert(inside(w.m_sheet,CZM_Rect(0,0,ScreenWidth,ScreenHeight)));
  assert(inside(w.m_clip,w.m_sheet)&&inside(w.m_input,w.m_sheet)&&inside(w.m_send,w.m_sheet));
  assert(!overlaps(w.m_input,w.m_send)&&!overlaps(w.m_clip,w.m_input));
  assert(w.m_send.w-w.m_send.h/2-(w.m_send.h/4)*3>=CZM_TextWidth(CZM_Font(CZMF_UI_LABEL),"Отправить"));
  assert(w.m_rooms_[0].x<w.m_clip.x&&w.m_rooms_[0].w<w.m_sheet.w/4);
  for(int i=0;i<ROOMS;i++){
   assert(inside(w.m_rooms_[i],w.m_sheet)&&!overlaps(w.m_rooms_[i],w.m_clip));
   point(w.m_rooms_[i]);assert(w.HitTest()==w.HIT_ROOM+i);
  }
  point(w.m_input);assert(w.HitTest()==w.HIT_INPUT);point(w.m_send);assert(w.HitTest()==w.HIT_SEND);
  point(w.m_close);assert(w.HitTest()==w.HIT_BACK);
  auto&room=w.m_rooms[0];room.messages.RemoveAll();room.loaded=true;w.m_iRoom=0;w.m_flScroll=0;
  for(int i=0;i<12;i++)room.messages.AddToTail(message(i+1,100+i));
  int fit=0,height=0;for(int i=11;i>=0;i--){height+=w.RowHeight(i);if(height<=w.m_clip.h)fit++;}
  assert(fit>=(ScreenHeight<=360?8:10));
  for(const char*text:{"gg","Привет, как дела?","Hello, join our Survival server!","Первая строка\nВторая строка с подробностями\nТретья строка"}){
   for(bool grouped:{false,true}){
    auto row=CzmCommunityChat::Layout(w.m_clip,50,text,"An exceptionally long player nickname",grouped,"support","CZM",10);
    assert(row.frame.w==w.m_clip.w&&row.height==row.frame.h&&row.body.w>0);
    assert(inside(row.body,row.frame)&&inside(row.menu,row.frame)&&inside(row.time,row.frame));
    assert(!overlaps(row.menu,row.body)&&!overlaps(row.time,row.body));
    assert(row.starts[row.originalLines]==(int)strlen(text));
    if(grouped)assert(!row.name.w&&!row.avatar.w&&!row.roleTag.w&&!row.topTag.w);
    else{
     assert(inside(row.name,row.frame)&&inside(row.roleTag,row.frame)&&inside(row.topTag,row.frame));
     assert(!overlaps(row.name,row.roleTag)&&!overlaps(row.roleTag,row.topTag)&&!overlaps(row.topTag,row.time));
    }
    if(row.canTranslate)assert(row.translate.y>=row.body.y+row.body.h&&inside(row.translate,row.frame));
    if(strstr(text,"Первая строка"))assert(row.originalLines==3);
   }
  }
  std::string longText;for(int i=0;i<190;i++)longText+="word ";
  auto longRow=CzmCommunityChat::Layout(w.m_clip,0,longText.c_str(),"Hunter");
  assert(longRow.originalLines>1&&longRow.starts[longRow.originalLines]==(int)longText.size());
 }
 ScreenWidth=1536;ScreenHeight=716;w.Layout();
 auto&room=w.m_rooms[0];room.messages.RemoveAll();w.m_flScroll=0;
 room.messages.AddToTail(message(11,8,"Привет"));room.messages.AddToTail(message(12,8,"Заходи играть"));room.messages.AddToTail(message(13,9,"Я уже здесь"));
 assert(!w.Grouped(0)&&w.Grouped(1)&&!w.Grouped(2));
 assert(w.RowHeight(1)<w.MessageHeight(room.messages[1]));
 assert(rowAt(w,0).frame.y==w.m_clip.y+CzmCommunityChat::DateHeight()); // short history starts at the top
 paintedText.clear();w.DrawMessages();int paintedNames=0,paintedTimes=0;
 for(const auto&text:paintedText){if(text.text=="Hunter")paintedNames++;if(text.text.size()==5&&text.text[2]==':')paintedTimes++;}
 assert(paintedNames==2&&paintedTimes==3); // grouping suppresses only the repeated identity, never an individual timestamp
 for(int i=0;i<3;i++){
  auto row=rowAt(w,i);point(row.menu);assert(w.HitTest()==w.HIT_OPTIONS+i);w.Activate(w.HitTest());
  assert(w.m_popupId==11+i);w.Activate(w.HIT_POPUP_CANCEL);
  point(row.body);assert(w.HitTest()==w.HIT_NONE);
  if(!row.grouped){point(row.avatar);assert(w.HitTest()==w.HIT_PROFILE+i);}
 }
 // Grouped messages retain their own report and profile context in the menu.
 w.Activate(w.HIT_OPTIONS+1);w.Activate(w.HIT_POPUP_AVATAR);assert(openedProfiles.back()==std::make_pair(8,12));
 w.Activate(w.HIT_OPTIONS+1);const auto before=requests.size();w.Activate(w.HIT_POPUP_MESSAGE);assert(requests.size()==before&&w.m_reportConfirm);
 w.Activate(w.HIT_POPUP_MESSAGE);assert(requests.back().body=="{\"message\":12}"&&w.m_iPopup==-1);w.m_iReportId=0;
 strcpy(room.messages[1].nickColor,"#66CCAA");assert(!w.Grouped(1));room.messages[1].nickColor[0]=0;
 room.messages[1].time=room.messages[0].time+301;assert(!w.Grouped(1));room.messages[1].time=room.messages[0].time+1;
 strcpy(room.messages[1].role,"support");assert(!w.Grouped(1));room.messages[1].role[0]=0;
 room.messages[1].time=room.messages[0].time+86400;assert(w.DateBefore(1)&&!w.Grouped(1));room.messages[1].time=room.messages[0].time+1;
 // Translation is below the original, and growing it cannot move the fixed composer.
 const char*foreign="Hello, join our Survival server!";strcpy(room.messages[1].text,foreign);
 auto pending=CzmCommunityChat::Layout(w.m_clip,0,foreign,"Hunter",true);assert(pending.canTranslate);
 auto row=rowAt(w,1);point(row.translate);assert(w.HitTest()==w.HIT_TRANSLATE+1);w.Activate(w.HitTest());
 const int translationRequest=requests.back().id;replies[translationRequest]={200,"{\"text\":\"Привет! Заходи на наш Survival сервер, будем играть вместе.\"}"};now+=.03;
 const auto composer=w.m_input;const auto translated=CzmCommunityChat::Layout(w.m_clip,0,foreign,"Hunter",true);
 assert(translated.resultLines&&translated.result.y>=translated.translate.y+translated.translate.h);
 assert(inside(translated.result,translated.frame)&&inside(translated.credit,translated.frame));
 assert(translated.height>pending.height);w.Layout();assert(w.m_input.x==composer.x&&w.m_input.y==composer.y&&w.m_input.h==composer.h);
 // An open menu follows its message ID when older rows disappear, then closes if its own row is deleted.
 w.Activate(w.HIT_OPTIONS+1);assert(w.m_popupId==12);room.messages.Remove(0);w.Layout();assert(w.m_iPopup==0&&w.m_popupId==12);
 room.messages.Remove(0);w.Layout();assert(w.m_iPopup==-1);
 // Parsing is optional and never turns a truncated invalid color into a valid one.
 room.messages.RemoveAll();room.lastId=0;
 w.ReadMessages(room,"{\"messages\":[{\"id\":21,\"p\":8,\"n\":\"Hunter\",\"t\":\"gg\",\"ts\":1792240021,\"nick_color\":\"#66CCAA\",\"r\":\"support\",\"k\":10},{\"id\":22,\"p\":9,\"n\":\"Other\",\"t\":\"gg\",\"ts\":1792240022,\"nick_color\":\"#66CCAAF\"},{\"id\":23,\"p\":10,\"n\":\"Legacy\",\"t\":\"gg\",\"ts\":1792240023}]}");
 assert(room.messages.Count()==3&&!strcmp(room.messages[0].nickColor,"#66CCAA"));
 assert(!room.messages[1].nickColor[0]&&!room.messages[2].nickColor[0]);
 assert(!strcmp(room.messages[0].role,"support")&&room.messages[0].place==10);
 assert(CzmNicknameColor::Parse(room.messages[0].nickColor,0)==PackRGBA(102,204,170,255));
 paintedText.clear();const int priorSupport=supportTags,priorTop=topTags;w.DrawMessages();
 bool customName=false,plainBody=false;
 for(const auto&text:paintedText){if(text.text=="Hunter")customName=text.color==PackRGBA(102,204,170,255);if(text.text=="gg")plainBody=text.color==CzmStyle::Ink();}
 assert(customName&&plainBody&&supportTags>priorSupport&&topTags>priorTop);
 // Poll/read receipts and history cursors still use the actual room/message IDs.
 room.nextPoll=0;w.Poll();assert(!readRooms.empty()&&readRooms.back()==std::make_pair(0,23));
 assert(requests.back().url=="/api/v1/chat/global?after=23");
 // Reopening fetches current nickname colors for the same old IDs, preserving drafts and in-flight writes.
 const int preReopenRequest=room.request;
 const int pendingSend=CZM_NetRequest("POST","/api/v1/chat/global","","{}"),pendingReport=CZM_NetRequest("POST","/api/v1/report","","{}");
 w.m_iSendId=pendingSend;w.m_iReportId=pendingReport;strcpy(w.m_szSending,"already sending");strcpy(w.m_szInput,"preserved unsent draft");
 for(int i=1;i<ROOMS;i++){w.m_rooms[i].messages.AddToTail(message(45,8));w.m_rooms[i].lastId=45;w.m_rooms[i].loaded=true;}
 w.Show();w.m_flOpen=1;w.Layout();
 assert(!strcmp(w.m_szInput,"preserved unsent draft")&&w.m_iSendId==pendingSend&&w.m_iReportId==pendingReport);
 for(int i=0;i<ROOMS;i++)assert(!w.m_rooms[i].messages.Count()&&!w.m_rooms[i].loaded&&!w.m_rooms[i].lastId&&!w.m_rooms[i].request);
 replies[preReopenRequest]={200,"{\"messages\":[{\"id\":99,\"n\":\"Stale after cursor\",\"t\":\"gg\",\"nick_color\":\"#111111\"}]}"};
 const auto readsBeforeReload=readRooms.size();w.Poll();
 assert(!replies.count(preReopenRequest)&&room.messages.Count()==0&&readRooms.size()==readsBeforeReload);
 assert(requests.back().url=="/api/v1/chat/global?after=0");
 replies[room.request]={200,"{\"messages\":[{\"id\":21,\"p\":8,\"n\":\"Hunter\",\"t\":\"gg\",\"ts\":1792240021,\"nick_color\":\"#AABBCC\",\"r\":\"support\",\"k\":10},{\"id\":23,\"p\":10,\"n\":\"Legacy\",\"t\":\"gg\",\"ts\":1792240023}]}"};
 w.Poll();assert(room.loaded&&room.lastId==23&&room.messages.Count()==2&&!strcmp(room.messages[0].nickColor,"#AABBCC"));
 assert(!strcmp(w.m_szInput,"preserved unsent draft")&&w.m_iSendId==pendingSend&&w.m_iReportId==pendingReport);
 w.Activate(w.HIT_OPTIONS);assert(w.m_popupId==21);w.Activate(w.HIT_POPUP_AVATAR);assert(openedProfiles.back()==std::make_pair(8,21));
 replies[pendingSend]={200,"{}"};replies[pendingReport]={200,"{}"};w.Poll();
 assert(!w.m_iSendId&&!w.m_iReportId&&!strcmp(w.m_szInput,"preserved unsent draft")&&readRooms.back()==std::make_pair(0,23));
 room.nextPoll=0;w.Poll();assert(requests.back().url=="/api/v1/chat/global?after=23");
 const int stale=room.request;w.BeginInput();strcpy(w.m_szInput,"old account draft");w.m_iSendId=987;w.m_iPopup=0;w.m_popupId=21;
 identity++;me=17;replies[stale]={200,"{\"messages\":[{\"id\":99,\"n\":\"stale\",\"t\":\"old account\"}]}"};w.Poll();
 assert(!w.m_bTyping&&!w.m_szInput[0]&&!w.m_iSendId&&w.m_iPopup==-1&&room.messages.Count()==0);
 assert(room.request!=stale&&room.lastId==0);w.Poll();assert(room.messages.Count()==0);
 w.BeginInput();strcpy(w.m_szInput,"draft from a previous account");const auto requestsBeforeIdentityChange=requests.size();identity++;w.Send();
 assert(requests.size()==requestsBeforeIdentityChange&&!w.m_szInput[0]&&!w.m_bTyping);
 // UTF-8 deletion and Escape still close the keyboard before the chat itself.
 w.BeginInput();strcpy(w.m_szInput,"яю");assert(w.KeyDown(8)&&!strcmp(w.m_szInput,"я"));
 w.KeyDown(27);assert(!w.m_bTyping&&!w.m_bClosing);w.KeyDown(27);assert(w.m_bClosing);
 puts("COMMUNITY_LAYOUT_OK");
}
'''


class CommunityLayoutTests(unittest.TestCase):
    def test_native_feed_geometry_actions_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            stub = STUB.replace(
                'CZMF_NICK,QM_CENTER=1',
                'CZMF_NICK,CZMF_TILE_STATUS,CZMF_UI_TITLE,CZMF_UI_ACTION,CZMF_UI_LABEL,CZMF_UI_META,CZMF_PROFILE_TITLE,CZMF_PROFILE_NAME,CZMF_PROFILE_TEXT,CZMF_CHAT_TEXT,QM_LEFT=0,QM_CENTER=1')
            stub = re.sub(r'struct Cursor\{[^}]*\}', 'struct Cursor{int cursorY,cursorX,realTime;}', stub)
            stub = stub.replace('struct CzmRect {int x,y,w,h;', 'struct CzmRect {int x,y,w,h;bool Contains(int a,int b)const{return a>=x&&a<x+w&&b>=y&&b<y+h;}CzmRect Grown(int n)const{return{x-n,y-n,w+2*n,h+2*n};}')
            stub = stub.replace('virtual void Draw(){}', 'void DisableTransition(){}virtual void Draw(){}')
            stub = stub.replace('inline void PushScissor(int,int,int,int){}inline void PopScissor(){}', 'void PushScissor(int,int,int,int);void PopScissor();')
            stub += '\nclass CzmJson;bool CZM_NetAvailable();bool CZM_OnlineBan(int*,bool*,const char**);void CZM_OnlineReadBan(CzmJson&,int);void CZM_OnlineSetLimit(int,CzmJson&,int);void CZM_ShowNotice(const char*,const char*);const char*CZM_T(const char*);void CZM_OpenProfile(int,int);\n'
            (p / 'stub.h').write_text(stub)
            (p / 'utlvector.h').write_text(VECTOR.replace('void RemoveAll(){v.clear();}', 'void RemoveAll(){v.clear();}void Remove(int n){v.erase(v.begin()+n);}'))
            (p / 'utlstring.h').write_text(STRING.replace('void Set(const char *v)', 'void Clear(){s.clear();}void Set(const char *v)'))
            for name in ['extdll_menu.h', 'BaseMenu.h', 'Utils.h', 'Framework.h', 'Scissor.h', 'keydefs.h', 'CzmMenu.h']:
                (p / name).write_text('#include "stub.h"\n')
            for name in ['CzmChat.cpp', 'CzmJson.h', 'CzmDesign.h', 'CzmCommunityChatStyle.h', 'CzmNicknameColor.h', 'CzmTranslation.h', 'CzmTranslation.cpp', 'CzmTextLanguage.h']:
                (p / name).write_text((ROOT / 'czm/menu' / name).read_text())
            harness = HARNESS.replace('void CZM_ChatHidePlayer(int id){hiddenPlayer=id;}', '')
            harness = harness.replace('int CZM_WrapText(HFont f,const char*s,int w,int*starts,int max)', 'int FixtureWrapText(HFont f,const char*s,int w,int*starts,int max)')
            harness = harness.replace('void CZM_WrapLine(const char*s,const int*starts,int n,char*out,size_t size)', 'void FixtureWrapLine(const char*s,const int*starts,int n,char*out,size_t size)')
            harness = harness.replace('void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){drawnLabels.emplace_back(s);', 'struct PaintedText{std::string text;unsigned color;};static std::vector<PaintedText>paintedText;void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){paintedText.push_back({s,c});drawnLabels.emplace_back(s);')
            menu = (ROOT / 'czm/menu/CzmMenu.cpp').read_text()
            wrapping = '\n'.join(function(menu, name) for name in ('static bool CZM_IsLineBreak(', 'int CZM_WrapText(', 'void CZM_WrapLine('))
            (p / 'main.cpp').write_text(harness + '\n#include "CzmJson.h"\n' + wrapping + EXTRA + '\n#define private public\n#include "CzmChat.cpp"\n#undef private\n' + SCENARIOS)
            exe = p / 'community'
            subprocess.run(['g++', '-std=c++11', '-w', '-I' + folder, str(p / 'main.cpp'), str(p / 'CzmTranslation.cpp'), str(ROOT / 'czm/menu/CzmJson.cpp'), '-o', str(exe)], check=True)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('COMMUNITY_LAYOUT_OK', result.stdout)
            if os.environ.get('CZM_COMMUNITY_SNAPSHOTS'):
                output = Path(os.environ['CZM_COMMUNITY_SNAPSHOTS'])
                output.mkdir(parents=True, exist_ok=True)
                for view in ('main', 'long', 'compact'):
                    result = subprocess.run([str(exe), view], check=True, capture_output=True, text=True)
                    (output / ('community-preview-' + view + '.tsv')).write_text(result.stdout)


if __name__ == '__main__':
    unittest.main()
