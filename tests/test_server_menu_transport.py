"""Exercise the actual ShowMenu receiver with fragmented rich and localized stock menus."""
from pathlib import Path
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
#define MAX_MENU_STRING 4096
#define FALSE 0
#define HUD_DRAW 1
enum { MENU_RADIOA, MENU_RADIOB, MENU_RADIOC, MENU_NUMERICAL_MENU };
char g_szMenuString[MAX_MENU_STRING], g_szPrelocalisedMenuString[MAX_MENU_STRING];
static char g_szRichMenuString[MAX_MENU_STRING];
static bool s_bCardsShown;
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
struct { void Cvar_Set(const char *,const char *s) { published=s; } } gEngfuncs;
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
    void UserCmd_OldStyleMenuClose(){PublishCards(false);}
    void ShowVGUIMenu(int){}
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
}
'''


class ServerMenuTransportTests(unittest.TestCase):
    def test_fragmented_rich_menu_bypasses_stock_localization(self):
        source = (ROOT / "cl_dll/menu.cpp").read_text()
        code = PREAMBLE
        for signature in ("void CHudMenu::PublishCards(", "static void CZM_PlainMenuText(",
                          "int CHudMenu :: MsgFunc_ShowMenu("):
            code += function(source, signature) + "\n"
        code += SCENARIO
        with tempfile.TemporaryDirectory(prefix="czm-menu-wire-") as folder:
            path = Path(folder)
            (path / "check.cpp").write_text(code)
            subprocess.run(["g++", "-std=c++11", "-Wall", str(path / "check.cpp"), "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)


if __name__ == "__main__":
    unittest.main()
