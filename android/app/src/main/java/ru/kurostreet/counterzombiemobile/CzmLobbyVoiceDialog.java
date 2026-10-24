package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.ScrollView;
import org.libsdl.app.SDLActivity;

/** Small native sound panel. Its PCM buffer belongs only to this open dialog. */
final class CzmLobbyVoiceDialog {
    private static Dialog current;
    private static final int INK=Color.rgb(239,243,248),MUTED=Color.rgb(155,166,184),GREEN=Color.rgb(107,218,167);
    private static final Handler UI=new Handler(Looper.getMainLooper());
    private CzmLobbyVoiceDialog(){}
    private static boolean preferencesLoaded;
    static synchronized void loadPreferences(){
        Context c=SDLActivity.getContext();if(preferencesLoaded||c==null)return;
        CzmLobbyAudio.sensitivity=Math.max(0,Math.min(100,c.getSharedPreferences("czm_lobby_voice",Context.MODE_PRIVATE).getInt("sensitivity",50)));
        preferencesLoaded=true;
    }
    private static String t(String ru,String en){return CzmDownloads.ru()?ru:en;}
    private static int dp(Context c,int n){return (int)(c.getResources().getDisplayMetrics().density*n+.5f);}
    private static GradientDrawable fill(Context c,int color){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(c,8));d.setStroke(dp(c,1),Color.rgb(51,62,78));return d;}
    private static TextView text(Context c,String label,int size,int color){TextView v=new TextView(c);v.setText(label);v.setTextSize(size);v.setTextColor(color);v.setFontFeatureSettings("kern");return v;}
    private static Button button(Context c,String label){Button b=new Button(c);b.setText(label);b.setTextSize(14);b.setTextColor(INK);b.setAllCaps(false);b.setMinHeight(dp(c,42));b.setMinimumWidth(0);b.setBackground(fill(c,Color.rgb(28,36,48)));return b;}
    static void show(){
        Context context=SDLActivity.getContext();if(!(context instanceof Activity))return;
        Activity a=(Activity)context;a.runOnUiThread(()->{
            if(a.isFinishing()||current!=null)return;
            if(!CzmLobbyMicTest.open())return;
            final Dialog dialog=new Dialog(a);current=dialog;dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
            LinearLayout body=new LinearLayout(a);body.setOrientation(LinearLayout.VERTICAL);
            int pad=dp(a,14);body.setPadding(pad,pad,pad,pad);body.setBackground(fill(a,Color.rgb(14,20,29)));
            TextView title=text(a,t("Проверка микрофона","Microphone check"),21,INK);title.setTypeface(Typeface.DEFAULT,Typeface.BOLD);body.addView(title);
            TextView hint=text(a,t("Проверку слышишь только ты · Запись до 3 секунд","Only you can hear this check · Up to 3 seconds"),13,MUTED);
            LinearLayout.LayoutParams hintLayout=new LinearLayout.LayoutParams(-1,-2);hintLayout.topMargin=dp(a,8);body.addView(hint,hintLayout);
            TextView status=text(a,"",14,MUTED);LinearLayout.LayoutParams statusLayout=new LinearLayout.LayoutParams(-1,-2);statusLayout.topMargin=dp(a,14);body.addView(status,statusLayout);
            ProgressBar meter=new ProgressBar(a,null,android.R.attr.progressBarStyleHorizontal);meter.setMax(100);meter.setProgressTintList(ColorStateList.valueOf(GREEN));
            LinearLayout.LayoutParams meterLayout=new LinearLayout.LayoutParams(-1,dp(a,10));meterLayout.topMargin=dp(a,8);body.addView(meter,meterLayout);
            SharedPreferences prefs=a.getSharedPreferences("czm_lobby_voice",Context.MODE_PRIVATE);
            CzmLobbyAudio.sensitivity=Math.max(0,Math.min(100,prefs.getInt("sensitivity",50)));
            TextView sensitivity=text(a,"",13,MUTED);LinearLayout.LayoutParams sensLayout=new LinearLayout.LayoutParams(-1,-2);sensLayout.topMargin=dp(a,14);body.addView(sensitivity,sensLayout);
            SeekBar slider=new SeekBar(a);slider.setMax(100);slider.setProgress(CzmLobbyAudio.sensitivity);slider.setProgressTintList(ColorStateList.valueOf(GREEN));slider.setThumbTintList(ColorStateList.valueOf(INK));
            slider.setPadding(0,dp(a,4),0,dp(a,4));body.addView(slider,new LinearLayout.LayoutParams(-1,dp(a,36)));
            slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
                public void onProgressChanged(SeekBar b,int value,boolean user){CzmLobbyAudio.sensitivity=value;sensitivity.setText(t("Чувствительность: ","Sensitivity: ")+value+"%");}
                public void onStartTrackingTouch(SeekBar b){}
                public void onStopTrackingTouch(SeekBar b){prefs.edit().putInt("sensitivity",b.getProgress()).apply();CzmLobbyVoice.sensitivityChanged();}
            });sensitivity.setText(t("Чувствительность: ","Sensitivity: ")+CzmLobbyAudio.sensitivity+"%");
            LinearLayout buttons=new LinearLayout(a);buttons.setGravity(Gravity.CENTER_VERTICAL);
            Button record=button(a,""),listen=button(a,t("Прослушать","Listen")),close=button(a,t("Закрыть","Close"));
            for(Button b:new Button[]{record,listen,close}){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(a,44),1);if(b!=record)p.leftMargin=dp(a,8);buttons.addView(b,p);}
            LinearLayout.LayoutParams rowLayout=new LinearLayout.LayoutParams(-1,-2);rowLayout.topMargin=dp(a,14);body.addView(buttons,rowLayout);
            record.setOnClickListener(v->{if(CzmLobbyMicTest.phase()==CzmLobbyMicTest.RECORDING)CzmLobbyMicTest.stopRecording();else CzmLobbyMicTest.record();});
            listen.setOnClickListener(v->CzmLobbyMicTest.play());close.setOnClickListener(v->dialog.dismiss());
            ScrollView scroll=new ScrollView(a);scroll.addView(body);dialog.setContentView(scroll);dialog.setCanceledOnTouchOutside(true);
            final Runnable refresh=new Runnable(){public void run(){
                if(current!=dialog||!dialog.isShowing())return;
                if(!CzmLobbyMicTest.opened()){dialog.dismiss();return;}
                int phase=CzmLobbyMicTest.phase();meter.setProgress(CzmLobbyMicTest.level());
                String message=phase==CzmLobbyMicTest.RECORDING?t("Говори… запись до 3 секунд","Speak… recording up to 3 seconds"):
                    phase==CzmLobbyMicTest.PLAYING?t("Прослушивание записи","Playing your recording"):
                    phase==CzmLobbyMicTest.PERMISSION?t("Разреши доступ к микрофону","Allow microphone access"):
                    phase==CzmLobbyMicTest.DENIED?t("Нет разрешения на микрофон","Microphone permission denied"):
                    phase==CzmLobbyMicTest.UNAVAILABLE?t("Микрофон или звук недоступен. Проверь разрешения и другие приложения.","Microphone or audio unavailable. Check permissions and other apps."):
                    phase==CzmLobbyMicTest.NO_SIGNAL?t("Сигнал не получен. Повтори проверку.","No input received. Try again."):
                    phase==CzmLobbyMicTest.READY?(CzmLobbyMicTest.heard()?t("Сигнал есть · Можно прослушать","Input detected · Ready to listen"):t("Записана тишина · Говори громче или увеличь чувствительность","Recording is quiet · Speak louder or increase sensitivity")):
                    t("Нажми «Записать 3 сек» и скажи несколько слов","Tap Record 3 sec and say a few words");
                if(CzmLobbyVoice.state()==3)message+=" · "+t("Голос: переподключение","Voice: reconnecting");
                status.setText(message);status.setTextColor(CzmLobbyMicTest.heard()?GREEN:MUTED);
                record.setText(phase==CzmLobbyMicTest.RECORDING?t("Остановить","Stop"):t("Записать 3 сек","Record 3 sec"));
                record.setEnabled(phase!=CzmLobbyMicTest.PLAYING&&phase!=CzmLobbyMicTest.PERMISSION);
                listen.setEnabled(CzmLobbyMicTest.hasRecording()&&phase!=CzmLobbyMicTest.RECORDING&&phase!=CzmLobbyMicTest.PLAYING&&phase!=CzmLobbyMicTest.PERMISSION);
                UI.postDelayed(this,80);
            }};
            dialog.setOnDismissListener(d->{UI.removeCallbacks(refresh);if(current==dialog)current=null;CzmLobbyMicTest.close();});
            dialog.show();Window w=dialog.getWindow();if(w!=null){
                w.setBackgroundDrawableResource(android.R.color.transparent);
                w.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                int width=Math.min(dp(a,550),a.getResources().getDisplayMetrics().widthPixels-dp(a,36));w.setLayout(width,WindowManager.LayoutParams.WRAP_CONTENT);
            }
            refresh.run();
        });
    }
}
