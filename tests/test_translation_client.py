"""Run the real translation router against the SDK's one-initialization contract."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/app/src/main/java/ru/kurostreet/counterzombiemobile"

STUBS = {
    "android/content/Context.java": """package android.content;
        public class Context { public Context getApplicationContext(){return this;} }""",
    "android/app/Activity.java": """package android.app;
        public class Activity extends android.content.Context { public boolean isFinishing(){return false;} }""",
    "android/os/Build.java": """package android.os;
        public class Build { public static class VERSION { public static int SDK_INT=35; } }""",
    "android/os/Looper.java": """package android.os;
        public class Looper { public static Looper getMainLooper(){return new Looper();} }""",
    "android/os/Handler.java": """package android.os;
        import java.util.*;
        public class Handler {
            private static long now;
            private static final List<Item> queue=new ArrayList<>();
            private static class Item { final Runnable run;final long at;Item(Runnable r,long t){run=r;at=t;} }
            public Handler(Looper l){}
            public boolean post(Runnable r){return postDelayed(r,0);}
            public boolean postDelayed(Runnable r,long delay){queue.add(new Item(r,now+delay));return true;}
            public void removeCallbacks(Runnable r){queue.removeIf(i->i.run==r);}
            public static void flush(){
                for(;;){Item next=null;for(Item i:queue)if(i.at<=now&&(next==null||i.at<next.at))next=i;
                    if(next==null)return;queue.remove(next);next.run.run();}
            }
            public static void advance(long ms){now+=ms;flush();}
        }""",
    "com/google/android/gms/tasks/Task.java": """package com.google.android.gms.tasks;
        import java.util.*;import java.util.function.Consumer;
        public class Task<T> {
            private boolean complete;private T value;private Exception error;
            private final List<Consumer<T>> success=new ArrayList<>();
            private final List<Consumer<Exception>> failure=new ArrayList<>();
            public Task<T> addOnSuccessListener(Consumer<T> f){success.add(f);if(complete&&error==null)f.accept(value);return this;}
            public Task<T> addOnFailureListener(Consumer<Exception> f){failure.add(f);if(complete&&error!=null)f.accept(error);return this;}
            public void succeed(T v){if(complete)throw new AssertionError("completed twice");complete=true;value=v;for(Consumer<T> f:success)f.accept(v);}
            public static <T> Task<T> ready(T value){Task<T> t=new Task<>();t.succeed(value);return t;}
        }""",
    "com/google/mlkit/common/MlKit.java": """package com.google.mlkit.common;
        public class MlKit {
            public static int attempts,initializations;public static boolean failNext;
            public static void initialize(android.content.Context context){
                attempts++;
                if(failNext){failNext=false;throw new IllegalStateException("Initialization failed");}
                // common18.11.0: MlKit.initialize -> MlKitContext.zza -> zzb.
                // zzb enforces the process singleton, unlike initializeIfNeeded.
                if(initializations!=0)throw new IllegalStateException("MlKitContext is already initialized");
                initializations++;
            }
        }""",
    "com/google/mlkit/common/model/DownloadConditions.java": """package com.google.mlkit.common.model;
        public class DownloadConditions { public static class Builder { public DownloadConditions build(){return new DownloadConditions();} } }""",
    "com/google/mlkit/common/model/RemoteModelManager.java": """package com.google.mlkit.common.model;
        import com.google.android.gms.tasks.Task;
        public class RemoteModelManager {
            public static boolean downloaded=true;
            public static RemoteModelManager getInstance(){return new RemoteModelManager();}
            public Task<Boolean> isModelDownloaded(Object model){return Task.ready(downloaded);}
        }""",
    "com/google/mlkit/nl/translate/TranslateLanguage.java": """package com.google.mlkit.nl.translate;
        public class TranslateLanguage { public static final String RUSSIAN="ru",ENGLISH="en"; }""",
    "com/google/mlkit/nl/translate/TranslateRemoteModel.java": """package com.google.mlkit.nl.translate;
        public class TranslateRemoteModel { public static class Builder { public Builder(String language){} public TranslateRemoteModel build(){return new TranslateRemoteModel();} } }""",
    "com/google/mlkit/nl/translate/TranslatorOptions.java": """package com.google.mlkit.nl.translate;
        public class TranslatorOptions {
            public String source,target;
            public static class Builder {
                final TranslatorOptions value=new TranslatorOptions();
                public Builder setSourceLanguage(String language){value.source=language;return this;}
                public Builder setTargetLanguage(String language){value.target=language;return this;}
                public TranslatorOptions build(){return value;}
            }
        }""",
    "com/google/mlkit/nl/translate/Translator.java": """package com.google.mlkit.nl.translate;
        import com.google.android.gms.tasks.Task;import com.google.mlkit.common.model.DownloadConditions;
        public interface Translator { Task<Void> downloadModelIfNeeded(DownloadConditions c);Task<String> translate(String text);void close(); }""",
    "com/google/mlkit/nl/translate/Translation.java": """package com.google.mlkit.nl.translate;
        import java.util.*;import com.google.android.gms.tasks.Task;
        import com.google.mlkit.common.model.*;
        public class Translation {
            public static final List<Client> clients=new ArrayList<>();
            public static final List<Task<String>> pending=new ArrayList<>();
            public static Translator getClient(TranslatorOptions options){Client c=new Client(options);clients.add(c);return c;}
            public static class Client implements Translator {
                public final TranslatorOptions options;public boolean closed;
                Client(TranslatorOptions o){options=o;}
                public Task<Void> downloadModelIfNeeded(DownloadConditions conditions){
                    if(closed)throw new IllegalStateException("closed");
                    RemoteModelManager.downloaded=true;return Task.ready(null);
                }
                public Task<String> translate(String text){
                    if(closed)throw new IllegalStateException("closed");
                    Task<String> t=new Task<>();pending.add(t);return t;
                }
                public void close(){closed=true;}
            }
            public static void complete(){List<Task<String>> tasks=new ArrayList<>(pending);pending.clear();for(Task<String> t:tasks)t.succeed("Переведённый текст");}
        }""",
    "ru/kurostreet/counterzombiemobile/CzmAccount.java": """package ru.kurostreet.counterzombiemobile;
        final class CzmAccount { static int current=1;static int generation(){return current;} }""",
    "ru/kurostreet/counterzombiemobile/CzmDialog.java": """package ru.kurostreet.counterzombiemobile;
        import java.util.function.Consumer;
        class CzmDialog {
            static CzmDialog latest;final Button submit=new Button();Consumer<CzmDialog> dismiss;
            static class Button { Consumer<Object> click;void setOnClickListener(Consumer<Object> c){click=c;} }
            CzmDialog(android.app.Activity a,String title,String subtitle,String yes,String no,boolean ru,boolean destructive){latest=this;}
            void note(String note){}void show(){}
            void setOnDismissListener(Consumer<CzmDialog> listener){dismiss=listener;}
            void dismiss(){if(dismiss!=null)dismiss.accept(this);}
            void accept(){submit.click.accept(null);}
        }""",
}


class TranslationClientTests(unittest.TestCase):
    def test_repeated_translations_idle_close_cancellation_and_failure(self):
        json_jar = os.environ.get("CZM_JSON_JAR", "/missing")
        if not shutil.which("javac") or not Path(json_jar).is_file():
            self.skipTest("requires javac and the JSON test jar")
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            sources = []
            for relative, source in STUBS.items():
                path = temp / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
                sources.append(str(path))
            subprocess.run(["javac", "--release", "11", "-encoding", "UTF-8",
                            "-cp", json_jar, "-d", folder, *sources,
                            str(JAVA / "CzmTranslator.java"),
                            str(ROOT / "tests/TranslationClientTest.java")], check=True)
            for scenario in ("repeat", "failure"):
                result = subprocess.run(["java", "-cp", folder + os.pathsep + json_jar,
                                         "ru.kurostreet.counterzombiemobile.TranslationClientTest", scenario],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("TRANSLATION_CLIENT_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
