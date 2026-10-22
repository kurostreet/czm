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

/**
 * Temporary lobby voice, strictly separated from in-match game voice.
 * Audio never reaches files/storage; only authenticated wss is permitted.
 *
 * Codec: G.711 mu-law, mono 16 kHz, 20 ms / 320 bytes per packet.
 * Server protocol: TX b'U'+320; RX b'U'+u32 player ID+320.
 */
public final class CzmLobbyVoice {
    private static final String TAG="CzmLobbyVoice";
    private static final int RATE=16000, SAMPLES=320, FRAME=321, RXFRAME=325;
    private static final Object LOCK=new Object();
    private static final Map<Integer,ArrayDeque<byte[]>> received=new HashMap<>();
    private static final Set<Integer> muted=new HashSet<>();
    private static final Map<Integer,Long> talking=new HashMap<>();
    private static WebSocketClient connection;
    private static String activeUrl="",activeKey="";
    private static long lastAttempt;
    private static boolean microphone=false, alive=false;
    private static int status=0; // 0 disconnected, 1 connecting, 2 active, 3 failed
    private static AudioRecord recorder;
    private static AudioTrack speaker;

    private CzmLobbyVoice(){}

    public static int state(){synchronized(LOCK){return status;}}
    public static boolean microphoneOn(){synchronized(LOCK){return microphone;}}
    public static boolean speaking(int id){
        synchronized(LOCK){
            Long last=talking.get(id);
            return last!=null&&SystemClock.elapsedRealtime()-last<900;
        }
    }
    public static boolean locallyMuted(int player){
        synchronized(LOCK){return muted.contains(player);}
    }
    public static void mutePlayer(int player,boolean value){
        synchronized(LOCK){
            if(value)muted.add(player);
            else muted.remove(player);
        }
    }
    private static Activity activity(){
        Context context=SDLActivity.getContext();
        return context instanceof Activity?(Activity)context:null;
    }
    private static boolean micAllowed(){
        Context context=SDLActivity.getContext();
        return context!=null&&(Build.VERSION.SDK_INT<23 ||
            context.checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED);
    }
    public static void setMic(boolean on){
        if(on&&!micAllowed()){
            Activity a=activity();
            if(a!=null&&Build.VERSION.SDK_INT>=23)
                a.runOnUiThread(()->a.requestPermissions(
                    new String[]{Manifest.permission.RECORD_AUDIO},1724));
            return;
        }
        synchronized(LOCK){
            microphone=on;
            if(!on&&recorder!=null)try{recorder.stop();}catch(Exception ignored){}
        }
        if(on)startRecorder();
    }
    public static void permissionResult(boolean granted){
        if(granted)setMic(true);
    }

    /** Called from the native menu; idempotent for repeated per-frame polling. */
    public static void start(String url,String key){
        if(url==null||key==null||key.isEmpty()||!CzmAccount.serviceUrl(url))return;
        URI uri;
        try {
            URI https=new URI(url);
            if(!"https".equalsIgnoreCase(https.getScheme())||https.getHost()==null||
               https.getRawQuery()!=null||https.getRawFragment()!=null)return;
            uri=new URI("wss",null,https.getHost(),https.getPort(),https.getRawPath(),null,null);
        }catch(Exception ignored){return;}
        synchronized(LOCK){
            if(activeUrl.equals(url)&&activeKey.equals(key)&&
               (status==1||status==2))return;
            if(activeUrl.equals(url)&&activeKey.equals(key)&&
               SystemClock.elapsedRealtime()-lastAttempt<4000)return;
        }
        stop();
        synchronized(LOCK){
            activeUrl=url;activeKey=key;lastAttempt=SystemClock.elapsedRealtime();
            status=1;alive=true;
            HashMap<String,String> headers=new HashMap<>();
            headers.put("X-CZM-Key",key);
            WebSocketClient client=new WebSocketClient(uri,new Draft_6455(),headers,5000){
                @Override public void onOpen(ServerHandshake handshake){
                    synchronized(LOCK){
                        if(connection!=this)return;
                        status=2;
                    }
                    startSpeaker();
                    startRecorder();
                }
                @Override public void onMessage(String text){
                    try {
                        JSONObject json=new JSONObject(text);
                        String type=json.optString("type");
                        int player=json.optInt("player",0);
                        if(player<1)return;
                        synchronized(LOCK){
                            if(connection!=this)return;
                            if("talk".equals(type)){
                                if(json.optBoolean("active"))talking.put(player,SystemClock.elapsedRealtime());
                                else talking.remove(player);
                            }else if("left".equals(type)){
                                received.remove(player);talking.remove(player);muted.remove(player);
                            }
                        }
                    }catch(Exception ignored){}
                }
                @Override public void onMessage(ByteBuffer bytes){
                    if(bytes==null||bytes.remaining()!=RXFRAME)return;
                    byte[] frame=new byte[RXFRAME];
                    bytes.get(frame);
                    if(frame[0]!='U')return;
                    int player=((frame[1]&255)<<24)|((frame[2]&255)<<16)|
                               ((frame[3]&255)<<8)|(frame[4]&255);
                    if(player<=0)return;
                    synchronized(LOCK){
                        if(connection!=this||muted.contains(player))return;
                        ArrayDeque<byte[]> q=received.get(player);
                        if(q==null){q=new ArrayDeque<>();received.put(player,q);}
                        if(q.size()>=5)q.removeFirst();
                        q.addLast(Arrays.copyOfRange(frame,5,frame.length));
                        talking.put(player,SystemClock.elapsedRealtime());
                    }
                }
                @Override public void onClose(int code,String reason,boolean remote){
                    boolean current;
                    synchronized(LOCK){
                        current=connection==this;
                        if(current){connection=null;status=3;alive=false;microphone=false;}
                    }
                    if(current)endAudio();
                }
                @Override public void onError(Exception ex){
                    Log.w(TAG,"temporary voice socket failed: "+ex.getClass().getSimpleName());
                }
            };
            client.setConnectionLostTimeout(15);
            connection=client;
            client.connect();
        }
    }

    public static void stop(){
        WebSocketClient old;
        synchronized(LOCK){
            old=connection;connection=null;
            activeUrl="";activeKey="";status=0;alive=false;microphone=false;
            received.clear();talking.clear();muted.clear();
        }
        if(old!=null)try{old.close();}catch(Exception ignored){}
        endAudio();
    }
    private static void endAudio(){
        AudioRecord capture;
        AudioTrack playback;
        synchronized(LOCK){
            capture=recorder;recorder=null;
            playback=speaker;speaker=null;
        }
        if(capture!=null){
            try{capture.stop();}catch(Exception ignored){}
            try{capture.release();}catch(Exception ignored){}
        }
        if(playback!=null){
            try{playback.pause();playback.flush();playback.release();}catch(Exception ignored){}
        }
    }
    private static void startSpeaker(){
        synchronized(LOCK){if(!alive||speaker!=null||status!=2)return;}
        int size=AudioTrack.getMinBufferSize(RATE,AudioFormat.CHANNEL_OUT_MONO,
                                            AudioFormat.ENCODING_PCM_16BIT);
        if(size<=0)return;
        final AudioTrack track;
        try {
            track=new AudioTrack(AudioManager.STREAM_MUSIC,RATE,AudioFormat.CHANNEL_OUT_MONO,
                                  AudioFormat.ENCODING_PCM_16BIT,Math.max(size,4096),
                                  AudioTrack.MODE_STREAM);
            if(track.getState()!=AudioTrack.STATE_INITIALIZED){track.release();return;}
            track.play();
        }catch(RuntimeException e){Log.w(TAG,"playback unavailable");return;}
        synchronized(LOCK){
            if(!alive||status!=2){track.release();return;}
            speaker=track;
        }
        Thread playback=new Thread(()->{
            short[] output=new short[SAMPLES];
            int[] accumulator=new int[SAMPLES];
            while(true){
                synchronized(LOCK){
                    if(!alive||status!=2||speaker!=track)break;
                    Arrays.fill(accumulator,0);
                    int peers=0;
                    for(Map.Entry<Integer,ArrayDeque<byte[]>> e:received.entrySet()){
                        if(muted.contains(e.getKey()))continue;
                        byte[] frame=e.getValue().pollFirst();
                        if(frame==null||frame.length!=SAMPLES)continue;
                        ++peers;
                        for(int i=0;i<SAMPLES;i++){
                            accumulator[i]+=decodeMuLaw(frame[i]&255);
                        }
                    }
                    // Scale once before clipping to prevent clipping distortion
                    // when several friends speak simultaneously.
                    double gain=peers>1?1.0/Math.sqrt(peers):1.0;
                    for(int i=0;i<SAMPLES;i++){
                        int value=(int)(accumulator[i]*gain);
                        output[i]=(short)Math.max(-32768,Math.min(32767,value));
                    }
                }
                try {
                    if(track.write(output,0,SAMPLES)<0)break;
                }catch(Exception exception){break;}
            }
        },"CZM Lobby Playback");
        playback.setDaemon(true);playback.start();
    }
    private static void startRecorder(){
        synchronized(LOCK){
            if(!microphone||!alive||status!=2||recorder!=null)return;
        }
        if(!micAllowed())return;
        int min=AudioRecord.getMinBufferSize(RATE,AudioFormat.CHANNEL_IN_MONO,
                                            AudioFormat.ENCODING_PCM_16BIT);
        if(min<=0)return;
        final AudioRecord capture;
        try{
            capture=new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION,RATE,
                       AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,
                       Math.max(min,4096));
            if(capture.getState()!=AudioRecord.STATE_INITIALIZED){
                capture.release();return;
            }
            capture.startRecording();
        }catch(SecurityException | IllegalStateException ex){
            Log.w(TAG,"microphone unavailable");return;
        }
        synchronized(LOCK){
            if(!microphone||!alive||status!=2){capture.release();return;}
            recorder=capture;
        }
        Thread worker=new Thread(()->{
            short[] samples=new short[SAMPLES];
            int accumulated=0;
            try{
                while(true){
                    synchronized(LOCK){
                        if(!microphone||!alive||status!=2||recorder!=capture)break;
                    }
                    int n=capture.read(samples,accumulated,SAMPLES-accumulated);
                    if(n<0)break; // Android audio error, avoid a busy retry loop
                    if(n==0)continue;
                    accumulated+=n;
                    if(accumulated<SAMPLES)continue;
                    accumulated=0;
                    byte[] frame=new byte[FRAME];frame[0]='U';
                    for(int i=0;i<SAMPLES;i++)frame[i+1]=(byte)encodeMuLaw(samples[i]);
                    WebSocketClient target;
                    synchronized(LOCK){target=connection;}
                    if(target!=null&&target.isOpen())target.send(frame);
                }
            }catch(RuntimeException exception){
                Log.w(TAG,"microphone stream ended");
            }finally{
                synchronized(LOCK){if(recorder==capture)recorder=null;}
                try{capture.stop();}catch(Exception ignored){}
                try{capture.release();}catch(Exception ignored){}
            }
        },"CZM Lobby Microphone");
        worker.setDaemon(true);worker.start();
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
