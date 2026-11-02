"""The RuStore build: its own package, updated by RuStore only (no installer code, no Play libraries)."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'android/app'
FLAVOR = APP / 'src/rustore'
CLASSES = FLAVOR / 'java/ru/kurostreet/counterzombiemobile'

STUBS = {
    'android/content/Context.java': '''package android.content;
        public class Context { public String getPackageName(){return "ru.kurostreet.counterzombiemobile";} }''',
    'android/content/ActivityNotFoundException.java': '''package android.content;
        public class ActivityNotFoundException extends RuntimeException {}''',
    'android/content/Intent.java': '''package android.content; import android.net.Uri;
        public class Intent { public static final String ACTION_VIEW="android.intent.action.VIEW";
        public final String action; public final Uri uri; public Intent(String a,Uri u){action=a;uri=u;} }''',
    'android/net/Uri.java': '''package android.net; public class Uri {
        private final String value; private Uri(String s){value=s;}
        public static Uri parse(String s){return new Uri(s);} public String toString(){return value;} }''',
    'android/app/Activity.java': '''package android.app; import android.content.*; import java.util.*;
        public class Activity extends Context { public final List<Intent> opened=new ArrayList<>();
        public int fail,attempts; public void runOnUiThread(Runnable r){r.run();}
        public void startActivity(Intent i){attempts++;if(fail-->0)throw new ActivityNotFoundException();opened.add(i);} }''',
    'ru/kurostreet/counterzombiemobile/RuStoreTest.java': '''package ru.kurostreet.counterzombiemobile;
        import android.app.Activity;
        public class RuStoreTest {
        static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
        public static void main(String[] args){
            Activity activity=new Activity();
            check(StoreUpdates.state(activity).isEmpty(),"RuStore installs updates itself: no bell");
            check(SelfUpdate.state().equals("0 0 0 ")&&!DistributionAccess.changed(),"no installer, no test access");
            StoreUpdates.start(activity);
            check(activity.opened.size()==1&&activity.opened.get(0).uri.toString().equals("rustore://apps.rustore.ru/app/ru.kurostreet.counterzombiemobile"),"the game's RuStore card");
            Activity browser=new Activity();browser.fail=1;StoreUpdates.start(browser);
            check(browser.opened.size()==1&&browser.opened.get(0).uri.toString().equals("https://www.rustore.ru/catalog/app/ru.kurostreet.counterzombiemobile"),"the site when RuStore is missing");
            Activity nothing=new Activity();nothing.fail=2;StoreUpdates.start(nothing);
            check(nothing.attempts==2&&nothing.opened.isEmpty(),"no store or browser must not crash the game");
            StoreUpdates.start(null);
            System.out.println("RUSTORE_BUILD_OK");
        }}''',
}


def flavor(gradle: str, name: str) -> str:
    start = gradle.index(f'create("{name}")')
    return gradle[start:gradle.index('\n\t\t}', start)]


class RuStoreBuildTests(unittest.TestCase):
    def test_flavors_choose_who_updates_the_game(self):
        gradle = (APP / 'build.gradle').read_text()
        rustore = flavor(gradle, 'rustore')
        # the game's own identifier (defaultConfig), not Play's and not the site test build's
        self.assertNotIn('applicationId', rustore)
        self.assertNotIn('applicationIdSuffix', rustore)
        self.assertIn('applicationId = "ru.kurostreet.counterzombiemobile"', gradle)
        self.assertIn('"SELF_UPDATE", "false"', rustore)
        self.assertIn('"SELF_UPDATE", "false"', flavor(gradle, 'googlePlay'))
        self.assertIn('"SELF_UPDATE", "true"', flavor(gradle, 'git'))
        self.assertIn('abiFilters "armeabi-v7a", "arm64-v8a" }', rustore)
        # Play libraries only in the Play build
        for line in gradle.splitlines():
            if ('"com.google.android.play' in line or '"androidx.fragment' in line) and not line.strip().startswith('//'):
                self.assertTrue(line.strip().startswith('googlePlayImplementation'), line)
        java = (APP / 'src/main/java/ru/kurostreet/counterzombiemobile/CzmNet.java').read_text()
        self.assertIn('return BuildConfig.SELF_UPDATE;', java)

    def test_no_installer_permission_and_no_play_code(self):
        self.assertFalse((FLAVOR / 'AndroidManifest.xml').exists(), 'REQUEST_INSTALL_PACKAGES lives in the site build only')
        self.assertNotIn('REQUEST_INSTALL_PACKAGES', (APP / 'src/main/AndroidManifest.xml').read_text())
        for source in FLAVOR.rglob('*.java'):
            text = source.read_text()
            self.assertNotRegex(text, re.compile(r'com\.google\.android\.play|PackageInstaller|play\.google'), source.name)

    def test_store_card_and_empty_bell(self):
        if not shutil.which('javac'):
            self.skipTest('requires javac')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name, content in STUBS.items():
                file = folder / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            sources = [str(p) for p in folder.rglob('*.java')] + [str(p) for p in CLASSES.glob('*.java')]
            subprocess.run(['javac', '--release', '11', '-encoding', 'UTF-8', '-d', temporary, *sources], check=True)
            result = subprocess.run(['java', '-cp', temporary, 'ru.kurostreet.counterzombiemobile.RuStoreTest'],
                                    capture_output=True, text=True, check=True)
            self.assertIn('RUSTORE_BUILD_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
