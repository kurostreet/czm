/* One HUD block painted from its layout; shared by the match HUD and the editor preview. GPL-2.0-or-later. */
#pragma once
#include <cstring>
#include "czm_hud_layout.h"

namespace CzmHud {
// Fill is additive in the match (FillRGBA), Blend is alpha blended, Text draws the glyph
// atlas with .65 of the height per character. The editor draws all three with its own calls.
struct Painter {
    virtual void Fill(int x,int y,int w,int h,int r,int g,int b,int a)=0;
    virtual void Blend(int x,int y,int w,int h,int r,int g,int b,int a)=0;
    virtual void Text(float x,float y,float height,const char *s,int r,int g,int b,float alpha)=0;
    virtual ~Painter() {}
};
static const char *const labels[COUNT] = { "HEALTH", "ARMOR", "ROUND", "CREDITS", "AMMO" };
// what the editor shows in the blocks, as long as the usual values in a match
static const char *const samples[COUNT] = { "100", "100", "1:45", "16000", "30 / 90" };

inline void Paint(Painter &d,int kind,int style,const Rect &p,const char *value,bool warning) {
    int x=p.x,y=p.y,w=p.w,h=p.h,a=255*p.opacity;
    int red=warning?255:224,green=warning?65:37,blue=warning?72:50;
    int edge=h/18+1;
    if(style!=1) {
        d.Blend(x,y,w,h,10,14,22,(style==2?220:165)*p.opacity);
        if(style==2) {
            d.Fill(x,y,w,edge,red,green,blue,a);
            d.Fill(x,y+h-edge,w,edge,62,70,88,a/2);
        } else d.Fill(x,y,edge,h,red,green,blue,a);
    } else d.Fill(x,y+h-edge,w,edge,warning?255:145,warning?65:160,warning?72:185,a/2);
    // Independently drawn geometric indicators: cross, shield, clock, wallet, cartridges.
    const int sz=h*.36f,ix=x+h*.18f,iy=y+(h-sz)/2,t=sz/5+1;
    const int ir=warning?255:214,ig=warning?70:224,ib=warning?78:239;
    if(kind==HEALTH) {
        d.Fill(ix+sz/2-t/2,iy,t,sz,ir,ig,ib,a);d.Fill(ix,iy+sz/2-t/2,sz,t,ir,ig,ib,a);
    } else if(kind==ARMOR) {
        for(int j=0;j<sz;j++) { int k=j>sz/2?(j-sz/2)/2:0;d.Fill(ix+k,iy+j,sz-k*2,1,ir,ig,ib,a); }
    } else if(kind==TIMER) {
        d.Fill(ix,iy,sz,t,ir,ig,ib,a);d.Fill(ix,iy+sz-t,sz,t,ir,ig,ib,a);
        d.Fill(ix,iy,t,sz,ir,ig,ib,a);d.Fill(ix+sz-t,iy,t,sz,ir,ig,ib,a);
        d.Fill(ix+sz/2,iy+t,t,sz/2,red,green,blue,a);
    } else if(kind==MONEY) {
        d.Fill(ix,iy,sz,sz,ir,ig,ib,a);d.Fill(ix+sz/2,iy+sz/3,sz/2,sz/3,red,green,blue,a);
    } else {
        for(int j=0;j<3;j++) d.Fill(ix+j*(sz/3),iy+(j%2)*t,t,sz-(j%2)*t,ir,ig,ib,a);
    }
    int length=(int)strlen(value);
    float textH=h*(style==1?.7f:.52f),tx=ix+sz+h*.15f;
    float maxH=(x+w-tx-h*.12f)/((length>1?length:1)*.65f);
    if(textH>maxH) textH=maxH;
    float ty=y+(h-textH)/2;
    if(style==2) {
        d.Text(tx,y+h*.13f,h*.16f,labels[kind],147,159,180,p.opacity);
        ty=y+h*.38f;
    }
    d.Text(tx,ty,textH,value,warning?255:246,warning?100:249,warning?105:255,p.opacity);
}
}
