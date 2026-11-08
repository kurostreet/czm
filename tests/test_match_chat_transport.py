"""Run the actual match chat wire, lifecycle and filtered SayText history code."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_loading_errors import function
from test_combat_controls import build

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs/engine"
CONSOLE = ENGINE / "client/console.c"


def client_sdk_flags():
    # Use the gameplay target's real include order, not the menu SDK or a mock.
    cmake = (ROOT / "cl_dll/CMakeLists.txt").read_text()
    paths = re.search(r"include_directories\((.*?)\)", cmake, re.S).group(1).split()
    flags = ["-std=c++11", "-fms-extensions", "-DCLIENT_WEAPONS", "-DCLIENT_DLL",
             "-DSTDINT_H=<cstdint>", "-DLINUX", "-D_LINUX", "-Dstricmp=strcasecmp",
             "-D_strnicmp=strncasecmp", "-Dstrnicmp=strncasecmp"]
    return flags + ["-I" + str((ROOT / "cl_dll" / path).resolve()) for path in paths]

ENGINE_STUB = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
#include <vector>
typedef bool qboolean; typedef unsigned char byte;
#define MAX_SYSPATH 1024
enum { FCVAR_ARCHIVE=1,FCVAR_PRIVILEGED=2,FCVAR_READ_ONLY=4,ca_active=5,key_game,key_menu,key_message,HOST_FRAME,HOST_NOFOCUS,HOST_SLEEP,clc_stringcmd,K_ESCAPE,K_BACK_BUTTON,K_ENTER,K_KP_ENTER,K_A_BUTTON };
struct convar_t { const char *name; const char *string; int flags; float value; std::string storage; };
#define CVAR_DEFINE_AUTO(name,value,flags,description) convar_t name={#name,value,flags,0,{}}
#define Q_strlen strlen
#define Q_strcmp strcmp
#define Q_snprintf snprintf
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
#define Q_atoi atoi
struct {int state=ca_active,key_dest=key_game;bool demoplayback=false;struct{int message;}netchan;}cls;
struct {int status=HOST_FRAME;}host;
struct {void *hInstance=(void*)1;}gameui;
struct Field {char buffer[512]={};};
struct {char chat_cmd[32];Field chat;}con;
std::vector<std::string> args, wire;std::string cbuf;
int touchReleases=0,keyReleases=0;bool osKeyboard=false,g_messagemode_privileged=true;
void Cvar_DirectSet(convar_t *v,const char *text){v->storage=text;v->string=v->storage.c_str();v->value=atof(text);}
void Cvar_DirectFullSet(convar_t *v,const char *text,int){Cvar_DirectSet(v,text);}
void Touch_ResetLoadingInput(){touchReleases++;}
void Key_ClearStates(){keyReleases++;}
void Key_EnableTextInput(bool enabled,bool){osKeyboard=enabled;}
void Key_SetKeyDest(int dest){cls.key_dest=dest;osKeyboard=dest==key_message;}
void MSG_BeginClientCmd(int *,int opcode){assert(opcode==clc_stringcmd);}
void MSG_WriteString(int *,const char *text){wire.emplace_back(text);}
int Cmd_Argc(){return args.size();}
const char *Cmd_Argv(int n){return n<(int)args.size()?args[n].c_str():"";}
bool Cmd_CurrentCommandIsPrivileged(){return true;}
void Con_ClearField(Field *f){f->buffer[0]=0;}
void Field_KeyDownEvent(Field *,int){}
void Cbuf_AddText(const char *s){cbuf+=s;}
void Cbuf_AddFilteredText(const char *s){cbuf+=s;}
'''


def engine_source():
    code = CONSOLE.read_text()
    declarations = "\n".join(re.findall(r"^.*CVAR_DEFINE_AUTO\( czm_match_chat[^;]+;", code, re.M))
    globals_ = "\nstatic unsigned int czm_chat_request_serial;\nstatic unsigned int czm_chat_epoch=1;\n"
    names = ["static qboolean Con_CzmValidChat", "static int Con_CzmHexDigit", "static qboolean Con_CzmDecodeChatHex",
             "static void Con_CzmReleaseChatInput", "void Con_CzmMatchChatReset", "static qboolean Con_CzmWriteChat",
             "static qboolean Con_CzmRequestChat", "static void Con_CzmMatchChatSend_f", "static void Con_CzmMatchChatClose_f",
             "static void Con_CzmMatchChatIme_f", "static void Con_CzmMatchChatFrame", "static void Con_MessageMode_f",
             "static void Con_MessageMode2_f", "void Key_Message"]
    return ENGINE_STUB + declarations + globals_ + "\n".join(function(code, name) for name in names)


HISTORY_STUB = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
#include <map>
#include <vector>
#define MAX_CHARS_PER_LINE 1024
#define MAX_PLAYERS 32
#define FCVAR_PRIVILEGED 2
std::map<std::string,std::string> cvars; std::vector<std::string> writes;
struct { void pfnRegisterVariable(const char *n,const char *v,int){cvars.emplace(n,v);}
void Cvar_Set(const char *n,const char *v){cvars[n]=v;writes.push_back(n);}}gEngfuncs;
struct {const char *name;} g_PlayerInfoList[33];
void GetPlayerInfo(int,void*){}float *GetClientColor(int){static float color[]={.6f,.8f,1.f};return color;}
static unsigned int s_czmChatHead,s_czmChatEpoch;
struct CUtlString{std::string value;void operator=(const char *s){value=s?s:"";}
char operator[](int i)const{return value[i];}const char *Get()const{return value.c_str();}int Length()const{return value.size();}
operator const char*()const{return value.c_str();}};
struct BufferReader{const char *p,*end;bool valid=true;BufferReader(const char*,void *b,int n):p((char*)b),end(p+n){}
int ReadByte(){return p<end?(unsigned char)*p++:0;}char *ReadString(){if(p>=end){valid=false;return const_cast<char*>("");}const char *out=p;while(p<end&&*p)p++;if(p<end)p++;return const_cast<char*>(out);}bool Valid(){return valid;}};
bool dead=false;int g_iUser1=0;bool CL_IsDead(){return dead;}
void Localize_Format(char *dst,size_t n,const char *format,const char **args,int count){
 std::string out=format;for(int i=0;i<count;i++){std::string key="%s"+std::to_string(i+1);size_t at;while((at=out.find(key))!=std::string::npos)out.replace(at,key.size(),args[i]);}snprintf(dst,n,"%s",out.c_str());}
struct CHudSayText{int MsgFunc_SayText(const char*,int,void*);void SayTextPrint(const char*,int,int=-1);};
'''


def history_source():
    code = (ROOT / "cl_dll/saytext.cpp").read_text()
    source = HISTORY_STUB + "\n".join(function(code, name) for name in [
        "static void CzmMatchChatRegister", "static void CzmMatchChatReset", "static void CzmMatchChatPublish"])
    table_start = code.index("struct\n{\n\tconst char key[32];")
    table_end = code.index("\n};", table_start) + 3
    source += code[table_start:table_end]
    source += function(code, "int CHudSayText :: MsgFunc_SayText")
    source += "\nvoid CHudSayText::SayTextPrint(const char *s,int n,int client){CzmMatchChatPublish(s,n,client);}\n"
    return source


class MatchChatTransportTests(unittest.TestCase):
    def test_production_client_sources_compile_with_gameplay_sdk_headers(self):
        subprocess.run(["g++", *client_sdk_flags(), "-fsyntax-only",
                        str(ROOT / "cl_dll/saytext.cpp"), str(ROOT / "cl_dll/text_message.cpp")], check=True)

    def test_production_cvar_registration_keeps_engine_privilege_bit(self):
        code = (ROOT / "cl_dll/saytext.cpp").read_text()
        with tempfile.TemporaryDirectory(prefix="czm-client-cvar-sdk-") as folder:
            path = Path(folder)
            (path / "engine.cpp").write_text(
                '#include "' + str(ROOT / "3rdparty/xash3d-fwgs/common/cvardef.h") + '"\n'
                'int EnginePrivilegeBit(){return FCVAR_PRIVILEGED;}\n')
            (path / "client.cpp").write_text(r'''
#include <cassert>
#include <map>
#include <string>
#include "hud.h"
cl_enginefunc_t gEngfuncs={};
int EnginePrivilegeBit();
static std::map<std::string,int> registered;
static cvar_t *Register(const char *name,const char *,int flags){registered[name]=flags;return nullptr;}
''' + function(code, "static void CzmMatchChatRegister") + r'''
int main(){
 assert(FCVAR_PRIVILEGED==EnginePrivilegeBit());
 gEngfuncs.pfnRegisterVariable=Register;CzmMatchChatRegister();
 assert(registered.size()==34&&registered.count("czm_mc_head")&&registered.count("czm_mc_epoch"));
 for(const auto &entry:registered)assert(entry.second==EnginePrivilegeBit());
}
''')
            subprocess.run(["g++", *client_sdk_flags(), str(path / "client.cpp"),
                            str(path / "engine.cpp"), "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)

    def test_localized_talk_and_radio_keep_utf8_text_beyond_128_bytes(self):
        text = (ROOT / "cl_dll/text_message.cpp").read_text()
        source = history_source() + r'''
enum{HUD_PRINTCENTER,HUD_PRINTNOTIFY,HUD_PRINTTALK,HUD_PRINTCONSOLE,HUD_PRINTRADIO};
#define MAX_TEXTMSG_STRING 512
struct {CHudSayText m_SayText;}gHUD;
int ScreenWidth=1000,ScreenHeight=500;
namespace DrawUtils{int ConsoleStringLen(const char*){return 0;}void DrawConsoleString(int,int,const char*){}}
void CenterPrint(const char*){}void ConsolePrint(const char*){}
const char *Localize(const char *s){return s;}
void StripEndNewlineFromString(char *s){size_t n=strlen(s);if(n&&(s[n-1]=='\n'||s[n-1]=='\r'))s[n-1]=0;}
struct CHudTextMessage{int MsgFunc_TextMsg(const char*,int,void*);char *LookupString(const char*s,int *dest=nullptr){return const_cast<char*>(s);}};
'''
        source += function(text, "char* ConvertCRtoNL(")
        source += function(text, "int CHudTextMessage::MsgFunc_TextMsg(")
        build(source + r'''
std::string Decode(const std::string &line){unsigned seq,rgb;int namelen,used=0;assert(sscanf(line.c_str(),"%u %x %d %n",&seq,&rgb,&namelen,&used)==3);std::string out;for(size_t i=used;i+1<line.size();i+=2){char part[3]={line[i],line[i+1],0};out+=(char)strtoul(part,nullptr,16);}return out;}
void Receive(CHudTextMessage &hud,int dest,const std::vector<std::string> &strings){std::string packet(1,(char)dest);for(const auto &s:strings){packet+=s;packet+='\0';}hud.MsgFunc_TextMsg("TextMsg",packet.size(),&packet[0]);}
int main(){
 CzmMatchChatRegister();CzmMatchChatReset();CHudTextMessage hud;g_PlayerInfoList[1].name="Игрок";
 std::string body;for(int i=0;i<90;i++)body+="я";body+=" tail \rконец";
 assert(body.size()>128&&body.size()<450);
 Receive(hud,HUD_PRINTTALK,{"%s1","Начало: "+body,"","",""});
 std::string expected=std::string(1,'\x02')+"Начало: "+body;for(char &c:expected)if(c=='\r')c='\n';
 assert(Decode(cvars["czm_mc_line0"])==expected);
 Receive(hud,HUD_PRINTRADIO,{"1","%s1: %s2","Игрок",body,""});
 expected=std::string(1,'\x02')+"Игрок: "+body;for(char &c:expected)if(c=='\r')c='\n';
 assert(Decode(cvars["czm_mc_line1"])==expected);
 return 0;
}
''')

    def test_open_releases_real_touch_fire_movement_latches_and_wheel(self):
        touch = (ENGINE / "client/input/in_touch.c").read_text()
        stub = r'''
#define FBitSet(value,flag) ((value)&(flag))
enum {TOUCH_FL_STICK=1,TOUCH_FL_COMMAND_LATCH=2,TOUCH_FL_UNPRIVILEGED=4,touch_joy,touch_command};
struct touch_button_t {touch_button_t *next;int finger,type,flags;bool latched;const char *command;float stick_x,stick_y;};
struct {struct {touch_button_t *first;}list_user;bool move_stick=true;int move_finger=4,resize_finger=4,look_finger=5,wheel_finger=6;touch_button_t *move_button;float forward=1,side=1,yaw=.4f,pitch=.6f;bool precision=true;}touch;
bool wheel=true;void Touch_CzmWheelClose(){wheel=false;}
'''
        source = ENGINE_STUB.replace("void Touch_ResetLoadingInput(){touchReleases++;}", "")
        source += stub + "\n".join(function(touch, name) for name in [
            "static void Touch_ReleaseStick(", "static void Touch_AddButtonCommand(",
            "static void Touch_ReleaseLatch(", "static void Touch_ResetSticks( void )\n{", "void Touch_ResetLoadingInput("])
        console = CONSOLE.read_text()
        source += function(console, "static void Con_CzmReleaseChatInput")
        build(source + r'''
int main(){
 touch_button_t joy={nullptr,4,touch_joy,TOUCH_FL_STICK,false,"",.4f,.7f};
 touch_button_t fire={&joy,1,touch_command,0,false,"+attack",0,0};
 touch_button_t mic={&fire,2,touch_command,TOUCH_FL_COMMAND_LATCH,true,"+voicerecord",0,0};
 touch_button_t skill={&mic,3,touch_command,0,false,"+czm_skill_e",0,0};
 touch.list_user.first=&skill;touch.move_button=&joy;osKeyboard=true;
 Con_CzmReleaseChatInput();
 assert(cbuf=="-czm_skill_e\n-voicerecord\n-attack\n");
 assert(!touch.forward&&!touch.side&&!touch.yaw&&!touch.pitch&&!touch.precision&&!touch.move_button&&!touch.move_stick&&!wheel&&!osKeyboard);
 assert(touch.move_finger==-1&&touch.look_finger==-1&&touch.resize_finger==-1&&touch.wheel_finger==-1);
 for(auto b:{&skill,&mic,&fire,&joy})assert(b->finger==-1&&!b->latched);
 assert(!joy.stick_x&&!joy.stick_y);std::string once=cbuf;
 Con_CzmReleaseChatInput();assert(cbuf==once&&keyReleases==2); // repeated close is idempotent
 return 0;
}
''')

    def test_filtered_history_colors_utf8_ring_and_reset(self):
        build(history_source() + r'''
std::string Decode(const std::string &line){unsigned seq,rgb;int namelen,used=0;assert(sscanf(line.c_str(),"%u %x %d %n",&seq,&rgb,&namelen,&used)==3);std::string out;for(size_t i=used;i+1<line.size();i+=2){char part[3]={line[i],line[i+1],0};out+=(char)strtoul(part,nullptr,16);}return out;}
void Receive(CHudSayText &hud,const char *format,const char *nick,const char *text){std::string packet(1,1);for(const char *s:{format,nick,text,""}){packet+=s;packet+='\0';}hud.MsgFunc_SayText("SayText",packet.size(),&packet[0]);}
int main(){
 CzmMatchChatRegister();CzmMatchChatReset();assert(cvars.size()==34&&cvars["czm_mc_head"]=="0");
 auto epoch=s_czmChatEpoch;CHudSayText hud;g_PlayerInfoList[1].name="Игрок";
 Receive(hud,"#Cstrike_Chat_AllDead","Игрок","hidden");assert(s_czmChatHead==0); // no history leak from filtered dead/spec messages
 Receive(hud,"#Cstrike_Chat_AllSpec","Игрок","hidden");assert(s_czmChatHead==0);
 dead=true;Receive(hud,"#Cstrike_Chat_AllDead","Игрок","visible");assert(s_czmChatHead==1);
 dead=false;g_iUser1=1;Receive(hud,"#Cstrike_Chat_AllSpec","Игрок","visible");assert(s_czmChatHead==2);
 g_iUser1=0;Receive(hud,"#Cstrike_Chat_All","","Привет");assert(Decode(cvars["czm_mc_line2"])==std::string("\x03")+"Игрок : \x01Привет");
 unsigned seq,rgb;int nicklen;assert(sscanf(cvars["czm_mc_line2"].c_str(),"%u %x %d",&seq,&rgb,&nicklen)==3);assert(seq==3&&rgb==0x99CCFF&&nicklen==11);
 const std::string raw=std::string("\x07")+"FF8844[LVL] \x03Игрок \x01hello \x04green ;quote\"";
 CzmMatchChatPublish(raw.c_str(),raw.size(),1);assert(Decode(cvars["czm_mc_line3"])==raw);
 assert(writes[writes.size()-2]=="czm_mc_line3"&&writes.back()=="czm_mc_head");
 std::string longline(1022,'x');longline+="я";CzmMatchChatPublish(longline.c_str(),longline.size(),0);assert(Decode(cvars["czm_mc_line4"])==std::string(1022,'x'));
 for(int i=0;i<65;i++){std::string s="message"+std::to_string(i);CzmMatchChatPublish(s.c_str(),s.size(),0);}
 assert(s_czmChatHead==70&&cvars.size()==34);
 assert(Decode(cvars["czm_mc_line5"])=="message64");
 CzmMatchChatReset();assert(s_czmChatHead==0&&s_czmChatEpoch==epoch+1&&cvars["czm_mc_head"]=="0");
 return 0;
}
''')

    def test_utf8_controls_and_raw_network_payload(self):
        build(engine_source() + r'''
std::string Hex(const std::string &s){const char *d="0123456789ABCDEF";std::string h;for(unsigned char c:s){h+=d[c>>4];h+=d[c&15];}return h;}
int main(){
 char text[191];
 for(const std::string &s:{"Привет ёж EN" ,"quotes \" ;quit; echo keep data", "😀"}){
  assert(Con_CzmDecodeChatHex(Hex(s).c_str(),text)&&text==s);
  assert(Con_CzmWriteChat(false,text));assert(wire.back()=="say \""+s+"\"");
  assert(Con_CzmWriteChat(true,text));assert(wire.back()=="say_team \""+s+"\"");
 }
 assert(cbuf.empty());
 for(const char *h:{"","0","GG","00","610062","0A","0D","1B","7F","C0AF","ED A080","EDA080","F4908080","F5808080","E282","80"})
  assert(!Con_CzmDecodeChatHex(h,text));
 assert(!Con_CzmValidChat("   "));assert(!Con_CzmValidChat("line\nquit"));assert(!Con_CzmValidChat("line\rquit"));
 assert(Con_CzmDecodeChatHex(Hex(std::string(190,'a')).c_str(),text));
 assert(!Con_CzmDecodeChatHex(Hex(std::string(191,'a')).c_str(),text));
 assert(Con_CzmDecodeChatHex(Hex(std::string(188,'a')+"я").c_str(),text));
 assert(!Con_CzmDecodeChatHex(Hex(std::string(189,'a')+"я").c_str(),text));
 size_t count=wire.size();cls.state=0;assert(!Con_CzmWriteChat(false,"hello"));cls.state=ca_active;
 cls.demoplayback=true;assert(!Con_CzmWriteChat(false,"hello"));cls.demoplayback=false;
 host.status=HOST_NOFOCUS;assert(!Con_CzmWriteChat(false,"hello"));assert(wire.size()==count);
 return 0;
}
''')

    def test_open_repeated_close_epochs_and_ime_fallback(self):
        build(engine_source() + r'''
int main(){
 czm_match_chat.value=1;
 for(int i=0;i<50;++i){
  args={"messagemode"};Con_MessageMode_f();assert(cls.key_dest==key_menu&&!osKeyboard&&czm_match_chat_active.value==1);
  unsigned seq=czm_chat_request_serial;assert(std::string(czm_match_chat_request.string)==std::to_string(seq)+" 0");
  args={"messagemode2"};Con_MessageMode2_f();assert(std::string(czm_match_chat_request.string)==std::to_string(seq+1)+" 1");
  args={"czm_match_chat_close",std::to_string(seq)};Con_CzmMatchChatClose_f();assert(czm_match_chat_active.value==1);
  args={"czm_match_chat_send","1",czm_match_chat_epoch.string,"D09FD180D0B8D0B2D0B5D182"};Con_CzmMatchChatSend_f();assert(wire.back()=="say_team \"Привет\"");
  size_t sent=wire.size();args[2]="0";Con_CzmMatchChatSend_f();assert(wire.size()==sent);
  args[2]=czm_match_chat_epoch.string;args[1]="9";Con_CzmMatchChatSend_f();assert(wire.size()==sent);
  auto oldEpoch=czm_chat_epoch;host.status=HOST_SLEEP;Con_CzmMatchChatFrame();assert(czm_chat_epoch==oldEpoch+1&&!czm_match_chat_active.value&&!osKeyboard);
  host.status=HOST_FRAME;args={"czm_match_chat_send","0",std::to_string(oldEpoch),"61"};Con_CzmMatchChatSend_f();assert(wire.size()==sent);
 }
 assert(touchReleases>=150&&keyReleases==touchReleases);
 args={"messagemode"};Con_MessageMode_f();unsigned epoch=czm_chat_epoch;cls.key_dest=key_game;Con_CzmMatchChatFrame();assert(czm_chat_epoch==epoch+1&&!czm_match_chat_active.value);
 args={"czm_match_chat_ime","1"};Con_CzmMatchChatIme_f();assert(osKeyboard&&cls.key_dest==key_message&&!strcmp(con.chat_cmd,"say_team"));
 strcpy(con.chat.buffer,"word\";quit");Key_Message(K_ENTER);assert(!osKeyboard&&cls.key_dest==key_game&&cbuf.empty());
 assert(wire.back()=="say_team \"word\";quit\"");
 czm_match_chat.value=0;args={"messagemode"};Con_MessageMode_f();assert(osKeyboard&&cls.key_dest==key_message&&!strcmp(con.chat_cmd,"say"));
 Key_Message(K_ESCAPE);assert(!osKeyboard);
 czm_match_chat.value=1;args={"messagemode","custom_message"};Con_MessageMode_f();assert(osKeyboard&&!strcmp(con.chat_cmd,"custom_message"));
 return 0;
}
''')

    def test_ime_after_active_custom_requests_survives_next_frame(self):
        build(engine_source() + r'''
int main(){
 czm_match_chat.value=1;
 for(int i=0;i<3;i++){args={"messagemode"};Con_MessageMode_f();}
 for(const char *channel:{"0","1"}){
  args={"messagemode2"};Con_MessageMode2_f();
  assert(czm_chat_request_serial>=3&&czm_match_chat_active.value==1&&cls.key_dest==key_menu&&!osKeyboard);
  unsigned epoch=czm_chat_epoch;int releases=keyReleases;
  args={"czm_match_chat_ime",channel};Con_CzmMatchChatIme_f();
  assert(!czm_match_chat_active.value&&!osKeyboard&&cls.key_dest==key_menu&&keyReleases==releases+1);
  assert(std::string(czm_match_chat_ime_pending.string)==(!strcmp(channel,"1")?"2":"1"));
  Con_CzmMatchChatFrame();assert(czm_chat_epoch==epoch&&!osKeyboard);
  // UI_CloseClientMenu runs first; its unconditional key_game must not erase the later IME destination.
  Key_SetKeyDest(key_game);Con_CzmMatchChatIme_f();
  assert(!czm_match_chat_active.value&&osKeyboard&&cls.key_dest==key_message&&!strcmp(czm_match_chat_ime_pending.string,"0"));
  assert(!strcmp(con.chat_cmd,!strcmp(channel,"1")?"say_team":"say"));
  strcpy(con.chat.buffer,"Черновик");Con_CzmMatchChatFrame();
  assert(czm_chat_epoch==epoch&&osKeyboard&&cls.key_dest==key_message&&!strcmp(con.chat.buffer,"Черновик"));
  Key_Message(K_ESCAPE);assert(!osKeyboard&&cls.key_dest==key_game);
 }
 return 0;
}
''')

    def test_reset_invalidates_open_request_before_ui_observes_it(self):
        build(engine_source() + r'''
int main(){
 czm_match_chat.value=1;args={"messagemode2"};Con_MessageMode2_f();
 unsigned serial=czm_chat_request_serial,epoch=czm_chat_epoch;
 assert(czm_match_chat_active.value==1&&std::string(czm_match_chat_request.string)==std::to_string(serial)+" 1");
 // Focus/map reset arrives before the UI consumes this pending open request.
 Cvar_DirectFullSet(&czm_match_chat_ime_pending,"2",0);Con_CzmMatchChatReset();
 assert(!strcmp(czm_match_chat_ime_pending.string,"0"));
 assert(czm_chat_epoch==epoch+1&&!czm_match_chat_active.value&&!strcmp(czm_match_chat_request.string,"0 0"));
 Con_CzmMatchChatFrame();assert(!strcmp(czm_match_chat_request.string,"0 0"));
 // The next deliberate open has a fresh serial, even though the UI never saw the old one.
 args={"messagemode"};Con_MessageMode_f();
 assert(czm_chat_request_serial==serial+1&&czm_match_chat_active.value==1);
 assert(std::string(czm_match_chat_request.string)==std::to_string(serial+1)+" 0");
 return 0;
}
''')

    def test_lifecycle_hooks_are_before_focus_sleep_and_clear_state(self):
        for file in ["platform/sdl1/host_sdl1.c", "platform/sdl2/host_sdl2.c", "platform/sdl3/host_sdl3.c"]:
            active = function((ENGINE/file).read_text(), "static void SDLash_ActiveEvent")
            self.assertLess(active.index("Con_CzmMatchChatReset"), active.index("host.status = HOST_NOFOCUS"))
        clear = function((ENGINE/"client/cl_main.c").read_text(), "void CL_ClearState")
        self.assertLess(clear.index("Con_CzmMatchChatReset"), clear.index("CL_ClearResourceLists"))
        console = CONSOLE.read_text()
        send = function(console, "static void Con_CzmMatchChatSend_f")
        self.assertIn("czm_match_chat_epoch.string", send)
        self.assertNotIn("Cbuf_", send)


if __name__ == "__main__":
    unittest.main()
