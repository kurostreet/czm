/* RU/EN chat hints. Shared game abbreviations and addresses are language-neutral. */
#pragma once
#include <string.h>
#include <ctype.h>

namespace CzmTextLanguage {
enum { Neutral, Russian, English };
inline int Detect(const char *text) {
    if(!text || !*text || !strncmp(text,"czm:invite ",11))return Neutral;
    int ru=0,en=0,ruWords=0,enWords=0;
    const unsigned char *p=(const unsigned char*)text;
    while(*p){
        while(*p && *p<=32)p++;
        const unsigned char *first=p;while(*p && *p>32)p++;
        const int length=(int)(p-first);if(!length)break;
        bool address=false;char token[96];int count=0,r=0,e=0;
        for(int i=0;i<length;i++){
            unsigned c=first[i];
            if(c==':'||c=='/'||c=='_'||c=='@'||c=='\\')address=true;
            if(c>=128){
                if((c==0xd0||c==0xd1)&&i+1<length&&(first[i+1]&0xc0)==0x80){r++;i++;}
                continue;
            }
            if(isalpha(c)){e++;if(count<95)token[count++]=(char)tolower(c);}
        }
        token[count]=0;
        if(address)continue;
        const char *neutral[]={"ok","gg","wp","ez","afk","brb","lol","xd","id","ze","zm","czm","fps","ping","support"};
        bool shared=false;
        if(!r)for(unsigned i=0;i<sizeof(neutral)/sizeof(neutral[0]);i++)if(!strcmp(token,neutral[i]))shared=true;
        if((length==4 && !memcmp(first,"ок",4))||(length==4 && !memcmp(first,"ОК",4)))shared=true;
        if(shared)continue;
        ru+=r;en+=e;if(r)ruWords++;if(e)enWords++;
    }
    if(!ru&&!en)return Neutral;
    // Map names and borrowed words should not turn an otherwise Russian sentence into English.
    if(ruWords && ruWords*2>=enWords)return Russian;
    if(ru>en)return Russian;
    return en?English:Russian;
}
inline bool Needs(const char *text,bool russian){
    const int language=Detect(text);
    return language!=Neutral && language!=(russian?Russian:English);
}
}
