package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.os.Handler;
import com.google.mlkit.common.MlKit;
import com.google.mlkit.common.model.RemoteModelManager;
import com.google.mlkit.nl.translate.Translation;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public final class TranslationClientTest {
    private static final Activity ACTIVITY=new Activity();
    private static final List<String> results=new ArrayList<>();
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static void begin(String text,boolean russian){
        CzmTranslator.translate(ACTIVITY,text.getBytes(StandardCharsets.UTF_8),russian,
            CzmAccount.generation(),results::add);
        Handler.flush();
    }
    private static void translate(String text,boolean russian){
        int before=results.size();begin(text,russian);Translation.complete();
        check(results.size()==before+1&&results.get(before).startsWith("200\n"),"translation must complete once");
    }
    public static void main(String[] args){
        if(args[0].equals("failure")){
            MlKit.failNext=true;begin("First initialization fails",true);
            check(results.size()==1&&results.get(0).equals("0\n"),"initialization error must be recoverable");
            for(int i=0;i<20;i++)translate("Retry message "+i,true);
            check(MlKit.initializations==1&&MlKit.attempts==2,"retry only an unsuccessful initialization");
        }else{
            android.os.Build.VERSION.SDK_INT=21;begin("Unsupported phone",true);
            check(results.get(0).equals("400\n")&&MlKit.attempts==0,"unsupported API must not initialize");
            android.os.Build.VERSION.SDK_INT=35;
            for(int i=0;i<30;i++)translate("Different English message "+i,true);
            translate("Сообщение по-русски",false);
            check(MlKit.initializations==1&&MlKit.attempts==1,"one SDK context for all messages and languages");
            check(Translation.clients.size()==2,"reuse one client in each direction");

            Handler.advance(30001);
            check(Translation.clients.stream().allMatch(c->c.closed),"idle clients should close");
            translate("Translation after idle cleanup",true);
            CzmTranslator.close();Handler.flush();
            translate("Translation after activity recreation",true);
            check(MlKit.attempts==1,"client cleanup must not reset the process SDK context");

            int before=results.size();
            for(int i=0;i<5;i++)begin("Parallel request "+i,true);
            check(results.size()==before+1&&results.get(before).equals("429\n"),"limit active work");
            Translation.complete();check(results.size()==before+5,"all accepted requests finish");

            begin("Old account request",true);CzmAccount.current++;Translation.complete();
            check(results.get(results.size()-1).equals("409\n"),"discard old account result");
            begin("Request interrupted by activity destruction",true);
            CzmTranslator.close();Handler.flush();before=results.size();Translation.complete();
            check(results.size()==before&&results.get(before-1).equals("499\n"),"ignore late completion after close");

            RemoteModelManager.downloaded=false;
            begin("Download cancelled",true);CzmDialog.latest.dismiss();
            check(results.get(results.size()-1).equals("499\n"),"download cancellation");
            begin("Download accepted",true);CzmDialog.latest.accept();Translation.complete();
            check(results.get(results.size()-1).startsWith("200\n"),"download retry");
            check(MlKit.attempts==1,"cancellation must not reinitialize the SDK");

            begin("Slow translation",true);Handler.advance(120001);before=results.size();
            check(results.get(before-1).equals("0\n"),"timeout");
            Translation.complete();check(results.size()==before,"ignore timed-out result");
            translate("Translation after timeout",true);
        }
        System.out.println("TRANSLATION_CLIENT_OK "+args[0]);
    }
}
