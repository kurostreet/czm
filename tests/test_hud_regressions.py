"""Execute the live-peer gate, editor/game aim geometry and Money message/draw lifecycle."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]


def run_cpp(code):
    with tempfile.TemporaryDirectory(prefix="czm-hud-regression-") as folder:
        path = Path(folder)
        (path / "check.cpp").write_text(code)
        subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-Wno-unused-variable", "-I" + str(ROOT / "common"),
                        str(path / "check.cpp"), "-o", str(path / "check")], check=True)
        subprocess.run([str(path / "check")], check=True)


class HudRegressionTests(unittest.TestCase):
    def test_new_connection_resets_lvl_data_even_when_the_map_does_not_change(self):
        source = (ROOT / "cl_dll/hud_msg.cpp").read_text()
        entry = function(source, "int CHud :: MsgFunc_InitHUD(")
        entry = entry[:entry.index("\tg_iFreezeTimeOver = 0;")] + "return 1;\n}"
        run_cpp(r'''
#include <cassert>
static int tagResets=0,widgetResets=0,clipResets=0,ammoResets=0,voteResets=0;
void CZM_TagsReset(){tagResets++;}
void CZM_VoteReset(){voteResets++;}
void CZM_ClipReset(){clipResets++;}
void CZM_AmmoReset(){ammoResets++;}
struct Widget {void InitHUDData(){widgetResets++;}};
struct HUDLIST {Widget *p;HUDLIST *pNext;};
struct CHud {HUDLIST *m_pHudList;int MsgFunc_InitHUD(const char *,int,void *);};
''' + entry + r'''
int main(){Widget widget;HUDLIST first={&widget,nullptr};CHud hud={&first};
hud.MsgFunc_InitHUD("InitHUD",0,nullptr);hud.MsgFunc_InitHUD("InitHUD",0,nullptr);
assert(tagResets==2&&widgetResets==2&&clipResets==2&&ammoResets==2&&voteResets==2);}
''')

    def test_live_peer_and_configured_ownership_control_all_lvl_overlays(self):
        source = (ROOT / "cl_dll/hud/czm_tags.cpp").read_text()
        code = r'''
#include "czm_hud_scope.h"
#include "czm_hud_layout.h"
#include <cassert>
#include <cstdlib>
typedef unsigned char byte;
struct netadr_t { char address[64]; };
struct net_status_t { bool connected; netadr_t remote_address; };
static bool connected=true,hidden=false,s_aimShown=false;
static const char *peer="203.0.113.44:27015",*cache="",*staleMenuAddress="194.226.112.249:27016";
void Status(net_status_t *s){s->connected=connected;snprintf(s->remote_address.address,64,"%s",peer);}
int Parse(char *s,netadr_t *a){snprintf(a->address,64,"%s",s);return 1;}
int Compare(netadr_t *a,netadr_t *b){return !strcmp(a->address,b->address);}
struct net_api_t {void(*Status)(net_status_t *);int(*StringToAdr)(char *,netadr_t *);int(*CompareAdr)(netadr_t *,netadr_t *);};
net_api_t api={Status,Parse,Compare};
byte *Load(const char *name,int,int *length){assert(!strcmp(name,"official_servers.lst"));*length=strlen(cache);byte *p=(byte*)malloc(*length);memcpy(p,cache,*length);return p;}
struct Engine {net_api_t *pNetAPI;byte *(*COM_LoadFile)(const char *,int,int *);void(*COM_FreeFile)(void *);};
Engine gEngfuncs={&api,Load,free};
struct Hud {float m_flTime;};Hud gHUD={0};
float CZM_HudValue(int,const char *,float){return hidden?1:0;}
static int s_progress,progressDraws,aimDraws,toastDraws;
void CZM_ProgressDraw(int){progressDraws++;}
void DrawAimTag(){aimDraws++;s_aimShown=true;}
void DrawToasts(float){toastDraws++;}
'''
        code += function(source, "static bool OnLvlServer(")
        code += function(source, "bool CZM_AimTagShown(")
        code += function(source, "void CZM_TagsDraw(")
        code += r'''
int main(){
 assert(!OnLvlServer());
 cache="0 194.226.112.249:27016 -\n";gHUD.m_flTime+=3;
 assert(!OnLvlServer()); // stale menu address and a foreign peer must not enable our card
 peer=staleMenuAddress;assert(OnLvlServer()); // the promotion switch is independent of ownership
 CZM_TagsDraw(0);assert(progressDraws==1&&aimDraws==1&&toastDraws==1&&CZM_AimTagShown());
 hidden=true;assert(!CZM_AimTagShown());hidden=false;
 peer="203.0.113.44:27015";assert(!CZM_AimTagShown());CZM_TagsDraw(0);
 assert(!s_aimShown&&progressDraws==1&&aimDraws==1&&toastDraws==1);
 peer=staleMenuAddress;connected=false;assert(!OnLvlServer());connected=true;
 cache="1 - [2001:db8::1]:27015";gHUD.m_flTime+=3;assert(!OnLvlServer());
 peer="[2001:db8::1]:27015";assert(OnLvlServer());
 for(const char *bad:{"","1","1 only-one","2 194.226.112.249:27016 -","1 say;/menu -"}){
   cache=bad;gHUD.m_flTime+=3;assert(!OnLvlServer());
 }
 cache="1 194.226.112.249:27016 -";peer=staleMenuAddress;gHUD.m_flTime=0;
 assert(OnLvlServer()); // a new map's clock cannot keep an old cached decision
}
'''
        run_cpp(code.replace('#include <cstdlib>', '#include <cstdlib>\n#include <initializer_list>'))

    def test_aim_card_fits_its_movable_frame_for_long_names_and_unknown_or_large_hp(self):
        run_cpp(r'''
#include "czm_hud_overlay.h"
#include <cassert>
#include <climits>
#include <cmath>
#include <initializer_list>
struct Check:CzmHud::Canvas {
 CzmHud::Rect p;int lh;Check(CzmHud::Rect rect,int height):p(rect),lh(height){}
 void Inside(float x,float y,float w,float h){assert(std::isfinite(x+y+w+h)&&w>=0&&h>=0&&x>=p.x-1&&y>=p.y-1&&x+w<=p.x+p.w+1&&y+h<=p.y+p.h+1);}
 void Blend(int x,int y,int w,int h,int,int,int,int a)override{assert(a>=0&&a<=255);Inside(x,y,w,h);}
 void Glyphs(float x,float y,float h,const char *s,int,int,int,float a)override{assert(h>0&&a>=0&&a<=1);Inside(x,y,CzmHud::GlyphWidth(s,h),h);}
 int LabelWidth(const char *s)override{int n=0;for(;*s;s++)if((*s&0xc0)!=0x80)n++;return n*lh/2;}
 int LabelHeight()override{return lh;}
 void Label(int x,int y,const char *s,int,int,int)override{Inside(x,y,LabelWidth(s),lh);}
 bool Avatar(int,int,int)override{return false;}
};
int main(){
 const float screens[][2]={{640,360},{1536,716},{2340,1080},{1024,768},{2000,1200}};
 const float places[]={-1,0,.3f,.7f,1,4,NAN},scales[]={0,.65f,1,1.6f,8,NAN};
 CzmHud::AimInfo states[]={
  {"Kuro","","",37,65,3089,8000,0,255,255,false},
  {"Цель с очень длинным именем 🚀 very very long name","Очень длинный префикс","PREMIUM",INT_MAX,100,INT_MAX,INT_MAX,255,150,0,false},
  {"Bot","","",-1,0,-1,0,0,0,0,false},
  {"Classic player","","",1,0,73,100,0,0,0,true}};
 for(auto &s:screens)for(float x:places)for(float scale:scales)for(int lh:{8,18,26,40})for(auto &state:states){
  auto p=CzmHud::AimLayout(s[0],s[1],x,x,scale,.25f,lh);
  assert(p.x>=0&&p.y>=0&&p.x+p.w<=s[0]+1&&p.y+p.h<=s[1]+1);
  Check c(p,lh);CzmHud::PaintAim(c,p,state,0,255,255);
 }
}
''')

    def test_editor_and_game_use_the_same_saved_aim_frame_and_hide_toggle(self):
        overlay = (ROOT / "cl_dll/hud/czm_overlay.cpp").read_text()
        editor = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        code = r'''
#include "czm_hud_overlay.h"
#include "czm_hud_paint.h"
#include <cassert>
#include <cmath>
static int ScreenWidth=1536,ScreenHeight=716,g_iUser1=0;
static bool ready=true,hidden=false;static float px=.25f,py=.8f,scale=1,alpha=.5f;
static CzmHud::Rect drawn;static int paints=0;
bool CZM_HudReady(){return ready;}
float CZM_HudValue(int kind,const char *field,float){assert(kind==CzmHud::AIM);return !strcmp(field,"hidden")?hidden:!strcmp(field,"x")?px:!strcmp(field,"y")?py:!strcmp(field,"scale")?scale:alpha;}
void Clean(const char *s,char *out,size_t n){snprintf(out,n,"%s",s?s:"");}
void CZM_LevelColor(int,int *r,int *g,int *b){*r=0;*g=*b=255;}
struct GameCanvas:CzmHud::Canvas {
 void Blend(int x,int y,int w,int h,int,int,int,int)override{if(!paints++)drawn={(float)x,(float)y,(float)w,(float)h,1,1};}
 void Glyphs(float,float,float,const char *,int,int,int,float)override{}
 int LabelWidth(const char *s)override{return strlen(s)*8;}
 int LabelHeight()override{return 18;}
 void Label(int,int,const char *,int,int,int)override{}
 bool Avatar(int,int,int)override{return false;}
};
struct CzmHudBlock {float x,y,scale,opacity;bool hidden;};
enum{CZMF_SMALL};int CZM_Font(int){return 0;}int CZM_FontHeight(int){return 18;}
float ChatLineHeight(int){return 18;}
class CCzmTouchEditor {public:int W=1536,H=716,m_iHudStyle=0;CzmHudBlock m_hud[CzmHud::BLOCKS];CzmHud::Rect HudLayout(int kind)const;};
'''
        code += function(overlay, "bool CZM_AimDraw(")
        code += function(editor, "CzmHud::Rect CCzmTouchEditor::HudLayout(")
        code += r'''
int main(){
 CCzmTouchEditor editor;
 CzmHud::AimInfo info={"Kuro","","",37,65,3089,8000,0,255,255,false};
 for(float x:{.01f,.3f,.8f,.99f})for(float size:{.65f,1.f,1.6f}){
  px=x;py=1-x;scale=size;editor.m_hud[CzmHud::AIM]={px,py,scale,alpha,false};
  auto expected=editor.HudLayout(CzmHud::AIM);paints=0;assert(CZM_AimDraw(info)&&paints>0);
  assert(fabs(drawn.x-expected.x)<1&&fabs(drawn.y-expected.y)<1&&fabs(drawn.w-expected.w)<1&&fabs(drawn.h-expected.h)<1);
 }
 for(int mode=0;mode<3;mode++){
  hidden=mode==0;ready=mode!=1;g_iUser1=mode==2;paints=0;
  assert(!CZM_AimDraw(info)&&paints==0);
 }
}
'''
        run_cpp(code.replace('#include <cmath>', '#include <cmath>\n#include <initializer_list>'))

    def test_aim_card_shows_no_placeholders_and_needs_server_data(self):
        run_cpp(r'''
#include "czm_hud_overlay.h"
#include <cassert>
#include <cstring>
#include <string>
struct Text:CzmHud::Canvas {
 std::string all;
 void Blend(int,int,int,int,int,int,int,int)override{}
 void Glyphs(float,float,float,const char *s,int,int,int,float)override{all+=s;all+="|";}
 int LabelWidth(const char *s)override{return (int)strlen(s)*6;}
 int LabelHeight()override{return 12;}
 void Label(int,int,const char *s,int,int,int)override{all+=s;all+="|";}
 bool Avatar(int,int,int)override{return false;}
};
int main(){
 auto p=CzmHud::AimLayout(1536,716,.5f,.64f,1,1,12);
 CzmHud::AimInfo unranked={"Kuro","","",-1,0,5400,5400,0,0,0,false};
 Text a;CzmHud::PaintAim(a,p,unranked,0,255,255);
 assert(a.all.find("LVL")==std::string::npos&&a.all.find("--")==std::string::npos);
 assert(a.all.find("5400 / 5400 HP")!=std::string::npos);
 CzmHud::AimInfo ranked={"Kuro","","VIP+",37,65,3089,8000,0,0,0,false};
 Text b;CzmHud::PaintAim(b,p,ranked,0,255,255);
 assert(b.all.find("LVL 37  WR 65%")!=std::string::npos&&b.all.find("VIP+")!=std::string::npos);
}
''')
        # without CzmAim and CzmTag from the server the stock status line stays, no card
        tags = (ROOT / "cl_dll/hud/czm_tags.cpp").read_text()
        aim = function(tags, "static void DrawAimTag(")
        self.assertIn("if( !s_aimReceived && !ranked )\n\t\treturn;", aim)
        self.assertLess(aim.index("if( !s_aimReceived && !ranked )"), aim.index("CZM_AimDraw( info )"))

    def test_editor_server_text_sample_follows_the_list_setting(self):
        touch = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        sample = function(touch, "static void DrawServerSample(")
        self.assertIn('EngFuncs::GetCvarFloat( "czm_hud_msg_list" ) > 0.5f', sample)
        self.assertIn("frame.h * 0.9f", sample)   # Zombie Plague status: x 0.02, y 0.9
        self.assertIn("frame.y + lineH / 2", sample)   # as a list: top left, as message.cpp

    def test_money_obeys_layout_after_zp_hide_flag_and_resets_on_new_connection(self):
        source = (ROOT / "cl_dll/hud/money.cpp").read_text()
        header = (ROOT / "cl_dll/hud.h").read_text()
        draw = function(source, "int CHudMoney::Draw(")
        # Keep the actual CZM path and the gate to the old sprite painter; sprites are covered
        # by the legacy renderer, not involved in this regression.
        draw = draw[:draw.index("\tfloat interpolate")] + "return 0;\n}"
        code = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
enum {HUD_DRAW=1,HIDEHUD_MONEY=2,HIDEHUD_ALL=4,WEAPON_SUIT=1,OBS_IN_EYE=4};
namespace CzmHud {enum{MONEY=3};}
static int g_iUser1=0,renders=0,shownMoney=-1;static bool ready=true,hidden=false,warning=false;static float moneyCvar;
bool CZM_HudNumber(int kind,int value,bool warn){assert(kind==CzmHud::MONEY);if(!ready)return false;if(!hidden){renders++;shownMoney=value;warning=warn;}return true;}
struct CHudBase {int m_iFlags=0;};struct CClientSprite {};
#define CHudMsgFunc(name) int MsgFunc_##name(const char *,int,void *)
'''
        code += function(header, "class CHudMoney : public CHudBase") + ";\n"
        code += r'''
struct Cvar {const char *name;};Cvar current={"cscl_currentmoney"};
struct Hud {int m_iHideHUDDisplay=0,m_iWeaponBits=(1<<WEAPON_SUIT);float m_flTimeDelta=.1f;Cvar *cscl_currentmoney=&current;};Hud gHUD;
void Set(const char *,float value){moneyCvar=value;}struct Engine {void(*Cvar_SetValue)(const char *,float);};Engine gEngfuncs={Set};
struct BufferReader {const byte *p;BufferReader(const char *,void *buf,int):p((const byte*)buf){}int ReadLong(){int32_t n;memcpy(&n,p,4);p+=4;return n;}int ReadByte(){return *p++;}};
'''.replace("const byte", "const unsigned char").replace("(const byte*", "(const unsigned char*")
        for signature in ["void CHudMoney::InitHUDData(", "int CHudMoney::MsgFunc_Money(", "int CHudMoney::MsgFunc_BlinkAcct("]:
            code += function(source, signature)
        code += draw
        code += r'''
int main(){
 CHudMoney money;money.InitHUDData();assert(money.GetMoney()==0&&money.m_iFlags==0&&moneyCvar==0);
 int32_t count=1250;money.MsgFunc_Money("Money",4,&count);
 assert(money.m_iFlags&HUD_DRAW);gHUD.m_iHideHUDDisplay=HIDEHUD_MONEY;
 money.Draw(0);assert(renders==1&&shownMoney==1250); // the exact ZP regression
 hidden=true;money.Draw(0);assert(renders==1);hidden=false;
 gHUD.m_iHideHUDDisplay|=HIDEHUD_ALL;money.Draw(0);assert(renders==1);
 gHUD.m_iHideHUDDisplay=0;g_iUser1=OBS_IN_EYE;money.Draw(0);assert(renders==1);g_iUser1=0;
 gHUD.m_iWeaponBits=0;money.Draw(0);assert(renders==1);gHUD.m_iWeaponBits=1<<WEAPON_SUIT;
 count=0;money.MsgFunc_Money("Money",4,&count);money.Draw(0);assert(shownMoney==0);
 count=999;money.MsgFunc_Money("Money",3,&count);assert(money.GetMoney()==0);
 count=2147483647;money.MsgFunc_Money("Money",4,&count);money.Draw(0);assert(shownMoney==count);
 unsigned char blink=1;money.MsgFunc_BlinkAcct("BlinkAcct",1,&blink);gHUD.m_flTimeDelta=.6f;
 money.Draw(0);assert(warning);money.Draw(0);money.Draw(0);assert(!warning); // custom drawing must advance the blink
 ready=false;gHUD.m_iHideHUDDisplay=HIDEHUD_MONEY;assert(money.Draw(0)==1);
 gHUD.m_iHideHUDDisplay=0;assert(money.Draw(0)==0); // still reaches stock sprites when CZM renderer is unavailable
 money.InitHUDData();assert(money.GetMoney()==0&&moneyCvar==0&&!(money.m_iFlags&HUD_DRAW));
}
'''
        run_cpp(code)


if __name__ == "__main__":
    unittest.main()
