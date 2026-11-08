/* Counter Zombie Mobile: native match chat and RU/EN touch keyboard. GPL-3.0-or-later. */
#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "BaseClientWindow.h"
#include "Scissor.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "CzmDesign.h"
#include "CzmMatchChatModel.h"

namespace MC=CzmMatchChat;
static CzmRect MatchRect(const MC::Rect &r){return CZM_Rect(r.x,r.y,r.w,r.h);}
static const char *MatchT(const char *ru,const char *en){return CZM_IsRussian()?ru:en;}

class CCzmMatchChat : public CMenuBaseClientWindow {
public:
    CCzmMatchChat():CMenuBaseClientWindow("CzmMatchChat"),m_shown(false),m_pressed(0),m_downY(0),m_downScroll(0),m_drag(false),m_moved(false),m_enterDown(false),m_repeat(0),m_shiftAt(-1){}
    void Frame();
    void AfterClientMenuFrame(bool menusActive);
    void Open(bool team);
    void Hide() override;
    void Draw() override;
    bool KeyDown(int key) override;
    bool KeyUp(int key) override;
    bool MouseMove(int x,int y) override;
    void Char(int key) override;
private:
    enum { HitOutside=1,HitHistory,HitChannel,HitField,HitSend,HitClose,HitKey=16 };
    void Layout(){
        if(m_feedback.key.action!=MC::None&&(m_feedback.width!=ScreenWidth||m_feedback.height!=ScreenHeight))m_feedback.Clear();
        m_layout.Build(ScreenWidth,ScreenHeight,m_model);
    }
    int Hit()const;
    void Activate(int hit);
    void KeyAction(const MC::Key &key);
    void Send();
    void Back();
    void ClearPress(){m_pressed=0;m_drag=m_moved=false;m_repeat=0;m_enterDown=false;m_model.input.Reset();m_feedback.Clear();}
    void BeginFeedback(const MC::Key &key);
    void DrawFeedback();
    void PollHistory();
    void DrawHistory();
    void DrawComposer();
    MC::Model m_model;
    MC::Layout m_layout;
    MC::PressFeedback m_feedback;
    bool m_shown;
    int m_pressed,m_downY,m_downScroll;
    bool m_drag,m_moved,m_enterDown;
    double m_repeat,m_shiftAt;
};

void CCzmMatchChat::Open(bool team){
    if(!CL_IsActive()||EngFuncs::GetCvarFloat("czm_match_chat")<0.5f||EngFuncs::GetCvarFloat("czm_match_chat_active")<0.5f)return;
    ClearPress();m_model.Open(team);Layout();CZM_KeepClientMenu(this);
    const float ru=EngFuncs::GetCvarFloat("czm_match_chat_ru");m_model.russian=ru<0?CZM_IsRussian():ru>=.5f;
    // This surface draws its own keyboard; never ask Android to pan the viewport.
    UI_EnableTextInput(false);
    EngFuncs::CvarSetValue("czm_match_chat_active",1);
    EngFuncs::KEY_SetDest(KEY_MENU);
    EngFuncs::ClientCmd(true,"touch_setclientonly 1");
    if(!m_shown||m_pStack->Current()!=this)CMenuBaseClientWindow::Show();
    DisableTransition();m_shown=true;
}

void CCzmMatchChat::Hide(){
    m_model.state=MC::Closed;ClearPress();
    if(!m_shown)return;
    m_shown=false;
    EngFuncs::CvarSetValue("czm_match_chat_active",0);
    char command[64];snprintf(command,sizeof(command),"czm_match_chat_close %u\n",m_model.request);EngFuncs::ClientCmd(true,command);
    CZM_CloseClientMenuSoon(this);
}

void CCzmMatchChat::PollHistory(){
    unsigned head=(unsigned)strtoul(EngFuncs::GetCvarString("czm_mc_head"),NULL,10);
    if(!head){if(m_model.head||m_model.count)m_model.ResetHistory();return;}
    if(head==m_model.head)return;
    if(head<m_model.head)m_model.ResetHistory();
    MC::Message available[MC::HistorySize];int count=0;
    for(int i=0;i<MC::HistorySize;i++){
        char name[32];snprintf(name,sizeof(name),"czm_mc_line%d",i);
        MC::Message message;
        if(!MC::ParseMessage(EngFuncs::GetCvarString(name),message)||message.seq<=m_model.head||message.seq>head)continue;
        int at=count;while(at&&available[at-1].seq>message.seq){available[at]=available[at-1];at--;}
        available[at]=message;count++;
    }
    for(int i=0;i<count;i++)m_model.Push(available[i]);
    m_model.head=head;
}

void CCzmMatchChat::Frame(){
    int epoch=atoi(EngFuncs::GetCvarString("czm_match_chat_epoch"));
    int historyEpoch=atoi(EngFuncs::GetCvarString("czm_mc_epoch"));
    const char *server=EngFuncs::GetCvarString("czm_connect_adr");
    if(m_model.Context(epoch,historyEpoch,server?server:"")){
        ClearPress();if(m_shown)Hide();
    }
    unsigned serial=0;int team=0;
    const char *request=EngFuncs::GetCvarString("czm_match_chat_request");
    if(request)sscanf(request,"%u %d",&serial,&team);
    if(!CL_IsActive()){
        if(m_shown)Hide();
        m_model.state=MC::Closed;m_model.ResetDraft();m_model.ResetHistory();m_model.request=serial;return;
    }
    PollHistory();
    if(m_shown&&(EngFuncs::GetCvarFloat("czm_match_chat")<0.5f||m_pStack->Current()!=this||EngFuncs::GetCvarFloat("czm_match_chat_active")<0.5f))Hide();
    if(serial&&serial!=m_model.request){
        m_model.request=serial;
        if(EngFuncs::GetCvarFloat("czm_match_chat_active")>=.5f)Open(team!=0);
    }
    if(!m_shown)return;
    Layout();
    if(m_repeat&&m_pressed>=HitKey&&m_pressed<HitKey+m_layout.count){
        const MC::Key &key=m_layout.keys[m_pressed-HitKey];
        double now=EngFuncs::DoubleTime();
        if(key.action==MC::Backspace&&Hit()==m_pressed&&now>=m_repeat){MC::Delete(m_model.draft);m_repeat=now+.055;}
    }
}

void CCzmMatchChat::AfterClientMenuFrame(bool menusActive){
    // UI_CloseClientMenu restores KEY_GAME. Start an intentional system-IME
    // handoff only after that stack cleanup, so it cannot overwrite KEY_MESSAGE.
    if(menusActive||m_shown||!CL_IsActive())return;
    int pending=atoi(EngFuncs::GetCvarString("czm_match_chat_ime_pending"));
    if(pending==1||pending==2){
        char command[48];snprintf(command,sizeof(command),"czm_match_chat_ime %d\n",pending-1);EngFuncs::ClientCmd(true,command);
    }
}

int CCzmMatchChat::Hit()const{
    int x=uiStatic.cursorX,y=uiStatic.cursorY;
    if(m_layout.close.Contains(x,y))return HitClose;
    if(m_layout.send.Contains(x,y))return HitSend;
    if(m_layout.channel.Contains(x,y))return HitChannel;
    if(m_layout.field.Contains(x,y))return HitField;
    if(m_layout.history.Contains(x,y))return HitHistory;
    if(m_model.state==MC::Typing)for(int i=0;i<m_layout.count;i++)if(m_layout.keys[i].rect.Contains(x,y))return HitKey+i;
    // Empty keyboard gaps are part of the keyboard, not a tap on the game.
    if(m_layout.keyboard.Contains(x,y)||m_layout.composer.Contains(x,y))return 0;
    return HitOutside;
}

void CCzmMatchChat::Back(){
    ClearPress();m_model.Back();if(m_model.state==MC::Closed)Hide();else Layout();
}

void CCzmMatchChat::Send(){
    if(!m_shown||m_model.state==MC::Closed)return;
    char text[MC::MaxBytes+1];if(!m_model.Take(text))return;
    char hex[MC::MaxBytes*2+1],command[MC::MaxBytes*2+80];MC::Encode(text,hex);
    snprintf(command,sizeof(command),"czm_match_chat_send %d %d %s\n",m_model.team?1:0,m_model.epoch,hex);
    ClearPress();EngFuncs::ClientCmd(true,command);
    if(EngFuncs::GetCvarFloat("czm_match_chat_keep_open")<0.5f)Hide();
}

void CCzmMatchChat::KeyAction(const MC::Key &key){
    switch(key.action){
    case MC::Letter:{char text[16];snprintf(text,sizeof(text),"%s",key.text);if(m_model.shift||m_model.caps)MC::Upper(text);MC::Append(m_model.draft,text);m_model.shift=false;break;}
    case MC::Space:MC::Append(m_model.draft," ");break;
    case MC::Backspace:MC::Delete(m_model.draft);break;
    case MC::Shift:{double now=EngFuncs::DoubleTime();if(m_model.caps){m_model.caps=m_model.shift=false;}else if(m_model.shift&&now-m_shiftAt<.4){m_model.caps=true;m_model.shift=false;}else m_model.shift=!m_model.shift;m_shiftAt=now;break;}
    case MC::Language:m_model.russian=!m_model.russian;m_model.numbers=false;EngFuncs::CvarSetValue("czm_match_chat_ru",m_model.russian?1:0);break;
    case MC::Numbers:m_model.numbers=!m_model.numbers;break;
    case MC::HideKeyboard:Back();break;
    case MC::Submit:Send();break;
    default:break;
    }
}

void CCzmMatchChat::Activate(int hit){
    if(!m_shown)return;
    if(hit==HitClose){Hide();return;}
    if(hit==HitOutside){Back();return;}
    if(hit==HitField){m_model.state=MC::Typing;m_model.input.Reset();return;}
    if(hit==HitChannel){m_model.team=!m_model.team;return;}
    if(hit==HitSend){Send();return;}
    if(hit>=HitKey&&hit<HitKey+m_layout.count)KeyAction(m_layout.keys[hit-HitKey]);
}

void CCzmMatchChat::BeginFeedback(const MC::Key &key){
    m_feedback.Begin(key,ScreenWidth,ScreenHeight);
    if(key.action==MC::Letter&&(m_model.shift||m_model.caps))MC::Upper(m_feedback.key.text);
    CZM_PlayClick();
    if(EngFuncs::GetCvarFloat("czm_match_chat_haptic")>=.5f&&EngFuncs::GetCvarFloat("vibration_enable")>=.5f)CZM_MatchKeyHaptic();
}

bool CCzmMatchChat::KeyDown(int key){
    if(!m_shown)return true;
    Layout();
    if(UI::Key::IsEscape(key)){Back();return true;}
    if(UI::Key::IsEnter(key)){if(!m_enterDown){m_enterDown=true;Send();}return true;}
    if(UI::Key::IsBackspace(key)){if(m_model.state==MC::Typing){m_model.input.Reset();MC::Delete(m_model.draft);}return true;}
    if(key==K_MWHEELUP||key==K_MWHEELDOWN){m_model.scroll=MC::Max(0,m_model.scroll+(key==K_MWHEELUP?3:-3));return true;}
    if(UI::Key::IsLeftMouse(key)){
        int hit=Hit();
        if(m_feedback.held&&m_pressed==hit)return true;
        m_feedback.Clear();m_pressed=hit;m_drag=m_pressed==HitHistory;m_moved=false;m_downY=uiStatic.cursorY;m_downScroll=m_model.scroll;
        if(m_pressed>=HitKey)BeginFeedback(m_layout.keys[m_pressed-HitKey]);
        if(m_pressed>=HitKey&&m_layout.keys[m_pressed-HitKey].action==MC::Backspace){m_model.input.Reset();MC::Delete(m_model.draft);m_repeat=EngFuncs::DoubleTime()+.42;}
    }
    // Every key belongs to the overlay until it has closed, including releases.
    return true;
}

bool CCzmMatchChat::KeyUp(int key){
    if(UI::Key::IsEnter(key)){m_enterDown=false;return true;}
    if(UI::Key::IsLeftMouse(key)){
        Layout();int pressed=m_pressed,hit=Hit();bool wasDelete=pressed>=HitKey&&pressed<HitKey+m_layout.count&&m_layout.keys[pressed-HitKey].action==MC::Backspace;
        bool activate=m_shown&&!m_moved&&pressed&&pressed==hit&&!wasDelete;
        if(m_shown&&!m_moved&&pressed==hit)m_feedback.Release(EngFuncs::DoubleTime());else m_feedback.Clear();
        m_pressed=0;m_repeat=0;m_drag=false;
        if(activate)Activate(hit);
    }
    return true;
}

bool CCzmMatchChat::MouseMove(int x,int y){
    CMenuBaseClientWindow::MouseMove(x,y);
    if(m_drag){int dy=uiStatic.cursorY-m_downY;if(abs(dy)>MC::Max(4,ScreenHeight/80))m_moved=true;if(m_moved)m_model.scroll=MC::Max(0,m_downScroll+dy/MC::Max(1,CZM_FontHeight(CZM_Font(CZMF_CHAT_TEXT))));}
    if(m_repeat&&Hit()!=m_pressed)m_repeat=0;
    if(m_feedback.held&&!m_feedback.key.rect.Contains(uiStatic.cursorX,uiStatic.cursorY))m_feedback.Clear();
    return true;
}

void CCzmMatchChat::Char(int key){if(m_shown&&m_model.state==MC::Typing&&key>=32&&key!=127)m_model.input.Add(m_model.draft,key);}

void CCzmMatchChat::DrawHistory(){
    CzmStyle::Surface(MatchRect(m_layout.history),PackRGBA(20,26,36,240));
    const HFont font=CZM_Font(CZMF_CHAT_TEXT);const int lineH=MC::Max(1,CZM_FontHeight(font)+ScreenHeight/300);
    // Keep full message text and colour spans. Wrapping is computed in glyphs so
    // scrolling and clipping never cut a UTF-8 character or a colour escape.
    struct Glyph {char text[5];unsigned color;short line,x;};
    static Glyph glyphs[MC::HistorySize*(MC::MessageBytes+1)];int count=0,line=0,x=0;
    for(int msg=0;msg<m_model.count;msg++){
        const MC::Message &message=m_model.messages[msg];unsigned color=PackRGBA(255,178,0,255);bool legacyName=false;
        const char *begin=message.text;
        for(const char *p=begin;*p;){
            unsigned char c=(unsigned char)*p;
            if(c==1||c==2||c==3||c==4){legacyName=c==2;color=c==1?PackRGBA(255,178,0,255):c==4?PackRGBA(0,255,0,255):PackRGBA((message.rgb>>16)&255,(message.rgb>>8)&255,message.rgb&255,255);p++;continue;}
            if(c==7){unsigned rgb=0;int n=0;for(;n<6&&p[n+1];n++){int h=MC::HexValue(p[n+1]);if(h<0)break;rgb=rgb*16+h;}p+=n==6?7:1;if(n==6){legacyName=false;color=PackRGBA((rgb>>16)&255,(rgb>>8)&255,rgb&255,255);}continue;}
            if(c=='\n'){if(x){line++;x=0;}p++;continue;}
            if(c<32||c==127){p++;continue;}
            if(legacyName&&p-begin>=message.nameLength){legacyName=false;color=PackRGBA(255,178,0,255);}
            int bytes=MC::Utf8Length(p);if(!bytes){p++;continue;}
            char text[5]={};memcpy(text,p,bytes);p+=bytes;
            int width=CZM_TextWidth(font,text);
            if(x&&x+width>m_layout.clip.w){line++;x=0;}
            if(count<(int)(sizeof(glyphs)/sizeof(glyphs[0]))){Glyph &g=glyphs[count++];memcpy(g.text,text,5);g.color=color;g.line=(short)line;g.x=(short)x;}
            x+=width;
        }
        if(x){line++;x=0;}
    }
    const int visible=MC::Max(1,m_layout.clip.h/lineH),maxScroll=MC::Max(0,line-visible);
    m_model.scroll=MC::Min(m_model.scroll,maxScroll);
    int first=MC::Max(0,line-visible-m_model.scroll),last=first+visible;
    UI::Scissor::PushScissor(m_layout.clip.x,m_layout.clip.y,m_layout.clip.w,m_layout.clip.h);
    if(!count)CzmStyle::Text(MatchRect(m_layout.clip),MatchT("Сообщения сервера","Server messages"),CZMF_SMALL,CzmStyle::Muted());
    for(int i=0;i<count;i++){
        const Glyph &g=glyphs[i];if(g.line<first||g.line>=last)continue;
        CZM_DrawText(font,m_layout.clip.x+g.x,m_layout.clip.y+(g.line-first)*lineH,MC::Max(1,m_layout.clip.w-g.x),g.text,g.color);
    }
    UI::Scissor::PopScissor();
    if(maxScroll){int thumb=MC::Max(8,m_layout.clip.h*visible/MC::Max(visible,line));UI_FillRect(m_layout.history.x+m_layout.history.w-3,m_layout.clip.y+(m_layout.clip.h-thumb)*(maxScroll-m_model.scroll)/maxScroll,2,thumb,CzmStyle::Muted());}
}

void CCzmMatchChat::DrawComposer(){
    using namespace CzmStyle;
    Button(MatchRect(m_layout.channel),m_model.team?MatchT("Команде","Team"):MatchT("Всем","All"),true,false,m_pressed==HitChannel,CzmStyle::AccentBlue(),CZMF_UI_LABEL);
    Surface(MatchRect(m_layout.field),PackRGBA(18,24,33,252),m_model.state==MC::Typing?AccentRed():Border());
    int pad=m_layout.field.h/4;MC::Rect textRect={m_layout.field.x+pad,m_layout.field.y,m_layout.field.w-pad*2,m_layout.field.h};
    const HFont font=CZM_Font(CZMF_CHAT_TEXT);const char *text=m_model.draft;
    while(*text&&CZM_TextWidth(font,text)>textRect.w-pad){int n=MC::Utf8Length(text);text+=n?n:1;}
    Text(MatchRect(textRect),*text?text:MatchT("Написать сообщение…","Write a message…"),CZMF_CHAT_TEXT,*text?Ink():Muted());
    if(m_model.state==MC::Typing&&((int)(EngFuncs::DoubleTime()*2)&1)==0){int caret=textRect.x+MC::Min(CZM_TextWidth(font,text),MC::Max(0,textRect.w-pad));UI_FillRect(caret,textRect.y+textRect.h/4,MC::Max(1,ScreenHeight/450),textRect.h/2,Ink());}
    Button(MatchRect(m_layout.send),"",m_model.draft[0]!=0,true,m_pressed==HitSend);
    Icon(MatchRect(m_layout.send),"gfx/czm/ui/icon_send.png",m_model.draft[0]?Ink():Muted());
    Button(MatchRect(m_layout.close),"",true,false,m_pressed==HitClose);
    Icon(MatchRect(m_layout.close),"gfx/czm/ui/icon_close.png");
}

void CCzmMatchChat::DrawFeedback(){
    const float amount=m_feedback.Amount(EngFuncs::DoubleTime());if(amount<=0)return;
    const MC::Key &key=m_feedback.key;
    const CzmRect r=MatchRect(MC::FeedbackRect(key.rect,m_layout.keyboard,m_layout.gap,amount));
    const bool submit=key.action==MC::Submit;
    unsigned fill=submit?PackRGBA(190+(int)(21*amount),43+(int)(15*amount),60+(int)(17*amount),255):PackRGBA(28+(int)(13*amount),36+(int)(15*amount),48+(int)(19*amount),255);
    unsigned border=submit?CzmStyle::AccentRed():PackRGBA(51+(int)(178*amount),62+(int)(1*amount),78-(int)(1*amount),255);
    CzmStyle::Surface(r,fill,border);
    CzmStyle::Text(CZM_Rect(r.x+r.h/4,r.y,r.w-r.h/2,r.h),key.text,key.action==MC::Letter?CZMF_UI_ACTION:CZMF_UI_LABEL,CzmStyle::Ink(),QM_CENTER);
}

void CCzmMatchChat::Draw(){
    if(!m_shown||m_model.state==MC::Closed)return;
    Layout();
    DrawHistory();DrawComposer();
    if(m_model.state!=MC::Typing)return;
    CzmStyle::Surface(MatchRect(m_layout.keyboard),PackRGBA(16,22,31,252));
    for(int i=0;i<m_layout.count;i++){
        const MC::Key &key=m_layout.keys[i];char text[16];snprintf(text,sizeof(text),"%s",key.text);
        if(key.action==MC::Letter&&(m_model.shift||m_model.caps))MC::Upper(text);
        const bool on=key.action==MC::Shift&&(m_model.shift||m_model.caps);
        CzmStyle::Button(MatchRect(key.rect),text,true,key.action==MC::Submit,false,on?CzmStyle::AccentRed():0,key.action==MC::Letter?CZMF_UI_ACTION:CZMF_UI_LABEL);
    }
    DrawFeedback(); // last: the small pop stays above the fixed neighbouring keys
}

ADD_MENU3(menu_czmmatchchat,CCzmMatchChat,UI_CzmMatchChat_Menu);
void UI_CzmMatchChat_Menu(){if(menu_czmmatchchat)menu_czmmatchchat->Open(false);}
void CZM_MatchChatFrame(){if(menu_czmmatchchat)menu_czmmatchchat->Frame();}
void CZM_MatchChatAfterClientMenuFrame(bool menusActive){if(menu_czmmatchchat)menu_czmmatchchat->AfterClientMenuFrame(menusActive);}
