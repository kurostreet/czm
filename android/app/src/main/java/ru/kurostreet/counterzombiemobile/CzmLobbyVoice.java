package ru.kurostreet.counterzombiemobile;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.SystemClock;
import android.util.Log;
import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import org.java_websocket.drafts.Draft_6455;
import org.libsdl.app.SDLActivity;
import org.json.JSONObject;
import java.net.URI;
import java.nio.ByteBuffer;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** Temporary, authenticated lobby voice. Audio stays in memory. G.711 / 16 kHz. */
public final class CzmLobbyVoice {
    private static final String TAG="CzmLobbyVoice";
    private static final int RATE=16000,SAMPLES=320,FRAME=321,RXFRAME=325;
    private static final Object LOCK=new Object();
    private static final CzmLobbyMicState mic=new CzmLobbyMicState();
    private static final Map<Integer,ArrayDeque<byte[]>> received=new HashMap<>();
    private static final Set<Integer> muted=new HashSet<>();
    private static final Map<Integer,Long> talking=new HashMap<>();
    private static final Map<Integer,CzmLobbyAudio.Signal> signals=new HashMap<>();
    private static final Map<Integer,Boolean> enabledPeers=new HashMap<>();
    private static final Map<Integer,Integer> peerSensitivity=new HashMap<>();
    private static CzmLobbyAudio.Signal localSignal=new CzmLobbyAudio.Signal();
    private static int localPlayer;
    private static long localTalkingUntil;
    private static boolean testing;
    private static WebSocketClient connection;
    private static String activeUrl="",activeKey="";
    private static long lastAttempt;
    private static boolean alive;
    private static int status;
    private static AudioRecord recorder;
    private static AudioTrack speaker;
    private CzmLobbyVoice(){}

    public static int state(){synchronized(LOCK){return status;}}
    public static boolean microphoneOn(){synchronized(LOCK){return mic.wanted();}}
    public static boolean microphoneEnabled(int player){synchronized(LOCK){
        if(player==localPlayer)return mic.wanted()&&!testing;
        Boolean value=enabledPeers.get(player);return value==null||value;
    }}
    private static void announceMic(){
        final WebSocketClient target;final boolean enabled;
        synchronized(LOCK){if(status!=2||!alive)return;target=connection;enabled=mic.wanted()&&!testing;}
        if(target!=null&&target.isOpen())try{target.send("{\"type\":\"mic\",\"enabled\":"+enabled+",\"sensitivity\":"+CzmLobbyAudio.sensitivity+"}");}catch(RuntimeException ignored){}
    }
    static void sensitivityChanged(){announceMic();}
    public static boolean speaking(int id){synchronized(LOCK){
        if(id==localPlayer)return !testing&&mic.wanted()&&status==2&&SystemClock.elapsedRealtime()<localTalkingUntil;
        Long last=talking.get(id);return last!=null&&SystemClock.elapsedRealtime()<last;
    }}
    public static boolean locallyMuted(int id){synchronized(LOCK){return muted.contains(id);}}
    public static void mutePlayer(int id,boolean value){synchronized(LOCK){if(value){muted.add(id);talking.remove(id);signals.remove(id);}else muted.remove(id);}}
    static boolean testAvailable(){synchronized(LOCK){return mic.foreground()&&!activeUrl.isEmpty();}}
    static boolean beginTest(){
        AudioRecord old;
        synchronized(LOCK){if(!mic.foreground()||activeUrl.isEmpty())return false;testing=true;localTalkingUntil=0;old=recorder;recorder=null;}
        releaseCapture(old);announceMic();return true;
    }
    static void endTest(){synchronized(LOCK){testing=false;localSignal=new CzmLobbyAudio.Signal();localTalkingUntil=0;}announceMic();startRecorder();}
    private static Activity activity(){Context c=SDLActivity.getContext();return c instanceof Activity?(Activity)c:null;}
    private static boolean micAllowed(){
        Context c=SDLActivity.getContext();
        return c!=null&&(Build.VERSION.SDK_INT<23||c.checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED);
    }
    public static void setMic(boolean on){
        final boolean request;
        AudioRecord old=null;
        synchronized(LOCK){
            request=mic.request(on,micAllowed());
            if(!on){old=recorder;recorder=null;localTalkingUntil=0;}
        }
        releaseCapture(old);
        announceMic();
        if(request){
            Activity a=activity();
            if(a!=null&&Build.VERSION.SDK_INT>=23)a.runOnUiThread(()->{
                synchronized(LOCK){if(!mic.foreground()||activeUrl.isEmpty())return;}
                a.requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},1724);
            });
        }else if(on)startRecorder();
    }
    public static void permissionResult(boolean granted){
        if(CzmLobbyMicTest.permissionResult(granted))return;
        synchronized(LOCK){mic.permissionResult(granted);}
        announceMic();
        if(granted)startRecorder();
    }
    public static void resume(){synchronized(LOCK){mic.foreground(true);}CzmLobbyMicTest.resume();}
    public static void pause(){
        CzmLobbyMicTest.pause();
        boolean keepTest=CzmLobbyMicTest.opened();
        Transport old;
        synchronized(LOCK){mic.foreground(false);if(!keepTest)testing=false;old=detachTransport();status=activeUrl.isEmpty()?0:3;}
        release(old);
    }
    private static final class Transport {
        final WebSocketClient socket;final AudioRecord capture;final AudioTrack playback;
        Transport(WebSocketClient s,AudioRecord r,AudioTrack t){socket=s;capture=r;playback=t;}
    }
    // Detach under the same lock as the socket identity check. A callback from
    // an old socket must never release a newly reconnected recorder/speaker.
    private static Transport detachTransport(){
        Transport old=new Transport(connection,recorder,speaker);
        connection=null;recorder=null;speaker=null;alive=false;
        received.clear();talking.clear();signals.clear();enabledPeers.clear();peerSensitivity.clear();localTalkingUntil=0;localSignal=new CzmLobbyAudio.Signal();return old;
    }
    private static void releaseCapture(AudioRecord r){
        CzmLobbyAudio.release(r);
    }
    private static void release(Transport old){
        if(old.socket!=null)try{old.socket.close();}catch(Exception ignored){}
        releaseCapture(old.capture);
        if(old.playback!=null){try{old.playback.pause();old.playback.flush();old.playback.release();}catch(Exception ignored){}}
    }
    public static void stop(){
        CzmLobbyMicTest.cancel();
        Transport old;
        synchronized(LOCK){testing=false;old=detachTransport();activeUrl="";activeKey="";status=0;mic.endSession();muted.clear();}
        release(old);
    }
    public static void start(String url,String key,int player){synchronized(LOCK){localPlayer=player;}start(url,key);}
    public static void start(String url,String key){
        if(url==null||key==null||key.isEmpty()||!CzmAccount.serviceUrl(url))return;
        final String credential=CzmAccount.lobbyVoiceKey(url);
        if(credential.isEmpty()){stop();return;}
        final URI uri;
        try{
            URI source=new URI(url);
            if(!"https".equalsIgnoreCase(source.getScheme())||source.getHost()==null||source.getRawQuery()!=null||source.getRawFragment()!=null)return;
            uri=new URI("wss",null,source.getHost(),source.getPort(),source.getRawPath(),null,null);
        }catch(Exception ignored){return;}
        final Transport old;final WebSocketClient next;final boolean changed;
        synchronized(LOCK){
            if(!mic.foreground())return;
            boolean same=activeUrl.equals(url)&&activeKey.equals(credential);
            changed=!same;
            if(same&&(status==1||status==2))return;
            if(same&&SystemClock.elapsedRealtime()-lastAttempt<4000)return;
            old=detachTransport();
            if(!same){testing=false;mic.beginSession();muted.clear();}
            activeUrl=url;activeKey=credential;lastAttempt=SystemClock.elapsedRealtime();status=1;alive=true;
            HashMap<String,String> headers=new HashMap<>();headers.put("X-CZM-Key",credential);
            next=new WebSocketClient(uri,new Draft_6455(),headers,5000){
                @Override public void onOpen(ServerHandshake handshake){
                    synchronized(LOCK){if(connection!=this)return;status=2;}
                    announceMic();
                    startSpeaker();startRecorder();
                }
                @Override public void onMessage(String text){
                    try{
                        JSONObject j=new JSONObject(text);String type=j.optString("type");int id=j.optInt("player",0);if(id<1)return;
                        synchronized(LOCK){
                            if(connection!=this)return;
                            // Old servers announce "talk" for every audio stream,
                            // including silence. Only measured audio activates it.
                            if("talk".equals(type)&&!j.optBoolean("active"))talking.remove(id);
                            else if("mic".equals(type)&&id!=localPlayer){
                                enabledPeers.put(id,j.optBoolean("enabled"));peerSensitivity.put(id,Math.max(0,Math.min(100,j.optInt("sensitivity",50))));
                                if(!j.optBoolean("enabled")){talking.remove(id);signals.remove(id);}
                            }
                            else if("left".equals(type)){received.remove(id);talking.remove(id);signals.remove(id);enabledPeers.put(id,false);muted.remove(id);}
                        }
                    }catch(Exception ignored){}
                }
                @Override public void onMessage(ByteBuffer bytes){
                    if(bytes==null||bytes.remaining()!=RXFRAME)return;
                    byte[] frame=new byte[RXFRAME];bytes.get(frame);if(frame[0]!='U')return;
                    int id=((frame[1]&255)<<24)|((frame[2]&255)<<16)|((frame[3]&255)<<8)|(frame[4]&255);if(id<1)return;
                    synchronized(LOCK){
                        if(connection!=this||muted.contains(id)||Boolean.FALSE.equals(enabledPeers.get(id)))return;
                        ArrayDeque<byte[]> q=received.get(id);if(q==null){q=new ArrayDeque<>();received.put(id,q);}
                        if(q.size()>=5)q.removeFirst();q.addLast(Arrays.copyOfRange(frame,5,frame.length));
                        short[] pcm=new short[SAMPLES];for(int i=0;i<SAMPLES;i++)pcm[i]=decodeMuLaw(frame[i+5]&255);
                        CzmLobbyAudio.Signal signal=signals.get(id);if(signal==null){signal=new CzmLobbyAudio.Signal();signals.put(id,signal);}
                        int sensitivity=peerSensitivity.containsKey(id)?peerSensitivity.get(id):50;
                        long now=SystemClock.elapsedRealtime();if(signal.update(pcm,SAMPLES,sensitivity,now))talking.put(id,signal.speakingUntil());else talking.remove(id);
                    }
                }
                @Override public void onClose(int code,String reason,boolean remote){
                    Transport stopped;
                    synchronized(LOCK){
                        if(connection!=this)return;
                        stopped=detachTransport();status=3;
                        if(code==4401||code==4403||code==4409)mic.request(false,true);
                    }
                    release(stopped);
                }
                @Override public void onError(Exception ex){Log.w(TAG,"temporary voice socket failed: "+ex.getClass().getSimpleName());}
            };
            next.setConnectionLostTimeout(15);connection=next;
        }
        if(changed)CzmLobbyMicTest.cancel();
        release(old);
        synchronized(LOCK){if(connection!=next)return;}
        try{next.connect();}catch(RuntimeException ex){
            synchronized(LOCK){if(connection==next){connection=null;alive=false;status=3;}}
        }
    }
    private static void startSpeaker(){
        synchronized(LOCK){if(!alive||!mic.foreground()||speaker!=null||status!=2)return;}
        int size=AudioTrack.getMinBufferSize(RATE,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_16BIT);if(size<=0)return;
        final AudioTrack track;
        try{
            track=new AudioTrack(AudioManager.STREAM_MUSIC,RATE,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(size,4096),AudioTrack.MODE_STREAM);
            if(track.getState()!=AudioTrack.STATE_INITIALIZED){track.release();return;}track.play();
        }catch(RuntimeException ex){Log.w(TAG,"playback unavailable");return;}
        synchronized(LOCK){if(!alive||!mic.foreground()||status!=2||speaker!=null){track.release();return;}speaker=track;}
        Thread worker=new Thread(()->{
            short[] output=new short[SAMPLES];int[] accumulator=new int[SAMPLES];
            while(true){
                synchronized(LOCK){
                    if(!alive||!mic.foreground()||status!=2||speaker!=track)break;
                    Arrays.fill(accumulator,0);int peers=0;
                    for(Map.Entry<Integer,ArrayDeque<byte[]>> e:received.entrySet()){
                        if(muted.contains(e.getKey()))continue;
                        byte[] frame=e.getValue().pollFirst();if(frame==null||frame.length!=SAMPLES)continue;
                        if(testing)continue;
                        ++peers;for(int i=0;i<SAMPLES;i++)accumulator[i]+=decodeMuLaw(frame[i]&255);
                    }
                    double gain=peers>1?1.0/Math.sqrt(peers):1.0;
                    for(int i=0;i<SAMPLES;i++)output[i]=(short)Math.max(-32768,Math.min(32767,(int)(accumulator[i]*gain)));
                }
                try{if(track.write(output,0,SAMPLES)<0)break;}catch(Exception ex){break;}
            }
        },"CZM Lobby Playback");worker.setDaemon(true);worker.start();
    }
    private static void microphoneFailed(WebSocketClient expected){
        synchronized(LOCK){if(connection!=expected||!alive||testing||!mic.canCapture())return;mic.request(false,true);}
        announceMic();
        Activity a=activity();if(a!=null)a.runOnUiThread(()->android.widget.Toast.makeText(a,
            CzmDownloads.ru()?"Микрофон недоступен. Проверь разрешение Android.":"Microphone unavailable. Check Android permission.",android.widget.Toast.LENGTH_LONG).show());
    }
    private static void startRecorder(){
        final WebSocketClient expected;
        final AudioRecord capture;
        synchronized(LOCK){
        if(testing||!mic.canCapture()||!alive||status!=2||recorder!=null)return;expected=connection;
        if(!micAllowed())return;
        AudioRecord candidate=null;
        try{
            candidate=CzmLobbyAudio.capture();
        }catch(RuntimeException ex){releaseCapture(candidate);Log.w(TAG,"microphone unavailable");microphoneFailed(expected);return;}
        capture=candidate;recorder=capture;
        }
        Thread worker=new Thread(()->{
            short[] samples=new short[SAMPLES];int accumulated=0;boolean hardwareFailure=false;
            try{
                while(true){
                    synchronized(LOCK){if(testing||!mic.canCapture()||!alive||status!=2||recorder!=capture)break;}
                    int n;
                    try{n=capture.read(samples,accumulated,SAMPLES-accumulated);}catch(RuntimeException ex){hardwareFailure=true;break;}
                    if(n<0){hardwareFailure=true;break;}if(n==0)continue;
                    accumulated+=n;if(accumulated<SAMPLES)continue;accumulated=0;
                    byte[] frame=new byte[FRAME];frame[0]='U';for(int i=0;i<SAMPLES;i++)frame[i+1]=(byte)encodeMuLaw(samples[i]);
                    WebSocketClient target;
                    synchronized(LOCK){
                        if(testing||recorder!=capture||!mic.canCapture()||!alive)break;target=connection;
                        long now=SystemClock.elapsedRealtime();localSignal.update(samples,SAMPLES,CzmLobbyAudio.sensitivity,now);localTalkingUntil=localSignal.speakingUntil();
                    }
                    if(target!=null&&target.isOpen())target.send(frame);
                }
            }catch(RuntimeException ex){Log.w(TAG,"microphone transport interrupted");}
            finally{
                boolean current;
                synchronized(LOCK){current=recorder==capture;if(current)recorder=null;}
                releaseCapture(capture);if(current&&hardwareFailure)microphoneFailed(expected);
            }
        },"CZM Lobby Microphone");worker.setDaemon(true);worker.start();
    }
    // ITU-T G.711 mu-law codec, stateless per sample; packet loss does not
    // corrupt the decoder state of the next frame.
    static int encodeMuLaw(short sample){
        int x=sample;
        int sign=(x>>8)&0x80;
        if(sign!=0)x=-x;
        if(x>32635)x=32635;
        x+=132;
        int exponent=7,mask=0x4000;
        while(exponent>0&&(x&mask)==0){mask>>=1;--exponent;}
        int mantissa=(x>>(exponent+3))&15;
        return (~(sign|(exponent<<4)|mantissa))&255;
    }
    static short decodeMuLaw(int code){
        int v=(~code)&255;
        int t=(((v&15)<<3)+132)<<((v>>4)&7);
        return (short)(((v&128)!=0)?(132-t):(t-132));
    }
}
