package ru.kurostreet.counterzombiemobile;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import org.libsdl.app.SDLActivity;

/**
 * Network for the game menu (chat, news, avatars, updates).
 *
 * The menu library calls these static methods through JNI from the game thread.
 * Nothing here blocks that thread: a request returns a number at once, the work runs
 * on a small pool, the menu asks poll(number) every frame until the answer is there.
 * HTTPS, timeouts and certificates are Android's.
 */
public final class CzmNet {
    private static final String TAG = "CzmNet";
    private static final ExecutorService POOL = Executors.newFixedThreadPool(3);
    private static final ConcurrentHashMap<Integer, String> RESULTS = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<Integer, Integer> GENERATIONS = new ConcurrentHashMap<>();
    private static final AtomicInteger NEXT = new AtomicInteger(1);
    private static final int MAX_BODY = 1 << 20;

    private CzmNet() {}

    public static void lobbyVoiceStart(String url,String key,int player){CzmLobbyVoiceDialog.loadPreferences();CzmLobbyVoice.start(url,key,player);}
    public static void lobbyVoiceTest(){CzmLobbyVoiceDialog.show();}
    public static boolean lobbyVoiceMicEnabled(int player){return CzmLobbyVoice.microphoneEnabled(player);}
    public static void lobbyVoiceStop(){CzmLobbyVoice.stop();}
    public static void lobbyVoiceMic(boolean enabled){CzmLobbyVoice.setMic(enabled);}
    public static boolean lobbyVoiceMicOn(){return CzmLobbyVoice.microphoneOn();}
    public static boolean lobbyVoiceSpeaking(int player){return CzmLobbyVoice.speaking(player);}
    public static int lobbyVoiceState(){return CzmLobbyVoice.state();}
    public static void lobbyVoiceLocalMute(int player,boolean enabled){
        CzmLobbyVoice.mutePlayer(player,enabled);
    }
    public static boolean lobbyVoiceIsMuted(int player){return CzmLobbyVoice.locallyMuted(player);}


    public static void serverAuthShow(String address, String name, boolean russian) {
        CzmServerAuth.show(address, name, russian);
    }

    public static void accountShow(String legacy, String nick, boolean russian) { CzmAccount.show(legacy, nick, russian); }
    public static void accountRegister(String legacy, String nick, boolean russian) { CzmAccount.register(legacy, nick, russian); }
    public static void accountContext(String legacy, String nick, boolean russian) { CzmAccount.rememberContext(legacy, nick, russian); }
    public static byte[] accountEvent() { return CzmAccount.event(); }
    public static void distributionShow(String key,String nick,boolean ru){DistributionAccess.show(key,nick,ru);}
    public static void distributionHelp(String key,String nick,boolean ru){DistributionAccess.help(key,nick,ru);}
    public static boolean distributionChanged(){return DistributionAccess.changed();}
    public static void colorShow(int r, int g, int b, boolean ru) { CzmColorPicker.show(r, g, b, ru); }
    public static byte[] colorEvent() { return CzmColorPicker.event(); }
    public static byte[] cloudEvent() { byte[] event=CzmCloud.event();return event!=null?event:CzmLayoutActivity.event(); }
    public static void layoutsShow() { Context ctx=context();if(ctx instanceof android.app.Activity)((android.app.Activity)ctx).runOnUiThread(()->ctx.startActivity(new Intent(ctx,CzmLayoutActivity.class))); }
    public static void cloudApplied(int request, boolean success) { CzmCloud.applied(request,success); }
    public static void loadingProgress(int session,int status,int percent,byte[] label){CzmDownloads.progress(session,status,percent,new String(label,StandardCharsets.UTF_8));}
    public static void loadingBackground(){CzmDownloads.request();}
    public static boolean loadingWait(){return CzmDownloads.waitForForeground();}
    public static boolean loadingCancel(){return CzmDownloads.cancelEvent();}
    private static String widgetPending="";
    public static synchronized byte[] widgetEvent() { if(widgetPending.isEmpty())return null;byte[] out=widgetPending.getBytes(StandardCharsets.UTF_8);widgetPending="";return out; }
    static void widgetConfirm(android.app.Activity a,Intent intent) {
        String address=intent.getStringExtra("czm_server"),protocol=intent.getStringExtra("czm_protocol");
        intent.removeExtra("czm_server");intent.removeExtra("czm_protocol");
        if(!ServerQuery.valid(address)||!("gs".equals(protocol)||"49".equals(protocol)))return;
        boolean ru=java.util.Locale.getDefault().getLanguage().equals("ru");
        CzmDialog d=new CzmDialog(a,ru?"Подключиться к серверу?":"Connect to server?",address,ru?"Подключиться":"Connect",ru?"Отмена":"Cancel",ru,false);
        d.submit.setOnClickListener(v->{synchronized(CzmNet.class){widgetPending=address+" "+protocol;}d.dismiss();});d.show();
    }


    public static byte[] serverUserinfo(String address, byte[] base, int limit) {
        return CzmServerAuth.userinfo(address, new String(base, StandardCharsets.UTF_8), limit).getBytes(StandardCharsets.UTF_8);
    }

    private static Context context() {
        return SDLActivity.getContext();
    }

    public static boolean copyText(String text) {
        Context ctx = context();
        if (!(ctx instanceof android.app.Activity) || text == null || text.length() > 64) return false;
        ((android.app.Activity) ctx).runOnUiThread(() -> {
            android.content.ClipboardManager clipboard = (android.content.ClipboardManager) ctx.getSystemService(Context.CLIPBOARD_SERVICE);
            if (clipboard != null) clipboard.setPrimaryClip(android.content.ClipData.newPlainText("CZM ID", text));
        });
        return true;
    }

    /** Native menu calls this only after its first complete draw. */
    public static void startupReady() {
        Context ctx = context();
        if (ctx instanceof CzmGameActivity) ((CzmGameActivity)ctx).menuReady();
    }

    /** files/game/cstrike: the game's writable folder. */
    public static String gameDir() {
        Context ctx = context();
        return ctx == null ? "" : new File(ctx.getFilesDir(), "game/cstrike").getAbsolutePath();
    }

    /** A fingerprint of this phone for bans: ANDROID_ID mixed with the package, never sent as it is. */
    @SuppressLint("HardwareIds")
    public static String deviceId() {
        Context ctx = context();
        if (ctx == null) return "";
        String id = Settings.Secure.getString(ctx.getContentResolver(), Settings.Secure.ANDROID_ID);
        return id == null ? "" : sha256Hex((ctx.getPackageName() + ":" + id).getBytes(StandardCharsets.UTF_8));
    }

    public static int versionCode() {
        Context ctx = context();
        try {
            PackageInfo info = ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? (int) info.getLongVersionCode() : info.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    /** Updates from inside the game, not allowed in the Google Play build. */
    public static boolean canSelfUpdate() {
        return !BuildConfig.IS_GOOGLE_PLAY_BUILD;
    }

    /** Google Play build: "code bytes" of the update Play offers, or "" (StoreUpdates per build flavor). */
    public static String storeUpdateState() {
        return StoreUpdates.state(context());
    }

    /** Google Play build: Play's own update screen over the game. */
    public static void storeUpdateStart() {
        StoreUpdates.start(context());
    }

    // requests ----------------------------------------------------------------

    /** GET or POST with a JSON body (UTF-8 bytes, empty for none); returns the number to poll. */
    public static int request(final String method, final String url, final String key, final byte[] body) {
        final int id = NEXT.getAndIncrement();
        final int generation = CzmAccount.generation();
        GENERATIONS.put(id, generation);
        POOL.execute(new Runnable() {
            @Override public void run() {
                RESULTS.put(id, CzmAccount.call(generation, method, url, key, body == null || body.length == 0 ? null : body, "application/json"));
            }
        });
        return id;
    }

    /** A new secret key for this player, kept by the menu in the game folder. */
    public static String newKey() {
        byte[] b = new byte[24];
        new java.security.SecureRandom().nextBytes(b);
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    /** POST of a file from the game folder (the avatar photo). */
    public static int upload(final String url, final String key, final String path, final String contentType) {
        final int id = NEXT.getAndIncrement();
        final int generation = CzmAccount.generation();
        GENERATIONS.put(id, generation);
        POOL.execute(new Runnable() {
            @Override public void run() {
                File file = gameFile(path);
                if (file == null || !file.isFile() || file.length() > MAX_BODY) {
                    RESULTS.put(id, "0\n");
                    return;
                }
                try {
                    RESULTS.put(id, CzmAccount.call(generation, "POST", url, key, readAll(new FileInputStream(file)), contentType));
                } catch (IOException e) {
                    RESULTS.put(id, "0\n");
                }
            }
        });
        return id;
    }

    /** Downloads a small file (someone's avatar) into the game folder. */
    public static int download(final String url, final String path) {
        final int id = NEXT.getAndIncrement();
        POOL.execute(new Runnable() {
            @Override public void run() {
                File file = gameFile(path);
                if (file == null) {
                    RESULTS.put(id, "0\n");
                    return;
                }
                HttpURLConnection conn = null;
                try {
                    conn = open(url, "GET", "");
                    int code = conn.getResponseCode();
                    if (code == 200) {
                        File dir = file.getParentFile();
                        if (dir != null && !dir.isDirectory()) dir.mkdirs();
                        File part = new File(file.getPath() + ".part");
                        try (InputStream in = conn.getInputStream(); OutputStream out = new FileOutputStream(part)) {
                            copy(in, out, MAX_BODY);
                        }
                        if (!part.renameTo(file)) code = 0;
                    }
                    RESULTS.put(id, code + "\n");
                } catch (IOException e) {
                    RESULTS.put(id, "0\n");
                } finally {
                    if (conn != null) conn.disconnect();
                }
            }
        });
        return id;
    }

    /** null while the request runs, then "status\nbody" once as UTF-8 (status 0: no network). */
    public static byte[] poll(int id) {
        String result = RESULTS.remove(id);
        if (result != null) {
            Integer generation = GENERATIONS.remove(id);
            if (generation != null && generation != CzmAccount.generation()) result = "409\n";
        }
        return result == null ? null : result.getBytes(StandardCharsets.UTF_8);
    }

    private static File gameFile(String path) {
        if (path == null || path.isEmpty() || path.contains("..") || path.startsWith("/")) return null;
        String dir = gameDir();
        return dir.isEmpty() ? null : new File(dir, path);
    }

    private static HttpURLConnection open(String url, String method, String key) throws IOException {
        if (key != null && !key.isEmpty() && !CzmAccount.serviceUrl(url)) throw new IOException("credential origin");
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        if (key != null && !key.isEmpty()) conn.setInstanceFollowRedirects(false);
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(20000);
        conn.setRequestMethod(method);
        conn.setRequestProperty("User-Agent", "CounterZombieMobile/" + versionCode());
        if (key != null && !key.isEmpty()) conn.setRequestProperty("X-CZM-Key", key);
        return conn;
    }

    static String call(String method, String url, String key, byte[] data, String contentType) {
        HttpURLConnection conn = null;
        try {
            conn = open(url, method, key);
            if (data != null) {
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", contentType);
                conn.setFixedLengthStreamingMode(data.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(data);
                }
            }
            int code = conn.getResponseCode();
            InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String body = in == null ? "" : new String(readAll(in), StandardCharsets.UTF_8);
            return code + "\n" + body;
        } catch (IOException e) {
            Log.w(TAG, method + " failed: " + e.getClass().getSimpleName());
            return "0\n";
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static byte[] readAll(InputStream in) throws IOException {
        try (InputStream stream = in) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            copy(stream, out, MAX_BODY);
            return out.toByteArray();
        }
    }

    private static long copy(InputStream in, OutputStream out, long limit) throws IOException {
        byte[] buf = new byte[64 * 1024];
        long total = 0;
        int n;
        while ((n = in.read(buf)) > 0) {
            total += n;
            if (total > limit) throw new IOException("too big");
            out.write(buf, 0, n);
        }
        return total;
    }

    private static String sha256Hex(byte[] data) {
        try {
            byte[] d = MessageDigest.getInstance("SHA-256").digest(data);
            StringBuilder sb = new StringBuilder();
            for (byte b : d) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }

    // update from inside the game ----------------------------------------------
    // Only the site build updates itself (SelfUpdate in src/git); the Google Play build has
    // no installer code at all and asks Google Play instead (StoreUpdates in src/googlePlay).

    /** "state done total error": the menu draws the bar from it. */
    public static String updateState() {
        return SelfUpdate.state();
    }

    public static void updateCancel() {
        SelfUpdate.cancel();
    }

    /** Downloads a patch when possible, then keeps the verified signed APK for updateInstall. */
    public static void updateStart(final String url, final String sha256, final long size,
                                   final String patchUrl, final String patchSha, final long patchSize, final String baseSha) {
        if (!canSelfUpdate()) return;
        Context ctx = context();
        if (ctx != null) SelfUpdate.start(ctx, url, sha256, size, patchUrl, patchSha, patchSize, baseSha);
    }

    /** Hands the downloaded APK to Android; the system asks the player to confirm. */
    public static void updateInstall() {
        Context ctx = context();
        if (ctx != null && canSelfUpdate()) SelfUpdate.install(ctx);
    }

    /** The updated app no longer needs the downloaded file. */
    public static void updateCleanup() {
        Context ctx = context();
        if (ctx != null) SelfUpdate.cleanup(ctx);
    }
}
