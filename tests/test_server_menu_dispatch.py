"""Run actual window choices through the gameplay DLL's menu/weapon dispatcher."""
from pathlib import Path
import re
import unittest

from test_combat_controls import build
from test_loading_errors import function
from test_server_menu_transport import CPP_MENU

ROOT = Path(__file__).resolve().parents[1]


class ServerMenuDispatchTests(unittest.TestCase):
    def test_current_packet_dispatch_and_stale_selection_never_selects_a_weapon(self):
        window = (ROOT / "czm/menu/CzmServerMenu.cpp").read_text()
        menu = (ROOT / "cl_dll/menu.cpp").read_text()
        ammo = (ROOT / "cl_dll/ammo.cpp").read_text()
        code = CPP_MENU + r'''
#include <vector>
#include <cstdarg>
#include <cstdlib>
#define SM_MAX_TABS 32
#define SM_MAX_CARDS 10
#define MAX_MENU_STRING 4096
#define FALSE 0
enum { HUD_DRAW=1,MAX_WEAPON_SLOTS=10,HIDEHUD_WEAPONS=1,HIDEHUD_ALL=2,WEAPON_SUIT=0 };
static std::vector<std::string> queue,network;
static std::string packet;
static int weaponLookups;
struct CHudMenu {
 int m_fMenuDisplayed=0,m_bitsValidSlots=0,m_iFlags=0;
 void PublishCards(bool);void SelectMenuItem(int);void UserCmd_OldStyleMenuClose();void Reset(){}
};
struct CHudAmmo {struct Cvar{float value=1;}fast;Cvar*m_pHud_FastSwitch=&fast;
 void SlotInput(int);void UserCmd_Slot1();void UserCmd_Slot2();void UserCmd_Slot3();void UserCmd_Slot4();void UserCmd_Slot5();
 void UserCmd_Slot6();void UserCmd_Slot7();void UserCmd_Slot8();void UserCmd_Slot9();void UserCmd_Slot10();};
struct {CHudMenu m_Menu;CHudAmmo m_Ammo;int m_fPlayerDead=0,m_iHideHUDDisplay=0,m_iWeaponBits=3;}gHUD;
struct WEAPON {int iSlot,iSlotPos,iId;const char*szName;};
static WEAPON weapon={0,0,7,"weapon_test"},*gpActiveSel;static int g_weaponselect;
struct WeaponsResource {void SelectSlot(int,int,int);WEAPON*GetFirstPos(int slot){weaponLookups++;weapon.iSlot=slot;return &weapon;}WEAPON*GetNextActivePos(int,int){return nullptr;}}gWR;
static bool s_bCardsShown;static int s_iCardsSerial;
static char g_szRichMenuString[MAX_MENU_STRING],g_szMenuString[MAX_MENU_STRING];
static std::vector<std::string> args;
struct {int realTime=1000;}uiStatic;
struct Engine {
 int Cmd_Argc(){return args.size();}const char*Cmd_Argv(int i){return args[i].c_str();}
 void Cvar_Set(const char*,const char*text){packet=text;}
 void pfnServerCmd(const char*text){network.push_back(text);}
}gEngfuncs;
static void ClientCmd(const char*text){queue.push_back(text);}
static void ServerCmd(const char*text){network.push_back(text);}
static void PlaySound(const char*,int){}
static void Touch_CloseMenu(){}
namespace EngFuncs {
 static void ClientCmd(bool,const char*text){queue.push_back(text);}
 static void ClientCmdF(bool,const char*format,...){char text[256];va_list a;va_start(a,format);vsnprintf(text,sizeof(text),format,a);va_end(a);queue.push_back(text);}
 static void SetTextInputRect(int,int,int,int){}
 static const char*GetCvarString(const char*){return "Player";}
}
static void UI_EnableTextInput(bool){}
static void CZM_PlayClick(){}
static bool CZM_OnSurvivalServer(){return true;}
static const char*CZM_OnlineKey(){return "";}
static void CZM_AccountShow(const char*,const char*){}
'''
        code += window[window.index("struct CzmMenuTab"):window.index("static bool IsRichMenu")]
        enum = re.search(r"\benum\s*\{(.*?)\};", window[window.index("class CCzmServerWindow"):], re.S).group(0)
        code += "\nstruct CCzmServerWindow {\n" + enum + r'''
 CzmRichMenu m_menu={};int m_iPicked=-1,m_iPickTime=0,m_request=0,m_nextOffset=-1,m_friendPage=0,m_friendOffset=0,m_friendCount=0,m_iTabFirst=0,m_iTabRows=7;
 bool m_typing=false;CzmRect m_field={};char m_notice[192]={},m_szTab[16]={};
 bool Waiting()const{return m_iPicked>=0&&uiStatic.realTime-m_iPickTime<700;}
 void Activate(int);void Submit(){}void FetchFriends(int){}void Close(bool){}void InviteFriend(int){}
};
'''
        code += function(window, "void CCzmServerWindow::Activate(") + "\n"
        for signature in ("void CHudMenu::PublishCards(", "void CHudMenu :: SelectMenuItem(",
                          "void CHudMenu::UserCmd_OldStyleMenuClose(", "static void SelectShopCard("):
            code += function(menu, signature) + "\n"
        code += function(ammo, "void WeaponsResource :: SelectSlot(") + "\n"
        code += function(ammo, "void CHudAmmo::SlotInput(") + "\n"
        for slot in range(1, 11):
            code += function(ammo, f"void CHudAmmo::UserCmd_Slot{slot}(") + "\n"
        code += r'''
static void Drain(){
 while(!queue.empty()){
  std::string cmd=queue.front();queue.erase(queue.begin());
  if(cmd.compare(0,4,"slot")==0){
   int slot=atoi(cmd.c_str()+4);
   void(CHudAmmo::*handlers[])()={&CHudAmmo::UserCmd_Slot1,&CHudAmmo::UserCmd_Slot2,&CHudAmmo::UserCmd_Slot3,&CHudAmmo::UserCmd_Slot4,&CHudAmmo::UserCmd_Slot5,&CHudAmmo::UserCmd_Slot6,&CHudAmmo::UserCmd_Slot7,&CHudAmmo::UserCmd_Slot8,&CHudAmmo::UserCmd_Slot9,&CHudAmmo::UserCmd_Slot10};
   assert(slot>=1&&slot<=10);(gHUD.m_Ammo.*handlers[slot-1])();
  }else if(cmd.compare(0,16,"czm_shop_select ")==0){
   char name[32],serial[24],slot[24];assert(sscanf(cmd.c_str(),"%31s %23s %23s",name,serial,slot)==3);
   args={name,serial,slot};SelectShopCard();
  }else{assert(cmd.compare(0,11,"menuselect ")==0);while(!cmd.empty()&&cmd.back()=='\n')cmd.pop_back();network.push_back(cmd);}
 }
}
static void Announce(CCzmServerWindow&w){
 gHUD.m_Menu.m_fMenuDisplayed=1;gHUD.m_Menu.m_bitsValidSlots=(1<<0)|(1<<6)|(1<<8)|(1<<9);
 gHUD.m_Menu.m_iFlags=HUD_DRAW;snprintf(g_szRichMenuString,sizeof(g_szRichMenuString),"#czm1\tmenu\tstandalone\tServer\n1. Enabled\n2. Disabled\n7. Language\n");
 gHUD.m_Menu.PublishCards(true);w.m_menu.serial=s_iCardsSerial;w.m_menu.validSlots=gHUD.m_Menu.m_bitsValidSlots;
 w.m_menu.navigation=true;w.m_menu.numCards=3;w.m_menu.menuPage=1;w.m_menu.menuPages=2;w.m_menu.nextSlot=9;
 for(int i=0;i<3;i++){w.m_menu.cards[i].key=i==2?7:i+1;w.m_menu.cards[i].enabled=i!=1;}
 w.m_iPicked=-1;network.clear();queue.clear();weaponLookups=0;
}
int main(){
 CCzmServerWindow w;Announce(w);int serial=s_iCardsSerial;
 w.Activate(w.HIT_CARD+1);Drain();assert(network.empty()&&gHUD.m_Menu.m_fMenuDisplayed);
 w.Activate(w.HIT_CARD);Drain();assert(network.size()==1&&network[0]=="menuselect 1");
 assert(!gHUD.m_Menu.m_fMenuDisplayed&&!gHUD.m_Menu.m_bitsValidSlots&&!s_bCardsShown&&packet.empty()&&!weaponLookups);
 // A timeout retry still belongs to the original packet. A raw slot here
 // would now select a weapon, since the accepted menu was already cleared.
 uiStatic.realTime+=1000;network.clear();w.Activate(w.HIT_CARD);Drain();
 assert(network.empty()&&weaponLookups==0);
 // A newer server menu rejects an old window, and honors its current mask.
 Announce(w);w.m_menu.serial=serial;w.Activate(w.HIT_CARD);Drain();
 assert(network.empty()&&weaponLookups==0&&gHUD.m_Menu.m_fMenuDisplayed);
 Announce(w);gHUD.m_Menu.m_bitsValidSlots&=~1;w.Activate(w.HIT_CARD);Drain();
 assert(network.empty()&&!weaponLookups&&gHUD.m_Menu.m_fMenuDisplayed);
 // A legitimate fresh submenu is accepted, preserving reordered real slots.
 Announce(w);w.Activate(w.HIT_CARD+2);Drain();assert(network.size()==1&&network[0]=="menuselect 7"&&!weaponLookups);
 Announce(w);std::swap(w.m_menu.cards[0],w.m_menu.cards[2]);w.Activate(w.HIT_CARD);Drain();assert(network.size()==1&&network[0]=="menuselect 7");
 Announce(w);w.Activate(w.HIT_MENU_NEXT);Drain();assert(network.size()==1&&network[0]=="menuselect 9"&&!weaponLookups);
 Announce(w);w.m_menu.prevSlot=10;w.Activate(w.HIT_MENU_PREV);Drain();assert(network.size()==1&&network[0]=="menuselect 10"&&!weaponLookups);
 // Prove the legacy path is covered too: normal gameplay slot commands still
 // use menu selection when a menu exists, then weapon selection after close.
 Announce(w);queue.push_back("slot1");Drain();assert(network.size()==1&&network[0]=="menuselect 1");
 network.clear();queue.push_back("slot1");Drain();assert(weaponLookups>0&&network.size()==1&&network[0]=="weapon_test");
}
'''
        build(code)


if __name__ == "__main__":
    unittest.main()
