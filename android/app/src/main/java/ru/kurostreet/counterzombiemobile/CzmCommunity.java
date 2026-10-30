/* Community tools use account-scoped requests and selected files only. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Toast;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;
import org.libsdl.app.SDLActivity;

final class CzmCommunity {
    private static final String BASE="https://counter-zombie.ru/api/v1/";
    private static final ExecutorService WORK=Executors.newSingleThreadExecutor();
    private static CzmDialog editor;
    private static TicketForm ticket;

    private static boolean live(CzmDialog dialog,int generation) {
        if(!dialog.isShowing())return false;
        if(generation!=CzmAccount.generation()){dialog.dismiss();return false;}
        return true;
    }
    private static void controls(android.view.View view,boolean enabled) {
        view.setEnabled(enabled);
        if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++)controls(group.getChildAt(i),enabled);}
    }
    private static void clear(CzmDialog dialog) {
        dialog.body.removeAllViews();dialog.body.addView(dialog.error);dialog.error.setVisibility(android.view.View.GONE);
    }
    private static String error(String response,boolean ru) {
        String code="";try{code=new JSONObject(response.substring(response.indexOf('\n')+1)).optString("error");}catch(Exception ignored){}
        if(code.equals("telegram"))return ru?"Укажите @имя или ссылку https://t.me/имя":"Enter @username or https://t.me/username";
        if(code.equals("role_contact_disabled"))return ru?"Для аккаунтов с ролью контакт Telegram скрыт":"Telegram contact is hidden for role accounts";
        if(code.equals("servers_limit"))return ru?"Можно добавить не больше пяти серверов":"You can add up to five servers";
        if(code.equals("server_blocked"))return ru?"Сервер ограничен модерацией CZM":"CZM moderation restricted this server";
        if(code.equals("server")||code.equals("server_address"))return ru?"Укажите публичный IP и порт":"Enter a public IP and port";
        if(code.equals("tester_required"))return ru?"Нужна роль Official Tester CZM":"Official Tester CZM role required";
        if(code.equals("server_owner_required"))return ru?"Нужна роль Server owner":"Server owner role required";
        if(code.equals("photo")||code.equals("attachment")||code.equals("text_file"))return ru?"Проверьте фото и текстовый файл UTF-8":"Check the photo and UTF-8 text file";
        if(code.equals("ticket"))return ru?"Заполните тему и описание":"Enter a subject and description";
        if(code.equals("rules"))return ru?"Примите правила сообщества в игре":"Accept the community rules in the game";
        if(response.startsWith("429\n"))return ru?"Слишком часто. Повторите позже":"Too often. Try later";
        if(response.startsWith("401\n")||response.startsWith("403\n"))return ru?"Войдите в аккаунт с нужной ролью":"Sign in with the required role";
        return ru?"Нет связи. Повторите":"Connection failed. Try again";
    }
    interface Done {void run(JSONObject value);}
    private static void request(Activity activity,CzmDialog dialog,int generation,String key,String method,String path,JSONObject body,boolean ru,Done done) {
        if(!live(dialog,generation))return;
        dialog.busy(true);controls(dialog.body,false);
        WORK.execute(() -> {
            String response=CzmAccount.call(generation,method,BASE+path,key,body==null?null:body.toString().getBytes(StandardCharsets.UTF_8),"application/json");
            activity.runOnUiThread(() -> {
                if(!live(dialog,generation))return;
                dialog.busy(false);controls(dialog.body,true);
                if(response.startsWith("200\n"))try{
                    if(method.equals("POST")&&path.equals("community/servers"))ServerOwners.INSTANCE.invalidate();
                    done.run(new JSONObject(response.substring(4)));return;
                }catch(Exception ignored){}
                dialog.fail(error(response,ru));
            });
        });
    }
    static void show(String mode,int target,String key,boolean ru) {
        Context context=SDLActivity.getContext();if(!(context instanceof Activity))return;
        Activity activity=(Activity)context;final int generation=CzmAccount.generation();
        if(mode.equals("admin")||mode.startsWith("admin-server/")){CzmAdmin.show(mode,key,ru);return;}
        if(mode.equals("telegram")){
            WORK.execute(() -> {
                String response=CzmAccount.call(generation,"GET",BASE+"social/profile/"+target,key,null,"application/json");
                activity.runOnUiThread(() -> {
                    if(generation!=CzmAccount.generation()||activity.isFinishing())return;
                    try{
                        String link=new JSONObject(response.substring(4)).getJSONObject("profile").getString("telegram");
                        if(!response.startsWith("200\n")||!link.matches("https://t\\.me/[A-Za-z][A-Za-z0-9_]{3,31}"))throw new Exception();
                        activity.startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(link)));
                    }catch(Exception ignored){Toast.makeText(activity,ru?"Контакт недоступен":"Contact unavailable",Toast.LENGTH_SHORT).show();}
                });
            });return;
        }
        activity.runOnUiThread(() -> {
            if(activity.isFinishing()||(editor!=null&&editor.isShowing())||generation!=CzmAccount.generation())return;
            String title=mode.equals("ticket")?(ru?"Тикет тестировщика":"Tester ticket"):mode.equals("servers")?(ru?"Серверы проекта":"Project servers"):(ru?"Сообщество":"Community");
            CzmDialog dialog=new CzmDialog(activity,title,"",ru?"Повторить":"Retry",ru?"Закрыть":"Close",ru,false);
            editor=dialog;dialog.setOnDismissListener(d -> {if(editor==dialog)editor=null;if(ticket!=null&&ticket.dialog==dialog)ticket=null;});
            dialog.submit.setOnClickListener(v -> {if(live(dialog,generation)){dialog.dismiss();show(mode,target,key,ru);}});
            dialog.note(ru?"Загружаем…":"Loading…");dialog.show();
            request(activity,dialog,generation,key,"GET","community/me",null,ru,me -> {
                if(mode.equals("ticket")){
                    JSONObject caps=me.optJSONObject("capabilities");
                    if(caps==null||!caps.optBoolean("tester")){dialog.fail(error("403\n{\"error\":\"tester_required\"}",ru));return;}
                    ticket=new TicketForm(activity,dialog,generation,key,ru);ticket.render();
                }else if(mode.equals("servers")){
                    request(activity,dialog,generation,key,"GET","community/servers",null,ru,data -> servers(activity,dialog,generation,key,ru,data));
                }else hub(activity,dialog,generation,key,ru,me);
            });
        });
    }
    private static void hub(Activity activity,CzmDialog dialog,int generation,String key,boolean ru,JSONObject me) {
        clear(dialog);
        JSONArray roles=me.optJSONArray("roles");boolean tagged=roles!=null&&roles.length()>0;
        dialog.submit.setText(tagged?(ru?"Готово":"Done"):(ru?"Сохранить":"Save"));
        final EditText contact;
        if(!tagged){
            dialog.note(ru?"Необязательный контакт виден в вашей карточке игрока":"Your optional contact is shown on your player card");
            contact=dialog.field(ru?"Telegram: @имя или https://t.me/имя":"Telegram: @username or https://t.me/username",false,100);
            contact.setText(me.optString("telegram"));
            dialog.note(ru?"Оставьте поле пустым, чтобы убрать кнопку":"Leave empty to remove the button");
        }else{contact=null;dialog.note(ru?"Возможности аккаунта":"Account tools");dialog.submit.setText(ru?"Готово":"Done");}
        JSONObject capabilities=me.optJSONObject("capabilities");
        if(capabilities!=null&&capabilities.optBoolean("admin"))dialog.link(ru?"Админ-панель":"Admin panel",v -> {if(live(dialog,generation)){dialog.dismiss();show("admin",0,key,ru);}});
        if(capabilities!=null&&capabilities.optBoolean("tester"))dialog.link(ru?"Передать тикет тестировщика":"Submit tester ticket",v -> {if(live(dialog,generation)){dialog.dismiss();show("ticket",0,key,ru);}});
        if(capabilities!=null&&capabilities.optBoolean("server_owner"))dialog.link(ru?"Мои серверы проекта":"My project servers",v -> {if(live(dialog,generation)){dialog.dismiss();show("servers",0,key,ru);}});
        dialog.submit.setOnClickListener(v -> {
            if(contact==null){dialog.dismiss();return;}
            try{JSONObject body=new JSONObject().put("telegram",contact.getText().toString());
                request(activity,dialog,generation,key,"POST","community/contact",body,ru,result -> {dialog.dismiss();Toast.makeText(activity,ru?"Контакт сохранён":"Contact saved",Toast.LENGTH_SHORT).show();});
            }catch(Exception ignored){}
        });
    }
    private static void servers(Activity activity,CzmDialog dialog,int generation,String key,boolean ru,JSONObject data) {
        clear(dialog);dialog.submit.setText(ru?"Добавить":"Add");
        dialog.note(ru?"До пяти серверов. Название запрашивается у сервера; если он не отвечает, показывается IP":"Up to five servers. Names come from the server; an offline server shows its IP");
        EditText address=dialog.field(ru?"IP:порт (без порта — 27015)":"IP:port (default port: 27015)",false,64);
        dialog.submit.setOnClickListener(v -> {
            try{JSONObject body=new JSONObject().put("server",address.getText().toString().trim());
                request(activity,dialog,generation,key,"POST","community/servers",body,ru,result -> servers(activity,dialog,generation,key,ru,result));
            }catch(Exception ignored){}
        });
        JSONArray list=data.optJSONArray("servers");if(list==null)return;
        for(int i=0;i<list.length();i++){
            JSONObject row=list.optJSONObject(i);if(row==null)continue;
            String endpoint=row.optString("server");dialog.note(row.optString("name",endpoint)+"\n"+endpoint+(row.optInt("restricted")!=0?(ru?" · Ограничен CZM":" · Restricted by CZM"):""));
            dialog.link(ru?"Убрать сервер":"Remove server",v -> {
                try{JSONObject body=new JSONObject().put("server",endpoint).put("remove",true);
                    request(activity,dialog,generation,key,"POST","community/servers",body,ru,result -> servers(activity,dialog,generation,key,ru,result));
                }catch(Exception ignored){}
            });
        }
    }
    private static final class TicketForm {
        final Activity activity;final CzmDialog dialog;final int generation;final String key;final boolean ru;
        EditText subject,description;Button photoButton,fileButton;byte[] photo,file;String fileName="",nonce=CzmNet.newKey(),previous="";
        TicketForm(Activity a,CzmDialog d,int g,String k,boolean r){activity=a;dialog=d;generation=g;key=k;ru=r;}
        void render(){
            clear(dialog);dialog.submit.setText(ru?"Отправить":"Send");
            dialog.note("Official Tester CZM");
            subject=dialog.field(ru?"Тема":"Subject",false,100);
            description=dialog.field(ru?"Что произошло и как повторить":"What happened and steps to reproduce",false,2000);
            description.setSingleLine(false);description.setMinLines(3);description.setGravity(android.view.Gravity.TOP|android.view.Gravity.START);
            description.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
            description.setLayoutParams(new LinearLayout.LayoutParams(-1,CzmDialog.dp(activity,92)));
            photoButton=dialog.link(ru?"Приложить фото":"Attach photo",v -> pick("photo"));
            fileButton=dialog.link(ru?"Приложить текстовый файл":"Attach text file",v -> pick("text"));
            dialog.link(ru?"Убрать вложения":"Clear attachments",v -> {photo=null;file=null;fileName="";labels();});
            dialog.note(ru?"Отправляются только выбранные файлы: фото и текст UTF-8 до 64 КБ. Тикет получит главный администратор":"Only selected files are sent: a photo and a UTF-8 text file up to 64 KB. The main administrator receives the ticket");
            dialog.submit.setOnClickListener(v -> send());
        }
        void labels(){photoButton.setText(photo==null?(ru?"Приложить фото":"Attach photo"):(ru?"Фото приложено":"Photo attached"));fileButton.setText(file==null?(ru?"Приложить текстовый файл":"Attach text file"):fileName);}
        void pick(String kind){
            if(!live(dialog,generation))return;
            Intent intent=new Intent(activity,CzmTicketPickerActivity.class);intent.putExtra("kind",kind);intent.putExtra("generation",generation);activity.startActivity(intent);
        }
        void send(){
            if(!live(dialog,generation))return;
            if(subject.getText().toString().trim().isEmpty()||description.getText().toString().trim().isEmpty()){dialog.fail(ru?"Заполните тему и описание":"Enter a subject and description");return;}
            try{
                JSONObject body=new JSONObject().put("subject",subject.getText().toString()).put("text",description.getText().toString());
                if(photo!=null)body.put("photo",android.util.Base64.encodeToString(photo,android.util.Base64.NO_WRAP));
                if(file!=null)body.put("text_file",android.util.Base64.encodeToString(file,android.util.Base64.NO_WRAP)).put("file_name",fileName);
                String payload=body.toString();if(!previous.isEmpty()&&!previous.equals(payload))nonce=CzmNet.newKey();previous=payload;body.put("nonce",nonce);
                request(activity,dialog,generation,key,"POST","community/tickets",body,ru,result -> {dialog.dismiss();Toast.makeText(activity,ru?"Тикет #"+result.optInt("id")+" принят":"Ticket #"+result.optInt("id")+" received",Toast.LENGTH_LONG).show();});
            }catch(Exception ignored){}
        }
    }
    static void selected(Activity picker,Uri uri,String kind,int generation) {
        final TicketForm form=ticket;if(form==null||form.generation!=generation||generation!=CzmAccount.generation()){picker.finish();return;}
        WORK.execute(() -> {
            byte[] selected=null;String name="report.txt";
            try{
                int limit=kind.equals("photo")?5*1024*1024:64*1024;
                ByteArrayOutputStream out=new ByteArrayOutputStream();
                try(InputStream input=picker.getContentResolver().openInputStream(uri)){
                    if(input==null)throw new java.io.IOException();byte[] buffer=new byte[8192];int n;
                    while((n=input.read(buffer))!=-1){if(out.size()+n>limit)throw new java.io.IOException();out.write(buffer,0,n);}
                }
                selected=out.toByteArray();
                if(kind.equals("photo")){
                    BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(selected,0,selected.length,bounds);
                    if(bounds.outWidth<1||bounds.outHeight<1||(long)bounds.outWidth*bounds.outHeight>20000000L)throw new java.io.IOException();
                    BitmapFactory.Options options=new BitmapFactory.Options();options.inSampleSize=1;
                    while(Math.max(bounds.outWidth,bounds.outHeight)/options.inSampleSize>1280)options.inSampleSize*=2;
                    Bitmap bitmap=BitmapFactory.decodeByteArray(selected,0,selected.length,options);if(bitmap==null)throw new java.io.IOException();
                    try{out.reset();bitmap.compress(Bitmap.CompressFormat.JPEG,82,out);selected=out.toByteArray();}finally{bitmap.recycle();}
                    if(selected.length>1024*1024)throw new java.io.IOException();
                }else{
                    String text=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(selected)).toString();
                    if(text.indexOf('\0')>=0)throw new java.io.IOException();
                    try(android.database.Cursor cursor=picker.getContentResolver().query(uri,new String[]{android.provider.OpenableColumns.DISPLAY_NAME},null,null,null)){
                        if(cursor!=null&&cursor.moveToFirst())name=cursor.getString(0);
                    }
                    if(name==null||!name.toLowerCase(java.util.Locale.ROOT).endsWith(".txt"))name="report.txt";
                }
            }catch(Exception|OutOfMemoryError ignored){selected=null;}
            final byte[] result=selected;final String fileName=name;
            picker.runOnUiThread(picker::finish);
            form.activity.runOnUiThread(() -> {
                if(ticket!=form||!live(form.dialog,generation))return;
                if(result==null){form.dialog.fail(form.ru?"Не удалось прочитать файл. Фото до 5 МБ, текст UTF-8 до 64 КБ":"Could not read file. Photo up to 5 MB; UTF-8 text up to 64 KB");return;}
                if(kind.equals("photo"))form.photo=result;else{form.file=result;form.fileName=fileName;}
                form.labels();
            });
        });
    }
}
