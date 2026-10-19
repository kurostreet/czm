package ru.kurostreet.counterzombiemobile;

import android.app.PendingIntent;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * The APK from the site updates itself: download (a patch when possible), check, then hand the
 * signed APK to the Android installer. Only this build has it; the Google Play build updates
 * through Google Play (its SelfUpdate does nothing).
 */
final class SelfUpdate {
    private static final String TAG = "CzmUpdate";
    static final int IDLE = 0, DOWNLOADING = 1, VERIFYING = 2, READY = 3, ERROR = 4, INSTALLING = 5, PERMISSION = 6;

    private static final ExecutorService WORK = Executors.newSingleThreadExecutor();
    private static volatile int state = IDLE;
    private static volatile long done, total;
    private static volatile boolean cancel;
    private static volatile String error = "";
    private static volatile int session = -1;
    private static File apk;

    private SelfUpdate() {}

    static String state() {
        return state + " " + done + " " + total + " " + error;
    }

    static void cancel() {
        cancel = true;
    }

    static void start(Context ctx, final String url, final String sha256, final long size,
                      final String patchUrl, final String patchSha, final long patchSize, final String baseSha) {
        if (state == DOWNLOADING || state == VERIFYING || state == INSTALLING) return;
        cancel = false;
        error = "";
        total = patchSize > 0 ? patchSize : size;
        done = 0;
        state = VERIFYING;
        final File dir = new File(ctx.getFilesDir(), "update");
        final File installed = new File(ctx.getApplicationInfo().sourceDir);
        WORK.execute(new Runnable() {
            @Override public void run() {
                try {
                    apk = ApkUpdate.prepare(dir, installed, url, sha256, size, patchUrl, patchSha, patchSize, baseSha,
                        new ApkUpdate.Progress() {
                            @Override public boolean cancelled() { return cancel; }
                            @Override public void update(boolean verifying, long d, long t) {
                                done = d;
                                total = t;
                                state = verifying ? VERIFYING : DOWNLOADING;
                            }
                        });
                    state = cancel ? IDLE : READY;
                } catch (Exception e) {
                    Log.w(TAG, "update download failed", e);
                    fail(e instanceof ApkUpdate.UpdateException ? ((ApkUpdate.UpdateException) e).reason : "network");
                    if (cancel) state = IDLE;
                }
            }
        });
    }

    private static void fail(String why) {
        error = why;
        state = ERROR;
    }

    static void install(final Context ctx) {
        final File file = apk;
        if (file == null || state != READY && state != PERMISSION) return;

        // Android 8+: the player allows installs from this app once
        if (Build.VERSION.SDK_INT >= 26 && !ctx.getPackageManager().canRequestPackageInstalls()) {
            state = PERMISSION;
            Intent settings = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + ctx.getPackageName()));
            settings.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                ctx.startActivity(settings);
            } catch (Exception e) {
                Log.w(TAG, "no install settings screen", e);
            }
            return;
        }

        state = INSTALLING;
        WORK.execute(new Runnable() {
            @Override public void run() {
                try {
                    PackageInstaller installer = ctx.getPackageManager().getPackageInstaller();
                    PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                    params.setAppPackageName(ctx.getPackageName());
                    int id = installer.createSession(params);
                    session = id;
                    try (PackageInstaller.Session s = installer.openSession(id)) {
                        try (InputStream in = new FileInputStream(file); OutputStream out = s.openWrite("base.apk", 0, file.length())) {
                            byte[] buf = new byte[64 * 1024];
                            int n;
                            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                            s.fsync(out);
                        }
                        // the answer goes to our own receiver by its exact name (action, package and
                        // component set); Android fills in the status, so the intent stays mutable
                        Intent status = new Intent(InstallStatusReceiver.ACTION)
                            .setPackage(ctx.getPackageName())
                            .setComponent(new ComponentName(ctx, InstallStatusReceiver.class));
                        int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                        s.commit(PendingIntent.getBroadcast(ctx, id, status, flags).getIntentSender());
                    }
                } catch (Exception e) {
                    Log.w(TAG, "install failed", e);
                    fail("install");
                }
            }
        });
    }

    /** The installer's answer (InstallStatusReceiver, not exported). */
    static void onStatus(Context c, Intent intent) {
        // only the answer about our own install session counts
        if (intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -2) != session) return;
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirm = systemConfirm(c, intent.getParcelableExtra(Intent.EXTRA_INTENT));
            if (confirm == null) {
                fail("install");
                return;
            }
            try {
                c.startActivity(confirm);
            } catch (Exception e) {
                Log.w(TAG, "no confirm screen", e);
                fail("install");
            }
        } else if (status == PackageInstaller.STATUS_SUCCESS) {
            state = IDLE; // Android restarts the app with the new version
        } else {
            // cancelled by the player or refused: the file stays, the button too
            Log.w(TAG, "install status " + status + ": " + intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE));
            state = status == PackageInstaller.STATUS_FAILURE_ABORTED ? READY : ERROR;
            if (state == ERROR) error = "install";
        }
    }

    /**
     * The confirm screen comes inside the installer's answer. Only a screen of a system app (the
     * Android installer) is opened, by its exact name and without access grants to our files.
     */
    static Intent systemConfirm(Context c, Intent confirm) {
        if (confirm == null) return null;
        PackageManager pm = c.getPackageManager();
        ComponentName target = confirm.resolveActivity(pm);
        if (target == null) return null;
        try {
            ApplicationInfo app = pm.getApplicationInfo(target.getPackageName(), 0);
            if ((app.flags & ApplicationInfo.FLAG_SYSTEM) == 0) return null;
        } catch (PackageManager.NameNotFoundException e) {
            return null;
        }
        Intent safe = new Intent(confirm);
        safe.setComponent(target);
        safe.removeFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        safe.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return safe;
    }

    static void cleanup(Context ctx) {
        File[] files = new File(ctx.getFilesDir(), "update").listFiles();
        if (files != null && state == IDLE) for (File f : files) f.delete();
    }
}
