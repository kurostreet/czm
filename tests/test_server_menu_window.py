"""Execute the real server window, its forms and invitation requests against controlled replies."""
from pathlib import Path
import os,subprocess,tempfile,unittest,re
from test_loading_errors import function
from test_social_menu import STUB,HARNESS
from test_tab_avatars import VECTOR,STRING

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=r'''
static CzmRichMenu sample(){CzmRichMenu m={};m.serial=1;strcpy(m.tab,"main");strcpy(m.root,"main");strcpy(m.head,"МЕНЮ СЕРВЕРА");strcpy(m.sub,"COUNTER ZOMBIE · SURVIVAL");strcpy(m.chip,"2/32 · zm_dust_world_summer_f · 19:21");strcpy(m.foot,"Честная игра · Чистый сервер · Приятное общение");
 const char *tabs[]={"Главная","LVL MOD","Игроки","Голосования","Сообщество"},*keys[]={"main","lvl","players","votes","server"},*icons[]={"star","crown","users","flag","globe"};m.numTabs=5;
 for(int i=0;i<5;i++){strcpy(m.tabs[i].key,keys[i]);strcpy(m.tabs[i].name,tabs[i]);strcpy(m.tabs[i].icon,icons[i]);}
 const char *names[]={"LVL MOD","Панель на сайте","Голосования","Телепорт","Приглашения","Новости сервера","Сообщение админу"},*sub[]={"Уровень, токены, награды","Скины, магазин, топ","Карта, бан, мут","К другу по запросу","Позвать друга на сервер","Что нового на сервере","Обращение администрации"},*art[]={"crown","globe","flag","target","person_add","bell","chat"};m.numCards=7;
 for(int i=0;i<7;i++){auto &c=m.cards[i];c.key=i+1;c.enabled=true;strcpy(c.name,names[i]);strcpy(c.sub,sub[i]);strcpy(c.icon,art[i]);}return m;}
static bool inside(CzmRect a,CzmRect b){return a.w>0&&a.h>0&&a.x>=b.x&&a.y>=b.y&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h;}
int main(int argc,char**argv){
 uiStatic.realTime=1000;CCzmServerWindow w;auto root=sample();w.Open(root);w.m_iOpenTime=0;w.m_iChangeTime=0;
 if(argc>1){drawTrace=true;
  std::string view=argv[1];if(view=="compact"){ScreenWidth=640;ScreenHeight=360;}
  if(argc>3){ScreenWidth=atoi(argv[2]);ScreenHeight=atoi(argv[3]);}
  if(view=="standalone"||view=="submenu"){
   CzmRichMenu m={};ParseRich("81 1023\n#czm1\tmenu\tstandalone\tМЕНЮ СЕРВЕРА\t\tLVL 8 | WR 64%\t\n#nav\t0\t1\t1\tstar\n#tokens\t117766\n1. Прогресс и токены\t\tchart\n2. Игровой магазин\t\tcart\n\\d3. Голосования\t\tflag\n4. Настройки игрока\t\tgear\n5. Мой инвентарь\t\tbox\n\\d6. Лавка игроков\t\tusers\n7. Язык\t\tglobe\t\tRU\n0. Выход",m);
   if(view=="submenu")ParseRich("82 1023\n#czm1\tmenu\tstandalone\tПрогресс и токены\t\tLVL 8 | WR 64%\t\n#nav\t1\t1\t2\tchart\n#tokens\t117766\n1. Моя статистика\t\tchart\n2. Прогресс уровня\t\ttarget\n3. Передать токены\t\tcoins\n4. Мой прогресс\t\tuser\n5. История токенов\t\tclock\n\\d6. Боевой пропуск\t\tticket\n8. Назад\n9. Далее\n0. Выход",m);
   survivalPeer=true;w.Update(m);
  }
  if(view=="form"){auto m=root;m.kind=CzmServerView::Form;strcpy(m.parent,"server");strcpy(m.pageTitle,"Сообщение админу");strcpy(m.command,"czm_admin_msg");strcpy(m.body,"Опиши проблему. Обращение получит администрация сервера. В общий чат оно не попадёт.\n\nПосле отправки здесь появится результат.");strcpy(m.hint,"Нажмите, чтобы ввести сообщение…");w.Update(m);strcpy(w.m_input,"На карте застрял игрок. Нужна помощь администрации.");}
  if(view=="friends"){auto m=root;m.kind=CzmServerView::Friends;strcpy(m.parent,"players");strcpy(m.pageTitle,"Пригласить друга");w.Update(m);w.m_friendsLoaded=true;w.m_friendCount=4;const char*n[]={"KuroStreet","Hunter","ZombieMaster","Алексей"};for(int i=0;i<4;i++){w.m_friends[i].id=i+20;w.m_friends[i].online=i<2;strcpy(w.m_friends[i].nick,n[i]);}}
  w.m_iChangeTime=0;w.Draw();return 0;
 }
 // Keyboard input and prefill cannot create another console command.
 char input[768]={};for(const unsigned char*c=(const unsigned char*)"Тест;quit\n\"x\\y^1";*c;c++)CzmServerView::Append(input,sizeof(input),*c);
 assert(!strchr(input,';')&&!strchr(input,'\n')&&!strchr(input,'"')&&!strchr(input,'\\')&&!strchr(input,'^'));
 input[0]=0;for(int i=0;i<181;i++)for(const unsigned char*c=(const unsigned char*)"Я";*c;c++)CzmServerView::Append(input,sizeof(input),*c);
 assert(CzmServerView::Characters(input)==180&&strlen(input)==360);CzmServerView::Backspace(input);assert(strlen(input)==358);
 auto form=root;form.kind=CzmServerView::Form;strcpy(form.command,"czm_admin_msg");strcpy(form.parent,"server");strcpy(form.pageTitle,"Message");strcpy(form.prefill,"Сохранённый текст;quit");w.Update(form);assert(!strcmp(w.m_input,"Сохранённый текстquit"));
 sentCommands.clear();w.Submit();assert(sentCommands=="czm_admin_msg \"Сохранённый текстquit\"\n"&&w.m_formPending);w.Submit();assert(sentCommands=="czm_admin_msg \"Сохранённый текстquit\"\n");
 w.Update(form);strcpy(w.m_input,"ok");sentCommands.clear();w.Submit();assert(sentCommands.empty()&&!w.m_formPending);
 strcpy(w.m_input,"  ok  ");w.Submit();assert(sentCommands.empty()&&!w.m_formPending&&!strcmp(w.m_input,"ok"));
 strcpy(w.m_menu.command,"quit");strcpy(w.m_input,"hello");w.Submit();assert(sentCommands.empty());
 w.Close(true);assert(sentCommands=="client_buy_close\nczm_menu_close\n");
 // A tap on a footer control uses its own action, and X never selects Back.
 CzmRichMenu admin,confirm;
 ParseRich("20 961\n#czm1\tmenu\tstandalone\tАдмин-меню\t\tLVL 1\t\n#nav\t1\t1\t2\tshield\n\\yАдмин-меню\n\\wLVL 1\n1. Выдать кредиты\t\tcoins\n8. Назад\n9. Далее\n0. Выход",admin);
 assert(admin.navigation&&admin.canGoBack&&admin.menuPage==1&&admin.menuPages==2&&admin.numCards==1);
 assert(!strcmp(admin.headerIcon,"shield")&&!strcmp(admin.cards[0].icon,"coins")&&!admin.body[0]);
 w.Open(admin);w.Layout(0);
 auto tap=[&](CzmRect r){assert(r.w&&r.h);uiStatic.cursorX=r.x+r.w/2;uiStatic.cursorY=r.y+r.h/2;sentCommands.clear();w.KeyDown(1);w.KeyUp(1);};
 assert(inside(w.m_navNext,w.m_foot)&&inside(w.m_back,w.m_head)&&inside(w.m_menu.cards[0].rect,w.m_body));
 assert(w.m_back.y+w.m_back.h<w.m_navNext.y&&inside(w.m_return,w.m_foot));
 tap(w.m_navNext);assert(sentCommands=="slot9\n");
 admin.menuPage=2;admin.nextSlot=0;w.Update(admin);w.Layout(0);
 tap(w.m_navPrev);assert(sentCommands=="czm_menu_prev\n");
 tap(w.m_back);assert(sentCommands=="czm_menu_back\n");
 ParseRich("22 641\n#czm1\tmenu\tstandalone\tПодтвердите действие\t\t\t\n#nav\t1\t1\t1\tshield\nKuro\nВыдать токены: 500\n1. Подтвердить\n8. Назад\n0. Выход",confirm);
 assert(confirm.numCards==1&&!strcmp(confirm.body,"Kuro\nВыдать токены: 500\n"));
 w.Update(confirm);w.Layout(0);
 assert(inside(w.m_cardInfo,w.m_body)&&w.m_cardInfo.y+w.m_cardInfo.h<=w.m_menu.cards[0].rect.y);
 tap(w.m_close);assert(sentCommands=="client_buy_close\nczm_menu_close\n"&&w.m_bClosing);
 // Structured views use server values, and a recovery code is only sent to Survival.
 CzmRichMenu stats,progress,migrate;
 ParseRich("23 640\n#czm1\tmenu\tstandalone\tМоя статистика\t\t\t\n#nav\t1\t1\t1\tstar\n#facts\tstats\tru\t12\t8\t4\t5\t472\t1\n8. Назад\n0. Выход",stats);
 assert(stats.facts.kind==CzmRichMenu::Facts::Statistics&&stats.facts.stats.seconds==472&&stats.facts.stats.saved);
 ParseRich("24 640\n#czm1\tmenu\tstandalone\tПрогресс уровня\t\t\t\n#nav\t1\t1\t1\tstar\n#facts\tprogress\tru\t3\t4\t6\t10\t95\t600\n8. Назад\n0. Выход",progress);
 assert(progress.facts.kind==CzmRichMenu::Facts::Progress&&progress.facts.progress.next==4&&progress.facts.progress.timeLeft==95);
 for(int height:{360,480,716}){ScreenHeight=height;ScreenWidth=height*2;w.Open(stats);w.Layout(0);assert(inside(w.m_cardInfo,w.m_body));w.Draw();w.Update(progress);w.Layout(0);assert(inside(w.m_cardInfo,w.m_body));w.Draw();}
 ParseRich("25 640\n#czm1\tmenu\tstandalone\tПеренос\t\t\t\n#nav\t1\t1\t1\tstar\n#page\tform\tВведи код\tczm_profile_migrate\tКод\n8. Назад\n0. Выход",migrate);
 w.Update(migrate);assert(migrate.kind==CzmServerView::Form);
 strcpy(w.m_input,"0123456789abcdef0123456789abcdef");sentCommands.clear();w.Submit();assert(sentCommands.empty());
 survivalPeer=true;strcpy(w.m_input,"wrong");w.Submit();assert(sentCommands.empty());
 strcpy(w.m_input,"0123456789abcdef0123456789abcdef");w.Submit();assert(sentCommands=="czm_profile_migrate \"0123456789abcdef0123456789abcdef\"\n");
 survivalPeer=false;
 // A tab switch abandons its request; a delayed result never enters another view/account.
 auto friends=root;friends.kind=CzmServerView::Friends;strcpy(friends.command,"@friends");strcpy(friends.parent,"players");strcpy(friends.pageTitle,"Пригласить друга");
 w.Open(friends);w.FriendsFrame();int pending=w.m_request;assert(pending>0&&requests.back().url=="/api/v1/social/people/friends?offset=0");
 w.Update(root);replies[pending]={200,"{\"people\":[{\"id\":99,\"nick\":\"private old\"}],\"next\":-1}"};w.FriendsFrame();assert(!w.m_friendCount&&w.m_abandoned.Count()==0);
 w.Update(friends);w.FriendsFrame();pending=w.m_request;replies[pending]={200,"{\"people\":[],\"next\":-1}"};int count=requests.size();w.FriendsFrame();w.FriendsFrame();assert(w.m_friendsLoaded&&!w.m_friendCount&&!w.m_request&&(int)requests.size()==count);
 // Friends are read from the real JSON format, invitations use the current endpoint and a retry nonce.
 w.FetchFriends(0);pending=w.m_request;replies[pending]={200,"{\"people\":[{\"id\":12,\"nick\":\"Hunter\",\"online\":true}],\"next\":-1}"};w.FriendsFrame();assert(w.m_friendCount==1&&w.m_friends[0].id==12);
 vars["czm_connect_adr"]="203.0.113.10:27016";vars["czm_connect_name"]="CZM Survival";w.InviteFriend(0);assert(requests.back().url=="/api/v1/social/invite/12");CzmJson invite;assert(invite.Parse(requests.back().body.c_str())&&!strcmp(invite.String(invite.Get(0,"server")),"203.0.113.10:27016"));
 std::string first=requests.back().body;pending=w.m_request;replies[pending]={0,""};w.FriendsFrame();w.InviteFriend(0);assert(requests.back().body==first);
 pending=w.m_request;replies[pending]={200,"{\"ok\":true}"};w.FriendsFrame();count=requests.size();w.InviteFriend(0);assert(w.m_successFriend==12&&(int)requests.size()==count);
 w.FetchFriends(40);w.Draw();pending=w.m_request;replies[pending]={200,"{\"people\":[{\"id\":13,\"nick\":\"Next\"}],\"next\":-1}"};w.FriendsFrame();w.FetchFriends(0);assert(w.m_friendPage==-1);w.Draw(); // loading a preceding page must not index a negative friend row
 pending=w.m_request;identity++;replies[pending]={200,"{\"people\":[{\"id\":8,\"nick\":\"other profile\"}],\"next\":-1}"};w.FriendsFrame();assert(!w.m_friendCount);
 authenticated=false;w.Submit();assert(logins==1);authenticated=true;
 // A foreign numbered menu uses the compact list but keeps its exact slots,
 // including 0/Back; local Return to game does not accidentally select it.
 CzmRichMenu foreign;
 PlainAsRich("71 1021\nForeign server\n1. First\n\\d2. Locked\n3. Third\n4. Fourth\n5. Fifth\n6. Sixth\n7. Seventh\n8. Eighth\n9. Next page\n0. Back",NULL,foreign);
 assert(foreign.plain&&foreign.numCards==10&&!foreign.cards[1].enabled);
 ScreenWidth=1536;ScreenHeight=716;w.Open(foreign);w.Layout(0);
 assert(w.m_iCardRows==7&&w.m_scrollMax>0&&w.m_menu.cards[9].rect.w==0);
 sentCommands.clear();w.Activate(w.HIT_CARD+1);assert(sentCommands.empty());
 w.m_scroll=w.m_scrollMax;w.Layout(0);assert(w.m_menu.cards[9].rect.w>0);
 tap(w.m_menu.cards[9].rect);assert(sentCommands=="slot10\n");
 w.Update(foreign);w.Layout(0);sentCommands.clear();w.KeyDown('9');assert(sentCommands=="slot9\n");
 w.Update(foreign);w.Layout(0);sentCommands.clear();w.KeyDown('0');assert(sentCommands=="slot10\n");
 w.Update(foreign);w.Layout(0);tap(w.m_return);assert(sentCommands=="client_buy_close\n"&&w.m_bClosing);
 // Updating another plain submenu must not lose its own 0/Back action.
 PlainAsRich("72 513\nChild\n1. Confirm\n0. Back",&foreign,foreign);
 assert(foreign.numCards==2&&foreign.cards[1].key==10&&!foreign.hasTokens);
 // The actual header only displays a typed current balance on our server.
 CzmRichMenu balance;ParseRich("73 1\n#czm1\tmenu\tmain\tMenu\t\tTokens 999999\t\n#tokens\t7321\n1. Item",balance);
 w.Open(balance);w.Layout(0);drawnLabels.clear();w.DrawHeader(255);
 bool wallet=false;for(auto&label:drawnLabels)if(label=="CZM Token: 7321")wallet=true;assert(!wallet);
 survivalPeer=true;drawnLabels.clear();w.DrawHeader(255);for(auto&label:drawnLabels)if(label=="CZM Token: 7321")wallet=true;assert(wallet);survivalPeer=false;
 // Every view remains within the window on the supported aspect ratios.
 for(auto wh:{std::make_pair(640,360),std::make_pair(1536,716),std::make_pair(2340,1080),std::make_pair(1024,768)}){
  ScreenWidth=wh.first;ScreenHeight=wh.second;
  for(int kind=0;kind<=4;kind++){auto m=root;m.kind=(CzmServerView::Kind)kind;strcpy(m.parent,"server");w.Update(m);w.Layout(0);assert(inside(w.m_body,w.m_win)&&inside(w.m_content,w.m_body));
   if(kind==CzmServerView::Form)assert(inside(w.m_field,w.m_body)&&inside(w.m_submit,w.m_body)&&w.m_field.y+w.m_field.h<=w.m_submit.y);
   if(kind==CzmServerView::Friends)for(int i=0;i<6;i++)assert(inside(w.m_friendRows[i],w.m_body));
  }
 }
 // The live frame converts compatible foreign menus, preserves serial updates,
 // and leaves the classic opt-out and weapon-specific views available.
 stack.current=nullptr;vars["czm_menu_cards"]="1";
 assert(ServerWindowFrame("91 513\nForeign\n1. First\n0. Back")&&menu_czmserver->Serial()==91);
 assert(menu_czmserver->Menu().plain&&menu_czmserver->Menu().numCards==2);
 ServerWindowFrame("91 513\nForeign\n1. Duplicate serial\n0. Back");
 assert(!strcmp(menu_czmserver->Menu().cards[0].name,"First"));
 ServerWindowFrame("92 512\nChild\n\\d1. Locked\n0. Back");
 assert(menu_czmserver->Serial()==92&&!menu_czmserver->Menu().cards[0].enabled);
 menu_czmserver->Close(true);assert(!CZM_ClientMenuOpen(menu_czmserver));
 ServerWindowFrame("92 512\nChild\n1. Closed serial\n0. Back");assert(!CZM_ClientMenuOpen(menu_czmserver));
 ServerWindowFrame("93 1\nChild\n1. Next serial");assert(CZM_ClientMenuOpen(menu_czmserver));
 vars["czm_menu_cards"]="0";assert(!ServerWindowFrame("94 1\nClassic\n1. Item")&&!CZM_ClientMenuOpen(menu_czmserver));
 vars["czm_menu_cards"]="1";weaponMenu=true;assert(!ServerWindowFrame("95 1\nWeapon\n1. Item"));weaponMenu=false;
 assert(!ServerWindowFrame("96 0\nText without numbered choices"));
}
'''

class ServerMenuWindowTests(unittest.TestCase):
 def test_forms_friends_replies_and_geometry(self):
  with tempfile.TemporaryDirectory(prefix='czm-server-window-') as folder:
   p=Path(folder)
   (p/'utlvector.h').write_text(VECTOR.replace('void RemoveAll(){v.clear();}','void RemoveAll(){v.clear();} void Remove(int n){v.erase(v.begin()+n);} T&Tail(){return v.back();}'))
   (p/'utlstring.h').write_text(STRING)
   stub=STUB.replace('CZMF_NICK,QM_CENTER=1','CZMF_NICK,CZMF_NAV,CZMF_SHOP_PRICE,CZMF_MENU_TITLE,CZMF_TILE_STATUS,CZMF_UI_TITLE,CZMF_UI_ACTION,CZMF_UI_LABEL,CZMF_UI_META,CZMF_TINY,CZMF_PROFILE_NAME,CZMF_PROFILE_TEXT,CZMF_CHAT_TEXT,CZMF_PROFILE_TITLE,KEY_MENU=100,QM_LEFT=0,QM_CENTER=1')
   stub=stub.replace('bool HasCursor()const{','bool Contains(int a,int b)const{return w>0&&h>0&&a>=x&&a<x+w&&b>=y&&b<y+h;}CzmRect Grown(int n)const{return{x-n,y-n,w+n*2,h+n*2};}bool HasCursor()const{')
   stub=re.sub(r'struct Cursor\{[^}]*\}', 'struct Cursor{int cursorY=0,cursorX=0,realTime=1000;struct Layer{bool active=false;bool IsActive()const{return active;}}menu,client;}', stub)
   stub=stub.replace('struct EngFuncs{','struct EngFuncs{static void KEY_SetDest(int){}static void ClientCmd(bool,const char*);static void ClientCmdF(bool,const char*,...);')
   stub=stub.replace('inline bool CL_IsActive(){return false;}','inline bool CL_IsActive(){return true;}')
   stub=stub.replace('unsigned CZM_White();','unsigned CZM_White(int=255);')
   stub+='\nusing CMenuBaseClientWindow=CMenuFramework;void CZM_KeepClientMenu(CMenuFramework*);void CZM_CloseClientMenuSoon(CMenuFramework*);int CZM_ImageAspect1000(const char*);\nstatic bool survivalPeer=false;inline bool CZM_OnSurvivalServer(){return survivalPeer;}\n'
   (p/'stub.h').write_text(stub)
   for name in ['CzmMenu.h','Scissor.h']:(p/name).write_text('#include "stub.h"\n')
   for name in ['CzmJson.h','CzmDesign.h']:(p/name).write_text((ROOT/'czm/menu'/name).read_text())
   harness=HARNESS.replace('unsigned CZM_White(){return 0xffffffff;}','unsigned CZM_White(int a){return PackRGBA(255,255,255,a);}')
   harness=harness.replace('f==CZMF_UI_META?15:','f==CZMF_TINY?10:f==CZMF_UI_ACTION?26:f==CZMF_UI_META?15:')
   # Article wrapping honors explicit newlines, unlike the simplified social-list test stub.
   old=function(harness,'int CZM_WrapText(')
   harness=harness.replace(old,r'''int CZM_WrapText(HFont f,const char*s,int w,int*starts,int max){int n=0,i=0;starts[0]=0;while(s[i]&&n<max){int begin=i,width=0;while(s[i]&&s[i]!='\n'){int k=i;i++;while((s[i]&0xc0)==0x80)i++;width+=CZM_FontHeight(f)*62/100;if(width>w&&k>begin){i=k;break;}}if(s[i]=='\n')i++;starts[++n]=i;}return n;}''')
   harness+='''\n#include <cstdarg>\nstatic std::string sentCommands;void EngFuncs::ClientCmd(bool,const char*s){sentCommands+=s;}void EngFuncs::ClientCmdF(bool,const char*f,...){char b[1600];va_list a;va_start(a,f);vsnprintf(b,sizeof(b),f,a);va_end(a);sentCommands+=b;}\nvoid CZM_KeepClientMenu(CMenuFramework*){}void CZM_CloseClientMenuSoon(CMenuFramework*p){p->CMenuFramework::Hide();}int CZM_ImageAspect1000(const char*){return 1000;}\n'''
   source=(ROOT/'czm/menu/CzmServerMenu.cpp').read_text()
   defs='\n#define UI_DIR "gfx/czm/ui/"\n#define MAX_CARDS 10\n#define MAX_LINES 3\n#define SM_MAX_TABS 32\n#define SM_MAX_CARDS 10\n#include "czm_server_view.h"\n#include "CzmJson.h"\n#include "CzmDesign.h"\n'
   defs+=source[source.index('struct CzmCard'):source.index('static void TrimCopy')]
   defs+=source[source.index('struct CzmMenuTab'):source.index('static bool IsRichMenu')]
   for sig in ['static void TrimCopy(','static void SplitLine(','static void ParseMenu(','static bool IsRichMenu(','static void NextField(','static unsigned int HexColor(','static unsigned int Tint(','static const char *MenuIcon(','static void ParseRich(','static void PlainAsRich(']:defs+=function(source,sig)+'\n'
   window=source[source.index('class CCzmServerWindow'):source.index('ADD_MENU3( menu_czmserver')].replace('private:','public:')
   window+='\nstatic CCzmServerWindow*menu_czmserver=new CCzmServerWindow();static bool CZM_ClientMenuOpen(CMenuFramework*m){return stack.current==m;}\nstatic bool weaponMenu;namespace CzmWeapons{static bool Wire(const char*){return weaponMenu;}}static bool CZM_IsWeaponMenu(const char*){return weaponMenu;}\n'
   window+=function(source,'static bool ServerWindowFrame(')
   (p/'main.cpp').write_text(harness+defs+window+SCENARIOS)
   exe=p/'window'
   subprocess.run(['g++','-std=c++11','-w','-I'+folder,'-I'+str(ROOT/'common'),str(p/'main.cpp'),str(ROOT/'czm/menu/CzmJson.cpp'),'-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True)
   preview=os.environ.get('CZM_SERVER_MENU_PREVIEW_DIR')
   if preview:
    out=Path(preview);out.mkdir(parents=True,exist_ok=True)
    for view in ['main','form','friends','compact','standalone','submenu']:
     r=subprocess.run([str(exe),view],check=True,capture_output=True,text=True);(out/(view+'.tsv')).write_text(r.stdout)
    for width,height in [(640,360),(1536,716),(2340,1080),(1024,768)]:
     for view in ['standalone','submenu']:
      r=subprocess.run([str(exe),view,str(width),str(height)],check=True,capture_output=True,text=True)
      (out/(f'{view}-{width}x{height}.tsv')).write_text(r.stdout)
