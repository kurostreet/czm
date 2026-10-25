"""Execute engine background branches: downloads continue, GL preparation waits."""
from pathlib import Path
import subprocess
import re
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs/engine/client"


class BackgroundDownloadsTests(unittest.TestCase):
    def test_indicator_follows_real_transfers_and_retires_stale_values(self):
        loading = (ENGINE / "czm_loading.c").read_text()
        self.assertIn("CZM_DownloadProgress();", function(loading, "void CZM_Loading_Frame("))
        defines = "\n".join(re.findall(r"^#define CZM_DOWNLOAD_\w+ .+$", loading, re.M))
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef bool qboolean;
enum { ca_disconnected, ca_connecting, ca_connected, ca_validate, ca_active };
#define FRAG_FILE_STREAM 1
struct { bool active; } czm;
struct { int state; struct { void *incomingbufs[2]; } netchan; } cls;
struct { int downloadcount; char downloadfile[64]; } host;
typedef struct { float value; } cvar_t;
cvar_t scr_download, czm_download_files;
static double clock_now; static int files, notes; static char note[256];
static double Platform_DoubleTime(void) { return clock_now; }
static int HTTP_FileDownloads(void) { return files; }
static void CZM_SetValue(cvar_t *v, float value) { v->value = value; }
static void Cvar_SetValue(const char *name, float value) { assert(!strcmp(name,"scr_download")); scr_download.value = value; }
#define Con_Reportf(...) (notes++, snprintf(note, sizeof(note), __VA_ARGS__))
''' + defines + "\n" + function(loading, "static void CZM_DownloadProgress(") + r'''
static void Tick(double now) { clock_now = now; CZM_DownloadProgress(); }
int main(void) {
 static int stream;
 cls.state=ca_active; scr_download.value=-1; Tick(0); assert(czm_download_files.value==0&&notes==0);
 // A file in the HTTP queue keeps the indicator while it moves.
 files=1; host.downloadcount=1; scr_download.value=45; Tick(1); scr_download.value=60; Tick(15); Tick(30);
 assert(scr_download.value==60 && czm_download_files.value==1);
 // Finished: the queue is empty, 100% stays a moment and goes; one line in the log.
 files=0; host.downloadcount=0; scr_download.value=100; Tick(31); Tick(32.4); assert(scr_download.value==100);
 Tick(32.6); assert(scr_download.value==-1&&notes==1&&strstr(note,"no transfer")); Tick(40); assert(notes==1);
 // A spray that never arrives keeps the counter up; the stale value still goes.
 host.downloadcount=2; strcpy(host.downloadfile,"!MD5abc"); scr_download.value=100; Tick(50); Tick(51.6);
 assert(scr_download.value==-1&&czm_download_files.value==0&&notes==2&&strstr(note,"2 files left"));
 // Between two files of a queue the bar does not blink.
 host.downloadcount=3; files=1; scr_download.value=10; Tick(60); files=0; Tick(61); files=1; scr_download.value=20; Tick(61.4);
 files=0; Tick(62); assert(scr_download.value==20); files=1; Tick(62.5); assert(scr_download.value==20);
 // A transfer over the game connection counts as moving too.
 files=0; cls.netchan.incomingbufs[FRAG_FILE_STREAM]=&stream; scr_download.value=30; Tick(70); scr_download.value=31; Tick(80);
 assert(scr_download.value==31);
 // Stopped in place: hidden after a while and kept hidden when the same value comes back.
 Tick(99.9); assert(scr_download.value==31); Tick(100.1); assert(scr_download.value==-1&&strstr(note,"no progress"));
 int was=notes; scr_download.value=31; Tick(101.2); assert(scr_download.value==-1&&notes==was);
 scr_download.value=32; Tick(101.3); assert(scr_download.value==32); // it moved again
 cls.netchan.incomingbufs[FRAG_FILE_STREAM]=0;
 // The loading screen keeps its own progress, and so does the connection.
 czm.active=true; scr_download.value=55; Tick(110); Tick(150); assert(scr_download.value==55);
 czm.active=false; cls.state=ca_validate; Tick(151); Tick(190); assert(scr_download.value==55);
 // In the menu an old value from a match goes as well.
 cls.state=ca_disconnected; Tick(191); Tick(192.6); assert(scr_download.value==-1);
 // Time going backwards starts a fresh grace period.
 cls.state=ca_active; scr_download.value=70; Tick(200); Tick(199); Tick(200.4); Tick(201.8); assert(scr_download.value==70);
 Tick(202); assert(scr_download.value==-1);
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="czm-download-finish-") as temporary:
            folder = Path(temporary)
            (folder / "check.c").write_text(harness)
            exe = folder / "check"
            subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(folder / "check.c"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_server_lists_read_into_memory_never_move_the_download_bar(self):
        http = (ROOT / "3rdparty/xash3d-fwgs/engine/common/http/net_http_xash.c").read_text()
        self.assertRegex(http, r"if\( !curfile->to_memory \)\n\t\t\{\n\t\t\thttp\.progress \+=")
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
typedef bool qboolean;
typedef struct httpfile_s { qboolean to_memory; struct httpfile_s *next; } httpfile_t;
static struct { httpfile_t *first_file; } http;
''' + function(http, "int HTTP_FileDownloads(") + r'''
int main(void) {
 httpfile_t list = { true, NULL }, map = { false, NULL }, sound = { false, NULL };
 assert(HTTP_FileDownloads() == 0);
 http.first_file = &list; assert(HTTP_FileDownloads() == 0);
 list.next = &map; map.next = &sound; assert(HTTP_FileDownloads() == 2);
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="czm-http-files-") as temporary:
            folder = Path(temporary)
            (folder / "check.c").write_text(harness)
            exe = folder / "check"
            subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(folder / "check.c"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_bytes_progress_and_graphics_wait_for_foreground(self):
        source = (ENGINE / "cl_main.c").read_text()
        loading = (ENGINE / "czm_loading.c").read_text()
        precache = function(source, "qboolean CL_PrecacheResources(")
        precache = precache[:precache.index("\t// if we downloaded")] + "return true;\n}\n"
        frame = function(source, "void Host_ClientFrame(")
        frame = frame[:frame.index("\tif( cls.key_dest")] + "rendered++;\n}\n"
        harness = r'''
#include <cassert>
#define __ANDROID__ 1
typedef bool qboolean;
struct resource_t {resource_t *pNext;};
enum {HOST_FRAME,HOST_SLEEP,ca_validate,key_game,event_up};
struct {int status;}host;
struct {bool initialized;int state,key_dest;}cls;
struct {resource_t resourcesneeded;}cl;
struct {bool active,files_ready;}czm;
struct {float value;}czm_loading_stage;
#define CZM_STAGE_DOWNLOAD 3
static bool requested,czm_deferred_precache;static int ready,rendered,acks,packets,retries,slept,registered,cancelled,background;
static bool CZM_AndroidFlag(const char *){return requested;}
static void CZM_AndroidProgress(int status){assert(status==3);ready++;}
static void CZM_Cancel(){cancelled++;}
static void CZM_AndroidBackground(){background++;}
''' + "\n".join(re.findall(r"^#define CZM_(?:CANCEL|BACKGROUND)_[XY][01] .+$", loading, re.M)) + "\n"
        harness += function(loading, "qboolean CZM_Loading_WaitForForeground(") + "\n"
        harness += function(loading, "void CZM_Loading_FilesReady(") + "\n" + precache
        harness += r'''
static bool CZM_Loading_Active(){return czm.active;}
static void CL_SendCommand(){acks++;}
static void CL_ReadPackets(){packets++;}
static void CL_CheckForResend(){retries++;}
static bool CL_RequestMissingResources(){return false;}
static void SCR_UpdateScreen(){}
static void Platform_Sleep(int ms){slept+=ms;}
static void CL_BatchResourceRequest(bool){if(CL_PrecacheResources())registered++;}
''' + frame + function(loading, "qboolean CZM_Loading_TouchEvent(") + r'''
int main(){
 cls.initialized=true;cls.state=ca_validate;cls.key_dest=key_game;czm.active=true;host.status=HOST_SLEEP;
 cl.resourcesneeded.pNext=&cl.resourcesneeded;
 assert(!CL_PrecacheResources()&&czm_deferred_precache&&ready==1);
 Host_ClientFrame();assert(acks==1&&packets==1&&retries==1&&rendered==0&&registered==0);
 host.status=HOST_FRAME;requested=true;assert(!CL_PrecacheResources());Host_ClientFrame();assert(registered==0);
 requested=false;Host_ClientFrame();assert(registered==1&&rendered==2&&!czm_deferred_precache);
 resource_t missing;cl.resourcesneeded.pNext=&missing;host.status=HOST_SLEEP;int was=ready;
 assert(!CL_PrecacheResources()&&ready==was);czm.active=false;Host_ClientFrame();assert(slept==100&&packets==1);
 czm.active=true;czm_loading_stage.value=3;assert(CZM_Loading_TouchEvent(event_up,.88f,.74f)&&background==1&&cancelled==0);
 CZM_Loading_TouchEvent(event_up,.7f,.85f);assert(background==1&&cancelled==0);
 CZM_Loading_TouchEvent(event_up,.88f,.794f);assert(background==1&&cancelled==0);
 CZM_Loading_TouchEvent(event_up,.88f,.85f);assert(cancelled==1&&background==1);
 czm_loading_stage.value=4;CZM_Loading_TouchEvent(event_up,.88f,.74f);assert(background==1&&cancelled==1);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "check.cpp").write_text(harness)
            exe = folder / "check"
            subprocess.run(["g++", "-std=c++11", str(folder / "check.cpp"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    unittest.main()
