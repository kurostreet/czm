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
 def test_actual_weapon_parser_and_grid_geometry(self):
  s=(ROOT/'czm/menu/CzmShop.cpp').read_text()
  code=BASE+s[s.index('enum\n{'):s.index('static const struct\n{\n\tconst char *ru, *en; // two lines')]
  code+=re.search(r'^#define CZM_WEAPON_EXTRA .*$',s,re.M).group(0)+'\n'
  code+=s[s.index('struct CzmWeaponMenu'):s.index('// the menu line without colour codes')]
  for sig in ['static const CzmShopItem *FindWeapon(','static bool Contains(','static void PlainLine(','static bool ParseWeaponMenu(']:code+=function(s,sig)+'\n'
  code+=r'''
#define CZM_QUICK 5
class CCzmShop{public:
 bool m_bServerMenu=true,m_bGrid=true;int m_iSlots=7,W,H;CzmWeaponMenu m_wmenu={};
 CzmRect m_top,m_close,m_tabs[CAT_COUNT],m_quick[5],m_info,m_buy,m_cards[8];int m_iWheelX,m_iWheelY,m_iWheelR;
 void Layout();int QuickCount()const;int QuickKey(int,const char**)const;
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
 def test_official_team_buttons_use_distinct_commands(self):
  s=(ROOT/'czm/menu/CzmServerMenu.cpp').read_text()
  code=BASE+r'''
static std::string sent;static void CZM_PlayClick(){}
namespace EngFuncs{static void ClientCmdF(bool,const char*f,...){char b[128];va_list a;va_start(a,f);vsnprintf(b,sizeof(b),f,a);va_end(a);sent=b;}}
class CCzmTeamCard{public:enum{BTN_NONE,BTN_PLAY,BTN_SPECTATE,BTN_T,BTN_AUTO,BTN_CT,BTN_CLOSE,BTN_COUNT};int m_iSlot=0;void Press(int);void Hide(){}};
'''+function(s,'void CCzmTeamCard::Press(')+r'''
int main(){CCzmTeamCard c;c.Press(c.BTN_PLAY);assert(sent=="czm_join auto\n");c.Press(c.BTN_SPECTATE);assert(sent=="czm_join spectator\n");c.Press(c.BTN_CT);assert(sent=="czm_join human\n");c.Press(c.BTN_T);assert(sent=="czm_join zombie\n");c.m_iSlot=-1;c.Press(c.BTN_CT);assert(sent=="jointeam 2\n");}
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
 def test_unfamiliar_zombie_source_is_rejected(self):
  spec=importlib.util.spec_from_file_location('czm_zp',ROOT/'server/zm/tools/patch_zombie_menus.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with self.assertRaises(ValueError):m.patch('public plugin_init() {}')
  self.assertEqual(m.patch(m.MARKER),m.MARKER)
