"""Run the real Java voice facade with deterministic Android/socket adapters."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
JAVA=ROOT/'android/app/src/main/java/ru/kurostreet/counterzombiemobile'
STUBS={
'android/Manifest.java': 'package android;public class Manifest{public static class permission{public static final String RECORD_AUDIO="mic";}}',
'android/content/pm/PackageManager.java':'package android.content.pm;public class PackageManager{public static final int PERMISSION_GRANTED=0;}',
'android/content/Context.java':'package android.content;public class Context{public static boolean granted=true;public int checkSelfPermission(String p){return granted?0:-1;}}',
'android/app/Activity.java':'package android.app;public class Activity extends android.content.Context{public static int requests;public void runOnUiThread(Runnable r){r.run();}public void requestPermissions(String[] p,int id){requests++;}}',
'android/os/Build.java':'package android.os;public class Build{public static class VERSION{public static int SDK_INT=35;}}',
'android/os/SystemClock.java':'package android.os;public class SystemClock{public static long now=10000;public static long elapsedRealtime(){return now;}}',
'android/util/Log.java':'package android.util;public class Log{public static int w(String a,String b){return 0;}}',
'android/widget/Toast.java':'package android.widget;public class Toast{public static final int LENGTH_LONG=1;public static Toast makeText(android.content.Context c,String s,int n){return new Toast();}public void show(){}}',
'android/media/AudioFormat.java':'package android.media;public class AudioFormat{public static final int CHANNEL_OUT_MONO=4,CHANNEL_IN_MONO=16,ENCODING_PCM_16BIT=2;}',
'android/media/AudioManager.java':'package android.media;public class AudioManager{public static final int STREAM_MUSIC=3;}',
'android/media/MediaRecorder.java':'package android.media;public class MediaRecorder{public static class AudioSource{public static final int VOICE_COMMUNICATION=7;}}',
'android/media/AudioRecord.java':'''package android.media;public class AudioRecord{
 public static final int STATE_INITIALIZED=1;private volatile boolean stopped;
 public AudioRecord(int a,int b,int c,int d,int e){}public static int getMinBufferSize(int a,int b,int c){return 4096;}
 public int getState(){return 1;}public void startRecording(){}public void stop(){stopped=true;}public void release(){stopped=true;}
 public int read(short[] a,int b,int c){try{Thread.sleep(2);}catch(Exception e){}return stopped?-1:0;}}
''',
'android/media/AudioTrack.java':'''package android.media;public class AudioTrack{
 public static final int STATE_INITIALIZED=1,MODE_STREAM=1;
 public AudioTrack(int a,int b,int c,int d,int e,int f){}public static int getMinBufferSize(int a,int b,int c){return 4096;}
 public int getState(){return 1;}public void play(){}public void pause(){}public void flush(){}public void release(){}
 public int write(short[] a,int b,int c){try{Thread.sleep(2);}catch(Exception e){}return c;}}
''',
'org/libsdl/app/SDLActivity.java':'package org.libsdl.app;public class SDLActivity{private static final android.app.Activity a=new android.app.Activity();public static android.content.Context getContext(){return a;}}',
'org/json/JSONObject.java':'package org.json;public class JSONObject{public JSONObject(String s){}public String optString(String s){return "";}public int optInt(String s,int n){return n;}public boolean optBoolean(String s){return false;}}',
'org/java_websocket/handshake/ServerHandshake.java':'package org.java_websocket.handshake;public interface ServerHandshake{}',
'org/java_websocket/drafts/Draft_6455.java':'package org.java_websocket.drafts;public class Draft_6455{}',
'org/java_websocket/client/WebSocketClient.java':'''package org.java_websocket.client;
import java.util.*;import java.net.URI;import java.nio.ByteBuffer;import org.java_websocket.handshake.ServerHandshake;import org.java_websocket.drafts.Draft_6455;
public abstract class WebSocketClient{
 public static final List<WebSocketClient> created=new ArrayList<>();public final Map<String,String> headers;private boolean open;
 public WebSocketClient(URI u,Draft_6455 d,Map<String,String> h,int timeout){headers=h;created.add(this);}
 public void setConnectionLostTimeout(int n){}public void connect(){}public boolean isOpen(){return open;}
 public void opened(){open=true;onOpen(null);}public void failed(int code){open=false;onClose(code,"test",true);}
 public void close(){open=false;onClose(1000,"closed",false);}public void send(byte[] b){}
 public abstract void onOpen(ServerHandshake h);public abstract void onMessage(String s);public abstract void onMessage(ByteBuffer b);public abstract void onClose(int c,String r,boolean remote);public abstract void onError(Exception e);
}''',
'ru/kurostreet/counterzombiemobile/CzmAccount.java':'package ru.kurostreet.counterzombiemobile;public class CzmAccount{static String token="account-session";static boolean serviceUrl(String u){return u.contains("counter-zombie.ru/");}static String lobbyVoiceKey(String u){return serviceUrl(u)?token:"";}}',
'ru/kurostreet/counterzombiemobile/CzmDownloads.java':'package ru.kurostreet.counterzombiemobile;public class CzmDownloads{static boolean ru(){return true;}}',
}
HARNESS=r'''
package ru.kurostreet.counterzombiemobile;
import android.content.Context;import android.app.Activity;import android.os.SystemClock;import org.java_websocket.client.WebSocketClient;
public class LobbyVoiceClientTest{
 static String url="https://counter-zombie.ru/api/v1/lobbies/room-one/voice";
 static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
 static WebSocketClient latest(){return WebSocketClient.created.get(WebSocketClient.created.size()-1);}
 static void advance(){SystemClock.now+=5000;}
 public static void main(String[] args)throws Exception{
  CzmLobbyVoice.resume();CzmLobbyVoice.start(url,"test-key");WebSocketClient first=latest();
  check(!CzmLobbyVoice.microphoneOn(),"new room starts muted");
  check("account-session".equals(first.headers.get("X-CZM-Key")),"socket uses Java session, never legacy device key");
  CzmLobbyVoice.setMic(true);check(CzmLobbyVoice.microphoneOn(),"remember explicit choice while connecting");
  first.opened();check(CzmLobbyVoice.state()==2,"connected");
  int count=WebSocketClient.created.size();CzmLobbyVoice.start(url,"test-key");check(WebSocketClient.created.size()==count,"poll must not restart a live socket");
  first.failed(1006);check(CzmLobbyVoice.microphoneOn(),"network failure must not erase explicit mic choice");
  advance();CzmLobbyVoice.start(url,"test-key");WebSocketClient second=latest();second.opened();
  first.failed(1006);check(CzmLobbyVoice.state()==2&&CzmLobbyVoice.microphoneOn(),"stale socket must not tear down reconnected audio");
  CzmLobbyVoice.setMic(false);advance();second.failed(1006);CzmLobbyVoice.start(url,"test-key");latest().opened();check(!CzmLobbyVoice.microphoneOn(),"explicit off survives reconnect");
  CzmLobbyVoice.setMic(true);latest().failed(4403);check(!CzmLobbyVoice.microphoneOn(),"authoritative denial clears microphone");
  CzmLobbyVoice.stop();advance();Context.granted=false;CzmLobbyVoice.resume();CzmLobbyVoice.start(url,"test-key");
  CzmLobbyVoice.setMic(true);CzmLobbyVoice.setMic(true);check(Activity.requests==1,"one permission prompt");
  CzmLobbyVoice.pause();Context.granted=true;CzmLobbyVoice.permissionResult(true);
  check(CzmLobbyVoice.microphoneOn(),"permission result retains the explicit request across dialog pause");
  count=WebSocketClient.created.size();advance();CzmLobbyVoice.start(url,"test-key");check(WebSocketClient.created.size()==count,"no socket restart in background");
  CzmLobbyVoice.resume();advance();CzmLobbyVoice.start(url,"test-key");latest().opened();check(CzmLobbyVoice.microphoneOn(),"grant applies on returning to the same lobby");
  CzmLobbyVoice.pause();check(!CzmLobbyVoice.microphoneOn(),"ordinary background transition disables mic");
  CzmLobbyVoice.stop();CzmLobbyVoice.resume();Context.granted=false;advance();CzmLobbyVoice.start(url,"test-key");CzmLobbyVoice.setMic(true);
  CzmLobbyVoice.stop();CzmLobbyVoice.start(url.replace("room-one","room-two"),"test-key");Context.granted=true;CzmLobbyVoice.permissionResult(true);
  check(!CzmLobbyVoice.microphoneOn(),"late permission cannot enable the mic in a new session");
  CzmLobbyVoice.setMic(true);CzmAccount.token="another-account-session";CzmLobbyVoice.start(url,"test-key");check(!CzmLobbyVoice.microphoneOn(),"account or room switch resets the mic");
  count=WebSocketClient.created.size();CzmLobbyVoice.start("http://counter-zombie.ru/voice","key");CzmLobbyVoice.start(url+"?token=x","key");check(WebSocketClient.created.size()==count,"invalid voice URLs rejected");
  CzmLobbyVoice.stop();check(!CzmLobbyVoice.microphoneOn()&&CzmLobbyVoice.state()==0,"explicit leave releases state");
  System.out.println("LOBBY_VOICE_CLIENT_OK");
 }
}
'''

class LobbyVoiceClientTests(unittest.TestCase):
    def test_reconnect_permission_background_and_stale_callbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,source in STUBS.items():
                file=root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(source)
            package=root/'ru/kurostreet/counterzombiemobile'
            for name in ['CzmLobbyVoice.java','CzmLobbyMicState.java']:(package/name).write_text((JAVA/name).read_text())
            (package/'LobbyVoiceClientTest.java').write_text(HARNESS)
            subprocess.run(['javac','--release','11','-d',str(root/'classes'),*[str(p) for p in root.rglob('*.java')]],check=True)
            subprocess.run(['java','-cp',str(root/'classes'),'ru.kurostreet.counterzombiemobile.LobbyVoiceClientTest'],check=True,timeout=20)

if __name__=='__main__':unittest.main()
