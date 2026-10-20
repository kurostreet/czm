package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Intent;
import android.widget.EditText;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import org.json.JSONObject;
import org.libsdl.app.SDLActivity;

/** The retired site APK may be used only by an account with private test access. */
final class DistributionAccess {
    private static final ExecutorService WORK = Executors.newSingleThreadExecutor();
    private static boolean refresh;
    static synchronized boolean changed() { boolean value=refresh; refresh=false; return value; }
    private static Activity activity() {
        android.content.Context c=SDLActivity.getContext();
        return c instanceof Activity ? (Activity)c : null;
    }
    static void show(String legacy, String nick, boolean ru) {
        Activity a=activity(); if(a==null)return;
        a.runOnUiThread(()->{
            CzmDialog d=new CzmDialog(a,ru?"Личный тестовый доступ":"Private test access",
                ru?"Сначала войдите в свой игровой аккаунт":"Sign in to your game account first",
                ru?"Активировать":"Activate",ru?"Закрыть":"Close",ru);
            EditText code=d.field(ru?"Личная ссылка или код":"Private link or code",false,256);
            d.link(ru?"Войти в аккаунт":"Sign in",v->{d.dismiss();CzmAccount.show(legacy,nick,ru);});
            d.submit.setOnClickListener(v->{
                String ticket=DevelopmentInvite.parse(code.getText().toString());
                if(ticket.isEmpty()){d.fail(ru?"Проверьте личную ссылку или код.":"Check your private link or code.");return;}
                int generation=CzmAccount.generation();d.busy(true);
                WORK.execute(()->{
                    String result;
                    try {
                        byte[] body=new JSONObject().put("invite",ticket).toString().getBytes(StandardCharsets.UTF_8);
                        result=CzmAccount.call(generation,"POST","https://counter-zombie.ru/api/v1/development/activate",legacy,body,"application/json");
                    } catch(Exception e){result="0\n";}
                    final String response=result;
                    a.runOnUiThread(()->{
                        if(a.isFinishing()||!d.isShowing())return;
                        d.busy(false);
                        if(generation!=CzmAccount.generation()){d.fail(ru?"Аккаунт изменился. Повторите.":"Account changed. Try again.");return;}
                        if(response.startsWith("200\n")){
                            synchronized(DistributionAccess.class){refresh=true;}
                            d.dismiss();
                        } else if(response.startsWith("401\n")) d.fail(ru?"Сначала войдите в игровой аккаунт.":"Sign in to your game account first.");
                        else d.fail(ru?"Ссылка недействительна, уже использована или нет соединения.":"The link is invalid, used, or the connection failed.");
                    });
                });
            });d.show();
        });
    }
    static void help(String legacy,String nick,boolean ru){
        Activity a=activity();if(a==null)return;
        a.runOnUiThread(()->{
            CzmDialog d=new CzmDialog(a,ru?"Переход в Google Play":"Move to Google Play","",ru?"Понятно":"OK",ru?"Закрыть":"Close",ru,false);
            d.note(ru?"1. Откройте counter-zombie.ru/#beta.\n2. Вступите в группу Google и подтвердите участие в бета-тесте.\n3. Установите игру из Google Play.":"1. Open counter-zombie.ru/#beta.\n2. Join the Google group and opt into the beta.\n3. Install the game from Google Play.");
            d.note(ru?"В группе, на странице участия и в Play Маркете должен быть выбран один и тот же Google-аккаунт.":"Use the same Google account in the group, on the opt-in page and in the Play Store.");
            d.note(ru?"Если страницы Google не открываются, может потребоваться VPN. Доступ иногда появляется с задержкой.":"If Google pages do not open, a VPN may be needed. Access can take some time to appear.");
            d.note(ru?"Не удаляйте старую игру до сохранения аккаунта и настроек. Версия Play устанавливается отдельно: войдите в ней в тот же игровой аккаунт.":"Keep the old game until your account and settings are saved. Play installs separately: sign in to the same game account there.");
            d.link(ru?"Аккаунт: вход или регистрация":"Account: sign in or register",v->{d.dismiss();CzmAccount.show(legacy,nick,ru);});
            d.link(ru?"Сохранить настройки в аккаунте":"Save settings to your account",v->{d.dismiss();CzmCloud.show(a,ru);});
            d.link(ru?"Экспортировать раскладку в файл":"Export your control layout",v->{d.dismiss();a.startActivity(new Intent(a,CzmLayoutActivity.class));});
            d.submit.setOnClickListener(v->d.dismiss());d.show();
        });
    }
    private DistributionAccess(){}
}
