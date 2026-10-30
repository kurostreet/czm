/* Native profile presentation; data and permissions stay with the social service. */
#pragma once
#include "CzmDesign.h"

namespace CzmProfileStyle {
enum { Ember, Frost, City, Lab, ThemeCount };
inline const char *ThemeKey(int index) {
    static const char *keys[]={"ember","frost","city","lab"};
    return keys[bound(0,index,ThemeCount-1)];
}
inline int ThemeIndex(const char *key) {
    for(int i=0;i<ThemeCount;i++)if(key&&!strcmp(key,ThemeKey(i)))return i;
    return Ember;
}
inline const char *ThemeArt(int index) {
    static const char *images[]={"gfx/czm/profile/ember.png","gfx/czm/profile/frost.png","gfx/czm/profile/city.png","gfx/czm/profile/lab.png"};
    return images[bound(0,index,ThemeCount-1)];
}
inline const char *ThemeName(int index) {
    static const char *ru[]={"Огненный фронт","Ледяной рубеж","Заброшенный город","Заражённая лаборатория"};
    static const char *en[]={"Ember front","Frozen frontier","Abandoned city","Infected laboratory"};
    return (CZM_IsRussian()?ru:en)[bound(0,index,ThemeCount-1)];
}
inline unsigned Alpha(unsigned color,int opacity) { return (color&0x00ffffffu)|((unsigned)bound(0,opacity,255)<<24); }
inline unsigned ThemeColor(int index) {
    static const unsigned colors[]={PackRGBA(244,89,60,255),PackRGBA(99,192,255,255),PackRGBA(230,166,101,255),PackRGBA(82,216,169,255)};
    return colors[bound(0,index,ThemeCount-1)];
}
inline unsigned RoleAccent(const char *role) {
    return role&&!strcmp(role,"support")?PackRGBA(255,80,57,255):CZM_RoleColor(role);
}
inline void Frame(const CzmRect &r,unsigned accent,double time) {
    const int line=Q_max(1,ScreenHeight/600),cut=Q_max(5,ScreenHeight/85);
    const unsigned left=PackRGBA(143,180,196,200),right=Alpha(accent,180+(int)(35*sin(time*1.25)));
    UI_FillRect(r.x+cut,r.y,r.w/2-cut,line,left);
    UI_FillRect(r.x+r.w/2,r.y,r.w/2-cut,line,right);
    UI_FillRect(r.x+cut,r.y+r.h-line,r.w/2-cut,line,left);
    UI_FillRect(r.x+r.w/2,r.y+r.h-line,r.w/2-cut,line,right);
    UI_FillRect(r.x,r.y+cut,line,r.h-cut*2,left);
    UI_FillRect(r.x+r.w-line,r.y+cut,line,r.h-cut*2,right);
    for(int i=0;i<cut;i++){
        const unsigned mask=PackRGBA(13,18,26,255);
        UI_FillRect(r.x,r.y+i,cut-i,1,mask);UI_FillRect(r.x+r.w-cut+i,r.y+i,cut-i,1,mask);
        UI_FillRect(r.x,r.y+r.h-i-1,cut-i,1,mask);UI_FillRect(r.x+r.w-cut+i,r.y+r.h-i-1,cut-i,1,mask);
        UI_FillRect(r.x+cut-i-1,r.y+i,line,1,left);UI_FillRect(r.x+r.w-cut+i,r.y+i,line,1,right);
        UI_FillRect(r.x+cut-i-1,r.y+r.h-i-1,line,1,left);UI_FillRect(r.x+r.w-cut+i,r.y+r.h-i-1,line,1,right);
    }
    const int length=Q_max(18,r.w/12);
    UI_FillRect(r.x+r.w-cut-length,r.y+line,length,line,Alpha(accent,90));
}
inline void Background(const CzmRect &r,int theme,double time,bool particles=true) {
    UI::Scissor::PushScissor(r.x,r.y,r.w,r.h);
    HIMAGE image=CZM_Image(ThemeArt(theme));
    if(image)CZM_DrawCover(image,r.x,r.y,r.w,r.h);
    else UI_FillRect(r.x,r.y,r.w,r.h,PackRGBA(9,17,26,255));
    CZM_DrawImage("gfx/czm/fade_left.png",r.x,r.y,r.w,r.h,PackRGBA(255,255,255,110));
    if(particles){
        for(int i=0;i<7;i++){
            const double phase=fmod(time*.035+i*.173,1.0);
            const int side=Q_max(2,ScreenHeight/300)+(i%2);
            const int x=r.x+(int)(r.w*(.66+.31*fmod(i*.37,1.0)))+(int)(sin(time*.28+i)*r.w*.006);
            const int y=r.y+(int)(r.h*(1.0-phase));
            CZM_DrawImage("gfx/czm/ui/dot.png",x,y,side,side,Alpha(ThemeColor(theme),(int)(95*sin(phase*M_PI))));
        }
    }
    UI::Scissor::PopScissor();
}
inline int BadgeWidth(const char *label,int height) {
    return CZM_TextWidth(CZM_Font(CZMF_UI_META),label)+height*7/4;
}
inline int Badge(int x,int y,int height,const char *label,const char *icon,unsigned color,int cap) {
    const int width=Q_min(cap,BadgeWidth(label,height));if(width<height*2)return 0;
    const CzmRect r=CZM_Rect(x,y,width,height);
    CzmStyle::Surface(r,PackRGBA(9,16,25,255),Alpha(color,190),Q_max(3,height/5));
    const int side=height*60/100;
    CZM_DrawImage(icon,x+height/5,y+(height-side)/2,side,side,color);
    CZM_DrawText(CZM_Font(CZMF_UI_META),x+height,y+(height-CZM_FontHeight(CZM_Font(CZMF_UI_META)))/2,width-height*6/5,label,color);
    return width;
}

struct Tag { const char *label,*icon; unsigned color; };
template<class Profile> inline int Tags(const Profile &p,Tag *tags) {
    int count=0;
    if(p.support)tags[count++]={"SUPPORT","gfx/czm/ui/icon_shield.png",RoleAccent("support")};
    if((p.roleFlags&2)||!strcmp(p.role,"moderator"))tags[count++]={"MODERATOR","gfx/czm/ui/icon_shield.png",CZM_RoleColor("moderator")};
    if((p.roleFlags&4)||!strcmp(p.role,"tester"))tags[count++]={"OFFICIAL TESTER CZM","gfx/czm/ui/icon_tools.png",CZM_RoleColor("tester")};
    if(p.serverOwner)tags[count++]={"SERVER OWNER","gfx/czm/ui/icon_crown.png",CZM_RoleColor("server_owner")};
    if(p.topPlace>0&&p.topPlace<=100)tags[count++]={p.topPlace<=3?"TOP 3":p.topPlace<=10?"TOP 10":p.topPlace<=50?"TOP 50":"TOP 100",CZM_TopCrown(p.topPlace),CZM_TopColor(p.topPlace)};
    return count;
}
inline int TagRows(const Tag *tags,int count,int width,int height,int space) {
    int rows=count?1:0,x=0;
    for(int i=0;i<count;i++){
        const int w=Q_min(width,BadgeWidth(tags[i].label,height));
        if(x&&x+w>width){rows++;x=0;}x+=w+space;
    }
    return rows;
}
template<class Profile> inline int NameY(const CzmRect &r,const Profile &p) {
    const int gap=Q_max(4,(int)(ScreenHeight*.012f)),footer=CZM_FontHeight(CZM_Font(CZMF_SMALL))+gap*2;
    const int av=Q_min(r.h-footer-gap*2,Q_max(44,(int)(ScreenHeight*(p.serverOwner&&ScreenHeight<480?.18f:.22f))));
    const int width=Q_max(0,r.w*69/100-(av+gap*4)),bh=CZM_FontHeight(CZM_Font(CZMF_UI_META))+Q_max(5,gap),space=Q_max(3,gap/2);
    Tag tags[5];const int count=Tags(p,tags),rows=TagRows(tags,count,width,bh,space);
    const int group=CZM_FontHeight(CZM_Font(CZMF_NICK))+gap+CZM_FontHeight(CZM_Font(CZMF_SMALL))+(rows?rows*(bh+space)-space+gap:0);
    return r.y+Q_max(gap,(r.h-footer-group)/2);
}

template<class Profile> inline void Banner(const CzmRect &r,const CzmRect &copy,const CzmRect &edit,
    const Profile &p,const char *presence,bool self,bool copying,bool editing) {
    using namespace CzmStyle;
    const int gap=Q_max(4,(int)(ScreenHeight*.012f)),theme=ThemeIndex(p.theme);
    const unsigned accent=p.role[0]?RoleAccent(p.role):ThemeColor(theme);
    const double time=EngFuncs::DoubleTime(),wave=.5+.5*sin(time*1.25);
    const HFont meta=CZM_Font(CZMF_UI_META),nick=CZM_Font(CZMF_NICK),small=CZM_Font(CZMF_SMALL);
    Background(r,theme,time);
    const int footer=CZM_FontHeight(small)+gap*2,upper=r.h-footer;
    UI_FillRect(r.x,r.y+upper,r.w,footer,PackRGBA(3,8,15,180));
    UI_FillRect(r.x+gap,r.y+upper,r.w-gap*2,1,Alpha(accent,70));
    const bool compact=p.serverOwner&&ScreenHeight<480;
    const int av=Q_min(upper-gap*2,Q_max(44,(int)(ScreenHeight*(compact?.18f:.22f))));
    const int ax=r.x+gap*2,ay=r.y+(upper-av)/2,ring=Q_max(2,av/32);
    CZM_DrawImage("gfx/czm/ui/glow.png",ax-av/3,ay-av/3,av*5/3,av*5/3,Alpha(accent,55+(int)(20*wave)));
    CZM_DrawImage("gfx/czm/ui/dot.png",ax-3,ay-3,av+6,av+6,PackRGBA(9,16,25,255));
    CZM_DrawImage(CZM_AvatarFor(p.avatar,p.id),ax,ay,av,av);
    CZM_DrawImage("gfx/czm/ui/icon_ring.png",ax-ring-2,ay-ring-2,av+ring*2+4,av+ring*2+4,PackRGBA(139,157,172,100));
    CZM_DrawImage("gfx/czm/ui/icon_ring.png",ax-ring,ay-ring,av+ring*2,av+ring*2,Alpha(accent,155+(int)(35*wave)));
    const int tx=ax+av+gap*2,tw=Q_max(0,r.w*69/100-(tx-r.x));
    const int nh=CZM_FontHeight(nick),pencil=self?Q_max(10,nh*3/5):0;
    const int nameY=NameY(r,p);
    CZM_DrawText(nick,tx,nameY,tw-(self?pencil+gap:0),p.nick,Ink());
    if(self&&edit.w)CZM_DrawImage("gfx/czm/ui/icon_pencil.png",edit.x+edit.w-pencil-gap/2,edit.y+(nh-pencil)/2,pencil,pencil,editing?Ink():PackRGBA(177,192,207,240));
    Tag tags[5];const int count=Tags(p,tags);
    const int bh=CZM_FontHeight(meta)+Q_max(5,gap),space=Q_max(3,gap/2),fh=CZM_FontHeight(small);
    const int rows=TagRows(tags,count,tw,bh,space);
    const int presenceY=nameY+nh+gap+(rows?rows*(bh+space)-space+gap:0);int x=tx,y=nameY+nh+gap;
    for(int i=0;i<count;i++){
        const int width=Q_min(tw,BadgeWidth(tags[i].label,bh));
        if(x>tx&&x+width>tx+tw){x=tx;y+=bh+space;}
        if(y+bh>presenceY-space)break;
        x+=Badge(x,y,bh,tags[i].label,tags[i].icon,tags[i].color,tx+tw-x)+space;
    }
    const int dot=Q_max(5,(int)(ScreenHeight*.012f));
    CZM_DrawImage("gfx/czm/ui/dot.png",tx,presenceY+(fh-dot)/2,dot,dot,p.online?PackRGBA(66,216,137,240):PackRGBA(120,128,142,220));
    CZM_DrawText(small,tx+dot+gap,presenceY,tw-dot-gap,presence,p.online?PackRGBA(135,237,179,255):Muted());
    char id[32];snprintf(id,sizeof(id),"ID %d",p.id);
    Surface(copy,copying?PackRGBA(42,54,73,245):PackRGBA(9,17,29,220),PackRGBA(97,117,140,160),copy.h/3);
    const int copyIcon=copy.h*57/100;
    CZM_DrawText(meta,copy.x+gap,copy.y+(copy.h-CZM_FontHeight(meta))/2,CZM_TextWidth(meta,id)+2,id,PackRGBA(215,226,237,255));
    CZM_DrawImage("gfx/czm/ui/icon_copy.png",copy.x+copy.w-gap-copyIcon,copy.y+(copy.h-copyIcon)/2,copyIcon,copyIcon,PackRGBA(215,226,237,255));
    char played[48],line[180];CZM_FormatPlaytime(p.topSeconds,played,sizeof(played));
    if(p.topPlace>0&&p.topPlace<=100)snprintf(line,sizeof(line),CZM_IsRussian()?"№%d в Топ 100  ·  %s на серверах":"#%d in the Top 100  ·  %s on servers",p.topPlace,played);
    else if(p.topPlace>0)snprintf(line,sizeof(line),CZM_IsRussian()?"Место №%d  ·  %s на серверах":"Place #%d  ·  %s on servers",p.topPlace,played);
    else snprintf(line,sizeof(line),CZM_IsRussian()?"На серверах: %s":"Time on servers: %s",played);
    const unsigned gold=p.topPlace>0&&p.topPlace<=100?CZM_TopColor(p.topPlace):PackRGBA(184,204,224,255);
    const int ly=r.y+upper+(footer-fh)/2;
    CZM_DrawImage(p.topPlace>0?CZM_TopCrown(p.topPlace):"gfx/czm/ui/icon_clock.png",r.x+gap*2,ly,fh,fh,gold);
    CZM_DrawText(small,r.x+gap*3+fh,ly,r.w-gap*5-fh,line,gold);
    Frame(r,accent,time);
}
}
