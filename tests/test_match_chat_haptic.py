"""Compile the production Java haptic bridge against deterministic Android adapters."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/app/src/main/java/ru/kurostreet/counterzombiemobile/CzmFeedback.java"
CLASS_NAME = "ru.kurostreet.counterzombiemobile.CzmFeedbackHapticTest"

# Exported with HARNESS so the same actual-Java checks can run under Termux's JDK.
STUBS = {
    "android/content/Context.java": r'''package android.content;
public class Context {}
''',
    "android/app/Activity.java": r'''package android.app;
import android.content.Context;
import java.util.ArrayList;
import java.util.List;
public class Activity extends Context {
    public static boolean executingUi;
    public static int totalScheduled;
    public boolean finishing, destroyed, windowFocus = true;
    public final List<Runnable> pending = new ArrayList<>();
    public boolean isFinishing() { return finishing; }
    public boolean isDestroyed() { return destroyed; }
    public boolean hasWindowFocus() { return windowFocus; }
    public void runOnUiThread(Runnable action) {
        totalScheduled++;
        pending.add(action);
    }
    public void drainUi() {
        boolean previous = executingUi;
        executingUi = true;
        try {
            while (!pending.isEmpty()) pending.remove(0).run();
        } finally {
            executingUi = previous;
        }
    }
}
''',
    "android/view/HapticFeedbackConstants.java": r'''package android.view;
public final class HapticFeedbackConstants {
    public static final int KEYBOARD_TAP = 3;
    public static final int FLAG_IGNORE_VIEW_SETTING = 1;
    public static final int FLAG_IGNORE_GLOBAL_SETTING = 2;
}
''',
    "android/view/View.java": r'''package android.view;
import android.app.Activity;
public class View {
    public static boolean systemHapticEnabled = true;
    public boolean attached = true, shown = true, windowFocus = true;
    public boolean hapticFeedbackEnabled = true;
    public int attempts, delivered, oneArgumentCalls, twoArgumentCalls;
    public int lastConstant = -1, lastFlags = -1;
    public boolean isAttachedToWindow() { return attached; }
    public boolean isShown() { return shown; }
    public boolean hasWindowFocus() { return windowFocus; }
    public boolean isHapticFeedbackEnabled() { return hapticFeedbackEnabled; }
    public boolean performHapticFeedback(int constant) {
        if (!Activity.executingUi) throw new AssertionError("haptics must run on the UI thread");
        oneArgumentCalls++;
        attempts++;
        lastConstant = constant;
        lastFlags = 0;
        boolean accepted = systemHapticEnabled && hapticFeedbackEnabled;
        if (accepted) delivered++;
        return accepted;
    }
    public boolean performHapticFeedback(int constant, int flags) {
        if (!Activity.executingUi) throw new AssertionError("haptics must run on the UI thread");
        twoArgumentCalls++;
        attempts++;
        lastConstant = constant;
        lastFlags = flags;
        boolean accepted = (systemHapticEnabled || (flags & 2) != 0)
            && (hapticFeedbackEnabled || (flags & 1) != 0);
        if (accepted) delivered++;
        return accepted;
    }
}
''',
    "org/libsdl/app/SDLActivity.java": r'''package org.libsdl.app;
import android.content.Context;
import android.view.View;
public class SDLActivity {
    public static Context context;
    public static View contentView;
    public static Context getContext() { return context; }
    public static View getContentView() { return contentView; }
}
''',
    "android/os/Build.java": r'''package android.os;
public final class Build {
    public static final class VERSION { public static int SDK_INT = 35; }
    public static final class VERSION_CODES {
        public static final int JELLY_BEAN_MR1 = 17, JELLY_BEAN_MR2 = 18, KITKAT = 19;
    }
}
''',
}

HARNESS = r'''
package ru.kurostreet.counterzombiemobile;
import android.app.Activity;
import android.content.Context;
import android.view.HapticFeedbackConstants;
import android.view.View;
import org.libsdl.app.SDLActivity;

public final class CzmFeedbackHapticTest {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    static final class Fixture {
        final Activity activity = new Activity();
        final View view = new View();
        Fixture() {
            SDLActivity.context = activity;
            SDLActivity.contentView = view;
            View.systemHapticEnabled = true;
            Activity.executingUi = false;
        }
        void tap() { CzmFeedback.matchKeyHaptic(); }
        void drain() { activity.drainUi(); }
        void noTap(String reason) {
            check(view.attempts == 0 && view.delivered == 0, reason);
            check(view.twoArgumentCalls == 0, "no forced haptic overload: " + reason);
        }
    }
    static void normalTapAndRapidTyping() {
        Fixture f = new Fixture();
        f.tap();
        check(f.view.attempts == 0 && f.activity.pending.size() == 1, "queue one tap on the UI thread");
        f.drain();
        check(f.view.attempts == 1 && f.view.delivered == 1, "one accepted key produces one haptic request");
        check(f.view.lastConstant == HapticFeedbackConstants.KEYBOARD_TAP, "use the platform keyboard tap feedback");
        check(f.view.oneArgumentCalls == 1 && f.view.twoArgumentCalls == 0 && f.view.lastFlags == 0,
            "use the one-argument API without settings override flags");
        f.drain();
        check(f.view.attempts == 1, "draining an empty queue must not repeat feedback");

        f = new Fixture();
        for (int i = 0; i < 160; i++) f.tap();
        check(f.activity.pending.size() == 160 && f.view.attempts == 0, "rapid key presses queue once each");
        f.drain();
        check(f.view.attempts == 160 && f.view.delivered == 160 && f.view.oneArgumentCalls == 160,
            "rapid typing has neither dropped nor duplicated callbacks");
        check(f.view.twoArgumentCalls == 0, "rapid typing never forces feedback settings");
        f.drain();
        check(f.view.attempts == 160, "rapid callbacks execute once only");
    }
    static void unavailableContextAndInitialLifecycle() {
        View view = new View();
        SDLActivity.contentView = view;
        int scheduled = Activity.totalScheduled;
        SDLActivity.context = null;
        CzmFeedback.matchKeyHaptic();
        SDLActivity.context = new Context();
        CzmFeedback.matchKeyHaptic();
        check(Activity.totalScheduled == scheduled && view.attempts == 0, "no Activity is a no-op");

        for (int invalid = 0; invalid < 7; invalid++) {
            Fixture f = new Fixture();
            if (invalid == 0) f.activity.finishing = true;
            if (invalid == 1) f.activity.destroyed = true;
            if (invalid == 2) f.activity.windowFocus = false;
            if (invalid == 3) SDLActivity.contentView = null;
            if (invalid == 4) f.view.attached = false;
            if (invalid == 5) f.view.shown = false;
            if (invalid == 6) f.view.windowFocus = false;
            f.tap();
            f.drain();
            f.noTap("initial inactive Activity/view must not receive feedback: " + invalid);
        }
    }
    static void staleActivityAndView() {
        Fixture f = new Fixture();
        f.tap();
        Activity replacement = new Activity();
        SDLActivity.context = replacement;
        f.drain();
        f.noTap("a replacement Activity cannot receive a callback queued for its predecessor");
        check(replacement.pending.isEmpty(), "do not transfer queued feedback to another Activity");

        f = new Fixture();
        f.tap();
        SDLActivity.context = null;
        f.drain();
        f.noTap("lost SDL Activity drops queued feedback");

        f = new Fixture();
        f.tap();
        View replacementView = new View();
        SDLActivity.contentView = replacementView;
        f.drain();
        f.noTap("a replaced content view invalidates the old queued tap");
        check(replacementView.attempts == 0, "a stale tap must not vibrate a newly installed view");

        f = new Fixture();
        f.tap();
        SDLActivity.contentView = null;
        f.drain();
        f.noTap("a missing content view drops queued feedback");
    }
    static void lifecycleChangesBeforeUiExecution() {
        for (int invalid = 0; invalid < 6; invalid++) {
            Fixture f = new Fixture();
            f.tap();
            check(f.activity.pending.size() == 1, "the foreground tap was queued before lifecycle change");
            if (invalid == 0) f.activity.finishing = true;
            if (invalid == 1) f.activity.destroyed = true;
            if (invalid == 2) f.activity.windowFocus = false;
            if (invalid == 3) f.view.attached = false;
            if (invalid == 4) f.view.shown = false;
            if (invalid == 5) f.view.windowFocus = false;
            f.drain();
            f.noTap("recheck Activity/view lifecycle at UI execution: " + invalid);
        }
        Fixture f = new Fixture();
        f.tap();
        f.activity.windowFocus = false;
        f.drain();
        f.activity.windowFocus = true;
        f.tap();
        f.drain();
        check(f.view.attempts == 1 && f.view.delivered == 1, "only a fresh key after returning to the game vibrates");
    }
    static void systemAndViewSettingsAreRespected() {
        Fixture f = new Fixture();
        View.systemHapticEnabled = false;
        f.tap();f.drain();
        check(f.view.attempts == 1 && f.view.delivered == 0 && f.view.twoArgumentCalls == 0,
            "disabled OS haptics remain disabled without retry or force flags");
        View.systemHapticEnabled = true;
        f.tap();f.drain();
        check(f.view.attempts == 2 && f.view.delivered == 1, "a later tap follows the current OS setting");

        f = new Fixture();f.view.hapticFeedbackEnabled = false;
        f.tap();f.drain();
        check(f.view.attempts == 1 && f.view.delivered == 0 && f.view.twoArgumentCalls == 0,
            "the view's feedback preference is not overridden");
        f = new Fixture();f.tap();View.systemHapticEnabled = false;f.drain();
        check(f.view.attempts == 1 && f.view.delivered == 0, "OS setting is honored when the queued callback executes");
    }
    public static void main(String[] args) {
        normalTapAndRapidTyping();
        unavailableContextAndInitialLifecycle();
        staleActivityAndView();
        lifecycleChangesBeforeUiExecution();
        systemAndViewSettingsAreRespected();
        System.out.println("MATCH_CHAT_HAPTIC_OK");
    }
}
'''


def prepare_java_sources(folder):
    """Write adapters and copy the whole production class; return javac inputs."""
    folder = Path(folder)
    for name, source in STUBS.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    package = folder / "ru/kurostreet/counterzombiemobile"
    package.mkdir(parents=True, exist_ok=True)
    (package / JAVA.name).write_text(JAVA.read_text())
    (package / "CzmFeedbackHapticTest.java").write_text(HARNESS)
    return sorted(str(path) for path in folder.rglob("*.java"))


class MatchChatHapticTests(unittest.TestCase):
    def test_actual_java_feedback_lifecycle_and_system_settings(self):
        if not shutil.which("javac") or not shutil.which("java"):
            self.skipTest("requires javac and java; exported STUBS/HARNESS can run with the Termux JDK")
        with tempfile.TemporaryDirectory(prefix="czm-match-haptic-") as temporary:
            folder = Path(temporary)
            sources = prepare_java_sources(folder)
            subprocess.run(["javac", "--release", "11", "-encoding", "UTF-8", "-d", str(folder / "classes"), *sources],
                           check=True)
            result = subprocess.run(["java", "-cp", str(folder / "classes"), CLASS_NAME],
                                    check=True, text=True, capture_output=True, timeout=20)
            self.assertIn("MATCH_CHAT_HAPTIC_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
