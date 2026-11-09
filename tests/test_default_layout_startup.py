"""Execute the real new-install, restored-profile and explicit-reset paths."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]


class DefaultLayoutStartupTests(unittest.TestCase):
    def test_new_install_saved_profiles_and_both_reset_entry_points(self):
        touch = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        settings = (ROOT / "czm/menu/CzmSettings.cpp").read_text()
        layout = json.loads((ROOT / "scripts/layouts/scheme1.json").read_text())
        source = PREAMBLE
        for name in ("static void SchemePath(", "void CZM_SaveTouchConfig(",
                     "int CZM_TouchScheme(", "void CZM_SetTouchScheme(",
                     "void CZM_TouchStartup(", "static float HudField(",
                     "static CzmHudBlock HudDefault(", "static void WriteHud(",
                     "void CZM_TouchResetHud("):
            source += function(touch, name) + "\n"
        source += "void ConfirmSettingsReset() { int hit=HIT_CONFIRM_YES;\n"
        source += function(function(settings, "void CCzmSettings::Activate("),
                           "if( hit == HIT_CONFIRM_YES )") + "\n}\n"
        source += function(touch, "void CCzmTouchEditor::Load(") + "\n"
        source += "void InstallPreset(){\n"
        for scheme in (1, 2, 3):
            data = (ROOT / f"3rdparty/czm_project/touch_presets/czm_scheme{scheme}.cfg").read_text()
            source += f'files["touch_presets/czm_scheme{scheme}.cfg"]=R"preset({data})preset";\n'
        source += "}\nvoid CheckOwnerHud(){\n"
        for key, value in layout["cvars"].items():
            if key.startswith("czm_hud_"):
                source += f'assert(std::fabs(EngFuncs::GetCvarFloat("{key}")-({float(value):.6f}f))<.000002f);\n'
        source += "}\n" + SCENARIO
        with tempfile.TemporaryDirectory(prefix="czm-default-layout-") as folder:
            path = Path(folder)
            (path / "default.cpp").write_text(source)
            subprocess.run(["g++", "-std=c++11", "-I" + str(ROOT / "common"),
                            str(path / "default.cpp"), "-o", str(path / "default")], check=True)
            subprocess.run([str(path / "default")], check=True)


PREAMBLE = r'''
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <map>
#include <string>
#include <vector>
#include "czm_hud_layout.h"
#define CZM_SCHEMES 3
#define HUD_BLOCKS CzmHud::BLOCKS
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
template<class T>T bound(T a,T v,T b){return v<a?a:v>b?b:v;}
struct CzmHudBlock {float x,y,scale,opacity;bool hidden;};
static std::map<std::string,std::string> files,cvars;
static std::vector<std::string> commands;
static std::string live;
static bool m_bConfirm=true;
enum {HIT_CONFIRM_YES=12};
static int hudReads=0;
static void CZM_PlayClick(){}
static void Toast(const char*){}
void CZM_TouchResetHud();
namespace EngFuncs {
bool FileExists(const char *path,bool){return files.count(path)!=0;}
const char *GetCvarString(const char *key){return cvars[key].c_str();}
float GetCvarFloat(const char *key){return cvars.count(key)?std::stof(cvars[key]):0;}
void CvarSetString(const char *key,const char *value){cvars[key]=value;}
void CvarSetValue(const char *key,float value){char b[32];snprintf(b,sizeof(b),"%.6f",value);cvars[key]=b;}
void ClientCmd(bool,const char *command){
    commands.push_back(command);
    char path[128];
    if(sscanf(command,"exec \"%127[^\"]\"",path)==1||sscanf(command,"exec %127s",path)==1){
        assert(files.count(path));live=files[path];
    }else if(sscanf(command,"touch_exportconfig \"%127[^\"]\"",path)==1){
        files[path]=live;
    }
}
void ClientCmdF(bool execute,const char *format,...){
    char b[256];va_list args;va_start(args,format);vsnprintf(b,sizeof(b),format,args);va_end(args);
    ClientCmd(execute,b);
}
}
static void ReadHud(CzmHudBlock*,int*,int*,int*){hudReads++;}
class CCzmTouchEditor {
public:
int m_iScheme=0,m_iSelected=4,m_iHudSelected=5;
bool m_bDirty=true;
CzmHudBlock m_hud[HUD_BLOCKS];
int m_iHudStyle,m_iRadarStyle,m_iMsgStyle;
std::string parsed;
bool Parse(const char *path){parsed=files[path];return true;}
void Load(int scheme,bool fromPreset);
};
'''


SCENARIO = r'''
std::string Path(int slot){return "touch_profiles/czm_scheme"+std::to_string(slot)+".cfg";}
void Fresh(){
    files.clear();cvars.clear();commands.clear();live="stock controls";InstallPreset();
    cvars["czm_touch_scheme"]="1";cvars["czm_touch_version"]="0";
    cvars["czm_hud_hp_x"]="0.19";cvars["czm_hud_style"]="2";
}
int main(){
    // A genuinely new installation receives the uploaded defaults once.
    Fresh();CZM_TouchStartup();CheckOwnerHud();
    const std::string owner=files["touch_presets/czm_scheme1.cfg"];
    assert(files[Path(1)]==owner&&live==owner);
    assert(EngFuncs::GetCvarFloat("czm_touch_version")==1);
    live="new player's changes";files[Path(1)]=live;cvars["czm_hud_hp_x"]="0.24";
    auto before=files;auto vars=cvars;commands.clear();CZM_TouchStartup();
    assert(files==before&&cvars==vars&&commands.empty());

    // Every existing player's active slot and HUD survive an app upgrade.
    for(int selected=1;selected<=3;selected++){
        Fresh();for(int slot=1;slot<=3;slot++)files[Path(slot)]="my controls "+std::to_string(slot);
        cvars["czm_touch_scheme"]=std::to_string(selected);cvars["czm_touch_version"]="1";
        before=files;vars=cvars;commands.clear();CZM_TouchStartup();
        assert(files==before&&cvars==vars&&commands.empty());

        // Restored files can have lost the startup marker. Their saved active
        // slot still wins over the new preset, including its custom HUD.
        cvars["czm_touch_version"]="0";const auto hud=cvars["czm_hud_hp_x"];
        CZM_TouchStartup();assert(files==before&&live==before[Path(selected)]);
        assert(cvars["czm_hud_hp_x"]==hud&&cvars["czm_hud_style"]=="2");
        assert(EngFuncs::GetCvarFloat("czm_touch_scheme")==selected);
    }
    // If the selected slot is absent, preserve another restored profile rather
    // than overwriting that profile and the HUD with default scheme1.
    for(int saved=1;saved<=3;saved++){
        Fresh();files[Path(saved)]="restored controls";cvars["czm_touch_scheme"]=std::to_string(saved%3+1);
        before=files;CZM_TouchStartup();
        assert(files==before&&live=="restored controls");
        assert(cvars["czm_hud_hp_x"]=="0.19"&&cvars["czm_hud_style"]=="2");
        assert(EngFuncs::GetCvarFloat("czm_touch_scheme")==saved);
    }
    // Explicit resets from Settings and from the editor use the uploaded
    // scheme1 in the selected slot; the other two saved slots stay intact.
    for(int entry=0;entry<2;entry++)for(int selected=1;selected<=3;selected++){
        Fresh();for(int slot=1;slot<=3;slot++)files[Path(slot)]="my controls "+std::to_string(slot);
        cvars["czm_touch_scheme"]=std::to_string(selected);cvars["czm_touch_version"]="1";
        before=files;
        if(entry==0){m_bConfirm=true;ConfirmSettingsReset();assert(!m_bConfirm);}
        else{CCzmTouchEditor editor;editor.Load(selected,true);assert(editor.parsed==owner);}
        assert(files[Path(selected)]==owner&&live==owner);CheckOwnerHud();
        for(int slot=1;slot<=3;slot++)if(slot!=selected)assert(files[Path(slot)]==before[Path(slot)]);
        assert(EngFuncs::GetCvarFloat("czm_touch_scheme")==selected);
    }
    // Simply opening an existing slot in the editor is not a reset.
    Fresh();files[Path(2)]="custom slot2";before=files;
    CCzmTouchEditor editor;editor.Load(2,false);
    assert(files==before&&editor.parsed=="custom slot2");
    assert(cvars["czm_hud_hp_x"]=="0.19"&&cvars["czm_hud_style"]=="2");
}
'''


if __name__ == "__main__":
    unittest.main()
