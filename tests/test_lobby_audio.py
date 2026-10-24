"""Real signal detection, private loopback, on/off state and cancellation."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_lobby_voice_client import STUBS, JAVA

HARNESS=r'''
package ru.kurostreet.counterzombiemobile;
import java.nio.ByteBuffer;import java.util.Arrays;import java.util.function.BooleanSupplier;
import android.content.Context;import android.media.AudioRecord;import android.media.AudioTrack;import android.os.SystemClock;
import org.java_websocket.client.WebSocketClient;
public class LobbyAudioTest{
 static void check(boolean ok,String reason){if(!ok)throw new AssertionError(reason);}
 static void await(BooleanSupplier condition,String reason)throws Exception{
  long end=System.nanoTime()+3000000000L;while(!condition.getAsBoolean()&&System.nanoTime()<end)Thread.sleep(4);check(condition.getAsBoolean(),reason);
 }
 static byte[] frame(int id,int amplitude){byte[] bytes=new byte[325];bytes[0]='U';bytes[4]=(byte)id;
  for(int i=0;i<320;i++)bytes[i+5]=(byte)CzmLobbyVoice.encodeMuLaw((short)(i%2==0?amplitude:-amplitude));return bytes;}
 public static void main(String[] args)throws Exception{
  short[] quiet=new short[320],voice=new short[320];Arrays.fill(voice,(short)1600);
  CzmLobbyAudio.Signal signal=new CzmLobbyAudio.Signal();
  for(int i=0;i<20;i++)check(!signal.update(quiet,320,50,1000+i*20),"silence is not speech");
  check(!signal.update(voice,320,50,1500),"a single impulse does not light the icon");
  check(!signal.update(quiet,320,50,1520),"impulse followed by silence stays inactive");
  check(!signal.update(voice,320,50,1600),"short attack");check(signal.update(voice,320,50,1620),"sustained voice activates");
  check(signal.update(quiet,320,50,1800),"small gaps between words stay smooth");check(!signal.update(quiet,320,50,1920),"release after silence");
  short[] soft=new short[320];Arrays.fill(soft,(short)250);
  CzmLobbyAudio.Signal low=new CzmLobbyAudio.Signal(),high=new CzmLobbyAudio.Signal();
  low.update(soft,320,10,100);high.update(soft,320,90,100);
  check(!low.update(soft,320,10,120)&&high.update(soft,320,90,120),"sensitivity changes the gate");

  CzmLobbyVoice.resume();CzmLobbyVoice.start("https://counter-zombie.ru/api/v1/lobbies/audio-room/voice","legacy",7);
  WebSocketClient socket=WebSocketClient.created.get(WebSocketClient.created.size()-1);socket.opened();
  socket.onMessage("{\"type\":\"talk\",\"player\":8,\"active\":true}");check(!CzmLobbyVoice.speaking(8),"control packets cannot pretend silence is speech");
  socket.onMessage("{\"type\":\"mic\",\"player\":8,\"enabled\":false}");
  check(!CzmLobbyVoice.microphoneEnabled(8),"remote off state");
  socket.onMessage(ByteBuffer.wrap(frame(8,1600)));socket.onMessage(ByteBuffer.wrap(frame(8,1600)));
  check(!CzmLobbyVoice.speaking(8),"stale audio cannot override explicit mute");
  socket.onMessage("{\"type\":\"mic\",\"player\":8,\"enabled\":true,\"sensitivity\":50}");
  check(CzmLobbyVoice.microphoneEnabled(8),"remote enabled state");
  for(int i=0;i<4;i++){SystemClock.now+=20;socket.onMessage(ByteBuffer.wrap(frame(8,0)));}
  check(!CzmLobbyVoice.speaking(8),"continuous silence packets do not light the icon");
  socket.onMessage(ByteBuffer.wrap(frame(8,1600)));SystemClock.now+=20;socket.onMessage(ByteBuffer.wrap(frame(8,1600)));
  check(CzmLobbyVoice.speaking(8),"decoded remote voice lights icon");SystemClock.now+=400;
  check(!CzmLobbyVoice.speaking(8),"remote icon expires without packets");
  CzmLobbyVoice.mutePlayer(8,true);check(!CzmLobbyVoice.speaking(8),"local mute clears speaking indicator");

  AudioRecord.feed=true;CzmLobbyVoice.setMic(true);await(()->CzmLobbyVoice.speaking(7),"own microphone level lights own icon");
  check(CzmLobbyMicTest.open(),"each member can open a private check");
  check(CzmLobbyVoice.microphoneOn()&&!CzmLobbyVoice.microphoneEnabled(7),"test suspends transmission but preserves the user's choice");
  int sent=socket.sent.size();CzmLobbyMicTest.record();await(()->CzmLobbyMicTest.phase()==CzmLobbyMicTest.READY,"three-second recording completes");
  check(CzmLobbyMicTest.heard()&&CzmLobbyMicTest.hasRecording(),"test sees real capture signal");
  java.lang.reflect.Field count=CzmLobbyMicTest.class.getDeclaredField("count");count.setAccessible(true);check(count.getInt(null)==48000,"recording is bounded to three seconds");
  check(socket.sent.size()==sent,"private recording is never sent to teammates");
  AudioTrack.nonZero=0;CzmLobbyMicTest.play();await(()->CzmLobbyMicTest.phase()==CzmLobbyMicTest.READY,"private playback completes");
  check(AudioTrack.nonZero>0&&socket.sent.size()==sent,"listen only plays locally");
  CzmLobbyMicTest.close();check(CzmLobbyVoice.microphoneOn()&&CzmLobbyVoice.microphoneEnabled(7),"closing restores an enabled microphone");
  await(()->socket.sent.size()>sent,"live speech resumes after the check");
  CzmLobbyVoice.setMic(false);check(!CzmLobbyVoice.speaking(7),"explicit off clears own indicator immediately");
  CzmLobbyMicTest.open();CzmLobbyMicTest.close();check(!CzmLobbyVoice.microphoneOn(),"checking never auto-enables an originally off microphone");

  Context.granted=false;CzmLobbyMicTest.open();CzmLobbyMicTest.record();
  check(CzmLobbyMicTest.phase()==CzmLobbyMicTest.PERMISSION,"test requests its own permission");
  CzmLobbyVoice.pause();Context.granted=true;CzmLobbyVoice.permissionResult(true);
  check(CzmLobbyMicTest.phase()==CzmLobbyMicTest.PERMISSION,"grant cannot capture while paused");
  CzmLobbyVoice.resume();await(()->CzmLobbyMicTest.phase()==CzmLobbyMicTest.READY,"test resumes only the explicit pending permission request");
  check(!CzmLobbyVoice.microphoneOn(),"test permission does not unmute the lobby");CzmLobbyMicTest.close();
  AudioRecord.fail=true;CzmLobbyMicTest.open();CzmLobbyMicTest.record();
  await(()->CzmLobbyMicTest.phase()==CzmLobbyMicTest.UNAVAILABLE,"hardware failure is visible");AudioRecord.fail=false;CzmLobbyMicTest.close();
  CzmLobbyMicTest.open();CzmLobbyMicTest.record();CzmLobbyVoice.stop();Thread.sleep(30);
  check(!CzmLobbyMicTest.opened()&&!CzmLobbyMicTest.hasRecording()&&count.getInt(null)==0,"leaving erases the private recording");
  check(!CzmLobbyVoice.microphoneOn(),"leaving never restarts a capture");
  check(AudioRecord.maxActive<=1,"live voice and private test never capture simultaneously");
  System.out.println("LOBBY_AUDIO_AND_PRIVATE_CHECK_OK");
 }
}
'''

class LobbyAudioTests(unittest.TestCase):
    def test_voice_activity_private_recording_permissions_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            for name,source in STUBS.items():
                f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(source)
            package=p/'ru/kurostreet/counterzombiemobile'
            for name in ['CzmLobbyVoice.java','CzmLobbyMicState.java','CzmLobbyAudio.java','CzmLobbyMicTest.java']:
                (package/name).write_text((JAVA/name).read_text())
            (package/'LobbyAudioTest.java').write_text(HARNESS)
            subprocess.run(['javac','--release','11','-d',str(p/'classes'),*[str(f)for f in p.rglob('*.java')]],check=True)
            subprocess.run(['java','-cp',str(p/'classes'),'ru.kurostreet.counterzombiemobile.LobbyAudioTest'],check=True,timeout=20)

if __name__=='__main__':unittest.main()
