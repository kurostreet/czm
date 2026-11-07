"""Execute the actual combat state, touch migration, keypad input and PCM meter."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs/engine/client"


def build(source):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)
        (path / "main.cpp").write_text(source)
        subprocess.run(["g++", "-std=c++11", "-I" + str(ROOT / "common"),
                        str(path / "main.cpp"), "-o", str(path / "run")], check=True)
        subprocess.run([str(path / "run")], check=True)


class CombatControlsTests(unittest.TestCase):
    def test_server_state_and_magazines_reset_between_lives_and_servers(self):
        code = (ROOT / "cl_dll/hud/czm_skills.cpp").read_text()
        code = re.sub(r'#include "[^"]+"\n', '', code)
        build(r'''
#include <cassert>
#include <map>
#include <string>
#include <vector>
#include <cstring>
#include "czm_combat.h"
struct {bool m_fPlayerDead=false;int m_iIntermission=0;} gHUD;
int g_iUser1;float clockTime;
std::map<std::string,std::string> cvars;
float Time(){return clockTime;}
const char *Get(const char *key){return cvars[key].c_str();}
void Set(const char *key,const char *value){cvars[key]=value;}
void Hook(const char *,int(*)(const char*,int,void*)){}
struct {void(*pfnHookUserMsg)(const char*,int(*)(const char*,int,void*));void(*Cvar_Set)(const char*,const char*);
const char *(*pfnGetCvarString)(const char*);float(*GetClientTime)();} gEngfuncs={Hook,Set,Get,Time};
struct BufferReader{const unsigned char *p;int pos=0,size;BufferReader(const char*,void *b,int n):p((unsigned char*)b),size(n){}
int ReadByte(){assert(pos<size);return p[pos++];}int ReadShort(){int a=ReadByte(),b=ReadByte();return (short)(a|(b<<8));}};
void CZM_SkillsFrame();void CZM_SkillsReset();
''' + code + r'''
void Skill(int klass,int flags=0,int cd=0,int secondary=0,int charge=0){
unsigned char b[11]={1,(unsigned char)klass,(unsigned char)flags,(unsigned char)(cd&255),(unsigned char)(cd>>8),
(unsigned char)(secondary&255),(unsigned char)(secondary>>8),(unsigned char)(charge&255),(unsigned char)(charge>>8),0,0};
MsgFunc_CzmSkill("CzmSkill",sizeof(b),b);}
int main(){
CZM_SkillsInit();assert(cvars["czm_skill_mask"]=="0");
const int expected[]={0,1,2,0,1,1,1,5,4,1,3};
for(int i=0;i<=10;i++){Skill(i);assert(std::stoi(cvars["czm_skill_mask"])==expected[i]);}
clockTime=4;Skill(10,0,200,100);CzmCombat::State s;assert(CzmCombat::Parse(Get("czm_skill_state"),s));
assert(CzmCombat::Cooldown(s,CzmCombat::G)==100&&CzmCombat::Cooldown(s,CzmCombat::R)==200);
clockTime=5.5;CZM_SkillsFrame();CzmCombat::Parse(Get("czm_skill_state"),s);assert(s.primary==185&&s.secondary==85);
Skill(7,1,100);assert(std::string(CzmCombat::Name(s,CzmCombat::G,false))=="Invisibility");
CzmCombat::Parse(Get("czm_skill_state"),s);assert(std::string(CzmCombat::Name(s,CzmCombat::G,false))=="Ice orb");
assert(CzmCombat::Cooldown(s,CzmCombat::E)==0);
gHUD.m_fPlayerDead=true;CZM_SkillsFrame();assert(cvars["czm_skill_mask"]=="0");
gHUD.m_fPlayerDead=false;CZM_SkillsFrame();assert(cvars["czm_skill_mask"]=="0"); // no stale life on respawn
Skill(8,2,0,0,100);assert(cvars["czm_skill_mask"]=="4");
g_iUser1=4;CZM_SkillsFrame();assert(cvars["czm_skill_mask"]=="0");g_iUser1=0;
unsigned char packet[33]={1};packet[1+28]=70;packet[1+20]=150;packet[1+21]=25;packet[32]=1;
MsgFunc_CzmClip("CzmClip",sizeof(packet),packet);
assert(CZM_ClipCapacity(28,30)==70&&CZM_ClipCapacity(20,100)==150&&CZM_ClipCapacity(21,8)==25&&CZM_UnlimitedReserve());
assert(CZM_ClipCapacity(99,7)==7);CZM_SkillsReset();assert(CZM_ClipCapacity(28,30)==30&&!CZM_UnlimitedReserve());
assert(!CzmCombat::Parse("8 0 0 0 1000 0",s)&&CzmCombat::Mask(s.klass)==0);
assert(!CzmCombat::Parse("1 0 0 0 0 0 trailing",s));
return 0;}
''')

    def test_existing_layouts_gain_only_missing_controls_and_release_hidden_holds(self):
        source = (ENGINE / "input/in_touch.c").read_text()
        names = ["static int Touch_CzmSkillSlot", "static qboolean Touch_IsVisible",
                 "static void Touch_CzmEnsureSkills( qboolean force )", "static void Touch_CzmPublishAnchors",
                 "static void Touch_CzmCancelSkillHolds( void )\n{", "void Touch_SetClientOnly( byte state )"]
        code = '\n'.join(function(source, name) for name in names)
        build(r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
typedef bool qboolean;typedef unsigned char byte;
#define Q_strcmp strcmp
#define Q_snprintf snprintf
#define TO_SCRN_X(x) ((x)*1000)
#define TO_SCRN_Y(y) ((y)*500)
#define FBitSet(v,b) ((v)&(b))
enum{TOUCH_FL_HIDE=1,TOUCH_FL_CLIENT=2,TOUCH_FL_MP=4,TOUCH_FL_SP=8,state_edit=1,ca_active=2};
struct touch_button_t{float x1,y1,x2,y2,aspect;char name[32],command[256],texture[256];int flags=0,finger=-1;bool latched=false;touch_button_t *next=nullptr;};
struct List{touch_button_t *first=nullptr,*last=nullptr;};
struct{List list_user;bool config_loaded=false,configchanged=false,clientonly=false;int state=0,resize_finger,move_finger,look_finger,wheel_finger;float forward,side;}touch;
struct{int state=ca_active;}cls;struct{int maxclients=32;}cl;
struct Cvar{float value=0;std::string text;const char *string="";};Cvar czm_skill_mask,czm_touch_anchors;
std::vector<std::string> commands;
void Cvar_DirectSet(Cvar *c,const char *s){c->text=s;c->string=c->text.c_str();}
void Touch_AddButtonCommand(const touch_button_t*,const char *s){commands.push_back(s);}
bool Touch_CzmLeftFireHidden(touch_button_t*){return false;}
enum{dc_arrow,dc_none};void Touch_DisableEdit_f(){}void Platform_SetCursorType(int){}void IN_ActivateMouse(){}void IN_DeactivateMouse(){}
float Touch_AspectRatio(){return .5f;}
touch_button_t *Touch_AddButton(List *l,const char *name,const char *texture,const char *command,float x1,float y1,float x2,float y2,byte *,bool){
auto b=new touch_button_t();strcpy(b->name,name);strcpy(b->texture,texture);strcpy(b->command,command);
b->x1=x1;b->y1=y1;b->x2=x2;b->y2=y2;if(l->last)l->last->next=b;else l->first=b;l->last=b;return b;}
''' + code + r'''
int main(){byte color[4]={};auto saved=Touch_AddButton(&touch.list_user,"custom","custom","czm_skill_g",.2,.3,.3,.5,color,true);
saved->flags=TOUCH_FL_HIDE;Touch_CzmEnsureSkills(true);assert(touch.configchanged);
int count=0;touch_button_t *e=nullptr,*r=nullptr;for(auto b=touch.list_user.first;b;b=b->next){count++;if(!strcmp(b->command,"+czm_skill_e"))e=b;if(!strcmp(b->command,"czm_skill_r"))r=b;}
assert(count==3&&e&&r&&saved->x1==.2f&&saved->y1==.3f&&saved->flags==TOUCH_FL_HIDE);
touch.config_loaded=true;czm_skill_mask.value=5;Touch_CzmEnsureSkills(false);
assert(Touch_IsVisible(saved)&&Touch_IsVisible(e)&&!Touch_IsVisible(r));
assert(r->next==e&&e->next==nullptr); // no duplicates or replacement
e->finger=42;czm_skill_mask.value=0;Touch_CzmPublishAnchors();assert(e->finger==-1&&commands.size()==1&&commands[0]=="-czm_skill_e\n");
Touch_CzmPublishAnchors();assert(commands.size()==1);czm_skill_mask.value=4;
assert(Touch_IsVisible(e)&&!Touch_IsVisible(saved));cls.state=0;assert(!Touch_IsVisible(e));
touch.state=state_edit;assert(Touch_IsVisible(saved)&&Touch_IsVisible(r)&&Touch_IsVisible(e));
e->finger=73;Touch_SetClientOnly(1);assert(e->finger==-1&&commands.size()==2&&commands.back()=="-czm_skill_e\n");
Touch_SetClientOnly(1);assert(commands.size()==2);e->latched=true;Touch_CzmCancelSkillHolds();assert(!e->latched&&commands.size()==3);
return 0;}
''')



UI_STUB = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <cstdarg>
#include <map>
#include <string>
#include <vector>
#include "czm_combat.h"
#define UI_DIR "gfx/czm/ui/"
#define Q_max(a,b) ((a)>(b)?(a):(b))
#define Q_min(a,b) ((a)<(b)?(a):(b))
#define bound(lo,x,hi) ((x)<(lo)?(lo):(x)>(hi)?(hi):(x))
enum{KEY_MENU,CZMF_SMALL,CZMF_PANEL_TITLE,CZMF_TINY,CZMF_TILE_TITLE};
int ScreenWidth=1536,ScreenHeight=716,closes=0,painted=0;typedef int HFont;
std::vector<std::string> commands;std::map<std::string,std::string>values;std::map<std::string,float>floats;
struct Active{bool IsActive(){return false;}};
struct {int cursorX=0,cursorY=0,xOffset=0,yOffset=0,width=1536,realTime=100;struct{Active menu,client;}unused;Active menu,client;}uiStatic;
namespace EngFuncs{void KEY_SetDest(int){}void ClientCmd(bool,const char*s){commands.push_back(s);}void ClientCmdF(bool,const char*f,...){char b[128];va_list args;va_start(args,f);vsnprintf(b,sizeof(b),f,args);va_end(args);commands.push_back(b);}
const char *GetCvarString(const char*n){return values[n].c_str();}float GetCvarFloat(const char*n){return floats[n];}}
namespace UI{namespace Key{bool IsEscape(int key){return key==27;}bool IsLeftMouse(int key){return key==1;}}}
bool CL_IsActive(){return true;}bool CZM_IsRussian(){return true;}void CZM_PlayClick(){}
unsigned PackRGBA(int,int,int,int){return 0;}unsigned CZM_White(){return 0;}unsigned CZM_Grey(){return 0;}
struct CzmRect{int x,y,w,h;};CzmRect CZM_Rect(int x,int y,int w,int h){return{x,y,w,h};}
struct V{int x=0,y=0,w=0,h=0;};
class CMenuBaseClientWindow{public:V pos,size;CMenuBaseClientWindow(const char*){}virtual void Init(){}virtual void VidInit(){}virtual void Show(){}virtual void Hide(){}virtual void Draw(){}virtual bool KeyDown(int){return true;}virtual bool KeyUp(int){return true;}virtual bool MouseMove(int,int){return true;}};
void CZM_KeepClientMenu(CMenuBaseClientWindow*){}void CZM_CloseClientMenuSoon(CMenuBaseClientWindow*){closes++;}
int CZM_Font(int){return 0;}
void FittedText(int,int,int,int,int,const char*,unsigned){painted++;}
void CZM_DrawPanel(CzmRect r){assert(r.x>=0&&r.y>=0&&r.x+r.w<=ScreenWidth&&r.y+r.h<=ScreenHeight);}
void CZM_DrawImage(const char*,int x,int y,int w,int h,unsigned){assert(x>=0&&y>=0&&x+w<=ScreenWidth&&y+h<=ScreenHeight);painted++;}
void CZM_DrawButton(const char*,CzmRect,const char*,unsigned,bool){}
void UI_FillRect(int x,int y,int w,int h,unsigned){assert(x>=0&&y>=0&&w>=0&&h>=0&&x+w<=ScreenWidth&&y+h<=ScreenHeight);painted++;}
'''


if __name__ == '__main__':
    unittest.main()
