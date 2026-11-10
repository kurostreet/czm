/* Reliable server messages; local clocks only interpolate a reported remaining duration. */
#include "hud.h"
#include "cl_util.h"
#include "parsemsg.h"
#include "czm_skills.h"
#include "../../common/czm_combat.h"
#include <cstring>
#include <algorithm>
static CzmCombat::State s_skill;
// Real time of the last CzmSkill. The client clock (cl.time) can step back a little
// while the engine re-synchronises with the server; real time never does.
static double s_received;
static bool s_receivedState;
static unsigned char s_clips[31];
static bool s_unlimited;

static int MsgFunc_CzmSkill(const char *name,int size,void *buffer) {
    if(size!=11)return 1;
    BufferReader reader(name,buffer,size);
    if(reader.ReadByte()!=1)return 1;
    CzmCombat::State value;
    value.klass=reader.ReadByte();value.flags=reader.ReadByte();value.primary=reader.ReadShort();
    value.secondary=reader.ReadShort();value.charge=reader.ReadShort();value.active=reader.ReadShort();
    char text[96];std::snprintf(text,sizeof(text),"%d %d %d %d %d %d",value.klass,value.flags,value.primary,value.secondary,value.charge,value.active);
    if(!CzmCombat::Parse(text,s_skill))return 1;
    s_received=gEngfuncs.GetAbsoluteTime();
    s_receivedState=true;
    CZM_SkillsFrame();return 1;
}
static int MsgFunc_CzmClip(const char *name,int size,void *buffer) {
    if(size!=33)return 1;
    BufferReader reader(name,buffer,size);
    if(reader.ReadByte()!=1)return 1;
    for(int i=0;i<31;i++)s_clips[i]=reader.ReadByte();
    s_unlimited=reader.ReadByte()==1;return 1;
}
void CZM_SkillsInit() {
    gEngfuncs.pfnHookUserMsg("CzmSkill",MsgFunc_CzmSkill);
    gEngfuncs.pfnHookUserMsg("CzmClip",MsgFunc_CzmClip);
    CZM_ClipReset();
    CZM_SkillsReset();
}
void CZM_SkillsReset() {
    s_skill=CzmCombat::State();s_received=0;s_receivedState=false;
    gEngfuncs.Cvar_Set("czm_skill_mask","0");gEngfuncs.Cvar_Set("czm_skill_state","");
    gEngfuncs.Cvar_Set("czm_fort_mask","0");
}
void CZM_ClipReset() {std::memset(s_clips,0,sizeof(s_clips));s_unlimited=false;}
void CZM_SkillsFrame() {
    CzmCombat::State value=s_skill;
    // A dead or spectating player never keeps controls from their last life.
    if(gHUD.m_fPlayerDead||gHUD.m_iIntermission||g_iUser1){s_skill=CzmCombat::State();value=s_skill;s_receivedState=false;}
    const float age=(float)(gEngfuncs.GetAbsoluteTime()-s_received);
    // Only a missing server heartbeat (1 s) hides the controls. Measuring with cl.time
    // hid both fortification buttons whenever the clock stepped back, until the next
    // heartbeat: the blinking Laser and Props. Map changes and new lives reset the
    // state through CZM_SkillsReset.
    if(age<0.f || age>3.f)s_receivedState=false;
    int elapsed=(int)std::fmax(0.f,age*10.f);
    value.primary=std::max(0,value.primary-elapsed);value.secondary=std::max(0,value.secondary-elapsed);
    value.charge=std::max(0,value.charge-elapsed);value.active=std::max(0,value.active-elapsed);
    char text[96],mask[8],fort[8];std::snprintf(text,sizeof(text),"%d %d %d %d %d %d",value.klass,value.flags,value.primary,value.secondary,value.charge,value.active);
    std::snprintf(mask,sizeof(mask),"%d",CzmCombat::Mask(value.klass));
    std::snprintf(fort,sizeof(fort),"%d",s_receivedState?CzmCombat::FortificationMask(value):0);
    if(std::strcmp(gEngfuncs.pfnGetCvarString("czm_skill_state"),text))gEngfuncs.Cvar_Set("czm_skill_state",text);
    if(std::strcmp(gEngfuncs.pfnGetCvarString("czm_skill_mask"),mask))gEngfuncs.Cvar_Set("czm_skill_mask",mask);
    if(std::strcmp(gEngfuncs.pfnGetCvarString("czm_fort_mask"),fort))gEngfuncs.Cvar_Set("czm_fort_mask",fort);
}
int CZM_ClipCapacity(int weapon,int fallback) {return weapon>0&&weapon<31&&s_clips[weapon]?s_clips[weapon]:fallback;}
bool CZM_UnlimitedReserve(){return s_unlimited;}
