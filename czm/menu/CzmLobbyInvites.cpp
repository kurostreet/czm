/*
 * CZM lobby invitations are transient game prompts, not catalog entries.
 * All authorization/TTL/allowlist checks live on the server.
 * This view only appears while the app is in foreground menu mode.
 */
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Framework.h"
#include "Utils.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "CzmJson.h"
#include "CzmDesign.h"

#define INV_UI "gfx/czm/ui/"

namespace {
const char *T(const char *ru,const char *en){return CZM_IsRussian()?ru:en;}
static void Label(const CzmRect &r,const char *s,int font,unsigned color){
    HFont f=CZM_Font(font);
    CZM_DrawText(f,r.x,r.y+(r.h-CZM_FontHeight(f))/2,r.w,s,color);
}
static void InviteButton(const CzmRect &r,const char *text,bool primary){
    CzmStyle::Button(r,text,true,primary);
}
}

void UI_CzmLobbyInvite_Menu(void);
void CZM_LobbyOpenAccepted(void);
bool CZM_LobbyHasRoom(void);

class CCzmLobbyInviteNotice: public CMenuFramework {
public:
    CCzmLobbyInviteNotice();
    void Show() override;
    void Hide() override;
    void Draw() override;
    bool KeyDown(int key) override;
    bool KeyUp(int key) override;
    bool IsRoot() const override {return false;}
    void Frame();
private:
    enum HitId {HIT_NONE,HIT_ACCEPT,HIT_DECLINE,HIT_CLOSE};
    void Layout();
    HitId Hit() const;
    void Act(HitId hit);
    void Stop(bool dismissed);
    void Answer(bool accept);
    bool WasDismissed(const char *id) const;
    int m_request,m_kind,m_identity,m_sender,m_count,m_capacity,m_dismissedCount;
    time_t m_expires;
    bool m_open,m_pending,m_answerAccept;
    HitId m_pressed;
    double m_pollAt;
    char m_id[64],m_dismissed[8][64],m_senderName[100],m_senderAvatar[32],
         m_roomTitle[128],m_server[64],m_map[64];
    char m_error[128];
    CzmRect m_panel,m_close,m_accept,m_decline,m_avatar,m_summary,m_title;
    int W,H;
};
CCzmLobbyInviteNotice::CCzmLobbyInviteNotice():CMenuFramework("CzmLobbyInvite"){
    m_request=m_kind=m_identity=0;m_sender=m_count=m_capacity=m_dismissedCount=0;
    m_expires=0;
    m_open=m_pending=m_answerAccept=false;m_pressed=HIT_NONE;m_pollAt=0;
    m_id[0]=m_senderName[0]=m_senderAvatar[0]=m_roomTitle[0]=m_server[0]=m_map[0]=m_error[0]=0;
    memset(m_dismissed,0,sizeof(m_dismissed));
    W=H=0;
}
void CCzmLobbyInviteNotice::Show(){
    m_open=true;m_pressed=HIT_NONE;
    CMenuFramework::Show();
}
void CCzmLobbyInviteNotice::Hide(){
    m_open=false;m_pressed=HIT_NONE;
    CMenuFramework::Hide();
}
void CCzmLobbyInviteNotice::Layout(){
    W=ScreenWidth;H=ScreenHeight;
    const int pw=Q_min((int)(W*.54f),(int)(H*1.24f));
    const int ph=(int)(H*.36f);
    const int pad=Q_max(10,(int)(H*.027f));
    const int gap=Q_max(6,(int)(H*.014f));
    m_panel=CZM_Rect((W-pw)/2,(H-ph)/2,pw,ph);
    m_close=CZM_Rect(m_panel.x+pw-pad-H*.040f,m_panel.y+pad/2,H*.040f,H*.040f);
    m_title=CZM_Rect(m_panel.x+pad,m_panel.y+pad,pw-2*pad-H*.050f,H*.050f);
    const int detailsTop=m_title.y+m_title.h+gap;
    m_avatar=CZM_Rect(m_panel.x+pad,detailsTop,(int)(H*.085f),(int)(H*.085f));
    m_summary=CZM_Rect(m_avatar.x+m_avatar.w+gap,detailsTop,
                       pw-3*pad-m_avatar.w-gap,(int)(H*.126f));
    const int bottom=m_panel.y+ph-pad-H*.058f;
    m_decline=CZM_Rect(m_panel.x+pad,bottom,(pw-2*pad-gap)/2,(int)(H*.058f));
    m_accept=CZM_Rect(m_decline.x+m_decline.w+gap,bottom,
                       m_decline.w,(int)(H*.058f));
}
CCzmLobbyInviteNotice::HitId CCzmLobbyInviteNotice::Hit() const{
    if(m_close.HasCursor())return HIT_CLOSE;
    if(m_accept.HasCursor())return HIT_ACCEPT;
    if(m_decline.HasCursor())return HIT_DECLINE;
    return HIT_NONE;
}
bool CCzmLobbyInviteNotice::WasDismissed(const char *id) const{
    if(!id||!id[0])return true;
    for(int i=0;i<m_dismissedCount;i++)
        if(!strcmp(m_dismissed[i],id))return true;
    return false;
}
void CCzmLobbyInviteNotice::Stop(bool dismissed){
    if(dismissed&&m_id[0]&&!WasDismissed(m_id)){
        const int max=(int)(sizeof(m_dismissed)/sizeof(m_dismissed[0]));
        if(m_dismissedCount==max){
            memmove(m_dismissed[0],m_dismissed[1],
                    (max-1)*sizeof(m_dismissed[0]));
            m_dismissedCount--;
        }
        Q_strncpy(m_dismissed[m_dismissedCount++],m_id,sizeof(m_dismissed[0]));
    }
    m_id[0]=0;m_expires=0;m_pending=false;
    if(m_open)Hide();
}
void CCzmLobbyInviteNotice::Answer(bool accept){
    if(!m_id[0]||m_request)return;
    char path[192];
    snprintf(path,sizeof(path),"/api/v1/lobbies/invitations/%s/answer",m_id);
    m_request=CZM_NetRequest("POST",CZM_OnlineUrl(path),CZM_OnlineKey(),
                            accept?"{\"accept\":true}":"{\"accept\":false}");
    if(!m_request){
        Q_strncpy(m_error,T("Нет соединения","Connection unavailable"),sizeof(m_error));
        return;
    }
    m_kind=2;m_answerAccept=accept;
}
void CCzmLobbyInviteNotice::Act(HitId hit){
    if(hit==HIT_CLOSE){Stop(true);return;}
    if(hit==HIT_DECLINE){Answer(false);return;}
    if(hit==HIT_ACCEPT){
        if(CZM_LobbyHasRoom()){
            Q_strncpy(m_error,T("Сначала выйдите из текущей комнаты",
                                "Leave your current lobby first"),sizeof(m_error));
            return;
        }
        Answer(true);
    }
}
bool CCzmLobbyInviteNotice::KeyDown(int key){
    Layout();
    if(UI::Key::IsEscape(key)){Stop(true);return true;}
    if(UI::Key::IsLeftMouse(key)){m_pressed=Hit();return true;}
    return CMenuFramework::KeyDown(key);
}
bool CCzmLobbyInviteNotice::KeyUp(int key){
    if(UI::Key::IsLeftMouse(key)){
        const HitId hit=Hit();
        if(hit!=HIT_NONE&&hit==m_pressed)Act(hit);
        m_pressed=HIT_NONE;return true;
    }
    return CMenuFramework::KeyUp(key);
}
void CCzmLobbyInviteNotice::Draw(){
    Layout();
    UI_FillRect(0,0,W,H,PackRGBA(0,0,0,148));
    CzmStyle::Surface(m_panel,PackRGBA(17,25,36,255),CzmStyle::AccentBlue());
    const int pad=Q_max(10,(int)(H*.027f));
    CZM_DrawImage(INV_UI "icon_users.png",m_title.x,m_title.y,
                  m_title.h,m_title.h);
    Label(CZM_Rect(m_title.x+m_title.h+pad/2,m_title.y,
                   m_title.w-m_title.h-pad/2,m_title.h),
          T("Приглашение в лобби","Lobby invitation"),
          CZMF_UI_TITLE,CZM_White());
    CZM_DrawImage(INV_UI "icon_close.png",m_close.x,m_close.y,
                  m_close.w,m_close.h);
    CZM_DrawImage(CZM_AvatarFor(m_senderAvatar,m_sender),m_avatar.x,m_avatar.y,
                  m_avatar.w,m_avatar.h);
    char inviter[145];
    snprintf(inviter,sizeof(inviter),T("%s приглашает тебя","%s invited you"),
             m_senderName[0]?m_senderName:T("Друг","Friend"));
    Label(CZM_Rect(m_summary.x,m_summary.y,m_summary.w,m_summary.h/3),
          inviter,CZMF_TILE_STATUS,CZM_White());
    Label(CZM_Rect(m_summary.x,m_summary.y+m_summary.h/3,m_summary.w,m_summary.h/3),
          m_roomTitle,CZMF_LANG,PackRGBA(232,237,244,255));
    char server[160];
    const char *mode=!strncmp(m_map,"ze_",3)?"Zombie Escape":
                     !strncmp(m_map,"zm_",3)?"Zombie Survivor":
                     T("Зомби-режим","Zombie Mode");
    snprintf(server,sizeof(server),"%s  ·  %d/%d",
             mode,m_count,m_capacity);
    Label(CZM_Rect(m_summary.x,m_summary.y+2*m_summary.h/3,
                   m_summary.w,m_summary.h/3),server,CZMF_SMALL,CZM_Grey());
    InviteButton(m_decline,T("Отклонить","Decline"),false);
    InviteButton(m_accept,T("Принять","Accept"),true);
    if(m_error[0])Label(CZM_Rect(m_panel.x+pad,m_decline.y-H*.052f,
                m_panel.w-2*pad,H*.048f),m_error,CZMF_SMALL,
                PackRGBA(235,125,139,255));
}
void CCzmLobbyInviteNotice::Frame(){
    if(m_identity!=CZM_OnlineIdentity()){
        m_identity=CZM_OnlineIdentity();m_request=0;m_kind=0;m_pollAt=0;
        m_id[0]=m_error[0]=0;m_expires=0;m_dismissedCount=0;
        memset(m_dismissed,0,sizeof(m_dismissed));
        if(m_open)Hide();
    }
    if(m_open&&m_expires&&time(NULL)>=m_expires)Stop(false);
    // Foreground only. Real Android background delivery is a separate task.
    if(!CZM_OnlineAccount()||!CZM_OnlineReady()||CL_IsActive()){
        if(m_open)Hide();
        return;
    }
    if(m_request){
        int status=0;CUtlString result;
        if(!CZM_NetPoll(m_request,&status,result))return;
        const int kind=m_kind;
        m_request=0;m_kind=0;
        CzmJson j;
        if(status!=200||!j.Parse(result.Get())){
            if(kind==2&&m_open)
                Q_strncpy(m_error,T("Не удалось ответить на приглашение",
                                    "Invitation could not be processed"),sizeof(m_error));
            m_pollAt=EngFuncs::DoubleTime()+8;
            return;
        }
        if(kind==2){
            const bool accepted=m_answerAccept;
            Stop(true);
            m_pollAt=EngFuncs::DoubleTime()+5;
            if(accepted)CZM_LobbyOpenAccepted();
            return;
        }
        const int array=j.Get(0,"invites");
        bool selected=false;
        if(!CZM_LobbyHasRoom()){
            for(int i=0;i<j.Count(array);i++){
                const int item=j.At(array,i);
                const char *id=j.String(j.Get(item,"id"));
                if(WasDismissed(id))continue;
                const time_t expires=(time_t)j.Int(j.Get(item,"expires"));
                if(expires<=time(NULL))continue;
                Q_strncpy(m_id,id,sizeof(m_id));
                Q_strncpy(m_senderName,j.String(j.Get(item,"sender_name")),
                          sizeof(m_senderName));
                Q_strncpy(m_senderAvatar,j.String(j.Get(item,"sender_avatar")),
                          sizeof(m_senderAvatar));
                Q_strncpy(m_roomTitle,j.String(j.Get(item,"title")),
                          sizeof(m_roomTitle));
                Q_strncpy(m_server,j.String(j.Get(item,"server")),sizeof(m_server));
                Q_strncpy(m_map,j.String(j.Get(item,"map")),sizeof(m_map));
                m_sender=j.Int(j.Get(item,"sender"));
                m_count=j.Int(j.Get(item,"count"),1);
                m_capacity=j.Int(j.Get(item,"capacity"),6);
                m_expires=expires;
                if(!m_senderName[0])snprintf(m_senderName,sizeof(m_senderName),
                                             "Игрок #%d",m_sender);
                m_pending=true;m_error[0]=0;selected=true;
                if(!m_open)Show();
                break;
            }
        }
        if(!selected&&m_open)Stop(false);
        m_pollAt=EngFuncs::DoubleTime()+10;
    }
    // Refresh active cards too: deleted or expired rooms disappear promptly.
    if(m_request||CZM_LobbyHasRoom()||EngFuncs::DoubleTime()<m_pollAt)return;
    m_request=CZM_NetRequest("GET",CZM_OnlineUrl("/api/v1/lobbies/invitations"),
                             CZM_OnlineKey(),"");
    if(m_request)m_kind=1;
    m_pollAt=EngFuncs::DoubleTime()+10;
}
ADD_MENU3(menu_czmlobbyinvite,CCzmLobbyInviteNotice,UI_CzmLobbyInvite_Menu);
void UI_CzmLobbyInvite_Menu(void){menu_czmlobbyinvite->Show();}
void CZM_LobbyInviteFrame(void){menu_czmlobbyinvite->Frame();}
