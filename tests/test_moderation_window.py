"""Run the native SUPPORT moderation window: the panel, a player's card and the steps of an action."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from native_community_stub import STUB as COMMUNITY_STUB, HARNESS as COMMUNITY_HARNESS
from test_rules_window import STUB as RULES_STUB, HARNESS as RULES_HARNESS
from test_tab_avatars import VECTOR, STRING
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
STUB = RULES_STUB + r'''
void CZM_ModerationFrame();
'''
STUB += COMMUNITY_STUB
HARNESS = RULES_HARNESS.replace("static void then(){thenCalls++;}", "") + r'''
static bool support=true,ready=true;static int me=9,tags;
bool CZM_OnlineSupport(){return support;}bool CZM_OnlineReady(){return ready;}int CZM_OnlinePlayer(){return me;}
int CZM_SupportTagWidth(int h){return h*4;}
int CZM_DrawSupportTag(int x,int y,int h){tags++;UI_FillRect(x,y,h*4,h,PackRGBA(196,150,62,255));return h*4;}
static int keys;void CZM_NetNewKey(char*out,size_t n){snprintf(out,n,"moderation-nonce-%03d",++keys);}
const char*CZM_AvatarFor(const char*,int){return "gfx/czm/ui/avatar.png";}
int CZM_CountBadgeWidth(int count,int h){return count>0?h*(count>9?2:1):0;}
void CZM_DrawCountBadge(const CzmRect&r,int){UI_FillRect(r.x,r.y,r.w,r.h,PackRGBA(229,63,77,255));}
static bool typing;void UI_EnableTextInput(bool on){typing=on;}
'''
HARNESS += COMMUNITY_HARNESS
SCENARIOS = r'''
static bool inside(const CzmRect&a,const CzmRect&b){return a.w>0&&a.h>0&&a.x>=b.x&&a.y>=b.y&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h;}
static bool overlap(const CzmRect&a,const CzmRect&b){return a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;}
static void point(const CzmRect&r){cursorX=r.x+r.w/2;cursorY=r.y+r.h/2;uiStatic.cursorY=cursorY;}
static int hit(CCzmModeration&w,const CzmRect&r){w.Layout();point(r);return w.Hit();}
static void tap(CCzmModeration&w,const CzmRect&r){w.Layout();point(r);w.KeyDown(1);w.KeyUp(1);}
static void reply(CCzmModeration&w,int status,const char*body,bool write=false){replies[write?w.m_write:w.m_read]={status,body};w.Draw();}
static int action(CCzmModeration&w,const char*code){for(int i=0;i<w.m_visibleCount;i++)if(!strcmp(s_actions[w.m_visible[i]].code,code))return i;return -1;}
static const char*REPORTS="{\"reports\":[{\"id\":101,\"kind\":\"chat\",\"evidence\":\"ты никто, удали игру\",\"context\":\"chat_ru\",\"target\":{\"id\":8,\"nick\":\"Hunter\",\"avatar\":\"3\"},\"reporter\":12,\"reports_week\":3,\"created\":1792240000},"
 "{\"id\":102,\"kind\":\"lobby\",\"evidence\":\"Реклама читов\",\"context\":\"Реклама читов\",\"target\":{\"id\":15,\"nick\":\"Seller\",\"avatar\":\"\"},\"reporter\":12,\"reports_week\":1,\"created\":1792240100}],\"next\":-1}";
static const char*CARD="{\"target\":{\"id\":8,\"nick\":\"Hunter\",\"avatar\":\"3\"},\"role\":\"\",\"quote\":null,\"ban\":null,\"moderation\":{\"text\":null,\"voice\":{\"until\":1792300000,\"forever\":false,\"reason\":\"Крик\"},\"photo\":null},\"reports_week\":3}";
int main(int argc,char**argv){
 auto&w=*menu_czmmoderation;
 // Only SUPPORT opens it; the service checks the role on every request anyway.
 support=false;CZM_ModerationOpen();CZM_ModerationTarget(8,"Hunter");assert(!w.m_open&&!nextRequest);support=true;
 CZM_ModerationOpen();assert(w.m_open&&stack.Current()==&w&&w.m_page==PAGE_PANEL&&lastUrl=="/api/v1/moderation/summary"&&lastKey==key);
 reply(w,200,"{\"reports_open\":2,\"sanctions_active\":1}");assert(w.m_counts[0]==2&&w.m_counts[1]==1);
 assert(lastUrl=="/api/v1/moderation/reports?offset=0");reply(w,200,REPORTS);assert(w.m_rows.Count()==2&&w.m_loaded&&w.m_next==-1);
 for(auto size:{std::pair<int,int>{1536,716},{960,540},{800,360},{2960,1440},{640,320},{1024,768}})for(int lang=0;lang<2;lang++){
  ScreenWidth=size.first;ScreenHeight=size.second;russian=lang==0;w.Layout();
  assert(w.m_panel.x>=0&&w.m_panel.y>0&&w.m_panel.x+w.m_panel.w<=ScreenWidth&&w.m_panel.y+w.m_panel.h<ScreenHeight);
  for(int i=0;i<TAB_COUNT;i++){assert(inside(w.m_tabs[i],w.m_panel));if(i)assert(!overlap(w.m_tabs[i-1],w.m_tabs[i]));assert(hit(w,w.m_tabs[i])==w.TAB+i);}
  assert(inside(w.m_clip,w.m_panel)&&!overlap(w.m_clip,w.m_tabs[0])&&w.m_clip.h>w.RowHeight()*2);
  assert(hit(w,w.RowRect(0))==w.ROW&&hit(w,w.RowRect(1))==w.ROW+1&&hit(w,w.m_back)==w.BACK&&hit(w,w.m_refresh)==w.REFRESH);
  tags=0;w.Draw();assert(tags==1); // the header carries the SUPPORT tag
 }
 ScreenWidth=1536;ScreenHeight=716;russian=true;
 // A report opens the player's card with the reported words and the actions that fit it.
 tap(w,w.RowRect(0));assert(w.m_page==PAGE_TARGET&&w.m_report==101&&w.m_fromPanel&&!strcmp(w.m_quote,"ты никто, удали игру"));
 assert(lastUrl=="/api/v1/moderation/player/8?message=0&lobby_message=0");
 w.Visible();assert(!w.m_targetLoaded&&action(w,"delete_message")>=0&&action(w,"dismiss")>=0&&action(w,"close_lobby")<0);
 int requests=nextRequest;w.Activate(w.ACTION+action(w,"mute_text"));assert(w.m_page==PAGE_TARGET); // nothing before the card is there
 reply(w,200,CARD);assert(w.m_targetLoaded&&!w.m_targetStaff&&w.m_reportsWeek==3&&strstr(w.m_limits,"Голос отключён"));
 for(int i=0;i<w.m_visibleCount;i++){assert(inside(w.m_actionRects[i],w.m_panel));assert(!overlap(w.m_actionRects[i],w.m_card)&&!overlap(w.m_actionRects[i],w.m_quoteRect));
  for(int k=0;k<i;k++)assert(!overlap(w.m_actionRects[i],w.m_actionRects[k]));}
 // mute the chat for a week because of spam
 tap(w,w.m_actionRects[action(w,"mute_text")]);assert(w.m_page==PAGE_DURATION);w.Layout();
 assert(w.m_choice[3].w&&!w.m_choice[4].w); // no "forever" for a mute
 for(int i=0;i<4;i++){assert(inside(w.m_choice[i],w.m_panel));if(i)assert(!overlap(w.m_choice[i-1],w.m_choice[i]));}
 tap(w,w.m_choice[2]);assert(w.m_page==PAGE_REASON&&w.m_minutes==10080);
 tap(w,w.m_choice[2]);assert(w.m_page==PAGE_CONFIRM&&!strcmp(w.m_reason,"Спам и реклама")&&nextRequest==requests);
 w.Draw();tap(w,w.m_confirm);
 const std::string body=lastBody;
 assert(lastUrl=="/api/v1/moderation/act"&&body=="{\"target\":8,\"action\":\"mute_text\",\"minutes\":10080,\"reason\":\"Спам и реклама\",\"report\":101,\"nonce\":\"moderation-nonce-001\"}");
 // A lost answer: the same request with the same nonce, never a second sanction.
 tap(w,w.m_confirm);assert(lastBody==body&&nextRequest==requests+1); // still waiting: no second request
 reply(w,0,"",true);assert(w.m_page==PAGE_CONFIRM&&w.m_toastError&&!w.m_write);
 tap(w,w.m_confirm);assert(lastBody==body);
 reply(w,200,"{\"ok\":true,\"log\":5,\"until\":1792900000}",true);
 assert(w.m_page==PAGE_PANEL&&!w.m_report&&!w.m_toastError&&!strcmp(w.m_toast,"Чат отключён")&&lastUrl=="/api/v1/moderation/summary");
 reply(w,200,"{\"reports_open\":1,\"sanctions_active\":2}");assert(lastUrl=="/api/v1/moderation/reports?offset=0");
 reply(w,200,"{\"reports\":[],\"next\":-1}");assert(!w.m_rows.Count());
 // A lobby report can close the room; dismissing needs no reason.
 w.m_listTab=-1;w.Draw();reply(w,200,REPORTS);tap(w,w.RowRect(1));reply(w,200,"{\"target\":{\"id\":15,\"nick\":\"Seller\"},\"role\":\"\",\"moderation\":{},\"reports_week\":1}");
 w.Visible();assert(action(w,"close_lobby")>=0&&action(w,"delete_message")<0);
 w.Activate(w.ACTION+action(w,"dismiss"));assert(w.m_page==PAGE_CONFIRM);w.Activate(w.CONFIRM);
 assert(lastBody=="{\"target\":15,\"action\":\"dismiss\",\"reason\":\"\",\"report\":102,\"nonce\":\""+std::string(w.m_nonce)+"\"}");
 reply(w,409,"{\"error\":\"target\"}",true);assert(w.m_toastError&&strstr(w.m_toast,"другом игроке")&&w.m_page==PAGE_CONFIRM);
 w.KeyDown(27);assert(w.m_page==PAGE_TARGET);w.KeyDown(27);assert(w.m_page==PAGE_PANEL&&w.m_open);
 // Straight from a chat message: ban forever asks twice, and its own reason needs words.
 w.Hide();CZM_ModerationTarget(8,"Hunter",71,0,"ссылка на читы");assert(w.m_open&&!w.m_fromPanel&&lastUrl=="/api/v1/moderation/player/8?message=71&lobby_message=0");
 reply(w,200,"{\"target\":{\"id\":8,\"nick\":\"Hunter\"},\"role\":\"\",\"quote\":{\"message\":71,\"text\":\"ссылка на читы\",\"context\":\"chat_global\"},\"moderation\":{},\"reports_week\":0}");
 assert(!strcmp(w.m_context,"chat_global")&&action(w,"delete_message")>=0&&action(w,"dismiss")<0);
 w.Activate(w.ACTION+action(w,"ban"));w.Layout();assert(w.m_page==PAGE_DURATION&&w.m_choice[4].w);tap(w,w.m_choice[4]);assert(w.m_minutes==0);
 tap(w,w.m_choice[MOD_OWN_REASON]);assert(w.m_page==PAGE_REASON&&typing&&w.m_field.w&&w.m_nextRect.w);
 assert(inside(w.m_field,w.m_panel)&&!overlap(w.m_field,w.m_nextRect)&&!overlap(w.m_field,w.m_choice[5]));
 w.Char('o');w.Char('k');tap(w,w.m_nextRect);assert(w.m_page==PAGE_REASON&&w.m_toastError); // two letters are not a reason
 for(const char*c="Продажа читов";*c;c++){w.Char((unsigned char)*c);}
 w.KeyDown(8);w.Char(0xd0);w.Char(0xb2);
 w.KeyDown(13);assert(w.m_page==PAGE_CONFIRM&&!typing&&!strcmp(w.m_reason,"okПродажа читов"));
 requests=nextRequest;tap(w,w.m_confirm);assert(w.m_armed&&nextRequest==requests);w.Draw();
 tap(w,w.m_confirm);assert(nextRequest==requests+1&&lastBody.find("\"action\":\"ban\",\"minutes\":0")!=std::string::npos&&lastBody.find("\"message\":71")!=std::string::npos);
 reply(w,200,"{\"ok\":true,\"forever\":true}",true);assert(w.m_page==PAGE_TARGET&&lastUrl.find("message=71")!=std::string::npos);
 // after a ban the card is read again; a deleted message disappears from it
 reply(w,200,"{\"target\":{\"id\":8,\"nick\":\"Hunter\"},\"role\":\"\",\"quote\":null,\"ban\":{\"until\":0,\"forever\":true,\"reason\":\"x\"},\"moderation\":{},\"reports_week\":0}");
 assert(w.m_messageGone&&strstr(w.m_limits,"Блокировка навсегда"));w.Visible();assert(action(w,"delete_message")<0);
 // Staff are never moderated from here.
 w.Hide();CZM_ModerationTarget(12,"Helper");reply(w,200,"{\"target\":{\"id\":12,\"nick\":\"Helper\"},\"role\":\"support\",\"moderation\":{}}");
 assert(w.m_targetStaff&&w.m_visibleCount==0);w.Draw();
 w.KeyDown(27);assert(!w.m_open); // opened straight: back closes
 // Own account: the panel; restrictions are lifted with a second tap.
 CZM_ModerationTarget(me,"Kuro");assert(w.m_open&&w.m_page==PAGE_PANEL);reply(w,200,"{\"reports_open\":0,\"sanctions_active\":1}");reply(w,200,"{\"reports\":[],\"next\":-1}");
 tap(w,w.m_tabs[TAB_SANCTIONS]);assert(w.m_tab==TAB_SANCTIONS);w.Draw();assert(lastUrl=="/api/v1/moderation/sanctions");
 reply(w,200,"{\"sanctions\":[{\"id\":31,\"kind\":\"text\",\"target\":{\"id\":8,\"nick\":\"Hunter\"},\"until\":1792900000,\"forever\":false,\"reason\":\"Спам\",\"created\":1792240000}]}");
 assert(w.m_rows.Count()==1&&w.m_next==-1);w.Layout();
 const CzmRect lift=w.LiftRect(w.RowRect(0));assert(inside(lift,w.RowRect(0))&&hit(w,lift)==w.LIFT);
 requests=nextRequest;tap(w,lift);assert(w.m_liftArmed==31&&nextRequest==requests);w.Draw();
 tap(w,lift);assert(lastUrl=="/api/v1/moderation/sanctions/31/lift"&&lastBody.find("\"nonce\":\"moderation-nonce-")==1);
 reply(w,200,"{\"ok\":true}",true);assert(!strcmp(w.m_toast,"Ограничение снято")&&lastUrl=="/api/v1/moderation/summary");
 reply(w,200,"{\"reports_open\":0,\"sanctions_active\":0}");assert(lastUrl=="/api/v1/moderation/sanctions");
 // The journal pages by "next" and shows who did what.
 tap(w,w.m_tabs[TAB_HISTORY]);reply(w,200,"{\"sanctions\":[]}");w.Draw();assert(lastUrl=="/api/v1/moderation/history?offset=0");
 reply(w,200,"{\"history\":[{\"id\":5,\"action\":\"mute_text\",\"target\":{\"id\":8,\"nick\":\"Hunter\"},\"moderator\":{\"id\":9,\"nick\":\"Kuro\"},\"reason\":\"Спам\",\"created\":1792240000},"
  "{\"id\":6,\"action\":\"lift\",\"target\":{\"id\":8,\"nick\":\"Hunter\"},\"moderator\":{\"id\":9,\"nick\":\"Kuro\"},\"reason\":\"text\",\"created\":1792240500}],\"next\":30}");
 assert(w.m_rows.Count()==2&&w.Rows()==3&&!strcmp(w.m_rows[1].text,"Чат отключён")&&!strcmp(w.m_rows[0].moderator,"Kuro"));
 w.Draw();tap(w,w.RowRect(2));assert(lastUrl=="/api/v1/moderation/history?offset=30");reply(w,200,"{\"history\":[],\"next\":-1}");assert(w.Rows()==2);
 // Errors speak plainly; the role went away: the window closes itself.
 w.Activate(w.REFRESH);reply(w,403,"{\"error\":\"forbidden\"}");assert(w.m_toastError&&strstr(w.m_toast,"доступа"));
 support=false;w.Draw();assert(!w.m_open);support=true;

 // A moderator has reversible chat actions, requires a reason even for dismissals,
 // and can act on cosmetic role holders when the API says they are not protected.
 actorRole="moderator";
 w.Hide();CZM_ModerationTarget(8,"Tester",71,0,"message");
 reply(w,200,"{\"target\":{\"id\":8,\"nick\":\"Tester\"},\"role\":\"tester\",\"protected\":false,\"quote\":{\"message\":71,\"text\":\"message\",\"context\":\"global\"},\"moderation\":{}}");
 assert(!w.m_targetStaff&&action(w,"delete_message")>=0&&action(w,"ban")>=0);
 assert(action(w,"remove_avatar")<0&&action(w,"restrict_photo")<0&&action(w,"close_lobby")<0);
 w.Activate(w.ACTION+action(w,"delete_message"));assert(w.m_page==PAGE_REASON&&w.NeedsReason());
 w.m_report=102;strcpy(w.m_reportKind,"lobby");w.Go(PAGE_TARGET);w.Visible();
 w.Activate(w.ACTION+action(w,"dismiss"));assert(w.m_page==PAGE_REASON&&w.NeedsReason());
 assert(strstr(ErrorText("moderator_paused",403),"приостановлены"));
 w.Hide();actorRole="support";

 // An answer that comes after closing is still collected.
 CZM_ModerationOpen();int pending=w.m_read;w.Hide();replies[pending]={200,"{}"};CZM_ModerationFrame();assert(!w.m_read&&!w.m_open);
 if(argc>1){
  std::string view=argv[1];russian=view.find("en")==std::string::npos;
  w.m_tab=TAB_REPORTS;w.m_toast[0]=0;
  CZM_ModerationOpen();reply(w,200,"{\"reports_open\":2,\"sanctions_active\":3}");reply(w,200,REPORTS);
  if(view.rfind("target",0)==0||view.rfind("confirm",0)==0){w.OpenTarget(8,"Hunter",0,0,"ты никто, удали игру",101,"chat","Сообщение в чате  ·  chat_ru",true);reply(w,200,CARD);}
  if(view.rfind("confirm",0)==0){w.m_action=8;w.m_minutes=0;Q_strncpy(w.m_reason,"Нацистская пропаганда",sizeof(w.m_reason));w.Go(PAGE_CONFIRM);w.m_armed=true;}
  if(view.rfind("reason",0)==0){w.OpenTarget(8,"Hunter",71,0,"текст");reply(w,200,CARD);w.m_action=3;w.m_minutes=1440;w.Go(PAGE_REASON);w.m_reasonIndex=MOD_OWN_REASON;Q_strncpy(w.m_reason,"Флуд в чате",sizeof(w.m_reason));}
  trace=true;w.Draw();
 }
 puts("MODERATION_WINDOW_OK");
}
'''


class ModerationWindowTests(unittest.TestCase):
    def test_panel_card_and_action_steps(self):
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
            source = (ROOT / "czm/menu/CzmModeration.cpp").read_text().replace("private:\n", "public:\n")
            (p / "main.cpp").write_text(HARNESS + wrapping + source + SCENARIOS)
            exe = p / "moderation"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", "-Wno-unused-function", "-Wno-unused-variable", "-I" + folder,
                            str(p / "main.cpp"), str(ROOT / "czm/menu/CzmJson.cpp"), "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn("MODERATION_WINDOW_OK", result.stdout)
            out = os.environ.get("CZM_MODERATION_PREVIEW_DIR")
            if out:
                dest = Path(out); dest.mkdir(parents=True, exist_ok=True)
                for view in ["panel", "target", "reason", "confirm", "target-en"]:
                    r = subprocess.run([str(exe), view], capture_output=True, text=True, check=True)
                    (dest / (view + ".tsv")).write_text(r.stdout)


if __name__ == "__main__":
    unittest.main()
