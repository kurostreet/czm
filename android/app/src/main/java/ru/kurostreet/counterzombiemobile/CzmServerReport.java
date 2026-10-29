/* A compact complaint form; moderation stays in the owner's bot. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.widget.EditText;
import android.widget.CheckBox;
import android.widget.Toast;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;
import org.json.JSONArray;
import org.libsdl.app.SDLActivity;

final class CzmServerReport {
    private static final ExecutorService WORK = Executors.newSingleThreadExecutor();
    private static CzmDialog editor;

    static void show(String address, String name, String key, boolean ru) {
        Context context = SDLActivity.getContext();
        if (!(context instanceof Activity) || ServerPolicy.endpoint(address).isEmpty()) return;
        Activity activity = (Activity)context;
        activity.runOnUiThread(() -> {
            if (activity.isFinishing() || (editor != null && editor.isShowing())) return;
            final int generation = CzmAccount.generation();
            final String[] nonce = {CzmNet.newKey()}, previous = {""};
            CzmDialog dialog = new CzmDialog(activity, ru ? "Заблокировать сервер" : "Block server",
                name + " · " + address, ru ? "ОК" : "OK", ru ? "Отмена" : "Cancel", ru);
            editor = dialog;
            dialog.note(ru ? "Укажите причину — можно выбрать несколько" : "Choose one or more reasons");
            String[] codes = {"sexual", "hate", "harassment", "copyright", "spam"};
            String[] labels = ru ? new String[]{"Сексуальный контент", "Нацизм или разжигание ненависти",
                "Оскорбления и травля", "Нарушение авторских прав", "Спам или обман"}
                : new String[]{"Sexual content", "Nazism or hate", "Harassment", "Copyright", "Spam or scam"};
            CheckBox[] reasons = new CheckBox[codes.length];
            for(int i=0;i<codes.length;i++){
                CheckBox choice=new CheckBox(activity);choice.setText(labels[i]);choice.setTextSize(14);
                choice.setTextColor(android.graphics.Color.WHITE);choice.setMinHeight(CzmDialog.dp(activity,44));
                choice.setButtonTintList(android.content.res.ColorStateList.valueOf(CzmDialog.RED));
                reasons[i]=choice;dialog.body.addView(choice);
            }
            EditText comment = dialog.field(ru ? "Своя причина (необязательно)" : "Your own reason (optional)", false, 300);
            dialog.note(ru ? "Сервер скроется у вас, а причины получит модератор" : "The server will be hidden for you; reasons go to moderation");
            dialog.note(ru ? "Подтверждённая почта: одна жалоба на этот сервер раз в 30 дней" : "Verified email: one report for this server every 30 days");
            android.widget.Button account = dialog.link(ru ? "Аккаунт и почта" : "Account and email",v -> { dialog.dismiss(); CzmAccount.showContext(key,ru); });
            dialog.setOnDismissListener(d -> { if (editor == dialog) editor = null; });
            dialog.submit.setOnClickListener(v -> {
                JSONObject body = new JSONObject();
                try {
                    JSONArray selected=new JSONArray();
                    for(int i=0;i<reasons.length;i++)if(reasons[i].isChecked())selected.put(codes[i]);
                    String own=comment.getText().toString().trim();
                    if(selected.length()==0&&own.isEmpty()){dialog.fail(ru?"Выберите причину или напишите свою":"Choose a reason or enter your own");return;}
                    if(selected.length()==0)selected.put("other");
                    body.put("server", address); body.put("name", name.length() > 128 ? name.substring(0,128) : name);
                    body.put("reasons",selected);body.put("comment",own);
                    String payload = body.toString();
                    if (!previous[0].isEmpty() && !previous[0].equals(payload)) nonce[0] = CzmNet.newKey();
                    previous[0] = payload; body.put("nonce", nonce[0]);
                } catch (Exception ignored) { return; }
                dialog.busy(true);
                for(CheckBox reason:reasons)reason.setEnabled(false);comment.setEnabled(false);account.setEnabled(false);
                WORK.execute(() -> {
                    String response = CzmAccount.call(generation, "POST",
                        "https://counter-zombie.ru/api/v1/servers/report", key,
                        body.toString().getBytes(StandardCharsets.UTF_8), "application/json");
                    activity.runOnUiThread(() -> {
                        if (!dialog.isShowing()) return;
                        dialog.busy(false);
                        for(CheckBox reason:reasons)reason.setEnabled(true);comment.setEnabled(true);account.setEnabled(true);
                        if (generation != CzmAccount.generation()) { dialog.dismiss(); return; }
                        if (response.startsWith("200\n")) {
                            try { ServerBlocks.acceptReport(new JSONObject(response.substring(4)),generation); } catch(Exception ignored) {}
                            dialog.dismiss();
                            Toast.makeText(activity, ru ? "Сервер скрыт у вас. Жалоба принята" : "Server hidden. Report received", Toast.LENGTH_SHORT).show();
                        } else dialog.fail(response.startsWith("429\n") && response.contains("server_report_cooldown")
                            ? (ru ? "С одной почты на этот сервер можно пожаловаться раз в 30 дней" : "One email can report this server once every 30 days")
                            : response.startsWith("429\n") ? (ru ? "Слишком часто. Попробуйте позже" : "Too often. Try later")
                            : response.startsWith("403\n") && response.contains("email_required") ? (ru ? "Привяжите и подтвердите почту: «Аккаунт и почта»" : "Link and verify your email in Account and email")
                            : response.startsWith("403\n") && response.contains("banned") ? (ru ? "Отправка жалоб для аккаунта ограничена" : "Reporting is restricted for this account")
                            : response.startsWith("403\n") || response.startsWith("401\n") ? (ru ? "Войдите в аккаунт CZM" : "Sign in to CZM")
                            : (ru ? "Не удалось отправить. Повторите" : "Could not send. Try again"));
                    });
                });
            });
            dialog.show();
        });
    }
}
