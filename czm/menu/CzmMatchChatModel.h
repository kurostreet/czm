/* Native match chat state/input/geometry. No engine or platform keyboard dependency. GPL-3.0-or-later. */
#pragma once
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace CzmMatchChat {
enum { MaxBytes = 190, MaxCharacters = 190, HistorySize = 32, MessageBytes = 1023, MaxKeys = 56 };
enum State { Closed, History, Typing };
enum Action { None, Letter, Shift, Backspace, Language, Numbers, Space, HideKeyboard, Submit, Channel, Close, HistoryBody, Field, Outside };
struct Rect {
    int x,y,w,h;
    bool Contains(int px,int py)const{return w>0&&h>0&&px>=x&&py>=y&&px<x+w&&py<y+h;}
};
inline int Min(int a,int b){return a<b?a:b;}
inline int Max(int a,int b){return a>b?a:b;}

// Reject overlong sequences, surrogates and codepoints beyond Unicode. A partial
// character is never put in the draft or sent to the engine.
inline int Utf8Length(const char *s) {
    const unsigned char *p=(const unsigned char*)s;
    if(!p[0])return 0;
    int n=p[0]<0x80?1:p[0]>=0xc2&&p[0]<=0xdf?2:p[0]>=0xe0&&p[0]<=0xef?3:p[0]>=0xf0&&p[0]<=0xf4?4:0;
    if(!n)return 0;
    for(int i=1;i<n;i++)if(!p[i]||(p[i]&0xc0)!=0x80)return 0;
    if(n==3&&((p[0]==0xe0&&p[1]<0xa0)||(p[0]==0xed&&p[1]>=0xa0)))return 0;
    if(n==4&&((p[0]==0xf0&&p[1]<0x90)||(p[0]==0xf4&&p[1]>=0x90)))return 0;
    return n;
}
inline int Characters(const char *s){int n=0;while(*s){int k=Utf8Length(s);if(!k)break;s+=k;n++;}return n;}
inline bool Allowed(const char *s,int n) {
    const unsigned char c=(unsigned char)*s;
    if(n==1)return c>=32&&c!=127&&c!='"'&&c!='\\'&&c!=';';
    // C1 controls and zero-width bidi controls do not belong in a chat draft.
    if(n==2&&c==0xc2&&(unsigned char)s[1]<0xa0)return false;
    if(n==3&&c==0xe2&&(unsigned char)s[1]==0x80&&((unsigned char)s[2]>=0x8b&&(unsigned char)s[2]<=0x8f))return false;
    if(n==3&&c==0xe2&&(unsigned char)s[1]==0x80&&((unsigned char)s[2]>=0xaa&&(unsigned char)s[2]<=0xae))return false;
    return true;
}
inline bool Append(char *out,const char *text) {
    size_t used=strlen(out);int count=Characters(out);bool added=false;
    for(const char *p=text;*p;){
        const int n=Utf8Length(p);if(!n){p++;continue;}
        if(Allowed(p,n)){
            if(used+n>MaxBytes||count>=MaxCharacters)break;
            memcpy(out+used,p,n);used+=n;out[used]=0;count++;added=true;
        }
        p+=n;
    }
    return added;
}
inline void Delete(char *text){size_t n=strlen(text);if(!n)return;do{n--;}while(n&&((unsigned char)text[n]&0xc0)==0x80);text[n]=0;}
inline void Trim(char *text){size_t n=strlen(text),from=0;while(from<n&&text[from]==' ')from++;while(n>from&&text[n-1]==' ')n--;memmove(text,text+from,n-from);text[n-from]=0;}
inline int HexValue(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
inline bool Decode(const char *hex,char *out,size_t size){
    size_t n=strlen(hex);if(n%2||n/2>=size)return false;
    for(size_t i=0;i<n;i+=2){int a=HexValue(hex[i]),b=HexValue(hex[i+1]);if(a<0||b<0||!(a||b))return false;out[i/2]=(char)(a*16+b);}
    out[n/2]=0;return true;
}
inline void Encode(const char *text,char *out){const char *hex="0123456789abcdef";for(;*text;text++){unsigned c=(unsigned char)*text;*out++=hex[c>>4];*out++=hex[c&15];}*out=0;}
struct ByteInput {
    char pending[5];int used,expected;
    ByteInput():used(0),expected(0){pending[0]=0;}
    void Reset(){used=expected=0;pending[0]=0;}
    bool Add(char *draft,int ch){
        if(ch>255){
            Reset();char s[5]={};unsigned c=(unsigned)ch;
            if(c>0x10ffff||(c>=0xd800&&c<=0xdfff))return false;
            if(c<0x80)s[0]=(char)c;
            else if(c<0x800){s[0]=(char)(0xc0|(c>>6));s[1]=(char)(0x80|(c&63));}
            else if(c<0x10000){s[0]=(char)(0xe0|(c>>12));s[1]=(char)(0x80|((c>>6)&63));s[2]=(char)(0x80|(c&63));}
            else{s[0]=(char)(0xf0|(c>>18));s[1]=(char)(0x80|((c>>12)&63));s[2]=(char)(0x80|((c>>6)&63));s[3]=(char)(0x80|(c&63));}
            return Append(draft,s);
        }
        unsigned c=(unsigned char)ch;
        if(c<0x80){Reset();char s[2]={(char)c,0};return Append(draft,s);}
        if(c>=0xc2&&c<=0xf4){Reset();expected=c<0xe0?2:c<0xf0?3:4;pending[used++]=(char)c;return false;}
        if((c&0xc0)!=0x80||!used){Reset();return false;}
        pending[used++]=(char)c;pending[used]=0;
        if(used<expected)return false;
        bool added=Utf8Length(pending)==expected&&Append(draft,pending);Reset();return added;
    }
};
struct Message { unsigned seq,rgb;int nameLength;char text[MessageBytes+1]; };
inline bool ParseMessage(const char *value,Message &m){
    char *end;unsigned long seq=strtoul(value,&end,10);if(!seq||*end!=' ')return false;
    value=end+1;unsigned rgb=0;for(int i=0;i<6;i++){int k=HexValue(value[i]);if(k<0)return false;rgb=rgb*16+k;}if(value[6]!=' ')return false;
    value+=7;long name=strtol(value,&end,10);if(end==value||*end!=' '||name<0||name>MessageBytes)return false;
    if(!Decode(end+1,m.text,sizeof(m.text)))return false;
    m.seq=(unsigned)seq;m.rgb=rgb;m.nameLength=(int)name;return true;
}
struct Model {
    State state;bool team,russian,numbers,shift,caps;int epoch,historyEpoch;unsigned request,head;
    char draft[MaxBytes+1],identity[256];ByteInput input;
    Message messages[HistorySize];int count,scroll;
    Model():state(Closed),team(false),russian(true),numbers(false),shift(false),caps(false),epoch(-1),historyEpoch(-1),request(0),head(0),count(0),scroll(0){draft[0]=identity[0]=0;}
    void ResetDraft(){draft[0]=0;input.Reset();shift=caps=false;}
    void ResetHistory(){count=scroll=0;head=0;}
    bool Context(int nextEpoch,int nextHistoryEpoch,const char *server){
        bool changed=epoch!=nextEpoch||historyEpoch!=nextHistoryEpoch||strcmp(identity,server);
        if(changed){
            state=Closed;ResetDraft();
            if(historyEpoch!=nextHistoryEpoch||strcmp(identity,server))ResetHistory();
            epoch=nextEpoch;historyEpoch=nextHistoryEpoch;snprintf(identity,sizeof(identity),"%s",server);
        }
        return changed;
    }
    void Open(bool toTeam){state=Typing;team=toTeam;scroll=0;input.Reset();}
    void Back(){input.Reset();shift=false;if(state==Typing)state=History;else state=Closed;}
    void Push(const Message &m){
        if(count&&m.seq<=messages[count-1].seq)return;
        if(count==HistorySize){memmove(messages,messages+1,sizeof(messages[0])*(HistorySize-1));count--;}
        messages[count++]=m;
    }
    bool Take(char *out){
        char clean[MaxBytes+1]={};Append(clean,draft);Trim(clean);snprintf(draft,sizeof(draft),"%s",clean);
        if(!*clean)return false;
        snprintf(out,MaxBytes+1,"%s",clean);ResetDraft();return true;
    }
};
struct Key { Rect rect;Action action;char text[16]; };
struct Layout {
    Rect history,clip,composer,channel,field,send,close,keyboard;
    Key keys[MaxKeys];int count,gap,pad,keyHeight;
    void Add(Action action,const char *label,int x,int y,int w,int h){if(count>=MaxKeys)return;Key &k=keys[count++];k.rect={x,y,w,h};k.action=action;snprintf(k.text,sizeof(k.text),"%s",label);}
    void Row(const char *letters,int y,int x,int width){
        int n=Characters(letters);if(!n)return;
        int at=x,index=0;
        for(const char *p=letters;*p;index++){
            int len=Utf8Length(p);if(!len)break;char text[5]={};memcpy(text,p,len);p+=len;
            const int right=x+(index+1)*(width+gap)/n-gap;
            Add(Letter,text,at,y,right-at,keyHeight);at=right+gap;
        }
    }
    void Build(int W,int H,const Model &m){
        count=0;gap=Max(2,H*7/1000);pad=Max(5,H*16/1000);keyHeight=Max(26,H*65/1000);
        const int margin=Max(6,H*18/1000),width=W-margin*2,bar=Max(30,H*68/1000);
        const int keyboardHeight=keyHeight*4+gap*3+pad*2;
        keyboard=m.state==Typing?Rect{margin,H-margin-keyboardHeight,width,keyboardHeight}:Rect{0,0,0,0};
        const int historyWidth=Min(width,Max(W*35/100,Min(W*53/100,H*74/100)));
        int composerY=m.state==Typing?keyboard.y-gap-bar:H*64/100;
        const int composerWidth=m.state==Typing?width:historyWidth;
        composer={margin,composerY,composerWidth,bar};
        int channelW=Min(composerWidth/4,Max(66,H*16/100));
        close={composer.x+composer.w-bar,composer.y,bar,bar};
        send={close.x-gap-bar*14/10,composer.y,bar*14/10,bar};
        channel={composer.x,composer.y,channelW,bar};
        field={channel.x+channel.w+gap,composer.y,Max(1,send.x-gap-channel.x-channel.w-gap),bar};
        // The history stays compact when the keyboard is hidden. On short
        // screens it yields rows to the keyboard instead of covering the radar.
        int historyTop=Max(margin,Max(H*27/100,composerY-gap-H*23/100));
        history={margin,Max(margin,historyTop),historyWidth,Max(1,composerY-gap-Max(margin,historyTop))};
        clip={history.x+pad,history.y+pad,history.w-pad*2,Max(1,history.h-pad*2)};
        if(m.state!=Typing)return;
        int x=keyboard.x+pad,y=keyboard.y+pad,w=keyboard.w-pad*2;
        const char *ru[]={"ёйцукенгшщзхъ","фывапролджэ","ячсмитьбю"};
        const char *en[]={"qwertyuiop","asdfghjkl","zxcvbnm"};
        const char *num[]={"1234567890","@#%&*()-+=",".,!?/:_"};
        const char **rows=m.numbers?num:m.russian?ru:en;
        Row(rows[0],y,x,w);y+=keyHeight+gap;
        Row(rows[1],y,x+w/24,w-w/12);y+=keyHeight+gap;
        int special=w*12/100;
        Add(Shift,m.caps?"CAPS":"Shift",x,y,special,keyHeight);
        Row(rows[2],y,x+special+gap,w-special*2-gap*2);
        Add(Backspace,"⌫",x+w-special,y,special,keyHeight);y+=keyHeight+gap;
        int unit=(w-gap*6)/13,at=x;
        Add(Numbers,m.numbers?"ABC":"123",at,y,unit*2,keyHeight);at+=unit*2+gap;
        Add(Language,m.russian?"RU":"EN",at,y,unit*2,keyHeight);at+=unit*2+gap;
        Add(Letter,",",at,y,unit,keyHeight);at+=unit+gap;
        Add(Space,m.russian?"Пробел":"Space",at,y,unit*4,keyHeight);at+=unit*4+gap;
        Add(Letter,".",at,y,unit,keyHeight);at+=unit+gap;
        Add(HideKeyboard,"⌄",at,y,unit,keyHeight);at+=unit+gap;
        Add(Submit,"Enter",at,y,x+w-at,keyHeight);
    }
};
inline void Upper(char *text){
    unsigned char *p=(unsigned char*)text;
    if(p[0]>='a'&&p[0]<='z')p[0]-=32;
    else if(p[0]==0xd0&&p[1]>=0xb0&&p[1]<=0xbf)p[1]-=32;
    else if(p[0]==0xd1&&p[1]>=0x80&&p[1]<=0x8f){p[0]=0xd0;p[1]+=32;}
    else if(p[0]==0xd1&&p[1]==0x91){p[0]=0xd0;p[1]=0x81;}
}
} // namespace CzmMatchChat
