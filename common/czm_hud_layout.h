/* Shared HUD geometry, independent of the renderer. GPL-2.0-or-later. */
#pragma once
#include <cmath>
#include <cstdio>

namespace CzmHud {
// COUNT text blocks, then the radar, the match chat, the frame of server messages and the
// indicator of server files downloading in a match; BLOCKS is everything the editor moves
enum { HEALTH, ARMOR, TIMER, MONEY, AMMO, COUNT, RADAR = COUNT, CHAT, MESSAGES, DOWNLOADS, BLOCKS };
enum { RADAR_CLASSIC, RADAR_TACTICAL, RADAR_MINIMAL, RADAR_STYLES };
// the chat and the server messages: as in CS, on dark plates, with a dark outline
enum { MSG_CLASSIC, MSG_CZM, MSG_OUTLINE, MSG_STYLES };
static const char *const keys[BLOCKS] = { "hp", "armor", "time", "money", "ammo", "radar", "chat", "msgs", "dl" };
// The default layout, made by the owner in the game (scripts/layouts/scheme1.json): health, time
// and armor in the bottom row, money under the radar on the left, the ammo shown on the reload
// button instead of its own block. The frame of server messages is the whole screen, so they
// stay where the server put them. The download indicator sits at the bottom left, beside the
// health block. A reset in the editor brings these back.
static const float defaults[BLOCKS][2] = {{.3944f,.9474f},{.6033f,.9474f},{.5f,.9362f},{.0553f,.3273f},{.6681f,.9477f},{.068f,.138f},{.156f,.6858f},{.5f,.5f},{.176813f,.952833f}};
static const float defaultScale[BLOCKS] = { .7535f, .7547f, 1, .7484f, .7484f, 1, .6f, 1, 1 };
static const bool defaultHidden[BLOCKS] = { false, false, false, false, true, false, false, false, false };
static const int defaultHudStyle = 0, defaultRadarStyle = RADAR_MINIMAL, defaultMessageStyle = MSG_CZM;
static const int chatLines = 5;
// The HUD grows with the screen height, but on screens narrower than 2.1:1 (16:9 phones, tablets)
// it follows the width instead: then the blocks keep their gaps as on the phone where the layout was made.
inline float Base(float sw, float sh) { float b = sw / 2.1f; return b < sh ? b : sh; }
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
    const float unit=Base(sw,sh)/480.0f * scale;
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
    float d=Base(sw,sh)*.24f*scale;
    if(d>sh*.62f) d=sh*.62f;
    if(d>sw*.45f) d=sw*.45f;
    x=Clamp(x,.01f,.99f,defaults[RADAR][0])*sw-d/2;
    y=Clamp(y,.01f,.99f,defaults[RADAR][1])*sh-d/2;
    x=Clamp(x,sw*.012f,sw-sw*.012f-d,sw*.012f);
    y=Clamp(y,sh*.018f,sh-sh*.018f-d,sh*.018f);
    return {x,y,d,d,d/(Base(sw,sh)*.24f),opacity};
}
// the chat: lines grow up from the bottom of the block, half the screen wide at 100 %
inline Rect ChatLayout(float sw, float sh, float x, float y, float scale, float opacity, float lineHeight) {
    scale = Clamp(scale,.6f,1.6f,1);
    opacity = Clamp(opacity,.25f,1,1);
    float w=sw*.5f*scale, h=lineHeight*chatLines;
    if(w>sw*.96f) w=sw*.96f;
    if(h>sh*.6f) h=sh*.6f;
    x=Clamp(x,.01f,.99f,defaults[CHAT][0])*sw-w/2;
    y=Clamp(y,.01f,.99f,defaults[CHAT][1])*sh-h/2;
    x=Clamp(x,sw*.006f,sw-sw*.006f-w,sw*.006f);
    y=Clamp(y,sh*.01f,sh-sh*.01f-h,sh*.01f);
    return {x,y,w,h,scale,opacity};
}
// server messages keep their places inside this frame: the whole screen at 100 %, 60 % at least
inline Rect MessageFrame(float sw, float sh, float x, float y, float scale, float opacity) {
    scale = Clamp(scale,.6f,1,1);
    opacity = Clamp(opacity,.25f,1,1);
    float w=sw*scale, h=sh*scale;
    x=Clamp(x,0,1,defaults[MESSAGES][0])*sw-w/2;
    y=Clamp(y,0,1,defaults[MESSAGES][1])*sh-h/2;
    x=Clamp(x,0,sw-w,0);
    y=Clamp(y,0,sh-h,0);
    return {x,y,w,h,scale,opacity};
}
// the download indicator: a plate with the words and the percent, at least as tall as the text
inline Rect DownloadLayout(float sw, float sh, float x, float y, float scale, float opacity, float lineHeight) {
    scale = Clamp(scale,.6f,1.6f,1);
    opacity = Clamp(opacity,.25f,1,1);
    const float unit=Base(sw,sh)/480.0f*scale;
    float h=28*unit, w=196*unit;
    if(h<lineHeight*1.7f) h=lineHeight*1.7f;
    if(w>sw*.6f) w=sw*.6f;
    if(h>sh*.15f) h=sh*.15f;
    x=Clamp(x,.01f,.99f,defaults[DOWNLOADS][0])*sw-w/2;
    y=Clamp(y,.01f,.99f,defaults[DOWNLOADS][1])*sh-h/2;
    x=Clamp(x,sw*.012f,sw-sw*.012f-w,sw*.012f);
    y=Clamp(y,sh*.018f,sh-sh*.018f-h,sh*.018f);
    return {x,y,w,h,unit,opacity};
}
// what the radar shows inside its frame, a share of the half side
inline float RadarInner(int style) { return style==RADAR_TACTICAL ? .86f : .84f; }
}
