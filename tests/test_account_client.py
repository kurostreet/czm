"""Host-side execution of the real account router; UI and Android Keystore need a device."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/app/src/main/java/ru/kurostreet/counterzombiemobile"


class AccountClientTests(unittest.TestCase):
    def test_pending_email_login_survives_recreation(self):
        if not shutil.which("javac"):
            self.skipTest("requires javac")
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run(["javac", "--release", "11", "-encoding", "UTF-8", "-d", temp,
                            str(JAVA / "EmailLoginState.java"), str(JAVA / "PasswordChangeState.java"), str(ROOT / "tests/EmailLoginStateTest.java")], check=True)
            result = subprocess.run(["java", "-cp", temp, "ru.kurostreet.counterzombiemobile.EmailLoginStateTest"],
                                    check=True, capture_output=True, text=True)
            self.assertIn("EMAIL_LOGIN_RESTORE_OK", result.stdout)

    def test_restore_origin_and_switching_requests(self):
        sdk = os.environ.get("CZM_ANDROID_JAR") or str(Path(os.environ.get("ANDROID_HOME", "/missing")) / "platforms/android-36/android.jar")
        json = os.environ.get("CZM_JSON_JAR", "/missing")
        if not shutil.which("javac") or not Path(sdk).is_file() or not Path(json).is_file():
            self.skipTest("requires javac, Android 36 SDK and the JSON test jar")
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            sources = {
                "SDLActivity": "package org.libsdl.app; public class SDLActivity { public static android.content.Context getContext(){return null;} }",
                "CzmGameActivity": "package ru.kurostreet.counterzombiemobile; public class CzmGameActivity extends android.app.Activity { public void menuReady(){} void prepareBackgroundDownload(){} }",
                "CzmDownloadService": "package ru.kurostreet.counterzombiemobile; public class CzmDownloadService {}",
                "SystemClock": "package android.os; public class SystemClock { public static long elapsedRealtime(){return 1000;} }",
                "BuildConfig": "package ru.kurostreet.counterzombiemobile; public class BuildConfig { public static final boolean IS_GOOGLE_PLAY_BUILD=false; }",
                # The account-router unit test intentionally runs without the
                # microphone, Android media stack or WebSocket dependency.
                # CzmNet forwards to the voice service, so give it a minimal
                # interface stub; Gradle compiles the real CzmLobbyVoice.java.
                "CzmLobbyVoice": """package ru.kurostreet.counterzombiemobile;
                    public final class CzmLobbyVoice {
                        public static void start(String url,String key){}
                        public static void stop(){}
                        public static void setMic(boolean enabled){}
                        public static boolean microphoneOn(){return false;}
                        public static boolean speaking(int player){return false;}
                        public static int state(){return 0;}
                        public static void mutePlayer(int player,boolean enabled){}
                        public static boolean locallyMuted(int player){return false;}
                    }""",
            }
            for name, text in sources.items():
                (tmp / (name + ".java")).write_text(text)
            files = [str(JAVA / (name + ".java")) for name in ("CzmNet", "CzmAccount", "EmailLoginState", "CzmDialog", "CzmServerAuth", "ServerAuthData", "CzmColorPicker", "ColorWheelData", "CzmCodeInput", "CzmCloud", "SettingsData", "SettingsSchema", "CzmLayoutActivity", "CzmLayoutProvider", "ServerQuery")]
            files += [str(JAVA / "CzmDownloads.java"),str(JAVA / "PasswordChangeState.java")]
            # the site build's flavor classes (the Google Play StoreUpdates needs the Play library)
            git = ROOT / "android/app/src/git/java/ru/kurostreet/counterzombiemobile"
            files += [str(git / (name + ".java")) for name in ("StoreUpdates", "SelfUpdate", "InstallStatusReceiver", "ApkUpdate", "DistributionAccess", "DevelopmentInvite")]
            cp = os.pathsep.join([json, sdk])
            subprocess.run(["javac", "--release", "11", "-encoding", "UTF-8", "-cp", cp, "-d", temp] +
                           [str(x) for x in tmp.glob("*.java")] + files + [str(ROOT / "tests/AccountClientTest.java"),str(ROOT / "tests/DownloadsStateTest.java")], check=True)
            result = subprocess.run(["java", "-cp", temp + os.pathsep + cp,
                                     "ru.kurostreet.counterzombiemobile.AccountClientTest"], check=True, capture_output=True, text=True)
            self.assertIn("ACCOUNT_CLIENT_ROUTING_OK", result.stdout)
            result = subprocess.run(["java", "-cp", temp + os.pathsep + cp,
                                     "ru.kurostreet.counterzombiemobile.DownloadsStateTest"], check=True, capture_output=True, text=True)
            self.assertIn("DOWNLOADS_STATE_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
