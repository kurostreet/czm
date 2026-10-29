/* Account-private server preferences, separate from CZM moderation. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.text.TextUtils;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;
import org.libsdl.app.SDLActivity;

final class ServerBlocks {
    private static final String URL = "https://counter-zombie.ru/api/v1/servers/hidden";
    private static final ExecutorService WORK = Executors.newSingleThreadExecutor();
    private static int identity = -1, revision;
    private static long epoch, next;
    private static boolean ready, failed, loading;
    private static String legacy = "";
    private static Set<String> enabled = Collections.emptySet();
    private static JSONArray snapshot = new JSONArray();
    private static CzmDialog editor;

    private static long clock() { return System.nanoTime()/1000000L; }

    private static void observe() {
        int current = CzmAccount.generation();
        if (identity == current) return;
        identity = current; enabled = Collections.emptySet(); snapshot = new JSONArray(); ready = !CzmAccount.hasSession();
        failed = false; next = 0; epoch++; revision++;
    }

    static synchronized int revision() { observe(); return revision; }
    static synchronized boolean hidden(String address) { observe(); return enabled.contains(ServerPolicy.endpoint(address)); }

    private static void apply(JSONObject response, int generation, long sequence) throws Exception {
        if (generation != CzmAccount.generation() || generation != identity || sequence != epoch) return;
        JSONArray list = response.getJSONArray("hidden");
        Set<String> keys = new HashSet<>();
        for (int i=0;i<list.length();i++) {
            JSONObject item = list.getJSONObject(i);
            String address = ServerPolicy.endpoint(item.getString("server"));
            if (address.isEmpty()) throw new IllegalArgumentException("endpoint");
            if (item.getInt("enabled") != 0) keys.add(address);
        }
        if (!keys.equals(enabled)) revision++;
        enabled = Collections.unmodifiableSet(keys); snapshot = list; ready = true; failed = false; next = clock()+30000;
    }

    /** Report success applies its private list immediately; older GET responses cannot undo it. */
    static synchronized void acceptReport(JSONObject response, int generation) throws Exception {
        observe();
        if (generation != identity) return;
        apply(response,generation,++epoch);
    }

    static synchronized void context(String key) { legacy = key == null ? "" : key; refresh(false); }

    static synchronized void refresh(boolean force) {
        observe();
        if (!CzmAccount.hasSession()) { enabled=Collections.emptySet(); ready=true; return; }
        if (force) { epoch++; ready=false; next=0; failed=false; }
        if (loading || legacy.isEmpty() || clock()<next) return;
        final int generation=identity; final long sequence=epoch; final String key=legacy;
        loading=true; next=clock()+30000;
        WORK.execute(() -> {
            try {
                String result=CzmAccount.call(generation,"GET",URL,key,null,"application/json");
                synchronized (ServerBlocks.class) {
                    if (result.startsWith("200\n")) apply(new JSONObject(result.substring(4)),generation,sequence);
                    else if (identity==generation && epoch==sequence) { failed=true; next=clock()+5000; }
                }
            } catch (Exception ignored) {
                synchronized (ServerBlocks.class) { if (identity==generation && epoch==sequence) {failed=true;next=clock()+5000;} }
            } finally { synchronized (ServerBlocks.class) {loading=false;if(!ready&&!failed)next=0;} }
        });
    }

    static synchronized int connectionState(String address) {
        observe();
        if (!CzmAccount.hasSession()) return 1;
        refresh(false);
        if (!ready) return failed&&!loading ? -1 : 0;
        return hidden(address) ? 3 : 1;
    }

    static void show(String key, boolean ru) {
        context(key);
        Context context=SDLActivity.getContext();
        if (!(context instanceof Activity)) return;
        Activity activity=(Activity)context;
        activity.runOnUiThread(() -> {
            if (activity.isFinishing() || (editor!=null&&editor.isShowing())) return;
            CzmDialog dialog=new CzmDialog(activity,ru?"Заблокированные серверы":"Blocked servers",
                ru?"Ваш личный список":"Your personal list",ru?"Обновить":"Refresh",ru?"Закрыть":"Close",ru,false);
            editor=dialog;
            dialog.setOnDismissListener(d -> {if(editor==dialog)editor=null;});
            dialog.submit.setOnClickListener(v -> request(activity,dialog,ru,null));
            dialog.show();request(activity,dialog,ru,null);
        });
    }

    private static void request(Activity activity,CzmDialog dialog,boolean ru,JSONObject body) {
        final int generation; final long sequence; final String key;
        synchronized(ServerBlocks.class){observe();generation=identity;sequence=++epoch;key=legacy;ready=false;failed=false;}
        dialog.busy(true);
        controls(dialog.body,false);
        WORK.execute(() -> {
            String result=CzmAccount.call(generation,body==null?"GET":"POST",URL,key,
                body==null?null:body.toString().getBytes(StandardCharsets.UTF_8),"application/json");
            JSONObject response=null;
            try {
                if(result.startsWith("200\n")){
                    response=new JSONObject(result.substring(4));
                    synchronized(ServerBlocks.class){apply(response,generation,sequence);}
                }
            }catch(Exception ignored){response=null;}
            final JSONObject loaded=response;
            synchronized(ServerBlocks.class){if(loaded==null&&identity==generation&&epoch==sequence){failed=true;next=clock()+5000;}}
            activity.runOnUiThread(() -> {
                if(!dialog.isShowing())return;
                dialog.busy(false);
                if(generation!=CzmAccount.generation()){dialog.dismiss();return;}
                if(loaded==null){
                    JSONArray previous; synchronized(ServerBlocks.class){previous=snapshot;}
                    render(activity,dialog,ru,previous);
                    dialog.fail(ru?"Не удалось сохранить. Обновите список":"Could not save. Refresh the list");return;
                }
                render(activity,dialog,ru,loaded.optJSONArray("hidden"));
            });
        });
    }

    private static void controls(android.view.View view,boolean enabled) {
        view.setEnabled(enabled);
        if(view instanceof android.view.ViewGroup){
            android.view.ViewGroup group=(android.view.ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++)controls(group.getChildAt(i),enabled);
        }
    }

    private static void render(Activity activity,CzmDialog dialog,boolean ru,JSONArray list) {
        dialog.body.setEnabled(true);
        dialog.body.removeAllViews();dialog.body.addView(dialog.error);dialog.error.setEnabled(true);dialog.error.setVisibility(android.view.View.GONE);
        dialog.note(ru?"Вкл — скрывать сервер. Выкл — снова показывать. «Убрать» удаляет запись.":
            "On hides a server. Off shows it again. Remove deletes the entry.");
        if(list==null||list.length()==0){dialog.note(ru?"Список пуст":"The list is empty");return;}
        for(int i=0;i<list.length();i++){
            JSONObject item=list.optJSONObject(i);if(item==null)continue;
            String address=item.optString("server"),name=item.optString("name",address);
            LinearLayout row=new LinearLayout(activity);row.setGravity(android.view.Gravity.CENTER_VERTICAL);
            LinearLayout label=new LinearLayout(activity);label.setOrientation(LinearLayout.VERTICAL);
            TextView title=dialog.text(name.isEmpty()?address:name,14,Color.WHITE);title.setMaxLines(1);title.setEllipsize(TextUtils.TruncateAt.END);
            label.addView(title);label.addView(dialog.text(address,11,CzmDialog.MUTED));
            if(item.optInt("restricted")!=0)label.addView(dialog.text(ru?"Ограничен модерацией CZM":"Restricted by CZM",11,CzmDialog.MUTED));
            row.addView(label,new LinearLayout.LayoutParams(0,-2,1));
            Switch toggle=new Switch(activity);toggle.setTextColor(Color.WHITE);toggle.setTextSize(12);
            toggle.setThumbTintList(new android.content.res.ColorStateList(new int[][]{new int[]{android.R.attr.state_checked},new int[]{}},
                new int[]{CzmDialog.RED,Color.rgb(155,163,177)}));
            toggle.setTrackTintList(new android.content.res.ColorStateList(new int[][]{new int[]{android.R.attr.state_checked},new int[]{}},
                new int[]{Color.rgb(115,35,42),Color.rgb(61,67,80)}));
            toggle.setText(ru?"Скрывать":"Hide");toggle.setChecked(item.optInt("enabled")!=0);
            toggle.setContentDescription((ru?"Скрывать ":"Hide ")+address);
            row.addView(toggle,new LinearLayout.LayoutParams(-2,CzmDialog.dp(activity,48)));
            Button remove=dialog.button(ru?"Убрать":"Remove",false);
            LinearLayout.LayoutParams removeSize=new LinearLayout.LayoutParams(CzmDialog.dp(activity,76),CzmDialog.dp(activity,42));
            removeSize.leftMargin=CzmDialog.dp(activity,8);row.addView(remove,removeSize);
            LinearLayout.LayoutParams rowSize=new LinearLayout.LayoutParams(-1,-2);rowSize.topMargin=CzmDialog.dp(activity,10);dialog.body.addView(row,rowSize);
            toggle.setOnCheckedChangeListener((view,value) -> {
                if(!dialog.submit.isEnabled())return;
                try{JSONObject action=new JSONObject().put("server",address).put("enabled",value);request(activity,dialog,ru,action);}catch(Exception ignored){}
            });
            remove.setOnClickListener(v -> {
                if(!dialog.submit.isEnabled())return;
                try{JSONObject action=new JSONObject().put("server",address).put("remove",true);request(activity,dialog,ru,action);}catch(Exception ignored){}
            });
        }
    }
}
