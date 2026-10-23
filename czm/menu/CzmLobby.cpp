/*
 * Counter Zombie Mobile temporary party lobby.
 * A room exists only until its owner exits, disconnects or launches a match.
 * API state and gameplay voice remain separate from this screen.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "Framework.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "CzmJson.h"

#define UI_DIR "gfx/czm/ui/"
#define CZM_LOBBY_LIST 4
#define CZM_LOBBY_MEMBERS 6
#define CZM_LOBBY_MESSAGES 8

namespace {
const char *L( const char *ru, const char *en ) { return CZM_IsRussian() ? ru : en; }
struct RoomCard { char id[64], title[128], address[64], proto[8], map[64]; int count,capacity; };
struct Member { int id; bool ready; char nick[100],avatar[32]; };
struct ChatLine { int sender; char nick[52],text[440]; };
bool SafeAddress(const char *p) {
    if(!p || !*p || strlen(p)>=64 || !strchr(p,':')) return false;
    for(;*p;p++) if(!((*p>='0'&&*p<='9')||*p=='.'||*p==':')) return false;
    return true;
}
void Caption(const CzmRect &r,const char *value,int font=CZMF_PANEL_TEXT,unsigned color=0) {
    HFont f=CZM_Font(font);
    CZM_DrawText(f,r.x,r.y+(r.h-CZM_FontHeight(f))/2,r.w,value,color?color:CZM_White());
}
void Button(const CzmRect &r,const char *label,bool active=true,bool accent=false) {
    CZM_DrawButton(accent?UI_DIR "button_primary.png":UI_DIR "button_secondary.png",
                   r,label,active?CZM_White():CZM_Grey(),false,CZMF_TILE_STATUS);
}
void IconChip(const CzmRect &r,const char *icon,bool active=false,bool warning=false){
    const unsigned tint=warning?PackRGBA(218,63,77,242):
                        active?PackRGBA(31,105,78,242):
                               PackRGBA(36,48,64,244);
    CZM_DrawPill(UI_DIR "chip_round.png",r.x,r.y,r.w,r.h,tint);
    const int side=Q_min(r.w,r.h)*2/3;
    CZM_DrawImage(icon,r.x+(r.w-side)/2,r.y+(r.h-side)/2,side,side);
}
}

class CCzmLobby : public CMenuFramework {
public:
    CCzmLobby();
    void Show() override;
    void Hide() override;
    void Draw() override;
    bool IsRoot() const override { return false; }
    bool KeyDown(int key) override;
    bool KeyUp(int key) override;
    void Char(int key) override;
    void Open(bool create);
    void JoinPublic(const char *room);
    void Frame();
    void ResetSession();
    void PickedServer(const char *address,const char *proto,const char *name,
                      const char *map,int players,int slots);
    void InviteFriend(int target);
    bool CanInvite() const {
        // Friends overlays hide the room panel; room ownership persists.
        return m_stage==ROOM&&m_room[0]&&m_owner==CZM_OnlinePlayer();
    }
    bool IsOpened() const { return m_open; }
    bool HasRoom() const { return m_room[0]!=0 && m_stage==ROOM; }
private:
    enum { CREATE, SEARCH, ROOM };
    enum { NONE=0, BACK, REFRESH, MAKE, VISIBILITY, LESS, MORE, TITLE,
           SELECT=100, MEMBER=200, READY=300, LAUNCH, LEAVE, SEND, CHAT, INVITE, SERVER_NEXT, NEXT, PREV,
           MODAL_PROFILE=500, MODAL_LOCAL_MUTE, MODAL_HOST_MUTE,
           MODAL_KICK, MODAL_TRANSFER, MODAL_CANCEL, VOICE_MIC, VOICE_ALL };
    enum { GET_LIST=1, GET_ROOM, GET_CHAT, POST_CREATE, POST_JOIN,
           POST_READY, POST_LAUNCH, POST_LEAVE, POST_CHAT, POST_SERVER, POST_INVITE, GET_MINE,
           POST_KICK, POST_TRANSFER, POST_HEARTBEAT, POST_VOICE_MUTE };
    void Layout();
    int Hit() const;
    void Action(int hit);
    void Query(int kind,const char *method,const char *path,const char *payload="");
    void ReadRoom(const CzmJson &j,int node);
    void FinishRequest(int status,const char *body,int kind);
    void Notice(const char *text);
    void Poll();
    void Refresh();
    void SendMessage();
    void StopInput();
    bool VoiceBlocked() const;
    void DrawField(const CzmRect &r,const char *placeholder);
    int m_stage,m_request,m_kind,m_pressed,m_capacity,m_server,m_offset,m_next;
    bool m_open,m_private,m_typing,m_ownReady,m_busy,m_voiceAllMuted;
    bool m_hostMuted[CZM_LOBBY_MEMBERS];
    double m_nextPoll,m_nextHeartbeat,m_nextVoicePoll,m_noticeUntil;
    char m_title[128],m_description[128],m_room[64],m_serverAddress[64],m_serverProto[8];
    char m_notice[230],m_text[450],m_lastText[450],m_nonce[80];
    char m_ownerName[100],m_roomTitle[128],m_pickedName[100],m_pickedMap[64];
    int m_owner,m_revision,m_memberCount,m_chatCount,m_cardCount;
    int m_selectedMemberId,m_memberConfirm;
    Member m_members[CZM_LOBBY_MEMBERS];
    ChatLine m_chat[CZM_LOBBY_MESSAGES];
    RoomCard m_cards[CZM_LOBBY_LIST];
    CzmRect m_panel,m_back,m_refresh,m_primary,m_secondary,m_extra,m_titleRect;
    CzmRect m_buttons[9],m_cardsRect[CZM_LOBBY_LIST],m_membersRect[CZM_LOBBY_MEMBERS],m_chatRect;
    CzmRect m_textRect,m_sendRect,m_micRect,m_voiceAllRect,m_roomServerRect,m_modal,m_modalButtons[6];
    int W,H,pad;
};

static CCzmLobby *s_lobby;

CCzmLobby::CCzmLobby():CMenuFramework("CzmLobby"){
    s_lobby=this; m_stage=CREATE; m_request=m_kind=m_pressed=0;m_capacity=6;
    m_server=m_offset=m_next=m_owner=m_revision=m_memberCount=m_chatCount=m_cardCount=0;
    m_selectedMemberId=m_memberConfirm=0;
    m_open=m_private=m_typing=m_ownReady=m_busy=m_voiceAllMuted=false;
    memset(m_hostMuted,0,sizeof(m_hostMuted));m_nextPoll=m_nextHeartbeat=m_nextVoicePoll=m_noticeUntil=0;
    m_title[0]=m_description[0]=m_room[0]=m_serverAddress[0]=m_serverProto[0]=0;
    m_notice[0]=m_text[0]=m_lastText[0]=m_nonce[0]=m_ownerName[0]=m_roomTitle[0]=m_pickedName[0]=m_pickedMap[0]=0;
    W=H=pad=0;
}

void CCzmLobby::Show() {
    CZM_Init();m_open=true;m_pressed=0;
    CMenuFramework::Show();
    Query(GET_MINE,"GET","/api/v1/lobbies/mine");
}
void CCzmLobby::Open(bool create){
    if(!CZM_OnlineAccount()){CZM_AccountShow(CZM_OnlineKey(),"");return;}
    if(!m_open){
        if(m_room[0]){
            m_stage=ROOM;
            Show(); // reconcile ownership and expiry with /mine
            return;
        }
        m_stage=create?CREATE:SEARCH; m_offset=0;m_request=0;
        Q_strncpy(m_title,"Zombie Team",sizeof(m_title));m_private=false;m_capacity=6;m_server=0;
        m_serverAddress[0]=m_serverProto[0]=m_pickedName[0]=m_pickedMap[0]=0;
        // Prefer a server with enough slots for the chosen lobby capacity.
        // Fallback remains the user's first server if occupancy is stale.
        CzmServer *first=CZM_Server(0);
        for(int i=0;i<CZM_ServerCount();i++){
            CzmServer *candidate=CZM_Server(i);
            if(candidate && SafeAddress(candidate->address) &&
               candidate->maxplayers-candidate->players>=m_capacity){
                first=candidate;m_server=i;break;
            }
        }
        if(first&&SafeAddress(first->address)){
            Q_strncpy(m_serverAddress,first->address,sizeof(m_serverAddress));
            Q_strncpy(m_serverProto,first->prot,sizeof(m_serverProto));
            Q_strncpy(m_pickedName,first->name,sizeof(m_pickedName));
            Q_strncpy(m_pickedMap,first->map,sizeof(m_pickedMap));
        }
        Show();
    }else{
        // Coming back from the friends/server browser must never silently
        // abandon or hide an active temporary room.
        if(m_room[0]){m_stage=ROOM;Refresh();}
        else{
            m_stage=create?CREATE:SEARCH;m_offset=0;
            Query(GET_MINE,"GET","/api/v1/lobbies/mine");
        }
    }
}
void CCzmLobby::JoinPublic(const char *room){
    if(m_room[0]){
        m_stage=ROOM;
        if(!m_open)Show();
        else Refresh();
        Notice(L("Сначала выйдите из текущего лобби",
                 "Leave your current lobby before joining another"));
        return;
    }
    if(!room||!room[0]||strlen(room)>63||!CZM_OnlineAccount())return;
    for(const char *p=room;*p;p++)
        if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||
             (*p>='0'&&*p<='9')||*p=='_'||*p=='-'))return;
    if(!m_open){
        m_stage=SEARCH;m_room[0]=0;m_open=true;m_request=0;m_pressed=0;
        CMenuFramework::Show();
    }
    char path[160];snprintf(path,sizeof(path),"/api/v1/lobbies/%s/join",room);
    Query(POST_JOIN,"POST",path,"{}");
}
void CCzmLobby::ResetSession(){
    CZM_LobbyVoiceStop();
    m_request=0;m_kind=0;m_busy=false;
    m_room[0]=m_roomTitle[0]=m_text[0]=m_pickedMap[0]=0;
    m_memberCount=m_chatCount=m_selectedMemberId=m_memberConfirm=0;
    m_owner=0;m_stage=SEARCH;m_nextVoicePoll=0;m_nextHeartbeat=0;
    if(m_open)Hide();
}
void CCzmLobby::Hide(){StopInput();m_open=false;m_pressed=0;m_selectedMemberId=0;m_memberConfirm=0;CMenuFramework::Hide();}
void CCzmLobby::Notice(const char *p){Q_strncpy(m_notice,p?p:"",sizeof(m_notice));m_noticeUntil=EngFuncs::DoubleTime()+4;}
void CCzmLobby::StopInput(){if(m_typing){UI_EnableTextInput(false);m_typing=false;}}
bool CCzmLobby::VoiceBlocked() const{
    const int me=CZM_OnlinePlayer();
    if(!me)return true;
    if(m_voiceAllMuted&&me!=m_owner)return true;
    for(int i=0;i<m_memberCount;i++)
        if(m_members[i].id==me)return m_hostMuted[i];
    return true;
}


void CCzmLobby::Layout(){
    // Compact landscape overlay: reserve the lower strip for readable notices.
    // All hit rectangles follow the same coordinates as the rendered controls.
    W=ScreenWidth;H=ScreenHeight;
    pad=Q_max(8,(int)(H*.018f));
    const int gap=Q_max(5,(int)(H*.011f));
    const int bh=Q_max(29,(int)(H*.056f));
    const int pw=Q_min((int)(W*(m_stage==ROOM?.72f:.70f)),
                       (int)(H*(m_stage==ROOM?1.54f:1.50f)));
    const int ph=(int)(H*(m_stage==ROOM?.66f:m_stage==SEARCH?.47f:.49f));
    m_panel=CZM_Rect((W-pw)/2,(H-ph)/2,pw,ph);
    const int left=m_panel.x+pad,inner=pw-2*pad;
    int top=m_panel.y+pad;
    m_back=CZM_Rect(left,top,bh,bh);
    m_refresh=CZM_Rect(left+inner-bh,top,bh,bh);
    top+=bh+gap;
    m_titleRect=CZM_Rect(0,0,0,0);
    m_primary=m_secondary=m_extra=CZM_Rect(0,0,0,0);
    for(int i=0;i<9;i++)m_buttons[i]=CZM_Rect(0,0,0,0);
    for(int i=0;i<CZM_LOBBY_LIST;i++)m_cardsRect[i]=CZM_Rect(0,0,0,0);
    for(int i=0;i<CZM_LOBBY_MEMBERS;i++)m_membersRect[i]=CZM_Rect(0,0,0,0);
    m_chatRect=m_textRect=m_sendRect=m_micRect=m_voiceAllRect=m_roomServerRect=CZM_Rect(0,0,0,0);

    const int modalW=Q_min((int)(W*.42f),(int)(H*.90f));
    const int modalH=(int)(H*.57f);
    m_modal=CZM_Rect((W-modalW)/2,(H-modalH)/2,modalW,modalH);
    const int mh=(int)(H*.064f),mpad=Q_max(6,(int)(H*.009f));
    for(int i=0;i<6;i++)
        m_modalButtons[i]=CZM_Rect(m_modal.x+mpad,
             m_modal.y+mpad+H*.055f+i*(mh+mpad/2),
             modalW-2*mpad,mh);
    if(m_stage==CREATE){
        m_titleRect=CZM_Rect(left,top,inner,(int)(H*.064f));
        top+=m_titleRect.h+gap;
        m_buttons[0]=CZM_Rect(left,top,(inner-gap)/2,(int)(H*.060f));
        m_buttons[1]=CZM_Rect(left+(inner+gap)/2,top,(inner-gap)/2,(int)(H*.060f));
        top+=m_buttons[0].h+gap;
        // One selected server instead of three oversized server cards.
        m_cardsRect[0]=CZM_Rect(left,top,inner,(int)(H*.106f));
        top+=m_cardsRect[0].h+gap;
        m_buttons[2]=CZM_Rect(left,top,inner,(int)(H*.052f));
        top+=m_buttons[2].h+gap;
        m_primary=CZM_Rect(left,top,inner,(int)(H*.067f));
    }else if(m_stage==SEARCH){
        m_titleRect=CZM_Rect(left,top,inner,(int)(H*.058f));
        top+=m_titleRect.h+gap;
        const int row=(int)(H*.061f);
        for(int i=0;i<CZM_LOBBY_LIST;i++)
            m_cardsRect[i]=CZM_Rect(left,top+i*(row+gap/2),inner,row);
        top+=CZM_LOBBY_LIST*(row+gap/2)+gap;
        m_buttons[0]=CZM_Rect(left,top,(inner-gap)/2,bh);
        m_buttons[1]=CZM_Rect(left+(inner+gap)/2,top,(inner-gap)/2,bh);
        // Empty state is actionable: users should not face a blank screen.
        m_buttons[2]=CZM_Rect(left+inner/5,top-H*.135f,
                               inner*3/5,(int)(H*.055f));
    }else{
        // Selected game server is one quiet strip above the party and chat.
        m_roomServerRect=CZM_Rect(left,top,inner,(int)(H*.070f));
        top+=m_roomServerRect.h+gap;
        const int col=(int)(inner*.44f),other=inner-col-gap;
        const int row=Q_max(27,(int)(H*.048f));
        for(int i=0;i<CZM_LOBBY_MEMBERS;i++)
            m_membersRect[i]=CZM_Rect(left,top+i*(row+gap/2),col,row);
        m_chatRect=CZM_Rect(left+col+gap,top,other,6*(row+gap/2)-gap/2);
        const int voiceSize=Q_max(29,(int)(H*.047f));
        m_micRect=CZM_Rect(m_chatRect.x+m_chatRect.w-voiceSize-gap/2,
                           m_chatRect.y+gap/2,voiceSize,voiceSize);
        m_voiceAllRect=CZM_Rect(m_micRect.x-voiceSize-gap/2,
                                 m_micRect.y,voiceSize,voiceSize);
        const int sendW=Q_max(34,(int)(H*.053f));
        m_textRect=CZM_Rect(m_chatRect.x,m_chatRect.y+m_chatRect.h+gap/2,
                             other-sendW-gap/2,(int)(H*.051f));
        m_sendRect=CZM_Rect(m_textRect.x+m_textRect.w+gap/2,
                             m_textRect.y,sendW,m_textRect.h);
        top+=6*(row+gap/2)+(int)(H*.056f)+gap;
        const int buttonW=(inner-gap*4)/5;
        const int footerH=Q_max(31,(int)(H*.057f));
        for(int i=0;i<5;i++)
            m_buttons[i]=CZM_Rect(left+i*(buttonW+gap),top,buttonW,footerH);
    }
}
int CCzmLobby::Hit() const{
    if(m_selectedMemberId){
        for(int i=0;i<6;i++)
            if(m_modalButtons[i].HasCursor())return MODAL_PROFILE+i;
        return MODAL_CANCEL; // tapping outside closes the action sheet
    }
    if(m_back.HasCursor())return BACK;
    if(m_refresh.HasCursor())return REFRESH;
    if(m_stage==CREATE){
        if(m_titleRect.HasCursor())return TITLE;
        if(m_buttons[2].HasCursor())return SERVER_NEXT;
        if(m_buttons[0].HasCursor())return VISIBILITY;
        if(m_buttons[1].HasCursor())return MORE;
        for(int i=0;i<3;i++)if(m_cardsRect[i].HasCursor())return SELECT+i;
        if(m_primary.HasCursor())return MAKE;
    }else if(m_stage==SEARCH){
        if(m_cardCount==0&&m_buttons[2].HasCursor())return MAKE;
        for(int i=0;i<CZM_LOBBY_LIST;i++)if(m_cardsRect[i].HasCursor())return SELECT+i;
        if(m_buttons[0].HasCursor())return PREV;
        if(m_buttons[1].HasCursor())return NEXT;
    }else {
        if(m_micRect.HasCursor())return VOICE_MIC;
        if(m_owner==CZM_OnlinePlayer()&&m_voiceAllRect.HasCursor())return VOICE_ALL;
        if(m_textRect.HasCursor())return CHAT;
        if(m_sendRect.HasCursor())return SEND;
        for(int i=0;i<CZM_LOBBY_MEMBERS;i++)if(m_membersRect[i].HasCursor())return MEMBER+i;
        for(int i=0;i<5;i++)if(m_buttons[i].HasCursor())
            return i==0?READY:i==1?LAUNCH:i==2?SERVER_NEXT:i==3?INVITE:LEAVE;
    }
    return NONE;
}
void CCzmLobby::Query(int kind,const char *method,const char *path,const char *payload){
    if(m_request||!CZM_OnlineReady())return;
    m_request=CZM_NetRequest(method,CZM_OnlineUrl(path),CZM_OnlineKey(),payload);
    if(!m_request){Notice(L("Нет соединения","Connection unavailable"));return;}
    m_kind=kind;m_busy=true;
}
void CCzmLobby::Refresh(){
    if(m_request||(!m_open&&m_stage!=ROOM))return;
    char url[190];
    if(m_stage==SEARCH){
        snprintf(url,sizeof(url),"/api/v1/lobbies?offset=%d",m_offset);
        Query(GET_LIST,"GET",url);
    }
    else if(m_stage==ROOM && m_room[0]){
        snprintf(url,sizeof(url),"/api/v1/lobbies/%s",m_room);Query(GET_ROOM,"GET",url);
    }
}
void CCzmLobby::ReadRoom(const CzmJson &j,int n){
    if(j.Type(n)!=CzmJson::T_OBJECT)return;
    Q_strncpy(m_room,j.String(j.Get(n,"id")),sizeof(m_room));
    Q_strncpy(m_roomTitle,j.String(j.Get(n,"title")),sizeof(m_roomTitle));
    const char *newServer=j.String(j.Get(n,"server"));
    if(strcmp(m_serverAddress,newServer)){
        m_pickedMap[0]=0;
        m_pickedName[0]=0; // never display another server's title
    }
    Q_strncpy(m_serverAddress,newServer,sizeof(m_serverAddress));
    Q_strncpy(m_serverProto,j.String(j.Get(n,"proto")),sizeof(m_serverProto));
    const char *map=j.String(j.Get(n,"map"));
    // Never keep displaying a thumbnail from a previous map on this server.
    Q_strncpy(m_pickedMap,map?map:"",sizeof(m_pickedMap));
    m_owner=j.Int(j.Get(n,"owner"));m_revision=j.Int(j.Get(n,"revision"));
    m_capacity=j.Int(j.Get(n,"capacity"),6);
    m_memberCount=0;
    int members=j.Get(n,"members");
    for(int i=0;i<j.Count(members)&&m_memberCount<CZM_LOBBY_MEMBERS;i++){
        int item=j.At(members,i);Member &m=m_members[m_memberCount++];
        m.id=j.Int(j.Get(item,"id"));m.ready=j.Bool(j.Get(item,"ready"));
        Q_strncpy(m.nick,j.String(j.Get(item,"nick")),sizeof(m.nick));
        Q_strncpy(m.avatar,j.String(j.Get(item,"avatar")),sizeof(m.avatar));
    }
    m_voiceAllMuted=j.Bool(j.Get(n,"voice_mute_all"));
    int voiceMuted=j.Get(n,"voice_muted");
    for(int i=0;i<m_memberCount;i++){
        m_hostMuted[i]=false;
        for(int k=0;k<j.Count(voiceMuted);k++)
            if(m_members[i].id==j.Int(j.At(voiceMuted,k)))m_hostMuted[i]=true;
    }
    // Server-side mute is authoritative. A forced-muted member must
    // not continue capturing/transmitting audio in the background.
    for(int i=0;i<m_memberCount;i++){
        if(m_members[i].id==CZM_OnlinePlayer()&&
           (m_hostMuted[i]||(m_voiceAllMuted&&m_owner!=CZM_OnlinePlayer()))){
            if(CZM_LobbyVoiceMicOn())CZM_LobbyVoiceMic(false);
            break;
        }
    }
    m_ownReady=false;
    bool found=false;
    for(int i=0;i<m_memberCount;i++){
        if(m_members[i].id==CZM_OnlinePlayer())m_ownReady=m_members[i].ready;
        if(m_members[i].id==m_selectedMemberId)found=true;
    }
    if(!found){m_selectedMemberId=0;m_memberConfirm=0;}
}

void CCzmLobby::FinishRequest(int status,const char *body,int kind){
    CzmJson j;bool parsed=j.Parse(body?body:"");
    if(status!=200||!parsed){
        const char *code=parsed?j.String(j.Get(0,"error")):"";
        if(!strcmp(code,"lobby_not_found")||!strcmp(code,"not_in_lobby")){
            if(m_stage==ROOM){
                m_room[0]=0;m_stage=SEARCH;m_offset=0;
                CZM_LobbyVoiceStop();
            }
            Notice(L("Комната уже закрыта","The room has closed"));
        }else if(!strcmp(code,"members_not_ready"))Notice(L("Не все игроки готовы","Players are not ready"));
        else if(!strcmp(code,"server_full"))Notice(L("На сервере не хватает мест","Not enough server slots"));
        else if(!strcmp(code,"server_unavailable"))Notice(L("Сервер не отвечает","Game server unavailable"));
        else if(!strcmp(code,"lobby_full"))Notice(L("Комната заполнена","The room is full"));
        else if(!strcmp(code,"language_warning")){
            const int warnings=j.Int(j.Get(0,"warnings"),0);
            char notice[120];
            if(warnings>=1&&warnings<=3){
                snprintf(notice,sizeof(notice),
                    L("Предупреждение %d из 3 · соблюдайте правила",
                      "Warning %d of 3 · follow chat rules"),warnings);
                Notice(notice);
            }else Notice(L("Предупреждение за нарушение правил",
                             "Warning for language violation"));
        }else if(!strcmp(code,"lobby_muted")){
            const int level=j.Int(j.Get(0,"level"),0);
            if(level==1)Notice(L("Мут за нарушения · до 10 минут",
                                  "Muted for violations · up to 10 min"));
            else if(level==2)Notice(L("Мут за нарушения · до 1 часа",
                                       "Muted for violations · up to 1 hour"));
            else if(level>=3)Notice(L("Мут за нарушения · до 24 часов",
                                       "Muted for violations · up to 24 hours"));
            else Notice(L("Мут за нарушения правил","Muted for violations"));
        }
        else if(!strcmp(code,"already_in_lobby"))Notice(L("Вы уже в другой комнате","You are already in a lobby"));
        else if(status==401||!strcmp(code,"account_required"))
            Notice(L("Войдите в CZM-аккаунт","Sign in to CZM"));
        else if(status==404 && (!code||!*code))
            Notice(L("Сервис лобби не запущен на сервере",
                     "Lobby service is not deployed"));
        else if(status==503)
            Notice(L("Сервер временно недоступен","Server temporarily unavailable"));
        else Notice(L("Ошибка сети. Проверьте подключение",
                      "Network request failed"));
        m_nextPoll=EngFuncs::DoubleTime()+3;
        return;
    }
    int n=j.Get(0,"lobby");
    if(kind==GET_MINE){
        if(j.Type(n)==CzmJson::T_OBJECT){
            if(kind==POST_KICK || kind==POST_TRANSFER){
                m_selectedMemberId=0;m_memberConfirm=0;
            }
            m_stage=ROOM;ReadRoom(j,n);
        }else{
            if(m_room[0]){
                m_room[0]=0;m_stage=SEARCH;CZM_LobbyVoiceStop();
            }
            if(m_stage==SEARCH)Refresh();
        }
    }else if(kind==GET_LIST){
        m_cardCount=0;
        int list=j.Get(0,"lobbies");
        // The API offers up to forty rows; our compact screen shows four.
        // Advance within that page, rather than jumping forty rooms.
        m_next=j.Count(list)>CZM_LOBBY_LIST?
               m_offset+CZM_LOBBY_LIST:-1;
        for(int i=0;i<j.Count(list)&&m_cardCount<CZM_LOBBY_LIST;i++){
            int item=j.At(list,i);RoomCard &r=m_cards[m_cardCount++];
            Q_strncpy(r.id,j.String(j.Get(item,"id")),sizeof(r.id));
            Q_strncpy(r.title,j.String(j.Get(item,"title")),sizeof(r.title));
            Q_strncpy(r.address,j.String(j.Get(item,"server")),sizeof(r.address));
            Q_strncpy(r.proto,j.String(j.Get(item,"proto")),sizeof(r.proto));
            Q_strncpy(r.map,j.String(j.Get(item,"map")),sizeof(r.map));
            r.count=j.Int(j.Get(item,"count"));
            r.capacity=j.Int(j.Get(item,"capacity"));
        }
    }else if(kind==GET_ROOM || kind==POST_JOIN || kind==POST_CREATE ||
             kind==POST_READY || kind==POST_SERVER ||
             kind==POST_KICK || kind==POST_TRANSFER){
        if(j.Type(n)==CzmJson::T_OBJECT){
            if(kind==POST_KICK||kind==POST_TRANSFER){
                m_selectedMemberId=0;m_memberConfirm=0;
            }
            m_stage=ROOM;ReadRoom(j,n);
            m_nextPoll=EngFuncs::DoubleTime()+3;
            if(kind==POST_CREATE || kind==POST_JOIN)Notice(L("Добро пожаловать в лобби","Welcome to the lobby"));
        }
    }else if(kind==GET_CHAT){
        m_chatCount=0;
        int array=j.Get(0,"messages"),count=j.Count(array);
        int start=count>CZM_LOBBY_MESSAGES?count-CZM_LOBBY_MESSAGES:0;
        for(int i=start;i<count;i++){
            int item=j.At(array,i);
            ChatLine &msg=m_chat[m_chatCount++];
            msg.sender=j.Int(j.Get(item,"sender"));
            Q_strncpy(msg.nick,j.String(j.Get(item,"nick")),sizeof(msg.nick));
            Q_strncpy(msg.text,j.String(j.Get(item,"text")),sizeof(msg.text));
        }
    }else if(kind==POST_VOICE_MUTE){
        m_selectedMemberId=0;m_memberConfirm=0;Refresh();
    }else if(kind==POST_INVITE){Notice(L("Приглашение отправлено","Invitation sent"));
    }else if(kind==POST_LEAVE){
        m_room[0]=0;CZM_LobbyVoiceStop();Hide();
    }else if(kind==POST_CHAT){
        m_text[0]=0;StopInput();
    }else if(kind==POST_LAUNCH){
        // The room is gone. The global delivery poll receives the same immutable
        // launch for all members, then acknowledges it before connecting.
        m_room[0]=0;CZM_LobbyVoiceStop();Hide();
    }
    m_nextPoll=EngFuncs::DoubleTime()+2.5;
}
void CCzmLobby::Poll(){
    if(!m_request)return;
    int code=0;CUtlString response;
    if(!CZM_NetPoll(m_request,&code,response))return;
    int kind=m_kind;m_request=0;m_kind=0;m_busy=false;
    if(!m_open&&kind!=GET_ROOM&&kind!=POST_HEARTBEAT&&kind!=POST_INVITE&&
       kind!=POST_SERVER)return;
    FinishRequest(code,response.Get(),kind);
}
void CCzmLobby::Frame(){
    Poll();
    if(!CZM_OnlineAccount()||CL_IsActive()){
        if(CZM_LobbyVoiceStatus()!=0)CZM_LobbyVoiceStop();
        return;
    }
    double now=EngFuncs::DoubleTime();
    bool inRoom=m_stage==ROOM&&m_room[0];
    if(inRoom){
        if(now>=m_nextVoicePoll){
            char path[170];
            snprintf(path,sizeof(path),"/api/v1/lobbies/%s/voice",m_room);
            CZM_LobbyVoiceStart(CZM_OnlineUrl(path),CZM_OnlineKey());
            m_nextVoicePoll=now+3;
        }
        if(m_owner==CZM_OnlinePlayer()&&now>=m_nextHeartbeat&&!m_request){
            char path[170];
            snprintf(path,sizeof(path),"/api/v1/lobbies/%s/heartbeat",m_room);
            Query(POST_HEARTBEAT,"POST",path,"{}");
            m_nextHeartbeat=now+25;return;
        }
    }else if(CZM_LobbyVoiceStatus()!=0)CZM_LobbyVoiceStop();
    if(m_request||now<m_nextPoll)return;
    if(inRoom){
        // Even when the owner visits Friends, the room must not silently expire.
        if(!m_open){Refresh();}
        else{
            char url[170];
            static bool chatTurn=false;
            if(chatTurn){
                snprintf(url,sizeof(url),"/api/v1/lobbies/%s/messages",m_room);
                Query(GET_CHAT,"GET",url);
            }else Refresh();
            chatTurn=!chatTurn;
        }
    }else if(m_open&&m_stage==SEARCH)Refresh();
    m_nextPoll=now+3;
}
void CCzmLobby::SendMessage(){
    if(m_request||!m_text[0]||!m_room[0])return;
    char path[140],nonce[80];CZM_NetNewKey(nonce,sizeof(nonce));
    snprintf(path,sizeof(path),"/api/v1/lobbies/%s/messages",m_room);
    CUtlString request;request.Append("{\"text\":");CZM_JsonQuote(request,m_text);
    request.Append(",\"nonce\":");CZM_JsonQuote(request,nonce);request.Append("}");
    Query(POST_CHAT,"POST",path,request.Get());
}
void CCzmLobby::Action(int hit){
    if(hit==VOICE_MIC){
        if(VoiceBlocked()){
            Notice(L("Микрофон выключен хозяином комнаты",
                     "The host muted your microphone"));
            CZM_LobbyVoiceMic(false);
            return;
        }
        CZM_LobbyVoiceMic(!CZM_LobbyVoiceMicOn());
        return;
    }
    if(hit==VOICE_ALL&&m_owner==CZM_OnlinePlayer()){
        char path[160];snprintf(path,sizeof(path),
                               "/api/v1/lobbies/%s/voice/mute",m_room);
        char body[80];snprintf(body,sizeof(body),
                               "{\"target\":null,\"muted\":%s}",m_voiceAllMuted?"false":"true");
        Query(POST_VOICE_MUTE,"POST",path,body);return;
    }
    if(m_selectedMemberId){
        if(hit==MODAL_CANCEL){m_selectedMemberId=m_memberConfirm=0;return;}
        if(hit==MODAL_PROFILE){
            const int id=m_selectedMemberId;
            m_selectedMemberId=m_memberConfirm=0;
            CZM_OpenProfile(id);return;
        }
        if(hit==MODAL_LOCAL_MUTE){
            int id=m_selectedMemberId;
            CZM_LobbyVoiceLocalMute(id,!CZM_LobbyVoiceIsMuted(id));
            m_selectedMemberId=m_memberConfirm=0;return;
        }
        if(m_request)return;
        if(hit==MODAL_HOST_MUTE){
            if(m_owner!=CZM_OnlinePlayer())return;
            bool muted=false;
            for(int i=0;i<m_memberCount;i++)
                if(m_members[i].id==m_selectedMemberId)muted=m_hostMuted[i];
            char path[170],body[100];
            snprintf(path,sizeof(path),"/api/v1/lobbies/%s/voice/mute",m_room);
            snprintf(body,sizeof(body),"{\"target\":%d,\"muted\":%s}",
                     m_selectedMemberId,muted?"false":"true");
            Query(POST_VOICE_MUTE,"POST",path,body);return;
        }
        if(hit==MODAL_KICK || hit==MODAL_TRANSFER){
            const int wanted=hit==MODAL_KICK?1:2;
            if(m_memberConfirm!=wanted){m_memberConfirm=wanted;return;}
            if(m_owner!=CZM_OnlinePlayer()){m_selectedMemberId=m_memberConfirm=0;return;}
            char path[170],body[80];
            snprintf(path,sizeof(path),"/api/v1/lobbies/%s/%s",m_room,
                     wanted==1?"kick":"transfer");
            snprintf(body,sizeof(body),"{\"target\":%d}",m_selectedMemberId);
            Query(wanted==1?POST_KICK:POST_TRANSFER,"POST",path,body);
            return;
        }
        return;
    }
    if(hit==BACK){
        StopInput();
        if(m_stage==ROOM && m_room[0]){
            if(m_request){Notice(L("Завершаем запрос","Finishing request"));return;}
            char path[150];snprintf(path,sizeof(path),"/api/v1/lobbies/%s/leave",m_room);
            Query(POST_LEAVE,"POST",path,"{}");
        }else Hide();
        return;
    }
    if(m_request)return;
    if(hit==REFRESH){m_nextPoll=0;Refresh();return;}
    if(m_stage==CREATE){
        if(hit==TITLE){
            m_typing=true;
            EngFuncs::SetTextInputRect(m_titleRect.x,m_titleRect.y,m_titleRect.w,m_titleRect.h);
            UI_EnableTextInput(true);return;
        }
        if(hit==VISIBILITY){m_private=!m_private;return;}
        if(hit==MORE){m_capacity=m_capacity==6?2:m_capacity+1;return;}
        if(hit==SERVER_NEXT){StopInput();CZM_LobbyServerPickerStart();return;}
        if(hit==SELECT){StopInput();CZM_LobbyServerPickerStart();return;}
        if(hit==MAKE){
            if(!CZM_OnlineAccount()){CZM_AccountShow(CZM_OnlineKey(),"");return;}
            if(!SafeAddress(m_serverAddress)){
                Notice(L("Выберите игровой сервер","Select a game server"));
                return;
            }
            if(strlen(m_title)<3){Notice(L("Название — от 3 символов","Title requires at least 3 characters"));return;}
            CZM_NetNewKey(m_nonce,sizeof(m_nonce));
            CUtlString body;body.Append("{\"title\":");CZM_JsonQuote(body,m_title);
            body.Append(",\"description\":\"\",\"visibility\":");
            CZM_JsonQuote(body,m_private?"private":"public");
            char rest[240];snprintf(rest,sizeof(rest),",\"capacity\":%d,\"server\":",m_capacity);
            body.Append(rest);CZM_JsonQuote(body,m_serverAddress);
            body.Append(",\"proto\":");CZM_JsonQuote(body,m_serverProto);
            body.Append(",\"nonce\":");CZM_JsonQuote(body,m_nonce);body.Append("}");
            Query(POST_CREATE,"POST","/api/v1/lobbies",body.Get());StopInput();
        }
    }else if(m_stage==SEARCH){
        if(hit==MAKE){Open(true);return;}
        if(hit==NEXT && m_next>=0){m_offset=m_next;Refresh();}
        if(hit==PREV && m_offset>0){m_offset=Q_max(0,m_offset-CZM_LOBBY_LIST);Refresh();}
        if(hit>=SELECT&&hit<SELECT+m_cardCount){
            char url[170];
            snprintf(url,sizeof(url),"/api/v1/lobbies/%s/join",m_cards[hit-SELECT].id);
            Query(POST_JOIN,"POST",url,"{}");
        }
    }else if(m_stage==ROOM){
        if(hit>=MEMBER&&hit<MEMBER+m_memberCount){
            int id=m_members[hit-MEMBER].id;
            if(id>0&&id!=CZM_OnlinePlayer()){
                if(m_owner==CZM_OnlinePlayer()){
                    m_selectedMemberId=id;m_memberConfirm=0;
                }else CZM_OpenProfile(id);
            }
            return;
        }
        if(hit==CHAT){
            m_typing=true;
            EngFuncs::SetTextInputRect(m_textRect.x,m_textRect.y,m_textRect.w,m_textRect.h);
            UI_EnableTextInput(true);return;
        }
        if(hit==SEND){SendMessage();return;}
        if(hit==READY){
            char url[140],body[100];
            snprintf(url,sizeof(url),"/api/v1/lobbies/%s/ready",m_room);
            snprintf(body,sizeof(body),"{\"revision\":%d,\"ready\":%s}",m_revision,m_ownReady?"false":"true");
            Query(POST_READY,"POST",url,body);return;
        }
        if(hit==LAUNCH){
            if(m_owner!=CZM_OnlinePlayer()){Notice(L("Стартует только хозяин","Host starts the match"));return;}
            bool everyoneReady=m_memberCount>=2;
            for(int i=0;i<m_memberCount;i++)
                if(m_members[i].id!=m_owner&&!m_members[i].ready)everyoneReady=false;
            if(!everyoneReady){Notice(L("Ждём готовности всех игроков","Waiting for all players to be ready"));return;}
            CZM_NetNewKey(m_nonce,sizeof(m_nonce));
            char url[140],body[190];
            snprintf(url,sizeof(url),"/api/v1/lobbies/%s/launch",m_room);
            snprintf(body,sizeof(body),"{\"revision\":%d,\"nonce\":\"%s\"}",m_revision,m_nonce);
            Query(POST_LAUNCH,"POST",url,body);return;
        }
        if(hit==LEAVE){Action(BACK);return;}
        if(hit==SERVER_NEXT){
            if(m_owner!=CZM_OnlinePlayer()){Notice(L("Сервер выбирает хозяин","Host selects the server"));return;}
            CZM_LobbyServerPickerStart();return;
        }
        if(hit==INVITE){CZM_OpenFriends();Notice(L("Выберите друга в профиле","Select a friend in their profile"));return;}
    }
}
void CCzmLobby::DrawField(const CzmRect &r,const char *placeholder){
    CZM_DrawPill(UI_DIR "button_secondary.png",r.x,r.y,r.w,r.h);
    Caption(CZM_Rect(r.x+pad,r.y,r.w-pad*2,r.h),placeholder,CZMF_PANEL_TEXT);
}
bool CCzmLobby::KeyDown(int key){
    Layout();
    if(m_typing&&UI::Key::IsBackspace(key)){
        char *t=m_stage==CREATE?m_title:m_text;
        size_t n=strlen(t);if(n){--n;while(n&&((unsigned char)t[n]&0xc0)==0x80)--n;t[n]=0;}
        return true;
    }
    if(m_typing&&UI::Key::IsEnter(key)){
        if(m_stage==ROOM)SendMessage();
        StopInput();return true;
    }
    if(UI::Key::IsEscape(key)){Action(BACK);return true;}
    if(UI::Key::IsLeftMouse(key)){
        m_pressed=Hit();
        if(m_typing&&m_pressed!=CHAT&&m_pressed!=TITLE&&m_pressed!=SEND)StopInput();
        return true;
    }
    return CMenuFramework::KeyDown(key);
}
bool CCzmLobby::KeyUp(int key){
    if(UI::Key::IsLeftMouse(key)){
        int h=Hit();
        if(h!=NONE&&h==m_pressed)Action(h);
        m_pressed=NONE;return true;
    }
    return CMenuFramework::KeyUp(key);
}
static int LobbyUtf8Chars(const char *text){
    int count=0;
    for(const unsigned char *p=(const unsigned char*)text;*p;p++)
        if((*p&0xC0)!=0x80)count++;
    return count;
}
void CCzmLobby::Char(int key){
    // Android's IME supplies UTF-8 bytes. Continuation bytes are not
    // separate characters; count code points, not the byte length.
    if(!m_typing||m_request||key<32||key>255||key==127||key=='^')return;
    char *t=m_stage==CREATE?m_title:m_text;
    size_t limit=m_stage==CREATE?sizeof(m_title):sizeof(m_text);
    size_t n=strlen(t);
    if(n+5>=limit)return;
    const bool continuation=((unsigned char)key&0xC0)==0x80;
    if(!continuation&&m_stage==CREATE&&LobbyUtf8Chars(t)>=40)return;
    if(!continuation&&m_stage==ROOM&&LobbyUtf8Chars(t)>=200)return;
    t[n]=(char)key;t[n+1]=0;
}

void CCzmLobby::PickedServer(const char *address,const char *proto,const char *name,
                              const char *map,int players,int slots){
    if(!SafeAddress(address)||(strcmp(proto,"gs")&&strcmp(proto,"49")))return;
    Q_strncpy(m_serverAddress,address,sizeof(m_serverAddress));
    Q_strncpy(m_serverProto,proto,sizeof(m_serverProto));
    Q_strncpy(m_pickedName,name?name:address,sizeof(m_pickedName));
    Q_strncpy(m_pickedMap,map?map:"",sizeof(m_pickedMap));
    if(m_stage==ROOM&&m_room[0]&&m_owner==CZM_OnlinePlayer()){
        char path[160];snprintf(path,sizeof(path),"/api/v1/lobbies/%s/server",m_room);
        CUtlString body;body.Append("{\"server\":");CZM_JsonQuote(body,address);
        body.Append(",\"proto\":");CZM_JsonQuote(body,proto);body.Append("}");
        Query(POST_SERVER,"POST",path,body.Get());
    }else m_server=-1;
}
void CCzmLobby::InviteFriend(int target){
    if(!CanInvite()||target<1){Notice(L("Сначала создайте лобби","Create a lobby first"));return;}
    if(m_request){Notice(L("Запрос выполняется","Request pending"));return;}
    char path[160],nonce[80];CZM_NetNewKey(nonce,sizeof(nonce));
    snprintf(path,sizeof(path),"/api/v1/lobbies/%s/invite/%d",m_room,target);
    char body[130];snprintf(body,sizeof(body),"{\"nonce\":\"%s\"}",nonce);
    Query(POST_INVITE,"POST",path,body);
}
void CCzmLobby::Draw(){
    Layout();UI_FillRect(0,0,W,H,PackRGBA(0,0,0,180));
    CZM_DrawPanel(m_panel);
    CZM_DrawImage(UI_DIR "chip_round.png",m_back.x,m_back.y,m_back.w,m_back.h);
    CZM_DrawImage(UI_DIR "icon_back.png",m_back.x+m_back.w/4,m_back.y+m_back.h/4,m_back.w/2,m_back.h/2);
    CZM_DrawImage(UI_DIR "icon_refresh.png",m_refresh.x+m_refresh.w/4,
                  m_refresh.y+m_refresh.h/4,m_refresh.w/2,m_refresh.h/2);
    const char *heading=m_stage==CREATE?L("СОЗДАТЬ ЛОББИ","CREATE LOBBY"):
                        m_stage==SEARCH?L("ПОИСК ЛОББИ","FIND LOBBY"):m_roomTitle;
    Caption(CZM_Rect(m_back.x+m_back.w+pad,m_back.y,m_refresh.x-m_back.x-m_back.w-2*pad,
                     m_back.h),heading,CZMF_PANEL_TITLE);
    if(m_stage==CREATE){
        DrawField(m_titleRect,m_title[0]?m_title:L("Название комнаты","Room name"));
        Button(m_buttons[0],m_private?L("ЗАКРЫТОЕ","PRIVATE"):L("ОТКРЫТОЕ","PUBLIC"),true,false);
        char cap[80];snprintf(cap,sizeof(cap),L("УЧАСТНИКОВ: %d","CAPACITY: %d"),m_capacity);
        Button(m_buttons[1],cap,true,false);
        // One legible selection row: picture, name, address and a clear change button.
        const CzmRect &rect=m_cardsRect[0];
        UI_FillRect(rect.x,rect.y,rect.w,rect.h,PackRGBA(21,32,45,244));
        UI_FillRect(rect.x,rect.y,Q_max(3,pad/3),rect.h,
                    PackRGBA(218,57,63,255));
        const int media=(int)(rect.h*1.50f),inset=Q_max(5,pad/2);
        int tx=rect.x+inset+4;
        if(m_pickedMap[0]){
            CZM_DrawMapPreview(m_pickedMap,tx,rect.y+inset/2,
                               media,rect.h-inset,m_pickedName);
            tx+=media+pad;
        }
        const int width=Q_max(50,rect.x+rect.w-tx-pad);
        Caption(CZM_Rect(tx,rect.y+inset/2,width,rect.h/2),
                m_pickedName[0]?m_pickedName:L("ВЫБЕРИТЕ СЕРВЕР","SELECT SERVER"),
                CZMF_LANG);
        char serverInfo[128];
        Q_strncpy(serverInfo,m_serverAddress,sizeof(serverInfo));
        for(int i=0;i<CZM_ServerCount();i++){
            CzmServer *info=CZM_Server(i);
            if(info&&m_serverAddress[0]&&!strcmp(info->address,m_serverAddress)){
                snprintf(serverInfo,sizeof(serverInfo),"%s · %d/%d",
                         m_serverAddress,info->players,info->maxplayers);
                break;
            }
        }
        Caption(CZM_Rect(tx,rect.y+rect.h/2,width,rect.h/2-inset/2),
                serverInfo[0]?serverInfo:L("Нажмите для выбора","Tap to choose"),
                CZMF_SMALL,CZM_Grey());
        Button(m_buttons[2],L("СМЕНИТЬ СЕРВЕР","CHANGE SERVER"),true);
        Button(m_primary,m_kind==POST_CREATE?L("СОЗДАЁМ...","CREATING..."):
                        L("СОЗДАТЬ ЛОББИ","CREATE LOBBY"),
                        SafeAddress(m_serverAddress)&&!m_request,true);
    }else if(m_stage==SEARCH){
        CZM_DrawImage(UI_DIR "icon_users.png",
                      m_titleRect.x,m_titleRect.y+m_titleRect.h/5,
                      m_titleRect.h*3/5,m_titleRect.h*3/5);
        Caption(CZM_Rect(m_titleRect.x+m_titleRect.h,m_titleRect.y,
                         m_titleRect.w-m_titleRect.h,m_titleRect.h),
                L("ПУБЛИЧНЫЕ КОМНАТЫ","PUBLIC ROOMS"),CZMF_TILE_STATUS);
        if(m_cardCount==0){
            const CzmRect &area=m_cardsRect[1];
            Caption(CZM_Rect(area.x,area.y-H*.038f,area.w,H*.070f),
                    L("Пока нет открытых комнат","No public rooms yet"),
                    CZMF_LANG,CZM_Grey());
            Button(m_buttons[2],L("СОЗДАТЬ ЛОББИ","CREATE LOBBY"),true,true);
        }
        for(int i=0;i<m_cardCount&&i<CZM_LOBBY_LIST;i++){
            const RoomCard &room=m_cards[i];const CzmRect &rect=m_cardsRect[i];
            UI_FillRect(rect.x,rect.y,rect.w,rect.h,PackRGBA(21,31,44,242));
            UI_FillRect(rect.x,rect.y,3,rect.h,PackRGBA(225,56,78,255));
            char summary[132];
            snprintf(summary,sizeof(summary),"%d/%d",room.count,room.capacity);
            int media=rect.h*1.68f,tx=rect.x+pad;
            if(room.map[0]){
                CZM_DrawMapPreview(room.map,rect.x+4,rect.y+3,media,rect.h-6,room.address);
                tx+=media+pad;
            }
            int textW=rect.x+rect.w-H*.145f-tx;
            if(textW<10)textW=10;
            Caption(CZM_Rect(tx,rect.y,textW,rect.h/2),room.title,CZMF_LANG);
            Caption(CZM_Rect(tx,rect.y+rect.h/2,textW,rect.h/2),
                    room.address,CZMF_SMALL,CZM_Grey());
            Caption(CZM_Rect(rect.x+rect.w-H*.14f,rect.y,H*.12f,rect.h),
                    summary,CZMF_LANG,PackRGBA(128,221,177,255));
        }
        // No dead pagination controls on an empty catalog.
        if(m_offset>0||m_next>=0){
            Button(m_buttons[0],L("← НАЗАД","← PREV"),m_offset>0);
            Button(m_buttons[1],L("ДАЛЬШЕ →","NEXT →"),m_next>=0);
        }
    }else if(m_stage==ROOM){
        // Immutable room capacity and current server visible to every member.
        UI_FillRect(m_roomServerRect.x,m_roomServerRect.y,
                    m_roomServerRect.w,m_roomServerRect.h,PackRGBA(24,35,49,245));
        const int inset=Q_max(7,pad/2);
        int sx=m_roomServerRect.x+inset;
        if(m_pickedMap[0]){
            const int thumbW=(int)(m_roomServerRect.h*1.45f);
            CZM_DrawMapPreview(m_pickedMap,sx,m_roomServerRect.y+2,
                                thumbW,m_roomServerRect.h-4,m_serverAddress);
            sx+=thumbW+pad;
        }else{
            CZM_DrawImage(UI_DIR "icon_globe.png",sx,
                          m_roomServerRect.y+m_roomServerRect.h/4,
                          m_roomServerRect.h/2,m_roomServerRect.h/2);
            sx+=m_roomServerRect.h/2+pad;
        }
        Caption(CZM_Rect(sx,m_roomServerRect.y,m_roomServerRect.w-(sx-m_roomServerRect.x)-pad,
                         m_roomServerRect.h/2),
                m_pickedName[0]?m_pickedName:m_serverAddress,CZMF_TILE_STATUS);
        char occupancy[130];
        snprintf(occupancy,sizeof(occupancy),"%s  ·  %d/%d",
                 m_serverAddress,m_memberCount,m_capacity);
        Caption(CZM_Rect(sx,m_roomServerRect.y+m_roomServerRect.h/2,
                         m_roomServerRect.w-(sx-m_roomServerRect.x)-pad,
                         m_roomServerRect.h/2),occupancy,CZMF_SMALL,CZM_Grey());
        for(int i=0;i<CZM_LOBBY_MEMBERS;i++){
            if(i>=m_capacity)continue;
            CzmRect rect=m_membersRect[i];
            bool occupied=i<m_memberCount;
            UI_FillRect(rect.x,rect.y,rect.w,rect.h,occupied?
                        PackRGBA(26,40,53,240):PackRGBA(15,23,35,210));
            int margin=Q_max(5,rect.h/12),av=rect.h-margin*2;
            int tx=rect.x+margin;
            if(occupied){
                const Member &member=m_members[i];
                CZM_DrawImage(CZM_AvatarFor(member.avatar,member.id),tx,rect.y+margin,av,av);
                tx+=av+margin;
                char name[110];snprintf(name,sizeof(name),"%s%s",member.nick,
                             member.id==m_owner?"  ★":"");
                const int micSpace=Q_max(24,(int)(H*.036f));
                Caption(CZM_Rect(tx,rect.y+margin,
                                 Q_max(10,rect.w-(tx-rect.x)-margin-micSpace),
                                 rect.h/2-margin),name,CZMF_TILE_STATUS);
                Caption(CZM_Rect(tx,rect.y+rect.h/2,rect.w-(tx-rect.x)-margin,
                    rect.h/2-margin),member.ready?L("Готов","Ready"):L("Не готов","Not ready"),
                    CZMF_SMALL,member.ready?PackRGBA(112,220,161,255):PackRGBA(234,165,165,255));
                const bool speaking=CZM_LobbyVoiceSpeaking(member.id);
                const bool muted=m_hostMuted[i]||CZM_LobbyVoiceIsMuted(member.id);
                if(speaking||muted){
                    const int iconSize=Q_max(21,(int)(H*.034f));
                    CZM_DrawImage(muted?UI_DIR "icon_lobby_mic_off.png":
                                        UI_DIR "icon_lobby_mic.png",
                                  rect.x+rect.w-iconSize-margin,
                                  rect.y+(rect.h-iconSize)/2,iconSize,iconSize,
                                  speaking?PackRGBA(99,229,162,255):
                                           PackRGBA(228,111,127,255));
                }
            }else Caption(CZM_Rect(tx+margin,rect.y,rect.w-3*margin,rect.h),
                         L("+ СВОБОДНО","OPEN SLOT"),CZMF_SMALL,CZM_Grey());
        }
        UI_FillRect(m_chatRect.x,m_chatRect.y,m_chatRect.w,m_chatRect.h,
                    PackRGBA(15,25,39,245));
        const int chatInset=Q_max(6,pad/2),titleH=Q_max(34,(int)(H*.052f));
        CZM_DrawImage(UI_DIR "icon_chat.png",m_chatRect.x+chatInset,
                      m_chatRect.y+titleH/4,titleH/2,titleH/2);
        Caption(CZM_Rect(m_chatRect.x+chatInset+titleH/2+chatInset,m_chatRect.y,
                Q_max(16,m_voiceAllRect.x-m_chatRect.x-3*chatInset-titleH/2),
                titleH),L("ЧАТ КОМАНДЫ","PARTY CHAT"),CZMF_TILE_STATUS);
        const bool micBlocked=VoiceBlocked();
        const bool microphoneOn=CZM_LobbyVoiceMicOn()&&!micBlocked;
        IconChip(m_micRect,microphoneOn?UI_DIR "icon_lobby_mic.png":
                UI_DIR "icon_lobby_mic_off.png",microphoneOn,micBlocked);
        // Tiny LED indicates voice transport state; no truncated words.
        const int voiceState=CZM_LobbyVoiceStatus();
        const int dot=Q_max(4,m_micRect.h/7);
        const unsigned voiceColor=voiceState==2?PackRGBA(109,226,174,255):
             voiceState==1?PackRGBA(244,191,110,255):
                           PackRGBA(236,96,109,255);
        UI_FillRect(m_micRect.x+m_micRect.w-dot-1,m_micRect.y+1,
                    dot,dot,voiceColor);
        if(m_owner==CZM_OnlinePlayer())
            IconChip(m_voiceAllRect,UI_DIR "icon_sound.png",
                     !m_voiceAllMuted,m_voiceAllMuted);
        int top=m_chatRect.y+titleH;
        if(m_chatCount==0)Caption(CZM_Rect(m_chatRect.x+inset,top,
            m_chatRect.w-2*inset,H*.06f),L("Напишите команде","Message your team"),
            CZMF_SMALL,CZM_Grey());
        int lineH=Q_max(17,(m_chatRect.h-titleH)/CZM_LOBBY_MESSAGES);
        for(int i=0;i<m_chatCount;i++){
            int y=top+i*lineH;
            ChatLine &msg=m_chat[i];
            char caption[490];
            const char *name=msg.nick[0]?msg.nick:L("Игрок","Player");
            // A single clipped line per message keeps small landscape screens readable.
            snprintf(caption,sizeof(caption),"%s: %s",name,msg.text);
            Caption(CZM_Rect(m_chatRect.x+inset,y,m_chatRect.w-inset*2,lineH),
                    caption,CZMF_SMALL);
        }
        DrawField(m_textRect,m_text[0]?m_text:L("Сообщение…","Message…"));
        IconChip(m_sendRect,UI_DIR "icon_send.png",true);
        Button(m_buttons[0],m_ownReady?L("СНЯТЬ ГОТОВ","UNREADY"):
                            L("ГОТОВ","READY"),true,m_ownReady);
        bool canStart=m_owner==CZM_OnlinePlayer()&&m_memberCount>=2;
        for(int i=0;i<m_memberCount;i++)
            if(m_members[i].id!=m_owner&&!m_members[i].ready)canStart=false;
        Button(m_buttons[1],L("В БОЙ","START"),canStart,canStart);
        Button(m_buttons[2],L("СЕРВЕР","SERVER"),m_owner==CZM_OnlinePlayer());
        Button(m_buttons[3],L("ДРУЗЬЯ","FRIENDS"));
        Button(m_buttons[4],L("ВЫЙТИ","LEAVE"));
    }
    if(m_selectedMemberId){
        UI_FillRect(0,0,W,H,PackRGBA(0,0,0,180));
        CZM_DrawPanel(m_modal);
        char caption[132];Q_strncpy(caption,L("УПРАВЛЕНИЕ ИГРОКОМ","PLAYER ACTIONS"),sizeof(caption));
        for(int i=0;i<m_memberCount;i++)if(m_members[i].id==m_selectedMemberId){
            Q_strncpy(caption,m_members[i].nick,sizeof(caption));break;
        }
        Caption(CZM_Rect(m_modal.x+pad,m_modal.y+pad,m_modal.w-2*pad,H*.058f),
                caption,CZMF_PANEL_TITLE);
        Button(m_modalButtons[0],L("ПРОФИЛЬ","PROFILE"));
        Button(m_modalButtons[1],CZM_LobbyVoiceIsMuted(m_selectedMemberId)?
               L("ВКЛЮЧИТЬ ЗВУК","UNMUTE LOCALLY"):
               L("УБРАТЬ ЗВУК","MUTE LOCALLY"));
        bool muted=false;
        for(int i=0;i<m_memberCount;i++)
            if(m_members[i].id==m_selectedMemberId)muted=m_hostMuted[i];
        Button(m_modalButtons[2],muted?L("СНЯТЬ МУТ","HOST UNMUTE"):
               L("МУТ ОТ ХОЗЯИНА","HOST MUTE"),m_owner==CZM_OnlinePlayer());
        Button(m_modalButtons[3],m_memberConfirm==1?
               L("ПОДТВЕРДИТЬ ИСКЛЮЧЕНИЕ","CONFIRM KICK"):
               L("ИСКЛЮЧИТЬ","KICK"),true,m_memberConfirm==1);
        Button(m_modalButtons[4],m_memberConfirm==2?
               L("ПОДТВЕРДИТЬ ПЕРЕДАЧУ","CONFIRM TRANSFER"):
               L("ПЕРЕДАТЬ ПРАВА","TRANSFER HOST"),true,m_memberConfirm==2);
        Button(m_modalButtons[5],L("ОТМЕНА","CANCEL"));
    }
    if(m_notice[0]&&EngFuncs::DoubleTime()<m_noticeUntil){
        // Ephemeral notices float outside the compact dialog; never cover
        // the READY / START / LEAVE controls or the chat input.
        int toastY=Q_max(4,m_panel.y-(int)(H*.061f));
        CzmRect bar=CZM_Rect(m_panel.x+pad,toastY,
                             m_panel.w-2*pad,(int)(H*.052f));
        CZM_DrawPill(UI_DIR "button_secondary.png",bar.x,bar.y,bar.w,bar.h);
        Caption(CZM_Rect(bar.x+pad,bar.y,bar.w-2*pad,bar.h),m_notice,CZMF_SMALL);
    }
}
ADD_MENU3(menu_czmlobby,CCzmLobby,UI_CzmLobby_Menu);
void UI_CzmLobby_Menu(void){menu_czmlobby->Open(false);}
void CZM_OpenLobbyCreate(void){menu_czmlobby->Open(true);}
void CZM_OpenLobbySearch(void){menu_czmlobby->Open(false);}
void CZM_OpenLobbyById(const char *id){menu_czmlobby->JoinPublic(id);}

// Match launches are one-shot events. Only their named members can read/ack.
// Running this pump through CZM_SocialFrame also works while the lobby window
// is closed; never use the lobby chat as a voice channel.
static int s_delivery=0,s_ack=0,s_identity=-1;
static double s_deliveryNext=0;
static char s_launchId[70],s_launchServer[64],s_launchProto[8];

void CZM_LobbyFrame(void){
    if(s_lobby)s_lobby->Frame();
    CZM_LobbyInviteFrame();
    if(s_identity!=CZM_OnlineIdentity()){
        if(s_identity!=-1&&s_lobby)s_lobby->ResetSession();
        s_identity=CZM_OnlineIdentity();s_deliveryNext=0;
        s_launchId[0]=s_launchServer[0]=s_launchProto[0]=0;
        s_delivery=0;s_ack=0;
    }
    if(!CZM_OnlineAccount()||!CZM_OnlinePlayAllowed())return;
    int status;CUtlString response;
    if(s_delivery&&CZM_NetPoll(s_delivery,&status,response)){
        s_delivery=0;
        if(status==200){
            CzmJson j;
            if(j.Parse(response.Get())){
                int entries=j.Get(0,"launches");
                if(j.Count(entries)>0&&!CL_IsActive()&&!CZM_QuickPlayActive()&&EngFuncs::GetCvarFloat("czm_loading")==0.0f){
                    int entry=j.At(entries,0);
                    Q_strncpy(s_launchId,j.String(j.Get(entry,"id")),sizeof(s_launchId));
                    Q_strncpy(s_launchServer,j.String(j.Get(entry,"server")),sizeof(s_launchServer));
                    Q_strncpy(s_launchProto,j.String(j.Get(entry,"proto")),sizeof(s_launchProto));
                    if(!SafeAddress(s_launchServer)||
                      (strcmp(s_launchProto,"gs")&&strcmp(s_launchProto,"49")))
                        s_launchId[0]=0;
                }
            }
        }
    }
    if(s_ack&&CZM_NetPoll(s_ack,&status,response)){
        s_ack=0;
        if(status==200&&s_launchId[0]&&SafeAddress(s_launchServer)&&!CL_IsActive()){
            CZM_LobbyVoiceStop();
            // An acknowledged launch never appears in pending again.
            EngFuncs::CvarSetString("password","");
            EngFuncs::CvarSetString("czm_connect_name",s_launchServer);
            EngFuncs::CvarSetString("czm_connect_adr",s_launchServer);
            if(s_lobby && s_lobby->IsOpened())s_lobby->Hide();
            EngFuncs::ClientCmdF(false,"connect \"%s\" %s\n",s_launchServer,s_launchProto);
        }
        s_launchId[0]=s_launchServer[0]=s_launchProto[0]=0;
        s_deliveryNext=EngFuncs::DoubleTime()+5;
    }
    if(!s_ack&&s_launchId[0]&&!CL_IsActive()){
        char url[160];snprintf(url,sizeof(url),"/api/v1/lobbies/launches/%s/ack",s_launchId);
        s_ack=CZM_NetRequest("POST",CZM_OnlineUrl(url),CZM_OnlineKey(),"{}");
    }else if(!s_delivery&&!s_ack&&!s_launchId[0]&&
             !CL_IsActive()&&EngFuncs::DoubleTime()>=s_deliveryNext){
        s_delivery=CZM_NetRequest("GET",CZM_OnlineUrl("/api/v1/lobbies/launches/pending"),
                                  CZM_OnlineKey(),"");
        s_deliveryNext=EngFuncs::DoubleTime()+5;
    }
}


void CZM_LobbyPickedServer(const char *address,const char *proto,
                           const char *name,const char *map,int players,int capacity){
    if(s_lobby)s_lobby->PickedServer(address,proto,name,map,players,capacity);
}
bool CZM_LobbyCanInvite(void){return s_lobby&&s_lobby->CanInvite();}
void CZM_LobbyInviteFriend(int player){if(s_lobby)s_lobby->InviteFriend(player);}
bool CZM_LobbyHasRoom(void){return s_lobby&&s_lobby->HasRoom();}
void CZM_LobbyOpenAccepted(void){if(s_lobby)s_lobby->Open(false);}
