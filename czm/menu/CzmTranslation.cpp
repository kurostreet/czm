/* Bounded, account-scoped, memory-only cache for on-device RU/EN translations. */
#include <string.h>
#include "extdll_menu.h"
#include "BaseMenu.h"
#include "CzmMenu.h"
#include "CzmJson.h"
#include "CzmTranslation.h"
#include "CzmTextLanguage.h"

namespace {
struct Entry { char original[1604],translated[6404];int request,state;bool shown;double used; };
CUtlVector<Entry> entries;
CUtlVector<int> abandoned;
int identity=-1;bool russian;double nextPoll;
int Find(const char *text){for(int i=0;i<entries.Count();i++)if(!strcmp(entries[i].original,text))return i;return -1;}
}
void CZM_TranslationFrame(){
    if(identity!=CZM_OnlineIdentity()||russian!=CZM_IsRussian()){
        for(int i=0;i<entries.Count();i++)if(entries[i].request)abandoned.AddToTail(entries[i].request);
        entries.RemoveAll();identity=CZM_OnlineIdentity();russian=CZM_IsRussian();nextPoll=0;
    }
    const double now=EngFuncs::DoubleTime();if(now<nextPoll)return;nextPoll=now+.02;
    int status;CUtlString body;
    for(int i=abandoned.Count()-1;i>=0;i--)if(CZM_NetPoll(abandoned[i],&status,body))abandoned.Remove(i);
    for(int i=0;i<entries.Count();i++){
        Entry &e=entries[i];if(!e.request||!CZM_NetPoll(e.request,&status,body))continue;
        e.request=0;CzmJson json;
        if(status==200&&json.Parse(body.Get())&&json.String(json.Get(0,"text"))[0]){
            Q_strncpy(e.translated,json.String(json.Get(0,"text")),sizeof(e.translated));e.state=2;e.shown=true;
        }else{e.state=status==499?0:3;e.shown=false;}
    }
}
bool CZM_CanTranslate(const char *text){return CZM_TranslationAvailable()&&CzmTextLanguage::Needs(text,CZM_IsRussian());}
CzmTranslationView CZM_TranslationGet(const char *text){
    CZM_TranslationFrame();const int i=Find(text);
    if(i<0)return {0,false,""};
    entries[i].used=EngFuncs::DoubleTime();return {entries[i].state,entries[i].shown,entries[i].translated};
}
void CZM_Translate(const char *text){
    CZM_TranslationFrame();if(!CZM_CanTranslate(text)||strlen(text)>=1604)return;
    int index=Find(text),pending=0;for(int i=0;i<entries.Count();i++)if(entries[i].request)pending++;
    if(index>=0){Entry&e=entries[index];if(e.state==2){e.shown=!e.shown;return;}if(e.request)return;}
    if(pending>=4)return;
    if(index<0){
        if(entries.Count()>=64){
            int oldest=-1;for(int i=0;i<entries.Count();i++)if(!entries[i].request&&(oldest<0||entries[i].used<entries[oldest].used))oldest=i;
            if(oldest<0)return;entries.Remove(oldest);
        }
        Entry entry;memset(&entry,0,sizeof(entry));Q_strncpy(entry.original,text,sizeof(entry.original));index=entries.AddToTail(entry);
    }
    Entry&e=entries[index];e.used=EngFuncs::DoubleTime();e.request=CZM_TranslationStart(text,CZM_IsRussian());e.state=e.request?1:3;
}
