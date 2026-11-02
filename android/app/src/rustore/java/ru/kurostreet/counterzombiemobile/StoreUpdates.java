package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;

/**
 * RuStore build: RuStore installs updates by itself, so the bell does not ask about them
 * (state is always empty). start() only opens the game's page in RuStore, or on the RuStore
 * site when the store app is missing.
 */
final class StoreUpdates {
    private StoreUpdates() {}

    static String state(Context ctx) { return ""; }

    static void start(Context ctx) {
        if (!(ctx instanceof Activity)) return;
        Activity activity = (Activity) ctx;
        activity.runOnUiThread(() -> openStore(activity));
    }

    private static void openStore(Activity activity) {
        String id = activity.getPackageName();
        try {
            activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("rustore://apps.rustore.ru/app/" + id)));
        } catch (ActivityNotFoundException | SecurityException e) {
            try {
                activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.rustore.ru/catalog/app/" + id)));
            } catch (ActivityNotFoundException | SecurityException unavailable) {
                // A missing store/browser must not crash the running game.
            }
        }
    }
}
