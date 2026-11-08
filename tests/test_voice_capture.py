"""Run the patched microphone lifecycle, PCM encoding paths and touch anchors."""
from pathlib import Path
import re
import unittest
from test_loading_errors import function
from test_combat_controls import build

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs/engine"


def capture_source(*extra):
    voice = (ENGINE / "client/sound/voice.c").read_text()
    cvars = (ENGINE / "common/cvar.c").read_text()
    declarations = "\n".join(re.findall(r"^.*CVAR_DEFINE_AUTO\(.*;$", voice, re.M))
    names = ["static void Voice_CzmSetValue", "static void Voice_CzmMeter(",
             "qboolean Voice_IsRecording", "void Voice_RecordStop", "void Voice_RecordStart",
             "static void Voice_CzmMeterFrame", "void Voice_RegisterCvars"]
    return (CAPTURE_STUB + function(cvars, "static qboolean Cvar_CanSet") + "\n"
            + function(cvars, "void Cvar_DirectFullSet") + "\n" + declarations
            + "\nstatic double czm_voice_sample_time;\n"
            + "\n".join(function(voice, name) for name in names + list(extra)))


class VoiceCaptureTests(unittest.TestCase):
    def test_readonly_capture_state_pcm_and_failed_repeated_holds(self):
        build(capture_source() + r'''
int main(){
Voice_RegisterCvars();
for(auto p:{&czm_voice_held,&czm_voice_recording,&czm_voice_level}){
 assert(registered.count(p->name)&&p->flags==(FCVAR_READ_ONLY|FCVAR_PRIVILEGED));
 assert(!Cvar_CanSet(p));
}
errors=0;int16_t speech[]={2000,-2000,2000,-2000};int16_t silence[]={0,0,0,0};
// Missing codec initialization and failed hardware both retain the held UI state.
Voice_RecordStart();assert(czm_voice_held.value==1&&!czm_voice_recording.value);
Voice_CzmMeter(speech,4);assert(!czm_voice_level.value);
Voice_RecordStop();assert(!czm_voice_held.value);
voice.initialized=true;voice.device_opened=true;captureAvailable=false;
Voice_RecordStart();assert(czm_voice_held.value==1&&!czm_voice_recording.value);
Voice_RecordStop();assert(!czm_voice_held.value&&!czm_voice_level.value);
captureAvailable=true;
for(int i=0;i<25;i++){
 host.realtime=i+1;Voice_RecordStart();
 assert(czm_voice_held.value==1&&czm_voice_recording.value==1);
 Voice_CzmMeter(speech,4);assert(czm_voice_level.value>.30&&czm_voice_level.value<.31);
 Voice_CzmMeter(silence,4);assert(czm_voice_level.value==0);
 int16_t noise[]={20,-20,20,-20};Voice_CzmMeter(noise,4);assert(czm_voice_level.value==0);
 int16_t loud[]={32767,-32768};Voice_CzmMeter(loud,2);assert(czm_voice_level.value==1);
 Voice_CzmMeter(speech,0);assert(czm_voice_level.value==0);
 Voice_CzmMeter(speech,4);Voice_RecordStop();
 assert(!czm_voice_held.value&&!czm_voice_recording.value&&!czm_voice_level.value);
 Voice_CzmMeter(speech,4);assert(!czm_voice_level.value); // no stale callback after release
}
// A prerecorded test WAV cannot claim live microphone capture.
voice_inputfromfile.value=1;loadFile=true;Voice_RecordStart();
assert(Voice_IsRecording()&&czm_voice_held.value==1&&!czm_voice_recording.value);
Voice_CzmMeter(speech,4);assert(!czm_voice_level.value);Voice_RecordStop();
assert(!voice.input_file&&freedFiles==1);
assert(errors==0);
for(auto p:{&czm_voice_held,&czm_voice_recording,&czm_voice_level})assert(p->flags==(FCVAR_READ_ONLY|FCVAR_PRIVILEGED));
return 0;}
''')

    def test_stale_audio_menu_disconnect_and_release_after_failed_start(self):
        source = capture_source("void Voice_Disconnect")
        sound = (ENGINE / "client/sound/s_main.c").read_text()
        build(source + function(sound, "static void S_VoiceRecordStop_f") + r'''
int main(){
voice.initialized=voice.device_opened=true;int16_t speech[]={4000,-4000};
host.realtime=10;Voice_RecordStart();Voice_CzmMeter(speech,2);
host.realtime=10.1;Voice_CzmMeterFrame();assert(czm_voice_level.value>0);
host.realtime=10.2;Voice_CzmMeterFrame();assert(czm_voice_level.value==0&&czm_voice_held.value==1);
cls.key_dest=key_menu;Voice_CzmMeterFrame();assert(!czm_voice_held.value&&!Voice_IsRecording());
cls.key_dest=key_game;Voice_RecordStart();cls.state=0;Voice_CzmMeterFrame();
assert(!czm_voice_held.value&&!czm_voice_recording.value);
cls.state=ca_active;Voice_RecordStart();host.status=HOST_NOFOCUS;Voice_CzmMeterFrame();
assert(!czm_voice_held.value&&!Voice_IsRecording());host.status=HOST_FRAME;
captureAvailable=false;Voice_RecordStart();assert(czm_voice_held.value==1);
S_VoiceRecordStop_f();assert(!czm_voice_held.value&&datagrams==0);
captureAvailable=true;Voice_RecordStart();S_VoiceRecordStop_f();
assert(!czm_voice_held.value&&!Voice_IsRecording()&&datagrams==1);
// Actual disconnect clears capture and cvars before the next server connection.
Voice_RecordStart();Voice_CzmMeter(speech,2);Voice_Disconnect();
assert(!czm_voice_held.value&&!czm_voice_recording.value&&!czm_voice_level.value&&!voice.device_opened);
voice.device_opened=true;Voice_RecordStart();assert(czm_voice_recording.value==1&&!czm_voice_level.value);Voice_RecordStop();
// Releasing after disconnection still clears state without submitting stale voice.
Voice_RecordStart();cls.state=0;S_VoiceRecordStop_f();assert(!czm_voice_held.value&&datagrams==1);
return 0;}
''')

    def test_both_codecs_meter_real_pcm_before_gain_and_include_silence(self):
        build(capture_source("static uint Voice_GetOpusCompressedData", "static uint Voice_GetGSCompressedData") + r'''
int main(){
voice.initialized=voice.device_opened=true;voice.frame_size=4;voice.width=2;Voice_RecordStart();
byte out[100]={};uint frames=0;
for(int codec=0;codec<2;codec++){
 int16_t speech[]={2000,-2000,2000,-2000};memcpy(voice.input_buffer,speech,sizeof(speech));
 voice.input_buffer_pos=sizeof(speech);frames=0;gainCalls=0;host.realtime++;
 uint bytes=codec?Voice_GetGSCompressedData(out,sizeof(out),&frames):Voice_GetOpusCompressedData(out,sizeof(out),&frames);
 assert(bytes>0&&frames==1&&gainCalls==1&&voice.input_buffer_pos==0);
 // Our gain stub zeroes the samples; a nonzero meter proves it observed raw capture.
 assert(czm_voice_level.value>.30&&czm_voice_level.value<.31);
 memset(voice.input_buffer,0,sizeof(speech));voice.input_buffer_pos=sizeof(speech);frames=0;
 if(codec)Voice_GetGSCompressedData(out,sizeof(out),&frames);else Voice_GetOpusCompressedData(out,sizeof(out),&frames);
 assert(czm_voice_level.value==0&&voice.input_buffer_pos==0);
 if(codec)assert(frames==0); // GoldSrc drops silent codec frames, meter still resets.
}
return 0;}
''')

    def test_focus_loss_stops_capture_before_android_can_skip_idle(self):
        for backend, signature in (("sdl2", "static void SDLash_ActiveEvent( int gain )"),
                                   ("sdl3", "static void SDLash_ActiveEvent( qboolean focus )")):
            with self.subTest(backend=backend):
                source = (ENGINE / f"platform/{backend}/host_{backend}.c").read_text()
                sound = (ENGINE / "client/sound/s_main.c").read_text()
                build(capture_source() + function(sound, "static void S_VoiceRecordStart_f") + FOCUS_STUB + function(source, signature) + r'''
int main(){voice.initialized=voice.device_opened=true;
Voice_RecordStart();assert(czm_voice_recording.value==1);SDLash_ActiveEvent(false);
assert(!Voice_IsRecording()&&!czm_voice_held.value&&host.status==HOST_NOFOCUS);
// Cbuf executes queued +voicerecord after event processing; it must not reopen capture.
S_VoiceRecordStart_f();assert(!Voice_IsRecording()&&!czm_voice_held.value);
SDLash_ActiveEvent(true);assert(host.status==HOST_FRAME&&!czm_voice_held.value);
// A denied/missing microphone must also lose its held state on backgrounding.
captureAvailable=false;Voice_RecordStart();assert(czm_voice_held.value==1);
SDLash_ActiveEvent(false);assert(!czm_voice_held.value);
cls.key_dest=key_menu;host.status=HOST_FRAME;captureAvailable=true;
S_VoiceRecordStart_f();assert(!Voice_IsRecording()&&!czm_voice_held.value);return 0;}
''')

    def test_mic_anchors_follow_layout_release_hidden_and_cancel_holds(self):
        touch = (ENGINE / "client/input/in_touch.c").read_text()
        code = "\n".join(function(touch, name) for name in (
            "static int Touch_CzmFortSlot", "static void Touch_CzmPublishAnchors", "static void Touch_CzmCancelSkillHolds( void )\n{"))
        build(TOUCH_STUB + code + r'''
int main(){
touch_button_t mic;strcpy(mic.command,"+voicerecord");mic.x1=.8;mic.y1=.4;mic.x2=.9;mic.y2=.6;
touch.list_user.first=&mic;Touch_CzmPublishAnchors();int b[16]={};
assert(sscanf(czm_touch_anchors.string,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d",b,b+1,b+2,b+3,b+4,b+5,b+6,b+7,b+8,b+9,b+10,b+11,b+12,b+13,b+14,b+15)==16);
assert(b[0]==0&&b[12]==800&&b[13]==200&&b[14]==900&&b[15]==300);
mic.x1=.2;mic.x2=.3;Touch_CzmPublishAnchors();assert(std::string(czm_touch_anchors.string).find("200 200 300 300")!=std::string::npos);
mic.finger=7;mic.visible=false;Touch_CzmPublishAnchors();assert(mic.finger==-1&&commands.back()=="-voicerecord\n");
int count=commands.size();Touch_CzmPublishAnchors();assert(commands.size()==count);
mic.visible=true;mic.finger=4;Touch_CzmCancelSkillHolds();assert(mic.finger==-1&&commands.back()=="-voicerecord\n");
mic.latched=true;Touch_CzmCancelSkillHolds();assert(!mic.latched&&commands.size()==count+2);
Touch_CzmCancelSkillHolds();assert(commands.size()==count+2);return 0;}
''')


CAPTURE_STUB = r'''
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cstdint>
#include <set>
#include <string>
typedef bool qboolean;typedef unsigned uint;typedef unsigned char byte;typedef long fs_offset_t;
enum{FCVAR_PRIVILEGED=1<<10,FCVAR_READ_ONLY=1<<17,FCVAR_SERVER=4,FCVAR_PROTECTED=32,
FCVAR_CHEAT=256,FCVAR_LATCH=1<<16,FCVAR_ARCHIVE=1,ca_active=2,key_game,key_menu,HOST_FRAME,HOST_NOFOCUS,
MAX_CLIENTS=32,VOICE_LOOPBACK_INDEX=-2,VOICE_LOCALCLIENT_INDEX=0,VOICE_PCM_CHANNELS=1,SOUND_RESAMPLE=1,GS_DEFAULT_FRAME_SIZE=4};
#define FBitSet(v,b) ((v)&(b))
#define SetBits(v,b) ((v)|=(b))
#define Q_snprintf snprintf
#define Q_strcmp strcmp
#define Q_strlen strlen
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
#define Q_atof atof
#define Q_min(a,b) ((a)<(b)?(a):(b))
#define bound(a,x,b) ((x)<(a)?(a):((x)>(b)?(b):(x)))
#define Mem_Realloc(pool,ptr,n) ((char*)realloc(ptr,n))
#define S_ERROR ""
struct convar_t{const char*name;char*string;float value;unsigned flags;};
#define CVAR_DEFINE_AUTO(name,value,flags,description) convar_t name={#name,strdup(value),float(atof(value)),flags}
struct {double realtime=1,force_draw_version_time=0;bool allow_cheats=false;int status=HOST_FRAME;}host;
struct {int state=ca_active,key_dest=key_game;bool initialized=true;}cls;
struct Sound{uint size=10000;byte buffer[10000];};Sound fileSound;
struct {bool initialized=false,device_opened=false,is_recording=false,goldsrc=false;
struct{bool talking_ack=false;}local;Sound*input_file=nullptr;
uint input_buffer_pos=0,input_file_pos=0,samplerate=16000,width=2,frame_size=4;
double start_time=0;byte input_buffer[32000];void*encoder=nullptr,*gs_encoder=nullptr;}voice;
int cvar_pool=0,errors=0,freedFiles=0,datagrams=0,gainCalls=0;
bool captureAvailable=true,loadFile=false;std::set<std::string> registered;
bool SV_Active(){return false;}bool CL_Active(){return true;}
void Con_Printf(const char*,...){errors++;}void Cvar_Changed(convar_t*){}
void Cvar_RegisterVariable(convar_t*p){registered.insert(p->name);}
bool VoiceCapture_Activate(bool active){return active?captureAvailable:true;}
bool VoiceCapture_Lock(bool){return true;}
void VoiceCapture_Shutdown(){}void Voice_ShutdownGoldSrcMode(){}void Voice_ShutdownOpusCustomMode(){}
void Voice_Status(int,bool){}void CL_AddVoiceToDatagram(){datagrams++;}
void FS_FreeSound(Sound*){freedFiles++;}Sound*FS_LoadSound(const char*,void*,int){return loadFile?&fileSound:nullptr;}
void Sound_Process(Sound**,uint,uint,int,int){}double Platform_DoubleTime(){return host.realtime;}
void Voice_ApplyGainAdjust(int16_t*p,int n,float){gainCalls++;memset(p,0,n*sizeof(*p));}
int opus_custom_encode(void*,const int16_t*,int,byte*,uint){return 4;}
int opus_encode(void*,const int16_t*,int,byte*,uint){return 4;}
const char*opus_strerror(int){return "error";}uint16_t LittleShort(uint16_t n){return n;}
'''

FOCUS_STUB = r'''
enum{FORCE_DRAW_VERSION_TIME=2,WINDOW_MODE_FULLSCREEN=1};typedef int window_mode_t;
struct{float value=0;}vid_fullscreen;
void IN_ActivateMouse(){}void IN_DeactivateMouse(){}void Key_ClearStates(){}
void Con_CzmMatchChatReset(){} // match-chat lifecycle is exercised in test_match_chat_transport
void VID_SetMode(){}void VID_RestoreScreenResolution(window_mode_t){}
'''

TOUCH_STUB = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define Q_strcmp strcmp
#define Q_snprintf snprintf
#define TO_SCRN_X(x) int((x)*1000)
#define TO_SCRN_Y(y) int((y)*500)
struct touch_button_t{char command[256]={};float x1,y1,x2,y2;int finger=-1;bool latched=false,visible=true;touch_button_t*next=nullptr;};
struct{struct{touch_button_t*first=nullptr;}list_user;}touch;
struct Cvar{std::string text;const char*string="";}czm_touch_anchors;
int Touch_CzmSkillSlot(const char*){return -1;}bool Touch_IsVisible(touch_button_t*b){return b->visible;}
std::vector<std::string>commands;
void Touch_AddButtonCommand(touch_button_t*,const char*s){commands.push_back(s);}
void Cvar_DirectFullSet(Cvar*p,const char*s,unsigned flags){assert(flags==0);p->text=s;p->string=p->text.c_str();}
'''


if __name__ == '__main__':
    unittest.main()
