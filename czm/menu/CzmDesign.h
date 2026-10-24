/* Shared native CZM surfaces. Geometry is also used by the touch controls. */
#pragma once
#include "CzmMenu.h"
#include "Scissor.h"

namespace CzmStyle {
inline unsigned Ink() { return PackRGBA(239,243,248,255); }
inline unsigned Muted() { return PackRGBA(155,166,184,255); }
inline unsigned AccentRed() { return PackRGBA(229,63,77,255); }
inline unsigned AccentBlue() { return PackRGBA(99,161,239,255); }
inline unsigned AccentGold() { return PackRGBA(231,187,96,255); }
inline unsigned Success() { return PackRGBA(107,218,167,255); }
inline unsigned Border() { return PackRGBA(51,62,78,255); }
inline unsigned Base() { return PackRGBA(20,26,36,255); }

inline void Round(const CzmRect &r,unsigned color,int radius=0) {
    if(r.w<=0||r.h<=0)return;
    const int edge=Q_min(Q_min(r.w,r.h)/2,
        radius?radius:Q_max(3,(int)(ScreenHeight*.011f)));
    CZM_DrawSliced("gfx/czm/ui/surface.png",r.x,r.y,r.w,r.h,16,edge,color);
}
inline void Surface(const CzmRect &r,unsigned fill=0,unsigned border=0,int radius=0) {
    Round(r,border?border:Border(),radius);
    const int line=Q_max(1,(int)(ScreenHeight/900));
    Round(CZM_Rect(r.x+line,r.y+line,r.w-line*2,r.h-line*2),
          fill?fill:Base(),radius?Q_max(1,radius-line):0);
}
inline void Text(const CzmRect &r,const char *text,int font=CZMF_UI_LABEL,
                 unsigned color=0,unsigned justify=QM_LEFT) {
    if(r.w<=0||r.h<=0)return;
    const HFont f=CZM_Font(font);
    CZM_DrawText(f,r.x,r.y+(r.h-CZM_FontHeight(f))/2,r.w,text,
                 color?color:Ink(),justify);
}
inline void Button(const CzmRect &r,const char *label,bool enabled=true,
                   bool primary=false,bool pressed=false,unsigned accent=0,
                   int font=CZMF_UI_LABEL) {
    const unsigned fill=primary&&enabled?
        (pressed?PackRGBA(158,38,54,255):PackRGBA(190,43,60,255)):
        pressed?PackRGBA(41,51,67,255):PackRGBA(28,36,48,255);
    Surface(r,fill,primary&&enabled?AccentRed():pressed&&accent?accent:Border());
    Text(CZM_Rect(r.x+r.h/4,r.y,r.w-r.h/2,r.h),label,font,
         enabled?(accent&&!primary?accent:Ink()):Muted(),QM_CENTER);
}
inline void Icon(const CzmRect &r,const char *path,unsigned color=0) {
    const int side=Q_min(r.w,r.h)/2;
    CZM_DrawImage(path,r.x+(r.w-side)/2,r.y+(r.h-side)/2,
                  side,side,color?color:Ink());
}
inline void Switch(const CzmRect &r,bool on,bool dim=false) {
    // Match the existing Settings switch, including its assets and thumb inset.
    const int inset=r.h*12/100,knob=r.h-inset*2;
    CZM_DrawPill(on?"gfx/czm/ui/pill_lang_on.png":"gfx/czm/ui/chip_lang.png",
        r.x,r.y,r.w,r.h,PackRGBA(255,255,255,dim?90:255));
    CZM_DrawImage("gfx/czm/ui/dot.png",on?r.x+r.w-inset-knob:r.x+inset,
        r.y+inset,knob,knob,dim?PackRGBA(150,150,150,120):Ink());
}
inline void MapPreview(const CzmRect &r,const char *map,const char *server="") {
    const HIMAGE photo=CZM_MapPreview(map);
    // Cover scales an image beyond the destination on one axis. Clip it so a
    // wide thumbnail cannot paint over the room title or neighbouring controls.
    UI::Scissor::PushScissor(r.x,r.y,r.w,r.h);
    if(photo){CZM_DrawCover(photo,r.x,r.y,r.w,r.h);UI::Scissor::PopScissor();return;}
    const HIMAGE art=CZM_Image(CZM_MapModeArt(map,server));
    if(art)CZM_DrawCover(art,r.x,r.y,r.w,r.h);
    UI_FillRect(r.x,r.y,r.w,r.h,PackRGBA(10,18,29,art?175:255));
    UI::Scissor::PopScissor();
    const int side=Q_min(r.w,r.h)*32/100;
    CZM_DrawImage("gfx/czm/ui/icon_globe.png",r.x+(r.w-side)/2,
                  r.y+(r.h-side)/2-side/4,side,side,Muted());
    if(r.h>CZM_FontHeight(CZM_Font(CZMF_UI_META))*4)
        Text(CZM_Rect(r.x+4,r.y+r.h*70/100,r.w-8,r.h/5),
             CZM_IsRussian()?"Превью карты":"Map preview",CZMF_UI_META,Muted(),QM_CENTER);
}
inline void HomeAction(const CzmRect &r,const char *label,const char *hint,
                       const char *icon,unsigned accent,bool primary,bool pressed) {
    const unsigned fill=primary?(pressed?PackRGBA(147,32,47,255):PackRGBA(177,38,55,255)):
        pressed?PackRGBA(35,46,63,255):PackRGBA(20,28,40,249);
    Surface(r,fill,primary?AccentRed():pressed?accent:PackRGBA(58,70,89,255));
    const int inset=Q_max(7,r.h/5),line=Q_max(2,r.h/25);
    UI_FillRect(r.x+1,r.y+inset,line,r.h-inset*2,accent);
    const int side=r.h*34/100,ix=r.x+r.h*25/100;
    CZM_DrawImage(icon,ix,r.y+(r.h-side)/2,side,side,primary?Ink():accent);
    const int tx=r.x+r.h*86/100,tw=r.w-(tx-r.x)-r.h/2;
    const int fh=CZM_FontHeight(CZM_Font(CZMF_UI_ACTION));
    const int sh=CZM_FontHeight(CZM_Font(CZMF_UI_META));
    const int gap=Q_max(2,r.h/20),top=r.y+(r.h-fh-sh-gap)/2;
    CZM_DrawText(CZM_Font(CZMF_UI_ACTION),tx,top,tw,label,Ink());
    CZM_DrawText(CZM_Font(CZMF_UI_META),tx,top+fh+gap,tw,hint,
        primary?PackRGBA(244,205,212,255):Muted());
    Text(CZM_Rect(r.x+r.w-r.h/3,r.y,r.h/5,r.h),"›",CZMF_UI_ACTION,
         primary?Ink():accent,QM_CENTER);
}
} // namespace CzmStyle
