/* Original Inter-based CZM HUD; no legacy HUD sprites. GPL-2.0-or-later. */
#include "hud.h"
#include "cl_util.h"
#include "draw_util.h"
#include "czm_hud.h"
#include "../../common/czm_hud_paint.h"
#include "triangleapi.h"
#include <cstring>

static int s_atlas;
void CZM_HudVidInit() {
    s_atlas=gRenderAPI.GL_LoadTexture("gfx/czm/hud_glyphs.tga",NULL,0,TF_NOMIPMAP|TF_CLAMP);
}
static float Value(int kind,const char *field,float fallback) {
    char key[64]; CzmHud::Key(key,sizeof(key),kind,field);
    const char *s=gEngfuncs.pfnGetCvarString(key);
    return s && *s ? gEngfuncs.pfnGetCvarFloat(key) : fallback;
}
static void Glyphs(float x,float y,float height,const char *s,int r,int g,int b,float alpha) {
    gRenderAPI.GL_SelectTexture(0); gRenderAPI.GL_Bind(0,s_atlas);
    gEngfuncs.pTriAPI->RenderMode(kRenderTransAlpha);
    gEngfuncs.pTriAPI->Color4f(r/255.f,g/255.f,b/255.f,alpha);
    const float scale=gHUD.m_flScale, width=height*.65f;
    for(;*s;s++,x+=width) {
        unsigned c=(unsigned char)*s; if(c<32 || c>95) c='?'; c-=32;
        float u=(c%16)/16.f,v=(c/16)/4.f;
        gEngfuncs.pTriAPI->Begin(TRI_QUADS);
        gEngfuncs.pTriAPI->TexCoord2f(u,v);gEngfuncs.pTriAPI->Vertex3f(x*scale,y*scale,0);
        gEngfuncs.pTriAPI->TexCoord2f(u,v+.25f);gEngfuncs.pTriAPI->Vertex3f(x*scale,(y+height)*scale,0);
        gEngfuncs.pTriAPI->TexCoord2f(u+.0625f,v+.25f);gEngfuncs.pTriAPI->Vertex3f((x+width)*scale,(y+height)*scale,0);
        gEngfuncs.pTriAPI->TexCoord2f(u+.0625f,v);gEngfuncs.pTriAPI->Vertex3f((x+width)*scale,y*scale,0);
        gEngfuncs.pTriAPI->End();
    }
    gEngfuncs.pTriAPI->Color4f(1,1,1,1);
}
namespace {
// the match: additive bars and icons, alpha-blended plates, glyphs from the atlas
struct GamePainter : CzmHud::Painter {
    void Fill(int x,int y,int w,int h,int r,int g,int b,int a) override { FillRGBA(x,y,w,h,r,g,b,a); }
    void Blend(int x,int y,int w,int h,int r,int g,int b,int a) override { FillRGBABlend(x,y,w,h,r,g,b,a); }
    void Text(float x,float y,float height,const char *s,int r,int g,int b,float alpha) override { Glyphs(x,y,height,s,r,g,b,alpha); }
};
}
bool CZM_HudDraw(int kind,const char *value,bool warning) {
    if(!s_atlas || !g_iXash || kind<0 || kind>=CzmHud::COUNT) return false;
    int style=(int)CzmHud::Clamp(gEngfuncs.pfnGetCvarFloat("czm_hud_style"),0,2,0);
    CzmHud::Rect p=CzmHud::Layout(kind,style,ScreenWidth,ScreenHeight,Value(kind,"x",CzmHud::defaults[kind][0]),
        Value(kind,"y",CzmHud::defaults[kind][1]),Value(kind,"scale",1),Value(kind,"opacity",1),(int)strlen(value));
    GamePainter painter;
    CzmHud::Paint(painter,kind,style,p,value,warning);
    return true;
}
bool CZM_HudNumber(int kind,int value,bool warning) {
    char s[32]; snprintf(s,sizeof(s),"%d",value);return CZM_HudDraw(kind,s,warning);
}
