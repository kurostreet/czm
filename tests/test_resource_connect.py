"""Exercise asynchronous joins: consent, cancellation, replacement and policy gates."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ResourceConnectTest(unittest.TestCase):
    def test_pending_joins_never_dispatch_early_or_after_cancellation(self):
        source = (ROOT / 'czm/menu/CzmOnline.cpp').read_text()
        fragment = source[source.index('// A new click replaces'):source.index('// ---------------------------------------------------------------- the player panel')]
        harness = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <map>
#include <vector>
#include <cstdio>
#include <cstdarg>
using CMenuBaseWindow=int;
struct {struct {int *current=nullptr;int *Current(){return current;}}menu;}uiStatic;
static std::map<std::string,std::string> vars;
static std::vector<std::string> calls;
static int state=2,shown=0,notice=0,cancelled=0,refreshes=0;
static bool allowed=true,blocked=false;
void Q_strncpy(char*out,const char*in,size_t n){snprintf(out,n,"%s",in);}
struct EngFuncs {
 static const char*GetCvarString(const char*k){return vars[k].c_str();}
 static void CvarSetString(const char*k,const char*v){vars[k]=v;}
 static void ClientCmdF(bool,const char*fmt,...){char b[512];va_list a;va_start(a,fmt);vsnprintf(b,sizeof b,fmt,a);va_end(a);calls.push_back(b);}
};
void CZM_ServerResourcesRefresh(const char*){refreshes++;state=2;}
int CZM_ServerResourcesPrepare(const char*){return state;}
void CZM_ServerResourcesShow(const char*,bool){shown++;}
void CZM_ServerResourcesCancelConnection(){cancelled++;}
bool CZM_IsRussian(){return true;}
void CZM_ShowNotice(const char*,const char*){notice++;}
bool CZM_OnlinePlayAllowed(){return allowed;}
bool CZM_ServerBlocked(const char*){return blocked;}
void CZM_PrepareConnect(const char*a){calls.push_back(std::string("ticket:")+a);}
'''
        scenario = r'''
int main(){
 int menu1,menu2;uiStatic.menu.current=&menu1;
 ResourceJoinFrame();assert(calls.empty());
 CZM_ConnectWithResources("1.2.3.4:27015;quit","gs");assert(refreshes==0);
 vars["password"]="original";vars["czm_connect_name"]="Survival";
 CZM_ConnectWithResources("1.2.3.4:27015","gs");assert(refreshes==1);
 ResourceJoinFrame();assert(calls.empty());
 state=3;ResourceJoinFrame();ResourceJoinFrame();assert(shown==1&&calls.empty());
 state=2;ResourceJoinFrame();assert(calls.empty());
 vars["password"]="other";state=1;ResourceJoinFrame();assert(calls.size()==2);
 assert(calls[0]=="ticket:1.2.3.4:27015");assert(calls[1]=="connect \"1.2.3.4:27015\" gs\n");
 assert(vars["password"]=="original"&&vars["czm_connect_name"]=="Survival");
 ResourceJoinFrame();assert(calls.size()==2);
 CZM_ConnectWithResources("1.2.3.4:27015","gs");
 CZM_ConnectWithResources("5.6.7.8:27016","49");state=0;ResourceJoinFrame();
 assert(calls.back()=="connect \"5.6.7.8:27016\" 49\n");
 size_t count=calls.size();
 CZM_ConnectWithResources("5.6.7.8:27016","gs");state=-2;ResourceJoinFrame();assert(calls.size()==count&&notice==0&&cancelled==1);
 CZM_ConnectWithResources("5.6.7.8:27016","gs");state=-1;ResourceJoinFrame();assert(notice==1&&calls.size()==count);
 CZM_ConnectWithResources("5.6.7.8:27016","gs");state=1;allowed=false;ResourceJoinFrame();assert(calls.size()==count);allowed=true;
 CZM_ConnectWithResources("5.6.7.8:27016","gs");state=1;uiStatic.menu.current=&menu2;ResourceJoinFrame();assert(calls.size()==count);
 CZM_ConnectWithResources("5.6.7.8:27016","gs");CZM_CancelResourceJoin();state=1;ResourceJoinFrame();assert(calls.size()==count);
 CZM_ConnectWithResources("[2001:db8::1]:27015","gs");state=0;ResourceJoinFrame();assert(calls.back()=="connect \"[2001:db8::1]:27015\" gs\n");
}
'''
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'join.cpp'
            path.write_text(harness + fragment + scenario)
            binary = Path(d) / 'join'
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', str(path), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

if __name__ == '__main__':
    unittest.main()
