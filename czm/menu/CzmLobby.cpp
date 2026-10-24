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
#include "CzmDesign.h"

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
void IconChip(const CzmRect &r,const char *icon,bool active=false,bool warning=false){
    const unsigned tint=warning?PackRGBA(218,63,77,242):
                        active?PackRGBA(31,105,78,242):
                               PackRGBA(36,48,64,244);
    CzmStyle::Surface(r,tint);
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
    enum { NONE=0, BACK, REFRESH, MAKE, VISIBILITY, TITLE,
           SELECT=100, MEMBER=200, READY=300, LAUNCH, LEAVE, SEND, CHAT, INVITE, SERVER_NEXT, NEXT, PREV,
           MODAL_PROFILE=500, MODAL_LOCAL_MUTE, MODAL_HOST_MUTE,
           MODAL_KICK, MODAL_TRANSFER, MODAL_CANCEL, VOICE_MIC, VOICE_ALL,
           CAPACITY=610, FILTER_MODE=630, BACKDROP=650 };
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
    void SetReady(bool ready);
    void StopInput();
    bool VoiceBlocked() const;
    bool CanStart() const;
    void ServerSummary(char *out,size_t size);
    void DrawField(const CzmRect &r,const char *placeholder);
    int m_stage,m_request,m_kind,m_pressed,m_capacity,m_server,m_offset,m_next;
    int m_filterMode,m_pickedPlayers,m_pickedSlots;
    bool m_closePending;
    bool m_needMine;
    bool m_readyQueued,m_readyTarget;
    int m_readEpoch,m_pendingEpoch;
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
    CzmRect m_visibilityRect,m_switchRect,m_capacityRect[5],m_filterRect[3],m_teamTitleRect,m_catalogRect;
    CzmRect m_createMapRect,m_createInfoRect;
    int W,H,pad;
};

static CCzmLobby *s_lobby;
static int LobbyUtf8Chars(const char *text);

CCzmLobby::CCzmLobby():CMenuFramework("CzmLobby"){
    s_lobby=this; m_stage=CREATE; m_request=m_kind=m_pressed=0;m_capacity=6;
    m_server=m_offset=m_next=m_owner=m_revision=m_memberCount=m_chatCount=m_cardCount=0;
    m_selectedMemberId=m_memberConfirm=0;
    m_filterMode=0;m_next=-1;m_closePending=false;m_pickedPlayers=m_pickedSlots=-1;
    m_needMine=false;m_readEpoch=m_pendingEpoch=0;
    m_readyQueued=m_readyTarget=false;
    m_open=m_private=m_typing=m_ownReady=m_busy=m_voiceAllMuted=false;
    memset(m_hostMuted,0,sizeof(m_hostMuted));m_nextPoll=m_nextHeartbeat=m_nextVoicePoll=m_noticeUntil=0;
    m_title[0]=m_description[0]=m_room[0]=m_serverAddress[0]=m_serverProto[0]=0;
    m_notice[0]=m_text[0]=m_lastText[0]=m_nonce[0]=m_ownerName[0]=m_roomTitle[0]=m_pickedName[0]=m_pickedMap[0]=0;
    W=H=pad=0;
}

void CCzmLobby::Show() {
    CZM_Init();m_open=true;m_pressed=0;m_needMine=true;
    CMenuFramework::Show();
    Query(GET_MINE,"GET","/api/v1/lobbies/mine");
}
void CCzmLobby::Open(bool create){
    if(!CZM_OnlineAccount()){CZM_AccountShow(CZM_OnlineKey(),"");return;}
    if(m_closePending){CZM_ShowMessage(L("Завершаем предыдущий запрос","Finishing the previous request"));return;}
    if(!m_open){
        ++m_readEpoch;
        if(m_room[0]){
            m_stage=ROOM;
            Show(); // reconcile ownership and expiry with /mine
            return;
        }
        m_stage=create?CREATE:SEARCH; m_offset=0;
        m_cardCount=0;m_next=-1;m_filterMode=0;
        m_pickedPlayers=m_pickedSlots=-1;
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
            m_pickedPlayers=first->players;m_pickedSlots=first->maxplayers;
        }
        Show();
    }else{
        // Coming back from the friends/server browser must never silently
        // abandon or hide an active temporary room.
        if(m_room[0]){m_stage=ROOM;Refresh();}
        else{
            ++m_readEpoch;m_needMine=true;m_stage=create?CREATE:SEARCH;m_offset=0;
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
    m_closePending=false;
    m_needMine=false;++m_readEpoch;
    m_readyQueued=false;
    m_room[0]=m_roomTitle[0]=m_text[0]=m_pickedMap[0]=0;
    m_memberCount=m_chatCount=m_selectedMemberId=m_memberConfirm=0;
    m_owner=0;m_stage=SEARCH;m_nextVoicePoll=0;m_nextHeartbeat=0;
    if(m_open)Hide();
}
void CCzmLobby::Hide(){StopInput();m_open=false;m_pressed=0;m_selectedMemberId=0;m_memberConfirm=0;++m_readEpoch;CMenuFramework::Hide();}
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
    W=ScreenWidth;H=ScreenHeight;
    pad=Q_max(8,(int)(H*(m_stage==ROOM?.028f:.024f)));
    const int gap=Q_max(5,(int)(H*(m_stage==ROOM?.016f:.014f)));
    const int bh=Q_max(30,(int)(H*(m_stage==ROOM?.068f:.062f)));
    const int header=Q_max(32,(int)(H*.070f));
    const int label=Q_max(10,CZM_FontHeight(CZM_Font(CZMF_UI_META))+gap/2);
    const int pw=Q_min(W-pad*2,m_stage==ROOM?(int)(W*.89f):
        Q_min((int)(W*.70f),(int)(H*(m_stage==CREATE?1.48f:1.60f))));
    const int rowH=Q_max(48,(int)(H*.105f));
    const int listRows=Q_min(m_cardCount,CZM_LOBBY_LIST);
    const bool paging=m_offset>0||m_next>=0;
    const int listH=listRows?listRows*rowH+(listRows-1)*gap:Q_max(95,(int)(H*.20f));
    const int createH=2*pad+header+gap+3*(label+bh)+2*gap+gap+bh;
    const int searchH=2*pad+header+gap+bh+gap+listH+(paging?gap+bh:0);
    const int ph=m_stage==ROOM?Q_min(H-pad,(int)(H*(H<480?.94f:.86f))):
        Q_min(H-pad*2,m_stage==CREATE?createH:searchH);
    m_panel=CZM_Rect((W-pw)/2,(H-ph)/2,pw,ph);
    const int left=m_panel.x+pad,inner=pw-2*pad;
    int top=m_panel.y+pad;
    m_back=CZM_Rect(left,top,header,header);
    m_refresh=CZM_Rect(left+inner-header,top,header,header);
    top+=header+gap;
    m_titleRect=m_primary=m_secondary=m_extra=CZM_Rect(0,0,0,0);
    for(int i=0;i<9;i++)m_buttons[i]=CZM_Rect(0,0,0,0);
    for(int i=0;i<CZM_LOBBY_LIST;i++)m_cardsRect[i]=CZM_Rect(0,0,0,0);
    for(int i=0;i<CZM_LOBBY_MEMBERS;i++)m_membersRect[i]=CZM_Rect(0,0,0,0);
    m_visibilityRect=m_switchRect=m_catalogRect=CZM_Rect(0,0,0,0);
    m_createMapRect=m_createInfoRect=CZM_Rect(0,0,0,0);
    for(int i=0;i<5;i++)m_capacityRect[i]=CZM_Rect(0,0,0,0);
    for(int i=0;i<3;i++)m_filterRect[i]=CZM_Rect(0,0,0,0);
    m_chatRect=m_textRect=m_sendRect=m_micRect=m_voiceAllRect=m_roomServerRect=m_teamTitleRect=CZM_Rect(0,0,0,0);
    const int footer=m_panel.y+ph-pad-bh;
    const int modalW=Q_min(W-pad*4,(int)(H*.78f));
    const int modalH=Q_min(H-pad*2,(int)(H*.76f));
    m_modal=CZM_Rect((W-modalW)/2,(H-modalH)/2,modalW,modalH);
    const int modalGap=Q_max(4,gap/2);
    const int mh=(modalH-pad*2-header-modalGap*6)/6;
    for(int i=0;i<6;i++)m_modalButtons[i]=CZM_Rect(m_modal.x+pad,
        m_modal.y+pad+header+modalGap+i*(mh+modalGap),modalW-pad*2,mh);

    if(m_stage==CREATE){
        const int col=(inner-gap)*53/100,right=inner-col-gap;
        const int bodyH=footer-gap-top;
        const int group=label+bh+gap;
        m_titleRect=CZM_Rect(left,top+label,col,bh);
        m_visibilityRect=CZM_Rect(left,top+group+label,col,bh);
        const int toggleH=Q_max(20,(int)(bh*.67f)),toggleW=toggleH*19/10;
        m_switchRect=CZM_Rect(left+col-gap-toggleW,m_visibilityRect.y+(bh-toggleH)/2,toggleW,toggleH);
        const int slot=(col-gap*4)/5;
        for(int i=0;i<5;i++)m_capacityRect[i]=CZM_Rect(left+i*(slot+gap),top+group*2+label,slot,bh);
        m_cardsRect[0]=CZM_Rect(left+col+gap,top,right,bodyH);
        m_buttons[2]=CZM_Rect(m_cardsRect[0].x+gap,m_cardsRect[0].y+bodyH-gap-bh,right-gap*2,bh);
        const int photo=Q_min(bodyH-bh-gap*3,(right-gap*3)*2/5);
        m_createMapRect=CZM_Rect(m_cardsRect[0].x+gap,top+gap,photo,photo);
        m_createInfoRect=CZM_Rect(m_createMapRect.x+photo+gap,top+gap,
            right-photo-gap*3,m_buttons[2].y-top-gap*2);
        m_primary=CZM_Rect(left+col+gap,footer,right,bh);
    }else if(m_stage==SEARCH){
        const int fw=(inner-gap*2)/3;
        for(int i=0;i<3;i++)m_filterRect[i]=CZM_Rect(left+i*(fw+gap),top,fw,bh);
        top+=bh+gap;
        const int pagingH=paging?bh+gap:0;
        const int available=m_panel.y+m_panel.h-pad-top-pagingH;
        m_catalogRect=CZM_Rect(left,top,inner,available);
        const int row=listRows?Q_min(rowH,(available-gap*(listRows-1))/listRows):0;
        for(int i=0;i<listRows;i++)m_cardsRect[i]=CZM_Rect(left,top+i*(row+gap),inner,row);
        const int pagingW=Q_min(inner/3,(int)(H*.22f));
        if(m_offset>0)m_buttons[0]=CZM_Rect(left,footer,pagingW,bh);
        if(m_next>=0)m_buttons[1]=CZM_Rect(left+inner-pagingW,footer,pagingW,bh);
    }else{
        m_roomServerRect=CZM_Rect(left,top,inner,Q_max(36,(int)(H*.085f)));
        top+=m_roomServerRect.h+gap;
        const int col=(inner-gap)*53/100,other=inner-col-gap;
        const int section=Q_max(24,(int)(H*.047f));
        const int status=Q_max(14,CZM_FontHeight(CZM_Font(CZMF_UI_META))+gap);
        const int bottom=footer-status-gap/2;
        m_teamTitleRect=CZM_Rect(left,top,col,section);
        const int rows=(bound(2,m_capacity,6)+1)/2;
        const int gridTop=top+section+gap/2;
        const int gridH=bottom-gridTop;
        const int cellW=(col-gap)/2;
        const int rowH=Q_min((gridH-gap*(rows-1))/rows,(int)(H*.16f));
        for(int i=0;i<m_capacity&&i<CZM_LOBBY_MEMBERS;i++)
            m_membersRect[i]=CZM_Rect(left+(i%2)*(cellW+gap),gridTop+(i/2)*(rowH+gap),cellW,rowH);
        m_chatRect=CZM_Rect(left+col+gap,top,other,bottom-top);
        const int voice=Q_max(25,section);
        m_micRect=CZM_Rect(m_chatRect.x+other-gap-voice,top,voice,voice);
        m_voiceAllRect=CZM_Rect(m_micRect.x-voice-gap/2,top,voice,voice);
        m_sendRect=CZM_Rect(m_chatRect.x+other-gap-bh,bottom-gap-bh,bh,bh);
        m_textRect=CZM_Rect(m_chatRect.x+gap,bottom-gap-bh,other-gap*3-bh,bh);
        const int startW=inner*22/100,readyW=inner*19/100;
        const int utility=(inner-startW-readyW-gap*4)/3;
        m_buttons[0]=CZM_Rect(left,footer,readyW,bh);
        for(int i=2;i<5;i++)m_buttons[i]=CZM_Rect(left+readyW+gap+(i-2)*(utility+gap),footer,utility,bh);
        m_buttons[1]=CZM_Rect(left+inner-startW,footer,startW,bh);
    }
}
int CCzmLobby::Hit() const{
    if(m_selectedMemberId){
        for(int i=0;i<6;i++)
            if(m_modalButtons[i].HasCursor()){
                if(i>=2&&i<=4&&m_owner!=CZM_OnlinePlayer())return NONE;
                return MODAL_PROFILE+i;
            }
        return MODAL_CANCEL; // tapping outside closes the action sheet
    }
    if(!m_panel.HasCursor())return m_stage==CREATE||m_stage==SEARCH?BACKDROP:NONE;
    if(m_back.HasCursor())return BACK;
    if(m_stage!=CREATE&&m_refresh.HasCursor())return REFRESH;
    if(m_stage==CREATE){
        if(m_titleRect.HasCursor())return TITLE;
        if(m_buttons[2].HasCursor())return SERVER_NEXT;
        if(m_visibilityRect.HasCursor())return VISIBILITY;
        for(int i=0;i<5;i++)if(m_capacityRect[i].HasCursor())return CAPACITY+i;
        if(m_cardsRect[0].HasCursor())return SELECT;
        if(m_primary.HasCursor())return MAKE;
    }else if(m_stage==SEARCH){
        for(int i=0;i<3;i++)if(m_filterRect[i].HasCursor())return FILTER_MODE+i;
        for(int i=0;i<m_cardCount;i++)if(m_cardsRect[i].HasCursor())return SELECT+i;
        if(m_offset>0&&m_buttons[0].HasCursor())return PREV;
        if(m_next>=0&&m_buttons[1].HasCursor())return NEXT;
    }else {
        if(m_micRect.HasCursor())return VOICE_MIC;
        if(m_owner==CZM_OnlinePlayer()&&m_voiceAllRect.HasCursor())return VOICE_ALL;
        if(m_textRect.HasCursor())return CHAT;
        if(m_sendRect.HasCursor())return SEND;
        for(int i=0;i<m_capacity&&i<CZM_LOBBY_MEMBERS;i++)if(m_membersRect[i].HasCursor())
            return i<m_memberCount?MEMBER+i:m_owner==CZM_OnlinePlayer()?INVITE:NONE;
        for(int i=0;i<5;i++)if(m_buttons[i].HasCursor())
            return i==0?READY:i==1?LAUNCH:i==2?SERVER_NEXT:i==3?INVITE:LEAVE;
    }
    return NONE;
}
void CCzmLobby::Query(int kind,const char *method,const char *path,const char *payload){
    if(m_request||!CZM_OnlineReady())return;
    m_request=CZM_NetRequest(method,CZM_OnlineUrl(path),CZM_OnlineKey(),payload);
    if(!m_request){Notice(L("Нет соединения","Connection unavailable"));return;}
    m_kind=kind;m_busy=true;m_pendingEpoch=m_readEpoch;
    if(kind==GET_MINE)m_needMine=false;
}
void CCzmLobby::Refresh(){
    if(m_request||(!m_open&&m_stage!=ROOM))return;
    char url[190];
    if(m_stage==SEARCH){
        const char *modes[]={"","ze","zs"};
        snprintf(url,sizeof(url),"/api/v1/lobbies?offset=%d&mode=%s",m_offset,modes[m_filterMode]);
        Query(GET_LIST,"GET",url);
    }
    else if(m_stage==ROOM && m_room[0]){
        snprintf(url,sizeof(url),"/api/v1/lobbies/%s",m_room);Query(GET_ROOM,"GET",url);
    }
}
void CCzmLobby::ReadRoom(const CzmJson &j,int n){
    if(j.Type(n)!=CzmJson::T_OBJECT)return;
    const char *newRoom=j.String(j.Get(n,"id"));
    if(strcmp(m_room,newRoom)){
        m_readyQueued=false;
        StopInput();m_text[0]=0;m_chatCount=0;
        m_nextVoicePoll=0;CZM_LobbyVoiceStop();
    }
    Q_strncpy(m_room,j.String(j.Get(n,"id")),sizeof(m_room));
    Q_strncpy(m_roomTitle,j.String(j.Get(n,"title")),sizeof(m_roomTitle));
    const char *newServer=j.String(j.Get(n,"server"));
    if(strcmp(m_serverAddress,newServer)){
        m_pickedMap[0]=0;
        m_pickedName[0]=0; // never display another server's title
        m_pickedPlayers=m_pickedSlots=-1;
    }
    Q_strncpy(m_serverAddress,newServer,sizeof(m_serverAddress));
    Q_strncpy(m_serverProto,j.String(j.Get(n,"proto")),sizeof(m_serverProto));
    const char *map=j.String(j.Get(n,"map"));
    // Never keep displaying a thumbnail from a previous map on this server.
    Q_strncpy(m_pickedMap,map?map:"",sizeof(m_pickedMap));
    m_owner=j.Int(j.Get(n,"owner"));m_revision=j.Int(j.Get(n,"revision"));
    m_capacity=j.Int(j.Get(n,"capacity"),6);
    m_capacity=bound(2,m_capacity,6);
    m_private=!strcmp(j.String(j.Get(n,"visibility")),"private");
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
        if(m_closePending){
            const bool gone=!strcmp(code,"lobby_not_found")||!strcmp(code,"not_in_lobby");
            if(gone||((kind==POST_CREATE||kind==POST_JOIN)&&status>=400&&status<500)){
                m_closePending=false;m_room[0]=0;CZM_LobbyVoiceStop();
            }
            // Ambiguous network failures are reconciled through /mine before
            // dropping a create/join operation; a hidden owner cannot be lost.
            m_nextPoll=EngFuncs::DoubleTime()+3;return;
        }
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
            if(m_closePending){Action(BACK);return;}
        }else{
            m_closePending=false;
            if(m_room[0]){
                m_room[0]=0;m_stage=SEARCH;CZM_LobbyVoiceStop();
            }
            if(m_open&&m_stage==SEARCH)Refresh();
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
            if(m_closePending){Action(BACK);return;}
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
        m_room[0]=0;m_text[0]=0;m_chatCount=0;m_closePending=false;CZM_LobbyVoiceStop();Hide();
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
    if(kind==GET_LIST&&m_pendingEpoch!=m_readEpoch){m_nextPoll=0;return;}
    if(!m_open&&!m_closePending&&kind!=GET_MINE&&kind!=GET_ROOM&&kind!=POST_HEARTBEAT&&kind!=POST_INVITE&&
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
    if(m_closePending){
        if(!m_request&&now>=m_nextPoll)Query(GET_MINE,"GET","/api/v1/lobbies/mine");
        return;
    }
    if(m_open&&m_needMine&&!m_request){Query(GET_MINE,"GET","/api/v1/lobbies/mine");return;}
    bool inRoom=m_stage==ROOM&&m_room[0];
    if(!inRoom)m_readyQueued=false;
    if(inRoom&&m_readyQueued&&!m_request){
        m_readyQueued=false;
        if(m_ownReady!=m_readyTarget){SetReady(m_readyTarget);return;}
    }
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
void CCzmLobby::SetReady(bool ready){
    char url[140],body[100];
    snprintf(url,sizeof(url),"/api/v1/lobbies/%s/ready",m_room);
    snprintf(body,sizeof(body),"{\"revision\":%d,\"ready\":%s}",m_revision,ready?"true":"false");
    Query(POST_READY,"POST",url,body);
}
void CCzmLobby::Action(int hit){
    if(m_stage==ROOM&&hit>=MEMBER&&hit<MEMBER+m_memberCount&&
       m_members[hit-MEMBER].id==CZM_OnlinePlayer()){
        StopInput();CZM_LobbyVoiceTest();return;
    }
    if(hit==BACKDROP){
        if(m_stage==CREATE||m_stage==SEARCH){
            if(m_request&&(m_kind==POST_CREATE||m_kind==POST_JOIN))m_closePending=true;
            Hide();
        }
        return;
    }
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
            if(m_owner!=CZM_OnlinePlayer())return;
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
        if(m_stage==CREATE||m_stage==SEARCH){Action(BACKDROP);return;}
        StopInput();
        if(m_stage==ROOM && m_room[0]){
            if(m_request){Notice(L("Завершаем запрос","Finishing request"));return;}
            char path[150];snprintf(path,sizeof(path),"/api/v1/lobbies/%s/leave",m_room);
            Query(POST_LEAVE,"POST",path,"{}");
        }else Hide();
        return;
    }
    if(m_request){
        // Background reads must neither flash the button nor swallow a tap.
        // Apply the requested state after the read, with its current revision.
        if(hit==READY&&m_stage==ROOM&&m_room[0]&&!m_readyQueued&&
           (m_kind==GET_ROOM||m_kind==GET_CHAT||m_kind==GET_MINE||m_kind==POST_HEARTBEAT)){
            m_readyQueued=true;m_readyTarget=!m_ownReady;
        }
        return;
    }
    if(hit==REFRESH){m_nextPoll=0;Refresh();return;}
    if(m_stage==CREATE){
        if(hit>=CAPACITY&&hit<CAPACITY+5){StopInput();m_capacity=hit-CAPACITY+2;return;}
        if(hit==TITLE){
            m_typing=true;
            EngFuncs::SetTextInputRect(m_titleRect.x,m_titleRect.y,m_titleRect.w,m_titleRect.h);
            UI_EnableTextInput(true);return;
        }
        if(hit==VISIBILITY){m_private=!m_private;return;}
        if(hit==SERVER_NEXT){StopInput();CZM_LobbyServerPickerStart();return;}
        if(hit==SELECT){StopInput();CZM_LobbyServerPickerStart();return;}
        if(hit==MAKE){
            if(!CZM_OnlineAccount()){CZM_AccountShow(CZM_OnlineKey(),"");return;}
            if(!SafeAddress(m_serverAddress)){
                Notice(L("Выберите игровой сервер","Select a game server"));
                return;
            }
            char title[sizeof(m_title)];const char *start=m_title;
            while(*start==' ')++start;
            Q_strncpy(title,start,sizeof(title));
            size_t len=strlen(title);while(len&&title[len-1]==' ')title[--len]=0;
            if(LobbyUtf8Chars(title)<3||LobbyUtf8Chars(title)>40){
                Notice(L("Название — от 3 до 40 символов","Use 3 to 40 characters for the name"));return;
            }
            CZM_NetNewKey(m_nonce,sizeof(m_nonce));
            CUtlString body;body.Append("{\"title\":");CZM_JsonQuote(body,title);
            body.Append(",\"description\":\"\",\"visibility\":");
            CZM_JsonQuote(body,m_private?"private":"public");
            char rest[240];snprintf(rest,sizeof(rest),",\"capacity\":%d,\"server\":",m_capacity);
            body.Append(rest);CZM_JsonQuote(body,m_serverAddress);
            body.Append(",\"proto\":");CZM_JsonQuote(body,m_serverProto);
            body.Append(",\"nonce\":");CZM_JsonQuote(body,m_nonce);body.Append("}");
            Query(POST_CREATE,"POST","/api/v1/lobbies",body.Get());StopInput();
        }
    }else if(m_stage==SEARCH){
        if(hit>=FILTER_MODE&&hit<FILTER_MODE+3){
            m_filterMode=hit-FILTER_MODE;
            m_offset=0;m_next=-1;m_cardCount=0;Refresh();return;
        }
        if(hit==NEXT && m_next>=0){m_offset=m_next;Refresh();}
        if(hit==PREV && m_offset>0){m_offset=Q_max(0,m_offset-CZM_LOBBY_LIST);Refresh();}
        if(hit>=SELECT&&hit<SELECT+m_cardCount){
            if(m_cards[hit-SELECT].count>=m_cards[hit-SELECT].capacity){
                Notice(L("Комната заполнена","The room is full"));return;
            }
            char url[170];
            snprintf(url,sizeof(url),"/api/v1/lobbies/%s/join",m_cards[hit-SELECT].id);
            Query(POST_JOIN,"POST",url,"{}");
        }
    }else if(m_stage==ROOM){
        if(hit>=MEMBER&&hit<MEMBER+m_memberCount){
            int id=m_members[hit-MEMBER].id;
            if(id>0&&id!=CZM_OnlinePlayer()){
                m_selectedMemberId=id;m_memberConfirm=0;
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
            SetReady(!m_ownReady);return;
        }
        if(hit==LAUNCH){
            if(m_owner!=CZM_OnlinePlayer()){Notice(L("Стартует только хозяин","Host starts the match"));return;}
            if(!CanStart()){Notice(L("Ждём готовности всех игроков","Waiting for all players to be ready"));return;}
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
    const bool focused=m_typing&&((m_stage==CREATE&&r.x==m_titleRect.x&&r.y==m_titleRect.y)||m_stage==ROOM);
    CzmStyle::Surface(r,PackRGBA(13,19,28,255),focused?CzmStyle::AccentBlue():CzmStyle::Border());
    Caption(CZM_Rect(r.x+pad/2,r.y,r.w-pad,r.h),placeholder,CZMF_UI_LABEL);
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
    m_pickedPlayers=players;m_pickedSlots=slots;
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
bool CCzmLobby::CanStart() const{
    if(m_owner!=CZM_OnlinePlayer()||m_memberCount<2)return false;
    for(int i=0;i<m_memberCount;i++)
        if(m_members[i].id!=m_owner&&!m_members[i].ready)return false;
    return true;
}
void CCzmLobby::ServerSummary(char *out,size_t size){
    for(int i=0;i<CZM_ServerCount();i++){
        CzmServer *info=CZM_Server(i);
        if(info&&!strcmp(info->address,m_serverAddress)){
            m_pickedPlayers=info->players;m_pickedSlots=info->maxplayers;
            if(info->name[0])CZM_CleanName(info->name,m_pickedName,sizeof(m_pickedName));
            if(info->map[0])Q_strncpy(m_pickedMap,info->map,sizeof(m_pickedMap));
            break;
        }
    }
    const char *mode=!strncmp(m_pickedMap,"ze_",3)?"Zombie Escape":
                     !strncmp(m_pickedMap,"zm_",3)?"Zombie Survivor":L("Игровой сервер","Game server");
    if(m_pickedSlots>0&&m_pickedPlayers>=0)
        snprintf(out,size,L("%s · На сервере %d/%d","%s · Server %d/%d"),mode,m_pickedPlayers,m_pickedSlots);
    else snprintf(out,size,"%s · %s",mode,m_pickedMap[0]?m_pickedMap:L("Онлайн уточняется","Checking server"));
}
void CCzmLobby::Draw(){
    Layout();
    UI_FillRect(0,0,W,H,PackRGBA(3,7,13,218));
    CzmStyle::Surface(m_panel,PackRGBA(14,20,29,253),PackRGBA(56,67,84,255));
    const int gap=Q_max(5,(int)(H*(m_stage==ROOM?.016f:.014f)));
    const int label=Q_max(10,CZM_FontHeight(CZM_Font(CZMF_UI_META))+gap/2);
    const unsigned accent=m_stage==CREATE?CzmStyle::AccentBlue():m_stage==SEARCH?CzmStyle::AccentGold():CzmStyle::AccentRed();
    UI_FillRect(m_panel.x+pad,m_panel.y,Q_min((int)(H*.12f),m_panel.w/6),2,accent);
    CzmStyle::Button(m_back,"",true,false,m_pressed==BACK,accent);
    CzmStyle::Icon(m_back,UI_DIR "icon_back.png");
    if(m_stage!=CREATE){
        CzmStyle::Button(m_refresh,"",!m_request,false,m_pressed==REFRESH,accent);
        CzmStyle::Icon(m_refresh,UI_DIR "icon_refresh.png",m_request?CzmStyle::Muted():CzmStyle::Ink());
    }
    const char *heading=m_stage==CREATE?L("Создать лобби","Create lobby"):
                        m_stage==SEARCH?L("Поиск лобби","Find lobby"):m_roomTitle;
    const int headX=m_back.x+m_back.w+gap;
    const int headW=m_refresh.x-headX-gap;
    CzmStyle::Text(CZM_Rect(headX,m_back.y-2,headW,m_back.h*62/100),heading,CZMF_UI_TITLE);
    const char *sub=m_stage==CREATE?L("Собери команду перед игрой","Bring your team together"):
                    m_stage==SEARCH?L("Публичные комнаты · Выбери свою команду","Public rooms · Find your team"):
                    m_private?L("По приглашению · Временная комната","Invite only · Temporary room"):
                              L("Открытое лобби · Временная комната","Public lobby · Temporary room");
    CzmStyle::Text(CZM_Rect(headX,m_back.y+m_back.h*62/100,headW,m_back.h*38/100),sub,CZMF_UI_META,CzmStyle::Muted());

    if(m_stage==CREATE){
        CzmStyle::Text(CZM_Rect(m_titleRect.x,m_titleRect.y-label,m_titleRect.w,label),
            L("НАЗВАНИЕ ЛОББИ","LOBBY NAME"),CZMF_UI_META,CzmStyle::Muted());
        DrawField(m_titleRect,m_title[0]?m_title:L("Название команды","Team name"));
        CzmStyle::Text(CZM_Rect(m_visibilityRect.x,m_visibilityRect.y-label,m_visibilityRect.w,label),
            L("ДОСТУП","VISIBILITY"),CZMF_UI_META,CzmStyle::Muted());
        CzmStyle::Surface(m_visibilityRect,PackRGBA(25,34,47,255));
        const int tx=m_visibilityRect.x+gap;
        const int tw=m_switchRect.x-tx-gap;
        const int fh=CZM_FontHeight(CZM_Font(CZMF_UI_LABEL));
        CzmStyle::Text(CZM_Rect(tx,m_visibilityRect.y+gap/3,tw,fh),
            L("Открытое лобби","Public lobby"),CZMF_UI_LABEL);
        CzmStyle::Text(CZM_Rect(tx,m_visibilityRect.y+fh+gap/3,tw,m_visibilityRect.h-fh-gap/3),
            m_private?L("Закрытое · Только по приглашению","Private · Invite only"):
                      L("Открытое · Свободный вход","Public · Anyone can join"),CZMF_UI_META,CzmStyle::Muted());
        CzmStyle::Switch(m_switchRect,!m_private);
        CzmStyle::Text(CZM_Rect(m_capacityRect[0].x,m_capacityRect[0].y-label,m_titleRect.w,label),
            L("МЕСТ В КОМАНДЕ · ВКЛЮЧАЯ ТЕБЯ","TEAM CAPACITY · INCLUDING YOU"),CZMF_UI_META,CzmStyle::Muted());
        for(int i=0;i<5;i++){
            char count[8];snprintf(count,sizeof(count),"%d",i+2);
            CzmStyle::Button(m_capacityRect[i],count,true,false,m_capacity==i+2,m_capacity==i+2?accent:0);
        }

        const CzmRect r=m_cardsRect[0];
        CzmStyle::Surface(r,PackRGBA(20,29,41,255));
        const CzmRect info=m_createInfoRect;
        const int th=CZM_FontHeight(CZM_Font(CZMF_UI_LABEL));
        char summary[160];ServerSummary(summary,sizeof(summary));
        CzmStyle::MapPreview(m_createMapRect,m_pickedMap,m_pickedName);
        CzmStyle::Text(CZM_Rect(info.x,info.y,info.w,label),L("ВЫБРАННЫЙ СЕРВЕР","SELECTED SERVER"),CZMF_UI_META,accent);
        CzmStyle::TextLines(CZM_Rect(info.x,info.y+label,info.w,th*2),
            m_pickedName[0]?m_pickedName:L("Выбери игровой сервер","Select a game server"),CZMF_UI_LABEL);
        CzmStyle::Text(CZM_Rect(info.x,info.y+label+th*2+gap/2,info.w,label),summary,CZMF_UI_META,CzmStyle::Muted());
        CzmStyle::Text(CZM_Rect(info.x,info.y+label*2+th*2+gap/2,info.w,label),m_pickedMap,CZMF_UI_META,CzmStyle::Muted());
        CzmStyle::Button(m_buttons[2],SafeAddress(m_serverAddress)?L("Изменить сервер","Change server"):L("Выбрать сервер","Select server"),true,false,m_pressed==SERVER_NEXT,accent);
        CzmStyle::Button(m_primary,m_kind==POST_CREATE?L("Создаём…","Creating…"):L("Создать лобби","Create lobby"),
            SafeAddress(m_serverAddress)&&!m_request,true,m_pressed==MAKE,0,CZMF_UI_ACTION);
        CzmStyle::Text(CZM_Rect(m_titleRect.x,m_primary.y,m_titleRect.w,m_primary.h),
            L("Лобби существует до выхода хозяина или старта игры","The lobby closes when the host leaves or starts"),CZMF_UI_META,CzmStyle::Muted());
    }else if(m_stage==SEARCH){
        const char *filters[]={L("Все режимы","All modes"),"Zombie Escape","Zombie Survivor"};
        for(int i=0;i<3;i++){
            const bool selected=m_filterMode==i;
            CzmStyle::Button(m_filterRect[i],filters[i],!m_request,false,selected,selected?accent:0);
        }
        if(m_cardCount==0){
            const CzmRect area=m_catalogRect;
            const int side=Q_max(28,(int)(H*.07f));
            const int titleH=CZM_FontHeight(CZM_Font(CZMF_UI_ACTION));
            const int metaH=CZM_FontHeight(CZM_Font(CZMF_UI_META))+gap/2;
            const int total=side+gap+titleH+gap/2+metaH;
            const int y=area.y+(area.h-total)/2;
            CZM_DrawImage(UI_DIR "icon_users.png",area.x+(area.w-side)/2,y,side,side,PackRGBA(98,115,140,255));
            CzmStyle::Text(CZM_Rect(area.x,y+side+gap,area.w,titleH),
                m_busy?L("Ищем команды…","Finding teams…"):
                m_filterMode?L("Подходящих лобби пока нет","No matching lobbies yet"):
                    L("Открытых лобби пока нет","No public lobbies yet"),CZMF_UI_ACTION,CzmStyle::Ink(),QM_CENTER);
            CzmStyle::Text(CZM_Rect(area.x,y+side+gap+titleH+gap/2,area.w,metaH),
                m_filterMode?L("Попробуй другой режим","Try a different mode"):
                    L("Здесь появятся команды для совместной игры","Open teams will appear here"),CZMF_UI_META,CzmStyle::Muted(),QM_CENTER);
        }
        for(int i=0;i<m_cardCount&&i<CZM_LOBBY_LIST;i++){
            const RoomCard &room=m_cards[i];const CzmRect r=m_cardsRect[i];
            CzmStyle::Surface(r,PackRGBA(22,31,43,255),m_pressed==SELECT+i?accent:0);
            const int inset=Q_max(4,gap/2),media=r.h-inset*2;
            CzmStyle::MapPreview(CZM_Rect(r.x+inset,r.y+inset,media,r.h-inset*2),room.map,room.address);
            const int tx=r.x+media+inset+gap;
            const int joinW=Q_max(64,(int)(H*.17f));
            const int joinX=r.x+r.w-joinW-gap;
            const int badgeW=Q_max(36,(int)(H*.085f));
            const int textW=Q_max(10,joinX-tx-gap*2-badgeW);
            CzmStyle::Text(CZM_Rect(tx,r.y+inset,textW,(r.h-inset*2)/2),room.title,CZMF_UI_ACTION);
            char count[24];snprintf(count,sizeof(count),"%d/%d",room.count,room.capacity);
            CzmStyle::Text(CZM_Rect(joinX-gap-badgeW,r.y,badgeW,r.h),count,CZMF_UI_LABEL,CzmStyle::Success(),QM_CENTER);
            const char *mode=!strncmp(room.map,"ze_",3)?"Zombie Escape":!strncmp(room.map,"zm_",3)?"Zombie Survivor":L("Зомби-режим","Zombie mode");
            char meta[160];snprintf(meta,sizeof(meta),"%s · %s",mode,room.map[0]?room.map:L("Карта уточняется","Checking map"));
            CzmStyle::Text(CZM_Rect(tx,r.y+r.h/2,textW,r.h/2-inset),meta,CZMF_UI_META,CzmStyle::Muted());
            CzmStyle::Button(CZM_Rect(joinX,r.y+(r.h-m_back.h*3/4)/2,joinW,m_back.h*3/4),
                room.count>=room.capacity?L("Заполнено","Full"):L("Войти","Join"),room.count<room.capacity,false,m_pressed==SELECT+i,accent);
        }
        if(m_offset>0)CzmStyle::Button(m_buttons[0],L("Назад","Previous"),true,false,m_pressed==PREV);
        if(m_next>=0)CzmStyle::Button(m_buttons[1],L("Дальше","Next"),true,false,m_pressed==NEXT);
    }else{
        char summary[160];ServerSummary(summary,sizeof(summary));
        const CzmRect sr=m_roomServerRect;
        CzmStyle::Surface(sr,PackRGBA(22,31,43,255));
        const int media=sr.h-gap;
        CzmStyle::MapPreview(CZM_Rect(sr.x+gap/2,sr.y+gap/2,media,sr.h-gap),m_pickedMap,m_pickedName);
        const int sx=sr.x+media+gap*2,sw=sr.w-(sx-sr.x)-gap;
        CzmStyle::Text(CZM_Rect(sx,sr.y,sw,sr.h/2),m_pickedName[0]?m_pickedName:m_serverAddress[0]?m_serverAddress:L("Выбранный игровой сервер","Selected game server"),CZMF_UI_LABEL);
        CzmStyle::Text(CZM_Rect(sx,sr.y+sr.h/2,sw,sr.h/2),summary,CZMF_UI_META,CzmStyle::Muted());
        char team[96];snprintf(team,sizeof(team),L("КОМАНДА  %d / %d","YOUR TEAM  %d / %d"),m_memberCount,m_capacity);
        CzmStyle::Text(m_teamTitleRect,team,CZMF_UI_LABEL);
        for(int i=0;i<m_capacity&&i<CZM_LOBBY_MEMBERS;i++){
            const CzmRect r=m_membersRect[i];
            const bool occupied=i<m_memberCount;
            const Member &member=m_members[i];
            const bool muted=occupied&&(m_hostMuted[i]||CZM_LobbyVoiceIsMuted(member.id)||
                (m_voiceAllMuted&&member.id!=m_owner)||!CZM_LobbyVoiceMicEnabled(member.id));
            const bool speaking=occupied&&!muted&&CZM_LobbyVoiceSpeaking(member.id);
            const bool host=occupied&&member.id==m_owner;
            CzmStyle::Surface(r,occupied?PackRGBA(24,34,47,255):PackRGBA(16,24,35,255),
                speaking?CzmStyle::Success():occupied&&member.id==CZM_OnlinePlayer()?PackRGBA(70,91,119,255):0);
            const int inset=Q_max(5,gap),av=Q_min(r.h-inset*2,(int)(H*.082f));
            const int ax=r.x+inset,ay=r.y+(r.h-av)/2;
            if(occupied){
                if(speaking)CZM_DrawImage(UI_DIR "dot.png",ax-2,ay-2,av+4,av+4,CzmStyle::Success());
                CZM_DrawImage(CZM_AvatarFor(member.avatar,member.id),ax,ay,av,av);
                const int tx=ax+av+gap,icon=Q_max(14,(int)(H*.027f));
                const int right=r.x+r.w-inset,tw=Q_max(10,right-tx-icon-gap/2);
                CzmStyle::Text(CZM_Rect(tx,r.y+r.h/2-label-2,tw,label+4),member.nick,CZMF_UI_LABEL);
                const char *state=member.ready?L("Готов","Ready"):L("Не готов","Not ready");
                CzmStyle::Text(CZM_Rect(tx,r.y+r.h/2+2,right-tx,label),state,CZMF_UI_META,member.ready?CzmStyle::Success():CzmStyle::Muted());
                if(member.id==CZM_OnlinePlayer())CzmStyle::Text(
                    CZM_Rect(tx,r.y+r.h-CZM_FontHeight(CZM_Font(CZMF_UI_META))-inset/2,tw,CZM_FontHeight(CZM_Font(CZMF_UI_META))),
                    L("Проверить микрофон","Check microphone"),CZMF_UI_META,CzmStyle::AccentBlue());
                if(host)CZM_DrawImage(UI_DIR "icon_crown.png",right-icon,r.y+inset/2,icon,icon,CzmStyle::AccentGold());
                CZM_DrawImage(muted?UI_DIR "icon_lobby_mic_off.png":UI_DIR "icon_lobby_mic.png",
                    right-icon,r.y+r.h-icon-inset/2,icon,icon,
                    speaking?CzmStyle::Success():muted?PackRGBA(153,122,137,255):CzmStyle::Muted());
            }else{
                CzmStyle::Icon(CZM_Rect(ax,ay,av,av),UI_DIR "icon_plus.png",CzmStyle::Muted());
                CzmStyle::Text(CZM_Rect(ax+av+gap,r.y,r.w-av-gap-inset*2,r.h),
                    m_owner==CZM_OnlinePlayer()?L("Пригласить","Invite friend"):L("Свободно","Open slot"),CZMF_UI_META,CzmStyle::Muted());
            }
        }
        CzmStyle::Surface(m_chatRect,PackRGBA(17,25,36,255));
        const int chatHead=m_micRect.h+gap;
        CzmStyle::Text(CZM_Rect(m_chatRect.x+gap,m_chatRect.y,
            Q_max(10,m_voiceAllRect.x-m_chatRect.x-gap*2),chatHead),L("ЧАТ КОМАНДЫ","TEAM CHAT"),CZMF_UI_LABEL);
        const bool blocked=VoiceBlocked(),mic=CZM_LobbyVoiceMicOn()&&!blocked;
        IconChip(m_micRect,mic?UI_DIR "icon_lobby_mic.png":UI_DIR "icon_lobby_mic_off.png",
            mic&&CZM_LobbyVoiceSpeaking(CZM_OnlinePlayer()),blocked);
        if(m_owner==CZM_OnlinePlayer())IconChip(m_voiceAllRect,UI_DIR "icon_sound.png",!m_voiceAllMuted,m_voiceAllMuted);
        const int dot=Q_max(3,m_micRect.h/8),voiceState=CZM_LobbyVoiceStatus();
        CzmStyle::Round(CZM_Rect(m_micRect.x+m_micRect.w-dot,m_micRect.y,dot,dot),
            voiceState==2?CzmStyle::Success():voiceState==1?CzmStyle::AccentGold():CzmStyle::Muted(),dot/2);
        const int msgTop=m_chatRect.y+chatHead+gap/2;
        const int msgBottom=m_textRect.y-gap;
        const int lineH=Q_max(CZM_FontHeight(CZM_Font(CZMF_SMALL))+gap/2,1);
        const int visible=Q_min(m_chatCount,Q_max(0,(msgBottom-msgTop)/lineH));
        if(!m_chatCount){
            CzmStyle::Text(CZM_Rect(m_chatRect.x+gap,msgTop,m_chatRect.w-gap*2,H*.05f),
                L("Обсуди план с командой","Make a plan with your team"),CZMF_SMALL,CzmStyle::Muted());
            CzmStyle::Text(CZM_Rect(m_chatRect.x+gap,msgTop+H*.05f,m_chatRect.w-gap*2,H*.04f),
                L("Чат и голос доступны до старта игры","Chat and voice stay here until the match starts"),CZMF_UI_META,CzmStyle::Muted());
        }
        for(int i=0;i<visible;i++){
            const ChatLine &msg=m_chat[m_chatCount-visible+i];
            char text[540];snprintf(text,sizeof(text),"%s: %s",msg.nick[0]?msg.nick:L("Игрок","Player"),msg.text);
            CzmStyle::Text(CZM_Rect(m_chatRect.x+gap,msgTop+i*lineH,m_chatRect.w-gap*2,lineH),
                text,CZMF_SMALL,msg.sender==CZM_OnlinePlayer()?PackRGBA(178,205,244,255):CzmStyle::Ink());
        }
        DrawField(m_textRect,m_text[0]?m_text:L("Сообщение команде…","Message your team…"));
        CzmStyle::Button(m_sendRect,"",!m_request&&m_text[0],false,m_pressed==SEND,CzmStyle::AccentBlue());
        CzmStyle::Icon(m_sendRect,UI_DIR "icon_send.png",m_text[0]?CzmStyle::AccentBlue():CzmStyle::Muted());
        CzmStyle::Button(m_buttons[0],m_ownReady?L("Готов ✓","Ready ✓"):L("Я готов","Ready up"),
            true,false,m_ownReady,m_ownReady?CzmStyle::Success():CzmStyle::AccentBlue());
        CzmStyle::Button(m_buttons[2],L("Сервер","Server"),m_owner==CZM_OnlinePlayer(),false,m_pressed==SERVER_NEXT);
        CzmStyle::Button(m_buttons[3],L("Друзья","Friends"),true,false,m_pressed==INVITE);
        CzmStyle::Button(m_buttons[4],L("Выйти","Leave"),true,false,m_pressed==LEAVE);
        CzmStyle::Button(m_buttons[1],L("В бой  ›","Start  ›"),CanStart()&&!m_request,true,m_pressed==LAUNCH,0,CZMF_UI_ACTION);
        const char *reason=m_owner!=CZM_OnlinePlayer()?L("Игру начинает хозяин лобби","The lobby host starts the match"):
            m_memberCount<2?L("Пригласи ещё одного игрока","Invite one more player"):
            !CanStart()?L("Ожидаем готовности игроков","Waiting for players to be ready"):
            L("Команда готова к старту","Your team is ready");
        CzmStyle::Text(CZM_Rect(m_teamTitleRect.x,m_buttons[0].y-label-gap/2,
            m_panel.w-pad*2,label),reason,CZMF_UI_META,CanStart()?CzmStyle::Success():CzmStyle::Muted(),QM_RIGHT);
    }
    if(m_selectedMemberId){
        UI_FillRect(0,0,W,H,PackRGBA(2,6,12,205));
        CzmStyle::Surface(m_modal,PackRGBA(18,26,38,255));
        const char *nick=L("Игрок","Player");
        bool muted=false;
        for(int i=0;i<m_memberCount;i++)if(m_members[i].id==m_selectedMemberId){nick=m_members[i].nick;muted=m_hostMuted[i];break;}
        CzmStyle::Text(CZM_Rect(m_modal.x+pad,m_modal.y+pad,m_modal.w-pad*2,m_back.h),nick,CZMF_UI_TITLE);
        const char *labels[]={L("Открыть профиль","Open profile"),
            CZM_LobbyVoiceIsMuted(m_selectedMemberId)?L("Включить звук у себя","Unmute for me"):L("Выключить звук у себя","Mute for me"),
            muted?L("Разрешить микрофон","Allow microphone"):L("Выключить микрофон игроку","Mute player for everyone"),
            m_memberConfirm==1?L("Подтвердить исключение","Confirm kick"):L("Исключить из лобби","Kick from lobby"),
            m_memberConfirm==2?L("Подтвердить передачу","Confirm transfer"):L("Передать права хозяина","Transfer host"),L("Закрыть","Close")};
        for(int i=0;i<6;i++)CzmStyle::Button(m_modalButtons[i],labels[i],
            !(i>=2&&i<=4)||m_owner==CZM_OnlinePlayer(),i==3&&m_memberConfirm==1,false,i==3?CzmStyle::AccentRed():0);
    }
    if(m_notice[0]&&EngFuncs::DoubleTime()<m_noticeUntil){
        const int height=Q_max(22,(int)(H*.048f));
        const int width=Q_min(m_panel.w-pad*2,CZM_TextWidth(CZM_Font(CZMF_UI_META),m_notice)+pad*2);
        const CzmRect toast=CZM_Rect((W-width)/2,Q_max(2,m_panel.y-height-gap/2),width,height);
        CzmStyle::Surface(toast,PackRGBA(25,36,51,255),CzmStyle::AccentBlue());
        CzmStyle::Text(CZM_Rect(toast.x+pad/2,toast.y,toast.w-pad,toast.h),m_notice,CZMF_UI_META,CzmStyle::Ink(),QM_CENTER);
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
