"""Draw real editor buttons and selected previews from saved texture paths."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]


class NativeTouchTextureTests(unittest.TestCase):
    def test_layout_handoff_exports_live_profile_before_config_and_java(self):
        touch = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        net = (ROOT / "czm/menu/CzmNet.cpp").read_text()
        code = HANDOFF_PREAMBLE
        code += function(touch, "void CZM_SaveTouchConfig(") + "\n"
        code += function(net, "void CZM_LayoutsShow(") + "\n"
        code += HANDOFF_SCENARIO
        with tempfile.TemporaryDirectory(prefix="czm-layout-handoff-") as folder:
            path = Path(folder)
            (path / "handoff.cpp").write_text(code)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra",
                            str(path / "handoff.cpp"), "-o", str(path / "handoff")], check=True)
            subprocess.run([str(path / "handoff")], check=True)

    def test_saved_png_and_extensionless_icons_draw_without_changing_controls(self):
        source = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        button = re.search(r"struct CzmTouchButton\s*\{.*?\n\};", source, re.S).group(0)
        code = PREAMBLE + button + "\n"
        code += function(source, "static void ButtonTexturePath(") + "\n"
        code += function(source, "static bool ButtonEditable(") + "\n"
        code += EDITOR
        code += function(source, "void CCzmTouchEditor::DrawButtons(") + "\n"
        code += function(source, "void CCzmTouchEditor::DrawPanel(") + "\n"
        code += SCENARIO
        with tempfile.TemporaryDirectory(prefix="czm-touch-texture-") as folder:
            path = Path(folder)
            (path / "editor.cpp").write_text(code)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra",
                            str(path / "editor.cpp"), "-o", str(path / "editor")], check=True)
            subprocess.run([str(path / "editor")], check=True)
        for icon in ("props", "lasermine", "skill_g", "skill_r", "skill_e", "fire"):
            self.assertTrue((ROOT / "3rdparty/czm_project/gfx/czm/touch" / (icon + ".png")).is_file())


PREAMBLE = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <strings.h>
#include <string>
#include <vector>
#define stricmp strcasecmp
#define UI_DIR "gfx/czm/ui/"
enum { TOUCH_FLAG_HIDE=1, TOUCH_FLAG_NOEDIT=2, HUD_BLOCKS=0,
       CZMF_SMALL, CZMF_NICK, CZMF_TILE_STATUS, QM_CENTER,
       HIT_HIDE, HIT_ICON, HIT_COMMAND, HIT_DELETE };
typedef int HFont;
struct CzmRect { int x=0,y=0,w=96,h=96; };
struct Image { std::string path; int x,y,w,h; };
static std::vector<Image> images;
static void CZM_DrawImage(const char *path,int x,int y,int w,int h,int=255){
    images.push_back({path,x,y,w,h});
}
static HFont CZM_Font(int){return 1;}
static int CZM_FontHeight(HFont){return 12;}
static int PackRGBA(int,int,int,int){return 255;}
static int CZM_White(int=255){return 255;}
static bool CZM_IsRussian(){return false;}
static void CZM_DrawPanel(const CzmRect&){}
template<class... A> static void CZM_DrawText(A...){}
template<class... A> static void CZM_DrawButton(A...){}
'''

EDITOR = r'''
static const char *ButtonLabel(const CzmTouchButton &b){return b.command;}
class CCzmTouchEditor {
public:
    CzmTouchButton m_buttons[16] = {};
    int m_iButtons=0,m_iSelected=-1,H=716;
    bool m_bShowHidden=false;
    int m_conflict[16];
    CzmRect m_panel,m_size,m_opacity,m_hide,m_icon,m_command,m_delete;
    CCzmTouchEditor(){for(int &v:m_conflict)v=-1;}
    CzmRect ButtonRect(int i)const{
        CzmRect r;const CzmTouchButton &b=m_buttons[i];
        r.x=b.x1*1536;r.y=b.y1*716;r.w=(b.x2-b.x1)*1536;r.h=(b.y2-b.y1)*716;
        return r;
    }
    int ConflictColor(int a){return a;}
    void DrawReloadPreview(const CzmRect&){}
    float ButtonSize(int i){return m_buttons[i].x2-m_buttons[i].x1;}
    const char *ItemName(int){return "button";}
    void DrawSlider(const CzmRect&,float,const char*,const char*){}
    bool IsPressed(int){return false;}
    void DrawButtons();void DrawPanel();
};
'''

SCENARIO = r'''
int main(){
    CCzmTouchEditor editor;
    const char *icons[]={"props","lasermine","skill_g","skill_r","skill_e","fire"};
    const char *commands[]={"czm_props","czm_lasermine","czm_skill_g","czm_skill_r","+czm_skill_e","+attack"};
    std::vector<std::string> expected;
    for(int icon=0;icon<6;icon++)for(int suffix=0;suffix<2;suffix++){
        int i=editor.m_iButtons++;
        CzmTouchButton &b=editor.m_buttons[i];
        std::snprintf(b.name,sizeof(b.name),"saved_%d",i);
        std::snprintf(b.texture,sizeof(b.texture),"gfx/czm/touch/%s%s",icons[icon],suffix?".png":"");
        std::snprintf(b.command,sizeof(b.command),"%s",commands[icon]);
        b.x1=.02f+i*.07f;b.y1=.55f;b.x2=b.x1+.06f;b.y2=.68f;
        b.color[0]=19;b.color[1]=29;b.color[2]=39;b.color[3]=235;
        expected.push_back(std::string("gfx/czm/touch/")+icons[icon]+".png");
    }
    CzmTouchButton saved[16];std::memcpy(saved,editor.m_buttons,sizeof(saved));
    editor.DrawButtons();
    assert(images.size()==expected.size());
    for(int i=0;i<editor.m_iButtons;i++){
        assert(images[i].path==expected[i]);
        assert(images[i].x==editor.ButtonRect(i).x&&images[i].y==editor.ButtonRect(i).y);
    }
    for(int i=0;i<editor.m_iButtons;i++){
        images.clear();editor.m_iSelected=i;editor.DrawPanel();
        assert(images.size()==1&&images[0].path==expected[i]);
    }
    // Explicit extensions keep their spelling; path resolution never rewrites saved controls.
    CzmTouchButton mixed={};std::strcpy(mixed.texture,"gfx/custom/icon.PNG");
    char path[96];ButtonTexturePath(mixed,path,sizeof(path));
    assert(!std::strcmp(path,mixed.texture));
    assert(editor.m_iButtons==12&&!std::memcmp(saved,editor.m_buttons,sizeof(saved)));
}
'''

HANDOFF_PREAMBLE = r'''
#include <cassert>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <string>
#include <vector>
typedef int jclass;
typedef int jmethodID;
typedef int jint;
static bool beginOk=true,methodOk=true;
static int selectedScheme=2,begins=0,ends=0;
static std::string profile="touch_profiles/czm_scheme2.cfg";
static const std::string hud="czm_hud_aim_x=0.31;czm_hud_radar_y=0.27";
static std::vector<std::string> calls;
struct JNIEnv {
    void CallStaticVoidMethod(jclass cls,jmethodID method,jint scheme){
        assert(cls==1&&method==2&&scheme==selectedScheme);
        calls.push_back("java:"+std::to_string(scheme));
    }
};
static JNIEnv java;
static bool CZM_Begin(JNIEnv **env,jclass *cls){
    begins++;if(!beginOk)return false;*env=&java;*cls=1;return true;
}
static jmethodID CZM_Method(JNIEnv *env,jclass cls,const char *name,const char *signature){
    assert(env==&java&&cls==1&&!std::strcmp(name,"layoutsShow")&&!std::strcmp(signature,"(I)V"));
    return methodOk?2:0;
}
static void CZM_End(JNIEnv *env){assert(env==&java);ends++;}
static int CZM_TouchScheme(){return selectedScheme;}
static void Q_strncpy(char *out,const char *value,size_t size){std::snprintf(out,size,"%s",value);}
namespace EngFuncs {
static const char *GetCvarString(const char *name){assert(!std::strcmp(name,"touch_config_file"));return profile.c_str();}
static void ClientCmd(bool execute,const char *text){assert(execute);calls.push_back(text);}
static void ClientCmdF(bool execute,const char *format,...){
    assert(execute);char text[256];va_list args;va_start(args,format);
    std::vsnprintf(text,sizeof(text),format,args);va_end(args);calls.push_back(text);
}
}
'''

HANDOFF_SCENARIO = r'''
int main(){
    const std::string originalHud=hud;
    beginOk=false;CZM_LayoutsShow();assert(calls.empty()&&begins==1&&ends==0);
    beginOk=true;methodOk=false;CZM_LayoutsShow();assert(calls.empty()&&begins==2&&ends==1);
    methodOk=true;
    for(int scheme=1;scheme<=3;scheme++){
        selectedScheme=scheme;profile="touch_profiles/czm_scheme"+std::to_string(scheme)+".cfg";
        std::string originalProfile=profile;calls.clear();
        CZM_LayoutsShow();
        std::vector<std::string> expected={"touch_exportconfig \""+profile+"\"\n",
            "host_writeconfig\n","java:"+std::to_string(scheme)};
        assert(calls==expected&&selectedScheme==scheme&&profile==originalProfile&&hud==originalHud);
    }
    assert(begins==5&&ends==4);
}
'''


if __name__ == "__main__":
    unittest.main()
