"""Run the real fortification role bridge, saved-layout migration and touch visibility."""
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
TOUCH = ROOT / "3rdparty/xash3d-fwgs/engine/client/input/in_touch.c"


def build(source):
    with tempfile.TemporaryDirectory(prefix="czm-fortification-controls-") as folder:
        path = Path(folder)
        (path / "main.cpp").write_text(source)
        subprocess.run(["g++", "-std=c++11", "-I" + str(ROOT / "common"),
                        str(path / "main.cpp"), "-o", str(path / "run")], check=True)
        subprocess.run([str(path / "run")], check=True)


def migration_code():
    source = TOUCH.read_text()
    names = ["static int Touch_CzmSkillSlot", "static qboolean Touch_CzmFortPositionClear",
             "static qboolean Touch_CzmFortFindPosition",
             "static void Touch_CzmEnsureFortifications( qboolean force )"]
    return '\n'.join(function(source, name) for name in names)


class FortificationControlsTests(unittest.TestCase):
    def test_only_explicit_ordinary_human_ct_role_enables_fortifications(self):
        build(r'''
#include <cassert>
#include <cstdio>
#include "czm_combat.h"
int main(){
using namespace CzmCombat;
State state;
assert(FORT_HUMAN_CT==4);
assert(Parse("0 4 0 0 0 0",state));
assert(FortificationMask(state)==3&&Mask(state.klass)==0);
// Class zero also describes classic zombies and unsupported legacy servers.
assert(Parse("0 0 0 0 0 0",state)&&FortificationMask(state)==0);
for(int klass=1;klass<=10;klass++)for(int flags=0;flags<=3;flags++){
    char text[64];std::snprintf(text,sizeof(text),"%d %d 10 20 30 40",klass,flags);
    assert(Parse(text,state)&&FortificationMask(state)==0);
}
for(int klass=0;klass<=10;klass++)for(int flags=4;flags<=255;flags++){
    if(klass==0&&flags==FORT_HUMAN_CT)continue;
    char text[64];std::snprintf(text,sizeof(text),"%d %d 0 0 0 0",klass,flags);
    assert(!Parse(text,state)&&FortificationMask(state)==0);
}
state.klass=1;state.flags=FORT_HUMAN_CT;assert(FortificationMask(state)==0);
assert(!Parse("0 4 0 0 0 0 trailing",state));
assert(!Parse("0 4 0 0 -1 0",state));
assert(!Parse("0 4 601 0 0 0",state));
return 0;}
''')

    def test_fortification_role_changes_expire_and_never_return_from_previous_life(self):
        code = (ROOT / "cl_dll/hud/czm_skills.cpp").read_text()
        code = re.sub(r'#include "[^\"]+"\n', '', code)
        build(CLIENT_STUB + code + r'''
void Skill(int klass,int flags=0,int cooldown=0){
    unsigned char packet[11]={1,(unsigned char)klass,(unsigned char)flags,
        (unsigned char)(cooldown&255),(unsigned char)(cooldown>>8),0,0,0,0,0,0};
    MsgFunc_CzmSkill("CzmSkill",sizeof(packet),packet);
}
void Fort(int expected){assert(std::stoi(cvars["czm_fort_mask"])==expected);}
int main(){
CZM_SkillsInit();Fort(0);CZM_SkillsFrame();Fort(0);
// Timestamp zero is valid; a packet must be received before controls appear.
clockTime=0;Skill(0,CzmCombat::FORT_HUMAN_CT);Fort(3);
assert(cvars["czm_skill_mask"]=="0");
clockTime=2.99f;CZM_SkillsFrame();Fort(3);
clockTime=3.01f;CZM_SkillsFrame();Fort(0);
clockTime=4;Skill(0,CzmCombat::FORT_HUMAN_CT);Fort(3);
// Infection into a classic zombie has class zero, exactly like a human.
Skill(0,0);Fort(0);Skill(0,CzmCombat::FORT_HUMAN_CT);Fort(3);
Skill(7,1,100);Fort(0);assert(cvars["czm_skill_mask"]=="5");
clockTime=9;CZM_SkillsFrame();Fort(0);
assert(cvars["czm_skill_mask"]=="5"); // fortification timeout must not disable zombie abilities
Skill(0,CzmCombat::FORT_HUMAN_CT);Fort(3);
gHUD.m_fPlayerDead=true;CZM_SkillsFrame();Fort(0);
gHUD.m_fPlayerDead=false;CZM_SkillsFrame();Fort(0);
Skill(0,CzmCombat::FORT_HUMAN_CT);Fort(3);
g_iUser1=4;CZM_SkillsFrame();Fort(0);g_iUser1=0;CZM_SkillsFrame();Fort(0);
Skill(0,CzmCombat::FORT_HUMAN_CT);gHUD.m_iIntermission=1;CZM_SkillsFrame();Fort(0);
gHUD.m_iIntermission=0;CZM_SkillsFrame();Fort(0);
clockTime=15;Skill(0,CzmCombat::FORT_HUMAN_CT);Fort(3);
clockTime=14;CZM_SkillsFrame();Fort(0);clockTime=15;CZM_SkillsFrame();Fort(0);
Skill(0,CzmCombat::FORT_HUMAN_CT);Fort(3);
Skill(1,CzmCombat::FORT_HUMAN_CT);CZM_SkillsFrame();Fort(0);
Skill(0,CzmCombat::FORT_HUMAN_CT);Fort(3);
CZM_SkillsReset();Fort(0);CZM_SkillsFrame();Fort(0);
return 0;}
''')

    def test_editor_catalogue_has_two_direct_server_actions_and_icons(self):
        menu = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        actions = re.search(r'static const CzmAction s_actions\[\] =\s*\{(.*?)\n\};', menu, re.S).group(1)
        icons = re.search(r'static const char \*s_icons\[\] =\s*\{(.*?)\n\};', menu, re.S).group(1)
        rows = re.findall(r'\{\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*(GROUP_\w+)\s*\}', actions)
        for command, icon, label in (("czm_props", "props", "Пропс"),
                                     ("czm_lasermine", "lasermine", "Лазер")):
            matching = [row for row in rows if row[3] == command]
            self.assertEqual(len(matching), 1)
            row = matching[0]
            self.assertEqual((row[0], row[1], row[4]), (icon, label, "GROUP_SERVER"))
            self.assertTrue(row[2])
            self.assertIn('"' + icon + '"', icons)
            self.assertTrue((ROOT / "3rdparty/czm_project/gfx/czm/touch" / (icon + ".png")).is_file())

    def test_reset_hud_message_revokes_role_even_if_no_dead_frame_was_drawn(self):
        code = (ROOT / "cl_dll/hud/czm_skills.cpp").read_text()
        code = re.sub(r'#include "[^\"]+"\n', '', code)
        hud = (ROOT / "cl_dll/hud_msg.cpp").read_text()
        reset = function(hud, "int CHud :: MsgFunc_ResetHUD")
        # Execute the real message's lifecycle prologue before its unrelated HUD element resets.
        prologue = reset[reset.index("{") + 1:reset.index("// clear all hud data")]
        build(CLIENT_STUB + code + "\nvoid ResetHudMessage(){\n" + prologue + r'''
}
int main(){
CZM_SkillsInit();clockTime=12;
unsigned char human[11]={1,0,CzmCombat::FORT_HUMAN_CT};
MsgFunc_CzmSkill("CzmSkill",sizeof(human),human);
assert(cvars["czm_fort_mask"]=="3");
// A fast server death/respawn may have no client draw between the two events.
assert(!gHUD.m_fPlayerDead);ResetHudMessage();
assert(cvars["czm_fort_mask"]=="0");CZM_SkillsFrame();
assert(cvars["czm_fort_mask"]=="0");
MsgFunc_CzmSkill("CzmSkill",sizeof(human),human);assert(cvars["czm_fort_mask"]=="3");
return 0;}
''')

    def test_saved_layouts_preserve_custom_controls_and_resolve_name_collisions(self):
        build(ENGINE_STUB + migration_code() + r'''
int main(){
byte color[4]={9,18,27,36};
auto saved=Touch_AddButton(&touch.list_user,"my_custom_props","custom.png","czm_props",.11f,.22f,.27f,.33f,color,true);
saved->flags=TOUCH_FL_HIDE|TOUCH_FL_MP;saved->aspect=.7f;saved->finger=13;saved->latched=true;
auto collision=Touch_AddButton(&touch.list_user,"czm_fort_laser","jump.png","+jump",.4f,.5f,.6f,.7f,color,true);
auto suffixed=Touch_AddButton(&touch.list_user,"czm_fort_laser_1","fire.png","+attack",.2f,.3f,.4f,.5f,color,true);
Touch_CzmEnsureFortifications(false);assert(Count()==3&&!touch.configchanged);
touch.config_loaded=true;Touch_CzmEnsureFortifications(false);assert(Count()==3);
czm_fort_mask.value=3;cls.state=0;Touch_CzmEnsureFortifications(false);assert(Count()==3);
cls.state=ca_active;Touch_CzmEnsureFortifications(false);
assert(Count()==4&&touch.configchanged);
auto laser=ByCommand("czm_lasermine");assert(laser&&ByCommand("czm_props")==saved);
assert(strcmp(laser->name,collision->name)&&strcmp(laser->name,suffixed->name));
assert(!strcmp(collision->command,"+jump")&&!strcmp(suffixed->command,"+attack"));
assert(saved->x1==.11f&&saved->y1==.22f&&saved->x2==.27f&&saved->y2==.33f);
assert(saved->aspect==.7f&&saved->flags==(TOUCH_FL_HIDE|TOUCH_FL_MP));
assert(saved->finger==13&&saved->latched&&!strcmp(saved->texture,"custom.png"));
assert(!memcmp(saved->color,color,4));
assert(laser->aspect==1.f&&ClearOfOtherControls(laser));
assert(!strcmp(laser->texture,"gfx/czm/touch/lasermine.png"));
touch.configchanged=false;Touch_CzmEnsureFortifications(false);Touch_CzmEnsureFortifications(true);
assert(Count()==4&&!touch.configchanged); // repeat profile loads never replace or duplicate actions
// Empty profiles can be populated by the editor without an active server.
touch.list_user=List();touch.config_loaded=false;cls.state=0;czm_fort_mask.value=0;
Touch_CzmEnsureFortifications(true);assert(Count()==2);
auto props=ByCommand("czm_props");laser=ByCommand("czm_lasermine");
assert(props&&laser&&props->x1==.50f&&props->y1==.65f&&props->aspect==1.f);
assert(laser->x1==.57f&&laser->y1==.65f&&laser->aspect==1.f);
assert(!strcmp(props->texture,"gfx/czm/touch/props.png"));
assert(props->x2>props->x1&&props->y2>props->y1&&laser->x2<=1.f&&laser->y2<=1.f);
return 0;}
''')

    def test_all_shipped_schemes_migrate_without_covering_real_controls(self):
        scenarios = []
        for scheme in range(1, 4):
            path = ROOT / "3rdparty/czm_project/touch_presets" / f"czm_scheme{scheme}.cfg"
            setup = []
            commands = set()
            for line in path.read_text().splitlines():
                if not line.startswith("touch_addbutton "):
                    continue
                row = shlex.split(line)
                name, texture, command = row[1:4]
                commands.add(command)
                coords = ','.join(f"{float(value):.9f}f" for value in row[4:8])
                color = ','.join(row[8:12])
                flags = row[12] if len(row) >= 13 else "0"
                aspect = float(row[13]) if len(row) >= 14 else 0.0
                setup.append(
                    '{byte color[4]={' + color + '};auto b=Touch_AddButton(&touch.list_user,'
                    + ','.join('"' + value + '"' for value in (name, texture, command))
                    + ',' + coords + ',color,true);b->flags=' + flags + ';'
                    + (f'b->aspect={aspect:.9f}f;b->y2=b->y1+(b->x2-b->x1)/touchAspect*b->aspect;'
                       if aspect and not texture.startswith('#') else '')
                    + 'before.push_back(*b);original.push_back(b);}'
                )
            missing = sum(command not in commands for command in ("czm_props", "czm_lasermine"))
            scenarios.append(r'''
for(float ratio:{.466f,.5625f,.75f}){
touchAspect=ratio;touch.list_user=List();touch.configchanged=false;
std::vector<touch_button_t> before;std::vector<touch_button_t*> original;
''' + '\n'.join(setup) + r'''
const int oldCount=Count();Touch_CzmEnsureFortifications(true);
auto props=ByCommand("czm_props"),laser=ByCommand("czm_lasermine");
assert(Count()==oldCount+MISSING&&props&&laser);
// Shipped owner controls stay where the owner put them; only auto-added
// controls must find unoccupied space among the other buttons.
if(MISSING)assert(ClearOfOtherControls(props)&&ClearOfOtherControls(laser));
for(unsigned i=0;i<before.size();i++){
    const auto &old=before[i];auto b=original[i];
    assert(b->x1==old.x1&&b->y1==old.y1&&b->x2==old.x2&&b->y2==old.y2);
    assert(b->aspect==old.aspect&&b->flags==old.flags&&!strcmp(b->command,old.command));
}
touch.configchanged=false;Touch_CzmEnsureFortifications(true);
assert(Count()==oldCount+MISSING&&!touch.configchanged);
}
'''.replace("MISSING", str(missing)))
        build(ENGINE_STUB + migration_code() + '\nint main(){\n'
              + '\n'.join(scenarios) + '\nreturn 0;}\n')

    def test_custom_obstacles_relocate_controls_and_full_layouts_add_nothing(self):
        build(ENGINE_STUB + migration_code() + r'''
int main(){
byte color[4]={};
auto hidden=Touch_AddButton(&touch.list_user,"custom-use","use.png","+use",.48f,.64f,.7f,.85f,color,true);
hidden->flags=TOUCH_FL_HIDE;
Touch_CzmEnsureFortifications(true);
auto props=ByCommand("czm_props"),laser=ByCommand("czm_lasermine");
assert(props&&laser&&ClearOfOtherControls(props)&&ClearOfOtherControls(laser));
assert(props->x1!=.50f||props->y1!=.65f);
assert(laser->x1!=.57f||laser->y1!=.65f);
assert(hidden->x1==.48f&&hidden->y1==.64f&&hidden->x2==.7f&&hidden->y2==.85f);
assert(hidden->flags==TOUCH_FL_HIDE);
// The search must fail without replacing custom actions when no clear cell exists.
touch.list_user=List();touch.configchanged=false;
auto full=Touch_AddButton(&touch.list_user,"custom-full","full.png","+jump",0,0,1,1,color,true);
full->flags=TOUCH_FL_HIDE;
Touch_CzmEnsureFortifications(true);
assert(Count()==1&&ByCommand("+jump")==full&&!touch.configchanged);
// Movement/look regions and zombie-only skills do not block the human controls.
touch.list_user=List();touch.configchanged=false;
for(const char *command:{"_move","_look","_joy","_dpad","czm_skill_g","czm_skill_r","+czm_skill_e"}){
    Touch_AddButton(&touch.list_user,command,"",command,0,0,1,1,color,true);
}
Touch_AddButton(&touch.list_user,"invalid-width","","+attack",1,0,0,1,color,true);
Touch_AddButton(&touch.list_user,"invalid-height","","+use",0,1,1,0,color,true);
Touch_CzmEnsureFortifications(true);
props=ByCommand("czm_props");laser=ByCommand("czm_lasermine");
assert(props&&laser&&props->x1==.50f&&props->y1==.65f&&laser->x1==.57f&&laser->y1==.65f);
// On a wide display, the physically nearest clear cell is above this obstacle,
// although comparing normalized x/y distances would choose the left-hand cell.
touch.list_user=List();
Touch_AddButton(&touch.list_user,"physical-obstacle","","+use",.45f,.64f,.70f,.85f,color,true);
float x=.50f,y=.65f;
assert(Touch_CzmFortFindPosition(&x,&y,.06f,.12f));
assert(x>.5299f&&x<.5301f&&y>.4199f&&y<.4201f);
return 0;}
''')

    def test_failed_automatic_placement_waits_before_scanning_again(self):
        build(ENGINE_STUB + migration_code() + r'''
int main(){
byte color[4]={};
Touch_AddButton(&touch.list_user,"occupied","","+jump",0,0,1,1,color,true);
touch.config_loaded=true;czm_fort_mask.value=3;host.realtime=10;
stringComparisons=0;Touch_CzmEnsureFortifications(false);
assert(Count()==1&&stringComparisons>0&&!touch.configchanged);
// This counts every production Q_strcmp: the cooldown must precede even the
// command/name scans, not merely skip the expensive placement grid.
for(double time:{10.,10.25,10.999}){
    host.realtime=time;stringComparisons=0;Touch_CzmEnsureFortifications(false);
    assert(stringComparisons==0&&Count()==1);
}
host.realtime=11.001;stringComparisons=0;Touch_CzmEnsureFortifications(false);
assert(stringComparisons>0&&Count()==1);
// Editor attempts bypass and reset a failed automatic attempt's cached deadline.
host.realtime=11.1;stringComparisons=0;Touch_CzmEnsureFortifications(true);
assert(stringComparisons>0&&Count()==1);
stringComparisons=0;Touch_CzmEnsureFortifications(false);assert(stringComparisons>0);
stringComparisons=0;Touch_CzmEnsureFortifications(false);assert(stringComparisons==0);
// A clock restart cannot retain a deadline from a previous session.
host.realtime=2;stringComparisons=0;Touch_CzmEnsureFortifications(false);
assert(stringComparisons>0&&Count()==1);
stringComparisons=0;Touch_CzmEnsureFortifications(false);assert(stringComparisons==0);
// Once the user makes room, an explicit editor attempt works immediately.
touch.list_user=List();Touch_CzmEnsureFortifications(true);
assert(Count()==2&&ByCommand("czm_props")&&ByCommand("czm_lasermine"));
assert(touch.configchanged);
return 0;}
''')

    def test_visibility_respects_role_editor_hidden_controls_and_releases_old_fingers(self):
        source = TOUCH.read_text()
        names = ["static int Touch_CzmSkillSlot", "static int Touch_CzmFortSlot",
                 "static qboolean Touch_IsVisible", "static void Touch_CzmPublishAnchors"]
        code = '\n'.join(function(source, name) for name in names)
        build(ENGINE_STUB + code + r'''
int main(){
byte color[4]={};
auto props=Touch_AddButton(&touch.list_user,"props","props.png","czm_props",.65f,.58f,.71f,.7f,color,true);
auto laser=Touch_AddButton(&touch.list_user,"laser","laser.png","czm_lasermine",.72f,.58f,.78f,.7f,color,true);
auto fire=Touch_AddButton(&touch.list_user,"fire","fire.png","+attack",.2f,.4f,.3f,.6f,color,true);
auto jump=Touch_AddButton(&touch.list_user,"jump","jump.png","+jump",.8f,.7f,.9f,.9f,color,true);
auto skill=Touch_AddButton(&touch.list_user,"skill","skill.png","+czm_skill_e",.4f,.2f,.5f,.4f,color,true);
assert(!Touch_IsVisible(props)&&!Touch_IsVisible(laser));
assert(Touch_IsVisible(fire)&&Touch_IsVisible(jump));
czm_fort_mask.value=1;assert(Touch_IsVisible(props)&&!Touch_IsVisible(laser));
czm_fort_mask.value=2;assert(!Touch_IsVisible(props)&&Touch_IsVisible(laser));
czm_fort_mask.value=3;assert(Touch_IsVisible(props)&&Touch_IsVisible(laser));
props->flags=TOUCH_FL_HIDE;assert(!Touch_IsVisible(props)&&Touch_IsVisible(laser));
props->flags=0;cls.state=0;assert(!Touch_IsVisible(props)&&!Touch_IsVisible(laser));
// Editor placement remains possible while disconnected, including manually hidden buttons.
touch.state=state_edit;props->flags=TOUCH_FL_HIDE;
assert(Touch_IsVisible(props)&&Touch_IsVisible(laser));
touch.clientonly=true;assert(!Touch_IsVisible(props));touch.clientonly=false;
touch.state=0;props->flags=0;cls.state=ca_active;
props->finger=7;laser->finger=8;laser->latched=true;fire->finger=9;jump->finger=10;
skill->finger=11;czm_skill_mask.value=4;Touch_CzmPublishAnchors();
assert(props->finger==7&&laser->finger==8&&commands.empty());
assert(czm_touch_anchors.text=="0 0 0 0 0 0 0 0 400 100 500 200 0 0 0 0");
czm_fort_mask.value=0;Touch_CzmPublishAnchors();
assert(props->finger==-1&&laser->finger==-1&&!laser->latched&&commands.empty());
assert(fire->finger==9&&jump->finger==10&&skill->finger==11);
czm_skill_mask.value=0;Touch_CzmPublishAnchors();
assert(skill->finger==-1&&commands.size()==1&&commands[0]=="-czm_skill_e\n");
Touch_CzmPublishAnchors();assert(commands.size()==1);
czm_fort_mask.value=3;assert(Touch_IsVisible(props)&&Touch_IsVisible(laser));
// Manual hiding after a press also clears the finger without sending a second placement.
props->finger=17;props->flags=TOUCH_FL_HIDE;Touch_CzmPublishAnchors();
assert(props->finger==-1&&commands.size()==1);
return 0;}
''')


CLIENT_STUB = r'''
#include <cassert>
#include <map>
#include <string>
#include <cstring>
#include <cmath>
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
void CZM_SkillsFrame();void CZM_SkillsReset();void CZM_ClipReset();
'''


ENGINE_STUB = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
typedef bool qboolean;typedef unsigned char byte;
int stringComparisons=0;
int CountCompare(const char *a,const char *b){stringComparisons++;return strcmp(a,b);}
#define Q_strcmp CountCompare
#define Q_snprintf snprintf
#define TO_SCRN_X(x) ((x)*1000)
#define TO_SCRN_Y(y) ((y)*500)
#define FBitSet(v,b) ((v)&(b))
enum{TOUCH_FL_HIDE=1,TOUCH_FL_CLIENT=2,TOUCH_FL_MP=4,TOUCH_FL_SP=8,state_edit=1,ca_active=2};
struct touch_button_t{
float x1,y1,x2,y2,aspect;char name[32],command[256],texture[256];byte color[4];
int flags=0,finger=-1;bool latched=false;touch_button_t *next=nullptr;
};
struct List{touch_button_t *first=nullptr,*last=nullptr;};
struct{List list_user;bool config_loaded=false,configchanged=false,clientonly=false;int state=0;}touch;
struct{int state=ca_active;}cls;struct{int maxclients=32;}cl;
struct{double realtime=0;}host;
struct Cvar{float value=0;std::string text;const char *string="";};
Cvar czm_skill_mask,czm_fort_mask,czm_touch_anchors;
std::vector<std::string> commands;
void Cvar_DirectFullSet(Cvar *c,const char *s,unsigned flags){assert(flags==0);c->text=s;c->string=c->text.c_str();}
void Touch_AddButtonCommand(const touch_button_t*,const char *s){commands.push_back(s);}
bool Touch_CzmLeftFireHidden(touch_button_t*){return false;}
float touchAspect=.5f;float Touch_AspectRatio(){return touchAspect;}
touch_button_t *Touch_AddButton(List *l,const char *name,const char *texture,const char *command,
float x1,float y1,float x2,float y2,byte *color,bool){
// Match the engine's replace-by-name semantics, so a migration collision destroys the sentinel.
touch_button_t *button=nullptr;
for(auto b=l->first;b;b=b->next)if(!strcmp(b->name,name)){button=b;break;}
if(!button){button=new touch_button_t();if(l->last)l->last->next=button;else l->first=button;l->last=button;}
strcpy(button->name,name);strcpy(button->texture,texture);strcpy(button->command,command);
button->x1=x1;button->y1=y1;button->x2=x2;button->y2=y2;memcpy(button->color,color,4);return button;
}
int Count(){int count=0;for(auto b=touch.list_user.first;b;b=b->next)count++;return count;}
touch_button_t *ByCommand(const char *command){
for(auto b=touch.list_user.first;b;b=b->next)if(!strcmp(b->command,command))return b;return nullptr;
}
bool ClearOfOtherControls(const touch_button_t *fort){
if(fort->x1<0||fort->y1<0||fort->x2>.98f||fort->y2>.98f)return false;
for(auto b=touch.list_user.first;b;b=b->next){
    if(b==fort||b->x2<=b->x1||b->y2<=b->y1)continue;
    if(!strcmp(b->command,"_move")||!strcmp(b->command,"_look")||!strcmp(b->command,"_joy")||!strcmp(b->command,"_dpad"))continue;
    if(!strcmp(b->command,"czm_skill_g")||!strcmp(b->command,"czm_skill_r")||!strcmp(b->command,"+czm_skill_e"))continue;
    const float gapX=.008f,gapY=.008f/touchAspect;
    if(fort->x1 < b->x2+gapX&&fort->x2+gapX > b->x1&&fort->y1 < b->y2+gapY&&fort->y2+gapY > b->y1)return false;
}
return true;
}
'''


if __name__ == "__main__":
    unittest.main()
