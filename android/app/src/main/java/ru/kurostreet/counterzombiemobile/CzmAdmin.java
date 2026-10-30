/* Account-scoped head administrator panel. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.Toast;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;
import org.libsdl.app.SDLActivity;

final class CzmAdmin {
    private static final ExecutorService WORK=Executors.newSingleThreadExecutor();
    private static final String BASE="https://counter-zombie.ru/api/v1/";
    private static CzmAdmin opened;
    private final Activity activity;private final String key;private final boolean ru;private final int generation;
    private final CzmDialog dialog;private Screen screen=new Screen("overview",0,"",0);private int serial;
    private static final class Screen {
        final String page,query;final int target,offset;
        Screen(String p,int t,String q,int o){page=p;target=t;query=q;offset=o;}
    }
    interface Done {void run(JSONObject value);}
    private String L(String russian,String english){return ru?russian:english;}
    private static JSONObject data(Object... values){
        JSONObject result=new JSONObject();try{for(int i=0;i<values.length;i+=2)result.put((String)values[i],values[i+1]);}catch(Exception ignored){}
        return result;
    }
    private static JSONObject object(JSONObject value,String name){JSONObject result=value.optJSONObject(name);return result==null?new JSONObject():result;}
    private static JSONArray array(JSONObject value,String name){JSONArray result=value.optJSONArray(name);return result==null?new JSONArray():result;}
    private static String encode(String value){try{return URLEncoder.encode(value,"UTF-8");}catch(Exception ignored){return "";}}
    private static String roles(JSONArray list){StringBuilder out=new StringBuilder();for(int i=0;i<list.length();i++){if(i>0)out.append(" · ");out.append(list.optString(i));}return out.toString();}
    private String stamp(long seconds){if(seconds<=0)return "—";SimpleDateFormat f=new SimpleDateFormat("dd.MM HH:mm",Locale.ROOT);f.setTimeZone(TimeZone.getTimeZone("Europe/Moscow"));return f.format(new Date(seconds*1000));}
    private CzmAdmin(Activity a,String k,boolean r){
        activity=a;key=k;ru=r;generation=CzmAccount.generation();
        dialog=new CzmDialog(a,L("Админ-панель","Admin panel"),"CZM",L("Обновить","Refresh"),L("Закрыть","Close"),r,false);
        dialog.setOnDismissListener(d->{if(opened==this)opened=null;});
    }
    static void show(String mode,String key,boolean ru){
        Context context=SDLActivity.getContext();if(!(context instanceof Activity))return;Activity activity=(Activity)context;
        activity.runOnUiThread(()->{
            if(activity.isFinishing()||(opened!=null&&opened.dialog.isShowing()))return;
            CzmAdmin admin=new CzmAdmin(activity,key,ru);opened=admin;admin.dialog.show();
            admin.open(mode.startsWith("admin-server/")?new Screen("server",0,mode.substring(13),0):new Screen("overview",0,"",0));
        });
    }
    private boolean live(){if(!dialog.isShowing())return false;if(generation!=CzmAccount.generation()){dialog.dismiss();return false;}return true;}
    private static void enabled(View view,boolean value){view.setEnabled(value);if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)enabled(group.getChildAt(i),value);}}
    private void clear(){dialog.body.removeAllViews();dialog.body.addView(dialog.error);dialog.error.setVisibility(View.GONE);}
    private void back(Runnable run){dialog.cancel.setText(L("Назад","Back"));dialog.cancel.setOnClickListener(v->run.run());}
    private void link(String text,Runnable run){dialog.link(text,v->{if(live())run.run();});}
    private void pair(String first,Runnable one,String second,Runnable two){
        Button a=dialog.link(first,v->{if(live())one.run();});Button b=dialog.link(second,v->{if(live())two.run();});
        dialog.body.removeView(a);dialog.body.removeView(b);LinearLayout row=new LinearLayout(activity);row.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams left=new LinearLayout.LayoutParams(0,CzmDialog.dp(activity,48),1);left.setMargins(0,0,CzmDialog.dp(activity,6),0);
        row.addView(a,left);row.addView(b,new LinearLayout.LayoutParams(0,CzmDialog.dp(activity,48),1));dialog.body.addView(row);
    }
    private String failure(String response){
        String code="";try{code=new JSONObject(response.substring(response.indexOf('\n')+1)).optString("error");}catch(Exception ignored){}
        if(code.equals("admin_required"))return L("Доступ главного администратора не подтверждён сервером","The server has not granted head administrator access");
        if(code.equals("reason"))return L("Укажите причину","Enter a reason");
        if(code.equals("batch")||code.equals("nonce"))return L("Данные изменились. Обновите страницу и проверьте заново","The data changed. Refresh and review again");
        if(code.equals("not_found")||code.equals("account_not_found"))return L("Игрок не найден","Player not found");
        if(code.equals("moderator_required"))return L("Модератор или его история не найдены","Moderator or history not found");
        if(code.equals("server")||code.equals("server_address"))return L("Нужен публичный IP:порт","Enter a public IP:port");
        if(code.equals("staff")||code.equals("self"))return L("Это действие запрещено для выбранного аккаунта","This action is not allowed for that account");
        if(response.startsWith("401\n"))return L("Сеанс истёк. Войдите снова","Session expired. Sign in again");
        if(response.startsWith("429\n"))return L("Слишком часто. Повторите позже","Too often. Try again later");
        return L("Не удалось выполнить запрос. Повторите","Request failed. Try again");
    }
    private void request(String method,String path,JSONObject body,Done done){
        if(!live())return;final int ticket=++serial;dialog.busy(true);enabled(dialog.body,false);
        WORK.execute(()->{
            String response=CzmAccount.call(generation,method,BASE+path,key,body==null?null:body.toString().getBytes(StandardCharsets.UTF_8),"application/json");
            activity.runOnUiThread(()->{
                if(!live()||ticket!=serial)return;dialog.busy(false);enabled(dialog.body,true);
                if(response.startsWith("200\n"))try{done.run(new JSONObject(response.substring(4)));return;}catch(Exception ignored){}
                dialog.fail(failure(response));
            });
        });
    }
    private void go(String page){open(new Screen(page,0,"",0));}
    private void player(int id){open(new Screen("player",id,"",0));}
    private void server(String endpoint){open(new Screen("server",0,endpoint,0));}
    private void open(Screen next){
        if(!live())return;screen=next;clear();dialog.note(L("Загружаем…","Loading…"));
        dialog.submit.setText(L("Обновить","Refresh"));dialog.submit.setOnClickListener(v->open(screen));
        if(next.page.equals("overview")){dialog.cancel.setText(L("Закрыть","Close"));dialog.cancel.setOnClickListener(v->dialog.dismiss());}
        else back(()->go("overview"));
        String path="admin/"+next.page+"?target="+next.target+"&query="+encode(next.query)+"&offset="+next.offset;
        request("GET",path,null,value->{clear();render(next,value);});
    }
    private void pages(Screen current,int next){
        int step=current.page.equals("moderator")?10:current.page.equals("servers")?25:current.page.equals("reports")||current.page.equals("moderation_history")?30:20;
        if(current.offset>0)link(L("← Предыдущая страница","← Previous page"),()->open(new Screen(current.page,current.target,current.query,Math.max(0,current.offset-step))));
        if(next>=0)link(L("Следующая страница →","Next page →"),()->open(new Screen(current.page,current.target,current.query,next)));
    }
    private void render(Screen current,JSONObject value){
        switch(current.page){
        case "overview":overview(value);break;
        case "players":players(current,value);break;
        case "player":playerCard(value);break;
        case "servers":servers(current,value);break;
        case "server":serverCard(value);break;
        case "moderators":moderators(value);break;
        case "moderator":moderator(current,value);break;
        case "reports":reports(current,value);break;
        case "sanctions":sanctions(current,value);break;
        default:history(current,value);break;
        }
    }
    private void overview(JSONObject v){
        dialog.note(L("Аккаунты: ","Accounts: ")+v.optInt("accounts")+L(" · Игроки: "," · Players: ")+v.optInt("players")+
            L("\nЗа последние 2 минуты: ","\nSeen in the last 2 minutes: ")+v.optInt("recent_players")+
            L("\nЖалобы на игроков: ","\nPlayer reports: ")+v.optInt("reports_open")+L(" · Ограничения: "," · Sanctions: ")+v.optInt("sanctions_active")+
            L("\nЗаблокировано серверов: ","\nRestricted servers: ")+v.optInt("servers_blocked")+L(" · Модераторов на паузе: "," · Paused moderators: ")+v.optInt("moderators_paused"));
        pair(L("Игроки и роли","Players and roles"),()->go("players"),L("Серверы","Servers"),()->go("servers"));
        pair(L("Жалобы на игроков","Player reports"),()->go("reports"),L("Модераторы","Moderators"),()->go("moderators"));
        pair(L("Действующие наказания","Active sanctions"),()->go("sanctions"),L("История действий","Action history"),()->go("history"));
        JSONObject development=object(v,"development");JSONArray play=array(v,"play");
        dialog.note("DEV: "+development.optString("version","—")+" · "+development.optInt("code")+
            "\nGoogle Play: "+(play.length()>0?objectAt(play,0).optInt("code"):"—"));
        link(L("Возможности моего аккаунта","My account tools"),()->{dialog.dismiss();CzmCommunity.show("hub",0,key,ru);});
    }
    private static JSONObject objectAt(JSONArray list,int index){JSONObject value=list.optJSONObject(index);return value==null?new JSONObject():value;}
    private void players(Screen current,JSONObject v){
        EditText query=dialog.field(L("Ник, логин или ID","Nickname, login or ID"),false,100);query.setText(current.query);
        dialog.submit.setText(L("Найти","Search"));dialog.submit.setOnClickListener(button->open(new Screen("players",0,query.getText().toString().trim(),0)));
        JSONArray list=array(v,"players");if(list.length()==0)dialog.note(L("Игроки не найдены","No players found"));
        for(int i=0;i<list.length();i++){
            JSONObject p=objectAt(list,i);int id=p.optInt("id");String role=roles(array(p,"roles"));
            link(p.optString("nick")+" · ID "+id+(role.isEmpty()?"":"\n"+role),()->player(id));
        }
        pages(current,v.optInt("next",-1));
    }
    private void playerCard(JSONObject p){
        int id=p.optInt("id");JSONObject state=object(p,"moderation");
        dialog.note(p.optString("nick")+" · ID "+id+"\n"+roles(array(p,"roles"))+
            (p.optBoolean("account")?"\n"+p.optString("login"):L("\nГость","\nGuest")));
        if(p.optBoolean("account")){
            String[] names={"moderator","tester","server_owner"};String[] labels={"Moderator","Official Tester CZM","Server owner"};
            JSONArray active=array(p,"roles");
            for(int i=0;i<names.length;i++){
                final String role=names[i],label=labels[i];boolean has=false;for(int n=0;n<active.length();n++)if(role.equals(active.optString(n)))has=true;
                final boolean revoke=has;
                link((has?L("Снять ","Revoke "):L("Выдать ","Grant "))+label,()->roleForm(p,role,label,revoke));
            }
            if(!p.optString("project").isEmpty())link(L("Изменить название проекта","Edit project name"),()->roleForm(p,"server_owner","Server owner",false));
        }
        JSONArray owned=array(p,"servers");for(int i=0;i<owned.length();i++){
            String address=objectAt(owned,i).optString("server");
            link(address,()->server(address));
            link(L("Убрать IP из профиля","Remove IP from profile"),()->confirm(data("action","owner_server_remove","target",id,"server",address),address,false,false));
        }
        if(!state.optBoolean("protected")){
            pair(L("Предупредить","Warn"),()->punish(id,"warn",0),L("Отключить текст","Mute text"),()->punish(id,"mute_text",0));
            pair(L("Отключить голос","Mute voice"),()->punish(id,"mute_voice",0),L("Заблокировать игрока","Ban player"),()->punish(id,"ban",0));
            pair(L("Сбросить фото и аватар","Reset photo and avatar"),()->punish(id,"remove_avatar",0),L("Запретить своё фото","Restrict custom photo"),()->punish(id,"restrict_photo",0));
            link(L("Закрыть лобби игрока","Close the player's lobby"),()->punish(id,"close_lobby",0));
        }
        if(roles(array(p,"roles")).contains("moderator"))link(L("Контроль модератора","Moderator controls"),()->open(new Screen("moderator",id,"",0)));
        JSONObject ban=state.optJSONObject("ban");if(ban!=null)dialog.note(L("Блокировка: ","Ban: ")+ban.optString("reason"));
        JSONArray sanctions=array(p,"sanctions");
        for(int i=0;i<sanctions.length();i++)sanction(objectAt(sanctions,i));
    }
    private void roleForm(JSONObject player,String role,String label,boolean revoke){
        Screen previous=screen;clear();String title=(revoke?L("Снять ","Revoke "):L("Выдать ","Grant "))+label;
        dialog.note(title+"\n"+player.optString("nick")+" · ID "+player.optInt("id"));
        final EditText project=!revoke&&role.equals("server_owner")?dialog.field(L("Название проекта","Project name"),false,32):null;
        if(project!=null)project.setText(player.optString("project"));
        back(()->open(previous));dialog.submit.setText(L("Подтвердить","Confirm"));final String[] nonce={CzmNet.newKey()},last={""};
        dialog.submit.setOnClickListener(button->{
            if(project!=null&&project.getText().toString().trim().isEmpty()){dialog.fail(L("Укажите название проекта","Enter a project name"));return;}
            JSONObject body=data("action",revoke?"role_revoke":"role_grant","target",player.optInt("id"),"role",role,"project",project==null?"":project.getText().toString().trim());
            String payload=body.toString();if(!last[0].isEmpty()&&!last[0].equals(payload))nonce[0]=CzmNet.newKey();last[0]=payload;
            try{body.put("nonce",nonce[0]);}catch(Exception ignored){}
            apply(body,previous);
        });
    }
    private String actionName(String action){
        if(action.equals("role_grant")||action.equals("grant"))return L("Выдача роли","Grant role");
        if(action.equals("role_revoke")||action.equals("revoke"))return L("Снятие роли","Revoke role");
        String[] keys={"warn","mute_text","mute_voice","ban","remove_avatar","restrict_photo","close_lobby","delete_message","dismiss","lift","server_ban","server_unban","mod_pause","mod_resume","mod_undo","owner_server_remove"};
        String[] russian={"Предупреждение","Отключение текста","Отключение голоса","Блокировка игрока","Сброс аватара","Запрет фото","Закрытие лобби","Удаление контента","Отклонение жалобы","Снятие наказания","Блокировка сервера в CZM","Разблокировка сервера","Приостановка прав","Возврат прав после проверки","Отмена действий модератора","Удаление IP из профиля"};
        String[] english={"Warning","Mute text","Mute voice","Player ban","Reset avatar","Restrict photo","Close lobby","Remove content","Dismiss report","Lift sanction","Restrict server in CZM","Restore server","Pause moderator","Resume after review","Undo moderator actions","Remove profile IP"};
        for(int i=0;i<keys.length;i++)if(keys[i].equals(action))return ru?russian[i]:english[i];return action;
    }
    private String reviewState(String value){
        if(value.equals("pending"))return L("На проверке","Awaiting review");
        if(value.equals("approved"))return L("Проверено","Reviewed");
        if(value.equals("reverted"))return L("Отменено","Reverted");return "";
    }
    private void punish(int target,String action,int report){
        JSONObject body=data("action",action,"target",target);if(report>0)try{body.put("report",report);}catch(Exception ignored){}
        boolean duration=action.equals("ban")||action.equals("mute_text")||action.equals("mute_voice")||action.equals("restrict_photo");
        confirm(body,"ID "+target,true,duration);
    }
    private void confirm(JSONObject template,String description,boolean needsReason,boolean duration){
        Screen previous=screen;clear();String action=template.optString("action");dialog.note(actionName(action)+"\n"+description);
        if(action.equals("mod_undo"))dialog.note(L("Поздние решения других администраторов сохранятся. Права модератора останутся приостановлены.","Later decisions by other administrators are preserved. Moderator permissions remain paused."));
        final EditText reason=needsReason?dialog.field(L("Причина","Reason"),false,200):null;final int[] minutes={10080};
        if(duration){
            final int[] values={60,1440,10080,43200,0};final String[] labels={L("1 час","1 hour"),L("1 день","1 day"),L("7 дней","7 days"),L("30 дней","30 days"),L("Навсегда","Forever")};
            final int count=action.equals("ban")||action.equals("restrict_photo")?5:4;final Button[] buttons=new Button[count];
            for(int i=0;i<count;i++){final int index=i;buttons[i]=dialog.link((values[i]==minutes[0]?"✓ ":"")+labels[i],v->{minutes[0]=values[index];for(int n=0;n<count;n++)buttons[n].setText((values[n]==minutes[0]?"✓ ":"")+labels[n]);});}
        }
        back(()->open(previous));dialog.submit.setText(L("Подтвердить","Confirm"));final String[] nonce={CzmNet.newKey()},last={""};
        dialog.submit.setOnClickListener(button->{
            if(reason!=null&&reason.getText().toString().trim().isEmpty()){dialog.fail(L("Укажите причину","Enter a reason"));return;}
            try{
                JSONObject body=new JSONObject(template.toString());if(reason!=null)body.put("reason",reason.getText().toString().trim());if(duration)body.put("minutes",minutes[0]);
                String payload=body.toString();if(!last[0].isEmpty()&&!last[0].equals(payload))nonce[0]=CzmNet.newKey();last[0]=payload;body.put("nonce",nonce[0]);apply(body,previous);
            }catch(Exception ignored){}
        });
    }
    private void apply(JSONObject body,Screen previous){
        request("POST","admin/action",body,result->{ServerOwners.INSTANCE.invalidate();Toast.makeText(activity,L("Выполнено","Done"),Toast.LENGTH_SHORT).show();open(previous);});
    }
    private void servers(Screen current,JSONObject v){
        EditText address=dialog.field("IP:port",false,64);address.setText(current.query);
        dialog.submit.setText(L("Открыть","Open"));dialog.submit.setOnClickListener(button->server(address.getText().toString().trim()));
        JSONArray cases=array(v,"servers");dialog.note(L("Жалобы и ограничения","Reports and restrictions"));
        for(int i=0;i<cases.length();i++){
            JSONObject entry=objectAt(cases,i);String endpoint=entry.optString("server");
            link(entry.optString("name",endpoint)+"\n"+endpoint+L(" · Жалоб: "," · Reports: ")+entry.optInt("count")+((entry.optBoolean("blocked")||entry.optInt("blocked")!=0)?L(" · Заблокирован"," · Restricted"):""),()->server(endpoint));
        }
        JSONArray projects=array(v,"projects");if(projects.length()>0)dialog.note(L("Серверы проектов","Project servers"));
        for(int i=0;i<projects.length();i++){
            JSONObject entry=objectAt(projects,i);String endpoint=entry.optString("server");link(endpoint+" · "+entry.optString("project"),()->server(endpoint));
        }
        pages(current,v.optInt("next",-1));
    }
    private void serverCard(JSONObject v){
        String endpoint=v.optString("server");dialog.note(v.optString("name")+"\n"+endpoint+L("\nЖалоб: ","\nReports: ")+v.optInt("count")+L(" · Заявителей: "," · Reporters: ")+v.optInt("reporters")+
            (v.optBoolean("blocked")?L("\nОграничен в CZM: ","\nRestricted in CZM: ")+v.optString("reason"):L("\nДоступен в CZM","\nAvailable in CZM")));
        boolean blocked=v.optBoolean("blocked");link(blocked?L("Разблокировать для всех","Restore for everyone"):L("Заблокировать для всех","Restrict for everyone"),()->confirm(data("action",blocked?"server_unban":"server_ban","server",endpoint),endpoint,!blocked,false));
        JSONArray owners=array(v,"owners");for(int i=0;i<owners.length();i++){
            JSONObject owner=objectAt(owners,i);int id=owner.optInt("id");link(L("Владелец: ","Owner: ")+owner.optString("nick")+" · ID "+id+"\n"+owner.optString("project"),()->player(id));
        }
        JSONArray reports=array(v,"reports");for(int i=0;i<reports.length();i++){
            JSONObject r=objectAt(reports,i);dialog.note(stamp(r.optLong("created"))+" · "+r.optString("nick")+" · ID "+r.optInt("reporter")+
                L(" · Всего жалоб автора: "," · Author total reports: ")+r.optInt("author_total")+"\n"+r.optString("reason")+"\n"+r.optString("comment"));
        }
        JSONArray history=array(v,"history");for(int i=0;i<history.length();i++){
            JSONObject r=objectAt(history,i);dialog.note(stamp(r.optLong("created"))+" · "+r.optString("actor")+" · "+r.optString("action")+"\n"+r.optString("reason"));
        }
    }
    private void moderators(JSONObject v){
        EditText id=dialog.field(L("ID модератора, включая удалённого","Moderator ID, including deleted accounts"),false,10);
        dialog.submit.setText(L("Открыть","Open"));dialog.submit.setOnClickListener(button->{try{open(new Screen("moderator",Integer.parseInt(id.getText().toString().trim()),"",0));}catch(Exception ignored){dialog.fail(L("Укажите ID","Enter an ID"));}});
        JSONArray list=array(v,"moderators");if(list.length()==0)dialog.note(L("Модераторов пока нет","No moderators yet"));
        for(int i=0;i<list.length();i++){
            JSONObject m=objectAt(list,i);int target=m.optInt("player");link(m.optString("nick")+" · ID "+target+"\n"+m.optInt("count")+"/10"+(m.optBoolean("paused")?L(" · На паузе"," · Paused"):L(" · Активен"," · Active")),()->open(new Screen("moderator",target,"",0)));
        }
    }
    private void moderator(Screen current,JSONObject m){
        int target=m.optInt("player");dialog.note(m.optString("nick")+" · ID "+target+
            L("\nНа проверку: ","\nAwaiting review: ")+m.optInt("count")+"/10"+L(" · Всего: "," · Total: ")+m.optInt("total")+
            L("\nБанов: ","\nBans: ")+m.optInt("bans_total")+L(" · За сутки: "," · Last 24h: ")+m.optInt("bans_day")+
            "\n"+stamp(m.optLong("first"))+" — "+stamp(m.optLong("last"))+" МСК"+(m.optBoolean("paused")?L("\nПрава приостановлены","\nPermissions paused"):""));
        if(m.optBoolean("has_role"))pair(L("Приостановить","Pause"),()->confirm(data("action","mod_pause","target",target),"ID "+target,false,false),L("Проверено: вернуть права","Reviewed: resume"),()->confirm(data("action","mod_resume","target",target),"ID "+target,false,false));
        if(m.optInt("count")>0)link(L("Приостановить и отменить серию","Pause and undo current batch"),()->undoPreview(target,false));
        if(object(m,"reviewable").optInt("count")>0)link(L("Приостановить и отменить всю историю","Pause and undo all history"),()->undoPreview(target,true));
        JSONArray list=array(m,"history");for(int i=0;i<list.length();i++){
            JSONObject r=objectAt(list,i);dialog.note(stamp(r.optLong("created"))+" · "+actionName(r.optString("action"))+" · ID "+r.optInt("target")+" · "+reviewState(r.optString("state"))+"\n"+r.optString("reason"));
        }
        pages(current,m.optInt("next",-1));
    }
    private void undoPreview(int target,boolean all){
        request("POST","admin/action",data("action","mod_pause","target",target,"nonce",CzmNet.newKey()),paused->
            request("GET","admin/moderator?target="+target,null,m->{
                JSONObject scope=object(m,"reviewable");int count=all?scope.optInt("count"):m.optInt("count");
                JSONObject body=data("action","mod_undo","target",target,"all_history",all,"batch",m.optInt("batch"),"expected_log",all?scope.optLong("last_log"):m.optLong("batch_last_log"));
                confirm(body,m.optString("nick")+" · ID "+target+L("\nДействий к отмене: ","\nActions to undo: ")+count,false,false);
            }));
    }
    private void reports(Screen current,JSONObject v){
        JSONArray list=array(v,"reports");if(list.length()==0)dialog.note(L("Открытых жалоб нет","No open reports"));
        for(int i=0;i<list.length();i++){
            JSONObject report=objectAt(list,i),target=object(report,"target");
            link("#"+report.optInt("id")+" · "+target.optString("nick")+" · ID "+target.optInt("id")+"\n"+report.optString("evidence"),()->report(report));
        }
        pages(current,v.optInt("next",-1));
    }
    private void report(JSONObject r){
        Screen previous=screen;clear();JSONObject target=object(r,"target");int id=target.optInt("id"),report=r.optInt("id");
        dialog.note("#"+report+" · "+target.optString("nick")+" · ID "+id+"\n"+r.optString("context")+"\n"+r.optString("evidence"));
        if(target.optString("avatar").startsWith("photo")){dialog.note(L("Текущее фото профиля","Current profile photo"));photo(id);}
        String remove=r.optString("kind").equals("profile")?"remove_avatar":r.optString("kind").equals("lobby")?"close_lobby":"delete_message";
        pair(L("Удалить контент","Remove content"),()->punish(id,remove,report),L("Предупредить","Warn"),()->punish(id,"warn",report));
        pair(L("Отключить текст","Mute text"),()->punish(id,"mute_text",report),L("Заблокировать игрока","Ban player"),()->punish(id,"ban",report));
        link(L("Отклонить жалобу","Dismiss report"),()->punish(id,"dismiss",report));
        link(L("Управление игроком и ролями","Manage player and roles"),()->player(id));
        back(()->open(previous));dialog.submit.setText(L("К списку","Back to list"));dialog.submit.setOnClickListener(button->open(previous));
    }
    private void photo(int player){
        final int version=serial;ImageView preview=new ImageView(activity);preview.setAdjustViewBounds(true);preview.setScaleType(ImageView.ScaleType.FIT_CENTER);
        dialog.body.addView(preview,new LinearLayout.LayoutParams(-1,CzmDialog.dp(activity,180)));
        WORK.execute(()->{
            Bitmap image=null;HttpURLConnection connection=null;
            try{
                connection=(HttpURLConnection)new URL("https://counter-zombie.ru/avatars/"+player+".png").openConnection();
                connection.setConnectTimeout(8000);connection.setReadTimeout(8000);connection.setInstanceFollowRedirects(false);connection.setUseCaches(false);
                if(connection.getResponseCode()==200){
                    ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(InputStream input=connection.getInputStream()){
                        byte[] buffer=new byte[8192];int n;while((n=input.read(buffer))!=-1){if(bytes.size()+n>1048576)throw new java.io.IOException();bytes.write(buffer,0,n);}
                    }
                    byte[] raw=bytes.toByteArray();BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(raw,0,raw.length,bounds);
                    if(bounds.outWidth>0&&bounds.outHeight>0&&(long)bounds.outWidth*bounds.outHeight<=4000000)image=BitmapFactory.decodeByteArray(raw,0,raw.length);
                }
            }catch(Exception|OutOfMemoryError ignored){}finally{if(connection!=null)connection.disconnect();}
            final Bitmap result=image;activity.runOnUiThread(()->{if(!live()||version!=serial){if(result!=null)result.recycle();return;}if(result!=null)preview.setImageBitmap(result);});
        });
    }
    private void sanctions(Screen current,JSONObject v){
        JSONArray list=array(v,"sanctions");if(list.length()==0)dialog.note(L("Действующих наказаний нет","No active sanctions"));
        for(int i=0;i<list.length();i++){
            sanction(objectAt(list,i));
        }
        pages(current,v.optInt("next",-1));
    }
    private void sanction(JSONObject sanction){
        JSONObject target=object(sanction,"target");int id=sanction.optInt("id");
        String kind=sanction.optString("kind");String label=kind.equals("text")?L("Текст","Text"):kind.equals("voice")?L("Голос","Voice"):kind.equals("photo")?L("Фото","Photo"):L("Блокировка","Ban");
        String description=target.optString("nick")+" · ID "+target.optInt("id")+" · "+label+"\n"+sanction.optString("reason")+"\n"+(sanction.optBoolean("forever")?L("Навсегда","Forever"):stamp(sanction.optLong("until")));
        dialog.note(description);link(L("Снять наказание","Lift sanction"),()->confirm(data("action","lift","sanction",id,"target",target.optInt("id")),description,false,false));
    }
    private void history(Screen current,JSONObject v){
        pair(L("Действия админки","Panel actions"),()->go("history"),L("Модерация","Moderation"),()->go("moderation_history"));
        link(L("Назначение ролей","Role assignments"),()->go("role_history"));
        JSONArray list=array(v,current.page.equals("role_history")?"roles":current.page.equals("moderation_history")?"history":"actions");
        if(list.length()==0)dialog.note(L("Записей пока нет","No records yet"));
        for(int i=0;i<list.length();i++){
            JSONObject r=objectAt(list,i);String detail=r.optString("detail");try{JSONObject body=new JSONObject(detail);detail=body.optString("reason")+" "+body.optString("role")+" "+body.optString("project")+" "+body.optString("server");}catch(Exception ignored){}
            JSONObject target=object(r,"target"),moderator=object(r,"moderator");
            String who=current.page.equals("moderation_history")?"ID "+moderator.optInt("id"):r.optString("actor");
            String subject=current.page.equals("moderation_history")?"ID "+target.optInt("id"):"ID "+r.optInt(current.page.equals("role_history")?"player":"target");
            dialog.note(stamp(r.optLong("created"))+" · "+who+" · "+actionName(r.optString("action"))+" · "+subject+"\n"+r.optString("reason")+" "+r.optString("role")+" "+detail);
        }
        pages(current,v.optInt("next",-1));
    }
}
