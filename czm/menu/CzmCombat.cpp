/* In-match controls for the current server-reported zombie abilities. */
#include <cstdio>
#include <cstring>
#include <cmath>
#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "CzmMenu.h"
#include "../../common/czm_combat.h"
#define UI_DIR "gfx/czm/ui/"

static void FittedText(HFont font,int x,int y,int w,int h,const char *text,unsigned int color) {
    int measured=CZM_TextWidth(font,text),size=CZM_FontHeight(font);
    if(measured>w&&measured>0)size=Q_max(1,size*w/measured);
    size=Q_min(size,h);
    UI_DrawString(font,x,y+(h-size)/2,w,size,text,color,size,QM_CENTER|QM_TOP,ETF_NO_WRAP|ETF_FORCECOL);
}

void CZM_DrawCombatControls() {
    if(!CL_IsActive()||uiStatic.menu.IsActive()||uiStatic.client.IsActive())return;
    int p[12]={0};
    const char *anchors=EngFuncs::GetCvarString("czm_touch_anchors");
    if(!anchors||std::sscanf(anchors,"%d %d %d %d %d %d %d %d %d %d %d %d",
        p,p+1,p+2,p+3,p+4,p+5,p+6,p+7,p+8,p+9,p+10,p+11)!=12)return;
    CzmCombat::State state;CzmCombat::Parse(EngFuncs::GetCvarString("czm_skill_state"),state);
    HFont font=CZM_Font(CZMF_SMALL);
    for(int button=0;button<3;button++) {
        int *b=p+button*4,w=b[2]-b[0],h=b[3]-b[1];
        if(!(CzmCombat::Mask(state.klass)&(1<<button))||w<=0||h<=0)continue;
        int remaining=CzmCombat::Cooldown(state,button);char count[24];
        const bool charging=state.klass==8&&button==CzmCombat::E&&(state.flags&2)&&state.charge>0;
        if(charging||remaining>0) {
            // Overlay the existing circle; its name stays readable below it.
            CZM_DrawImage(UI_DIR "dot.png",b[0],b[1],w,h,PackRGBA(7,12,20,charging?150:195));
            std::snprintf(count,sizeof(count),"%d",((charging?state.charge:remaining)+9)/10);
            FittedText(CZM_Font(CZMF_PANEL_TITLE),b[0],b[1],w,h,count,charging?PackRGBA(111,232,196,255):CZM_White());
        }
        int labelH=Q_max(12,ScreenHeight/42),labelW=Q_min(ScreenWidth,Q_max(w,(int)(w*1.30f)));
        int x=bound(0,b[0]+w/2-labelW/2,ScreenWidth-labelW),y=bound(0,b[3]+2,ScreenHeight-labelH);
        UI_FillRect(x,y,labelW,labelH,PackRGBA(7,12,20,185));
        FittedText(font,x,y,labelW,labelH,CzmCombat::Name(state,button,CZM_IsRussian()),
            remaining>0&&!charging?PackRGBA(164,176,191,255):PackRGBA(132,239,201,255));
    }
}
