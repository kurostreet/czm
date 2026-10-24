package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.Manifest;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.os.Build;
import android.os.SystemClock;
import org.libsdl.app.SDLActivity;
import java.util.Arrays;

/** A three-second in-memory loopback, isolated from the lobby's transmission. */
final class CzmLobbyMicTest {
    static final int IDLE=0,RECORDING=1,READY=2,PLAYING=3,PERMISSION=4,DENIED=5,UNAVAILABLE=6,NO_SIGNAL=7;
    private static final Object LOCK=new Object();
    private static final int LIMIT=CzmLobbyAudio.RATE*3;
    private static boolean opened,pending,afterResume,heard;
    private static int generation,phase,count,level;
    private static short[] recording;
    private static AudioRecord capture;
    private static AudioTrack playback;
    private CzmLobbyMicTest(){}
    static boolean open(){
        if(!CzmLobbyVoice.beginTest())return false;
        synchronized(LOCK){if(opened)return true;opened=true;phase=IDLE;count=level=0;heard=false;++generation;recording=new short[LIMIT];}
        if(!CzmLobbyVoice.testAvailable()){cancel();return false;}
        return true;
    }
    static boolean opened(){synchronized(LOCK){return opened;}}
    static int phase(){synchronized(LOCK){return phase;}}
    static int level(){synchronized(LOCK){return level;}}
    static boolean heard(){synchronized(LOCK){return heard;}}
    static boolean hasRecording(){synchronized(LOCK){return opened&&count>=CzmLobbyAudio.FRAME;}}
    static void close(){cancel();CzmLobbyVoice.endTest();}
    static void cancel(){
        AudioRecord old;AudioTrack sound;
        synchronized(LOCK){++generation;opened=pending=afterResume=false;phase=IDLE;old=capture;sound=playback;capture=null;playback=null;
            if(recording!=null)Arrays.fill(recording,(short)0);recording=null;count=level=0;heard=false;}
        CzmLobbyAudio.release(old);CzmLobbyAudio.release(sound);
    }
    static void pause(){boolean keep;synchronized(LOCK){keep=pending;}if(!keep)cancel();}
    static void resume(){boolean start;synchronized(LOCK){start=opened&&afterResume;afterResume=false;}if(start)record();}
    static boolean permissionResult(boolean granted){
        synchronized(LOCK){if(!opened||!pending)return false;pending=false;if(!granted){phase=DENIED;return true;}}
        if(CzmLobbyVoice.testAvailable())record();else synchronized(LOCK){afterResume=true;}
        return true;
    }
    static void record(){
        if(!CzmLobbyVoice.testAvailable())return;
        Context context=SDLActivity.getContext();if(!(context instanceof Activity))return;
        Activity activity=(Activity)context;
        synchronized(LOCK){if(!opened||phase==RECORDING||phase==PLAYING||pending)return;}
        if(Build.VERSION.SDK_INT>=23&&activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){
            final int requestToken;
            synchronized(LOCK){if(!opened)return;pending=true;phase=PERMISSION;requestToken=generation;}
            activity.runOnUiThread(()->{
                synchronized(LOCK){if(!opened||!pending||generation!=requestToken)return;}
                activity.requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},1724);
            });return;
        }
        final int token;
        synchronized(LOCK){if(!opened||phase==RECORDING||phase==PLAYING)return;token=++generation;phase=RECORDING;count=level=0;heard=false;Arrays.fill(recording,(short)0);}
        Thread worker=new Thread(()->{
            AudioRecord own=null;boolean failed=false;
            try{
                own=CzmLobbyAudio.capture();
                synchronized(LOCK){if(!opened||token!=generation){CzmLobbyAudio.release(own);return;}capture=own;}
                short[] frame=new short[CzmLobbyAudio.FRAME];CzmLobbyAudio.Signal signal=new CzmLobbyAudio.Signal();int accumulated=0;
                long deadline=SystemClock.elapsedRealtime()+6000;
                while(SystemClock.elapsedRealtime()<deadline){
                    synchronized(LOCK){if(!opened||token!=generation||phase!=RECORDING)break;}
                    int n=own.read(frame,accumulated,frame.length-accumulated);if(n<0){failed=true;break;}if(n==0)continue;
                    accumulated+=n;if(accumulated<frame.length)continue;accumulated=0;
                    boolean sound=signal.update(frame,frame.length,CzmLobbyAudio.sensitivity,SystemClock.elapsedRealtime());
                    synchronized(LOCK){
                        if(!opened||token!=generation||phase!=RECORDING)break;
                        heard|=sound;level=signal.level();int save=Math.min(frame.length,LIMIT-count);
                        for(int i=0;i<save;i++)recording[count+i]=CzmLobbyVoice.decodeMuLaw(CzmLobbyVoice.encodeMuLaw(frame[i]));
                        count+=save;if(count>=LIMIT)break;
                    }
                }
            }catch(RuntimeException ex){failed=true;}
            finally{
                synchronized(LOCK){if(token==generation&&opened){capture=null;phase=failed?UNAVAILABLE:count>=CzmLobbyAudio.FRAME?READY:NO_SIGNAL;}}
                CzmLobbyAudio.release(own);
            }
        },"CZM Private Mic Check");worker.setDaemon(true);worker.start();
    }
    static void stopRecording(){AudioRecord old;synchronized(LOCK){if(phase!=RECORDING)return;++generation;old=capture;capture=null;phase=count>=CzmLobbyAudio.FRAME?READY:NO_SIGNAL;}CzmLobbyAudio.release(old);}
    static void play(){
        final int token;final short[] samples;
        synchronized(LOCK){if(!opened||count<CzmLobbyAudio.FRAME||phase==RECORDING||phase==PLAYING||phase==PERMISSION)return;token=++generation;samples=Arrays.copyOf(recording,count);phase=PLAYING;}
        Thread worker=new Thread(()->{
            AudioTrack own=null;boolean failed=false;
            try{
                own=CzmLobbyAudio.playback();synchronized(LOCK){if(token!=generation||!opened){CzmLobbyAudio.release(own);return;}playback=own;}
                for(int at=0;at<samples.length;){
                    synchronized(LOCK){if(token!=generation||!opened)break;}
                    int written=own.write(samples,at,Math.min(CzmLobbyAudio.FRAME,samples.length-at));
                    if(written<=0){failed=true;break;}at+=written;
                }
                long deadline=SystemClock.elapsedRealtime()+2000;
                while(!failed&&((long)own.getPlaybackHeadPosition()&0xffffffffL)<samples.length&&SystemClock.elapsedRealtime()<deadline){
                    synchronized(LOCK){if(token!=generation||!opened)break;}
                    try{Thread.sleep(10);}catch(InterruptedException ex){Thread.currentThread().interrupt();break;}
                }
            }catch(RuntimeException ex){failed=true;}
            finally{
                synchronized(LOCK){if(token==generation&&opened){playback=null;phase=failed?UNAVAILABLE:READY;}}
                CzmLobbyAudio.release(own);Arrays.fill(samples,(short)0);
            }
        },"CZM Private Mic Playback");worker.setDaemon(true);worker.start();
    }
}
