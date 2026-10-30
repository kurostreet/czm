/* On-device RU/EN translation, started only by an explicit message action. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import com.google.mlkit.common.model.DownloadConditions;
import com.google.mlkit.common.MlKit;
import com.google.mlkit.common.model.RemoteModelManager;
import com.google.mlkit.nl.translate.TranslateLanguage;
import com.google.mlkit.nl.translate.TranslateRemoteModel;
import com.google.mlkit.nl.translate.Translation;
import com.google.mlkit.nl.translate.Translator;
import com.google.mlkit.nl.translate.TranslatorOptions;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import org.json.JSONObject;

final class CzmTranslator {
    interface Done { void complete(String response); }
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private static final ArrayList<Job> JOBS=new ArrayList<>();
    private static Translator toRussian,toEnglish;
    private static CzmDialog prompt;
    private static boolean ready,preparing;
    private static int lifecycle;
    private static final Runnable RELEASE=()->{
        if(!JOBS.isEmpty())return;
        if(toRussian!=null)toRussian.close();if(toEnglish!=null)toEnglish.close();
        toRussian=toEnglish=null;
    };
    private static final class Job {
        final String text;final boolean russian;final int generation;final Done done;
        boolean finished;
        Job(String t,boolean r,int g,Done d){text=t;russian=r;generation=g;done=d;}
        void finish(String response){
            if(finished)return;finished=true;JOBS.remove(this);
            done.complete(generation==CzmAccount.generation()?response:"409\n");
            MAIN.removeCallbacks(RELEASE);MAIN.postDelayed(RELEASE,30000);
        }
    }
    static boolean available(){return Build.VERSION.SDK_INT>=23;}
    static void translate(Context context,byte[] input,boolean russian,int generation,Done done){
        if(!available()||input==null||input.length==0||input.length>1603){done.complete("400\n");return;}
        final String text=new String(input,StandardCharsets.UTF_8);
        MAIN.post(()->{
            if(generation!=CzmAccount.generation()){done.complete("409\n");return;}
            if(!(context instanceof Activity)||((Activity)context).isFinishing()){done.complete("499\n");return;}
            if(JOBS.size()>=4){done.complete("429\n");return;}
            MAIN.removeCallbacks(RELEASE);
            MlKit.initialize(context.getApplicationContext());
            Job job=new Job(text,russian,generation,done);JOBS.add(job);
            MAIN.postDelayed(()->{
                job.finish("0\n");
                if(JOBS.isEmpty()&&prompt!=null){CzmDialog previous=prompt;prompt=null;preparing=false;previous.dismiss();}
            },120000);
            if(ready){run(job);return;}
            if(preparing)return;preparing=true;final int version=lifecycle;
            TranslateRemoteModel model=new TranslateRemoteModel.Builder(TranslateLanguage.RUSSIAN).build();
            RemoteModelManager.getInstance().isModelDownloaded(model)
                .addOnSuccessListener(downloaded->{
                    if(version!=lifecycle)return;
                    if(JOBS.isEmpty()){preparing=false;return;}
                    if(downloaded){download(version);return;}
                    Activity activity=(Activity)context;
                    if(activity.isFinishing()){finishAll("499\n");return;}
                    CzmDialog dialog=new CzmDialog(activity,russian?"Перевод сообщений":"Message translation","Google Translate",
                        russian?"Скачать":"Download",russian?"Отмена":"Cancel",russian,false);
                    prompt=dialog;final boolean[] accepted={false};
                    dialog.note(russian?
                        "Для перевода RU ↔ EN нужен языковой пакет около 30 МБ. Можно скачать по Wi-Fi или мобильной сети. После загрузки текст переводится на устройстве и не отправляется в Google.":
                        "RU ↔ EN translation needs a language pack of about 30 MB. Download over Wi-Fi or mobile data. Once installed, text is translated on your device and is not sent to Google.");
                    dialog.setOnDismissListener(d->{if(prompt==dialog)prompt=null;if(!accepted[0])finishAll("499\n");});
                    dialog.submit.setOnClickListener(v->{accepted[0]=true;dialog.dismiss();download(version);});
                    dialog.show();
                }).addOnFailureListener(e->{if(version==lifecycle)finishAll("0\n");});
        });
    }
    private static Translator client(boolean russian){
        if(russian&&toRussian!=null)return toRussian;
        if(!russian&&toEnglish!=null)return toEnglish;
        Translator client=Translation.getClient(new TranslatorOptions.Builder()
            .setSourceLanguage(russian?TranslateLanguage.ENGLISH:TranslateLanguage.RUSSIAN)
            .setTargetLanguage(russian?TranslateLanguage.RUSSIAN:TranslateLanguage.ENGLISH).build());
        if(russian)toRussian=client;else toEnglish=client;return client;
    }
    private static void download(int version){
        // A missing pack is downloaded only after the explicit dialog above.
        client(true).downloadModelIfNeeded(new DownloadConditions.Builder().build())
            .addOnSuccessListener(v->{
                if(version!=lifecycle)return;ready=true;preparing=false;
                for(Job job:new ArrayList<>(JOBS))run(job);
            }).addOnFailureListener(e->{if(version==lifecycle)finishAll("0\n");});
    }
    private static void run(Job job){
        if(job.finished)return;
        if(job.generation!=CzmAccount.generation()){job.finish("409\n");return;}
        client(job.russian).translate(job.text).addOnSuccessListener(text->{
            try{job.finish("200\n"+new JSONObject().put("text",text).toString());}
            catch(Exception ignored){job.finish("0\n");}
        }).addOnFailureListener(e->job.finish("0\n"));
    }
    private static void finishAll(String result){preparing=false;for(Job job:new ArrayList<>(JOBS))job.finish(result);}
    static void close(){
        MAIN.post(()->{
            lifecycle++;ready=preparing=false;
            MAIN.removeCallbacks(RELEASE);
            if(prompt!=null){CzmDialog previous=prompt;prompt=null;previous.dismiss();}
            finishAll("499\n");
            if(toRussian!=null)toRussian.close();if(toEnglish!=null)toEnglish.close();
            toRussian=toEnglish=null;
        });
    }
}
