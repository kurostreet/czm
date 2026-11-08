"""Compile the real manager and exercise fresh mapping, leases and join cancellation."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / 'android/app/src/main/java/ru/kurostreet/counterzombiemobile'

STUBS = {
    'android/content/Context.java': '''package android.content;
public class Context {
 public static final String CONNECTIVITY_SERVICE="connectivity";
 public java.io.File getFilesDir(){return new java.io.File(System.getProperty("java.io.tmpdir"),"czm-manager-test-unused");}
 public Object getSystemService(String key){return new android.net.ConnectivityManager();}
 public Preferences getSharedPreferences(String key,int mode){return new Preferences();}
 public static class Preferences { public boolean getBoolean(String key,boolean fallback){return fallback;} public Editor edit(){return new Editor();} }
 public static class Editor { public Editor putBoolean(String key,boolean value){return this;} public void apply(){} }
}''',
    'android/app/Activity.java': '''package android.app; public class Activity extends android.content.Context { public boolean isFinishing(){return false;} public void runOnUiThread(Runnable action){} }''',
    'android/net/ConnectivityManager.java': '''package android.net; public class ConnectivityManager { public boolean isActiveNetworkMetered(){return true;} }''',
    'android/os/Looper.java': '''package android.os; public class Looper {public static Looper getMainLooper(){return new Looper();}}''',
    'android/os/Handler.java': '''package android.os; public class Handler {public Handler(Looper looper){} public boolean post(Runnable action){return true;} public boolean postDelayed(Runnable action,long delay){return true;} public void removeCallbacks(Runnable action){} }''',
    'android/view/View.java': '''package android.view; public class View {public static final int GONE=8; public interface OnClickListener {void onClick(View view);} public void setOnClickListener(OnClickListener action){} public void setEnabled(boolean enabled){} public void setVisibility(int value){} }''',
    'android/widget/TextView.java': '''package android.widget; public class TextView extends android.view.View { public TextView(){} public TextView(android.content.Context context){} public void setText(CharSequence text){} public void setTextColor(int color){} public void setTextSize(float value){} }''',
    'android/widget/Button.java': '''package android.widget; public class Button extends TextView {public Button(){} public Button(android.content.Context context){} }''',
    'android/widget/CheckBox.java': '''package android.widget; public class CheckBox extends Button { public interface Listener {void onCheckedChanged(CheckBox view,boolean checked);} public CheckBox(android.content.Context context){} public void setChecked(boolean value){} public void setOnCheckedChangeListener(Listener listener){} }''',
    'android/widget/ProgressBar.java': '''package android.widget; public class ProgressBar extends android.view.View {public ProgressBar(android.content.Context context,Object attrs,int style){} public void setMax(int value){} public void setProgress(int value){} public void setIndeterminate(boolean value){} }''',
    'android/widget/LinearLayout.java': '''package android.widget; public class LinearLayout extends android.view.View { public static class LayoutParams {public LayoutParams(int width,int height){}} public void addView(android.view.View view){} public void addView(android.view.View view,LayoutParams params){} }''',
    'android/R.java': '''package android; public final class R {public static class attr {public static final int progressBarStyleHorizontal=1;}}''',
    'org/libsdl/app/SDLActivity.java': '''package org.libsdl.app; public class SDLActivity {public static android.content.Context getContext(){return null;}}''',
    'ru/kurostreet/counterzombiemobile/CzmDialog.java': '''package ru.kurostreet.counterzombiemobile;
final class CzmDialog {static final int MUTED=0; final android.widget.Button submit=new android.widget.Button(); final android.widget.TextView error=new android.widget.TextView(); final android.widget.LinearLayout body=new android.widget.LinearLayout(); interface Dismiss {void dismissed(CzmDialog dialog);} CzmDialog(android.app.Activity a,String title,String text,String ok,String cancel,boolean ru,boolean secure){} static int dp(android.content.Context c,int value){return value;} android.widget.TextView note(String text){return new android.widget.TextView();} android.widget.Button link(String text,android.view.View.OnClickListener listener){return new android.widget.Button();} void fail(String text){} boolean isShowing(){return false;} void dismiss(){} void show(){} void setOnDismissListener(Dismiss listener){} }''',
}


class ServerResourcesManagerTest(unittest.TestCase):
    def test_actual_manager_mapping_expiry_and_single_use_mount(self):
        jar = Path(os.environ.get('CZM_JSON_JAR', '/missing'))
        if not shutil.which('javac') or not jar.is_file():
            self.skipTest('requires javac and JSON jar')
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            stubs = []
            for name, content in STUBS.items():
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                stubs.append(str(path))
            subprocess.run(['javac', '--release', '11', '-encoding', 'UTF-8', '-cp', str(jar), '-d', directory]
                           + stubs + [str(JAVA / (name + '.java')) for name in ['ServerPolicy', 'ServerResourceStore', 'ServerResources']]
                           + [str(ROOT / 'tests/ServerResourcesManagerTest.java')], check=True)
            result = subprocess.run(['java', '-cp', directory + os.pathsep + str(jar),
                                     'ru.kurostreet.counterzombiemobile.ServerResourcesManagerTest'],
                                    text=True, capture_output=True, timeout=35)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('SERVER_RESOURCES_MANAGER_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
