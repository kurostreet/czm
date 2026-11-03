"""The wheel previews the server's current skin, updates it, and rejects paths from player info."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include "czm_player_model.h"
#include <cassert>
#include <map>
#include <string>
#define MAX_PLAYERS 32
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
#define strlcpy Q_strncpy
static std::map<std::string,std::string> values;
static const char *serverModel="czm_professional";
struct cl_entity_t { int index=7;void *model=nullptr; } localEntity,previewEntity;
struct hud_player_info_t { const char *model; };
void GetPlayerInfo(int index,hud_player_info_t *info){assert(index==7);info->model=serverModel;}
bool CL_IsDead(){return false;}
int g_iTeamNumber=2;
struct Money { int GetMoney(){return 100;} };
struct Battery { int GetArmor(){return 100;}bool HasHelmet(){return true;} };
struct { Money m_Money;Battery m_Battery;unsigned int m_iWeaponBits=1; } gHUD;
struct {
 cl_entity_t *GetLocalPlayer(){return &localEntity;}
 const char *pfnGetCvarString(const char *key){return values[key].c_str();}
 void Cvar_Set(const char *key,const char *value){values[key]=value;}
} gEngfuncs;
enum { QMF_DISABLESCAILING=1,QMF_INACTIVE=2 };
struct CzmRect { int x,y,w,h; };
struct Color { void SetDefault(int){} };
static int loads,draws,inits;static bool exists=true;
struct CMenuPlayerModelView {
 enum { PMV_SHOWMODEL=1 };
 cl_entity_t *ent=nullptr;unsigned iFlags=0;bool m_bCanCaptureFocus=true;int eOverrideMode=0,iStrokeWidth=1;
 Color backgroundColor,colorStroke;
 void SetRect(int,int,int,int){}
 void VidInit(){inits++;ent=&previewEntity;ent->model=nullptr;}
 void Draw(){assert(!m_bCanCaptureFocus&&eOverrideMode==PMV_SHOWMODEL);draws++;}
};
namespace EngFuncs {
 const char *GetCvarString(const char *key){return values[key].c_str();}
 bool FileExists(const char *){return exists;}
 void SetModel(cl_entity_t *ent,const char *path){assert(!strcmp(path,values["czm_player_model"]=="leet"?"models/player/leet/leet.mdl":"models/player/czm_professional/czm_professional.mdl"));loads++;ent->model=ent;}
}
struct CCzmShop {
 CMenuPlayerModelView m_skinView;char m_szSkinPath[128]={};CzmRect m_skinRect={};
 bool DrawPlayerSkin(const CzmRect &);
};
'''

SCENARIO = r'''
int main(){
 char path[128];
 assert(CzmPlayerModel::Path("czm_skin-2",path,sizeof(path)));
 assert(!strcmp(path,"models/player/czm_skin-2/czm_skin-2.mdl"));
 for(const char *bad:{"","../leet","a/b","a\\b","a;quit","a\nquit","a.b"})
    assert(!CzmPlayerModel::Path(bad,path,sizeof(path))&&!path[0]);
 assert(!CzmPlayerModel::Path("leet",path,5)&&!path[0]);
 // The selected profile model can differ from the actual server-assigned skin.
 values["model"]="leet";
 CZM_UpdateShopState();assert(values["czm_player_model"]=="czm_professional");
 CCzmShop shop;CzmRect rect={1200,200,150,250};
 assert(shop.DrawPlayerSkin(rect)&&loads==1&&draws==1);
 assert(shop.DrawPlayerSkin(rect)&&loads==1&&draws==2);
 serverModel="leet";CZM_UpdateShopState();assert(shop.DrawPlayerSkin(rect)&&loads==2);
 rect.w=170;assert(shop.DrawPlayerSkin(rect)&&inits==3);
 exists=false;assert(!shop.DrawPlayerSkin(rect)&&draws==4);
 exists=true;serverModel="../leet";CZM_UpdateShopState();
 assert(values["czm_player_model"].empty()&&!shop.DrawPlayerSkin(rect));
}
'''


class PlayerSkinPreviewTests(unittest.TestCase):
    def test_server_model_changes_reach_the_wheel_without_profile_overrides(self):
        hud = (ROOT/'cl_dll/hud_redraw.cpp').read_text()
        shop = (ROOT/'czm/menu/CzmShop.cpp').read_text()
        code = HARNESS + function(hud,'static void CZM_UpdateShopState(')
        code += function(shop,'bool CCzmShop::DrawPlayerSkin(') + SCENARIO
        with tempfile.TemporaryDirectory(prefix='czm-skin-') as folder:
            path = Path(folder)
            (path/'check.cpp').write_text(code)
            subprocess.run(['g++','-std=c++11','-Wall','-I'+str(ROOT/'common'),str(path/'check.cpp'),'-o',str(path/'check')],check=True)
            subprocess.run([str(path/'check')],check=True)
