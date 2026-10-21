"""Execute the branded notice and real engine cvar queries against saved diagnostic choices."""
from pathlib import Path
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
from test_loading_errors import function
from test_social_menu import STUB, VECTOR, STRING

ROOT = Path(__file__).resolve().parents[1]


class ConnectionNoticeTests(unittest.TestCase):
    def test_recovery_requires_a_click_and_valid_destination_and_keeps_all_controls_reachable(self):
        stub = STUB.replace("unsigned CZM_White();", "unsigned CZM_White(int=255);")
        stub = stub.replace("static double DoubleTime();", "static double DoubleTime();static void ClientCmd(bool,const char*);static void ClientCmdF(bool,const char*,...);")
        stub += '\nconst char *CZM_T(const char *);bool CZM_OnlinePlayAllowed();\n'
        stub += 'int CZM_DiagnosticsMode();void CZM_SetDiagnosticsMode(int);bool CZM_DiagnosticsRequired(const char*);\n'
        stub += 'void CZM_ShowNotice(const char*,const char*,const char*="",bool=false);void CZM_ShowMessage(const char*);\n'
        # Separate the default argument from the pointer token for C++ parsing.
        stub = stub.replace('const char*=""', 'const char* = ""')
        stub = stub.replace('struct Cursor{int cursorY;}', 'struct Cursor{int cursorY;struct{bool IsActive(){return true;}}menu;}')
        upstream_header = ROOT / "3rdparty/mainui_cpp/BaseMenu.h"
        if not upstream_header.exists():
            upstream_header = ROOT.parent / "czm/3rdparty/mainui_cpp/BaseMenu.h"
        header = upstream_header.read_text()
        stub += '\nclass CMenuEntry{public:CMenuEntry(const char*,void(*precache)(),void(*)(),void(*)()){precache();}};\n'
        stub += '#undef ADD_MENU3\n' + header[header.index('#define ADD_MENU4('):header.index('#define ADD_COMMAND(')]
        source = (ROOT / "czm/menu/CzmNotice.cpp").read_text()
        source = re.sub(r'^#include .*\n', '', source, flags=re.M).replace('private:', 'public:')
        strings = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
        strings = strings[strings.index('s_strings[] ='):]
        strings = strings[strings.index('{'):strings.index('\n};')+3]
        harness = r'''
#include "stub.h"
#include <map>
#include <cstdarg>
#include <cassert>
#include <fstream>
int ScreenWidth=1536,ScreenHeight=716,cursorX,cursorY;Cursor uiStatic;Stack stack;
std::map<std::string,std::string> vars;std::vector<std::string> commands;
bool allowPlay=true,russian=true;
std::ofstream trace;
const char *EngFuncs::GetCvarString(const char *key){return vars[key].c_str();}
float EngFuncs::GetCvarFloat(const char *key){return atof(GetCvarString(key));}
void EngFuncs::CvarSetString(const char *key,const char *value){vars[key]=value;}
void EngFuncs::CvarSetValue(const char *key,float value){vars[key]=std::to_string(value);}
void EngFuncs::ClientCmd(bool,const char *command){commands.push_back(command);}
void EngFuncs::ClientCmdF(bool,const char *format,...){char text[256];va_list a;va_start(a,format);vsnprintf(text,sizeof(text),format,a);va_end(a);commands.push_back(text);}
bool CZM_OnlinePlayAllowed(){return allowPlay;}
void CZM_PlayClick(){}
unsigned CZM_White(int a){return PackRGBA(245,247,250,a);}unsigned CZM_Grey(){return PackRGBA(155,163,175,255);}
HFont CZM_Font(int id){return id;}
int CZM_FontHeight(HFont font){return (font==CZMF_PANEL_TITLE?42:font==CZMF_SMALL?17:21)*ScreenHeight/768;}
int CZM_TextWidth(HFont f,const char *s){int n=0;for(;*s;s++)n+=((*s&0xc0)!=0x80);return n*CZM_FontHeight(f)*.58;}
int CZM_WrapText(HFont f,const char *s,int width,int *starts,int max){
 int lines=0,start=0,pos=0,lastSpace=-1;starts[0]=0;
 while(s[pos]&&lines<max){
  if(s[pos]==' '||s[pos]=='\n')lastSpace=pos;
  int next=pos+1;while(s[next]&&((unsigned char)s[next]&0xc0)==0x80)next++;
  std::string segment(s+start,next-start);
  if(s[pos]=='\n'||CZM_TextWidth(f,segment.c_str())>width){
   int end=s[pos]=='\n'?pos+1:lastSpace>=start?lastSpace+1:pos;
   if(end<=start)end=next;
   starts[++lines]=end;start=pos=end;lastSpace=-1;
  }else pos=next;
 }
 if(start<pos&&lines<max)starts[++lines]=pos;
 return lines;
}
void CZM_WrapLine(const char *s,const int *starts,int line,char *out,size_t size){int n=std::min((int)size-1,starts[line+1]-starts[line]);memcpy(out,s+starts[line],n);while(n&&(out[n-1]=='\n'||out[n-1]==' '))n--;out[n]=0;}
void UI_FillRect(int x,int y,int w,int h,unsigned color){if(trace)trace<<"rect\t"<<x<<"\t"<<y<<"\t"<<w<<"\t"<<h<<"\t"<<color<<"\n";}
void CZM_DrawText(HFont f,int x,int y,int w,const char *s,unsigned color,unsigned){if(trace)trace<<"text\t"<<x<<"\t"<<y<<"\t"<<w<<"\t"<<CZM_FontHeight(f)<<"\t"<<color<<"\t"<<s<<"\n";}
void CZM_DrawPanel(const CzmRect &r){UI_FillRect(r.x,r.y,r.w,r.h,PackRGBA(15,18,24,255));}
void CZM_DrawImage(const char*,int x,int y,int w,int h,unsigned color){UI_FillRect(x,y,w,h,color);}
void CZM_DrawButton(const char *image,const CzmRect&r,const char *label,unsigned color,bool,int font){
 UI_FillRect(r.x,r.y,r.w,r.h, strstr(image,"primary")?PackRGBA(230,38,38,255):PackRGBA(37,42,51,255));
 int width=CZM_TextWidth(CZM_Font(font),label);assert(width<r.w);
 CZM_DrawText(CZM_Font(font),r.x+(r.w-width)/2,r.y+(r.h-CZM_FontHeight(font))/2,r.w,label,color,0);
}
'''
        harness += 'struct {const char *key,*ru,*en;} strings[]='+strings+'\n'
        harness += 'const char*CZM_T(const char *key){for(auto &s:strings)if(!strcmp(s.key,key))return russian?s.ru:s.en;return key;}\n'
        harness += source
        menu = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
        for signature in ["static void CZM_CleanReason(", "static bool CZM_Contains(", "static void CZM_ShowPendingError("]:
            harness += function(menu, signature) + "\n"
        harness += r'''
void Click(const CzmRect &r){cursorX=r.x+r.w/2;cursorY=uiStatic.cursorY=r.y+r.h/2;auto&w=*menu_czmnotice;w.KeyDown(1);w.KeyUp(1);}
int main(int argc,char **argv){
 for(const char*s:{"Kicked: Напишите developer 0 в консоли", "DEVELOPER = \"0\"", "developer\t0", "developer '0'"})assert(CZM_DiagnosticsRequired(s));
 for(const char*s:{"developer 1","developer 10","developer 0.5","developer 0x1","mydeveloper 0","developer 00","developer 0_debug","developer","Server full","Banned"})assert(!CZM_DiagnosticsRequired(s));
 assert(!CZM_DiagnosticsRequired(nullptr));
 vars["czm_diagnostics"]="1";vars["developer"]="1";vars["czm_retry_address"]="203.0.113.17:27015";vars["czm_retry_protocol"]="gs";
 auto&w=*menu_czmnotice;CZM_ShowNotice(CZM_T("diag_server_title"),CZM_T("diag_server_text"),"Kicked: developer 0",true);
 assert(commands.empty()&&CZM_DiagnosticsMode()==1);w.Draw();
 vars["czm_loading_error"]="#dropped Kicked: Напишите developer 0 в консоли";CZM_ShowPendingError();assert(w.CanRetry()&&vars["czm_loading_error"].empty());
 for(const char*reason:{"#dropped Banned: developer 0", "#connection_timeout", "#dropped Kicked: server maintenance"}){
  vars["czm_loading_error"]=reason;CZM_ShowPendingError();assert(!w.CanRetry()&&CZM_DiagnosticsMode()==1&&commands.empty());
 }
 vars["czm_loading_error"]="#dropped Banned: test reason";CZM_ShowPendingError();assert(strstr(w.m_text,"test reason"));
 // Returning to the main menu during disconnect must not bury the pending notice.
 stack.current=nullptr;CZM_ShowNotice(CZM_T("diag_server_title"),CZM_T("diag_server_text"),"Kicked: developer 0",true);assert(stack.current==&w);
 // A later attempted connection cannot change the address captured for this notice.
 vars["czm_retry_address"]="198.51.100.50:27015";Click(w.m_retry);
 assert(CZM_DiagnosticsMode()==0&&vars["developer"]=="0.000000"&&!w.m_open);
 assert(commands.size()==2&&commands[0]=="host_writeconfig\n"&&commands[1]=="connect \"203.0.113.17:27015\" gs\n");
 w.Activate(w.RETRY);assert(commands.size()==2);
 for(const char*bad:{"", "example.org:27015", "203.0.113.7:27015\";quit", "203.0.113.7:27015\nquit"}){
  vars["czm_retry_address"]=bad;CZM_ShowNotice("Error","Message","Reason",true);w.Draw();assert(!w.CanRetry());w.Activate(w.RETRY);assert(commands.size()==2);w.Hide();
 }
 vars["czm_retry_address"]="[2001:db8::1]:27015";vars["czm_retry_protocol"]="49";
 CZM_ShowNotice("Error","Message","Reason",true);w.Draw();assert(w.CanRetry());
 allowPlay=false;w.Activate(w.RETRY);assert(commands.size()==2);allowPlay=true;
 Click(w.m_close);assert(commands.size()==2);
 CZM_ShowMessage("Server ban: do not reconnect");w.Draw();assert(!w.CanRetry());w.KeyDown(27);assert(!w.m_open);
 for(auto resolution:{std::pair<int,int>{1536,716},{960,540},{1024,768},{1280,720},{640,360}})for(bool ru:{false,true}){
  ScreenWidth=resolution.first;ScreenHeight=resolution.second;russian=ru;
  CZM_ShowNotice(CZM_T("diag_server_title"),CZM_T("diag_server_text"),"Kicked: Напишите developer 0 в консоли, чтобы играть на сервере",true);w.Draw();
  for(bool expanded:{false,true}){
   w.m_expanded=expanded;w.Draw();assert(w.m_panel.x>=0&&w.m_panel.y>0&&w.m_panel.y+w.m_panel.h<ScreenHeight);
   assert(w.m_clip.h>0&&w.m_clip.y+w.m_clip.h<=w.m_detail.y);
   for(auto*r:{&w.m_close,&w.m_retry,&w.m_detail}){assert(r->h>0&&r->x>=w.m_panel.x&&r->x+r->w<=w.m_panel.x+w.m_panel.w&&r->y+r->h<=w.m_panel.y+w.m_panel.h);}
   assert(w.m_detail.y+w.m_detail.h<w.m_retry.y&&w.m_retry.y+w.m_retry.h<w.m_close.y);
  }
  std::string longMessage;for(int i=0;i<30;i++)longMessage+="Server connection details\n";
  CZM_ShowMessage(longMessage.c_str());w.Draw();assert(w.m_maxScroll>0&&w.m_close.h>0);
  w.KeyDown(K_MWHEELDOWN);assert(w.m_scroll>0);w.Hide();
 }
 if(argc>1){ScreenWidth=1536;ScreenHeight=716;russian=true;vars["czm_diagnostics"]="1";trace.open(argv[1]);
  CZM_ShowNotice(CZM_T("diag_server_title"),CZM_T("diag_server_text"),"Kicked: Напишите developer 0 в консоли, чтобы играть на сервере",true);w.Draw();trace.close();}
 puts("BRANDED_CONNECTION_NOTICE_OK");
}
'''
        with tempfile.TemporaryDirectory(prefix="czm-notice-") as temporary:
            folder = Path(temporary)
            for name, content in [("stub.h", stub), ("utlvector.h", VECTOR), ("utlstring.h", STRING), ("notice.cpp", harness)]:
                (folder / name).write_text(content)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I"+temporary,
                            str(folder / "notice.cpp"), "-o", str(folder / "notice")], check=True)
            command = [str(folder / "notice")]
            if os.environ.get("CZM_NOTICE_TRACE"):
                command.append(os.environ["CZM_NOTICE_TRACE"])
            subprocess.run(command, check=True)

    def test_engine_preserves_saved_mode_through_legacy_configs_connect_and_reconnect(self):
        engine = ROOT / "3rdparty/xash3d-fwgs/engine"
        main = (engine / "client/cl_main.c").read_text()
        parse = (engine / "client/parse/cl_parse.c").read_text()
        host = (engine / "common/host.c").read_text()
        startup = host[host.index('Cbuf_ExecStuffCmds();\t// execute stuffcmds (commandline)'):]
        self.assertLess(startup.index("CZM_Diagnostics_Apply();"), startup.index("SCR_CheckStartupVids();"))
        program = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
typedef bool qboolean;typedef int connprotocol_t;
enum {ca_connected,PROTO_GOLDSRC,PROTO_CURRENT,FCVAR_PRIVILEGED=16,FCVAR_SERVER=32,FCVAR_PROTECTED=64,
 clc_goldsrc_requestcvarvalue2=100,clc_requestcvarvalue2,clc_goldsrc_requestcvarvalue,clc_requestcvarvalue};
struct netadr_t{};struct sizebuf_t{};
struct convar_t{float value;const char*string;int flags;} host_developer,choice;
struct Channel{sizebuf_t message;};
struct{char userinfo[128];Channel netchan;int net_protocol,demonum,movienum,state,signon,lastoutgoingcommand;double nextcmdtime;}cls;
struct{int validsequence,delta_sequence,last_command_ack;}cl;struct{double realtime;}host;
bool enabled=true;int expected=1;char developerText[32];std::vector<std::string> response;
std::string retryAddress,retryProtocol;
template<class T>T bound(T a,T b,T c){return b<a?a:b>c?c:b;}
bool CZM_Loading_Enabled(){return enabled;}
convar_t*Cvar_FindVar(const char*n){return !strcmp(n,"czm_diagnostics")?&choice:!strcmp(n,"developer")?&host_developer:nullptr;}
void Cvar_DirectSetValue(convar_t*v,float n){v->value=n;snprintf(developerText,sizeof(developerText),"%g",n);v->string=developerText;}
void Cvar_Set(const char*n,const char*v){if(!strcmp(n,"czm_retry_address"))retryAddress=v;else if(!strcmp(n,"czm_retry_protocol"))retryProtocol=v;else assert(false);}
const char*NET_AdrToString(netadr_t){return "203.0.113.17:27015";}
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
#define Q_stricmp strcasecmp
int MSG_ReadLong(sizebuf_t*){return 123;}const char*MSG_ReadString(sizebuf_t*){return "developer";}
void MSG_BeginClientCmd(sizebuf_t*,int){response.clear();}void MSG_WriteLong(sizebuf_t*,int n){assert(n==123);}
void MSG_WriteString(sizebuf_t*,const char*s){response.push_back(s);}
void CL_SetupNetchanForProtocol(int){}void Netchan_Clear(Channel*){}void MSG_Clear(sizebuf_t*){}
void CL_ServerCommand(bool,const char*s){assert(!strcmp(s,"new")&&host_developer.value==expected);}
void CL_StartupDemoHeader(){}
'''
        for signature in ["void CZM_Diagnostics_Apply(", "static const char *CZM_ConnectUserinfo(", "static void CL_Reconnect("]:
            program += function(main, signature) + "\n"
        program += function(parse, "static void CL_ParseCvarValue(") + "\n"
        program += r'''
void Query(int wanted){sizebuf_t msg;for(int proto:{PROTO_GOLDSRC,PROTO_CURRENT})for(bool ext:{false,true}){
 CL_ParseCvarValue(&msg,ext,proto);assert(response.size()==(ext?2:1));if(ext)assert(response[0]=="developer");assert(response.back()==std::to_string(wanted));}}
int main(){
 strcpy(cls.userinfo,"\\name\\Tester");
 for(int saved:{0,1,2}){
  choice.value=saved;expected=saved;
  // Startup: config.cfg restores our choice; legacy userconfig.cfg enables debug.
  Cvar_DirectSetValue(&host_developer,1);CZM_Diagnostics_Apply();assert(host_developer.value==saved);Query(saved);
  for(int protocol:{PROTO_GOLDSRC,PROTO_CURRENT}){
   cls.net_protocol=protocol;Cvar_DirectSetValue(&host_developer,2);char wire[128];
   CZM_ConnectUserinfo(netadr_t{},wire,sizeof(wire));assert(!strcmp(wire,cls.userinfo));Query(saved);
   assert(retryAddress=="203.0.113.17:27015"&&retryProtocol==(protocol==PROTO_GOLDSRC?"gs":"49"));
   for(bool setup:{false,true}){Cvar_DirectSetValue(&host_developer,1);CL_Reconnect(setup);Query(saved);}
  }
 }
 enabled=false;choice.value=0;Cvar_DirectSetValue(&host_developer,2);CZM_Diagnostics_Apply();Query(2);
 // Cvar responses remain truthful even after an explicit later console change.
 enabled=true;Cvar_DirectSetValue(&host_developer,1);Query(1);
 puts("SAVED_DIAGNOSTICS_AND_SERVER_QUERIES_OK");
}
'''
        with tempfile.TemporaryDirectory(prefix="czm-diagnostics-") as temporary:
            folder = Path(temporary)
            (folder / "engine.cpp").write_text(program)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                            str(folder / "engine.cpp"), "-o", str(folder / "engine")], check=True)
            subprocess.run([str(folder / "engine")], check=True)

    def test_upstream_message_hook_preserves_input_recovery_and_replaces_only_generic_alert(self):
        spec = importlib.util.spec_from_file_location("brand", ROOT / "scripts/brand_mainui.py")
        brand = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(brand)
        upstream = ROOT / "3rdparty/mainui_cpp/controls/YesNoMessageBox.cpp"
        if not upstream.exists():
            upstream = ROOT.parent / "czm/3rdparty/mainui_cpp/controls/YesNoMessageBox.cpp"
        transformed = brand.brand_message_box(upstream.read_text())
        self.assertIn("msgBoxInputDev.onNegative = UI_InputDevices_Menu", transformed)
        self.assertEqual(transformed.count("CZM_ShowMessage( msg );"), 1)
        self.assertNotIn("\tmsgBox.Show();", transformed)


if __name__ == "__main__":
    unittest.main()
