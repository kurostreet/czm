"""Run actual loading teardown and Host_EndGame: keep the cause of failed entry and of a lost game."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs/engine"


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class LoadingErrorsTests(unittest.TestCase):
    def test_disconnect_keeps_original_cause(self):
        loading = (ENGINE / "client/czm_loading.c").read_text()
        host = (ENGINE / "common/host.c").read_text()
        source = PREAMBLE
        source += function(loading, "static void CZM_End(") + "\n"
        source += function(loading, "void CZM_Loading_SetError(") + "\n"
        source += function(loading, "void CZM_Loading_Dropped(") + "\n"
        source += function(loading, "void CZM_Loading_Disconnected(") + "\n"
        source += "void CL_Disconnect() { cls.state = ca_disconnected; CZM_Loading_Disconnected(); }\n"
        source += "void CL_Drop() { CZM_Loading_Dropped(); CL_Disconnect(); }\n"
        source += function(host, "void Host_EndGame(") + "\n"
        source += function(host, "void GAME_EXPORT Host_Error(") + "\n"
        source += SCENARIO
        with tempfile.TemporaryDirectory(prefix="czm-loading-errors-") as folder:
            path = Path(folder)
            (path / "check.cpp").write_text(source)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", str(path / "check.cpp"),
                            "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)


PREAMBLE = r'''
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <string>
typedef bool qboolean;
#define XASH_DEDICATED 0
#define GAME_EXPORT
#define S_RED ""
#define S_DEFAULT ""
#define MAX_SYSPATH 1024
#define Q_vsnprintf vsnprintf
#define Q_strcmp strcmp
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
#define COM_StringEmpty(s) (!(s)[0])
enum { ca_disconnected, ca_active, key_menu, key_console, CZM_STAGE_NONE, HOST_SHUTDOWN, HOST_ERR_FATAL };
struct { bool active, forced, cancelled, seen_loading, reopen_menu; char error[256], game_error[256]; double game_error_time; } czm;
struct { int state, key_dest; } cls;
struct { double realtime; int framecount, errorframe, status; } host;
struct { float value; } host_developer;
bool customLoading=true;
int consoleCalls=0, nativeMessages=0;
bool CZM_Loading_Enabled() { return customLoading; }
const char *va(const char *f, ...) { static char b[1024]; va_list a; va_start(a,f); vsnprintf(b,sizeof(b),f,a); va_end(a); return b; }
struct Var { std::string value; } czm_loading_error, czm_loading, czm_loading_stage;
void CZM_SetString(Var *v, const char *s) { v->value=s; }
void CZM_SetValue(Var *, float) {}
void Cvar_SetValue(const char *,float) {}
void CZM_AndroidProgress(int) {}
void UI_SetActiveMenu(bool) {}
void Con_Printf(const char *,...) {}
void SV_Shutdown(const char *) {}
void CL_ClearEdicts() {}
void Mod_FreeAll() {}
void Host_AbortCurrentFrame() {}
void CL_WriteMessageHistory() {}
void COM_InitHostState() {}
void Cbuf_Clear() {}
void Sys_Error(const char *,...) { assert(false); }
void Key_SetKeyDest(int) { consoleCalls++; }
void Platform_MessageBox(const char *,const char *,bool) { nativeMessages++; }
'''

SCENARIO = r'''
void Reset() {
 memset(&czm,0,sizeof(czm)); czm.active=true; czm.seen_loading=true;
 cls.state=ca_disconnected; cls.key_dest=key_menu; czm_loading_error.value.clear();
 host.framecount=20; host.errorframe=0; host.status=0; host_developer.value=0;
 consoleCalls=0; nativeMessages=0; customLoading=true;
}
void InGame() { Reset(); czm.active=false; cls.state=ca_active; host.realtime=100; }
void Drop() { CZM_Loading_Dropped(); cls.state=ca_disconnected; CZM_Loading_Disconnected(); }
int main() {
 Reset();
 Host_EndGame(true,"Resource %s is missing\n","models/test.mdl");
 assert(czm_loading_error.value=="Resource models/test.mdl is missing\n");
 Reset();
 CZM_Loading_SetError("Server rejected connection: test");
 Host_EndGame(true,"disconnected from server\n");
 assert(czm_loading_error.value=="Server rejected connection: test");
 Reset();
 CZM_Loading_SetError("#connection_timeout");
 CZM_Loading_SetError("secondary error");
 CL_Disconnect();
 assert(czm_loading_error.value=="#connection_timeout");
 Reset();
 Host_EndGame(true,"disconnected from server\n");
 assert(czm_loading_error.value=="#connect_failed");
 Reset(); czm.cancelled=true;
 CZM_Loading_SetError("error after cancellation"); CL_Disconnect();
 assert(czm_loading_error.value.empty());
 Reset();
 CZM_Loading_SetError("old transient error"); cls.state=ca_active; CZM_End(true);
 assert(czm_loading_error.value.empty());
 Reset(); czm.active=false;
 CZM_Loading_SetError("not a loading session");
 assert(czm.error[0]==0);
 Reset(); czm.seen_loading=false; CL_Disconnect();
 assert(czm_loading_error.value.empty());
 // thrown out of a running game: the menu gets the first reason
 InGame(); CZM_Loading_SetError("Kicked by Console"); Drop();
 assert(czm_loading_error.value=="#dropped Kicked by Console" && czm.game_error[0]==0);
 InGame(); Drop();
 assert(czm_loading_error.value=="#dropped #connection_lost");
 InGame(); CZM_Loading_SetError("#connection_timeout"); CZM_Loading_SetError("later error");
 cls.state=ca_disconnected; CZM_Loading_Disconnected();
 assert(czm_loading_error.value=="#dropped #connection_timeout");
 // the player left by himself, or an old reason: nothing to show
 InGame(); cls.state=ca_disconnected; CZM_Loading_Disconnected();
 assert(czm_loading_error.value.empty());
 InGame(); CZM_Loading_SetError("old reason"); host.realtime+=60; cls.state=ca_disconnected; CZM_Loading_Disconnected();
 assert(czm_loading_error.value.empty() && czm.game_error[0]==0);
 // a drop while loading keeps the loading screen's own reason
 Reset(); CZM_Loading_Dropped(); assert(czm.error[0]==0);
 CZM_Loading_Disconnected();
 assert(czm_loading_error.value=="#connect_failed");
 // A saved/server-set developer cvar must not open a console with no usable controls.
 InGame(); host_developer.value=2;
 Host_Error("Bad server resource: %s", "test.mdl");
 assert(czm_loading_error.value=="#dropped Bad server resource: test.mdl");
 assert(consoleCalls==0 && nativeMessages==0);
 Reset(); host_developer.value=1;
 Host_Error("Protocol error while joining");
 assert(czm_loading_error.value=="Protocol error while joining");
 assert(consoleCalls==0 && nativeMessages==0);
 // Disabling our loading UI keeps the upstream developer console available.
 InGame(); customLoading=false; host_developer.value=1;
 Host_Error("Debug error"); assert(consoleCalls==1 && nativeMessages==0);
 puts("LOADING_ERRORS_OK");
}
'''


class ConsoleBackgroundTests(unittest.TestCase):
    def test_disconnect_returns_to_our_menu_even_with_a_saved_developer_cvar(self):
        source = (ROOT / "3rdparty/xash3d-fwgs/engine/client/cl_main.c").read_text()
        start = source.index("void CL_Disconnect( void )")
        end = source.index("\nvoid CL_Disconnect_f", start)
        program = r'''
#include <cassert>
#include <cstring>
enum { ca_disconnected, ca_active, key_menu, key_game, FRAGMENT_MAX_SIZE=1024, PROTO_CURRENT=49 };
struct { int state,key_dest,connect_time,max_fragment_size,netchan,connect_retry,signon,net_protocol;
 bool changedemo,set_lastdemo; char serveradr[16],bandwidth_test[16]; } cls;
struct { float value; } host_developer;
bool customLoading=true; int menuCalls=0,disconnectCalls=0;
bool CZM_Loading_Enabled() { return customLoading; }
void Voice_Disconnect() {} void CL_Stop_f() {} void CL_SendDisconnectMessage(int) {}
void SteamBroker_TerminateGameConnection() {} void CL_ClearState() {}
void S_StopBackgroundTrack() {} void SCR_EndLoadingPlaque() {} void Netchan_Clear(int *) {}
void IN_LockInputDevices(bool) {} void CZM_Loading_Disconnected() { disconnectCalls++; }
void UI_SetActiveMenu(bool active) { assert(active); menuCalls++; cls.key_dest=key_menu; }
'''
        program += source[start:end]
        program += r'''
void Reset(int developer,bool custom) {
 memset(&cls,0,sizeof(cls));cls.state=ca_active;cls.key_dest=key_game;
 host_developer.value=developer;customLoading=custom;menuCalls=disconnectCalls=0;
}
int main() {
 for(int developer=0;developer<=2;developer++) {
  Reset(developer,true);CL_Disconnect();
  assert(cls.state==ca_disconnected && cls.key_dest==key_menu && menuCalls==1 && disconnectCalls==1);
 }
 Reset(2,false);CL_Disconnect();assert(menuCalls==0 && disconnectCalls==1);
 Reset(0,false);CL_Disconnect();assert(menuCalls==1);
 Reset(2,true);cls.key_dest=key_menu;CL_Disconnect();assert(menuCalls==0);
 Reset(2,true);cls.state=ca_disconnected;CL_Disconnect();assert(menuCalls==0 && disconnectCalls==0);
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "disconnect.cpp").write_text(program)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", str(path / "disconnect.cpp"), "-o", str(path / "disconnect")], check=True)
            subprocess.run([str(path / "disconnect")], check=True)

    def test_missing_textures_use_our_second_background_or_a_neutral_fallback(self):
        source = (ROOT / "3rdparty/xash3d-fwgs/engine/client/console.c").read_text()
        signature = "static int Con_LoadCzmBackground("
        start = source.index(signature)
        opening = source.index("{", start)
        end, depth = opening + 1, 1
        while depth:
            depth += (source[end] == "{") - (source[end] == "}")
            end += 1
        program = r'''
#include <cassert>
#include <cstring>
#include <cstddef>
#define ARRAYSIZE(a) (int)(sizeof(a)/sizeof(a[0]))
#define CZM_CONBACK "gfx/czm/loading_3.png"
enum { REF_DEFAULT_TEXTURE=1, REF_GRAY_TEXTURE=2 };
bool con_czm_background;
int mode=0, calls=0;
bool Exists(const char *,bool) { return mode!=3; }
int Texture(const char *path,void *,int,int) {
 assert(!strcmp(path,CZM_CONBACK)||!strcmp(path,"gfx/czm/menu_bg.png"));
 calls++;
 if(!strcmp(path,CZM_CONBACK))return mode==0?7:REF_DEFAULT_TEXTURE;
 return mode==1?8:0;
}
int R_GetBuiltinTexture(int texture) { return texture; }
struct { bool (*FileExists)(const char *,bool); } g_fsapi={Exists};
struct { struct { int (*GL_LoadTexture)(const char *,void *,int,int); } dllFuncs; } ref={{Texture}};
'''
        program += source[start:end]
        program += r'''
int main() {
 assert(Con_LoadCzmBackground(0)==7 && con_czm_background && calls==1);
 mode=1;calls=0; assert(Con_LoadCzmBackground(0)==8 && con_czm_background && calls==2);
 mode=2;calls=0; assert(Con_LoadCzmBackground(0)==REF_GRAY_TEXTURE && !con_czm_background && calls==2);
 mode=3;calls=0; assert(Con_LoadCzmBackground(0)==REF_GRAY_TEXTURE && !con_czm_background && calls==0);
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "test.cpp").write_text(program)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", str(path / "test.cpp"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
