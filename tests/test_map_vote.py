"""The next-map vote window: CzmVote messages, the czm_vote ballot and when the window opens."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def build(source):
    with tempfile.TemporaryDirectory(prefix="czm-map-vote-") as folder:
        path = Path(folder)
        (path / "main.cpp").write_text(source)
        subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", "-I" + str(ROOT / "common"),
                        str(path / "main.cpp"), "-o", str(path / "run")], check=True)
        subprocess.run([str(path / "run")], check=True)


HUD_STUB = r'''
#include <cassert>
#include <cstring>
#include <map>
#include <string>
#include <vector>
#include "czm_vote.h"
std::map<std::string,std::string> cvars;
int(*handler)(const char*,int,void*);
const char *Get(const char *key){return cvars[key].c_str();}
void Set(const char *key,const char *value){cvars[key]=value;}
void Hook(const char *name,int(*f)(const char*,int,void*)){assert(!strcmp(name,"CzmVote"));handler=f;}
struct {void(*pfnHookUserMsg)(const char*,int(*)(const char*,int,void*));void(*Cvar_Set)(const char*,const char*);
const char *(*pfnGetCvarString)(const char*);} gEngfuncs={Hook,Set,Get};
struct BufferReader{const unsigned char *p;int pos=0,size;BufferReader(const char*,void *b,int n):p((unsigned char*)b),size(n){}
int ReadByte(){assert(pos<size);return p[pos++];}
int ReadLong(){int v=0;for(int i=0;i<4;i++)v|=ReadByte()<<(8*i);return v;}};
void CZM_VoteInit(void);void CZM_VoteReset(void);
'''

HUD_TEST = r'''
typedef std::vector<unsigned char> Packet;
void Send(const Packet &p){Packet copy=p;handler("CzmVote",(int)copy.size(),copy.data());}
void Long(Packet &p,int v){for(int i=0;i<4;i++)p.push_back((v>>(8*i))&255);}
Packet State(int flags,int count,int own,int seconds,int voters,int players,int session){
    Packet p={1,(unsigned char)flags,(unsigned char)count,(unsigned char)(own+1),(unsigned char)seconds,(unsigned char)voters,(unsigned char)players};
    Long(p,session);return p;}
Packet Rows(std::vector<std::pair<int,int>> rows,std::vector<std::string> maps){
    Packet p={2};
    for(size_t i=0;i<rows.size();i++){
        p.push_back(rows[i].first);p.push_back(rows[i].second);
        for(char c:maps[i]){p.push_back(c);}
        p.push_back(0);
    }
    return p;}
CzmVote::Ballot Ballot(){CzmVote::Ballot b;assert(CzmVote::Parse(cvars["czm_vote"].c_str(),b));return b;}
int main(){
CZM_VoteInit();assert(cvars["czm_vote"].empty());
// The state comes first; the window gets the ballot only when every row has arrived.
Send(State(CzmVote::AUTO,3,-1,60,0,4,123456));assert(cvars["czm_vote"].empty());
Send(Rows({{7,2},{0,1}},{"zm_defense","zm_3rooms"}));assert(cvars["czm_vote"].empty());
Send(Rows({{4,0}},{"zm_zombust"}));
CzmVote::Ballot b=Ballot();
assert(b.session==123456&&b.count==3&&b.own==-1&&b.seconds==60&&b.players==4&&b.flags==CzmVote::AUTO&&b.opens==0);
assert(b.rows[0].number==7&&b.rows[0].votes==2&&!strcmp(b.rows[0].map,"zm_defense"));
assert(b.rows[2].number==4&&!strcmp(b.rows[2].map,"zm_zombust")&&CzmVote::Find(b,0)==1&&CzmVote::Find(b,9)==-1);
const int serial=b.serial;
// The remaining time each second keeps the rows.
Packet t={4,41,2,5};Long(t,123456);Send(t);b=Ballot();
assert(b.seconds==41&&b.voters==2&&b.players==5&&b.count==3&&b.serial>serial);
Packet stale={4,10,0,0};Long(stale,999);Send(stale);assert(Ballot().seconds==41);
// The player's own vote and a later /votemap: "open now" is counted, never a lasting flag.
Send(State(CzmVote::AUTO|CzmVote::OPEN,3,7,40,3,5,123456));Send(Rows({{7,3},{0,1},{4,0}},{"zm_defense","zm_3rooms","zm_zombust"}));
b=Ballot();assert(b.own==7&&b.opens==1&&b.voters==3);
Send(State(CzmVote::AUTO,3,7,39,3,5,123456));Send(Rows({{7,3},{0,1},{4,0}},{"zm_defense","zm_3rooms","zm_zombust"}));
assert(Ballot().opens==1);
// Rows a client cannot show are never published.
const std::string before=cvars["czm_vote"];
Send(State(CzmVote::AUTO,1,-1,30,0,1,123456));Send(Rows({{1,0}},{"../evil"}));assert(cvars["czm_vote"]==before);
Send(State(CzmVote::AUTO,1,-1,30,0,1,123456));Packet cut={2,1,0,'z','m'};Send(cut);assert(cvars["czm_vote"]==before);
// Rows without a state are ignored; so is a close for another vote.
Send(Rows({{1,0}},{"zm_mini_re"}));assert(cvars["czm_vote"]==before);
Packet other={3};Long(other,5);Send(other);assert(cvars["czm_vote"]==before);
Send(State(CzmVote::AUTO,3,7,39,3,5,123456));Send(Rows({{7,3},{0,1},{4,0}},{"zm_defense","zm_3rooms","zm_zombust"}));
Packet close={3};Long(close,123456);Send(close);assert(cvars["czm_vote"].empty());
Send(t);assert(cvars["czm_vote"].empty());
// A new map or server forgets the vote.
Send(State(0,1,-1,60,0,1,77));Send(Rows({{0,0}},{"zm_tc_death"}));assert(!cvars["czm_vote"].empty());
CZM_VoteReset();assert(cvars["czm_vote"].empty());
return 0;}
'''


class MapVoteTests(unittest.TestCase):
    def test_ballot_text_round_trip_and_rejections(self):
        build(r'''
#include <cassert>
#include <cstring>
#include "czm_vote.h"
int main(){
using namespace CzmVote;
Ballot b;b.serial=3;b.session=99;b.flags=AUTO;b.opens=2;b.seconds=42;b.own=5;b.voters=9;b.players=14;b.count=2;
b.rows[0].number=5;b.rows[0].votes=5;strcpy(b.rows[0].map,"zm_zombust");
b.rows[1].number=0;b.rows[1].votes=0;strcpy(b.rows[1].map,"zm_battleground_extreme");
char text[512];Format(b,text,sizeof(text));
Ballot c;assert(Parse(text,c));
assert(c.serial==3&&c.session==99&&c.flags==AUTO&&c.opens==2&&c.seconds==42&&c.own==5&&c.voters==9&&c.players==14&&c.count==2);
assert(c.rows[1].number==0&&!strcmp(c.rows[1].map,"zm_battleground_extreme"));
assert(!Parse("",c)&&!Parse("1 2 1 0 60 -1 0 1 0\n",c));
assert(!Parse("1 2 1 0 60 -1 0 1 2\n0 0 zm_a\n",c));
assert(!Parse("1 2 1 0 60 -1 0 1 1\n0 0 zm/a\n",c));
assert(!Parse("1 2 1 0 999 -1 0 1 1\n0 0 zm_a\n",c));
char name[32];assert(MapName("zm_ark_deko2_v1",name,sizeof(name))&&!MapName("zm a",name,sizeof(name))&&!MapName("",name,sizeof(name)));
assert(!MapName("zm_name_that_is_far_too_long_for_a_map",name,sizeof(name)));
char clock[16];Clock(42,clock,sizeof(clock));assert(!strcmp(clock,"0:42"));Clock(60,clock,sizeof(clock));assert(!strcmp(clock,"1:00"));
return 0;}
''')

    def test_window_opens_once_per_vote_and_again_only_when_asked(self):
        build(r'''
#include <cassert>
#include "czm_vote.h"
int main(){
using namespace CzmVote;
Opening o;Ballot b;b.count=1;b.session=10;b.flags=AUTO;b.opens=0;
assert(o.Next(b));                      // a new vote the popup setting allows
assert(!o.Next(b));b.serial++;assert(!o.Next(b)); // updates of the same vote, also after the player closed it
b.opens=1;assert(o.Next(b));assert(!o.Next(b));   // /votemap
b.session=11;b.flags=0;assert(!o.Next(b));        // the next vote with the popup turned off
b.opens=2;assert(o.Next(b));                      // still opens when asked
Opening late;Ballot j;j.count=1;j.session=12;j.flags=AUTO|OPEN;j.opens=3;assert(late.Next(j));
return 0;}
''')

    def test_list_follows_the_finger_flings_and_tells_taps(self):
        build(r"""
#include <cassert>
#include <cmath>
#include "czm_scroll.h"
using CzmScroll::List;
int main(){
const double f=1.0/60;
// A tap that wobbles less than the touch slop is a tap and does not move the list.
List l;l.slop=24;l.SetMax(1000);
l.Press(500,0);l.Move(510,0.02);l.Move(495,0.04);assert(l.Release(0.06)&&l.pos==0);
// A drag starts where the slop ends: no jump, then the list follows the finger 1:1.
l.Press(800,1);l.Move(790,1.016);assert(l.pos==0&&!l.dragging);
l.Move(770,1.032);assert(l.dragging&&l.pos==0);
l.Move(700,1.048);assert(std::fabs(l.pos-70)<0.01f);
l.Move(600,1.064);assert(std::fabs(l.pos-170)<0.01f);
// Lifted while moving: a drag is not a tap and the flick goes on, slowing down to a stop.
assert(!l.Release(1.070));assert(l.velocity>1000);
float last=l.pos;double t=0;
for(;t<4&&l.velocity!=0;t+=f){l.Step(f);assert(l.pos>=last&&l.pos<=l.max);last=l.pos;}
assert(l.velocity==0&&t<3.5&&l.pos>300);
// A finger that stopped before lifting does not fling.
List s;s.slop=24;s.SetMax(1000);s.Press(800,0);s.Move(700,0.016);s.Move(600,0.032);
assert(!s.Release(0.3));const float kept=s.pos;for(int i=0;i<60;i++)s.Step(f);assert(s.pos==kept);
// A finger that catches a moving list stops it and is not a tap.
List c;c.SetMax(1000);c.velocity=900;c.Step(f);c.Press(400,0);assert(c.velocity==0);
assert(!c.Release(0.05));const float caught=c.pos;c.Step(f);assert(c.pos==caught);
// Revealing a row glides there without overshooting.
List r;r.SetMax(1000);r.Reveal(900,1000,500);assert(r.aiming&&r.target==500);
float prev=0;int frames=0;while(r.aiming&&frames<120){r.Step(f);assert(r.pos>=prev&&r.pos<=500);prev=r.pos;frames++;}
assert(r.pos==500&&frames<40);
r.Reveal(600,700,500);assert(!r.aiming);                 // already in view: nothing moves
// The wheel and drags never leave the list.
r.Wheel(5000);for(int i=0;i<120;i++)r.Step(f);assert(r.pos==1000);
List e;e.slop=10;e.SetMax(300);e.Press(100,0);e.Move(0,0.01);e.Move(-900,0.02);assert(e.pos==300);
e.Release(0.021);for(int i=0;i<60;i++)e.Step(f);assert(e.pos==300&&e.velocity==0);
// A reordered row glides to its new place.
float g=5;int n=0;while(g!=0&&n<60){const float next=CzmScroll::Glide(g,0,f);assert(next<=g&&next>=0);g=next;n++;}
assert(g==0&&n<45);
return 0;}
""")

    def test_window_never_reorders_under_the_finger(self):
        window = (ROOT / "czm/menu/CzmMapVote.cpp").read_text()
        self.assertIn('#include "../../common/czm_scroll.h"', window)
        draw = window[window.index("void CCzmVoteWindow::Draw()"):]
        self.assertIn("if( !m_scroller.down && !m_barDrag )", draw)
        self.assertIn("if( m_orderWaiting ) TakeOrder();", draw)
        self.assertIn("m_scroller.Step( dt );", draw)
        # rows are hit where they are drawn and by map number, never by their place in the list
        self.assertIn("return HIT_ROW + m_view[i];", window)
        self.assertIn("m_selected = hit - HIT_ROW;", window)
        # the slider has its own strip beside the list, so a tap on a row never moves the list
        self.assertIn("const int barLeft = m_list.x + m_list.w + 1;", window)

    def test_hud_turns_messages_into_the_ballot(self):
        code = (ROOT / "cl_dll/hud/czm_vote.cpp").read_text()
        code = re.sub(r'#include "[^\"]+"\n', '', code)
        build(HUD_STUB + code + HUD_TEST)

    def test_client_reports_the_window_and_votes_by_map_number(self):
        menu = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
        self.assertIn('EngFuncs::CvarRegister( "czm_mapvote_ui", "1", 0 );', menu)
        self.assertIn('EngFuncs::CvarRegister( "czm_vote", "", FCVAR_PRIVILEGED );', menu)
        window = (ROOT / "czm/menu/CzmMapVote.cpp").read_text()
        self.assertIn('EngFuncs::ClientCmdF( false, "czm_vote_map %d\\n", m_selected );', window)
        # The window is modal like our other windows over the game: it never says otherwise.
        self.assertNotIn("Ходить", window)
        self.assertIn("/votemap", window)
        brand = (ROOT / "scripts/brand_mainui.py").read_text()
        self.assertLess(brand.index("CZM_DrawGameOverlay();"), brand.index("CZM_VoteFrame();"))
        self.assertIn("czm/menu/CzmMapVote.cpp", (ROOT / "cmake/CzmBranding.cmake").read_text())

    def test_vote_lives_for_one_connection(self):
        tags = (ROOT / "cl_dll/hud/czm_tags.cpp").read_text()
        self.assertIn("CZM_VoteInit();", tags)
        messages = (ROOT / "cl_dll/hud_msg.cpp").read_text()
        init = messages[messages.index("int CHud :: MsgFunc_InitHUD"):]
        init = init[:init.index("\n}\n")]
        reset = messages[messages.index("int CHud :: MsgFunc_ResetHUD"):]
        reset = reset[:reset.index("\n}\n")]
        self.assertIn("CZM_VoteReset();", init)
        self.assertNotIn("CZM_VoteReset", reset)


if __name__ == "__main__":
    unittest.main()
