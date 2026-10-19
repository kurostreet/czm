package ru.kurostreet.counterzombiemobile;

import android.content.Context;

/** Google Play updates the game itself (StoreUpdates); this build has no installer code. */
final class SelfUpdate {
    private SelfUpdate() {}

    static String state() { return "0 0 0 "; }

    static void cancel() {}

    static void start(Context ctx, String url, String sha256, long size,
                      String patchUrl, String patchSha, long patchSize, String baseSha) {}

    static void install(Context ctx) {}

    static void cleanup(Context ctx) {}
}
