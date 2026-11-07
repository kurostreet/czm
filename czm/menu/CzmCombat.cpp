/* In-match server ability controls and local push-to-talk feedback. */
#include <cstdio>
#include <cstring>
#include <cmath>
#include "extdll_menu.h"
#include "BaseMenu.h"
#include "BaseClientWindow.h"
#include "Utils.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "../../common/czm_combat.h"
#define UI_DIR "gfx/czm/ui/"

static void FittedText(HFont font,int x,int y,int w,int h,const char *text,unsigned int color) {
    int measured=CZM_TextWidth(font,text),size=CZM_FontHeight(font);
    if(measured>w&&measured>0)size=Q_max(1,size*w/measured);
    size=Q_min(size,h);
    UI_DrawString(font,x,y+(h-size)/2,w,size,text,color,size,QM_CENTER|QM_TOP,ETF_NO_WRAP|ETF_FORCECOL);
}

static CzmRect MicrophoneMeterRect(const CzmRect &mic) {
    int w=Q_min(ScreenWidth,Q_max(mic.w,ScreenHeight/5));
    int h=Q_min(ScreenHeight,Q_max(18,ScreenHeight/24));
    const int gap=Q_min(6,Q_max(1,ScreenHeight/120));
    const int above=Q_max(0,mic.y-gap),below=Q_max(0,ScreenHeight-mic.y-mic.h-gap);
    const int left=Q_max(0,mic.x-gap),right=Q_max(0,ScreenWidth-mic.x-mic.w-gap);
    int x=bound(0,mic.x+mic.w/2-w/2,ScreenWidth-w),y=0;
    if(above>=h)y=mic.y-gap-h;
    else if(below>=h)y=mic.y+mic.h+gap;
    else if(Q_max(left,right)>=w) {
        x=right>=left?mic.x+mic.w+gap:mic.x-gap-w;
        y=bound(0,mic.y+mic.h/2-h/2,ScreenHeight-h);
    } else if(Q_max(above,below)>0) {
        h=Q_min(h,Q_max(above,below));y=above>=below?mic.y-gap-h:mic.y+mic.h+gap;
    } else if(Q_max(left,right)>0) {
        w=Q_min(w,Q_max(left,right));x=right>=left?mic.x+mic.w+gap:mic.x-gap-w;
        y=bound(0,mic.y+mic.h/2-h/2,ScreenHeight-h);
    } else y=bound(0,mic.y-h-gap,ScreenHeight-h);
    return CZM_Rect(x,y,w,h);
}

static void DrawMicrophoneIndicator(const int *anchor) {
    if(!(EngFuncs::GetCvarFloat("czm_voice_held")>0)||ScreenWidth<=0||ScreenHeight<=0)return;
    const int left=bound(0,anchor[0],ScreenWidth),top=bound(0,anchor[1],ScreenHeight);
    CzmRect mic=CZM_Rect(left,top,bound(0,anchor[2],ScreenWidth)-left,bound(0,anchor[3],ScreenHeight)-top);
    if(mic.w<=0||mic.h<=0)return;
    const bool recording=EngFuncs::GetCvarFloat("czm_voice_recording")>0;
    const float raw=EngFuncs::GetCvarFloat("czm_voice_level");
    const float level=recording&&std::isfinite(raw)?bound(0.f,raw,1.f):0.f;
    CzmRect meter=MicrophoneMeterRect(mic);
    // The light indicates local capture, never an acknowledgement from another player.
    CZM_DrawImage(UI_DIR "dot.png",mic.x,mic.y,mic.w,mic.h,
        recording?PackRGBA(89,230,175,80):PackRGBA(255,153,103,80));
    UI_FillRect(meter.x,meter.y,meter.w,meter.h,PackRGBA(8,18,23,225));
    const int pad=Q_min(4,Q_min(meter.w/4,meter.h/4));
    const int innerW=meter.w-2*pad,innerH=meter.h-2*pad;
    const int labelH=recording?innerH/2:innerH;
    if(innerW>=24&&labelH>=6)FittedText(CZM_Font(CZMF_TINY),meter.x+pad,meter.y+pad,innerW,labelH,
        recording?(CZM_IsRussian()?"Микрофон включён":"Microphone on"):
            (CZM_IsRussian()?"Микрофон недоступен":"Mic unavailable"),
        recording?CZM_White():PackRGBA(255,153,103,255));
    if(!recording)return;
    const int barH=innerH-labelH,bars=Q_min(12,innerW);
    if(barH<=0||bars<=0)return;
    // A zero PCM level lights no bars. No timed/random animation or stale history.
    const int lit=level>0?(int)std::ceil(level*bars):0;
    for(int i=0;i<bars;i++) {
        int start=innerW*i/bars,end=innerW*(i+1)/bars;
        int gap=end-start>2?1:0,bh=Q_max(1,barH*(i+1)/bars);
        UI_FillRect(meter.x+pad+start,meter.y+pad+innerH-bh,end-start-gap,bh,
            i<lit?PackRGBA(89,230,175,255):PackRGBA(52,72,78,190));
    }
}

void CZM_DrawCombatControls() {
    if(!CL_IsActive()||uiStatic.menu.IsActive()||uiStatic.client.IsActive())return;
    int p[16]={0};
    const char *anchors=EngFuncs::GetCvarString("czm_touch_anchors");
    const int fields=anchors?std::sscanf(anchors,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d",
        p,p+1,p+2,p+3,p+4,p+5,p+6,p+7,p+8,p+9,p+10,p+11,p+12,p+13,p+14,p+15):0;
    if(fields<12)return;
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
    if(fields==16)DrawMicrophoneIndicator(p+12);
}

class CCzmDigits:public CMenuBaseClientWindow {
public:
    typedef CMenuBaseClientWindow BaseClass;
    CCzmDigits():BaseClass("CzmDigits"),pressed(-1),closing(false){}
    void Init() override {BaseClass::Init();pos.x=uiStatic.xOffset;pos.y=uiStatic.yOffset;size.w=uiStatic.width;size.h=768;}
    void VidInit() override {pos.x=uiStatic.xOffset;pos.y=uiStatic.yOffset;size.w=uiStatic.width;size.h=768;BaseClass::VidInit();}
    void Open(){pressed=-1;closing=false;CZM_KeepClientMenu(this);Show();}
    void Show() override {EngFuncs::KEY_SetDest(KEY_MENU);EngFuncs::ClientCmd(true,"touch_setclientonly 1");BaseClass::Show();}
    void Close(){if(!closing){closing=true;pressed=-1;CZM_CloseClientMenuSoon(this);}}
    void Hide() override {Close();}
    bool KeyDown(int key) override {
        if(UI::Key::IsEscape(key)){Close();return true;}
        if(UI::Key::IsLeftMouse(key)){CzmCombat::Keypad pad(ScreenWidth,ScreenHeight);pressed=pad.Hit(uiStatic.cursorX,uiStatic.cursorY);}
        return true;
    }
    bool KeyUp(int key) override {
        if(!UI::Key::IsLeftMouse(key))return true;
        CzmCombat::Keypad pad(ScreenWidth,ScreenHeight);int hit=pad.Hit(uiStatic.cursorX,uiStatic.cursorY),down=pressed;pressed=-1;
        if(hit!=down||hit<0)return true;
        if(hit==10){Close();return true;}
        CZM_PlayClick();EngFuncs::ClientCmdF(false,"slot%d\n",hit?hit:10);
        return true;
    }
    bool MouseMove(int,int) override {return true;}
    void Draw() override {
        if(closing||!CL_IsActive()){Close();return;}
        CzmCombat::Keypad pad(ScreenWidth,ScreenHeight);
        CZM_DrawPanel(CZM_Rect(pad.x,pad.y,pad.w,pad.h));
        FittedText(CZM_Font(CZMF_TILE_TITLE),pad.x+pad.gap,pad.y,pad.w-pad.header-pad.gap,pad.header,"CZM  123",CZM_White());
        CzmRect cross=CZM_Rect(pad.x+pad.w-pad.header,pad.y,pad.header,pad.header);
        CZM_DrawImage(UI_DIR "icon_close.png",cross.x+cross.w/4,cross.y+cross.h/4,cross.w/2,cross.h/2,pressed==10?CZM_Grey():CZM_White());
        for(int digit=0;digit<=9;digit++) {
            int x,y;pad.Cell(digit,x,y);char text[2]={(char)('0'+digit),0};
            CzmRect cell=CZM_Rect(x,y,pad.key,pad.key);
            CZM_DrawButton(UI_DIR "button_secondary.png",cell,"",CZM_White(),pressed==digit);
            FittedText(CZM_Font(CZMF_PANEL_TITLE),x,y,pad.key,pad.key,text,pressed==digit?PackRGBA(255,181,88,255):CZM_White());
        }
    }
private:int pressed;bool closing;
};
ADD_MENU3(menu_czmdigits,CCzmDigits,UI_CzmDigits_Menu);
void UI_CzmDigits_Menu() {
    if(!menu_czmdigits||!CL_IsActive())return;
    if(CZM_ClientMenuOpen(menu_czmdigits))menu_czmdigits->Close();else menu_czmdigits->Open();
}
