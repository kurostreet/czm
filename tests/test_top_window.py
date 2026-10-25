"""Run the native Top 100 window: the three first, the list, the pinned own place, taps to profiles."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_moderation_window import STUB as MODERATION_STUB, HARNESS as MODERATION_HARNESS
from test_tab_avatars import VECTOR, STRING
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
STUB = MODERATION_STUB + r'''
unsigned CZM_TopColor(int);const char*CZM_TopCrown(int);int CZM_TopTagWidth(int,int);int CZM_DrawTopTag(int,int,int,int);
void CZM_FormatPlaytime(int,char*,size_t);void CZM_OpenTop();
'''
HARNESS = MODERATION_HARNESS + r'''
static int profileOpened,tops;
void CZM_OpenProfile(int id){profileOpened=id;}
void CZM_CleanName(const char*in,char*out,size_t n){Q_strncpy(out,in,n);}
unsigned CZM_TopColor(int place){return place==1?PackRGBA(255,206,84,255):place<=10?PackRGBA(231,187,96,255):PackRGBA(176,188,204,255);}
const char*CZM_TopCrown(int place){return place<=3?"gfx/czm/ui/icon_crown_royal.png":"gfx/czm/ui/icon_crown_top.png";}
int CZM_TopTagWidth(int place,int h){return place>=1&&place<=100?h*4:0;}
int CZM_DrawTopTag(int x,int y,int h,int place){if(place<1||place>100)return 0;tops++;UI_FillRect(x,y,h*4,h,CZM_TopColor(place));return h*4;}
void CZM_FormatPlaytime(int s,char*out,size_t n){if(s>=3600)snprintf(out,n,"%d ч %d мин",s/3600,s/60%60);else snprintf(out,n,"%d мин",s/60);}
'''
SCENARIOS = r'''
static bool inside(const CzmRect&a,const CzmRect&b){return a.w>0&&a.h>0&&a.x>=b.x&&a.y>=b.y&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h;}
static bool overlap(const CzmRect&a,const CzmRect&b){return a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;}
static void point(const CzmRect&r){cursorX=r.x+r.w/2;cursorY=r.y+r.h/2;uiStatic.cursorY=cursorY;}
static void tap(CCzmTop&w,const CzmRect&r){w.Layout();point(r);w.KeyDown(1);w.KeyUp(1);}
static std::string board(int count,int mePlace,int meSeconds,int behind){
 std::string s="{\"top\":[";
 for(int i=1;i<=count;i++){char item[300];snprintf(item,sizeof(item),"%s{\"place\":%d,\"id\":%d,\"nick\":\"%s\",\"avatar\":\"%d\",\"seconds\":%d,\"online\":%s%s}",
  i>1?",":"",i,100+i,i==1?"Kuro":i==2?"Hunter":"Player",i%10,500000-i*3000,i%3?"true":"false",i==1?",\"role\":\"support\"":"");s+=item;}
 s+="],\"players\":"+std::to_string(count+400);
 if(mePlace){char me[160];snprintf(me,sizeof(me),",\"me\":{\"place\":%d,\"seconds\":%d%s}",mePlace,meSeconds,behind?(",\"behind\":"+std::to_string(behind)).c_str():"");s+=me;}
 return s+"}";
}
int main(int argc,char**argv){
 auto&w=*menu_czmtop;
 CZM_OpenTop();assert(w.m_open&&stack.Current()==&w&&lastUrl=="/api/v1/top"&&lastKey==key);
 w.Draw();assert(!w.m_loaded); // loading
 replies[w.m_request]={200,board(100,489,44280,120000)};w.Draw();
 assert(w.m_loaded&&w.m_count==100&&w.m_rows[0].support&&!w.m_rows[1].support&&w.m_hasMe&&w.m_mePlace==489&&w.m_meBehind==120000);
 for(auto size:{std::pair<int,int>{1536,716},{960,540},{800,360},{2960,1440},{640,320},{1024,768}})for(int lang=0;lang<2;lang++){
  ScreenWidth=size.first;ScreenHeight=size.second;russian=lang==0;w.Layout();
  assert(w.m_panel.x>=0&&w.m_panel.y>0&&w.m_panel.x+w.m_panel.w<=ScreenWidth&&w.m_panel.y+w.m_panel.h<ScreenHeight);
  for(int i=0;i<3;i++){assert(inside(w.m_podium[i],w.m_panel));for(int k=0;k<i;k++)assert(!overlap(w.m_podium[i],w.m_podium[k]));
   assert(!overlap(w.m_podium[i],w.m_clip)&&!overlap(w.m_podium[i],w.m_back));point(w.m_podium[i]);assert(w.Hit()==w.PODIUM+i);}
  // the winner stands in the middle, a little higher than the second and the third
  assert(w.m_podium[1].x<w.m_podium[0].x&&w.m_podium[0].x<w.m_podium[2].x&&w.m_podium[0].y<w.m_podium[1].y);
  assert(inside(w.m_me,w.m_panel)&&!overlap(w.m_me,w.m_clip)&&w.m_clip.h>w.rowH);
  point(w.m_me);assert(w.Hit()==w.ME);
  point(w.RowRect(0));assert(w.Hit()==w.ROW);
  assert(w.m_maxScroll==97*w.rowH-w.m_clip.h);
  tops=0;tags=0;w.Draw();assert(tags>=1); // the SUPPORT tag of the first place
 }
 ScreenWidth=1536;ScreenHeight=716;russian=true;w.Layout();
 // taps open profiles: the first place, a row deep in the list after scrolling, the own card
 tap(w,w.m_podium[0]);assert(profileOpened==101&&w.m_open);
 w.m_scroll=w.m_maxScroll;w.Layout();CzmRect last=w.RowRect(96);assert(last.y+last.h<=w.m_clip.y+w.m_clip.h+w.rowH);
 point(CZM_Rect(last.x,std::max(last.y,w.m_clip.y),last.w,std::min(last.h,w.m_clip.y+w.m_clip.h-last.y)));assert(w.Hit()==w.ROW+96);
 w.KeyDown(1);w.KeyUp(1);assert(profileOpened==200);
 tap(w,w.m_me);assert(profileOpened==9);
 // a drag scrolls and does not open anyone
 w.m_scroll=0;w.Layout();point(w.RowRect(2));profileOpened=0;w.KeyDown(1);uiStatic.cursorY-=w.rowH*2;cursorY=uiStatic.cursorY;w.MouseMove(cursorX,cursorY);w.KeyUp(1);
 assert(profileOpened==0&&w.m_scroll>0);
 // a small board: no invented players, nothing to scroll; the own place inside the hundred
 w.Activate(w.REFRESH);replies[w.m_request]={200,board(2,2,7200,0)};w.Draw();
 assert(w.m_count==2&&w.ListCount()==0&&w.m_maxScroll==0&&w.m_mePlace==2);
 point(w.m_podium[2]);assert(w.Hit()!=w.PODIUM+2);w.Draw();
 // nobody has played yet; a failed refresh keeps what was shown
 w.Activate(w.REFRESH);replies[w.m_request]={200,"{\"top\":[],\"players\":0}"};w.Draw();assert(w.m_loaded&&!w.m_count&&!w.m_hasMe);
 w.Activate(w.REFRESH);replies[w.m_request]={0,""};w.Draw();assert(w.m_loaded&&!w.m_failed);
 // outside and Escape close it
 cursorX=1;cursorY=uiStatic.cursorY=1;assert(w.Hit()==w.BACK);w.KeyDown(27);assert(!w.m_open);
 if(argc>1){
  std::string view=argv[1];russian=view.find("en")==std::string::npos;
  CZM_OpenTop();w.m_openedAt=-10;
  replies[w.m_request]={200,view.rfind("in",0)==0?board(100,7,420000,0):board(100,489,44280,120000)};
  trace=true;w.Draw();
 }
 puts("TOP_WINDOW_OK");
}
'''


class TopWindowTests(unittest.TestCase):
    def test_podium_list_own_place_and_taps(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "utlvector.h").write_text(VECTOR)
            (p / "utlstring.h").write_text(STRING)
            (p / "stub.h").write_text(STUB)
            for name in ["extdll_menu.h", "BaseMenu.h", "Utils.h", "Framework.h", "Scissor.h", "keydefs.h", "CzmMenu.h"]:
                (p / name).write_text('#include "stub.h"\n')
            for name in ["CzmJson.h", "CzmDesign.h"]:
                (p / name).write_text((ROOT / "czm/menu" / name).read_text())
            helpers = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
            wrapping = "\n".join(function(helpers, signature) for signature in
                                 ["static bool CZM_IsLineBreak(", "int CZM_WrapText(", "void CZM_WrapLine("])
            source = (ROOT / "czm/menu/CzmTop.cpp").read_text()
            (p / "main.cpp").write_text("#include <cmath>\n" + HARNESS + wrapping + source + SCENARIOS)
            exe = p / "top"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", "-Wno-unused-function", "-Wno-unused-variable", "-I" + folder,
                            str(p / "main.cpp"), str(ROOT / "czm/menu/CzmJson.cpp"), "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn("TOP_WINDOW_OK", result.stdout)
            out = os.environ.get("CZM_TOP_PREVIEW_DIR")
            if out:
                dest = Path(out); dest.mkdir(parents=True, exist_ok=True)
                for view in ["out", "in", "out-en"]:
                    r = subprocess.run([str(exe), view], capture_output=True, text=True, check=True)
                    (dest / (view + ".tsv")).write_text(r.stdout)


if __name__ == "__main__":
    unittest.main()
