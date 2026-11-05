/* Address-based scope of the server LVL HUD. GPL-2.0-or-later. */
#pragma once
#include <cstdio>
#include <cstring>

namespace CzmHud {
static const char *const serverScopeFile = "official_servers.lst";
struct ServerScope {
    char addresses[2][64];
    void Load(const char *text) {
        memset(addresses,0,sizeof(addresses));
        int visible=-1;
        if(!text || sscanf(text,"%d %63s %63s",&visible,addresses[0],addresses[1])!=3 || (visible!=0 && visible!=1)) {
            memset(addresses,0,sizeof(addresses));
            return;
        }
        // The first field controls promotion in the server list, not ownership of the addresses.
        for(auto &address:addresses)
            if(!strcmp(address,"-") || strspn(address,"0123456789abcdefABCDEF.:[]")!=strlen(address)) address[0]=0;
    }
};
}
