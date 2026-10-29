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
void CZM_LobbyPickedServer(const char*,const char*,const char*,const char*,int,int);
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
HARNESS += r'''
#include <cmath>
static int picked,detailsAsked,authOpened,reportsOpened,blocksOpened;static std::string pickedAddress,blockedAddress,reportedAddress;
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
 {"ms","мс","ms"},{"srv_password","Требуется пароль","Password required"}};
 for(auto&v:labels){if(!strcmp(v[0],k))return v[russian?1:2];}return k;
}
bool CZM_HomePinned(const char*){return false;}bool CZM_HomeSetPinned(const char*,const char*,bool){return true;}
void CZM_ServerAuthShow(const char*,const char*){authOpened++;}
void CZM_LobbyPickedServer(const char*a,const char*,const char*,const char*,int,int){picked++;pickedAddress=a;}
static std::vector<CzmRect> mapRects;
void CZM_DrawMapPreview(const char*,int x,int y,int w,int h,const char*){mapRects.push_back(CZM_Rect(x,y,w,h));if(trace)printf("M\t%d\t%d\t%d\t%d\n",x,y,w,h);}
'''

ADAPTERS = r'''
CCzmServers::~CCzmServers(){}
void CCzmServers::Refresh(bool){}void CCzmServers::SaveLists(){}
void CCzmServers::RequestDetails(CzmEntry*){detailsAsked++;}
CzmEntry*CCzmServers::Selected(){return m_szSelected[0]?&m_entries[0]:nullptr;}
void CCzmServers::Select(CzmEntry*e){Q_strncpy(m_szSelected,e->address,sizeof(m_szSelected));RequestDetails(e);}
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
 for(auto resolution:{std::pair<int,int>{1536,716},{960,540},{800,360},{1024,768},{1280,720},{2960,1440},{640,320}}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;
  for(int lang=0;lang<2;lang++)for(int picker=0;picker<2;picker++){
   russian=lang==0;s_lobbyPicker=picker;w.m_bDetailsOpen=false;w.Layout();
   int beforeBlocks=blocksOpened;cursor(w.m_blocked);assert(w.HitTest()==w.HIT_BLOCKS);w.Activate(w.HIT_BLOCKS);
   assert(blocksOpened==beforeBlocks+1);
   assert(w.m_clip.w==ScreenWidth-w.m_iMargin*2);assert(w.m_detailsMap.w==w.m_detailsMap.h);
   for(auto*r:{&w.m_detailsMap,&w.m_detailsInfo,&w.m_detailsClose,&w.m_report,&w.m_fav,&w.m_admin,&w.m_play})assert(inside(*r,w.m_details));
   assert(!overlap(w.m_report,w.m_detailsClose));
   for(auto&r:w.m_filters)assert(r.y>w.m_tabs[0].y||!overlap(r,w.m_blocked));
   assert(!overlap(w.m_detailsMap,w.m_detailsInfo));assert(!overlap(w.m_detailsMap,w.m_fav));
   assert(!overlap(w.m_admin,w.m_play)&&!overlap(w.m_fav,w.m_admin));
   cursor(w.RowRect(0));assert(w.HitTest()==w.HIT_ROW);int oldPicked=picked;
   w.Activate(w.HIT_ROW);assert(w.m_bDetailsOpen&&picked==oldPicked);
   w.m_iPlayersState=2;w.m_iNumPlayers=18;strcpy(w.m_szPlayersFor,e.address);
   for(int i=0;i<18;i++){snprintf(w.m_players[i].name,48,"Player %d",i+1);w.m_players[i].frags=65-i;}
   mapRects.clear();int oldLabels=blockLabels;w.Draw();for(auto&r:mapRects)assert(r.w==r.h);
   assert(blockLabels==oldLabels+1&&blockLabelColor==CzmStyle::Ink());
   int beforeReport=reportsOpened;cursor(w.m_report);assert(w.HitTest()==w.HIT_REPORT);w.Activate(w.HIT_REPORT);
   assert(reportsOpened==beforeReport+1&&reportedAddress==e.address);
   cursor(w.m_play);assert(w.HitTest()==w.HIT_PLAY);
   float scroll=w.m_flScroll;w.KeyDown(K_MWHEELDOWN);assert(w.m_flScroll==scroll);
   w.KeyDown(1);assert(!w.m_bMaybeScroll);w.KeyUp(1);
   if(picker){assert(picked==oldPicked+1&&pickedAddress==e.address&&!w.m_bDetailsOpen);s_lobbyPicker=true;}
   else assert(w.m_bReturnHere);
   w.m_bDetailsOpen=true;cursorX=uiStatic.cursorX=w.m_details.x-2;cursorY=uiStatic.cursorY=w.m_details.y;
   assert(w.HitTest()==w.HIT_DETAILS_BACKDROP);w.KeyDown(1);w.KeyUp(1);assert(!w.m_bDetailsOpen);
   // An interior-to-exterior drag cannot trigger backdrop dismissal.
   w.m_bDetailsOpen=true;cursor(w.m_detailsInfo);w.KeyDown(1);cursorX=uiStatic.cursorX=w.m_details.x-2;w.KeyUp(1);assert(w.m_bDetailsOpen);
   w.KeyDown(27);assert(!w.m_bDetailsOpen);
   w.m_bDetailsOpen=true;w.OpenDialog(w.DLG_PASSWORD);cursor(w.m_dlgField);assert(w.HitTest()==w.HIT_DIALOG_FIELD);
   w.KeyDown(27);assert(w.m_iDialog==w.DLG_NONE&&w.m_bDetailsOpen);w.m_bDetailsOpen=false;
  }
 }
 for(int tab=0;tab<TAB_COUNT;tab++){
  w.m_iTab=tab;w.m_iFilters=0;w.m_szQuery[0]=0;e.sources=SRC_INTERNET|SRC_FAVORITE|SRC_HISTORY;
  blockedAddress.clear();assert(w.Passes(e));blockedAddress=e.address;assert(!w.Passes(e));
  blockedAddress.clear();assert(w.Passes(e));assert(e.sources==(SRC_INTERNET|SRC_FAVORITE|SRC_HISTORY));
 }
 ScreenWidth=1536;ScreenHeight=716;russian=true;s_lobbyPicker=true;w.m_bDetailsOpen=false;w.Layout();
 if(argc>1){trace=true;if(!strcmp(argv[1],"details"))w.m_bDetailsOpen=true;w.Draw();}
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
            'void CCzmServers::DrawChip(', 'void CCzmServers::Connect(', 'bool CCzmServers::Passes(']
        drawing='\n'.join(function(source,s) for s in ['static const char *Plural(', 'static void CountText(', 'static void DrawMapPicture(', 'static unsigned int ModeColor(', 'static void FillRect('])
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

if __name__=='__main__':unittest.main()
