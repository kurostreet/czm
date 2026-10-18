/* Shared HUD geometry, independent of the renderer. GPL-2.0-or-later. */
#pragma once
#include <cmath>
#include <cstdio>

namespace CzmHud {
// COUNT text blocks, then the radar; BLOCKS is everything the editor moves
enum { HEALTH, ARMOR, TIMER, MONEY, AMMO, COUNT, RADAR = COUNT, BLOCKS };
enum { RADAR_CLASSIC, RADAR_TACTICAL, RADAR_MINIMAL, RADAR_STYLES };
static const char *const keys[BLOCKS] = { "hp", "armor", "time", "money", "ammo", "radar" };
// the radar sits in the top left corner, like in the original game
static const float defaults[BLOCKS][2] = {{.085f,.94f},{.25f,.94f},{.5f,.94f},{.88f,.82f},{.86f,.94f},{.01f,.01f}};
// cvar czm_hud_<key>_<field>; "hidden" is 1 when the player took the block off the screen
static const char *const fields[5] = { "x", "y", "scale", "opacity", "hidden" };
static const float radarMinScale = .6f, radarMaxScale = 2.f;
// world units from the centre to the edge of the radar, as in the original (64 px * 32)
static const float radarRange = 2048.f;
inline float Clamp(float v, float low, float high, float fallback) {
    return std::isfinite(v) ? (v < low ? low : v > high ? high : v) : fallback;
}
inline void Key(char *out, size_t n, int kind, const char *field) {
    snprintf(out, n, "czm_hud_%s_%s", keys[kind], field);
}
struct Rect { float x,y,w,h,scale,opacity; };
inline Rect Layout(int kind, int style, float sw, float sh, float x, float y, float scale, float opacity, int digits) {
    scale = Clamp(scale,.65f,1.6f,1);
    opacity = Clamp(opacity,.25f,1,1);
    const float unit=sh/480.0f * scale;
    float h=(style==1?32:style==2?52:44)*unit;
    float w=(34 + (digits<5?5:digits)*17)*unit;
    if(w>sw*.38f) w=sw*.38f;
    if(h>sh*.17f) h=sh*.17f;
    x=Clamp(x,.01f,.99f,defaults[kind][0])*sw-w/2;
    y=Clamp(y,.01f,.99f,defaults[kind][1])*sh-h/2;
    x=Clamp(x,sw*.012f,sw-sw*.012f-w,sw*.012f);
    y=Clamp(y,sh*.018f,sh-sh*.018f-h,sh*.018f);
    return {x,y,w,h,unit,opacity};
}
// the radar is a square, its side a quarter of the screen height at 100 %
inline Rect RadarLayout(float sw, float sh, float x, float y, float scale, float opacity) {
    scale = Clamp(scale,radarMinScale,radarMaxScale,1);
    opacity = Clamp(opacity,.25f,1,1);
    float d=sh*.24f*scale;
    if(d>sh*.62f) d=sh*.62f;
    if(d>sw*.45f) d=sw*.45f;
    x=Clamp(x,.01f,.99f,defaults[RADAR][0])*sw-d/2;
    y=Clamp(y,.01f,.99f,defaults[RADAR][1])*sh-d/2;
    x=Clamp(x,sw*.012f,sw-sw*.012f-d,sw*.012f);
    y=Clamp(y,sh*.018f,sh-sh*.018f-d,sh*.018f);
    return {x,y,d,d,d/(sh*.24f),opacity};
}
// what the radar shows inside its frame, a share of the half side
inline float RadarInner(int style) { return style==RADAR_TACTICAL ? .86f : .84f; }
}
