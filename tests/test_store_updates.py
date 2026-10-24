"""Execute the real Play update router without credentials, network or Android UI."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / 'android/app/src/googlePlay/java/ru/kurostreet/counterzombiemobile/StoreUpdates.java'

STUBS = {
    'android/content/Context.java': '''package android.content;
        public class Context { public Context getApplicationContext(){return this;}
        public String getPackageName(){return "dev.gaming.czm";} }''',
    'android/content/ActivityNotFoundException.java': '''package android.content;
        public class ActivityNotFoundException extends RuntimeException {}''',
    'android/content/Intent.java': '''package android.content; import android.net.Uri;
        public class Intent { public static final String ACTION_VIEW="android.intent.action.VIEW";
        public final String action; public final Uri uri; public String target;
        public Intent(String a,Uri u){action=a;uri=u;} public Intent setPackage(String p){target=p;return this;} }''',
    'android/net/Uri.java': '''package android.net; public class Uri {
        private final String value; private Uri(String s){value=s;}
        public static Uri parse(String s){return new Uri(s);} public String toString(){return value;} }''',
    'android/app/Activity.java': '''package android.app; import android.content.*; import java.util.*;
        public class Activity extends Context { public final List<Intent> opened=new ArrayList<>();
        public int fail,attempts; public void runOnUiThread(Runnable r){r.run();}
        public void startActivity(Intent i){attempts++;if(fail-->0)throw new ActivityNotFoundException();opened.add(i);} }''',
    'android/os/SystemClock.java': '''package android.os; public class SystemClock {
        public static long now; public static long elapsedRealtime(){return now;} }''',
    'com/google/android/gms/tasks/Task.java': '''package com.google.android.gms.tasks;
        import java.util.function.Consumer; public class Task<T> { final T value; final boolean fail;
        public Task(T v,boolean f){value=v;fail=f;}
        public Task<T> addOnSuccessListener(Consumer<T> c){if(!fail)c.accept(value);return this;}
        public Task<T> addOnFailureListener(Consumer<Exception> c){if(fail)c.accept(new Exception("offline"));return this;} }''',
    'com/google/android/play/core/install/model/UpdateAvailability.java': '''package com.google.android.play.core.install.model;
        public class UpdateAvailability { public static final int UPDATE_NOT_AVAILABLE=1,UPDATE_AVAILABLE=2,DEVELOPER_TRIGGERED_UPDATE_IN_PROGRESS=3; }''',
    'com/google/android/play/core/appupdate/AppUpdateInfo.java': '''package com.google.android.play.core.appupdate;
        public class AppUpdateInfo { final int state,version; final long bytes;
        public AppUpdateInfo(int s,int v,long b){state=s;version=v;bytes=b;}
        public int updateAvailability(){return state;} public int availableVersionCode(){return version;}
        public long totalBytesToDownload(){return bytes;}
        public boolean isUpdateTypeAllowed(int type){throw new AssertionError("Availability must not depend on immediate-update eligibility");} }''',
    'com/google/android/play/core/appupdate/AppUpdateManager.java': '''package com.google.android.play.core.appupdate;
        import com.google.android.gms.tasks.Task; public class AppUpdateManager {
        public int requests; public boolean throwsError; public Task<AppUpdateInfo> next;
        public Task<AppUpdateInfo> getAppUpdateInfo(){requests++;if(throwsError)throw new RuntimeException("offline");return next;} }''',
    'com/google/android/play/core/appupdate/AppUpdateManagerFactory.java': '''package com.google.android.play.core.appupdate;
        import android.content.Context; public class AppUpdateManagerFactory {
        public static final AppUpdateManager instance=new AppUpdateManager();
        public static AppUpdateManager create(Context c){return instance;} }''',
    'ru/kurostreet/counterzombiemobile/StoreUpdatesTest.java': '''package ru.kurostreet.counterzombiemobile;
        import android.app.Activity; import android.os.SystemClock; import com.google.android.gms.tasks.Task;
        import com.google.android.play.core.appupdate.*; import com.google.android.play.core.install.model.UpdateAvailability;
        public class StoreUpdatesTest {
        static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
        static final AppUpdateManager manager=AppUpdateManagerFactory.instance;
        static void offer(int state,int version,long bytes){manager.next=new Task<>(new AppUpdateInfo(state,version,bytes),false);}
        static void advance(){SystemClock.now+=31*60*1000L;}
        public static void main(String[] args){
            Activity activity=new Activity();
            check(StoreUpdates.state(null).isEmpty()&&manager.requests==0,"no context must not query Play");
            offer(UpdateAvailability.UPDATE_AVAILABLE,40102000,25000000);
            check(StoreUpdates.state(activity).equals("40102000 25000000"),"available update produces bell state");
            check(StoreUpdates.state(activity).equals("40102000 25000000")&&manager.requests==1,"cache avoids per-frame queries");
            StoreUpdates.start(activity);
            check(manager.requests==1&&activity.opened.size()==1,"tap opens store immediately without another network request");
            check(activity.opened.get(0).uri.toString().equals("market://details?id=dev.gaming.czm"),"correct existing game listing");
            check(activity.opened.get(0).target.equals("com.android.vending"),"explicit Google Play destination");
            Activity browser=new Activity();browser.fail=1;StoreUpdates.start(browser);
            check(browser.opened.size()==1&&browser.opened.get(0).uri.toString().equals("https://play.google.com/store/apps/details?id=dev.gaming.czm"),"browser fallback");
            Activity unavailable=new Activity();unavailable.fail=2;StoreUpdates.start(unavailable);
            check(unavailable.attempts==2&&unavailable.opened.isEmpty(),"no store or browser must not crash the game");
            advance();offer(UpdateAvailability.UPDATE_NOT_AVAILABLE,40103000,100);
            check(StoreUpdates.state(activity).isEmpty(),"no update for this Play account means no badge");
            advance();manager.next=new Task<>(null,true);StoreUpdates.state(activity);int count=manager.requests;
            offer(UpdateAvailability.UPDATE_AVAILABLE,40104000,400);
            SystemClock.now+=59999;check(StoreUpdates.state(activity).isEmpty()&&manager.requests==count,"failed request backs off");
            SystemClock.now++;check(StoreUpdates.state(activity).equals("40104000 400")&&manager.requests==count+1,"retry after network recovery");
            advance();manager.throwsError=true;check(StoreUpdates.state(activity).isEmpty(),"synchronous Play failure is contained");
            manager.throwsError=false;SystemClock.now+=60000;
            offer(UpdateAvailability.DEVELOPER_TRIGGERED_UPDATE_IN_PROGRESS,40105000,-1);
            check(StoreUpdates.state(activity).equals("40105000 0"),"existing pending update remains visible, unknown size is safe");
            StoreUpdates.start(null);System.out.println("PLAY_BELL_AND_STORE_NAVIGATION_OK");
        }}''',
}


class StoreUpdateTests(unittest.TestCase):
    def test_account_specific_availability_retry_and_store_navigation(self):
        if not shutil.which('javac'):
            self.skipTest('requires javac')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name, content in STUBS.items():
                file = folder / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            sources = [str(p) for p in folder.rglob('*.java')] + [str(JAVA)]
            subprocess.run(['javac', '--release', '11', '-encoding', 'UTF-8', '-d', temporary, *sources], check=True)
            result = subprocess.run(['java', '-cp', temporary, 'ru.kurostreet.counterzombiemobile.StoreUpdatesTest'],
                                    capture_output=True, text=True, check=True)
            self.assertIn('PLAY_BELL_AND_STORE_NAVIGATION_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
