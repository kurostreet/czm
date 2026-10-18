package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.SystemClock;

import com.google.android.play.core.appupdate.AppUpdateInfo;
import com.google.android.play.core.appupdate.AppUpdateManager;
import com.google.android.play.core.appupdate.AppUpdateManagerFactory;
import com.google.android.play.core.appupdate.AppUpdateOptions;
import com.google.android.play.core.install.model.AppUpdateType;
import com.google.android.play.core.install.model.UpdateAvailability;

/**
 * Google Play build: the game never installs APKs itself (Play rules). The bell asks Google Play
 * whether a newer version is out and starts Play's own update screen over the game.
 */
final class StoreUpdates {
    private static final long RECHECK_MS = 30 * 60 * 1000L;
    private static volatile int available;      // version code offered by Play, 0: none
    private static volatile long bytes;
    private static volatile long checkedAt = -RECHECK_MS;
    private static AppUpdateManager manager;

    private StoreUpdates() {}

    private static synchronized AppUpdateManager manager(Context ctx) {
        if (manager == null) manager = AppUpdateManagerFactory.create(ctx.getApplicationContext());
        return manager;
    }

    private static boolean offered(AppUpdateInfo info) {
        int state = info.updateAvailability();
        return state == UpdateAvailability.DEVELOPER_TRIGGERED_UPDATE_IN_PROGRESS
            || (state == UpdateAvailability.UPDATE_AVAILABLE && info.isUpdateTypeAllowed(AppUpdateType.IMMEDIATE));
    }

    /** "code bytes" of the version Play offers, or "" (a new check starts every 30 minutes). */
    static String state(Context ctx) {
        if (ctx == null) return "";
        long now = SystemClock.elapsedRealtime();
        if (now - checkedAt >= RECHECK_MS) {
            checkedAt = now;
            try {
                manager(ctx).getAppUpdateInfo()
                    .addOnSuccessListener(info -> {
                        boolean ok = offered(info);
                        bytes = ok ? Math.max(0, info.totalBytesToDownload()) : 0;
                        available = ok ? Math.max(1, info.availableVersionCode()) : 0;
                    })
                    .addOnFailureListener(e -> available = 0);   // not installed from Play, offline
            } catch (RuntimeException e) {
                available = 0;
            }
        }
        return available > 0 ? available + " " + bytes : "";
    }

    /** Play's own update screen; the store page when Play cannot show it. */
    static void start(Context ctx) {
        if (!(ctx instanceof Activity)) return;
        Activity activity = (Activity) ctx;
        activity.runOnUiThread(() -> {
            try {
                manager(activity).getAppUpdateInfo()
                    .addOnSuccessListener(info -> {
                        if (offered(info)) {
                            manager(activity).startUpdateFlow(info, activity, AppUpdateOptions.defaultOptions(AppUpdateType.IMMEDIATE))
                                .addOnFailureListener(e -> openStore(activity));
                        } else {
                            openStore(activity);
                        }
                    })
                    .addOnFailureListener(e -> openStore(activity));
            } catch (RuntimeException e) {
                openStore(activity);
            }
        });
    }

    private static void openStore(Activity activity) {
        String id = activity.getPackageName();
        try {
            activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + id)));
        } catch (ActivityNotFoundException e) {
            activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=" + id)));
        }
    }
}
