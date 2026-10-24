/* Account forms, HTTPS sessions and game-thread profile handoff. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.text.InputType;
import android.view.View;
import android.widget.EditText;
import android.widget.Toast;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;
import org.libsdl.app.SDLActivity;

final class CzmAccount {
    private static final String API = "https://counter-zombie.ru/api/v1/auth/";
    private static final ExecutorService WORK = Executors.newSingleThreadExecutor();
    private static String token = "", event = "";
    private static boolean loaded, synced;
    private static int generation;
    private static CzmDialog editor;
    private static final java.util.Map<String,Long> mailAt=new java.util.HashMap<>();
    private static Activity foregroundActivity;
    private static String profileKey = "", profileNick = "";
    private static boolean contextReady, russian;
    private CzmAccount() {}

    static boolean serviceUrl(String address) {
        try {
            URL url = new URL(address);
            return url.getProtocol().equals("https") && (url.getPort() == -1 || url.getPort() == 443)
                && url.getUserInfo() == null && (url.getHost().equals("counter-zombie.ru") || url.getHost().equals("kontrafps.ru"));
        } catch (Exception e) { return false; }
    }

    private static synchronized void load() {
        if (loaded) return;
        Context ctx = SDLActivity.getContext();
        if (ctx == null) return;
        try { token = CzmServerAuth.session(ctx); }
        catch (Exception e) { token = ""; } // The UI can replace an unreadable session by logging in again.
        loaded = true;
    }

    /** Java-only credential for the authenticated lobby socket; never sent to JNI. */
    static synchronized String lobbyVoiceKey(String url) {
        if(!serviceUrl(url))return "";
        load();return token;
    }

    static synchronized int generation() { load(); return generation; }

    private static JSONObject object(String response) throws Exception {
        int line = response.indexOf('\n');
        if (line < 0) throw new IllegalArgumentException();
        return new JSONObject(response.substring(line + 1));
    }
    private static int status(String response) {
        try { return Integer.parseInt(response.substring(0, response.indexOf('\n'))); }
        catch (Exception e) { return 0; }
    }
    private static String raw(String action, String credential, JSONObject body) {
        return CzmNet.call("POST", API + action, credential, body.toString().getBytes(StandardCharsets.UTF_8), "application/json");
    }
    private static synchronized void profile(JSONObject profile) {
        event = new JSONObject().toString();
        try { event = new JSONObject().put("profile", profile).toString(); }
        catch (Exception ignored) {}
        synced = true;
        CzmCloud.account(profile.optInt("id"));
    }
    private static synchronized void clear(String expected) throws Exception {
        if (!token.equals(expected)) return;
        CzmServerAuth.session(SDLActivity.getContext(), "");
        token = ""; synced = false; ++generation; event = "{\"guest\":true}";
        CzmCloud.clear();
        clearPendingPassword(SDLActivity.getContext());
    }
    private static void expired(String expected) {
        try { clear(expected); } catch (Exception ignored) {}
    }

    /** Native receives public profile data only. Session tokens never enter cfg, cvars or userinfo. */
    static synchronized byte[] event() {
        load();
        if (event.isEmpty()) return null;
        byte[] result = event.getBytes(StandardCharsets.UTF_8); event = ""; return result;
    }

    /** Captured generation prevents an old request from being attributed to a new account. */
    static String call(int expectedGeneration, String method, String url, String legacy, byte[] body, String contentType) {
        final String credential;
        final boolean needsSync, hello;
        synchronized (CzmAccount.class) {
            load();
            if (expectedGeneration != generation) return "409\n";
            credential = token;
            hello = serviceUrl(url) && url.endsWith("/api/v1/hello");
            needsSync = hello && !credential.isEmpty() && !synced;
        }
        if (needsSync) {
            String me = raw("me", credential, new JSONObject());
            synchronized (CzmAccount.class) {
                if (!token.equals(credential) || generation != expectedGeneration) return "409\n";
                try { if (status(me) == 200) profile(object(me)); }
                catch (Exception ignored) { return "0\n"; }
            }
            if (status(me) == 401) expired(credential);
            return status(me) == 200 ? "409\n" : me;
        }
        String key = legacy;
        if (!credential.isEmpty() && serviceUrl(url) && (hello || (legacy != null && !legacy.isEmpty()))) {
            key = credential;
            synchronized (CzmAccount.class) { if (hello && !event.isEmpty()) return "409\n"; }
            if (hello) {
                try { body = new JSONObject(new String(body, StandardCharsets.UTF_8)).put("key", credential).toString().getBytes(StandardCharsets.UTF_8); }
                catch (Exception e) { return "0\n"; }
            }
        }
        String result = CzmNet.call(method, url, key, body, contentType);
        synchronized (CzmAccount.class) { if (generation != expectedGeneration) return "409\n"; }
        if (status(result) == 401 && !credential.isEmpty()) expired(credential);
        else if (hello && status(result) == 401) {
            synchronized (CzmAccount.class) { event = "{\"guest\":true}"; ++generation; }
        }
        return result;
    }

    private static String error(String code, boolean ru) {
        switch (code) {
        case "credentials": return ru ? "Неверный ник для входа или пароль." : "Incorrect login or password.";
        case "taken": return ru ? "Этот ник для входа уже занят." : "This login is already taken.";
        case "nick": return ru ? "Ник: 2–24 символа, без команд и служебных знаков." : "Login: 2–24 characters, no commands or control characters.";
        case "password": return ru ? "Пароль: от 8 до 128 символов." : "Password: 8–128 characters.";
        case "repeat": return ru ? "Пароли не совпадают." : "Passwords do not match.";
        case "slow": return ru ? "Слишком много попыток. Попробуйте позже." : "Too many attempts. Try again later.";
        case "mail_unavailable": return ru ? "Отправка писем ещё не настроена." : "Email delivery has not been configured yet.";
        case "email": return ru ? "Проверьте адрес почты." : "Check the email address.";
        case "email_used": return ru ? "Эта почта привязана к другому аккаунту." : "This email belongs to another account.";
        case "email_required": return ru ? "Сначала привяжите и подтвердите почту в аккаунте." : "Link and verify your email in the account first.";
        case "account_changed": return ru ? "Аккаунт изменился. Откройте его снова." : "Account changed. Open it again.";
        case "code": return ru ? "Код неверен или истёк. Запросите новый." : "Invalid or expired code. Request a new one.";
        case "session": return ru ? "Войдите в аккаунт снова." : "Please sign in again.";
        case "profile": return ru ? "Дождитесь подключения профиля и повторите." : "Wait for your profile to connect and retry.";
        default: return ru ? "Не удалось выполнить. Проверьте соединение и повторите." : "Could not complete. Check the connection and retry.";
        }
    }

    private interface Done { void run(JSONObject result) throws Exception; }
    private static void send(CzmDialog d, String action, String credential, JSONObject body, boolean ru, Done done) {
        final int requestGeneration=generation();
        d.busy(true);
        WORK.execute(() -> {
            String response = raw(action, credential, body);
            d.activity.runOnUiThread(() -> {
                if (d.activity.isFinishing()) return;
                d.busy(false);
                if (!d.isShowing()) return;
                if (requestGeneration!=generation()) { d.fail(error("account_changed",ru)); return; }
                try {
                    if (status(response) != 200) {
                        String code = status(response) == 0 ? "network" : object(response).optString("error");
                        if (status(response) == 401 && code.equals("session")) expired(credential);
                        d.fail(error(code, ru)); return;
                    }
                    done.run(object(response));
                } catch (Exception e) { d.fail(ru ? "Не удалось сохранить сеанс. Войдите ещё раз." : "Could not save the session. Sign in again."); }
            });
        });
    }
    private static CzmDialog panel(Activity a, String title, String subtitle, String action, boolean ru) {
        if (editor != null) editor.dismiss();
        CzmDialog d = new CzmDialog(a, title, subtitle, action, ru ? "Закрыть" : "Close", ru); editor = d;
        d.setOnDismissListener(v -> { if (editor == d) editor = null; });
        return d;
    }

    private static android.content.SharedPreferences pendingStore(Context context) {
        return context.getSharedPreferences("czm_pending_email_login", Context.MODE_PRIVATE);
    }
    private static void clearPending(Context context) { pendingStore(context).edit().clear().apply(); }
    private static EmailLoginState pending(Context context) {
        android.content.SharedPreferences p = pendingStore(context);
        EmailLoginState state = EmailLoginState.restore(p.getString("email", ""), p.getLong("expires", 0),
                p.getLong("resend", 0), System.currentTimeMillis());
        if (state == null && p.contains("email")) clearPending(context);
        return state;
    }
    private static void rememberEmail(Context context, String email) {
        EmailLoginState state = EmailLoginState.requested(email, System.currentTimeMillis());
        pendingStore(context).edit().putString("email", state.email).putLong("expires", state.expiresAt)
                .putLong("resend", state.resendAt).apply();
        restoreThrottle(state);
    }
    private static void restoreThrottle(EmailLoginState state) {
        mailAt.put("login:" + state.email.toLowerCase(java.util.Locale.ROOT),
                android.os.SystemClock.elapsedRealtime() + state.resendDelay(System.currentTimeMillis()));
    }

    private static android.content.SharedPreferences passwordStore(Context c) {
        return c.getSharedPreferences("czm_pending_password_change", Context.MODE_PRIVATE);
    }
    private static void clearPendingPassword(Context c) { if(c!=null)passwordStore(c).edit().clear().apply(); }
    private static PasswordChangeState pendingPassword(Context c) {
        android.content.SharedPreferences p=passwordStore(c);
        PasswordChangeState state=PasswordChangeState.restore(p.getInt("owner",0),p.getString("email",""),
            p.getLong("expires",0),p.getLong("resend",0),System.currentTimeMillis());
        if(state==null&&p.contains("owner"))clearPendingPassword(c);
        return state;
    }
    private static void rememberPassword(Context c,int owner,String email) {
        PasswordChangeState state=PasswordChangeState.requested(owner,email,System.currentTimeMillis());
        passwordStore(c).edit().putInt("owner",owner).putString("email",email).putLong("expires",state.mail.expiresAt)
            .putLong("resend",state.mail.resendAt).apply();
        passwordThrottle(state);
    }
    private static void passwordThrottle(PasswordChangeState state) {
        mailAt.put("password:"+state.owner,android.os.SystemClock.elapsedRealtime()+state.mail.resendDelay(System.currentTimeMillis()));
    }

    // Activity recreation can also restart the native engine. Wait for its guest profile key
    // before restoring the dialog; no credentials or profile keys need to be persisted for it.
    static void rememberContext(String legacy, String nick, boolean ru) {
        Context context = SDLActivity.getContext(); if (!(context instanceof Activity)) return;
        Activity a = (Activity)context;
        a.runOnUiThread(() -> {
            profileKey = legacy; profileNick = nick; russian = ru; contextReady = true;
            restoreEmail(a);
        });
    }
    static void resume(Activity a) { foregroundActivity = a; restoreEmail(a); }
    static void pause(Activity a) { if (foregroundActivity == a) foregroundActivity = null; }
    static void destroy(Activity a) {
        pause(a);
        if (editor != null && editor.activity == a) editor.dismiss();
    }
    private static void restoreEmail(Activity a) {
        if (!contextReady || foregroundActivity != a || a.isFinishing() || a.isDestroyed()) return;
        if (editor != null) {
            if (editor.activity == a && editor.isShowing()) return;
            editor.dismiss(); editor = null;
        }
        load();
        synchronized (CzmAccount.class) {
            if (!token.isEmpty()) {
                clearPending(a);
                if(pendingPassword(a)!=null)show(profileKey,profileNick,russian);
                return;
            }
        }
        if(pendingPassword(a)!=null)clearPendingPassword(a);
        EmailLoginState state = pending(a);
        if (state != null) {
            restoreThrottle(state);
            emailLogin(a, profileKey, profileNick, russian, true, state.email);
        }
    }

    private static void signedIn(CzmDialog d, JSONObject result, boolean ru) throws Exception {
        signedIn(d,result,ru,false);
    }
    private static void signedIn(CzmDialog d, JSONObject result, boolean ru, boolean passwordChanged) throws Exception {
        synchronized (CzmAccount.class) {
            String next = result.getString("token");
            if (!next.matches("czms1_[A-Za-z0-9_-]{43}")) throw new IllegalArgumentException();
            CzmServerAuth.session(d.activity, next); token = next; ++generation;
            profile(result.getJSONObject("profile"));
        }
        clearPending(d.activity);
        clearPendingPassword(d.activity);
        d.dismiss(); Toast.makeText(d.activity, passwordChanged ? (ru?"Пароль изменён":"Password changed") : (ru ? "Вход выполнен" : "Signed in"), Toast.LENGTH_SHORT).show();
    }

    static void show(String legacy, String nick, boolean ru) {
        show(legacy, nick, ru, false);
    }
    static void register(String legacy, String nick, boolean ru) {
        show(legacy, nick, ru, true);
    }
    private static void show(String legacy, String nick, boolean ru, boolean registration) {
        Context context = SDLActivity.getContext(); if (!(context instanceof Activity)) return;
        Activity a = (Activity)context;
        a.runOnUiThread(() -> {
            if (a.isFinishing() || a.isDestroyed()) return;
            if (editor != null && editor.activity != a) editor.dismiss();
            if (editor != null && editor.isShowing()) return;
            profileKey = legacy; profileNick = nick; russian = ru; contextReady = true;
            load();
            final String saved;
            synchronized (CzmAccount.class) { saved = token; }
            if (saved.isEmpty()) {
                EmailLoginState state = registration ? null : pending(a);
                if (state != null) {
                    restoreThrottle(state);
                    emailLogin(a, legacy, nick, ru, true, state.email);
                } else form(a, legacy, nick, registration ? "register" : "login", ru);
            }
            else {
                CzmDialog d = panel(a, ru ? "Аккаунт CZM" : "CZM account", ru ? "Проверяем сеанс…" : "Checking session…", "…", ru);
                d.submit.setVisibility(View.GONE);
                d.show();
                send(d, "me", saved, new JSONObject(), ru, info -> details(a, legacy, nick, saved, info, ru));
            }
        });
    }

    private static void form(Activity a, String legacy, String nick, String mode, boolean ru) {
        clearPending(a);
        boolean register = mode.equals("register"), recovery = mode.equals("recover"), reset = mode.equals("reset");
        String title = register ? (ru ? "Создать аккаунт" : "Create account") : recovery || reset ? (ru ? "Восстановить пароль" : "Reset password") : (ru ? "Вход в CZM" : "Sign in to CZM");
        CzmDialog d = panel(a, title, register ? (ru ? "Сохраним текущий профиль и аватар" : "Keep your current profile and avatar")
            : (ru ? "Один профиль на всех ваших устройствах" : "One profile on all your devices"),
            recovery ? (ru ? "Получить код" : "Get code") : reset ? (ru ? "Сменить пароль" : "Reset password") : register ? (ru ? "Создать" : "Create") : (ru ? "Войти" : "Sign in"), ru);
        EditText login = d.field(ru ? "Ник для входа" : "Login nickname", false, 24); login.setText(register || recovery || reset ? nick : "");
        EditText code = reset ? d.codeField(ru ? "Код из письма" : "Email code") : null;
        if (code != null) code.setInputType(InputType.TYPE_CLASS_NUMBER);
        EditText password = recovery ? null : d.field(ru ? "Пароль · минимум 8 символов" : "Password · at least 8 characters", true, 128);
        EditText repeat = register || reset ? d.field(ru ? "Повтор пароля" : "Repeat password", true, 128) : null;
        if (register) d.note(ru ? "Ник для входа уникален. Игровой ник можно менять отдельно. Почта для восстановления добавляется после регистрации."
            : "Your login is unique. Your in-game nickname can be changed separately. Add recovery email after registration.");
        if (recovery) {
            d.note(ru ? "Код придёт на подтверждённую почту аккаунта, если она привязана." : "The code goes to your account's verified recovery email, if one is linked.");
            d.link(ru ? "У меня уже есть код" : "I already have a code", v -> form(a, legacy, login.getText().toString(), "reset", ru));
        }
        if (!register && !recovery && !reset) {
            d.link(ru ? "Войти по коду из почты" : "Sign in with email code", v -> emailLogin(a, legacy, nick, ru, false, ""));
            d.link(ru ? "Создать аккаунт" : "Create an account", v -> form(a, legacy, nick, "register", ru));
            d.link(ru ? "Забыли пароль?" : "Forgot password?", v -> form(a, legacy, login.getText().toString(), "recover", ru));
        }
        if(reset) resend(d,"recover:"+login.getText().toString().toLowerCase(java.util.Locale.ROOT),ru,()->{
            try {send(d,"recover","",new JSONObject().put("nick",login.getText().toString()),ru,result->mailAt.put("recover:"+login.getText().toString().toLowerCase(java.util.Locale.ROOT),android.os.SystemClock.elapsedRealtime()+60000));}catch(Exception e){d.fail(error("network",ru));}
        });
        if (register || recovery || reset) d.link(ru ? "Назад ко входу" : "Back to sign in", v -> form(a, legacy, nick, "login", ru));
        d.submit.setOnClickListener(v -> {
            try {
                JSONObject body = new JSONObject().put("nick", login.getText().toString());
                if (password != null) body.put("password", password.getText().toString());
                if (repeat != null) body.put("repeat", repeat.getText().toString());
                if (code != null) body.put("code", code.getText().toString());
                if (repeat != null && !password.getText().toString().equals(repeat.getText().toString())) { d.fail(error("repeat", ru)); return; }
                send(d, mode, register ? legacy : "", body, ru, result -> {
                    if (recovery) {
                        mailAt.put("recover:"+login.getText().toString().toLowerCase(java.util.Locale.ROOT),android.os.SystemClock.elapsedRealtime()+60000);
                        form(a, legacy, login.getText().toString(), "reset", ru);
                        editor.note(ru ? "Если у аккаунта есть подтверждённая почта, код отправлен. Проверьте также «Спам»." : "If the account has a verified email, a code was sent. Also check Spam.");
                    } else if (reset) {
                        form(a, legacy, login.getText().toString(), "login", ru);
                        editor.note(ru ? "Пароль изменён. Войдите с новым паролем." : "Password changed. Sign in with the new password.");
                    } else {
                        signedIn(d, result, ru);
                    }
                });
            } catch (Exception e) { d.fail(error("network", ru)); }
        });
        d.setOnDismissListener(v -> { if (password != null) password.setText(""); if (repeat != null) repeat.setText(""); if (editor == d) editor = null; });
        d.show();
    }

    private static void details(Activity a, String legacy, String nick, String credential, JSONObject info, boolean ru) {
        PasswordChangeState pending=pendingPassword(a);
        if(pending!=null) {
            if(pending.belongsTo(info.optInt("id"),info.optString("email"))) {
                passwordThrottle(pending);passwordChange(a,legacy,nick,credential,info,ru,true);return;
            }
            clearPendingPassword(a);
        }
        CzmDialog d = panel(a, ru ? "Аккаунт CZM" : "CZM account", info.optString("login") + " · ID " + info.optInt("id"), ru ? "Выйти" : "Sign out", ru);
        d.link(ru ? "Настройки в облаке" : "Cloud settings", v -> CzmCloud.show(a,ru));
        d.note((ru ? "Почта для входа и восстановления: " : "Sign-in and recovery email: ") + (info.optString("email").isEmpty() ? (ru ? "не привязана" : "not linked") : info.optString("email")));
        d.link(ru ? (info.optString("email").isEmpty() ? "Привязать почту" : "Изменить почту") : (info.optString("email").isEmpty() ? "Link email" : "Change email"), v -> email(a, legacy, nick, credential, ru, false));
        d.link(ru?"Изменить пароль":"Change password",v->passwordChange(a,legacy,nick,credential,info,ru,false));
        if (!info.optBoolean("mail_ready")) d.note(ru ? "Отправка писем пока недоступна. Для входа используйте пароль." : "Email is temporarily unavailable. Use your password to sign in.");
        d.link(ru ? "Выйти на всех устройствах" : "Sign out on all devices", v -> {
            // An explicit second tap keeps this separate from signing out of the current phone.
            CzmDialog confirm = panel(a, ru ? "Завершить все сеансы?" : "End all sessions?", ru ? "Профиль и аватар сохранятся" : "Your profile and avatar will stay", ru ? "Выйти везде" : "Sign out everywhere", ru);
            confirm.submit.setOnClickListener(w -> send(confirm, "logout-all", credential, new JSONObject(), ru, r -> { clear(credential); confirm.dismiss(); })); confirm.show();
        });
        d.link(ru ? "Удалить аккаунт" : "Delete account", v -> {
            // Google Play: the account can be deleted from the game; the password confirms it.
            CzmDialog confirm = panel(a, ru ? "Удалить аккаунт навсегда?" : "Delete the account for good?", info.optString("login"), ru ? "Удалить навсегда" : "Delete for good", ru);
            confirm.note(ru ? "Удалятся аккаунт, почта, друзья, личные сообщения, сообщения в чате, фото и настройки в облаке. Вернуть их будет нельзя."
                : "The account, email, friends, private messages, chat messages, photo and cloud settings will be deleted. They cannot be restored.");
            EditText password = confirm.field(ru ? "Пароль аккаунта" : "Account password", true, 128);
            confirm.submit.setOnClickListener(w -> {
                try {
                    send(confirm, "delete-account", credential, new JSONObject().put("password", password.getText().toString()), ru, r -> {
                        clear(credential); confirm.dismiss(); d.dismiss();
                    });
                } catch (Exception e) { confirm.fail(error("network", ru)); }
            });
            confirm.setOnDismissListener(w -> password.setText(""));
            confirm.show();
        });
        d.submit.setOnClickListener(v -> send(d, "logout", credential, new JSONObject(), ru, result -> { clear(credential); d.dismiss(); }));
        d.show();
    }

    private static void passwordChange(Activity a,String legacy,String nick,String credential,JSONObject info,boolean ru,boolean confirm) {
        String address=info.optString("email");int owner=info.optInt("id");
        CzmDialog d=panel(a,ru?"Изменить пароль":"Change password",address.isEmpty()?"":address,
            confirm?(ru?"Сохранить пароль":"Save password"):(ru?"Получить код":"Get code"),ru);
        d.cancel.setOnClickListener(v->{clearPendingPassword(a);details(a,legacy,nick,credential,info,ru);});
        d.setOnCancelListener(v->clearPendingPassword(a));
        if(address.isEmpty()) {
            d.note(error("email_required",ru));d.submit.setVisibility(View.GONE);
            d.link(ru?"Привязать почту":"Link email",v->email(a,legacy,nick,credential,ru,false));d.show();return;
        }
        d.note(confirm?(ru?"Введите код из письма, новый пароль и повторите его.":"Enter the email code, a new password and repeat it."):
            (ru?"Отправим код на подтверждённую почту аккаунта. Код действует 10 минут.":"We will send a code to the account's verified email. It expires in 10 minutes."));
        d.note(ru?"После смены пароля другие устройства выйдут из аккаунта. На этом устройстве вход сохранится.":"Changing the password signs out other devices. You will stay signed in here.");
        if(!confirm) {
            d.submit.setOnClickListener(v->send(d,"password-change",credential,new JSONObject(),ru,result->{
                if(result.optInt("id")!=owner)throw new IllegalArgumentException();
                info.put("email",result.getString("email"));rememberPassword(a,owner,info.getString("email"));
                passwordChange(a,legacy,nick,credential,info,ru,true);
            }));d.show();return;
        }
        EditText code=d.codeField(ru?"Код из письма":"Email code");
        EditText password=d.field(ru?"Новый пароль (от 8 символов)":"New password (8+ characters)",true,128);
        EditText repeat=d.field(ru?"Повторите новый пароль":"Repeat new password",true,128);
        resend(d,"password:"+owner,ru,()->send(d,"password-change",credential,new JSONObject(),ru,result->{
            if(result.optInt("id")!=owner||!address.equals(result.optString("email"))){clearPendingPassword(a);throw new IllegalArgumentException();}
            rememberPassword(a,owner,address);code.setText("");
        }));
        d.submit.setOnClickListener(v->{try {
            if(password.getText().length()<8){d.fail(error("password",ru));return;}
            if(!password.getText().toString().equals(repeat.getText().toString())){d.fail(error("repeat",ru));return;}
            send(d,"password-change-confirm",credential,new JSONObject().put("code",code.getText().toString())
                .put("password",password.getText().toString()).put("repeat",repeat.getText().toString()),ru,result->signedIn(d,result,ru,true));
        }catch(Exception e){d.fail(error("network",ru));}});
        d.setOnDismissListener(v->{code.setText("");password.setText("");repeat.setText("");if(editor==d)editor=null;});
        d.show();
    }

    private static void resend(CzmDialog d,String key,boolean ru,Runnable action) {
        android.widget.Button button=d.link(ru?"Отправить код ещё раз":"Resend code",v->action.run());
        button.post(new Runnable(){public void run(){if(!d.isShowing())return;long seconds=Math.max(0,((mailAt.containsKey(key)?mailAt.get(key):0L)-android.os.SystemClock.elapsedRealtime()+999)/1000);button.setEnabled(seconds==0&&d.submit.isEnabled());button.setText(seconds>0?(ru?"Отправить ещё раз через ":"Resend in ")+seconds+(ru?" сек.":" sec."):(ru?"Отправить код ещё раз":"Resend code"));button.postDelayed(this,1000);}});
    }

    private static void emailLogin(Activity a, String legacy, String nick, boolean ru, boolean confirm, String address) {
        if (!confirm) clearPending(a);
        CzmDialog d=panel(a,ru?"Вход по почте":"Sign in with email",confirm?address:(ru?"Введите почту, подтверждённую в аккаунте":"Use the email verified in your account"),confirm?(ru?"Войти":"Sign in"):(ru?"Получить код":"Get code"),ru);
        EditText input=confirm?d.codeField(ru?"Код из письма":"Email code"):d.field("Email",false,254);
        input.setInputType(confirm?InputType.TYPE_CLASS_NUMBER:InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        if(!confirm)input.setText(address);
        String throttle="login:"+address.toLowerCase(java.util.Locale.ROOT);
        if(confirm) {
            d.note(ru?"Если почта привязана к аккаунту, код отправлен. Проверьте также «Спам».":"If this email is linked, a code was sent. Also check Spam.");
            resend(d,throttle,ru,()->{try{send(d,"email-login","",new JSONObject().put("email",address),ru,result->rememberEmail(a,address));}catch(Exception e){d.fail(error("email",ru));}});
            d.link(ru?"Изменить адрес":"Change email address",v->emailLogin(a,legacy,nick,ru,false,address));
        }
        d.link(ru?"Войти по паролю":"Use password instead",v->form(a,legacy,nick,"login",ru));
        d.submit.setOnClickListener(v->{
            try {
                String email=confirm?address:input.getText().toString().trim();
                JSONObject body=new JSONObject().put("email",email);
                if(confirm)body.put("code",input.getText().toString());
                send(d,confirm?"email-login-confirm":"email-login","",body,ru,result->{
                    if(confirm)signedIn(d,result,ru);
                    else{rememberEmail(a,email);emailLogin(a,legacy,nick,ru,true,email);}
                });
            }catch(Exception e){d.fail(error("email",ru));}
        });
        d.cancel.setOnClickListener(v -> { clearPending(a); d.dismiss(); });
        d.setOnCancelListener(v -> clearPending(a));
        d.setOnDismissListener(v->{if(confirm)input.setText("");if(editor==d)editor=null;});
        d.show();
    }
    private static void email(Activity a, String legacy, String nick, String credential, boolean ru, boolean confirm) { email(a,legacy,nick,credential,ru,confirm,""); }
    private static void email(Activity a, String legacy, String nick, String credential, boolean ru, boolean confirm,String target) {
        CzmDialog d = panel(a, ru ? "Привязка почты" : "Link email", confirm ? (ru ? "Введите код из письма" : "Enter the email code") : (ru ? "Для входа по коду и восстановления аккаунта" : "For email sign-in and account recovery"),
            confirm ? (ru ? "Подтвердить" : "Confirm") : (ru ? "Получить код" : "Get code"), ru);
        EditText input = confirm ? d.codeField(ru ? "Код из письма" : "Email code") : d.field("Email", false, 254);
        input.setInputType(confirm ? InputType.TYPE_CLASS_NUMBER : InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        if(!confirm)input.setText(target);
        if (!confirm) d.link(ru ? "У меня уже есть код" : "I already have a code", v -> email(a, legacy, nick, credential, ru, true,input.getText().toString()));
        if(confirm&&!target.isEmpty())resend(d,"email:"+credential+target,ru,()->{try{send(d,"email",credential,new JSONObject().put("email",target),ru,result->mailAt.put("email:"+credential+target,android.os.SystemClock.elapsedRealtime()+60000));}catch(Exception e){d.fail(error("network",ru));}});
        d.submit.setOnClickListener(v -> {
            try {
                send(d, confirm ? "email-confirm" : "email", credential, new JSONObject().put(confirm ? "code" : "email", input.getText().toString()), ru,
                    result -> { if (confirm) details(a, legacy, nick, credential, result, ru); else {String address=input.getText().toString();mailAt.put("email:"+credential+address,android.os.SystemClock.elapsedRealtime()+60000);email(a, legacy, nick, credential, ru, true,address);} });
            } catch (Exception e) { d.fail(error("email", ru)); }
        });
        if(confirm)input.addTextChangedListener(new android.text.TextWatcher(){public void beforeTextChanged(CharSequence s,int st,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){}public void afterTextChanged(android.text.Editable text){if(text.length()==6&&d.isShowing()&&d.submit.isEnabled())d.submit.performClick();}});
        d.show();
    }
}
