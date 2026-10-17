package ru.kurostreet.counterzombiemobile;

import android.annotation.SuppressLint;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.net.Uri;
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
    private static final ExecutorService UPDATE = Executors.newSingleThreadExecutor();
    private static final ConcurrentHashMap<Integer, String> RESULTS = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<Integer, Integer> GENERATIONS = new ConcurrentHashMap<>();
    private static final AtomicInteger NEXT = new AtomicInteger(1);
    private static final int MAX_BODY = 1 << 20;

    private CzmNet() {}

    public static void serverAuthShow(String address, String name, boolean russian) {
        CzmServerAuth.show(address, name, russian);
    }

    public static void accountShow(String legacy, String nick, boolean russian) { CzmAccount.show(legacy, nick, russian); }
    public static byte[] accountEvent() { return CzmAccount.event(); }
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

    public static final int UPDATE_IDLE = 0;
    public static final int UPDATE_DOWNLOADING = 1;
    public static final int UPDATE_VERIFYING = 2;
    public static final int UPDATE_READY = 3;
    public static final int UPDATE_ERROR = 4;
    public static final int UPDATE_INSTALLING = 5;
    public static final int UPDATE_PERMISSION = 6;

    private static final String INSTALL_ACTION = "ru.kurostreet.counterzombiemobile.INSTALL_STATUS";
    private static volatile int updateState = UPDATE_IDLE;
    private static volatile long updateDone, updateTotal;
    private static volatile boolean updateCancel;
    private static volatile String updateError = "";
    private static File updateFile;
    private static BroadcastReceiver installReceiver;

    /** "state done total error": the menu draws the bar from it. */
    public static String updateState() {
        return updateState + " " + updateDone + " " + updateTotal + " " + updateError;
    }

    public static void updateCancel() {
        updateCancel = true;
    }

    /** Downloads a patch when possible, then hands the verified signed APK to Android. */
    public static void updateStart(final String url, final String sha256, final long size,
                                   final String patchUrl, final String patchSha, final long patchSize, final String baseSha) {
        if (!canSelfUpdate() || updateState == UPDATE_DOWNLOADING || updateState == UPDATE_VERIFYING || updateState == UPDATE_INSTALLING) return;
        Context ctx = context();
        if (ctx == null) return;
        updateCancel = false;
        updateError = "";
        updateTotal = patchSize > 0 ? patchSize : size;
        updateDone = 0;
        updateState = UPDATE_VERIFYING;
        final File dir = new File(ctx.getFilesDir(), "update");
        final File installed = new File(ctx.getApplicationInfo().sourceDir);
        UPDATE.execute(new Runnable() {
            @Override public void run() {
                try {
                    updateFile = ApkUpdate.prepare(dir, installed, url, sha256, size, patchUrl, patchSha, patchSize, baseSha,
                        new ApkUpdate.Progress() {
                            @Override public boolean cancelled() { return updateCancel; }
                            @Override public void update(boolean verifying, long done, long total) {
                                updateDone = done;
                                updateTotal = total;
                                updateState = verifying ? UPDATE_VERIFYING : UPDATE_DOWNLOADING;
                            }
                        });
                    updateState = updateCancel ? UPDATE_IDLE : UPDATE_READY;
                } catch (Exception e) {
                    Log.w(TAG, "update download failed", e);
                    fail(e instanceof ApkUpdate.UpdateException ? ((ApkUpdate.UpdateException) e).reason : "network");
                    if (updateCancel) updateState = UPDATE_IDLE;
                }
            }
        });
    }

    private static void fail(String why) {
        updateError = why;
        updateState = UPDATE_ERROR;
    }

    /** Hands the downloaded APK to Android; the system asks the player to confirm. */
    public static void updateInstall() {
        final Context ctx = context();
        final File apk = updateFile;
        if (ctx == null || apk == null || updateState != UPDATE_READY && updateState != UPDATE_PERMISSION) return;

        // Android 8+: the player allows installs from this app once
        if (Build.VERSION.SDK_INT >= 26 && !ctx.getPackageManager().canRequestPackageInstalls()) {
            updateState = UPDATE_PERMISSION;
            Intent settings = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + ctx.getPackageName()));
            settings.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                ctx.startActivity(settings);
            } catch (Exception e) {
                Log.w(TAG, "no install settings screen", e);
            }
            return;
        }

        updateState = UPDATE_INSTALLING;
        UPDATE.execute(new Runnable() {
            @Override public void run() {
                try {
                    registerInstallReceiver(ctx);
                    PackageInstaller installer = ctx.getPackageManager().getPackageInstaller();
                    PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                    params.setAppPackageName(ctx.getPackageName());
                    int sessionId = installer.createSession(params);
                    try (PackageInstaller.Session session = installer.openSession(sessionId)) {
                        try (InputStream in = new FileInputStream(apk); OutputStream out = session.openWrite("base.apk", 0, apk.length())) {
                            copy(in, out, Long.MAX_VALUE);
                            session.fsync(out);
                        }
                        Intent status = new Intent(INSTALL_ACTION).setPackage(ctx.getPackageName());
                        int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                        session.commit(PendingIntent.getBroadcast(ctx, sessionId, status, flags).getIntentSender());
                    }
                } catch (Exception e) {
                    Log.w(TAG, "install failed", e);
                    fail("install");
                }
            }
        });
    }

    private static synchronized void registerInstallReceiver(Context ctx) {
        if (installReceiver != null) return;
        installReceiver = new BroadcastReceiver() {
            @Override public void onReceive(Context c, Intent intent) {
                int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
                if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                    Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
                    if (confirm != null) {
                        confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        try {
                            c.startActivity(confirm);
                        } catch (Exception e) {
                            Log.w(TAG, "no confirm screen", e);
                            fail("install");
                        }
                    }
                } else if (status == PackageInstaller.STATUS_SUCCESS) {
                    updateState = UPDATE_IDLE; // Android restarts the app with the new version
                } else {
                    // cancelled by the player or refused: the file stays, the button too
                    Log.w(TAG, "install status " + status + ": " + intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE));
                    updateState = status == PackageInstaller.STATUS_FAILURE_ABORTED ? UPDATE_READY : UPDATE_ERROR;
                    if (updateState == UPDATE_ERROR) updateError = "install";
                }
            }
        };
        IntentFilter filter = new IntentFilter(INSTALL_ACTION);
        Context app = ctx.getApplicationContext();
        if (Build.VERSION.SDK_INT >= 33) app.registerReceiver(installReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        else app.registerReceiver(installReceiver, filter);
    }

    /** The updated app no longer needs the downloaded file. */
    public static void updateCleanup() {
        Context ctx = context();
        if (ctx == null) return;
        File[] files = new File(ctx.getFilesDir(), "update").listFiles();
        if (files != null && updateState == UPDATE_IDLE) for (File f : files) f.delete();
    }
}
