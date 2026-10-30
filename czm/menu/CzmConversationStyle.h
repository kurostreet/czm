/* One geometry for rendering and tapping public and private chat messages. */
#pragma once
#include <time.h>
#include "CzmDesign.h"
#include "CzmTranslation.h"

namespace CzmConversation {
enum { Lines=128 };
inline bool SameDay(int a,int b){time_t x=a,y=b;struct tm first,second;localtime_r(&x,&first);localtime_r(&y,&second);return first.tm_year==second.tm_year&&first.tm_yday==second.tm_yday;}
inline int DateHeight(){return CZM_FontHeight(CZM_Font(CZMF_UI_META))+Q_max(8,ScreenHeight/70);}
inline void Date(const CzmRect &clip,int y,int stamp){
    time_t value=stamp;struct tm day;localtime_r(&value,&day);char label[40];strftime(label,sizeof(label),"%d.%m.%Y",&day);
    const int height=DateHeight(),width=CZM_TextWidth(CZM_Font(CZMF_UI_META),label)+height;
    CzmStyle::Round(CZM_Rect(clip.x+(clip.w-width)/2,y,width,height-3),PackRGBA(27,35,47,255));
    CzmStyle::Text(CZM_Rect(clip.x,y,clip.w,height-3),label,CZMF_UI_META,CzmStyle::Muted(),QM_CENTER);
}
struct Bubble {
    CzmRect frame,avatar,header,menu,translate,body,result,credit,roleTag,topTag;
    int height,originalLines,resultLines,starts[Lines+1],translatedStarts[Lines+1];
    bool canTranslate;CzmTranslationView translation;
};
inline const char *TranslateLabel(const CzmTranslationView &view){
    if(view.state==1)return CZM_IsRussian()?"Переводим…":"Translating…";
    if(view.state==3)return CZM_IsRussian()?"Повторить перевод":"Retry translation";
    if(view.state==2&&view.shown)return CZM_IsRussian()?"Скрыть перевод":"Hide translation";
    return CZM_IsRussian()?"Перевести с Google":"Translate with Google";
}
inline Bubble Layout(const CzmRect &clip,int top,const char *text,const char *nick,bool mine,bool deleted=false,const char *role="",const char *project="",int place=0){
    Bubble b={};const int H=ScreenHeight,inset=Q_max(6,H/85),gap=Q_max(4,H/150);
    const HFont body=CZM_Font(CZMF_CHAT_TEXT),name=CZM_Font(CZMF_UI_LABEL),meta=CZM_Font(CZMF_UI_META);
    const int line=CZM_FontHeight(body)+2,header=Q_max(CZM_FontHeight(name),H/28);
    const int av=Q_max(24,(int)(H*.055f)),maxWidth=Q_max(80,Q_min(clip.w-av-inset*2,clip.w*74/100));
    b.canTranslate=!deleted&&CZM_CanTranslate(text);b.translation=b.canTranslate?CZM_TranslationGet(text):CzmTranslationView{0,false,""};
    b.originalLines=CZM_WrapText(body,text,Q_max(1,maxWidth-inset*2),b.starts,Lines);
    b.resultLines=b.translation.state==2&&b.translation.shown?CZM_WrapText(body,b.translation.text,Q_max(1,maxWidth-inset*2),b.translatedStarts,Lines):0;
    int width=Q_min(maxWidth,CZM_TextWidth(name,nick)+CZM_TextWidth(meta,"00:00")+header+inset*4);
    for(int i=0;i<b.originalLines;i++){char part[1604];CZM_WrapLine(text,b.starts,i,part,sizeof(part));width=Q_max(width,Q_min(maxWidth,CZM_TextWidth(body,part)+inset*2));}
    for(int i=0;i<b.resultLines;i++){char part[6404];CZM_WrapLine(b.translation.text,b.translatedStarts,i,part,sizeof(part));width=Q_max(width,Q_min(maxWidth,CZM_TextWidth(body,part)+inset*2));}
    if(b.canTranslate)width=Q_max(width,Q_min(maxWidth,CZM_TextWidth(meta,TranslateLabel(b.translation))+inset*2));
    if(b.resultLines)width=Q_max(width,Q_min(maxWidth,H/5+inset*2));
    // Re-wrap at the final content width, including unexpectedly narrow screens.
    b.originalLines=CZM_WrapText(body,text,Q_max(1,width-inset*2),b.starts,Lines);
    if(b.resultLines)b.resultLines=CZM_WrapText(body,b.translation.text,Q_max(1,width-inset*2),b.translatedStarts,Lines);
    const int x=mine?clip.x+clip.w-av-inset-width:clip.x+av+inset;
    int y=top+inset;
    b.header=CZM_Rect(x+inset,y,width-inset*2,header);
    b.menu=CZM_Rect(x+width-header-inset,y,header,header);y+=header+gap;
    if((role&&role[0])||(place>0&&place<=100)){
        const int height=CZM_FontHeight(meta)+4,roleWidth=role&&role[0]?CZM_RoleTagWidth(role,height,project,width-inset*2):0;
        const int topWidth=CZM_TopTagWidth(place,height);
        if(roleWidth)b.roleTag=CZM_Rect(x+inset,y,roleWidth,height);
        int tx=x+inset+(roleWidth?roleWidth+gap:0);
        if(topWidth&&tx+topWidth>x+width-inset){y+=height+gap;tx=x+inset;}
        if(topWidth)b.topTag=CZM_Rect(tx,y,Q_min(topWidth,width-inset*2),height);
        y+=height+gap;
    }
    if(b.canTranslate){b.translate=CZM_Rect(x+inset,y,width-inset*2,Q_max(20,CZM_FontHeight(meta)+gap*2));y+=b.translate.h+gap;}
    b.body=CZM_Rect(x+inset,y,width-inset*2,b.originalLines*line);y+=b.body.h;
    if(b.resultLines){
        y+=gap*2;b.result=CZM_Rect(x+inset,y,width-inset*2,b.resultLines*line);y+=b.result.h+gap;
        const int creditWidth=Q_min(width-inset*2,Q_max(88,(int)(H*.26f)));
        b.credit=CZM_Rect(x+inset,y,creditWidth,Q_max(8,creditWidth*32/352));y+=b.credit.h;
    }
    b.frame=CZM_Rect(x,top,width,y+inset-top);b.height=Q_max(av,b.frame.h)+gap*2;
    b.avatar=CZM_Rect(mine?clip.x+clip.w-av:clip.x,top,av,av);return b;
}
inline void Draw(const Bubble &b,const char *text,const char *nick,const char *avatar,int stamp,bool mine,bool deleted,bool menuPressed=false,const char *role="",const char *project="",int place=0){
    using namespace CzmStyle;
    const int inset=Q_max(6,ScreenHeight/85),gap=Q_max(4,ScreenHeight/150);
    Surface(b.frame,mine?PackRGBA(48,29,40,255):PackRGBA(24,33,46,255),mine?PackRGBA(103,47,62,255):Border());
    CZM_DrawImage(avatar,b.avatar.x,b.avatar.y,b.avatar.w,b.avatar.h);
    const int nameWidth=Q_max(0,b.header.w-b.menu.w-CZM_TextWidth(CZM_Font(CZMF_UI_META),"00:00")-gap*2);
    Text(CZM_Rect(b.header.x,b.header.y,nameWidth,b.header.h),nick,CZMF_UI_LABEL,mine?PackRGBA(245,179,188,255):Ink());
    time_t value=stamp;struct tm date;char when[20];localtime_r(&value,&date);strftime(when,sizeof(when),"%H:%M",&date);
    const int timeWidth=CZM_TextWidth(CZM_Font(CZMF_UI_META),when)+gap;
    Text(CZM_Rect(b.menu.x-timeWidth-gap,b.header.y,timeWidth,b.header.h),when,CZMF_UI_META,Muted());
    if(!deleted){if(menuPressed)Round(b.menu,PackRGBA(57,66,82,255));Icon(b.menu,"gfx/czm/ui/icon_more.png",Muted());}
    if(b.roleTag.w)CZM_DrawRoleTag(b.roleTag.x,b.roleTag.y,b.roleTag.h,role,project,b.roleTag.w);
    if(b.topTag.w)CZM_DrawTopTag(b.topTag.x,b.topTag.y,b.topTag.h,place);
    if(b.canTranslate)Text(b.translate,TranslateLabel(b.translation),CZMF_UI_META,b.translation.state==3?AccentGold():AccentBlue());
    const int line=CZM_FontHeight(CZM_Font(CZMF_CHAT_TEXT))+2;
    for(int i=0;i<b.originalLines;i++){char part[1604];CZM_WrapLine(text,b.starts,i,part,sizeof(part));CZM_DrawText(CZM_Font(CZMF_CHAT_TEXT),b.body.x,b.body.y+i*line,b.body.w,part,deleted?Muted():Ink());}
    if(b.resultLines){
        UI_FillRect(b.result.x,b.result.y-gap,b.result.w,1,PackRGBA(67,89,115,255));
        for(int i=0;i<b.resultLines;i++){char part[6404];CZM_WrapLine(b.translation.text,b.translatedStarts,i,part,sizeof(part));CZM_DrawText(CZM_Font(CZMF_CHAT_TEXT),b.result.x,b.result.y+i*line,b.result.w,part,PackRGBA(186,216,247,255));}
        // Official, unmodified Google Translate attribution asset.
        CZM_DrawImage("gfx/czm/ui/google_translate.png",b.credit.x,b.credit.y,b.credit.w,b.credit.h);
    }
}
}
