"""Community API boundaries shared by native menu fixtures."""
STUB = r'''
#ifndef CZM_NATIVE_COMMUNITY_STUB
#define CZM_NATIVE_COMMUNITY_STUB
int CZM_RoleTagWidth(const char*,int,const char* = "",int = 0);
int CZM_DrawRoleTag(int,int,int,const char*,const char* = "",int = 0);
unsigned CZM_RoleColor(const char*,int = 255);
const char*CZM_OnlineRole();void CZM_CommunityShow(const char*,int);
int CZM_ServerOwner(const char*);
#endif
'''
HARNESS = r'''
static std::string actorRole="support",communityMode;static int communityPlayer;
static std::string verifiedAddress;static int verifiedOwner;
int CZM_ServerOwner(const char*address){return address&&verifiedAddress==address?verifiedOwner:0;}
const char*CZM_OnlineRole(){return actorRole.c_str();}
void CZM_CommunityShow(const char*mode,int player){communityMode=mode;communityPlayer=player;}
int CZM_RoleTagWidth(const char*role,int h,const char*,int cap){if(!role||!*role)return 0;return cap>0?std::min(h*4,cap):h*4;}
unsigned CZM_RoleColor(const char*role,int alpha){
 if(!strcmp(role,"support"))return PackRGBA(231,187,96,alpha);
 if(!strcmp(role,"moderator"))return PackRGBA(89,174,255,alpha);
 if(!strcmp(role,"tester"))return PackRGBA(185,137,255,alpha);
 if(!strcmp(role,"server_owner"))return PackRGBA(78,216,177,alpha);
 return PackRGBA(236,72,86,alpha);
}
int CZM_DrawRoleTag(int x,int y,int h,const char*role,const char*project,int cap){
 if(role&&!strcmp(role,"support")){const int width=CZM_DrawSupportTag(x,y,h);return cap>0?std::min(width,cap):width;}
 const int w=CZM_RoleTagWidth(role,h,project,cap);if(w)UI_FillRect(x,y,w,h,CZM_RoleColor(role,255));return w;
}
'''
