"""Actual policy state machine and the engine's common packet guard."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]


class ServerPolicyTests(unittest.TestCase):
    def test_async_freshness_restriction_lift_failure_and_endpoints(self):
        jar = Path(os.environ.get("CZM_JSON_JAR", "/missing"))
        if not shutil.which("javac") or not jar.is_file(): self.skipTest("requires javac and JSON jar")
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run(["javac", "--release", "11", "-cp", str(jar), "-d", temp,
                str(ROOT/"android/app/src/main/java/ru/kurostreet/counterzombiemobile/ServerPolicy.java"),
                str(ROOT/"android/app/src/main/java/ru/kurostreet/counterzombiemobile/ServerOwners.java"),
                str(ROOT/"tests/ServerOwnersTest.java"),
                str(ROOT/"tests/ServerPolicyTest.java")], check=True)
            result = subprocess.run(["java", "-cp", temp+os.pathsep+str(jar),
                "ru.kurostreet.counterzombiemobile.ServerPolicyTest"], check=True, capture_output=True, text=True)
            self.assertIn("SERVER_POLICY_OK", result.stdout)
            result = subprocess.run(["java", "-cp", temp+os.pathsep+str(jar),
                "ru.kurostreet.counterzombiemobile.ServerOwnersTest"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SERVER_OWNERS_OK", result.stdout)

    def test_common_guard_waits_without_sending_and_explains_denials(self):
        source = (ROOT/"3rdparty/xash3d-fwgs/engine/client/cl_main.c").read_text()
        helper = function(source, "static qboolean CZM_ServerPolicyAllowed(")
        harness = r'''
#include <cassert>
#include <cstring>
typedef bool qboolean;struct netadr_t{int local;};
static int state,disconnected,opened;static const char*error;
enum{ca_connected=1};struct{int state;bool demoplayback;struct{netadr_t remote_address;}netchan;}cls;
struct{double realtime;}host;
bool NET_IsLocalAddress(netadr_t a){return a.local;}
const char*NET_AdrToString(netadr_t){return "203.0.113.5:27015";}
int CZM_ServerPolicyCall(const char*){return state;}
void CZM_Loading_SetError(const char*s){error=s;}void CL_Disconnect(){disconnected++;}
void Cvar_Set(const char*,const char*s){error=s;}void UI_SetActiveMenu(bool){opened++;}
'''
        scenarios = r'''
int main(){netadr_t a={0};state=0;assert(!CZM_ServerPolicyAllowed(a));assert(!disconnected&&!opened);
state=1;assert(CZM_ServerPolicyAllowed(a));state=2;assert(!CZM_ServerPolicyAllowed(a));
assert(disconnected==1&&opened==1&&!strcmp(error,"#czm_server_blocked"));
state=-1;assert(!CZM_ServerPolicyAllowed(a));assert(disconnected==2&&!strcmp(error,"#czm_server_policy"));
state=3;assert(!CZM_ServerPolicyAllowed(a));assert(disconnected==3&&!strcmp(error,"#czm_server_hidden"));
a.local=1;assert(CZM_ServerPolicyAllowed(a));assert(disconnected==3);
cls.state=ca_connected;cls.netchan.remote_address.local=0;host.realtime=100;state=-1;CZM_ServerPolicyFrame();assert(disconnected==3);
host.realtime=101;state=0;CZM_ServerPolicyFrame();assert(disconnected==3);
host.realtime=102;state=3;CZM_ServerPolicyFrame();assert(disconnected==3);
host.realtime=103;state=2;CZM_ServerPolicyFrame();assert(disconnected==4&&!strcmp(error,"#czm_server_blocked"));
cls.demoplayback=true;host.realtime=104;CZM_ServerPolicyFrame();assert(disconnected==4);}
'''
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/"test.cpp").write_text(harness+helper+function(source,"static void CZM_ServerPolicyFrame(")+scenarios)
            subprocess.run(["g++","-std=c++11",str(p/"test.cpp"),"-o",str(p/"test")],check=True)
            subprocess.run([str(p/"test")],check=True)
        # Both protocols and all UI/console entry points converge before outbound packets.
        for signature in ("void CL_SendGoldSrcConnectPacket(","static void CL_SendConnectPacket(","static void CL_CheckForResend("):
            body=function(source,signature)
            self.assertIn("CZM_ServerPolicyAllowed( adr )",body)
        body=function(source,"static void CL_CheckForResend(")
        self.assertLess(body.index("CZM_ServerPolicyAllowed( adr )"),body.index("cls.connect_retry++"))
        for signature in ("static void CL_Connect_f(","static void CL_Retry_f(","static void CL_Reconnect_f("):
            self.assertIn("CZM_ServerPolicyCall( NULL )",function(source,signature))


if __name__ == "__main__": unittest.main()
