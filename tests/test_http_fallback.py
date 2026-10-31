"""Execute the downloader's real C states with controlled DNS/socket outcomes."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
HTTP = ROOT / "3rdparty/xash3d-fwgs/engine/common/http/net_http_xash.c"


class HttpFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = HTTP.read_text()
        structs = source[source.index("typedef struct httpserver_s"):source.index("poolhandle_t http_mempool;")]
        names = [
            "static void HTTP_CloseIPv4Probe( httpfile_t *file )",
            "static void HTTP_CloseTransfer( httpfile_t *file )",
            "static qboolean HTTP_RetryIPv4( httpfile_t *file )",
            "static void HTTP_FreeFile( httpfile_t *file, qboolean error )",
            "static int HTTP_FileIPv4Fallback( httpfile_t *file )",
            "static int HTTP_FileFree( httpfile_t *file )",
            "static int HTTP_FileQueue( httpfile_t *file )",
            "static int HTTP_FileResolveNS( httpfile_t *file )",
            "static int HTTP_FileCreateSocket( httpfile_t *file )",
            "static int HTTP_FilePrepareRequest( httpfile_t *file )",
            "static int HTTP_FileWaitConnect( httpfile_t *file )",
            "static int HTTP_FileConnect( httpfile_t *file )",
            "static void HTTP_DownloadStatus( void )",
            "void HTTP_Run( void )",
            "static void HTTP_Clear_f( void )",
            "void HTTP_AddDownload( const char *path, int size, qboolean process, resource_t *res )",
            "qboolean HTTP_GetToMemory( const char *url, http_memory_cb_t cb, void *userdata )",
            "static qboolean HTTP_FileRedirect( httpfile_t *file, const char *location )",
        ]
        code = PREAMBLE + structs + STUBS
        code += "\n\n".join(function(source, name + "\n{") for name in names)
        code += SCENARIOS
        cls.temporary = tempfile.TemporaryDirectory(prefix="czm-http-fallback-")
        folder = Path(cls.temporary.name)
        cls.exe = folder / "check"
        (folder / "check.c").write_text(code)
        subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", str(folder / "check.c"), "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def check(self, scenario):
        subprocess.run([str(self.exe), scenario], check=True, timeout=5)

    def test_stalled_ipv6_reuses_the_same_secure_request_over_ipv4(self):
        self.check("stalled")

    def test_working_ipv6_wins_without_duplicate_request(self):
        self.check("ipv6-wins")

    def test_ipv6_only_and_failed_ipv4_keep_the_original_socket(self):
        self.check("ipv6-only")
        self.check("ipv4-fails")

    def test_async_dns_and_tcp_waits_are_bounded(self):
        self.check("dns-timeout")
        self.check("tcp-timeout")

    def test_old_async_address_is_consumed_before_resolving_ipv4(self):
        self.check("old-answer")

    def test_immediate_ipv6_connect_error_can_fall_back(self):
        self.check("connect-error")
        self.check("async-connect-error")

    def test_literals_active_responses_and_ipv4_are_not_restarted(self):
        self.check("guards")

    def test_cancel_and_redirect_close_the_probe(self):
        self.check("cancel")
        self.check("redirect")
        self.check("clear")

    def test_dns_queues_time_out_and_socket_setup_balances_counts(self):
        self.check("dns-queue")
        self.check("socket-fails")

    def test_status_excludes_credentials_query_strings_and_memory_requests(self):
        self.check("status")

    def test_stall_hint_waits_for_eight_seconds_and_retires_on_progress(self):
        menu = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
        code = "#include <cassert>\nenum { CZM_STAGE_DOWNLOAD = 3 };\n"
        code += function(menu, "static bool CZM_DownloadStalled(")
        code += r"""
int main() {
 assert(!CZM_DownloadStalled(1,3,0,0,100));
 assert(!CZM_DownloadStalled(1,3,0,0,8099));
 assert(CZM_DownloadStalled(1,3,0,0,8100));
 assert(!CZM_DownloadStalled(1,3,0,1,8101)); // even one byte is progress
 assert(!CZM_DownloadStalled(1,3,1,1,10000)); // next file
 assert(CZM_DownloadStalled(1,3,1,1,18000));
 assert(!CZM_DownloadStalled(2,3,1,1,18001)); // fresh connection
 assert(!CZM_DownloadStalled(2,4,1,1,28000)); // no download
 assert(!CZM_DownloadStalled(2,3,1,1,29000));
 assert(!CZM_DownloadStalled(2,3,1,1,100)); // clock restarted
 assert(CZM_DownloadStalled(2,3,1,1,8100));
}
"""
        folder = Path(self.temporary.name)
        (folder / "hint.cpp").write_text(code)
        subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                        str(folder / "hint.cpp"), "-o", str(folder / "hint")], check=True)
        subprocess.run([str(folder / "hint")], check=True, timeout=5)

    def test_download_and_memory_constructors_never_own_stdin(self):
        self.check("constructors")


PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <netinet/in.h>
typedef bool qboolean;
typedef unsigned char byte;
typedef int file_t;
typedef int tlsctx_t;
typedef int resource_t;
typedef char string[256];
typedef void (*http_memory_cb_t)(const char *, qboolean, const byte *, size_t, void *);
typedef enum { NET_EAI_OK, NET_EAI_AGAIN, NET_EAI_NONAME } net_gai_state_t;
#define MAX_SYSPATH 1024
#define MAX_HTTP_BUFFER_SIZE 65536
#define S_ERROR ""
#define XASH_ENGINE_NAME "Xash"
#define XASH_VERSION "test"
#define WSAEWOULDBLOCK EWOULDBLOCK
#define WSAEINPROGRESS EINPROGRESS
#define WSAGetLastError() errno
#define NET_IsSocketError(n) ((n) < 0)
#define Q_strchr strchr
#define Q_strrchr strrchr
#define Q_strpbrk strpbrk
#define Q_strcmp strcmp
#define Q_strnicmp strncasecmp
#define Q_strncpy bounded_copy
static void bounded_copy(char *out,const char *text,size_t size) { size_t count=strlen(text); if(count>=size)count=size-1;memcpy(out,text,count);out[count]=0; }
#define Q_snprintf snprintf
#define MSG_BigShort htons
#define COM_StringEmpty(s) (!(s)[0])
#define Con_Printf quiet_log
#define Con_Reportf quiet_log
static void quiet_log(const char *format, ...) {}
'''

STUBS = r'''
static int http_mempool;
static struct { float frametime; } host = { 1.0f };
typedef struct { float value; char string[1024]; } cvar_t;
static cvar_t czm_download_source, czm_download_file;
static void Cvar_DirectSet(cvar_t *var,const char *text) { snprintf(var->string,sizeof(var->string),"%s",text); }
static cvar_t http_timeout = {45,""},
 http_maxconnections = {5,""}, http_autoremove = {1,""},
 http_useragent = {0,"xash3d"}, http_max_redirects = {5,""};
static const char *g_buildcommit = "test";
static const char *Q_buildos(void) { return "Android"; }
static const char *Q_buildarch(void) { return "arm64"; }
static int Q_buildnum(void) { return 1; }
static double now = 100;
static double Platform_DoubleTime(void) { return now; }
static int dns_calls, dns_again, dns_wrong, dns_missing;
static net_gai_state_t NET_StringToSockaddr(const char *name, struct sockaddr_storage *addr, bool async, int family) {
 assert(name[0] && async); dns_calls++;
 if(dns_again) { dns_again--; return NET_EAI_AGAIN; }
 if(dns_missing) return NET_EAI_NONAME;
 addr->ss_family = dns_wrong ? AF_INET6 : family == AF_UNSPEC ? AF_INET6 : AF_INET;
 dns_wrong = 0; return NET_EAI_OK;
}
static int new_fd=70, sockets, closed[128], ready[128], errors[128], fail_connect[128], fail_nonblock;
static int fake_socket(int family, int kind, int protocol) {
 assert(family==AF_INET || family==AF_INET6); assert(kind==SOCK_STREAM && protocol==IPPROTO_TCP);
 sockets++; return new_fd++;
}
static int fake_close(int fd) { assert(fd>0 && fd<128); closed[fd]++; return 0; }
static bool NET_MakeSocketNonBlocking(int fd) { return !fail_nonblock; }
static int fake_connect(int fd, const struct sockaddr *addr, socklen_t len) {
 assert(addr->sa_family==AF_INET || addr->sa_family==AF_INET6);
 assert(len>0); errno=fail_connect[fd] ? ENETUNREACH : EINPROGRESS; return -1;
}
static int fake_select(int n, fd_set *readfds, fd_set *writefds, fd_set *exceptfds, struct timeval *timeout) {
 assert(!readfds && timeout->tv_sec==0 && timeout->tv_usec==0); int count=0;
 for(int fd=0;fd<n;fd++) if(FD_ISSET(fd,writefds)) {
  if(ready[fd]) count++; else {FD_CLR(fd,writefds);FD_CLR(fd,exceptfds);}
 }
 return count;
}
static int fake_getsockopt(int fd,int level,int opt,char *value,socklen_t *len) {
 assert(level==SOL_SOCKET && opt==SO_ERROR && *len==sizeof(int)); *(int *)value=errors[fd]; errors[fd]=0; return 0;
}
#define socket(f,k,p) fake_socket(f,k,p)
#define closesocket fake_close
#define connect fake_connect
#define select fake_select
#define getsockopt fake_getsockopt
static socklen_t NET_SockAddrLen(const struct sockaddr_storage *addr) { return addr->ss_family==AF_INET6?sizeof(struct sockaddr_in6):sizeof(struct sockaddr_in); }
static const char *NET_ErrorString(void) { return "test"; }
static void *Mem_Calloc(int pool,size_t length) { return calloc(1,length); }
static void Mem_Free(void *ptr) { free(ptr); }
static int tls_freed, tls_created, file_closed;
static void HTTP_TlsFree(tlsctx_t *tls) { assert(tls); tls_freed++; }
static tlsctx_t *HTTP_TlsNew(int fd,const char *host) { static tlsctx_t tls; assert(fd==70 && !strcmp(host,"dl.example")); tls_created++; return &tls; }
static void FS_Close(file_t *file) { assert(file); file_closed++; }
static void FS_AllowDirectPaths(bool allow) {}
static void FS_Delete(const char *path) {}
static void FS_Rename(const char *from,const char *to) {}
static void COM_DownloadCachePath(char *out,size_t size,const char *path,bool incomplete) { snprintf(out,size,"%s",path); }
static bool COM_CheckNastyPath(const char *path) { return false; }
static bool Host_IsDedicated(void) { return false; }
static void Cvar_SetValue(const char *name,float value) {}
static void HTTP_AutoClean(void) {}
static int seek_file(file_t *file,long offset,int origin) { return 0; }
static struct {int (*Seek)(file_t *,long,int);} g_fsapi = {seek_file};
static httpserver_t *HTTP_ParseURL(const char *url,bool full) {
 httpserver_t *server=calloc(1,sizeof(*server)); strcpy(server->host,"redirect.example");
 strcpy(server->path,"/maps/test.bsp"); server->secure=!strncmp(url,"https:",6); server->port=443; return server;
}
static int HTTP_FileFree(httpfile_t *file);
static int HTTP_FileConnect(httpfile_t *file);
static int HTTP_FilePrepareRequest(httpfile_t *file);
static int HTTP_FileCreateSocket(httpfile_t *file);
static int HTTP_FileQueue(httpfile_t *file);
static int HTTP_FileResolveNS(httpfile_t *file);
static int HTTP_FileSendRequest(httpfile_t *file) { return 0; }
static int HTTP_FileTlsHandshake(httpfile_t *file) { return 0; }
static int idle(httpfile_t *file) { file->blocktime+=host.frametime; return 0; }
static int respond(httpfile_t *file) { file->got_response=true; return 0; }
'''

SCENARIOS = r'''
static void tick(void) { now+=1; HTTP_Run(); }
static void init(httpfile_t *file,httpserver_t *server) {
 memset(file,0,sizeof(*file)); memset(server,0,sizeof(*server));
 strcpy(server->host,"dl.example"); strcpy(server->path,"/cstrike/"); server->port=443;server->secure=true;
 server->resolved=true;server->addr.ss_family=AF_INET6;
 file->server=server;file->addr=server->addr;file->socket=20;file->ipv4_socket=-1;
 file->buf=calloc(1,MAX_HTTP_BUFFER_SIZE+1);strcpy(file->path,"maps/test.bsp");file->size=99;
 file->reported_size=99;file->pfn_process=idle;http.first_file=file;http.active_count=1;
}
int main(int argc,char **argv) {
 assert(argc==2);const char *scenario=argv[1];httpfile_t f;httpserver_t s;init(&f,&s);
 if(!strcmp(scenario,"stalled")) {
  static tlsctx_t old_tls;f.tls=&old_tls;dns_again=1;
  for(int n=0;n<3;n++){tick();}assert(sockets==0 && f.socket==20);
  tick();assert(dns_calls==1 && sockets==0);tick();assert(sockets==1 && f.socket==20 && !closed[20]);
  ready[70]=1;tick();assert(f.socket==70 && f.ipv4_socket==-1 && closed[20]==1 && !closed[70]);
  assert(tls_freed==1 && http.active_count==1 && f.buf && f.blocktime==0 && f.size==99);
  assert(s.addr.ss_family==AF_INET && f.addr.ss_family==AF_INET && s.secure && s.port==443);
  assert(!strcmp(f.path,"maps/test.bsp") && f.pfn_process==HTTP_FilePrepareRequest);
  tick();assert(tls_created==1 && strstr(f.buf,"GET /cstrike/maps/test.bsp HTTP/1.1\r\n") && strstr(f.buf,"Host: dl.example:443"));
  for(int n=0;n<10;n++){tick();}assert(sockets==1 && dns_calls==2);
 } else if(!strcmp(scenario,"ipv6-wins")) {
  f.blocktime=3;tick();assert(f.ipv4_socket==70 && !closed[20]);
  f.pfn_process=respond;ready[70]=1;tick();assert(f.socket==20 && closed[70]==1 && !closed[20] && tls_created==0);
 } else if(!strcmp(scenario,"ipv6-only") || !strcmp(scenario,"ipv4-fails")) {
  if(!strcmp(scenario,"ipv6-only"))dns_missing=1;else {ready[70]=1;errors[70]=ECONNREFUSED;}
  f.blocktime=3;tick();assert(f.ipv4_done && f.socket==20 && !closed[20]);
  int was=dns_calls;for(int n=0;n<10;n++){tick();}assert(f.socket==20 && dns_calls==was);
  f.pfn_process=respond;tick();assert(f.socket==20 && f.got_response);
 } else if(!strcmp(scenario,"dns-timeout") || !strcmp(scenario,"tcp-timeout")) {
  if(!strcmp(scenario,"dns-timeout"))dns_again=100;
  f.blocktime=3;tick();assert(!f.ipv4_done);
  for(int n=0;n<5;n++){tick();}assert(f.ipv4_done && f.socket==20 && !closed[20]);
  if(!strcmp(scenario,"tcp-timeout"))assert(closed[70]==1);
  f.blocktime=45;tick();assert(closed[20]==1 && http.active_count==0 && f.server==NULL);
 } else if(!strcmp(scenario,"old-answer")) {
  dns_wrong=1;f.blocktime=3;tick();assert(sockets==0 && f.socket==20);
  ready[70]=1;tick();assert(f.socket==70 && dns_calls==2);
 } else if(!strcmp(scenario,"connect-error") || !strcmp(scenario,"async-connect-error")) {
  if(!strcmp(scenario,"connect-error")){fail_connect[20]=1;f.pfn_process=HTTP_FileConnect;}
  else {ready[20]=1;errors[20]=ENETUNREACH;f.pfn_process=HTTP_FileWaitConnect;}
  dns_again=1;tick();assert(f.pfn_process==HTTP_FileIPv4Fallback && f.socket==20);
  ready[70]=1;tick();assert(f.socket==70 && closed[20]==1 && f.pfn_process==HTTP_FilePrepareRequest);
 } else if(!strcmp(scenario,"guards")) {
  f.got_response=true;assert(!HTTP_RetryIPv4(&f));f.got_response=false;f.downloaded=1;assert(!HTTP_RetryIPv4(&f));
  f.downloaded=0;strcpy(s.host,"2001:db8::1");assert(!HTTP_RetryIPv4(&f));strcpy(s.host,"dl.example");
  f.addr.ss_family=AF_INET;assert(!HTTP_RetryIPv4(&f));assert(sockets==0 && dns_calls==0);
 } else if(!strcmp(scenario,"cancel")) {
  f.blocktime=3;tick();assert(f.ipv4_socket==70);HTTP_FreeFile(&f,true);
  assert(closed[20]==1 && closed[70]==1 && !f.buf && http.active_count==0);
 } else if(!strcmp(scenario,"clear")) {
  httpfile_t *heap=malloc(sizeof(f));*heap=f;http.first_file=heap;heap->blocktime=3;
  tick();assert(heap->ipv4_socket==70);HTTP_Clear_f();
  assert(closed[20]==1 && closed[70]==1 && http.first_file==NULL && http.active_count==0);
  assert(!czm_download_source.string[0] && !czm_download_file.string[0]);
 } else if(!strcmp(scenario,"status")) {
  strcpy(s.host,"account@dl.example");strcpy(f.path,"maps/test.bsp?token=secret#fragment");
  f.blockreason="receiving header";tick();
  assert(strstr(czm_download_source.string,"HTTPS IPv6 dl.example:443 - receiving header"));
  assert(!strstr(czm_download_source.string,"account") && !strstr(czm_download_source.string,"secret"));
  assert(!strcmp(czm_download_file.string,"maps/test.bsp"));
  f.to_memory=true;tick();assert(!czm_download_source.string[0] && !czm_download_file.string[0]);
 } else if(!strcmp(scenario,"redirect")) {
  f.blocktime=3;tick();assert(f.ipv4_socket==70);
  assert(!HTTP_FileRedirect(&f,"http://redirect.example/test"));assert(f.socket==20 && !closed[70]);
  assert(HTTP_FileRedirect(&f,"https://redirect.example/test"));assert(closed[20]==1 && closed[70]==1);
  assert(f.ipv4_socket==-1 && !f.ipv4_done && f.ipv4_started==0 && f.server->secure);
  assert(f.pfn_process==HTTP_FileResolveNS && f.blocktime==0 && http.active_count==0);
 } else if(!strcmp(scenario,"dns-queue")) {
  HTTP_CloseTransfer(&f);s.resolved=false;f.pfn_process=HTTP_FileResolveNS;dns_again=1000;
  httpfile_t other={0};other.socket=other.ipv4_socket=-1;other.server=&s;other.pfn_process=HTTP_FileResolveNS;f.next=&other;
  for(int n=0;n<46;n++){tick();}assert(f.server==NULL && other.server==NULL && !http.active_count);
 } else if(!strcmp(scenario,"socket-fails")) {
  HTTP_CloseTransfer(&f);f.pfn_process=HTTP_FileCreateSocket;fail_nonblock=1;tick();
  assert(http.active_count==0 && closed[70]==1 && f.server==NULL);
 } else if(!strcmp(scenario,"constructors")) {
  http.first_server=&s;HTTP_AddDownload("maps/test.bsp",99,true,NULL);httpfile_t *download=http.first_file;
  assert(download->socket==-1 && download->ipv4_socket==-1);HTTP_FreeFile(download,true);assert(!closed[0]);
  assert(HTTP_GetToMemory("https://example/test",NULL,NULL));httpfile_t *memory=http.first_file;
  assert(memory->socket==-1 && memory->ipv4_socket==-1);HTTP_FreeFile(memory,true);assert(!closed[0]);
 } else assert(!"unknown scenario");
 return 0;
}
'''


if __name__ == "__main__":
    unittest.main()
