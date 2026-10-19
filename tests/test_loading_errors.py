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
        source += "void CL_Disconnect() { cls.state = ca_disconnected; CZM_End(false); }\n"
        source += function(host, "void Host_EndGame(") + "\n"
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
#define MAX_SYSPATH 1024
#define Q_vsnprintf vsnprintf
#define Q_strcmp strcmp
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
#define COM_StringEmpty(s) (!(s)[0])
enum { ca_disconnected, ca_active, key_menu, CZM_STAGE_NONE };
struct { bool active, forced, cancelled, seen_loading, reopen_menu; char error[256], game_error[256]; double game_error_time; } czm;
struct { int state, key_dest; } cls;
struct { double realtime; } host;
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
'''

SCENARIO = r'''
void Reset() {
 memset(&czm,0,sizeof(czm)); czm.active=true; czm.seen_loading=true;
 cls.state=ca_disconnected; cls.key_dest=key_menu; czm_loading_error.value.clear();
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
 puts("LOADING_ERRORS_OK");
}
'''


if __name__ == "__main__":
    unittest.main()
