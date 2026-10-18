package ru.kurostreet.counterzombiemobile;

import android.content.Context;

/** The APK from the site updates itself (CzmNet.updateStart); there is no store to ask. */
final class StoreUpdates {
    private StoreUpdates() {}

    static String state(Context ctx) { return ""; }

    static void start(Context ctx) {}
}
