"""Exercise the real server-browser layout, touch routing and lobby selection."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_lobby_menu import STUB as LOBBY_STUB, HARNESS as LOBBY_HARNESS
from test_tab_avatars import VECTOR, STRING
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
STUB = LOBBY_STUB.replace('CZMF_UI_META,QM_LEFT',
    'CZMF_UI_META,CZMF_TILE_TEXT,CZMF_SHOP_NAME,CZMF_SHOP_PRICE,CZMF_BUTTON,QM_LEFT')
STUB = STUB.replace('bool HasCursor()const{',
    'bool Contains(int px,int py)const{return w>0&&h>0&&px>=x&&px<x+w&&py>=y&&py<y+h;}'
    'CzmRect Grown(int n)const{return{x-n,y-n,w+n*2,h+n*2};}bool HasCursor()const{')
STUB = STUB.replace('struct Cursor{int cursorY;}',
    'struct Cursor{int cursorY,cursorX,realTime;const char*sounds[1];}')
STUB = STUB.replace('static double DoubleTime();',
    'static double DoubleTime();static char*GetClipboardData(){return nullptr;}'
    'static void PlayLocalSound(const char*){}')
STUB = STUB.replace('unsigned CZM_White();', 'unsigned CZM_White(int alpha=255);')
STUB = STUB.replace('template<class T> T Q_min(T a,T b){return std::min(a,b);}',
    'template<class A,class B>auto Q_min(A a,B b)->decltype(a+b){return a<b?a:b;}')
STUB += r'''
struct netadr_t{int value;};struct net_response_t{};
enum{SND_OUT=0};
struct CzmTextEdit{char text[128];bool active;void End(){active=false;}
 void Begin(const char*,const CzmRect&){active=true;}bool KeyDown(int){return false;}void Char(int){}};
const char*CZM_T(const char*);unsigned CZM_PingColor(int);int CZM_LineWidth();
bool CZM_HomePinned(const char*);bool CZM_HomeSetPinned(const char*,const char*,bool);
void CZM_ServerAuthShow(const char*,const char*);
void CZM_ServerReportShow(const char*,const char*);bool CZM_ServerBlocked(const char*);
void CZM_ServerBlocksShow();
int CZM_ServerResourcesEligibility(const char*);void CZM_ServerResourcesShow(const char*,bool);
int CZM_ServerResourcesStatus(const char*);int CZM_ServerResourcesProgress(const char*);
void CZM_LobbyPickedServer(const char*,const char*,const char*,const char*,int,int);
struct CzmServer;
enum{CZM_OFFICIAL_SURVIVAL=0,CZM_OFFICIAL_ESCAPE,CZM_OFFICIAL_COUNT};
CzmServer*CZM_OfficialServer(int);bool CZM_IsOfficial(const char*);void CZM_PrepareConnect(const char*);
void CZM_ConnectWithResources(const char*,const char*);
void CZM_CancelResourceJoin();
int CZM_OfficialBadge(int,int,int,bool);void CZM_GoldComet(const CzmRect&,float,float);void CZM_OfficialMark(int,int,int);
'''
HARNESS = LOBBY_HARNESS.replace('unsigned CZM_White(){return 0xffffffff;}',
    'unsigned CZM_White(int alpha){return PackRGBA(255,255,255,alpha);}')
HARNESS = HARNESS.replace('int h=f==CZMF_UI_TITLE?',
    'int h=f==CZMF_PANEL_TITLE?42:f==CZMF_NICK?28:f==CZMF_TILE_TEXT?19:'
    'f==CZMF_SHOP_PRICE?20:f==CZMF_BUTTON?27:f==CZMF_UI_TITLE?')
HARNESS = HARNESS.replace('void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){',
    'static unsigned blockLabelColor;static int blockLabels;'
    'void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){'
    'if(!strcmp(s,"Заблокировать")||!strcmp(s,"Block")){blockLabelColor=c;blockLabels++;}')
HARNESS = HARNESS.replace('x,y,w,f,c,just,s);','x,y,w,CZM_FontHeight(f),c,just,s);')
HARNESS = HARNESS.replace('void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){',
    'static std::vector<std::string> detailLabels;void CZM_DrawText(HFont f,int x,int y,int w,const char*s,unsigned c,unsigned just){detailLabels.emplace_back(s);')
HARNESS = HARNESS.replace('void CZM_OpenProfile(int){}',
    'static int openedOwner;void CZM_OpenProfile(int owner){openedOwner=owner;}')
HARNESS += r'''
#include <cmath>
static int picked,detailsAsked,authOpened,reportsOpened,blocksOpened;static std::string pickedAddress,blockedAddress,reportedAddress;
static int resourcesOpened;static bool resourcesRussian;static std::string resourcesAddress,configuredResourceAddress;
static int resourceJoinCancels;static bool resourceJoinPending;
void CZM_CancelResourceJoin(){if(resourceJoinPending){resourceJoinPending=false;resourceJoinCancels++;}}
int CZM_ServerResourcesEligibility(const char*a){return !configuredResourceAddress.empty()&&configuredResourceAddress==a?1:0;}
static int resourceStatus=1,resourceProgress=-1;
int CZM_ServerResourcesStatus(const char*a){return CZM_ServerResourcesEligibility(a)?resourceStatus:0;}
int CZM_ServerResourcesProgress(const char*){return resourceProgress;}
void CZM_ServerResourcesShow(const char*a,bool ru){resourcesOpened++;resourcesAddress=a;resourcesRussian=ru;}
bool CZM_ServerBlocked(const char*a){return blockedAddress==a;}
void CZM_ServerReportShow(const char*a,const char*){reportsOpened++;reportedAddress=a;}
void CZM_ServerBlocksShow(){blocksOpened++;}
unsigned CZM_PingColor(int){return PackRGBA(231,187,96,255);}int CZM_LineWidth(){return 1;}
const char*CZM_T(const char*k){
 static const char*labels[][3]={{"srv_title","СЕРВЕРЫ","SERVERS"},{"srv_tab_all","Все","All"},
 {"srv_tab_fav","Избранное","Favorites"},{"srv_tab_hist","История","History"},
 {"srv_f_notempty","Не пустые","Not empty"},{"srv_f_notfull","Есть места","Has slots"},
 {"srv_f_nopass","Без пароля","No password"},{"srv_f_zombie","Зомби","Zombie"},
 {"srv_sort_players","По игрокам","By players"},{"srv_sort_ping","По пингу","By ping"},
 {"srv_sort_name","По названию","By name"},{"srv_search","Поиск: название, карта, IP","Search: name, map, IP"},
 {"srv_fav_add","В избранное","Favorite"},{"srv_fav_in","В избранном","Favorited"},
 {"srv_players","ИГРОКИ","PLAYERS"},{"srv_more","и ещё %d","and %d more"},
 {"ms","мс","ms"},{"srv_password","Требуется пароль","Password required"},
 {"offline","Сервер не отвечает","Server not responding"},{"querying","Проверяем сервер…","Querying server…"},
 {"srv_players_wait","Загружаем список игроков…","Loading players…"},
 {"srv_players_none","Пока никого нет","No players yet"},{"srv_players_hidden","Сервер не передал список игроков","Player list unavailable"}};
 for(auto&v:labels){if(!strcmp(v[0],k))return v[russian?1:2];}return k;
}
bool CZM_HomePinned(const char*){return false;}bool CZM_HomeSetPinned(const char*,const char*,bool){return true;}
void CZM_ServerAuthShow(const char*,const char*){authOpened++;}
CzmServer*CZM_OfficialServer(int){return nullptr;}bool CZM_IsOfficial(const char*){return false;}
int CZM_OfficialBadge(int,int,int,bool){return 0;}void CZM_GoldComet(const CzmRect&,float,float){}void CZM_OfficialMark(int,int,int){}
void CZM_LobbyPickedServer(const char*a,const char*,const char*,const char*,int,int){picked++;pickedAddress=a;}
static std::vector<CzmRect> mapRects;
void CZM_DrawMapPreview(const char*,int x,int y,int w,int h,const char*){mapRects.push_back(CZM_Rect(x,y,w,h));if(trace)printf("C\t%d\t%d\t%d\t%d\tgfx/czm/maps/_zombie.png\n",x,y,w,h);}
'''

ADAPTERS = r'''
CCzmServers::~CCzmServers(){}
void CCzmServers::Refresh(bool){}void CCzmServers::SaveLists(){}
void CCzmServers::RequestDetails(CzmEntry*){detailsAsked++;}
CzmEntry*CCzmServers::Selected(){return m_szSelected[0]?&m_entries[0]:nullptr;}
void CCzmServers::SetFavorite(CzmEntry*e,bool on){if(on)e->sources|=SRC_FAVORITE;else e->sources&=~SRC_FAVORITE;}
void CCzmServers::AddHistory(const CzmEntry*){}
void CCzmServers::OpenDialog(int i){m_iDialog=i;}void CCzmServers::CloseDialog(){m_iDialog=DLG_NONE;}
void CCzmServers::SubmitDialog(){}
void CCzmServers::Toast(const char*){}
bool CCzmServers::IsStale(const CzmEntry&)const{return false;}
void CCzmServers::Draw(){Layout();DrawHeader();DrawFilters();for(int i=0;i<ViewCount();i++)DrawRow(i,RowRect(i));if(m_bDetailsOpen)DrawDetails();}
'''

SCENARIOS = r'''
static bool inside(const CzmRect&a,const CzmRect&b){return a.w>0&&a.h>0&&a.x>=b.x&&a.y>=b.y&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h;}
static bool overlap(const CzmRect&a,const CzmRect&b){return a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;}
static void cursor(const CzmRect&r){cursorX=uiStatic.cursorX=r.x+r.w/2;cursorY=uiStatic.cursorY=r.y+r.h/2;}
int main(int argc,char**argv){
 CCzmServers w;CzmEntry e={};strcpy(e.address,"203.0.113.5:27015");strcpy(e.name,"OLD SCHOOL CS #HALLOWEEN #S3");strcpy(e.map,"de_dust2");strcpy(e.badge,"DE");
 e.answered=e.gs=true;e.players=18;e.maxPlayers=32;e.ping=116;w.m_entries.AddToTail(e);w.m_view.AddToTail(0);
 for(auto resolution:{std::pair<int,int>{1536,716},{640,360},{2340,1080},{960,540},{800,360},{1024,768},{1280,720},{2960,1440},{640,320}}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;
  for(int lang=0;lang<2;lang++)for(int picker=0;picker<2;picker++){
   russian=lang==0;s_lobbyPicker=picker;w.m_bDetailsOpen=false;w.Layout();
   int beforeBlocks=blocksOpened;cursor(w.m_blocked);assert(w.HitTest()==w.HIT_BLOCKS);w.Activate(w.HIT_BLOCKS);
   assert(blocksOpened==beforeBlocks+1);
   assert(w.m_clip.w==ScreenWidth-w.m_iMargin*2);assert(abs(w.m_detailsMap.w*2-w.m_detailsMap.h*3)<=2);
   assert(w.m_detailsMap.h<=ScreenHeight*.311f);
   for(auto*r:{&w.m_detailsMap,&w.m_detailsInfo,&w.m_detailsName,&w.m_detailsRoster,&w.m_detailsPlayers,&w.m_detailsClose,&w.m_report,&w.m_fav,&w.m_admin,&w.m_play})assert(inside(*r,w.m_details));
   assert(!overlap(w.m_report,w.m_detailsClose));
   for(auto&r:w.m_filters)assert(r.y>w.m_tabs[0].y||!overlap(r,w.m_blocked));
   assert(!overlap(w.m_detailsMap,w.m_detailsInfo));assert(!overlap(w.m_detailsMap,w.m_fav));
   assert(!overlap(w.m_admin,w.m_play)&&!overlap(w.m_fav,w.m_admin));
   cursor(w.RowRect(0));assert(w.HitTest()==w.HIT_ROW);int oldPicked=picked;
   w.Activate(w.HIT_ROW);assert(w.m_bDetailsOpen&&picked==oldPicked);
   // A configured server exposes resources even while its official badge is hidden.
   assert(!w.m_resources.w&&!CZM_IsOfficial(e.address));
   configuredResourceAddress=e.address;w.Layout();
   assert(inside(w.m_resources,w.m_details));
   // The card invites the optional download; the label follows the pack on the device.
   {const char*want[][2]={{"Скачать ресурсы","Download resources"},{"Обновить ресурсы","Update resources"},{"Ресурсы ✓","Resources ✓"},{"Загрузка 42%","Downloading 42%"}};
    for(int s=1;s<=4;s++){resourceStatus=s;resourceProgress=s==4?420:-1;detailLabels.clear();w.Layout();w.DrawDetails();
     const std::string label=want[s-1][russian?0:1];
     assert(std::find(detailLabels.begin(),detailLabels.end(),label)!=detailLabels.end());
     assert(w.m_resources.w-w.m_resources.h/2>=CZM_TextWidth(CZM_Font(CZMF_UI_LABEL),label.c_str()));}
    resourceStatus=1;resourceProgress=-1;w.Layout();}
   assert(!overlap(w.m_resources,w.m_report)&&!overlap(w.m_resources,w.m_detailsClose));
   assert(!overlap(w.m_resources,w.m_detailsName)&&!overlap(w.m_resources,w.m_detailsMap));
   assert(w.m_resources.x>=w.m_details.x+ScreenHeight*.028f);
   int beforeResources=resourcesOpened;cursor(w.m_resources);assert(w.HitTest()==w.HIT_RESOURCES);
   w.KeyDown(1);w.KeyUp(1);assert(resourcesOpened==beforeResources+1&&resourcesAddress==e.address&&resourcesRussian==russian);
   // A mapping change between draw and tap cannot open the old server's pack.
   configuredResourceAddress="203.0.113.6:27015";
   assert(w.HitTest()==w.HIT_DETAILS);w.Activate(w.HIT_RESOURCES);assert(resourcesOpened==beforeResources+1);
   w.Layout();assert(!w.m_resources.w);configuredResourceAddress.clear();
   w.m_iPlayersState=2;w.m_iNumPlayers=18;strcpy(w.m_szPlayersFor,e.address);
   for(int i=0;i<18;i++){snprintf(w.m_players[i].name,48,"Player %d",i+1);w.m_players[i].frags=65-i;}
   mapRects.clear();int oldLabels=blockLabels;w.Draw();assert(mapRects.back().w==w.m_detailsMap.w&&mapRects.back().h==w.m_detailsMap.h);
   for(size_t i=0;i+1<mapRects.size();i++)assert(mapRects[i].w==mapRects[i].h); // browser rows retain square thumbnails
   assert(blockLabels==oldLabels+1&&blockLabelColor==CzmStyle::Ink());
   verifiedAddress=e.address;verifiedOwner=42;w.Layout();
   assert(inside(w.m_verified,w.m_detailsInfo));
   cursor(w.m_verified);assert(w.HitTest()==w.HIT_VERIFIED);w.Activate(w.HIT_VERIFIED);assert(openedOwner==42);
   w.Draw();w.m_bDetailsOpen=false;
   CzmRect row=w.RowRect(0);cursorY=uiStatic.cursorY=row.y+row.h/2;
   // the verified shield comes first, the heart and the star keep their places
   cursorX=uiStatic.cursorX=row.x+row.w-row.h*5/2;
   assert(w.HitTest()==w.HIT_ROW+3);openedOwner=0;w.Activate(w.HitTest());assert(openedOwner==42);
   cursorX=uiStatic.cursorX=row.x+row.w-row.h*3/2;assert(w.HitTest()==w.HIT_ROW+2);
   cursorX=uiStatic.cursorX=row.x+row.w-row.h/2;assert(w.HitTest()==w.HIT_ROW+1);
   verifiedOwner=0;w.m_bDetailsOpen=true;w.Layout();assert(!w.m_verified.w);
   actorAdmin=true;configuredResourceAddress=e.address;w.Layout();assert(inside(w.m_manage,w.m_details)&&!overlap(w.m_manage,w.m_report));
   assert(inside(w.m_resources,w.m_details)&&!overlap(w.m_resources,w.m_manage));
   assert(w.m_resources.x>=w.m_details.x+ScreenHeight*.028f);configuredResourceAddress.clear();w.Layout();
   cursor(w.m_manage);assert(w.HitTest()==w.HIT_MANAGE);w.Activate(w.HIT_MANAGE);assert(managedServer==e.address);
   w.Draw();actorAdmin=false;w.Layout();assert(!w.m_manage.w);
   int beforeReport=reportsOpened;cursor(w.m_report);assert(w.HitTest()==w.HIT_REPORT);w.Activate(w.HIT_REPORT);
   assert(reportsOpened==beforeReport+1&&reportedAddress==e.address);
   // Only the overflowing roster can scroll; the browser's list offset stays unchanged.
   float browserScroll=w.m_flScroll;cursor(w.m_detailsPlayers);w.KeyDown(K_MWHEELDOWN);
   assert(w.m_iDetailPlayerFirst==1&&w.m_flScroll==browserScroll);
   w.KeyDown(1);assert(w.m_bDetailPlayerDrag);uiStatic.cursorY-=w.DetailPlayerRowH()*3;cursorY=uiStatic.cursorY;w.MouseMove(uiStatic.cursorX,uiStatic.cursorY);w.KeyUp(1);
   assert(w.m_iDetailPlayerFirst>1&&w.m_flScroll==browserScroll);w.Draw();
   w.m_iDetailPlayerFirst=999;w.Layout();assert(w.m_iDetailPlayerFirst==w.m_iNumPlayers-w.DetailPlayerRows());
   // A short roster has no drag range, and finger jitter on a button stays a tap.
   w.m_iNumPlayers=1;w.Layout();bool wasFavorite=(w.m_entries[0].sources&SRC_FAVORITE)!=0;cursor(w.m_fav);w.KeyDown(1);assert(!w.m_bDetailPlayerDrag);
   uiStatic.cursorY+=ScreenHeight/100;cursorY=uiStatic.cursorY;w.MouseMove(uiStatic.cursorX,uiStatic.cursorY);w.KeyUp(1);assert(((w.m_entries[0].sources&SRC_FAVORITE)!=0)!=wasFavorite);
   for(int state:{0,1,2,3}){w.m_iPlayersState=state;w.m_iNumPlayers=0;w.Draw();}
   w.m_entries[0].answered=false;w.Draw();w.m_entries[0].answered=true;
   cursor(w.m_play);assert(w.HitTest()==w.HIT_PLAY);
   float scroll=w.m_flScroll;w.KeyDown(K_MWHEELDOWN);assert(w.m_flScroll==scroll);
   w.KeyDown(1);assert(!w.m_bMaybeScroll);w.KeyUp(1);
   if(picker){assert(picked==oldPicked+1&&pickedAddress==e.address&&!w.m_bDetailsOpen);s_lobbyPicker=true;}
   else assert(w.m_bReturnHere);
   w.m_bDetailsOpen=true;cursorX=uiStatic.cursorX=w.m_details.x-2;cursorY=uiStatic.cursorY=w.m_details.y;
   int cancelledBefore=resourceJoinCancels;resourceJoinPending=true;
   assert(w.HitTest()==w.HIT_DETAILS_BACKDROP);w.KeyDown(1);w.KeyUp(1);assert(!w.m_bDetailsOpen&&!resourceJoinPending&&resourceJoinCancels==cancelledBefore+1);
   // An interior-to-exterior drag cannot trigger backdrop dismissal.
   w.m_bDetailsOpen=true;cursor(w.m_detailsInfo);w.KeyDown(1);cursorX=uiStatic.cursorX=w.m_details.x-2;w.KeyUp(1);assert(w.m_bDetailsOpen);
   resourceJoinPending=true;cancelledBefore=resourceJoinCancels;
   w.KeyDown(27);assert(!w.m_bDetailsOpen&&!resourceJoinPending&&resourceJoinCancels==cancelledBefore+1);
   w.m_bDetailsOpen=true;w.OpenDialog(w.DLG_PASSWORD);cursor(w.m_dlgField);assert(w.HitTest()==w.HIT_DIALOG_FIELD);
   resourceJoinPending=true;cancelledBefore=resourceJoinCancels;
   w.KeyDown(27);assert(w.m_iDialog==w.DLG_NONE&&w.m_bDetailsOpen&&resourceJoinPending&&resourceJoinCancels==cancelledBefore);resourceJoinPending=false;w.m_bDetailsOpen=false;
  }
 }
 for(int tab=0;tab<TAB_COUNT;tab++){
  w.m_iTab=tab;w.m_iFilters=0;w.m_szQuery[0]=0;e.sources=SRC_INTERNET|SRC_FAVORITE|SRC_HISTORY;
  blockedAddress.clear();assert(w.Passes(e));blockedAddress=e.address;assert(!w.Passes(e));
  blockedAddress.clear();assert(w.Passes(e));assert(e.sources==(SRC_INTERNET|SRC_FAVORITE|SRC_HISTORY));
 }
 // Long foreign names and all 64 returned players retain the last scroll page.
 for(auto resolution:{std::pair<int,int>{640,360},{1536,716},{2340,1080},{1024,768}}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;russian=true;s_lobbyPicker=false;
  std::string longName(63,'W');Q_strncpy(w.m_entries[0].name,longName.c_str(),sizeof(w.m_entries[0].name));
  w.m_iNumPlayers=64;w.m_iPlayersState=2;w.m_bDetailsOpen=true;strcpy(w.m_szPlayersFor,w.m_entries[0].address);
  for(int i=0;i<64;i++){snprintf(w.m_players[i].name,sizeof(w.m_players[i].name),"ОченьДлинныйНикИгрока_%d",i);w.m_players[i].frags=1000-i;}
  w.m_iDetailPlayerFirst=999;w.Layout();assert(w.m_iDetailPlayerFirst+ w.DetailPlayerRows()==64);w.DrawDetails();
  // Closing and reopening the same server is a fresh view, not its last roster page.
  std::string sameServer=w.m_szSelected;w.m_bDetailPlayerDrag=true;w.m_bScrolling=true;
  int cancelledBefore=resourceJoinCancels;resourceJoinPending=true;
  w.Activate(w.HIT_DETAILS_CLOSE);assert(!w.m_bDetailsOpen&&!w.m_iDetailPlayerFirst&&!w.m_bDetailPlayerDrag&&!w.m_bScrolling&&!resourceJoinPending&&resourceJoinCancels==cancelledBefore+1);
  w.Activate(w.HIT_ROW);assert(w.m_bDetailsOpen&&sameServer==w.m_szSelected&&!w.m_iDetailPlayerFirst&&!w.m_bDetailPlayerDrag);
  detailLabels.clear();w.Layout();w.DrawDetails();assert(std::find(detailLabels.begin(),detailLabels.end(),w.m_players[0].name)!=detailLabels.end());
  resourceJoinPending=true;cancelledBefore=resourceJoinCancels;w.Select(&w.m_entries[0]);assert(resourceJoinPending&&resourceJoinCancels==cancelledBefore);
  CzmEntry other=e;strcpy(other.address,"203.0.113.6:27015");w.Select(&other);assert(w.m_iDetailPlayerFirst==0&&!resourceJoinPending&&resourceJoinCancels==cancelledBefore+1);
  resourceJoinPending=true;w.Select(nullptr);assert(!resourceJoinPending&&resourceJoinCancels==cancelledBefore+2);w.Select(&w.m_entries[0]);
  w.m_entries[0].password=true;w.Activate(w.HIT_PLAY);assert(w.m_iDialog==w.DLG_PASSWORD&&!strcmp(w.m_szPending,e.address));w.CloseDialog();w.m_entries[0].password=false;
  int beforeAuth=authOpened;w.Activate(w.HIT_ADMIN);assert(authOpened==beforeAuth+1);
  actorAdmin=false;managedServer.clear();w.Activate(w.HIT_MANAGE);assert(managedServer.empty());
 }
 ScreenWidth=1536;ScreenHeight=716;russian=true;s_lobbyPicker=true;w.m_bDetailsOpen=false;w.Layout();
 if(argc>1){
  if(argc>3){ScreenWidth=atoi(argv[2]);ScreenHeight=atoi(argv[3]);}
  trace=true;if(!strcmp(argv[1],"details")){
   s_lobbyPicker=false;actorAdmin=true;w.m_bDetailsOpen=true;
   configuredResourceAddress=w.m_entries[0].address;
   strcpy(w.m_entries[0].name,"Counter Zombie | Survival | ZP 5");strcpy(w.m_entries[0].map,"zm_3rooms");strcpy(w.m_entries[0].badge,"ZM");
   w.m_entries[0].players=1;w.m_entries[0].ping=37;w.m_entries[0].password=true;w.m_entries[0].sources|=SRC_FAVORITE;
   w.m_iPlayersState=2;w.m_iNumPlayers=1;strcpy(w.m_szPlayersFor,w.m_entries[0].address);strcpy(w.m_players[0].name,"Magnus");w.m_players[0].frags=0;
  }w.Draw();}
 puts("NATIVE_SERVER_BROWSER_OK");
}
'''

class ServerBrowserTests(unittest.TestCase):
    def test_photo_and_placeholder_restore_nested_clip(self):
        source=(ROOT/'czm/menu/CzmMapPics.cpp').read_text()
        harness=r'''
#include "stub.h"
#include <cassert>
int ScreenWidth=1536,ScreenHeight=716,cursorX,cursorY;
static int picture,depth,covers;static CzmRect clips[8],expected;
namespace UI{namespace Scissor{
void PushScissor(int x,int y,int w,int h){CzmRect r={x,y,w,h};if(depth){auto&p=clips[depth-1];int right=Q_min(x+w,p.x+p.w),bottom=Q_min(y+h,p.y+p.h);r.x=Q_max(x,p.x);r.y=Q_max(y,p.y);r.w=right-r.x;r.h=bottom-r.y;}clips[depth++]=r;}
void PopScissor(){assert(depth>0);depth--;}
}}
HIMAGE CZM_MapPreview(const char*){return picture;}HIMAGE CZM_Image(const char*){return 1;}
bool CZM_MapInstalled(const char*){return false;}const char*CZM_MapModeArt(const char*,const char*){return "art";}
HFont CZM_Font(int f){return f;}int CZM_FontHeight(HFont){return 14;}
void CZM_DrawCover(HIMAGE,int,int,int,int){assert(depth>0);const auto&r=clips[depth-1];assert(r.x==expected.x&&r.y==expected.y&&r.w==expected.w&&r.h==expected.h);covers++;}
void CZM_DrawImage(const char*,int,int,int,int,unsigned){}
void CZM_DrawText(HFont,int,int,int,const char*,unsigned,unsigned){}
const char*CZM_T(const char*){return "Map";}unsigned CZM_White(){return 0xffffffff;}
'''
        scenarios=r'''
int main(){for(int photo=0;photo<2;photo++)for(int size:{48,136,280}){
 picture=photo;expected={20,30,size,size};int before=covers;
 CZM_DrawMapPreview("de_dust2",20,30,size,size,"Server");assert(depth==0&&covers==before+1);
 UI::Scissor::PushScissor(0,0,100,90);expected={20,30,Q_min(size,80),Q_min(size,60)};
 CZM_DrawMapPreview("missing",20,30,size,size,"Server");assert(depth==1);
 assert(clips[0].w==100&&clips[0].h==90);UI::Scissor::PopScissor();
 }int before=covers;CZM_DrawMapPreview("de_dust2",0,0,0,20,"");assert(!depth&&before==covers);}
'''
        stub=LOBBY_STUB.replace('namespace Scissor{inline void PushScissor(int,int,int,int){}inline void PopScissor(){}}',
            'namespace Scissor{void PushScissor(int,int,int,int);void PopScissor();}')
        stub+='\nbool CZM_MapInstalled(const char*);const char*CZM_T(const char*);\n'
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'stub.h').write_text(stub);(p/'utlvector.h').write_text(VECTOR);(p/'utlstring.h').write_text(STRING)
            (p/'main.cpp').write_text(harness+'\n'+function(source,'static void Fill(')+'\n'+function(source,'void CZM_DrawMapPreview(')+scenarios)
            exe=p/'clip';subprocess.run(['g++','-std=c++11','-I'+folder,str(p/'main.cpp'),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)

    def test_full_width_list_modal_touches_and_picker(self):
        source=(ROOT/'czm/menu/CzmServers.cpp').read_text()
        declarations=source[source.index('#define UI_DIR'):source.index('static void FoldText(')]
        declaration=source[source.index('class CCzmServers :'):source.index('static CCzmServers *s_browser;')].replace('private:', 'public:')
        helpers=(ROOT/'czm/menu/CzmMenu.cpp').read_text()
        wrapping='\n'.join(function(helpers,s) for s in ['static bool CZM_IsLineBreak(', 'int CZM_WrapText(', 'void CZM_WrapLine('])
        methods=['CCzmServers::CCzmServers()', 'void CCzmServers::Show()', 'void CCzmServers::Hide()',
            'CzmTextEdit *CCzmServers::ActiveEdit(', 'int CCzmServers::MaxScroll(', 'void CCzmServers::ClampScroll(',
            'CzmRect CCzmServers::RowRect(', 'void CCzmServers::Layout(', 'int CCzmServers::HitTest(',
            'void CCzmServers::Activate(', 'bool CCzmServers::KeyDown(', 'bool CCzmServers::KeyUp(',
            'bool CCzmServers::MouseMove(', 'void CCzmServers::Char(', 'void CCzmServers::DrawDetails(',
            'void CCzmServers::DrawHeader(', 'void CCzmServers::DrawFilters(', 'void CCzmServers::DrawRow(',
            'void CCzmServers::DrawChip(', 'void CCzmServers::Connect(', 'void CCzmServers::Select(', 'bool CCzmServers::Passes(']
        drawing='\n'.join(function(source,s) for s in ['static const char *Plural(', 'static void CountText(', 'static void DrawMapPicture(', 'static unsigned int ModeColor(', 'static void FillRect(',
            'static const char *ResourcesLabel(', 'static int ResourcesLabelWidth(', 'static void DrawResourcesButton('])
        code='\n'.join([HARNESS,wrapping,declarations,drawing,declaration,'static CCzmServers*s_browser;static bool s_lobbyPicker;\n'])
        code+='\n'.join(function(source,s) for s in methods)+ADAPTERS+SCENARIOS
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'stub.h').write_text(STUB)
            (p/'utlvector.h').write_text(VECTOR);(p/'utlstring.h').write_text(STRING)
            (p/'CzmMenu.h').write_text('#include "stub.h"\n');(p/'Scissor.h').write_text('#include "stub.h"\n')
            (p/'CzmDesign.h').write_text((ROOT/'czm/menu/CzmDesign.h').read_text())
            (p/'main.cpp').write_text('#include "CzmDesign.h"\n'+code)
            exe=p/'browser';subprocess.run(['g++','-std=c++11','-Wall','-I'+folder,str(p/'main.cpp'),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
            if os.environ.get('CZM_SERVER_PREVIEW_DIR'):
                dest=Path(os.environ['CZM_SERVER_PREVIEW_DIR']);dest.mkdir(parents=True,exist_ok=True)
                for view in ['servers','details']:
                    result=subprocess.run([str(exe),view],check=True,capture_output=True,text=True)
                    (dest/(view+'.tsv')).write_text(result.stdout)
                for width,height in [(1536,716),(640,360)]:
                    result=subprocess.run([str(exe),'details',str(width),str(height)],check=True,capture_output=True,text=True)
                    (dest/(f'details-{width}x{height}.tsv')).write_text(result.stdout)

if __name__=='__main__':unittest.main()
