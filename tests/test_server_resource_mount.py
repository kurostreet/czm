"""Execute the production engine mount boundary and JNI lifecycle with deterministic adapters."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs/engine"

STUB = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>
#include "czm_resource_mount.h"
typedef bool qboolean;
typedef char string[256];
#define Q_snprintf snprintf
#define Q_strcmp strcmp
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
enum { FS_NOWRITE_PATH=1,FS_CUSTOM_PATH=8,FS_EXEC_PATH=32,FS_STATIC_PATH=64 };
static czm_resource_mount_t fs_czm_resources;
static struct {const char *string="english";}ui_language;
static std::vector<std::string> paths;
static std::string writepath="userdata/cstrike";
static std::map<std::string,std::string> resource;
static int rescans=0,adds=0;
static unsigned FS_MountFlags(){return 0;}
static void Rescan(unsigned,const char*){rescans++;paths={"bundled"};}
static void Add(const char *path,unsigned flags){
 assert(flags==(FS_NOWRITE_PATH|FS_CUSTOM_PATH));
 assert(!(flags&(FS_EXEC_PATH|FS_STATIC_PATH)));
 paths.insert(paths.begin(),path);adds++;
 if(!(flags&FS_NOWRITE_PATH))writepath=path;
}
static struct {void(*Rescan)(unsigned,const char*)=::Rescan;void(*AddGameDirectory)(const char*,unsigned)=Add;}g_fsapi;
static std::string Find(){for(const auto &path:paths){auto f=resource.find(path);if(f!=resource.end())return f->second;}return "";}
'''

JNI = r'''
#define __ANDROID__ 1
typedef const char *jclass;
typedef const char *jmethodID;
typedef const char *jstring;
struct JNITable;
typedef JNITable *JNIEnv;
struct JNITable {
 int(*PushLocalFrame)(JNIEnv*,int);
 bool(*ExceptionCheck)(JNIEnv*);
 void(*ExceptionClear)(JNIEnv*);
 jclass(*FindClass)(JNIEnv*,const char*);
 jmethodID(*GetStaticMethodID)(JNIEnv*,jclass,const char*,const char*);
 jstring(*NewStringUTF)(JNIEnv*,const char*);
 jstring(*CallStaticObjectMethod)(JNIEnv*,jclass,jmethodID,jstring);
 const char*(*GetStringUTFChars)(JNIEnv*,jstring,void*);
 void(*ReleaseStringUTFChars)(JNIEnv*,jstring,const char*);
 void(*PopLocalFrame)(JNIEnv*,void*);
 void(*CallStaticVoidMethod)(JNIEnv*,jclass,jmethodID);
};
static int consumeCalls=0,unmountCalls=0;
static std::string pendingEndpoint,pendingPath,inUse;
static bool failPush=false,failChars=false;
static int Push(JNIEnv*,int){return failPush?-1:0;}
static bool Exception(JNIEnv*){return false;}
static void Noop(JNIEnv*){}
static jclass Class(JNIEnv*,const char *name){assert(!strcmp(name,"ru/kurostreet/counterzombiemobile/CzmNet"));return name;}
static jmethodID Method(JNIEnv*,jclass,const char *name,const char*){return name;}
static jstring String(JNIEnv*,const char *s){return s;}
static jstring Consume(JNIEnv*,jclass,jmethodID m,jstring endpoint){
 assert(!strcmp(m,"serverResourcesMountPath"));consumeCalls++;
 if(pendingEndpoint!=endpoint)return "";
 static std::string result;result=pendingPath;inUse=pendingPath;pendingEndpoint.clear();pendingPath.clear();return result.c_str();
}
static const char *Chars(JNIEnv*,jstring s,void*){return failChars?nullptr:s;}
static void Release(JNIEnv*,jstring,const char*){}
static void Pop(JNIEnv*,void*){}
static void Unmounted(JNIEnv*,jclass,jmethodID m){assert(!strcmp(m,"serverResourcesUnmounted"));unmountCalls++;inUse.clear();}
static JNITable table={Push,Exception,Noop,Class,Method,String,Consume,Chars,Release,Pop,Unmounted};
static JNIEnv env=&table;
static JNIEnv *Android_GetNativeObject(const char *name){assert(!strcmp(name,"JNIEnv"));return &env;}
struct netadr_t {const char *address;};
static const char *NET_AdrToString(netadr_t adr){return adr.address;}
static string czm_resources_address;
static qboolean czm_resources_mounted;
static void CZM_ServerResourcesClear(void);
static int rejectedConnections=0;
static bool menuVisible=false;
static std::string loadingError;
static void CZM_Loading_SetError(const char *reason){loadingError=reason;}
static void CL_Disconnect(){rejectedConnections++;CZM_ServerResourcesClear();}
static void Cvar_Set(const char *name,const char *reason){assert(!strcmp(name,"czm_loading_error"));loadingError=reason;}
static void UI_SetActiveMenu(bool visible){menuVisible=visible;}
static int sentPackets=0;
'''


class ServerResourceMountTests(unittest.TestCase):
    def run_code(self, body, jni=False):
        filesystem = (ENGINE / "common/filesystem_engine.c").read_text()
        code = STUB + function(filesystem, "void FS_Rescan_f(") + "\n"
        code += function(filesystem, "qboolean FS_CzmSetServerResources(") + "\n"
        if jni:
            client = (ENGINE / "client/cl_main.c").read_text()
            self.assertEqual(client.count("if( !CZM_ServerResourcesBind( adr )) return;"), 3)
            code += JNI + function(client, "static qboolean CZM_ServerResourcesReject(") + "\n"
            code += function(client, "static qboolean CZM_ServerResourcesBind(") + "\n"
            # Signature has a forward declaration; select the actual definition.
            definition = client.index("static void CZM_ServerResourcesClear( void )\n{")
            code += function(client[definition:], "static void CZM_ServerResourcesClear(") + "\n"
            code += "static void SendHandshake(netadr_t adr){if(!CZM_ServerResourcesBind(adr))return;sentPackets++;}\n"
        with tempfile.TemporaryDirectory(prefix="czm-server-resource-mount-") as folder:
            p = Path(folder)
            (p / "main.cpp").write_text(code + body)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I" + str(ENGINE / "common"), str(p / "main.cpp"), "-o", str(p / "mount")], check=True)
            subprocess.run([str(p / "mount")], check=True)

    def test_server_switch_rescan_readonly_and_boundary_revocation(self):
        self.run_code(r'''
int main(){
 CZM_ResourceRoot(&fs_czm_resources,"/data/user/0/dev.gaming.czm/files/game");
 const char *a="/data/user/0/dev.gaming.czm/files/server-resources/survival/r1/files";
 const char *b="/data/user/0/dev.gaming.czm/files/server-resources/escape/r9/files";
 resource["bundled"]="base";resource[std::string(a)+"/"]="ZM model";resource[std::string(b)+"/"]="ZE model";
 FS_Rescan_f();assert(Find()=="base");
 assert(FS_CzmSetServerResources(a));assert(Find()=="ZM model");
 int saved=rescans;assert(FS_CzmSetServerResources(a));assert(rescans==saved);
 FS_Rescan_f();assert(Find()=="ZM model"&&paths.size()==2);
 assert(FS_CzmSetServerResources(b));assert(Find()=="ZE model"&&paths.size()==2);
 assert(writepath=="userdata/cstrike");
 assert(!FS_CzmSetServerResources(""));assert(Find()=="base");
 for(const char *bad:{"/tmp/x/r1/files","/data/user/0/dev.gaming.czm/files/server-resources/../r1/files",
   "/data/user/0/dev.gaming.czm/files/server-resources/p//files",
   "/data/user/0/dev.gaming.czm/files/server-resources/p/r1/files/config.cfg",
   "/data/user/0/dev.gaming.czm/files/server-resources/p/r1/files/",
   "/data/user/0/dev.gaming.czm/files/server-resources/p/r1/file",
   "/data/user/0/dev.gaming.czm/files/server-resources/p/r1/files2",
   "/data/user/0/dev.gaming.czm/files/server-resources/p/rev.1/files",
   "/data/user/0/dev.gaming.czm/files/server-resources/p/r1\\files",
   "/data/user/0/dev.gaming.czm/files/server-resources/p",
   "/data/user/0/dev.gaming.czm/files/server-resources/p/"}){
  assert(FS_CzmSetServerResources(a));assert(!FS_CzmSetServerResources(bad));assert(Find()=="base");
 }
 std::string prefix=fs_czm_resources.root;
 std::string maximal=prefix+std::string(64,'a')+"/"+std::string(64,'b')+"/files";
 assert(FS_CzmSetServerResources(maximal.c_str()));
 assert(!FS_CzmSetServerResources((prefix+std::string(65,'a')+"/r/files").c_str()));
 assert(writepath=="userdata/cstrike");
 CZM_ResourceRoot(&fs_czm_resources,"relative/game");assert(!FS_CzmSetServerResources(a));
 CZM_ResourceRoot(&fs_czm_resources,"/data/user/0/dev.gaming.czm/files/wrong");assert(!FS_CzmSetServerResources(a));
 assert(adds>0);return 0;
}''')

    def test_actual_endpoint_grant_consumed_once_and_unmount_preserves_next_grant(self):
        self.run_code(r'''
int main(){
 CZM_ResourceRoot(&fs_czm_resources,"/data/user/0/dev.gaming.czm/files/game");
 const char *a="/data/user/0/dev.gaming.czm/files/server-resources/survival/r1/files";
 const char *b="/data/user/0/dev.gaming.czm/files/server-resources/escape/r9/files";
 resource["bundled"]="base";resource[std::string(a)+"/"]="ZM";resource[std::string(b)+"/"]="ZE";
 pendingEndpoint="1.2.3.4:27016";pendingPath=a;
 SendHandshake({"1.2.3.4:27016"});assert(consumeCalls==1&&Find()=="ZM"&&inUse==a&&sentPackets==1);
 for(int retry=0;retry<4;retry++){assert(CZM_ServerResourcesBind({"1.2.3.4:27016"}));FS_Rescan_f();assert(Find()=="ZM");}
 assert(consumeCalls==1);
 pendingEndpoint="4.3.2.1:27015";pendingPath=b;
 CZM_ServerResourcesClear();assert(Find()=="base"&&unmountCalls==1&&inUse.empty());
 assert(pendingPath==b); // connect's own disconnect must retain its next pending grant
 assert(CZM_ServerResourcesBind({"4.3.2.1:27015"}));assert(consumeCalls==2&&Find()=="ZE");
 CZM_ServerResourcesClear();CZM_ServerResourcesClear();assert(unmountCalls==2);
 assert(CZM_ServerResourcesBind({"4.3.2.1:27015"}));assert(Find()=="base"&&inUse.empty()); // no reusable grant
 CZM_ServerResourcesClear();pendingEndpoint="1.2.3.4:27016";pendingPath="/tmp/evil/r/files";
 SendHandshake({"1.2.3.4:27016"});assert(Find()=="base"&&inUse.empty()&&unmountCalls==3);
 assert(sentPackets==1&&rejectedConnections==1&&menuVisible&&loadingError=="#czm_server_resources");
 // A root mismatch or failed JNI string copy releases the consumed Java lease too.
 pendingEndpoint="1.2.3.4:27016";pendingPath=a;failChars=true;
 SendHandshake({"1.2.3.4:27016"});assert(Find()=="base"&&inUse.empty()&&unmountCalls==4);
 assert(sentPackets==1&&rejectedConnections==2);
 failChars=false;failPush=true;SendHandshake({"1.2.3.4:27016"});
 assert(sentPackets==1&&rejectedConnections==3);failPush=false;
 assert(writepath=="userdata/cstrike");return 0;
}''', jni=True)


if __name__ == "__main__":
    unittest.main()
