"""Run native chat text capture through the actual engine/SDL input functions."""
from pathlib import Path
import unittest

from test_combat_controls import build
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs/engine"
SDL = ROOT / "3rdparty/SDL"


STUB = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>
typedef bool qboolean;typedef unsigned char byte;typedef bool SDL_bool;
enum {key_game,key_menu,key_message,ca_active=8,HOST_FRAME,HOST_NOFOCUS,HOST_SLEEP,
      BUGCOMP_ALWAYS_ENABLE_TEXT_INPUT=1,SDL_TEXTINPUT=2,SDL_TEXTEDITING=3,SDL_ENABLE=1,SDL_DISABLE=0,SDL_HINT_OVERRIDE=2};
const bool SDL_TRUE=true;
#define FBitSet(value,flag) ((value)&(flag))
#define SDL_HINT_ENABLE_SCREEN_KEYBOARD "SDL_ENABLE_SCREEN_KEYBOARD"
struct SDL_Rect {float x,y,w,h;};
struct SDL_Window{};SDL_Window window;
struct {int key_dest=key_menu,state=ca_active;bool accept_utf8=true;}cls;
struct {int status=HOST_FRAME,bugcomp=0;bool textmode=false;SDL_Window *hWnd=&window;}host;
struct {float value=0;}osk_enable;
struct {float scale_x=2,scale_y=2;}refState;
struct {int x=12,y=24,w=240,h=40;}key_textinput_rect;
bool key_textinput_enabled=false,chatActive=true,builtinKeyboard=false,softKeyboard=false;
int builtinCalls=0,starts=0,stops=0,shown=0,hidden=0,rects=0;
std::map<std::string,std::string> hints;
std::map<int,int> events;
SDL_Rect actualRect;
int Cvar_VariableInteger(const char *name){assert(!strcmp(name,"czm_match_chat_active"));return chatActive;}
const char *SDL_GetHint(const char *name){auto it=hints.find(name);return it==hints.end()?nullptr:it->second.c_str();}
bool SDL_GetHintBoolean(const char *name,bool fallback){const char *v=SDL_GetHint(name);return v?strcmp(v,"0")!=0:fallback;}
bool SDL_SetHintWithPriority(const char *name,const char *value,int priority){assert(priority==SDL_HINT_OVERRIDE);hints[name]=value;return true;}
bool SDL_ResetHint(const char *name){hints.erase(name);return true;}
char *SDL_strdup(const char *text){return strdup(text);}void SDL_free(void *p){free(p);}
int SDL_EventState(int type,int state){int old=events[type];events[type]=state;return old;}
SDL_Window *SDL_GetFocusWindow(){return &window;}
struct SDL_VideoDevice {
 void (*ShowScreenKeyboard)(SDL_VideoDevice*,SDL_Window*);
 void (*HideScreenKeyboard)(SDL_VideoDevice*,SDL_Window*);
 void (*StartTextInput)(SDL_VideoDevice*);
 void (*StopTextInput)(SDL_VideoDevice*);
};
void Show(SDL_VideoDevice*,SDL_Window*){shown++;softKeyboard=true;}
void Hide(SDL_VideoDevice*,SDL_Window*){hidden++;softKeyboard=false;}
void Start(SDL_VideoDevice*){starts++;assert(rects>0);}
void Stop(SDL_VideoDevice*){stops++;}
SDL_VideoDevice device={Show,Hide,Start,Stop},*_this=&device;
void SDL_SetTextInputRect(const SDL_Rect *rect){actualRect=*rect;rects++;}
void SDL_SetTextInputArea(SDL_Window *w,const SDL_Rect *rect,int){assert(w==&window);SDL_SetTextInputRect(rect);}
void Key_GetTextInputRect(int *x,int *y,int *w,int *h){*x=key_textinput_rect.x;*y=key_textinput_rect.y;*w=key_textinput_rect.w;*h=key_textinput_rect.h;}
void OSK_EnableTextInput(bool enabled,bool){builtinCalls++;builtinKeyboard=enabled;}
'''


def capture_source(backend):
    video = (SDL / "src/video/SDL_video.c").read_text()
    source = STUB + function(video, "void SDL_StartTextInput(void)")
    source += function(video, "void SDL_StopTextInput(void)")
    if backend == "sdl3":
        # The SDL3 platform function uses window-scoped signatures; use the
        # pinned SDL2 activation body to model the same documented hint/event contract.
        source += "\nvoid SDL_StartTextInput(SDL_Window *w){assert(w==&window);SDL_StartTextInput();}\n"
        source += "void SDL_StopTextInput(SDL_Window *w){assert(w==&window);SDL_StopTextInput();}\n"
    source += function((ENGINE / f"platform/{backend}/in_{backend}.c").read_text(), "void Platform_EnableTextInput(")
    source += function((ENGINE / "client/input/in_keys.c").read_text(), "void Key_EnableTextInput(")
    return source


SCENARIO = r'''
void Clear(){
 cls.key_dest=key_menu;cls.state=ca_active;host.status=HOST_FRAME;host.textmode=false;host.bugcomp=0;
 chatActive=true;key_textinput_enabled=false;osk_enable.value=0;builtinKeyboard=softKeyboard=false;
 builtinCalls=starts=stops=shown=hidden=rects=0;events.clear();hints.clear();
 key_textinput_rect.x=12;key_textinput_rect.y=24;key_textinput_rect.w=240;key_textinput_rect.h=40;
}
int main(){
 for(const char *prior:{(const char*)nullptr,"1","auto","0"}){
  Clear();if(prior)hints[SDL_HINT_ENABLE_SCREEN_KEYBOARD]=prior;
  Key_EnableTextInput(false,false);
  assert(events[SDL_TEXTINPUT]==SDL_ENABLE&&events[SDL_TEXTEDITING]==SDL_ENABLE);
  assert(host.textmode&&key_textinput_enabled&&!softKeyboard&&shown==0&&starts==1);
  assert(actualRect.x==6&&actualRect.y==12&&actualRect.w==120&&actualRect.h==20);
  assert(prior?SDL_GetHint(SDL_HINT_ENABLE_SCREEN_KEYBOARD)&&!strcmp(SDL_GetHint(SDL_HINT_ENABLE_SCREEN_KEYBOARD),prior):!SDL_GetHint(SDL_HINT_ENABLE_SCREEN_KEYBOARD));
  Key_EnableTextInput(false,false);assert(starts==1); // idempotent own-keyboard capture
  chatActive=false;Key_EnableTextInput(false,true);
  assert(events[SDL_TEXTINPUT]==SDL_DISABLE&&!host.textmode&&!key_textinput_enabled&&stops==1);
  cls.key_dest=key_message;Key_EnableTextInput(true,false);
  assert(events[SDL_TEXTINPUT]==SDL_ENABLE&&host.textmode&&key_textinput_enabled);
  assert(softKeyboard==(prior==nullptr||strcmp(prior,"0")));
  Key_EnableTextInput(false,true);assert(events[SDL_TEXTINPUT]==SDL_DISABLE&&!softKeyboard);
 }
 // Capture exists only while this active, focused game menu owns input.
 for(int lost=0;lost<4;lost++){
  Clear();Key_EnableTextInput(false,false);assert(events[SDL_TEXTINPUT]==SDL_ENABLE);
  if(lost==0)host.status=HOST_NOFOCUS;
  if(lost==1)host.status=HOST_SLEEP;
  if(lost==2)cls.state=0;
  if(lost==3)cls.key_dest=key_game;
  Key_EnableTextInput(false,true);
  assert(events[SDL_TEXTINPUT]==SDL_DISABLE&&!host.textmode&&!key_textinput_enabled&&!softKeyboard);
 }
 // A user's built-in OSK setting must not steal native capture, and leaving
 // native chat for the normal OSK must stop that SDL capture before returning.
 Clear();osk_enable.value=1;Key_EnableTextInput(false,false);
 assert(events[SDL_TEXTINPUT]==SDL_ENABLE&&host.textmode&&key_textinput_enabled&&builtinCalls==0&&!builtinKeyboard&&!softKeyboard);
 chatActive=false;cls.key_dest=key_message;Key_EnableTextInput(true,false);
 assert(events[SDL_TEXTINPUT]==SDL_DISABLE&&!host.textmode&&!key_textinput_enabled&&builtinKeyboard&&builtinCalls==1);
 Key_EnableTextInput(false,true);assert(!builtinKeyboard&&builtinCalls==2);
 return 0;
}
'''


TEXT_STUB = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
typedef unsigned char byte;typedef bool qboolean;
enum {key_game,key_menu,key_message,ca_active=8,HOST_FRAME,HOST_NOFOCUS};
struct {int key_dest=key_menu,state=ca_active;bool accept_utf8=false;}cls;
struct {int status=HOST_FRAME;}host;
bool chatActive=true;int conversions=0,reports=0;
struct SDL_TextInputEvent{char text[64];};
int Cvar_VariableInteger(const char *name){assert(!strcmp(name,"czm_match_chat_active"));return chatActive;}
void VGui_ReportTextInput(const char*){reports++;}
int Con_UtfProcessCharForce(int ch){conversions++;return ch<128?ch:'?';}
std::vector<int> chars;
void CL_CharEvent(int ch){chars.push_back(ch);}
'''


class MatchChatHardwareTests(unittest.TestCase):
    def test_real_platform_capture_suppresses_only_soft_keyboard_and_restores_hint(self):
        for backend in ("sdl2", "sdl3"):
            with self.subTest(backend=backend):
                build(capture_source(backend) + SCENARIO)

    def test_native_hardware_utf8_survives_legacy_game_charset(self):
        for backend, signature, invoke in (
                ("sdl2", "static void SDLash_InputEvent(", "SDLash_InputEvent(input);"),
                ("sdl3", "static void SDLash_TextEvent(", "SDLash_TextEvent(&input);")):
            with self.subTest(backend=backend):
                source = TEXT_STUB + function((ENGINE / f"platform/{backend}/host_{backend}.c").read_text(), signature)
                source += r'''
void Receive(){SDL_TextInputEvent input;strcpy(input.text,"Привет ё Ё 😀");
''' + invoke + r'''
}
int main(){
 Receive();assert(!conversions&&reports==1);
 std::string actual;for(int ch:chars)actual+=(char)ch;assert(actual=="Привет ё Ё 😀");
 // No change to the console/game's deliberately configured single-byte path.
 chars.clear();chatActive=false;Receive();assert(conversions>0&&reports==2);
 conversions=0;chars.clear();chatActive=true;cls.key_dest=key_game;Receive();assert(conversions>0);
 conversions=0;chars.clear();cls.key_dest=key_menu;cls.accept_utf8=true;chatActive=false;Receive();
 actual.clear();for(int ch:chars)actual+=(char)ch;assert(!conversions&&actual=="Привет ё Ё 😀");
 return 0;
}
'''
                build(source)


if __name__ == "__main__":
    unittest.main()
