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
    def test_finished_in_match_indicator_expires_and_new_download_restarts_it(self):
        loading = (ENGINE / "czm_loading.c").read_text()
        self.assertIn("CZM_DownloadProgress();", function(loading, "void CZM_Loading_Frame("))
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
enum { ca_disconnected, ca_validate, ca_active };
struct { bool active; } czm;
struct { int state; } cls;
struct { int downloadcount; } host;
typedef struct { float value; } cvar_t;
cvar_t scr_download, czm_download_files;
static double clock_now;
static double Platform_DoubleTime(void) { return clock_now; }
static void CZM_SetValue(cvar_t *v, float value) { v->value = value; }
static void Cvar_SetValue(const char *name, float value) { assert(!strcmp(name,"scr_download")); scr_download.value = value; }
''' + function(loading, "static void CZM_DownloadProgress(") + r'''
static void Tick(double now) { clock_now = now; CZM_DownloadProgress(); }
int main(void) {
 cls.state=ca_active; scr_download.value=-1; Tick(0); assert(czm_download_files.value==0);
 host.downloadcount=1; scr_download.value=45; Tick(1); Tick(20);
 assert(scr_download.value==45 && czm_download_files.value==1);
 // Completion in a match: leave 100% briefly, then clear the source cvar, not just the drawing.
 host.downloadcount=0; scr_download.value=100; Tick(21); Tick(22.999);
 assert(scr_download.value==100); Tick(23); assert(scr_download.value==-1); Tick(30); assert(scr_download.value==-1);
 // A full current file is not the end of a queue with more files.
 host.downloadcount=2; scr_download.value=100; Tick(40); Tick(100);
 assert(scr_download.value==100 && czm_download_files.value==2);
 host.downloadcount=0; Tick(101); Tick(102);
 // A fresh transfer cancels the old completion timer.
 host.downloadcount=1; scr_download.value=25; Tick(102.5);
 host.downloadcount=0; scr_download.value=100; Tick(103); Tick(104.9);
 assert(scr_download.value==100); Tick(105); assert(scr_download.value==-1);
 // Never retire progress on the connection/loading screen.
 czm.active=true; scr_download.value=100; Tick(110); Tick(150); assert(scr_download.value==100);
 czm.active=false; cls.state=ca_validate; Tick(151); Tick(190); assert(scr_download.value==100);
 cls.state=ca_active; Tick(191); Tick(193); assert(scr_download.value==-1);
 // The painter rounds 99.5 and above to 100%.
 scr_download.value=99.6f; Tick(200); Tick(202); assert(scr_download.value==-1);
 scr_download.value=99.4f; Tick(210); Tick(220); assert(scr_download.value==99.4f);
 // Disconnects and backwards time start a fresh grace period.
 scr_download.value=100; Tick(230); cls.state=ca_disconnected; Tick(231);
 cls.state=ca_active; Tick(240); Tick(239); Tick(240.9); assert(scr_download.value==100);
 Tick(241); assert(scr_download.value==-1);
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="czm-download-finish-") as temporary:
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
