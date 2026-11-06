"""Exercise the actual ShowMenu receiver with fragmented rich and localized stock menus."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]

PREAMBLE = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include "czm_weapon_menu.h"
#define MAX_MENU_STRING 4096
#define FALSE 0
#define HUD_DRAW 1
enum { MENU_RADIOA, MENU_RADIOB, MENU_RADIOC, MENU_NUMERICAL_MENU };
char g_szMenuString[MAX_MENU_STRING], g_szPrelocalisedMenuString[MAX_MENU_STRING];
static char g_szRichMenuString[MAX_MENU_STRING];
static bool s_bCardsShown;
static bool g_pMenu=true;
static int classicMenus;
static std::string touchSlots;
static void Touch_CloseMenu(){touchSlots.clear();}
struct {
 void pfnTouchAddClientButton(const char *,const char *,const char *command,float x,float y,float r,float b,
                              unsigned char *,int,float,int) {
    assert(x>.68f && y>0 && r>x && b>y && r<1 && b<1);
    touchSlots+=command;touchSlots+=' ';
 }
 void pfnTouchSetClientOnly(int){}
} gMobileAPI;
static int s_iCardsSerial, translations, bindings;
static std::string published;
#define strlcpy StubCopy
#define strlcat StubCat
static size_t strlcpy(char *d,const char *s,size_t n) { size_t len=strlen(s); if(n) snprintf(d,n,"%s",s); return len; }
static size_t strlcat(char *d,const char *s,size_t n) { size_t len=strlen(d); if(len<n) strlcpy(d+len,s,n-len); return len+strlen(s); }
struct Cvar { float value; } extended={0};
struct Localizer { char *BufferedLocaliseTextString(const char *s) {
    translations++; return const_cast<char *>(!strncmp(s,"#czm1",5)?"czm1":!strcmp(s,"#stock")?"Translated stock":s);
} };
struct { float m_flTime=10; Localizer m_TextMessage; } gHUD;
static float style=2, automatic=1, vgui=1;
static std::string commands;
static void ClientCmd(const char *s){commands+=s;}
struct { void Cvar_Set(const char *,const char *s) { published=s; }
 float pfnGetCvarFloat(const char *key){return !strcmp(key,"czm_shop")?style:!strcmp(key,"_vgui_menus")?vgui:automatic;}
} gEngfuncs;
static int KB_ConvertString(char *,char **) { bindings++; return 0; }
struct BufferReader {
    const unsigned char *p;
    BufferReader(const char *,void *b,int):p((unsigned char *)b){}
    int ReadShort(){int n=p[0]|(p[1]<<8);p+=2;return n;}
    int ReadChar(){return (signed char)*p++;}
    int ReadByte(){return *p++;}
    char *ReadString(){return (char *)p;}
};
struct CHudMenu {
    int m_bitsValidSlots=0,m_fWaitingForMore=0,m_fMenuDisplayed=0,m_iFlags=0;
    float m_flShutoffTime=0;
    Cvar *_extended_menus=&extended;
    bool CardsEnabled(){return true;}
    void PublishCards(bool);
    void PresentSurvivalShop(bool);
    void UserCmd_OldStyleMenuClose(){PublishCards(false);}
    void ShowVGUIMenu(int){classicMenus++;}
    int MsgFunc_ShowMenu(const char *,int,void *);
};
'''

SCENARIO = r'''
static void Receive(CHudMenu &menu,const std::string &text,int slots=1023) {
    for(size_t at=0;at<text.size();) {
        size_t n=text.size()-at; if(n>173)n=173;
        std::string packet;
        packet.push_back(slots&255);packet.push_back((slots>>8)&255);
        packet.push_back((char)-1);packet.push_back(at+n<text.size());
        packet.append(text,at,n);packet.push_back(0);
        menu.MsgFunc_ShowMenu("ShowMenu",packet.size(),&packet[0]);
        at+=n;
    }
}
int main() {
    CHudMenu menu;
    std::string rich="#czm1\tmenu\tmain\tМЕНЮ СЕРВЕРА\tSurvival\t1/32\tFair play\n#tabs\tmain:Главное:home:\tlvl:LVL MOD:chart:\n\n";
    for(int i=1;i<=9;i++)rich+="\\r"+std::to_string(i)+".\\w Карточка сервера с длинным названием\tПодпись +attack #literal и цвет\tusers\tFF8800\tNEW\n";
    rich+="\n\\r0.\\w Выход";
    assert(rich.size()>1024 && rich.size()<MAX_MENU_STRING);
    Receive(menu,rich);
    assert(translations==0 && bindings==0);
    assert(!strcmp(g_szRichMenuString,rich.c_str()));
    assert(published=="1 1023\n"+rich);
    assert(strstr(g_szMenuString,"Карточка сервера"));
    assert(!strstr(g_szMenuString,"#czm1") && !strchr(g_szMenuString,'\t'));
    assert(strstr(g_szMenuString,"0.\\w Выход"));
    Receive(menu,"#stock");
    assert(translations==1 && bindings==1);
    assert(!g_szRichMenuString[0] && published=="2 1023\nTranslated stock");
    menu.PublishCards(false);
    assert(published.empty());
    std::string weapon="#czmw1\tprimary\t0\t3\t0\t28\t0\t0\n\\yPrimary Weapon\n1. AK-47\n8. Remember [Off]\n0. Exit";
    Receive(menu,weapon);assert(published.find("#czmw1")!=std::string::npos&&translations==1);
    style=0;Receive(menu,weapon);assert(published.empty()&&strstr(g_szMenuString,"AK-47")&&!strstr(g_szMenuString,"#czmw1"));
    style=2;vgui=0;Receive(menu,weapon);assert(published.empty());
    vgui=1;automatic=0;
    Receive(menu,"#czmw1\tprimary\t0\t3\t0\t28\t0\t1\nPrimary Weapon\n1. AK-47");
    assert(published.empty()&&commands=="menuselect 10\n");
    Receive(menu,"#czm1\tmenu\tserver\tMENU\t\t\t\n#page\tform\tСообщение админу\tczm_admin_msg\tТекст\n#body\tПервая строка\n#body\tВторая строка\n1. Открыть\n0. Назад",513);
    assert(strstr(g_szMenuString,"Сообщение админу")&&strstr(g_szMenuString,"Первая строка")&&strstr(g_szMenuString,"Вторая строка"));
    assert(!strstr(g_szMenuString,"#page")&&!strstr(g_szMenuString,"#body")&&published.find("#page")!=std::string::npos);
    // The same complete packet supports every style. Rendering it again never
    // issues a slot command or creates a new transaction.
    const auto before=commands;
    const std::string loadout="#czms1\t39\t0\t0\t2\t4\t5\t1\t1\t28\t26\t3\t0\t2\n"
        "#item\t0\t28\t4\t0\nPrimary weapon\n1. AK-47\n8. Sections\n9. Loadout\n0. Exit";
    Receive(menu,loadout,896);
    assert(s_bCardsShown && published.find(loadout)!=std::string::npos && menu.m_bitsValidSlots==896);
    style=1;
    menu.PresentSurvivalShop(false);
    assert(published.find(loadout)!=std::string::npos);
    vgui=0;style=0;
    const int oldClassic=classicMenus;
    menu.PresentSurvivalShop(false);
    assert(!s_bCardsShown && published.empty() && classicMenus==oldClassic);
    assert(touchSlots=="slot8 slot9 slot10 ");
    assert(strstr(g_szMenuString,"9. Loadout")&&!strstr(g_szMenuString,"#czms1")&&!strstr(g_szMenuString,"#item"));
    assert(menu.m_fMenuDisplayed && menu.m_bitsValidSlots==896);
    vgui=1;style=2;
    menu.PresentSurvivalShop(false);
    assert(published.find(loadout)!=std::string::npos && commands==before && touchSlots.empty());
    style=0;vgui=0;Receive(menu,loadout,513);
    assert(touchSlots=="slot1 slot10 " && classicMenus==oldClassic);

}
'''


class ServerMenuTransportTests(unittest.TestCase):
    def test_fragmented_rich_menu_bypasses_stock_localization(self):
        source = (ROOT / "cl_dll/menu.cpp").read_text()
        code = PREAMBLE
        for signature in ("void CHudMenu::PublishCards(", "static void CZM_PlainMenuText(",
                          "static void CZM_SurvivalClassicButtons(",
                          "void CHudMenu::PresentSurvivalShop(", "int CHudMenu :: MsgFunc_ShowMenu("):
            code += function(source, signature) + "\n"
        code += SCENARIO
        with tempfile.TemporaryDirectory(prefix="czm-menu-wire-") as folder:
            path = Path(folder)
            (path / "check.cpp").write_text(code)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-D__ANDROID__", "-I"+str(ROOT/"common"), str(path / "check.cpp"), "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)


CPP_MENU = r"""
#include "czm_server_view.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <algorithm>
#include <string>
#include <initializer_list>
#define Q_min(a,b) std::min(a,b)
#define Q_max(a,b) std::max(a,b)
inline void Q_strncpy(char*d,const char*s,size_t n){if(n){size_t k=std::min(n-1,strlen(s));memcpy(d,s,k);d[k]=0;}}
inline void Q_strncat(char*d,const char*s,size_t n){size_t k=strlen(d);if(k<n)snprintf(d+k,n-k,"%s",s);}
inline bool CZM_IsRussian(){return true;}
inline unsigned int PackRGBA(int r,int g,int b,int a){return r|(g<<8)|(b<<16)|((unsigned)a<<24);}
inline int bound(int lo,int x,int hi){return std::max(lo,std::min(x,hi));}
struct CzmRect{int x,y,w,h;};
inline CzmRect CZM_Rect(int x,int y,int w,int h){return {x,y,w,h};}
"""


def run_cpp(code):
    with tempfile.TemporaryDirectory(prefix="czm-menu-policy-") as folder:
        path = Path(folder)
        (path / "check.cpp").write_text(code)
        subprocess.run(["g++", "-std=c++11", "-Wall", "-I"+str(ROOT/"common"), str(path / "check.cpp"), "-o", str(path / "check")], check=True)
        subprocess.run([str(path / "check")], check=True)


class ServerMenuStructureTests(unittest.TestCase):
    def test_current_roles_ancestor_access_and_expiry_guard_dispatch(self):
        source = (ROOT / 'server/zm/scripting/czm_menu.sma').read_text()
        api = (ROOT / 'server/zm/scripting/include/czm_menu.inc').read_text()
        admin = (ROOT / 'server/zm/scripting/czm_admin.sma').read_text()
        code = CPP_MENU + '\n'.join(re.findall(r'^#define CZM_MENU_.*$', api, re.M))
        code += r"""
#define MAX_SECTIONS 32
#define MaxClients 32
#define LibType_Library 1
static int role,clockNow=100,g_priv[33],g_privUntil[33],g_numSections=4,g_numItems=2;
static int get_systime(){return clockNow;}
static int staff_of(int){return role;}
static bool LibraryExists(const char*,int){return true;}
struct Section{const char*SecKey;const char*SecParent;int SecAccess;};
static Section g_sections[32]={{"main","",0},{"admin","",CZM_MENU_ADMIN},{"child","admin",0},{"vip","",CZM_MENU_VIP}};
struct Item{int ItAccess;const char*ItOpen;};
static Item g_items[2]={{0,""},{0,"admin"}};
static int find_section(const char*key){for(int i=0;i<g_numSections;i++)if(!strcmp(key,g_sections[i].SecKey))return i;return -1;}
"""
        privilege = function(admin, '\nprivilege_of(id)\n').replace('privilege_of(id)', 'int czm_privilege(int id)')
        privilege = privilege.replace('1 <= id <= MaxClients', '1 <= id && id <= MaxClients')
        code += privilege + '\n'
        for signature, cpp in [('bool:allowed(id, access)', 'bool allowed(int id,int access)'),
                               ('bool:section_allowed(id, s)', 'bool section_allowed(int id,int s)'),
                               ('section_root(s)', 'int section_root(int s)'),
                               ('bool:item_allowed(id, i)', 'bool item_allowed(int id,int i)'),
                               ('bool:can_dispatch(id, s, i)', 'bool can_dispatch(int id,int s,int i)')]:
            body = function(source, signature).replace(signature, cpp).replace('new ', 'int ')
            body = re.sub(r'(g_sections|g_items)\[([a-z]+)\]\[([A-Za-z]+)\]', r'\1[\2].\3', body)
            code += body + '\n'
        code += r"""
int main(){
 const int paid[]={0,CZM_MENU_VIP,CZM_MENU_PREMIUM,CZM_MENU_DELUXE,CZM_MENU_TESTER};
 for(role=0;role<=2;role++)for(int p=0;p<=4;p++){
   g_priv[1]=p;g_privUntil[1]=0;
   int granted=paid[p]|(role?CZM_MENU_STAFF:0)|(role==2?CZM_MENU_HEAD:0)|((role||p)?CZM_MENU_PRIV:0);
   assert(allowed(1,0));
   for(int mask=1;mask<128;mask++)assert(allowed(1,mask)==!!(mask&granted));
   assert(!allowed(1,128));assert(!allowed(1,CZM_MENU_ALL|128));
   assert(section_allowed(1,2)==(role==2));
   assert(can_dispatch(1,2,0)==(role==2));
   assert(can_dispatch(1,0,1)==(role==2));
 }
 role=2;assert(can_dispatch(1,2,0));role=0;assert(!can_dispatch(1,2,0));
 g_priv[1]=1;g_privUntil[1]=101;assert(section_allowed(1,3));
 clockNow=101;assert(!section_allowed(1,3));assert(!czm_privilege(0)&&!czm_privilege(33));
 assert(section_root(2)==1);
 g_sections[1].SecParent="child";assert(!section_allowed(1,2)&&section_root(2)==-1);
 g_sections[2].SecParent="missing";assert(!section_allowed(1,2)&&section_root(2)==-1);
}
"""
        run_cpp(code)

    def test_old_and_new_headers_and_native_submenus_preserve_real_slots(self):
        source = (ROOT / 'czm/menu/CzmServerMenu.cpp').read_text()
        code = CPP_MENU + '\n'.join(re.findall(r'^#define (?:MAX_CARDS|MAX_LINES|SM_MAX_TABS|SM_MAX_CARDS) .*$', source, re.M)) + '\n'
        code += source[source.index('struct CzmCard'):source.index('static void TrimCopy')]
        code += source[source.index('struct CzmMenuTab'):source.index('static bool IsRichMenu')]
        for sig in ('static void TrimCopy(', 'static void SplitLine(', 'static void ParseMenu(',
                    'static void NextField(', 'static unsigned int HexColor(', 'static void ParseRich(', 'static void PlainAsRich('):
            code += function(source,sig)+'\n'
        code += r"""
int main(){
 CzmRichMenu root,child,plain;
 ParseRich("1 3\n#czm1\tmenu\tadmin\tSERVER MENU\tSurvival\t1/32\tFair\n#tabs\tmain:Home:star:\tadmin:Admin:shield:\n\\r1.\\w Players\tPick\tusers\tFF8800\tNEW\n",root);
 assert(root.numTabs==2&&root.numCards==1&&!root.parent[0]&&!root.root[0]);
 ParseRich("2 3\n#czm1\tmenu\tadmin_players\tSERVER MENU\tAdmin / Players\t1/32\tFair\tadmin\tadmin\n#tabs\tmain:Home:star:\tadmin:Admin:shield:\n\\r1.\\w Punish\tPick\tusers\tFF8800\t\n",child);
 assert(!strcmp(child.parent,"admin")&&!strcmp(child.root,"admin"));
 PlainAsRich("3 5\n\\yPick player\n\\w1. Alice\n\\d2. Disabled\n\\w3. Bob\\R37 LVL\n\\w0. Exit",&child,plain);
 assert(plain.serial==3&&plain.numTabs==2&&plain.numCards==3&&!plain.tab[0]);
 assert(!strcmp(plain.parent,"admin_players")&&!strcmp(plain.root,"admin"));
 assert(plain.cards[0].key==1&&plain.cards[0].enabled&&!plain.cards[1].enabled&&plain.cards[2].key==3&&plain.cards[2].enabled);
 assert(!strcmp(plain.cards[2].sub,"37 LVL"));
 CzmRichMenu next;PlainAsRich("4 1\nDuration\n1. One hour",&plain,next);
 assert(!strcmp(next.parent,"admin_players"));
 PlainAsRich("5 1\nVote\n1. Yes",NULL,next);assert(next.numTabs==0&&!next.parent[0]&&!next.root[0]);
 PlainAsRich("6 1\nZombie Plague 4.4\n1. Choose weapon",NULL,next);assert(!strcmp(next.head,"МЕНЮ ЗОМБИ")&&!next.parent[0]);
 ParseRich("7 512\n#czm1\tmenu\tserver\tSERVER MENU\tSurvival\t2/32\tFair\t\tserver\n#tabs\tmain:Главная:star:\tserver:Сообщество:globe:\n#page\tform\tСообщение админу\tczm_admin_msg\tВведите сообщение\tСохранённый текст\n#body\tПервая строка\n#body\tВторая строка\n",next);
 assert(next.kind==CzmServerView::Form&&!strcmp(next.parent,"server")&&!strcmp(next.command,"czm_admin_msg"));
 assert(!strcmp(next.prefill,"Сохранённый текст")&&!strcmp(next.body,"Первая строка\nВторая строка\n"));
 assert(!strcmp(next.tabs[0].name,"Главная")&&!strcmp(next.tabs[1].name,"Сообщество"));
 ParseRich("8 512\n#czm1\tmenu\tplayers\tMENU\tSurvival\t2/32\tFair\n#page\tfriends\tПригласить\t@friends\t\n#body\tВыбери друга\n",next);
 assert(next.kind==CzmServerView::Friends&&next.numCards==0&&!strcmp(next.parent,"players"));
 ParseRich("9 512\n#czm1\tmenu\tmain\tMENU\t\t\t\n#page\tform\tUnsafe\tquit;exec evil\t\n",next);assert(next.kind==CzmServerView::Text);
 ParseRich("10 897\n#czm1\tmenu\tstandalone\tAdmin menu\t\t\t\n#nav\t1\t1\t2\tshield\n1. Kick\t\tuser\n8. Back\n9. Next\n0. Exit",root);
 PlainAsRich("11 769\nKick Player Menu 2/3\n1. Bob\n9. Дальше...\n0. Назад",&root,next);
 assert(next.navigation&&next.canGoBack&&next.nextSlot==9&&next.prevSlot==10&&next.numCards==1);
 assert(!strcmp(next.cards[0].name,"Bob")&&!next.menuPages);
}
"""
        run_cpp(code)

    def test_sidebar_scroll_and_back_button_fit_all_supported_screens(self):
        source = (ROOT/'czm/menu/CzmServerMenu.cpp').read_text()
        code = CPP_MENU + '\n'.join(re.findall(r'^#define (?:SM_MAX_TABS|SM_MAX_CARDS) .*$', source, re.M)) + '\n'
        code += source[source.index('struct CzmMenuTab'):source.index('static bool IsRichMenu')]
        code += r"""
static int ScreenWidth,ScreenHeight;
enum { CZMF_UI_META };
static int CZM_Font(int font){return font;}
static int CZM_FontHeight(int){return 15;}
struct CCzmServerWindow{
 CzmRichMenu m_menu={};int m_iTabFirst=0,m_iTabRows=0,W,H;
 CzmRect m_win,m_head,m_side,m_body,m_foot,m_close,m_back,m_tabsUp,m_tabsDown;
 CzmRect m_navPrev,m_navNext,m_cardInfo;
 CzmRect m_content,m_field,m_submit,m_prev,m_next,m_refresh,m_friendRows[6];
 void Layout(int);
};
"""
        code += function(source,'void CCzmServerWindow::Layout(')
        code += r"""
static bool inside(CzmRect a,CzmRect b){return a.w>0&&a.h>0&&a.x>=b.x&&a.y>=b.y&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h;}
int main(){
 for(auto wh:{std::make_pair(640,360),std::make_pair(1536,716),std::make_pair(2340,1080),std::make_pair(1024,768)})
 for(int tabs:{0,5,10,11,32})for(int first:{0,5,31})for(int nested:{0,1}){
  ScreenWidth=wh.first;ScreenHeight=wh.second;CCzmServerWindow w;w.m_menu.numTabs=tabs;w.m_menu.numCards=9;
  if(nested)strcpy(w.m_menu.parent,"admin");
  w.m_iTabFirst=first;w.Layout(0);
  for(int i=0;i<tabs;i++){
   auto t=w.m_menu.tabs[i].rect;
   if(i>=w.m_iTabFirst&&i<w.m_iTabFirst+w.m_iTabRows)assert(inside(t,w.m_side));else assert(t.w==0&&t.h==0);
  }
  for(int i=0;i<9;i++){assert(inside(w.m_menu.cards[i].rect,w.m_body));if(nested)assert(w.m_menu.cards[i].rect.y>=w.m_back.y+w.m_back.h);}
  if(nested)assert(inside(w.m_back,w.m_body));
  if(tabs>10){assert(inside(w.m_tabsUp,w.m_side)&&inside(w.m_tabsDown,w.m_side));assert(w.m_iTabRows>0);}
  if(tabs==32&&first==31)assert(w.m_menu.tabs[31].rect.w>0);
 }
}
"""
        run_cpp(code)


if __name__ == "__main__":
    unittest.main()
