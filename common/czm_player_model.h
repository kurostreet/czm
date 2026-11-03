/* A model name from player info, never a free-form file path. GPL-2.0-or-later. */
#pragma once
#include <cstdio>
#include <cstring>
namespace CzmPlayerModel {
inline bool Path(const char *name,char *out,size_t size) {
    if(size) out[0]=0;
    if(!name || !*name || strlen(name)>48 || !size) return false;
    for(const unsigned char *p=(const unsigned char *)name;*p;p++)
        if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='_'||*p=='-')) return false;
    int n=snprintf(out,size,"models/player/%s/%s.mdl",name,name);
    if(n<0 || (size_t)n>=size) { out[0]=0; return false; }
    return true;
}
}
