"""Exercise the actual weapon parser, layout, team actions and Zombie Plague handlers."""
from pathlib import Path
import importlib.util,re,subprocess,tempfile,unittest
from test_loading_errors import function
ROOT=Path(__file__).resolve().parents[1]
def cpp(code):
 with tempfile.TemporaryDirectory(prefix='czm-arsenal-') as tmp:
  p=Path(tmp);(p/'test.cpp').write_text(code)
  subprocess.run(['g++','-std=c++11','-Wall','-Wno-unused-function','-I'+str(ROOT/'common'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
BASE=r'''
#include "czm_weapon_menu.h"
#include "czm_aim.h"
#include <cassert>
#include <algorithm>
#include <cstdarg>
#include <cmath>
#include <string>
#define TEAM_T 1
#define TEAM_CT 2
#define Q_min(a,b) std::min(a,b)
#define Q_max(a,b) std::max(a,b)
static void Q_strncpy(char*d,const char*s,size_t n){if(n){size_t k=std::min(n-1,strlen(s));memcpy(d,s,k);d[k]=0;}}
static bool CZM_IsRussian(){return true;}
static const char *V_stristr(const char*s,const char*w){std::string a(s),b(w);for(char &c:a)c=tolower(c);for(char &c:b)c=tolower(c);auto i=a.find(b);return i==std::string::npos?nullptr:s+i;}
struct CzmRect{int x,y,w,h;};
static CzmRect CZM_Rect(int x,int y,int w,int h){return {x,y,w,h};}
int ScreenWidth=1536,ScreenHeight=716;
'''
class WeaponShopTests(unittest.TestCase):
 def test_card_sends_the_current_menu_choice_to_the_server(self):
  source=(ROOT/'cl_dll/menu.cpp').read_text()
  cpp(BASE+r'''
static bool s_bCardsShown=true;
static int s_iCardsSerial=12,argc=3;
static const char *argv[]={"czm_shop_select","12","4"};
static std::string sent;
struct CHudMenu{
 int m_fMenuDisplayed=1,m_bitsValidSlots=1<<3,m_fWaitingForMore=0;
 void UserCmd_OldStyleMenuClose(){m_fMenuDisplayed=0;s_bCardsShown=false;}
};
static struct {CHudMenu m_Menu;} gHUD;
static struct {
 int Cmd_Argc(){return argc;}
 const char *Cmd_Argv(int i){return argv[i];}
 void pfnServerCmd(const char *cmd){sent=cmd;}
} gEngfuncs;
'''+function(source,'static void SelectShopCard(')+r'''
int main(){
 argv[1]="11";SelectShopCard();assert(sent.empty());
 argv[1]="12";argv[2]="1";SelectShopCard();assert(sent.empty());
 argv[2]="4";SelectShopCard();assert(sent=="menuselect 4"&&!gHUD.m_Menu.m_fMenuDisplayed);
 sent.clear();SelectShopCard();assert(sent.empty());
}
''')

 def test_actual_weapon_parser_and_grid_geometry(self):
  s=(ROOT/'czm/menu/CzmShop.cpp').read_text()
  code=BASE+s[s.index('enum\n{'):s.index('static const struct\n{\n\tconst char *ru, *en; // two lines')]
  code+=re.search(r'^#define CZM_WEAPON_EXTRA .*$',s,re.M).group(0)+'\n'
  code+=s[s.index('struct CzmWeaponMenu'):s.index('// the menu line without colour codes')]
  for sig in ['static const CzmShopItem *FindWeapon(','static bool Contains(','static void PlainLine(','static const CzmShopItem *ShopWeapon(','static bool ParseWeaponMenu(']:code+=function(s,sig)+'\n'
  code+=r'''
#define CZM_QUICK 5
class CCzmShop{public:
 bool m_bServerMenu=true,m_bGrid=true;int m_iSlots=7,W,H;CzmWeaponMenu m_wmenu={};
 CzmRect m_top,m_close,m_tabs[CAT_COUNT],m_quick[5],m_info,m_buy,m_cards[8];int m_iWheelX,m_iWheelY,m_iWheelR;
 void Layout();void LayoutSurvival(){} bool Survival()const{return false;}int QuickCount()const;int QuickKey(int,const char**)const;
};
'''
  for sig in ['void CCzmShop::Layout(','int CCzmShop::QuickCount(','int CCzmShop::QuickKey(']:code+=function(s,sig)+'\n'
  code+=r'''
int main(){
 CzmWeaponMenu m;
 const char *wire="12 1023\n#czmw1\tprimary\t1\t3\t1\t28\t1\t0\n\\yPrimary Weapon [8-14]\n1. Galil\n2. FAMAS\n3. M4A1\n4. AK-47\n5. SG552\n6. AUG\n7. Scout\n8. Remember [On]\n9. Next/Back\n0. Exit";
 assert(ParseWeaponMenu(wire,m)&&m.meta.valid&&m.meta.page==1&&m.meta.queued&&m.meta.selected==28&&m.toggleOn&&m.count==7);
 assert(m.items[0]->weapon==14&&m.items[3]->weapon==28&&m.keys[3]==4);
 assert(!CzmWeapons::HideAutomatic(wire,0)&&CzmWeapons::Classic(wire,0)&&!CzmWeapons::Classic(wire,2));
 assert(!ParseWeaponMenu("5 3\nVote\n1. Yes\n2. No",m));
 assert(ParseWeaponMenu("5 1023\n#czmw1\tsecondary\t0\t1\t0\t16\t0\t0\nSecondary Weapon\n1. USP\n8. Remember [Off]\n0. Exit",m)&&m.count==1);
 assert(!CzmWeapons::Parse("#czmw1\tprimary\t-1\t3\t0\t28\t1\t0").valid);
 assert(!CzmWeapons::Parse("#czmw1\tprimary\t3\t3\t0\t28\t1\t0").valid);
 int screens[][2]={{640,360},{1536,716},{2340,1080},{1024,768},{2000,1200}};
 for(auto &screen:screens)for(int n=1;n<=8;n++){
  ScreenWidth=screen[0];ScreenHeight=screen[1];CCzmShop shop;shop.m_iSlots=n;shop.m_wmenu.meta=CzmWeapons::Parse(wire);shop.m_wmenu.toggleKey=8;
  shop.Layout();assert(shop.QuickCount()==3);const char *text;assert(shop.QuickKey(0,&text)==8&&shop.QuickKey(1,&text)==-1&&shop.QuickKey(2,&text)==-2);
  for(int i=0;i<n;i++){
   auto a=shop.m_cards[i];assert(a.w>0&&a.h>0&&a.x>=0&&a.y>=shop.m_top.h&&a.x+a.w<=ScreenWidth&&a.y+a.h<ScreenHeight*.824f);
   if(i)assert(a.w==shop.m_cards[0].w&&a.h==shop.m_cards[0].h);
   for(int j=i+1;j<n;j++){auto b=shop.m_cards[j];assert(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y);}
  }
 }
}
'''
  cpp(code)
 def test_survival_shop_wheel_grid_and_equipment_use_the_same_actions(self):
  source=(ROOT/'czm/menu/CzmShop.cpp').read_text()
  code=BASE.replace(
   'struct CzmRect{int x,y,w,h;};',
   'struct CzmRect{int x,y,w,h;bool Contains(int a,int b)const{return w>0&&h>0&&a>=x&&b>=y&&a<x+w&&b<y+h;} CzmRect Grown(int n)const{return{x-n,y-n,w+2*n,h+2*n};}};')
  code+=source[source.index('enum\n{'):source.index('static const struct\n{\n\tconst char *ru, *en; // two lines')]
  code+=re.search(r'^#define CZM_WEAPON_EXTRA .*$',source,re.M).group(0)+'\n'
  code+=source[source.index('struct CzmWeaponMenu'):source.index('// the menu line without colour codes')]
  for signature in ('static const CzmShopItem *FindWeapon(', 'static bool Contains(', 'static void PlainLine(',
                    'static const CzmShopItem *ShopWeapon(', 'static bool ParseWeaponMenu('):
   code+=function(source,signature)+'\n'
  code+=r"""
#define CZM_QUICK 5
static int style=1;
static std::string command;
static struct {int cursorX,cursorY,realTime;} uiStatic;
static int bound(int lo,int value,int hi){return std::min(hi,std::max(lo,value));}
static void CZM_PlayClick(){}
namespace EngFuncs{
 static float GetCvarFloat(const char*){return style;}
 static void ClientCmdF(bool,const char *fmt,...){
  char text[96];va_list a;va_start(a,fmt);vsnprintf(text,sizeof(text),fmt,a);va_end(a);command=text;
 }
}
class CCzmShop{
public:
 enum{HIT_NONE=0,HIT_CLOSE,HIT_HUB,HIT_SELECT,HIT_CANCEL,HIT_TAB=10,HIT_QUICK=30,HIT_ITEM=100};
 bool m_bGrid=false;
 int W,H,m_iSlots=0,m_iPressed=0,m_iHover=-1,m_iPickTime=0,m_iInfo=0,m_iWheelX,m_iWheelY,m_iWheelR;
 CzmWeaponMenu m_wmenu={};
 const CzmShopItem *m_slots[8]={};
 CzmRect m_top,m_close,m_tabs[CAT_COUNT],m_quick[CZM_QUICK],m_info,m_buy,m_cancel,m_cards[8];
 bool RoundShop()const{return m_wmenu.shop.roundPurchase;}
 bool Gear()const{return m_wmenu.shop.tab==CzmSurvivalShop::Equipment;}
 bool RowEnabled(int row)const{return m_wmenu.shop.rows[m_wmenu.keys[row]].enabled;}
 bool Waiting()const{return m_iPickTime&&uiStatic.realTime-m_iPickTime<700;}
 void CloseServerMenu(bool){SendSurvival(CzmSurvivalShop::Close,0);}
 void LayoutSurvival();
 void ActivateSurvival(int);
 void SendSurvival(int,int);
 int HitTest()const;
 int WheelSlot(int,int)const;
};
static void click(CCzmShop &s,const CzmRect &r){
 uiStatic.cursorX=r.x+r.w/2;uiStatic.cursorY=r.y+r.h/2;
 uiStatic.realTime+=1000;s.ActivateSurvival(s.HitTest());
}
"""
  for signature in ('void CCzmShop::LayoutSurvival(', 'int CCzmShop::WheelSlot(', 'int CCzmShop::HitTest(',
                    'void CCzmShop::SendSurvival(', 'void CCzmShop::ActivateSurvival('):
   code+=function(source,signature)+'\n'
  code+=r"""
int main(){
 using namespace CzmSurvivalShop;
 CCzmShop s;
 assert(ParseWeaponMenu("4 1023\n#czms1\t22\t0\t0\t3\t10\t4\t0\t0\t28\t0\t0\t0\t3\n#item\t0\t28\t4\t1\nPrimary weapon",s.m_wmenu));
 s.m_iSlots=s.m_wmenu.count;
 assert(s.m_iSlots==1&&s.m_wmenu.items[0]->weapon==28);
 for(auto width:{640,780,1536}){
  s.W=width;s.H=width==640?360:width==780?440:716;
  style=1;s.LayoutSurvival();
  assert(!s.m_bGrid&&s.m_iWheelY+s.m_iWheelR<s.H*.75f);
  command.clear();
  click(s,CZM_Rect(s.m_iWheelX,s.m_iWheelY-s.m_iWheelR*3/4,1,1));
  assert(command=="czm_loadout 22 1 0\n");
  style=2;s.LayoutSurvival();
  assert(s.m_bGrid&&s.m_cards[0].y>=s.m_top.h&&s.m_cards[0].y+s.m_cards[0].h<s.H*.75f);
  click(s,s.m_cards[0]);assert(command=="czm_loadout 22 1 0\n");
  click(s,s.m_tabs[2]);assert(command=="czm_loadout 22 2 2\n");
  click(s,s.m_quick[4]);assert(command=="czm_loadout 22 5 0\n");
  assert(s.m_quick[4].x+s.m_quick[4].w<=s.W&&s.m_quick[4].y+s.m_quick[4].h<=s.H);
 }
 assert(ParseWeaponMenu("5 1023\n#czms1\t23\t2\t0\t1\t5\t5\t1\t1\t28\t26\t3\t0\t2\n"
  "#item\t0\t4\t6\t1\n#item\t1\t25\t4\t1\n#item\t2\t9\t4\t0\n#item\t3\t0\t20\t1\nEquipment",s.m_wmenu));
 s.m_iSlots=s.m_wmenu.count;
 style=1;s.LayoutSurvival();
 assert(s.m_iSlots==4&&s.m_bGrid&&s.m_cards[0].x+s.m_cards[0].w<s.m_cards[3].x);
 click(s,s.m_cards[3]);assert(command=="czm_loadout 23 1 3\n");
 command.clear();click(s,s.m_cards[2]);assert(command.empty());
 click(s,s.m_quick[4]);assert(command=="czm_loadout 23 6 0\n");
 click(s,s.m_close);assert(command=="czm_loadout 23 8 0\n");
 View bad={};
 assert(!Parse("#czms1\t2147483648\t0\t0\t1\t5\t4\t0\t0\t28\t0\t0\t0\t3\n",bad));
 assert(!Parse("#czms1\t24\t2\t0\t1\t5\t0\t2\t0\t28\t26\t3\t0\t2\n#item\t0\t4\t6\t1\n",bad));
 assert(!Parse("#czms2\t25\t0\t0\t1\t10\t0\t0\t0\t0\t0\t0\t0\t6\n#round\t14\t1\t0\t0\t0\t0\t0\t30001\n",bad));
 assert(!Parse("#czms3\t25\t0\t0\t1\t10\t0\t0\t0\t0\t0\t0\t0\t6\n#round\t14\t1\t0\t0\t0\t0\t0\t0\n#gear\t16\t0\t0\n",bad));
 assert(ParseWeaponMenu("7 1023\n#czms3\t26\t2\t0\t1\t50000\t26\t0\t1\t0\t0\t0\t0\t7\n"
  "#round\t0\t1\t0\t0\t0\t0\t0\t30000\n#gear\t9\t0\t0\n"
  "#item\t0\t4\t6\t1\n#item\t1\t25\t4\t1\n#item\t2\t9\t4\t1\n#item\t3\t0\t20\t1\nEquipment",s.m_wmenu));
 s.m_iSlots=s.m_wmenu.count;
 assert(s.m_wmenu.shop.equipmentSelection&&s.m_wmenu.shop.equipment==9&&s.m_wmenu.shop.balance==50000);
 s.LayoutSurvival();
 click(s,s.m_cards[0]);assert(command=="czm_loadout 26 1 0\n");
 click(s,s.m_quick[4]);assert(command=="czm_loadout 26 5 0\n");
 assert(ParseWeaponMenu("6 1023\n#czms2\t24\t0\t0\t2\t12\t5\t1\t1\t28\t26\t0\t0\t7\n"
  "#round\t14\t2\t16\t26\t22\t26\t4\t0\n#item\t0\t14\t4\t1\n#item\t1\t28\t4\t1\nPrimary",s.m_wmenu));
 s.m_iSlots=s.m_wmenu.count;
 for(int i=0;i<s.m_iSlots;i++)s.m_slots[i]=s.m_wmenu.items[i];
 assert(s.RoundShop()&&s.m_wmenu.shop.nextPrimary==22&&s.m_wmenu.shop.reserved==4);
 for(auto width:{640,780,1536}){
  s.W=width;s.H=width==640?360:width==780?440:716;
  for(int format:{1,2}){
   s.m_wmenu.shop.preview=14;s.m_iInfo=0;style=format;s.LayoutSurvival();
   if(format==2)assert(s.m_cards[1].x+s.m_cards[1].w<s.m_info.x);
   CzmRect item=format==2?s.m_cards[1]:CZM_Rect(s.m_iWheelX,s.m_iWheelY+s.m_iWheelR*3/4,1,1);
   click(s,item);assert(command=="czm_loadout 24 1 1\n"&&s.m_iInfo==1);
   command.clear();click(s,s.m_buy);assert(command.empty()); // wait for the highlighted row from the server
   s.m_wmenu.shop.preview=28;
   click(s,s.m_buy);assert(command=="czm_loadout 24 12 28\n");
   click(s,s.m_cancel);assert(command=="czm_loadout 24 6 0\n");
   click(s,s.m_quick[4]);assert(command=="czm_loadout 24 5 0\n");
  }
 }
}
"""
  cpp(code)

 def test_purchase_metadata_does_not_change_other_servers(self):
  cpp(BASE+r'''
int main(){
 auto m=CzmWeapons::Parse("8 1023\n#czmw1\tprimary\t0\t2\t1\t0\t0\t0\tbuy\t4\t5\t0\n");
 assert(m.valid&&m.purchase&&m.primary&&m.pages==2&&m.queued&&m.price==4&&m.balance==5);
 m=CzmWeapons::Parse("#czmw1\tsecondary\t0\t1\t1\t0\t0\t0\tbuy\t1\t0\t1\n");
 assert(m.valid&&m.purchase&&!m.primary&&m.price==1&&m.notice==1);
 m=CzmWeapons::Parse("#czmw1\tprimary\t0\t1\t1\t28\t0\t0\n");
 assert(m.valid&&!m.purchase&&m.queued);
 assert(!CzmWeapons::Parse("#czmw1\tprimary\t0\t1\t1\t0\t0\t0\tbuy\t-1\t5\t0").purchase);
}
''')
 def test_equipment_releases_the_previous_weapon_window(self):
  source=(ROOT/'czm/menu/CzmServerMenu.cpp').read_text()
  cpp(BASE+r'''
static bool shopOpen=true, closeShop=false, gearOpen=false, parsedFallback=false;
static const char *value="21 513\n#czm1\tmenu\tloadout\tGrenades\n1. HE grenade\n0. Exit";
namespace EngFuncs {
 const char *GetCvarString(const char *) { return value; }
 float GetCvarFloat(const char *) { return 1.0f; }
}
static bool CL_IsActive() { return true; }
struct WindowStack { bool IsActive() const { return shopOpen||gearOpen; } };
static struct { WindowStack menu,client; } uiStatic;
static bool CZM_ShopWeaponFrame(const char *v) {
 if(shopOpen && strstr(v,"#czm1\t")) closeShop=true;
 return false;
}
static bool ServerWindowFrame(const char *v) {
 if(!strstr(v,"#czm1\t")) return false;
 if(!uiStatic.client.IsActive()) gearOpen=true;
 return true;
}
static struct { int serial,layoutW,layoutH;bool buttons; } s_menu;
static void SpectatorExitFrame(const char *) {}
static void RemoveButtons() {}
static void ParseMenu(const char *) {parsedFallback=true;}
static void Layout() {}
static void AddButtons() {}
static void DrawMenu() {}
'''+function(source,'void CZM_DrawGameOverlay(')+r'''
int main(){
 CZM_DrawGameOverlay(); assert(closeShop&&!gearOpen);
 shopOpen=false; // deferred close, before rendering the next frame
 CZM_DrawGameOverlay(); assert(gearOpen);
 gearOpen=false;value="22 513\n#czms2\t17\t2\t0\t1\t5\t0\t2\t0\t0\t0\t0\t0\t7\n";
 CZM_DrawGameOverlay();assert(!parsedFallback); // a closing shop's packet must not appear as plain text
}
''')
 def test_official_team_buttons_use_distinct_commands(self):
  s=(ROOT/'czm/menu/CzmServerMenu.cpp').read_text()
  code=BASE+r'''
static std::string sent;static void CZM_PlayClick(){}static bool play=false;static bool CZM_PlayServer(){return play;}
namespace EngFuncs{static void ClientCmdF(bool,const char*f,...){char b[128];va_list a;va_start(a,f);vsnprintf(b,sizeof(b),f,a);va_end(a);sent=b;}}
static bool preview;static bool OpenClassPreview(bool ct,bool,int){if(preview)sent=ct?"preview ct":"preview t";return preview;}
class CCzmTeamCard{public:enum{BTN_NONE,BTN_PLAY,BTN_SPECTATE,BTN_T,BTN_AUTO,BTN_CT,BTN_CLOSE,BTN_COUNT};int m_iSlot=0,m_teamFlags=1;bool m_conditionZero=false;void Press(int);void Hide(){}};
'''+function(s,'void CCzmTeamCard::Press(')+r'''
int main(){CCzmTeamCard c;c.Press(c.BTN_PLAY);assert(sent=="czm_join auto\n");c.Press(c.BTN_SPECTATE);assert(sent=="czm_join spectator\n");c.Press(c.BTN_CT);assert(sent=="czm_join human\n");c.Press(c.BTN_T);assert(sent=="czm_join zombie\n");c.m_iSlot=-1;c.Press(c.BTN_CT);assert(sent=="jointeam 2\n");preview=true;c.Press(c.BTN_CT);assert(sent=="preview ct");c.Press(c.BTN_T);assert(sent=="preview t");c.Press(c.BTN_SPECTATE);assert(sent=="jointeam 6\n");play=true;c.Press(c.BTN_CT);assert(sent=="czm_join human\n");c.Press(c.BTN_T);assert(sent=="czm_join zombie\n");c.Press(c.BTN_PLAY);assert(sent=="czm_join auto\n");c.Press(c.BTN_SPECTATE);assert(sent=="czm_join spectator\n");}
'''
  cpp(code)
 def test_actual_hp_ratio_colors_and_stale_target_expiry(self):
  cpp(BASE+r'''
int main(){
 assert(fabs(CzmAim::Fraction(3167,5400)-.58648f)<.0001f);assert(CzmAim::Fraction(5400,5400)==1&&CzmAim::Fraction(1,5400)>0&&CzmAim::Fraction(50,0)==0);
 int r,g,b;CzmAim::Color(1,r,g,b);assert(r==0&&g==220);CzmAim::Color(.5f,r,g,b);assert(r==255&&g==220);CzmAim::Color(.1f,r,g,b);assert(r==255&&g<50);
 CzmAim::Target t={2,3167,5400,10};assert(t.Live(10.5f)&&!t.Live(11.2f)&&!t.Live(9));t.index=0;assert(!t.Live(10));t.index=33;assert(!t.Live(10));
}
''')
 def test_real_zombie_handlers_limit_grants_and_apply_queued_choices_next_round(self):
  spec=importlib.util.spec_from_file_location('czm_zp_policy',ROOT/'server/zm/tools/patch_zombie_menus.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  primary=m.PRIMARY[:m.PRIMARY.index('    static menu')]+"    shown++;\n}\n"
  bodies=primary+m.PICK_PRIMARY+m.PICK_SECONDARY
  bodies=bodies.replace('public show_menu_buy1(taskid)','void show_menu_buy1(int taskid)').replace('public menu_buy1(id, key)','int menu_buy1(int id,int key)').replace('public menu_buy2(id, key)','int menu_buy2(int id,int key)').replace('new bool:','bool ').replace('new ','int ')
  bodies=bodies.replace('case MENU_KEY_AUTOSELECT: WPN_AUTO_ON = 1 - WPN_AUTO_ON;','case MENU_KEY_AUTOSELECT: WPN_AUTO_ON = 1 - WPN_AUTO_ON; break;').replace('case MENU_KEY_NEXT: WPN_STARTID = WPN_STARTID + 7 < WPN_MAXIDS ? WPN_STARTID + 7 : 0;','case MENU_KEY_NEXT: WPN_STARTID = WPN_STARTID + 7 < WPN_MAXIDS ? WPN_STARTID + 7 : 0; break;')
  code=BASE+r'''
#define PLUGIN_HANDLED 1
#define MENU_KEY_AUTOSELECT 7
#define MENU_KEY_NEXT 8
#define MENU_KEY_EXIT 9
#define WPN_STARTID start[id]
#define WPN_MAXIDS 14
#define WPN_SELECTION (start[id]+key)
#define WPN_AUTO_PRI pri[id]
#define WPN_AUTO_SEC sec[id]
#define WPN_AUTO_ON remember[id]
#define ID_SPAWN (taskid-100)
#define charsmax(s) 31
#define Ham_GiveAmmo 1
int g_maxplayers=32,g_czmRound=3,shown=0,primaryGrants=0,pistolGrants=0,lastPri=-1,lastSec=-1;
int g_czmNextPri[33],g_czmNextSec[33],g_czmDue[33],start[33],pri[33],sec[33],remember[33];
bool g_czmBought[33],g_czmSecondaryNow[33],g_isalive[33],g_zombie[33],g_survivor[33],g_isbot[33],boughtProfile;
bool g_canbuy[33];int g_primary_items,g_secondary_items,g_primary_weaponids,g_secondary_weaponids,cvar_randweapons;
int MAXBPAMMO[32];const char *AMMOTYPE[32];
bool is_user_valid_connected(int id){return id==1;}int get_pcvar_num(int){return 0;}int random_num(int a,int){return a;}int ArraySize(int){return 6;}
int ArrayGetCell(int,int n){lastSec=n;return n;}void ArrayGetString(int,int,int*,int){}
int czm_menu_bridge(const char *f,int){if(!strcmp(f,"czm_weapon_bought"))return boughtProfile;if(!strcmp(f,"czm_weapon_mark"))boughtProfile=true;return 0;}
void buy_primary_weapon(int,int n){primaryGrants++;lastPri=n;}void show_menu_buy2(int){shown++;}void zp_drop_weapons(int,int){}void zp_give_item(int,int*){pistolGrants++;}void ExecuteHamB(int,int,int,const char*,int){}
int clamp(int n,int lo,int hi){return std::max(lo,std::min(n,hi));}int menu_buy2(int,int);
'''+bodies+r'''
void init(){g_czmBought[1]=g_czmSecondaryNow[1]=boughtProfile=false;g_isalive[1]=true;g_zombie[1]=g_survivor[1]=false;g_czmNextPri[1]=g_czmNextSec[1]=-1;g_czmDue[1]=0;}
int main(){
 init();menu_buy1(1,3);assert(primaryGrants==1&&lastPri==3&&boughtProfile);menu_buy2(1,2);assert(pistolGrants==1&&sec[1]==2);
 menu_buy1(1,4);menu_buy2(1,1);assert(primaryGrants==1&&pistolGrants==1&&g_czmDue[1]==4);assert(g_czmNextPri[1]==4&&g_czmNextSec[1]==1);
 show_menu_buy1(101);assert(lastPri==3&&sec[1]==2&&g_czmDue[1]==4);
 g_czmRound++;show_menu_buy1(101);assert(lastPri==4&&sec[1]==1&&!g_czmDue[1]);
 g_czmBought[1]=false;menu_buy1(1,5);assert(g_czmNextPri[1]==5);
 init();g_zombie[1]=true;int grants=primaryGrants+pistolGrants;menu_buy1(1,6);menu_buy2(1,4);assert(primaryGrants+pistolGrants==grants&&g_czmDue[1]==5);
 g_zombie[1]=false;g_czmRound++;show_menu_buy1(101);assert(lastPri==6&&sec[1]==4);
 init();menu_buy1(1,2);g_isalive[1]=false;grants=pistolGrants;menu_buy2(1,3);assert(pistolGrants==grants&&g_czmNextSec[1]==3);
 grants=primaryGrants+pistolGrants;menu_buy1(1,50);menu_buy2(1,-1);assert(primaryGrants+pistolGrants==grants);
}
'''
  cpp(code)
 def test_new_protocol_is_not_sent_to_an_older_client(self):
  s=(ROOT/'server/zm/scripting/czm_play.sma').read_text()
  body=function(s,'public czm_capable(').replace('public czm_capable(id, unused)','int capable(int id,int unused)')
  cpp(BASE+r'''
bool connected=true,rich=true,g_aimUi[33];
bool is_user_connected(int){return connected;}bool czm_menu_rich(int){return rich;}
'''+body+r'''
int main(){assert(!capable(1,0));g_aimUi[1]=true;assert(capable(1,0));rich=false;assert(!capable(1,0));rich=true;connected=false;assert(!capable(1,0));}
''')
 def test_team_bridge_routes_selections_without_reopening_the_card(self):
  s=(ROOT/'server/zm/scripting/czm_play.sma').read_text()
  body=function(s,'public czm_team_open(').replace('public czm_team_open(id, unused)','int team_open(int id,int unused)').replace('new ','char ')
  cpp(BASE+r'''
#define PLUGIN_HANDLED 1
#define charsmax(s) (sizeof(s)-1)
static const char *command="chooseteam",*argument="";static bool capable=true;
static int opened=0,announced=0;static std::string picked;
static bool czm_capable(int,int){return capable;}
static void read_argv(int n,char *out,size_t max){snprintf(out,max+1,"%s",n?argument:command);}
static bool equal(const char*a,const char*b){return !strcmp(a,b);}
static int read_argc(){return argument[0]?2:1;}
static int join_choice(int,const char *choice){picked=choice;return 1;}
static void play_state(int){announced++;}
static void client_cmd(int,const char*s){assert(!strcmp(s,"showvguimenu 2"));opened++;}
'''+body+r'''
int main(){
 assert(team_open(1,0)==1&&opened==1);command="jointeam";
 const char *numbers[]={"1","2","5","6"},*choices[]={"zombie","human","auto","spectator"};
 for(int i=0;i<4;i++){argument=numbers[i];picked.clear();assert(team_open(1,0)==1);assert(picked==choices[i]&&opened==1);}
 argument="99";picked.clear();assert(team_open(1,0)==1&&picked.empty()&&opened==1);
 capable=false;argument="5";assert(team_open(1,0)==0&&picked.empty()&&opened==1);
 capable=true;argument="";assert(team_open(1,0)==1&&opened==2);
}
''')
 def test_play_capability_resets_between_servers_and_does_not_grant_official_access(self):
  source=(ROOT/'cl_dll/menu.cpp').read_text()
  online=(ROOT/'czm/menu/CzmOnline.cpp').read_text()
  code=BASE+r'''
static float play=0;static bool active=true;static int resets=0;
static bool CL_IsActive(){return active;}
namespace EngFuncs {static float GetCvarFloat(const char *s){assert(!strcmp(s,"czm_play_mode"));return play;}}
struct {void Cvar_Set(const char *s,const char *v){if(!strcmp(s,"czm_play_mode"))play=atof(v);}} gEngfuncs;
struct BufferReader{unsigned char*p;BufferReader(const char*,void*b,int):p((unsigned char*)b){}int ReadByte(){return *p;}};
static char g_szRichMenuString[64]="old menu";
struct CHudMenu{int m_fMenuDisplayed=1,m_bitsValidSlots=1023;void Reset(){resets++;}void PublishCards(bool){}void InitHUDData();};
'''
  code+=function(source,'static int MsgFunc_CzmPlay(')+function(source,'void CHudMenu :: InitHUDData(')+function(online,'bool CZM_PlayServer(')+r'''
int main(){CHudMenu menu;unsigned char b=1;
 MsgFunc_CzmPlay("CzmPlay",1,&b);assert(CZM_PlayServer());active=false;assert(!CZM_PlayServer());active=true;
 menu.InitHUDData();assert(!CZM_PlayServer()&&!menu.m_fMenuDisplayed&&!menu.m_bitsValidSlots&&resets==1);
 MsgFunc_CzmPlay("CzmPlay",0,&b);assert(!CZM_PlayServer());b=99;MsgFunc_CzmPlay("CzmPlay",1,&b);assert(!CZM_PlayServer());
 b=1;MsgFunc_CzmPlay("CzmPlay",1,&b);assert(CZM_PlayServer());b=0;MsgFunc_CzmPlay("CzmPlay",1,&b);assert(!CZM_PlayServer());
}
'''
  cpp(code)
  panel=function(online,'static bool CZM_OnOfficialServer(')
  self.assertIn('CZM_OfficialSlotNow()',panel)
  self.assertNotIn('CZM_PlayServer',panel)
 def test_real_join_handler_finishes_entry_and_preserves_round_and_slot_guards(self):
  source=(ROOT/'server/zm/scripting/czm_play.sma').read_text()
  bodies=function(source,'join_choice(id, const choice[])').replace('join_choice(id, const choice[])','int join_choice(int id,const char *choice)').replace('new ','int ')
  bodies+=function(source,'public finish_join(').replace('public finish_join(task)','void finish_join(int task)').replace('new ','int ')
  cpp(BASE+r'''
#define PLUGIN_HANDLED 1
#define CS_TEAM_UNASSIGNED 0
#define CS_TEAM_T 1
#define CS_TEAM_CT 2
#define CS_TEAM_SPECTATOR 3
#define ZP_TEAM_HUMAN 2
#define ZP_TEAM_ZOMBIE 1
#define Ham_Killed 1
#define charsmax(s) (sizeof(s)-1)
static bool connected=true,alive=false,started=false,special=false,zombie=false,last=false,failTeam=false,failSet=false,refuseSpectator=false,leaveAlive=false;
static int team=0,userid=10,teamCommands=0,classCommands=0,respawns=0,infections=0,opened=0,scheduled=0,clockNow=10,fallbacks=0,kills=0;
static float g_nextJoin[33];static int g_teamChoice[33],g_joinUserid[33],g_joinTeam[33];
static bool equal(const char*a,const char*b){return !strcmp(a,b);}
static bool is_user_connected(int){return connected;}static float get_gametime(){return clockNow;}
static int cs_get_user_team(int){return team;}static int get_user_userid(int){return userid;}
static void cs_set_user_team(int,int choice){fallbacks++;if(!failSet)team=choice;}
static bool is_user_alive(int){return alive;}static bool zp_has_round_started(){return started;}
static bool special_round(){return special;}static bool zp_get_user_zombie(int){return zombie;}
static bool zp_get_user_last_human(int){return last;}static void zp_infect_user(int){infections++;zombie=true;}
static void zp_respawn_user(int,int){respawns++;alive=true;}
static void zp_call(const char*s,int,int){assert(!strcmp(s,"menu_game"));if(!refuseSpectator){team=CS_TEAM_SPECTATOR;if(!leaveAlive)alive=false;}}
static void ExecuteHamB(int,int,int,int){alive=false;kills++;}
static void engclient_cmd(int,const char*s,const char*v){assert(!strcmp(v,"5"));if(!strcmp(s,"jointeam")){teamCommands++;if(!failTeam)team=CS_TEAM_CT;}else{classCommands++;assert(!strcmp(s,"joinclass"));}}
static void remove_task(int){}static void set_task(float,const char*s,int task){assert(!strcmp(s,"finish_join"));scheduled=task;}
static void czm_chat(int,const char*,const char*){}static void client_cmd(int,const char*){opened++;}
'''+bodies+r'''
int main(){
 join_choice(1,"auto");assert(team==CS_TEAM_CT&&teamCommands==1&&classCommands==1&&scheduled==7201&&!opened);
 finish_join(scheduled);assert(alive&&respawns==1&&!opened);
 clockNow++;join_choice(1,"spectator");assert(team==CS_TEAM_SPECTATOR&&!alive);
 clockNow++;started=true;join_choice(1,"human");finish_join(scheduled);assert(team==CS_TEAM_CT&&!alive&&respawns==1&&!opened);
 clockNow++;join_choice(1,"zombie");assert(!alive&&teamCommands==2&&infections==0);
 alive=true;clockNow++;join_choice(1,"zombie");assert(zombie&&infections==1);
 zombie=false;special=true;clockNow++;join_choice(1,"zombie");assert(!zombie&&infections==1);
 special=false;last=true;clockNow++;join_choice(1,"zombie");assert(!zombie&&infections==1);
 last=false;team=CS_TEAM_UNASSIGNED;alive=false;clockNow++;join_choice(1,"auto");userid++;finish_join(scheduled);assert(!alive&&respawns==1&&!opened);
 failTeam=true;team=CS_TEAM_SPECTATOR;clockNow++;join_choice(1,"auto");finish_join(scheduled);assert(!opened&&!alive&&team==CS_TEAM_CT&&fallbacks==1&&respawns==1);
 failSet=true;team=CS_TEAM_UNASSIGNED;clockNow++;join_choice(1,"auto");finish_join(scheduled);assert(opened==1&&!alive);
 connected=false;clockNow++;join_choice(1,"auto");assert(teamCommands==5&&classCommands==7);
 connected=true;alive=true;team=CS_TEAM_CT;refuseSpectator=true;clockNow++;join_choice(1,"spectator");assert(alive&&team==CS_TEAM_CT&&!kills);
 refuseSpectator=false;leaveAlive=true;clockNow++;join_choice(1,"spectator");assert(!alive&&team==CS_TEAM_SPECTATOR&&kills==1);
}
''')
 def test_team_card_updates_when_capability_arrives_after_opening(self):
  source=(ROOT/'czm/menu/CzmServerMenu.cpp').read_text()
  cpp(BASE+r'''
typedef int HFont;enum{CZMF_MENU_TITLE,CZMF_PANEL_TEXT,CZMF_UI_META};
static int CZM_Font(int n){return n;}static int CZM_FontHeight(int){return ScreenHeight*.04f;}
static int CZM_WrapText(int,const char*,int,int*,int){return 2;}
static int slot=-1,motd=0;static bool play=false;
static int CZM_OfficialSlotNow(){return slot;}static bool CZM_PlayServer(){return play;}
namespace EngFuncs{static void CvarSetString(const char*k,const char*v){assert(!strcmp(k,"czm_motd_off")&&!strcmp(v,"1"));motd++;}}
class CCzmTeamCard{public:enum{BTN_NONE,BTN_PLAY,BTN_SPECTATE,BTN_T,BTN_AUTO,BTN_CT,BTN_CLOSE,BTN_COUNT};
 int m_iSlot=-1,m_iPressed=3,W,H,m_iTextY;bool m_bPlay=false,m_bSpectate=true,m_bCancel=false;char m_szText[10]="test";
 CzmRect m_card,m_map,m_btn[BTN_COUNT];void Layout();};
'''+function(source,'void CCzmTeamCard::Layout(')+r'''
int main(){for(auto screen:{std::pair<int,int>(640,360),{1536,716},{2340,1080},{1024,768},{2000,1200}}){
 ScreenWidth=screen.first;ScreenHeight=screen.second;CCzmTeamCard c;play=false;slot=-1;c.Layout();assert(!c.m_bPlay&&c.m_btn[c.BTN_AUTO].w>0&&!c.m_btn[c.BTN_PLAY].w);
 play=true;c.Layout();assert(c.m_bPlay&&!c.m_iPressed&&!c.m_btn[c.BTN_AUTO].w);
 int buttons[]={c.BTN_PLAY,c.BTN_SPECTATE,c.BTN_CT,c.BTN_T};
 for(int i:buttons){auto a=c.m_btn[i];assert(a.w>0&&a.h>0&&a.x>=0&&a.y>=0&&a.x+a.w<=ScreenWidth&&a.y+a.h<=ScreenHeight);}
 assert(c.m_btn[c.BTN_PLAY].y==c.m_btn[c.BTN_SPECTATE].y&&c.m_btn[c.BTN_T].y>c.m_btn[c.BTN_PLAY].y);
 play=false;c.Layout();assert(!c.m_bPlay);slot=0;c.Layout();assert(c.m_bPlay);
}assert(motd==10);}
''')
 def test_unfamiliar_zombie_source_is_rejected(self):
  spec=importlib.util.spec_from_file_location('czm_zp',ROOT/'server/zm/tools/patch_zombie_menus.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with self.assertRaises(ValueError):m.patch('public plugin_init() {}')
  self.assertEqual(m.patch(m.MARKER),m.MARKER)
