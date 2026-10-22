package ru.kurostreet.counterzombiemobile;

import android.content.Context;
import android.media.AudioManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.ViewGroup;
import org.libsdl.app.CzmAudioGate;
import org.libsdl.app.SDLActivity;
import su.xash.engine.XashActivity;

/** Keep the startup artwork above SDL until the native menu has drawn. */
public final class CzmGameActivity extends XashActivity implements AudioManager.OnAudioFocusChangeListener {
    private final Handler ui = new Handler(Looper.getMainLooper());
    private CzmStartupView startup;
    private AudioManager audio;
    private boolean foreground, focus, ready,backgroundIntent;
    private final Runnable silence = new Runnable() {
        @Override public void run() {
            if (foreground && !focus) {
                CzmAudioGate.mute(true);
                ui.postDelayed(this, 200);
            }
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        audio = (AudioManager)getSystemService(Context.AUDIO_SERVICE);
        if (!SDLActivity.mBrokenLibraries) {
            startup = new CzmStartupView(this);
            startup.setClickable(true);
            addContentView(startup, new ViewGroup.LayoutParams(-1, -1));
        }
    }

    public void menuReady() {
        ui.post(() -> {
            if (ready || startup == null || isFinishing()) return;
            ready = true;
            CzmNet.widgetConfirm(this,getIntent());
            // Let the first native frame reach the surface before fading its cover.
            startup.postOnAnimation(() -> startup.postOnAnimation(() -> {
                if (startup == null) return;
                startup.animate().alpha(0f).setDuration(220).withEndAction(() -> {
                    if (startup != null && startup.getParent() instanceof ViewGroup)
                        ((ViewGroup)startup.getParent()).removeView(startup);
                    startup = null;
                }).start();
            }));
        });
    }

    @Override protected void onNewIntent(android.content.Intent intent) { super.onNewIntent(intent);setIntent(intent);if(ready)CzmNet.widgetConfirm(this,intent); }

    private void updateAudio() {
        ui.removeCallbacks(silence);
        CzmAudioGate.mute(!foreground || !focus);
        if (foreground && !focus) ui.post(silence);
    }

    @Override protected void onResume() {
        super.onResume();
        if(!backgroundIntent)CzmDownloads.foreground(this);
        foreground = true;
        focus = audio == null || audio.requestAudioFocus(this, AudioManager.STREAM_MUSIC,
                AudioManager.AUDIOFOCUS_GAIN) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
        updateAudio();
        CzmAccount.resume(this);
    }

    @Override protected void onPause() {
        CzmAccount.pause(this);
        CzmLobbyVoice.stop(); // do not capture a microphone in the background
        foreground = false;
        updateAudio();
        if (audio != null) audio.abandonAudioFocus(this);
        focus = false;
        super.onPause();
    }

    @Override public void onAudioFocusChange(int change) {
        focus = change == AudioManager.AUDIOFOCUS_GAIN;
        updateAudio();
    }

    void prepareBackgroundDownload(){
        backgroundIntent=true;
        if(isFinishing()){backgroundIntent=false;CzmDownloads.declined();return;}
        if(android.os.Build.VERSION.SDK_INT>=33&&checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS},1519);return;}
        if(android.os.Build.VERSION.SDK_INT>=24&&!((android.app.NotificationManager)getSystemService(NOTIFICATION_SERVICE)).areNotificationsEnabled()){
            backgroundIntent=false;CzmDownloads.declined();android.widget.Toast.makeText(this,CzmDownloads.ru()?"Разреши уведомления CZM для фоновой загрузки.":"Allow CZM notifications to download in the background.",android.widget.Toast.LENGTH_LONG).show();return;
        }
        CzmDownloads.start(this);
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] grants){
        super.onRequestPermissionsResult(request,permissions,grants);
        if(request==1724){
            CzmLobbyVoice.permissionResult(grants.length>0&&
                grants[0]==android.content.pm.PackageManager.PERMISSION_GRANTED);
            return;
        }
        if(request==1519){if(grants.length>0&&grants[0]==android.content.pm.PackageManager.PERMISSION_GRANTED)CzmDownloads.start(this);else{backgroundIntent=false;CzmDownloads.declined();}}
    }
    @Override protected void onStop(){backgroundIntent=false;super.onStop();}

    @Override public void onDestroy() {
        CzmLobbyVoice.stop();
        CzmAccount.destroy(this);
        ui.removeCallbacksAndMessages(null);
        if (audio != null) audio.abandonAudioFocus(this);
        super.onDestroy();
    }
}
