/* The spectator overlay and the download indicator, painted the same in the match and in the
   menu previews. GPL-2.0-or-later. */
#pragma once
#include <cstdio>
#include <cstring>
#include "czm_hud_layout.h"

namespace CzmHud {
// three looks of the spectator overlay (czm_hud_spec_style), chosen in Settings → HUD
enum { SPEC_MINIMAL, SPEC_CARD, SPEC_CINEMA, SPEC_STYLES };
static const int defaultSpecStyle = SPEC_CARD;

// What the overlays draw with: alpha-blended plates, the glyph atlas (digits, capital latin
// letters and signs, .65 of the height per character) and the UTF-8 font for names and words.
// The match draws them with the HUD calls, the menu with its own.
struct Canvas {
    virtual void Blend(int x,int y,int w,int h,int r,int g,int b,int a)=0;
    virtual void Glyphs(float x,float y,float height,const char *s,int r,int g,int b,float alpha)=0;
    virtual int LabelWidth(const char *s)=0;
    virtual int LabelHeight()=0;
    virtual void Label(int x,int y,const char *s,int r,int g,int b)=0;
    virtual bool Avatar(int x,int y,int size)=0; // the watched player's picture; false: none
    virtual ~Canvas() {}
};

struct SpecInfo {
    const char *name;     // the watched player in UTF-8 without colour codes; "" when nobody
    int team;             // 1 terrorists (zombies), 2 counter-terrorists (humans), else none
    int health;           // below 0: unknown
    int scoreCT, scoreT;
    const char *timer;    // "1:45"; "" while the bomb ticks
    const char *watching; // the word over the name on the card
    bool status;          // the score and the time at the top ("Show status" of the spectator menu)
};

inline float GlyphWidth(const char *s, float h) { return (float)strlen(s) * h * .65f; }
inline int Max(int a, int b) { return a > b ? a : b; }

inline void TeamColor(int team, int &r, int &g, int &b) {
    if(team == 1) { r = 236; g = 72; b = 78; }
    else if(team == 2) { r = 86; g = 156; b = 255; }
    else { r = 180; g = 188; b = 204; }
}

inline void HealthColor(int hp, int &r, int &g, int &b) {
    if(hp > 50) { r = 74; g = 212; b = 140; }
    else if(hp > 25) { r = 255; g = 176; b = 32; }
    else { r = 239; g = 68; b = 68; }
}

// a name the atlas can draw (latin letters, digits, signs) in capitals; false: use the font
inline bool AtlasName(const char *s, char *out, size_t n) {
    size_t k = 0;
    for(; *s && k + 1 < n; s++) {
        unsigned char c = (unsigned char)*s;
        if(c >= 'a' && c <= 'z') c -= 32;
        if(c < 32 || c > 95) return false;
        out[k++] = (char)c;
    }
    out[k] = 0;
    return k > 0 && !*s;
}

// the text cut with "..." to the width, whole UTF-8 characters only
inline void Fit(Canvas &c, const char *s, float width, char *out, size_t n) {
    snprintf(out, n, "%s", s ? s : "");
    if(c.LabelWidth(out) <= width) return;
    size_t len = strlen(out);
    while(len > 0) {
        do len--; while(len > 0 && ((unsigned char)out[len] & 0xc0) == 0x80);
        out[len] = 0;
        char cut[160];
        snprintf(cut, sizeof(cut), "%s...", out);
        if(c.LabelWidth(cut) <= width || !len) { snprintf(out, n, "%s", len ? cut : ""); return; }
    }
}

// a soft dark band at the top (down = true) or the bottom edge of the screen
inline void Fade(Canvas &c, float sw, float y, float h, bool down, int alpha) {
    const int steps = 18;
    for(int i = 0; i < steps; i++) {
        int y0 = (int)(y + h * i / steps), y1 = (int)(y + h * (i + 1) / steps);
        float k = (i + .5f) / steps;
        if(down) k = 1 - k;
        if(y1 > y0) c.Blend(0, y0, (int)sw, y1 - y0, 4, 6, 10, (int)(alpha * k * k));
    }
}

// the small cross of health
inline void Cross(Canvas &c, float x, float y, float s, int r, int g, int b) {
    int t = Max(2, (int)(s * .34f));
    c.Blend((int)(x + (s - t) / 2), (int)y, t, (int)s, r, g, b, 255);
    c.Blend((int)x, (int)(y + (s - t) / 2), (int)s, t, r, g, b, 255);
}

// the watched player's picture, a team-coloured square with a light frame when there is none
inline void Portrait(Canvas &c, float x, float y, float size, int team) {
    int r, g, b; TeamColor(team, r, g, b);
    int edge = Max(1, (int)(size * .05f));
    c.Blend((int)x - edge, (int)y - edge, (int)size + edge * 2, (int)size + edge * 2, r, g, b, 255);
    if(!c.Avatar((int)x, (int)y, (int)size)) {
        c.Blend((int)x, (int)y, (int)size, (int)size, r / 3, g / 3, b / 3, 255);
        Cross(c, x + size * .3f, y + size * .3f, size * .4f, 235, 238, 244);
    }
}

// the score and the round time at the top in the middle
inline void PaintScore(Canvas &c, int style, float sw, float u, const SpecInfo &s) {
    char ct[12], t[12];
    snprintf(ct, sizeof(ct), "%d", s.scoreCT);
    snprintf(t, sizeof(t), "%d", s.scoreT);
    const char *timer = s.timer && *s.timer ? s.timer : ":";
    int br, bg, bb, rr, rg, rb;
    TeamColor(2, br, bg, bb); TeamColor(1, rr, rg, rb);

    if(style == SPEC_CARD) {
        // a broadcast score: blue box, the time on a dark box with a red line, red box
        const float gh = 17 * u, h = gh + 14 * u, y = 6 * u;
        float side = GlyphWidth("00", gh) + 20 * u;
        float wct = GlyphWidth(ct, gh) + 20 * u, wt = GlyphWidth(t, gh) + 20 * u;
        if(wct < side) wct = side;
        if(wt < side) wt = side;
        float mid = GlyphWidth("00:00", gh) + 24 * u;
        float x = (sw - wct - mid - wt) / 2;
        c.Blend((int)x, (int)y, (int)wct, (int)h, br, bg, bb, 235);
        c.Glyphs(x + (wct - GlyphWidth(ct, gh)) / 2, y + (h - gh) / 2, gh, ct, 255, 255, 255, 1);
        x += wct;
        c.Blend((int)x, (int)y, (int)mid, (int)h, 10, 14, 22, 235);
        c.Blend((int)x, (int)(y + h - 2 * u), (int)mid, Max(2, (int)(2 * u)), 224, 37, 50, 255);
        c.Glyphs(x + (mid - GlyphWidth(timer, gh)) / 2, y + (h - gh) / 2, gh, timer, 246, 249, 255, 1);
        x += mid;
        c.Blend((int)x, (int)y, (int)wt, (int)h, rr, rg, rb, 235);
        c.Glyphs(x + (wt - GlyphWidth(t, gh)) / 2, y + (h - gh) / 2, gh, t, 255, 255, 255, 1);
        return;
    }

    // minimal and cinema: the scores in team colours around the time
    const float gh = (style == SPEC_CINEMA ? 17 : 15) * u, th = (style == SPEC_CINEMA ? 21 : 15) * u;
    const float gap = 14 * u, pad = 12 * u;
    float wct = GlyphWidth(ct, gh), wt = GlyphWidth(t, gh), wtm = GlyphWidth(timer, th);
    float w = pad * 2 + wct + gap + wtm + gap + wt, h = th + 12 * u;
    float x = (sw - w) / 2, y = (style == SPEC_CINEMA ? 9 : 8) * u;
    if(style == SPEC_MINIMAL) c.Blend((int)x, (int)y, (int)w, (int)h, 10, 14, 22, 175);
    int line = Max(2, (int)(2 * u));
    float tx = x + pad;
    c.Glyphs(tx, y + (h - gh) / 2, gh, ct, br, bg, bb, 1);
    c.Blend((int)tx, (int)(y + h - line - 2 * u), (int)wct, line, br, bg, bb, 255);
    tx += wct + gap;
    c.Glyphs(tx, y + (h - th) / 2, th, timer, 246, 249, 255, 1);
    tx += wtm + gap;
    c.Glyphs(tx, y + (h - gh) / 2, gh, t, rr, rg, rb, 1);
    c.Blend((int)tx, (int)(y + h - line - 2 * u), (int)wt, line, rr, rg, rb, 255);
}

// the spectator overlay over the whole screen sw x sh
inline void PaintSpectator(Canvas &c, int style, float sw, float sh, const SpecInfo &s) {
    if(style < 0 || style >= SPEC_STYLES) style = defaultSpecStyle;
    const float u = Base(sw, sh) / 480.0f;
    const bool named = s.name && *s.name;
    const int lh = Max(1, c.LabelHeight());
    char hp[16] = "", name[160];
    if(s.health >= 0) snprintf(hp, sizeof(hp), "%d", s.health);
    int tr, tg, tb, hr, hg, hb;
    TeamColor(s.team, tr, tg, tb);
    HealthColor(s.health, hr, hg, hb);

    if(style == SPEC_CINEMA) {
        Fade(c, sw, 0, 48 * u, true, 215);
        Fade(c, sw, sh - 62 * u, 62 * u, false, 230);
    }
    if(s.status) PaintScore(c, style, sw, u, s);
    if(!named) return;

    if(style == SPEC_MINIMAL) {
        // one dark pill: the picture, the name and the health
        const float h = (float)Max((int)(30 * u), lh + (int)(12 * u)), gh = 14 * u, av = h - 8 * u;
        const float hpW = *hp ? gh * .8f + 6 * u + GlyphWidth(hp, gh) + 12 * u : 0;
        Fit(c, s.name, sw * .26f, name, sizeof(name));
        float w = 4 * u + av + 10 * u + c.LabelWidth(name) + hpW + 12 * u;
        float x = (sw - w) / 2, y = sh - h - 10 * u;
        c.Blend((int)x, (int)y, (int)w, (int)h, 10, 14, 22, 185);
        c.Blend((int)x, (int)(y + h - Max(2, (int)(2 * u))), (int)w, Max(2, (int)(2 * u)), tr, tg, tb, 230);
        Portrait(c, x + 4 * u, y + 4 * u, av, s.team);
        float tx = x + 4 * u + av + 10 * u;
        c.Label((int)tx, (int)(y + (h - lh) / 2), name, 246, 249, 255);
        if(*hp) {
            tx += c.LabelWidth(name) + 12 * u;
            Cross(c, tx, y + (h - gh * .8f) / 2, gh * .8f, hr, hg, hb);
            c.Glyphs(tx + gh * .8f + 6 * u, y + (h - gh) / 2, gh, hp, 246, 249, 255, 1);
        }
        return;
    }

    if(style == SPEC_CARD) {
        // a player card: team stripe, picture, "Spectating", the name, a health bar with the number
        const float pad = 9 * u, stripe = 5 * u, gh = 13 * u;
        const float h = pad * 2 + lh * 2 + 3 * u + 7 * u + gh;
        const float av = h - pad * 2;
        float w = 300 * u;
        if(w > sw * .34f) w = sw * .34f;
        float x = (sw - w) / 2, y = sh - h - 8 * u;
        c.Blend((int)x, (int)y, (int)w, (int)h, 10, 14, 22, 228);
        c.Blend((int)x, (int)y, (int)stripe, (int)h, tr, tg, tb, 255);
        c.Blend((int)x, (int)y, (int)w, Max(1, (int)(1.5f * u)), tr, tg, tb, 110);
        Portrait(c, x + stripe + pad, y + pad, av, s.team);
        float tx = x + stripe + pad + av + 11 * u, tw = x + w - pad - tx;
        c.Label((int)tx, (int)(y + pad), s.watching ? s.watching : "", 147, 159, 180);
        Fit(c, s.name, tw, name, sizeof(name));
        c.Label((int)tx, (int)(y + pad + lh + 3 * u), name, 246, 249, 255);
        float by = y + pad + lh * 2 + 3 * u + 7 * u;
        if(*hp) {
            float hw = GlyphWidth(hp, gh), barW = tw - hw - 9 * u, barH = 6 * u;
            float share = s.health >= 100 ? 1 : s.health / 100.0f;
            c.Blend((int)tx, (int)(by + (gh - barH) / 2), (int)barW, (int)barH, 44, 50, 64, 255);
            c.Blend((int)tx, (int)(by + (gh - barH) / 2), (int)(barW * share), (int)barH, hr, hg, hb, 255);
            c.Glyphs(tx + barW + 9 * u, by, gh, hp, 246, 249, 255, 1);
        }
        return;
    }

    // cinema: a large name over a thin team line and the health, on the soft bottom band
    char big[64];
    const float ng = 22 * u, gh = 12 * u;
    float nameW, nameH;
    bool atlas = AtlasName(s.name, big, sizeof(big)) && GlyphWidth(big, ng) < sw * .6f;
    if(atlas) { nameW = GlyphWidth(big, ng); nameH = ng; }
    else { Fit(c, s.name, sw * .5f, name, sizeof(name)); nameW = (float)c.LabelWidth(name); nameH = (float)lh; }
    float y = sh - 14 * u - gh - 9 * u - nameH;
    if(atlas) c.Glyphs((sw - nameW) / 2, y, ng, big, 246, 249, 255, 1);
    else c.Label((int)((sw - nameW) / 2), (int)y, name, 246, 249, 255);
    float lineW = nameW * .5f;
    if(lineW < 40 * u) lineW = 40 * u;
    c.Blend((int)((sw - lineW) / 2), (int)(y + nameH + 4 * u), (int)lineW, Max(2, (int)(2 * u)), tr, tg, tb, 255);
    if(*hp) {
        char line[24];
        snprintf(line, sizeof(line), "%s HP", hp);
        c.Glyphs((sw - GlyphWidth(line, gh)) / 2, sh - 14 * u - gh, gh, line, hr, hg, hb, 1);
    }
}

// the download indicator: a plate, an arrow, the words and the percent, the progress along the bottom
inline void PaintDownload(Canvas &c, const Rect &p, const char *words, float percent) {
    const int a = (int)(222 * p.opacity);
    const float edge = (float)Max(2, (int)(p.h * .09f));
    if(percent < 0) percent = 0;
    if(percent > 100) percent = 100;
    c.Blend((int)p.x, (int)p.y, (int)p.w, (int)p.h, 10, 14, 22, a);
    c.Blend((int)p.x, (int)(p.y + p.h - edge), (int)p.w, (int)edge, 52, 60, 76, a);
    c.Blend((int)p.x, (int)(p.y + p.h - edge), (int)(p.w * percent / 100), (int)edge, 224, 37, 50, (int)(255 * p.opacity));

    // the arrow down into a tray
    const float inner = p.h - edge, s = inner * .46f, ix = p.x + inner * .32f, iy = p.y + (inner - s) / 2;
    const int t = Max(2, (int)(s * .16f)), wr = 235, wg = 239, wb = 245, wa = (int)(255 * p.opacity);
    c.Blend((int)(ix + (s - t) / 2), (int)iy, t, (int)(s * .5f), wr, wg, wb, wa);
    for(int j = 0, rows = Max(2, (int)(s * .32f)); j < rows; j++) {
        int width = (int)(s * .62f * (1 - (float)j / rows));
        if(width < 1) width = 1;
        c.Blend((int)(ix + (s - width) / 2), (int)(iy + s * .5f + j), width, 1, wr, wg, wb, wa);
    }
    c.Blend((int)ix, (int)(iy + s - t), (int)s, t, wr, wg, wb, wa);

    char pct[8];
    snprintf(pct, sizeof(pct), "%d%%", (int)(percent + .5f));
    const float gh = inner * .44f, pw = GlyphWidth(pct, gh), right = p.x + p.w - inner * .32f - pw;
    c.Glyphs(right, p.y + (inner - gh) / 2, gh, pct, 246, 249, 255, p.opacity);

    char line[160];
    const float tx = ix + s + inner * .3f;
    Fit(c, words, right - tx - inner * .25f, line, sizeof(line));
    c.Label((int)tx, (int)(p.y + (inner - c.LabelHeight()) / 2), line, 220, 226, 236);
}
}
