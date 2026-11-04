"""The actual spectator action only covers real observers and releases its touch target."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#define UI_DIR "gfx/czm/ui/"
#define Q_min(a,b) ((a)<(b)?(a):(b))
#define Q_max(a,b) ((a)>(b)?(a):(b))
int ScreenWidth=1536,ScreenHeight=716,added,removed,drawn;
bool active=true,ru=true;
int team=0;
bool CL_IsActive(){return active;}
bool CZM_IsRussian(){return ru;}
struct Stack { bool active=false;bool IsActive(){return active;} };
struct { Stack menu,client; } uiStatic;
struct Globals { bool demoplayback=false; } globals,*gpGlobals=&globals;
namespace EngFuncs {
const char *GetCvarString(const char *){static char s[64];snprintf(s,sizeof(s),"100 %d 0 0 0 0",team);return s;}
float GetCvarFloat(const char *){return 1;}
void ClientCmd(bool,const char *s){assert(strstr(s,"touch_removebutton \"_czm_spec_exit\""));removed++;}
void ClientCmdF(bool,const char *s,...){assert(strstr(s,"\"czm_join auto\""));assert(strstr(s,"255 255 255 0 4"));added++;}
}
typedef int HFont;
enum { CZMF_TILE_NAME };
int CZM_Font(int){return 1;}
int CZM_FontHeight(int){return 20;}
int CZM_TextWidth(int,const char *s){int n=0;for(;*s;s++)if((*s&0xc0)!=0x80)n++;return n*10;}
struct CzmRect { int x,y,w,h; };
CzmRect CZM_Rect(int x,int y,int w,int h){assert(x>=0&&y>=0&&w>0&&h>0&&x+w<=ScreenWidth&&y+h<=ScreenHeight);return {x,y,w,h};}
int PackRGBA(int,int,int,int){return 0;}
int CZM_White(){return 0;}
void CZM_DrawImage(const char *,int,int,int,int,int){}
void CZM_DrawSliced(const char *,int,int,int,int,int,int,int){}
void CZM_DrawText(HFont,int,int,int,const char *s,int){assert(!strcmp(s,ru?"Выйти с наблюдателей":"Leave spectator mode"));drawn++;}
'''

SCENARIO = r'''
int main(){
 SpectatorExitFrame(""); assert(!added&&!drawn);
 // A dead teammate also uses an observer camera; the team stays T/CT, not spectator.
 for(team=1;team<=2;team++)SpectatorExitFrame("");
 assert(!added);
 team=3;SpectatorExitFrame("");SpectatorExitFrame("");assert(added==1&&drawn==2);
 uiStatic.client.active=true;SpectatorExitFrame("");assert(removed==1);
 uiStatic.client.active=false;ru=false;SpectatorExitFrame("");assert(added==2);
 SpectatorExitFrame("5 1023\n#czm1\tmenu");assert(removed==2);
 SpectatorExitFrame("");ScreenWidth=2000;SpectatorExitFrame("");assert(added==4&&removed==3);
 team=2;SpectatorExitFrame("");assert(removed==4);
 team=3;gpGlobals->demoplayback=true;SpectatorExitFrame("");assert(added==4);
 gpGlobals->demoplayback=false;active=false;SpectatorExitFrame("");assert(added==4);
 active=true;uiStatic.menu.active=true;SpectatorExitFrame("");assert(added==4);
}
'''


class SpectatorExitTests(unittest.TestCase):
    def test_visibility_and_touch_button_lifecycle(self):
        source = (ROOT / 'czm/menu/CzmServerMenu.cpp').read_text()
        code = HARNESS + function(source, 'static void SpectatorExitFrame(') + SCENARIO
        with tempfile.TemporaryDirectory(prefix='czm-spec-exit-') as folder:
            path = Path(folder)
            (path / 'check.cpp').write_text(code)
            subprocess.run(['g++', '-std=c++11', '-Wall', str(path/'check.cpp'), '-o', str(path/'check')], check=True)
            subprocess.run([str(path/'check')], check=True)
