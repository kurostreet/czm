/* Original CZM in-match HUD. GPL-2.0-or-later. */
#pragma once
#include "../../common/czm_hud_layout.h"
void CZM_HudVidInit();
bool CZM_HudReady();
bool CZM_HudDraw(int kind, const char *value, bool warning=false);
bool CZM_HudNumber(int kind, int value, bool warning=false);
float CZM_HudValue(int kind, const char *field, float fallback);
void CZM_HudText(float x, float y, float height, const char *s, int r, int g, int b, float alpha);

// the radar (czm_radar.cpp): marks in radar space, -1..1 from the centre, up is where the player looks
enum { CZM_MARK_DOT, CZM_MARK_UP, CZM_MARK_DOWN, CZM_MARK_X, CZM_MARKS };
struct CzmRadarMark { float x, y; int kind; int r, g, b; };
void CZM_RadarVidInit();
// false: the CZM radar cannot draw, use the stock one; *labelX, *labelY: where the place name goes
bool CZM_RadarDraw(float yaw, const CzmRadarMark *marks, int count, int *labelX, int *labelY);

// the clip and the reserve for the reload button (czm_ammo.cpp)
void CZM_AmmoReset();
void CZM_AmmoFrameBegin();
void CZM_AmmoReport(int weapon, int clip, int reserve);
void CZM_AmmoFrameEnd();

// the spectator overlay in the style of czm_hud_spec_style and the download indicator (czm_overlay.cpp)
int CZM_SpectatorStyle();
// false: the CZM HUD cannot draw, use the stock overlay
bool CZM_SpectatorDraw(int target, const char *timer, int scoreCT, int scoreT, bool status);
void CZM_DownloadsDraw();
