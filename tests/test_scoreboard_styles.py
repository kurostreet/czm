"""Execute the real TAB renderer: all players must fit, including uneven teams."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STUB = r'''
#pragma once
#define MAX_PLAYERS 32
struct hud_player_info_t { const char *name; int ping; bool thisplayer; };
struct extra_player_info_t { int teamnumber, frags, deaths; bool dead; };
extern hud_player_info_t g_PlayerInfoList[33];
extern extra_player_info_t g_PlayerExtraInfo[33];
struct Engine {
 const char *(*pfnGetCvarString)(const char *);
 float (*pfnGetCvarFloat)(const char *);
 void (*pfnDrawConsoleStringLen)(const char *,int *,int *);
 void (*pfnDrawSetTextColor)(float,float,float);
 int (*pfnDrawConsoleString)(int,int,const char *);
 const char *(*PlayerInfo_ValueForKey)(int,const char *);
};
extern Engine gEngfuncs;
struct Hud { char m_szServerName[256]; };
extern Hud gHUD;
extern int ScreenHeight, ScreenWidth;
void FillRGBA(int,int,int,int,int,int,int,int);
void FillRGBABlend(int,int,int,int,int,int,int,int);
class CHudScoreboard { public: void GetAllPlayersInfo() {} int DrawCzmScoreboard(); };
'''
HARNESS = r'''
#include "hud.h"
#include "@TAGS@"
#include <cstdio>
#include <cstdlib>
#include <cstring>
hud_player_info_t g_PlayerInfoList[33];
extra_player_info_t g_PlayerExtraInfo[33];
Hud gHUD;
int xstart,xend,ystart,yend,ScreenHeight,ScreenWidth,fh;
float style;
int cr,cg,cb;
const char *lang;
const char *String(const char *) { return lang; }
float Float(const char *) { return style; }
void Len(const char *s,int *w,int *h) {
 int n=0;for(;*s;s++) if((static_cast<unsigned char>(*s)&0xc0)!=0x80)n++;
 *w=n*fh/2;*h=fh;
}
void Color(float r,float g,float b) { cr=r*255;cg=g*255;cb=b*255; }
int Text(int x,int y,const char *s) { int w,h;Len(s,&w,&h);printf("T\t%d\t%d\t%d\t%d\t%d\t%d\t%s\n",x,y,w,cr,cg,cb,s);return x+w; }
const char *Bot(int i,const char *) { return i==3?"1":"0"; }
bool CZM_DrawTabAvatar(int,bool,int,int,int) { return true; }
void CZM_TabProfilesBeginDraw() {}
void CZM_TabProfileRow(int,bool,int,int,int,int) {}
// the LVL MOD tags of our servers: with CZM_TEST_TAGS every other player wears one
CzmTag tags[33];
const CzmTag *CZM_TagFor(int i) {
 if(!getenv("CZM_TEST_TAGS")||i%2==0) return nullptr;
 tags[i].lvl=i*40;tags[i].wr=52;strcpy(tags[i].prefix,i%3?"Зомбоубийца":"X");tags[i].r=0;tags[i].g=255;tags[i].b=170;
 strcpy(tags[i].priv,i%5==1?"PREMIUM":"");return &tags[i];
}
void CZM_LevelColor(int,int *r,int *g,int *b) { *r=255;*g=136;*b=0; }
Engine gEngfuncs={String,Float,Len,Color,Text,Bot};
void FillRGBA(int x,int y,int w,int h,int r,int g,int b,int a) { printf("R\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n",x,y,w,h,r,g,b,a); }
void FillRGBABlend(int x,int y,int w,int h,int r,int g,int b,int a) { FillRGBA(x,y,w,h,r,g,b,a); }
int main(int argc,char **argv) {
 style=atof(argv[1]);int count=atoi(argv[2]);ScreenWidth=atoi(argv[3]);ScreenHeight=atoi(argv[4]);fh=atoi(argv[5]);lang=argv[6];
 xstart=ScreenWidth*.06f;xend=ScreenWidth-xstart;ystart=ScreenHeight*.06f;yend=ScreenHeight*.92f;
 strcpy(gHUD.m_szServerName,"CZM / ZOMBIE ESCAPE");
 char names[33][256];
 for(int i=1;i<=count;i++) {
  snprintf(names[i],sizeof(names[i]),i==32?"^1P%02d\n\\r":"P%02d",i);
  if(argc>7 && i==1) snprintf(names[i],sizeof(names[i]),"^1ОченьДлинноеИмяИгрокаОченьДлинноеИмяИгрокаОченьДлинноеИмяИгрока");
  g_PlayerInfoList[i]={names[i],i==2?250:42,i==2};
  g_PlayerExtraInfo[i]={i==count?2:1,33-i,i,i%3==0};
 }
 CHudScoreboard board;return board.DrawCzmScoreboard()==1?0:1;
}
'''


class ScoreboardStylesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('g++'):
            raise unittest.SkipTest('requires g++')
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / 'hud.h').write_text(STUB)
        for name in ['cl_util.h', 'draw_util.h']:
            (root / name).write_text('')
        (root / 'main.cpp').write_text(HARNESS.replace('@TAGS@', str(ROOT / 'cl_dll/hud/czm_tags.h')))
        cls.exe = root / 'scoreboard'
        subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Wno-unused-parameter', '-I', str(root),
                        str(ROOT / 'cl_dll/hud/czm_scoreboard.cpp'), str(root / 'main.cpp'), '-o', str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def draw(cls, style, count, width, height, font, lang='ru', long_name=False, tags=False):
        env = dict(os.environ)
        env.pop('CZM_TEST_TAGS', None)
        if tags:
            env['CZM_TEST_TAGS'] = '1'
        result = subprocess.run([str(cls.exe), str(style), str(count), str(width), str(height), str(font), lang] +
                                (['long'] if long_name else []), capture_output=True, text=True, check=True, env=env)
        return [line.split('\t') for line in result.stdout.splitlines()]

    def test_every_player_fits_once_without_overlapping(self):
        for style, tags in [(0, False), (1, False), (2, False), (-1, False), (9, False), (0, True), (1, True), (2, True)]:
            for count in [0, 1, 8, 10, 11, 16, 31, 32]:
                for width, height, font in [(640, 360, 12), (960, 540, 16), (1536, 716, 18), (1280, 720, 24)]:
                    with self.subTest(style=style, tags=tags, count=count, width=width, font=font):
                        calls = self.draw(style, count, width, height, font, tags=tags)
                        players = [c for c in calls if c[0] == 'T' and re.fullmatch(r'P\d{2}', c[-1])]
                        self.assertEqual(sorted(c[-1] for c in players), ['P%02d' % i for i in range(1, count + 1)])
                        for c in calls:
                            x, y, w = map(int, c[1:4]); h = int(c[4]) if c[0] == 'R' else font
                            self.assertGreaterEqual(x, 0); self.assertGreaterEqual(y, 0)
                            self.assertGreaterEqual(w, 0); self.assertGreaterEqual(h, 0)
                            self.assertLessEqual(x + w, width); self.assertLessEqual(y + h, height)
                        texts = [c for c in calls if c[0] == 'T' and int(c[3]) > 0]
                        for i, a in enumerate(texts):
                            ax, ay, aw = map(int, a[1:4])
                            for b in texts[i+1:]:
                                bx, by, bw = map(int, b[1:4])
                                self.assertTrue(ax + aw <= bx or bx + bw <= ax or ay + font <= by or by + font <= ay)

    def test_custom_styles_differ_and_utf8_stays_valid(self):
        self.assertEqual(self.draw(-1, 8, 1536, 716, 18), self.draw(0, 8, 1536, 716, 18))
        self.assertEqual(self.draw(9, 8, 1536, 716, 18), self.draw(2, 8, 1536, 716, 18))
        drawings = [self.draw(style, 8, 1536, 716, 18, 'en', True) for style in range(3)]
        self.assertEqual(len({repr(x) for x in drawings}), 3)
        for calls in drawings:
            text = [c[-1] for c in calls if c[0] == 'T']
            self.assertTrue(any('Очень' in x for x in text))
            self.assertTrue(any(x.endswith('...') for x in text))
            self.assertFalse(any('^1' in x or '\\r' in x for x in text))

    def test_tags_show_level_prefix_and_privilege(self):
        calls = self.draw(0, 8, 1536, 716, 18, tags=True)
        text = [c[-1] for c in calls if c[0] == 'T']
        self.assertIn('LVL 40 · 52%', text)
        self.assertIn('PREMIUM', text)
        self.assertTrue(any(x.startswith('[Зомбоубийца]') for x in text))
        level = [c for c in calls if c[0] == 'T' and c[-1] == 'LVL 40 · 52%'][0]
        self.assertEqual(level[4:7], ['255', '136', '0'])
        self.assertEqual(text, [c[-1] for c in self.draw(0, 8, 1536, 716, 18, tags=True) if c[0] == 'T'])
        self.assertNotIn('LVL 40 · 52%', [c[-1] for c in self.draw(0, 8, 1536, 716, 18) if c[0] == 'T'])

    def test_optional_geometry_preview(self):
        output = os.environ.get('CZM_SCOREBOARD_PREVIEW')
        if output:
            import json
            Path(output).mkdir(parents=True, exist_ok=True)
            for style in range(3):
                Path(output, 'tab-%d.json' % style).write_text(json.dumps(self.draw(style, 32, 1536, 716, 18), ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
