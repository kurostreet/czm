/* Match keyboard feedback follows Android's normal haptic preference. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.view.HapticFeedbackConstants;
import android.view.View;
import org.libsdl.app.SDLActivity;

public final class CzmFeedback {
    private CzmFeedback() {}

    public static void matchKeyHaptic() {
        Context context = SDLActivity.getContext();
        if (!(context instanceof Activity)) return;
        Activity activity = (Activity) context;
        View view = SDLActivity.getContentView();
        if (view == null) return;
        activity.runOnUiThread(() -> {
            // A queued key from an old window must not buzz after a pause or recreation.
            if (SDLActivity.getContext() != activity || SDLActivity.getContentView() != view
                    || activity.isFinishing() || activity.isDestroyed() || !activity.hasWindowFocus()
                    || !view.isAttachedToWindow() || !view.hasWindowFocus() || !view.isShown()) return;
            // No IGNORE_* flags: Android and the view decide whether feedback is enabled.
            view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
        });
    }
}
