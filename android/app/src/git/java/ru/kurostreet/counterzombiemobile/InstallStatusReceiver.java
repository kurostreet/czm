package ru.kurostreet.counterzombiemobile;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** The Android installer's answer for SelfUpdate; declared not exported in the site build's manifest. */
public final class InstallStatusReceiver extends BroadcastReceiver {
    static final String ACTION = "ru.kurostreet.counterzombiemobile.INSTALL_STATUS";

    @Override public void onReceive(Context c, Intent intent) {
        if (ACTION.equals(intent.getAction())) SelfUpdate.onStatus(c, intent);
    }
}
