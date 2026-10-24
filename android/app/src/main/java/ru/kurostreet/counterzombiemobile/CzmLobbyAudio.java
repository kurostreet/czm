package ru.kurostreet.counterzombiemobile;

import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;

/** One capture format for the live lobby and its private microphone check. */
final class CzmLobbyAudio {
    static final int RATE=16000, FRAME=320;
    static volatile int sensitivity=50;
    private static final Object CAPTURE_LOCK=new Object();
    private static AudioRecord activeCapture;
    private CzmLobbyAudio(){}
    static AudioRecord capture(){
        synchronized(CAPTURE_LOCK){
        long deadline=System.nanoTime()+1500000000L;
        while(activeCapture!=null){
            if(System.nanoTime()>=deadline)throw new IllegalStateException("capture is still closing");
            try{CAPTURE_LOCK.wait(50);}catch(InterruptedException ex){Thread.currentThread().interrupt();throw new IllegalStateException("capture cancelled");}
        }
        int size=AudioRecord.getMinBufferSize(RATE,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT);
        if(size<=0)throw new IllegalStateException("capture format unavailable");
        AudioRecord record=new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION,RATE,
            AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(size,4096));
        try{
            if(record.getState()!=AudioRecord.STATE_INITIALIZED)throw new IllegalStateException("capture unavailable");
            record.startRecording();activeCapture=record;return record;
        }catch(RuntimeException ex){record.release();throw ex;}
        }
    }
    static AudioTrack playback(){
        int size=AudioTrack.getMinBufferSize(RATE,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_16BIT);
        if(size<=0)throw new IllegalStateException("playback format unavailable");
        AudioTrack track=new AudioTrack(AudioManager.STREAM_MUSIC,RATE,AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,Math.max(size,4096),AudioTrack.MODE_STREAM);
        try{
            if(track.getState()!=AudioTrack.STATE_INITIALIZED)throw new IllegalStateException("playback unavailable");
            track.play();return track;
        }catch(RuntimeException ex){track.release();throw ex;}
    }
    static void release(AudioRecord value){if(value!=null){synchronized(CAPTURE_LOCK){
        try{value.stop();}catch(Exception ignored){}try{value.release();}catch(Exception ignored){}
        if(activeCapture==value){activeCapture=null;CAPTURE_LOCK.notifyAll();}
    }}}
    static void release(AudioTrack value){if(value!=null){try{value.pause();value.flush();}catch(Exception ignored){}try{value.release();}catch(Exception ignored){}}}

    /** Energy gate with a short attack and release; silence packets are not speech. */
    static final class Signal {
        private double noise=55;
        private int attack,level;
        private long until;
        boolean update(short[] samples,int length,int sensitivity,long now){
            if(length<=0)return now<until;
            double energy=0;for(int i=0;i<length;i++)energy+=(double)samples[i]*samples[i];
            double rms=Math.sqrt(energy/length);
            int fresh=(int)Math.min(100,Math.sqrt(rms/5000.0)*100);
            level=(level*2+fresh)/3;
            double floor=Math.max(100,900-Math.max(0,Math.min(100,sensitivity))*11.0);
            double threshold=Math.max(floor,noise*3.0);
            if(rms>=threshold){
                if(++attack>=2)until=now+280;
            }else{
                attack=0;
                if(now>=until)noise=noise*.98+Math.min(rms,threshold)*.02;
            }
            return now<until;
        }
        int level(){return level;}
        long speakingUntil(){return until;}
    }
}
