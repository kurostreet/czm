"""Run real layout export/Intent/file/provider methods with small Android boundary stubs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/app/src/main/java/ru/kurostreet/counterzombiemobile"


class LayoutFileFlowTests(unittest.TestCase):
    def test_share_provider_is_private_and_uses_each_application_id(self):
        android = "{http://schemas.android.com/apk/res/android}"
        manifest = ET.parse(ROOT / "android/app/src/main/AndroidManifest.xml").getroot()
        provider = next(p for p in manifest.findall("application/provider")
                        if p.get(android + "name") == ".CzmLayoutProvider")
        self.assertEqual(provider.get(android + "authorities"), "${applicationId}.layouts")
        self.assertEqual(provider.get(android + "exported"), "false")
        self.assertEqual(provider.get(android + "grantUriPermissions"), "true")

    def test_export_share_document_save_and_readonly_provider(self):
        jar = os.environ.get("CZM_JSON_JAR", "/missing")
        java, javac = shutil.which("java"), shutil.which("javac")
        if not java or not Path(jar).is_file():
            self.skipTest("Java runtime and JSON jar required")
        activity = (JAVA / "CzmLayoutActivity.java").read_text()
        provider = (JAVA / "CzmLayoutProvider.java").read_text()
        methods = "\n".join(function(activity, name) for name in (
            "private File exportFile(", "private boolean prepareExport(",
            "private void share(", "private void save(", "private void saveTo("))
        provider_methods = "\n".join(function(provider, name) for name in (
            "private File file(", "public String getType(", "public ParcelFileDescriptor openFile(",
            "public Cursor query("))
        source = STUB + "\nclass LayoutActivity extends Activity {\n" + r'''
boolean ru=false;int scheme=1;static final int SAVE=6;
LayoutActivity(File cache,String app){super(cache,app);}
void send(CzmDialog d){share(d);}void document(CzmDialog d){save(d);}
void write(Uri uri){saveTo(uri);}File shared(){return exportFile();}
''' + methods + "\n}\nclass LayoutProvider {\nActivity context;LayoutProvider(Activity a){context=a;}Activity getContext(){return context;}\n" + provider_methods + "\n}\n" + SCENARIO
        with tempfile.TemporaryDirectory(prefix="czm-layout-file-flow-") as temporary:
            path = Path(temporary)
            harness = path / "LayoutFileFlowTest.java"
            harness.write_text(source)
            compiler = [javac] if javac else [java, "com.sun.tools.javac.Main"]
            language = ["--release", "11"] if javac else ["-source", "11", "-target", "11"]
            compiled = subprocess.run(compiler + language + ["-encoding", "UTF-8", "-cp", jar, "-d", temporary,
                                      str(JAVA / "SettingsSchema.java"), str(JAVA / "SettingsData.java"), str(harness)],
                                      capture_output=True, text=True)
            if compiled.returncode and "ClassNotFoundException: com.sun.tools.javac.Main" in compiled.stderr:
                self.skipTest("Java compiler unavailable")
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([java, "-Dczm.test.dir=" + temporary, "-cp", temporary + os.pathsep + jar,
                                     "ru.kurostreet.counterzombiemobile.LayoutFileFlowTest"],
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("LAYOUT_FILE_FLOW_OK", result.stdout)


STUB = r'''
package ru.kurostreet.counterzombiemobile;
import java.io.*;import java.nio.file.*;import java.nio.charset.StandardCharsets;import java.util.*;import org.json.*;
class CzmNet {static String gameDir(){return System.getProperty("czm.test.dir");}}
class Uri {final String value;Uri(String s){value=s;}static Uri parse(String s){return new Uri(s);}
String getPath(){return java.net.URI.create(value).getPath();}public String toString(){return value;}}
class ClipData {final Uri uri;ClipData(Uri u){uri=u;}static ClipData newRawUri(String label,Uri u){return new ClipData(u);}}
class Intent {
static final String ACTION_SEND="android.intent.action.SEND",ACTION_CREATE_DOCUMENT="android.intent.action.CREATE_DOCUMENT";
static final String CATEGORY_OPENABLE="android.intent.category.OPENABLE",EXTRA_STREAM="android.intent.extra.STREAM",EXTRA_TITLE="android.intent.extra.TITLE";
static final int FLAG_GRANT_READ_URI_PERMISSION=1;
final String action;String type;int flags;ClipData clip;Intent target;Map<String,Object> extra=new HashMap<>();Set<String> categories=new HashSet<>();
Intent(String a){action=a;}Intent setType(String s){type=s;return this;}Intent putExtra(String k,Object v){extra.put(k,v);return this;}
Intent addFlags(int f){flags|=f;return this;}Intent addCategory(String s){categories.add(s);return this;}
void setClipData(ClipData c){clip=c;}static Intent createChooser(Intent target,String title){Intent i=new Intent("chooser");i.target=target;return i;}}
class ActivityNotFoundException extends RuntimeException {}
class Resolver {File destination;boolean nullStream;OutputStream openOutputStream(Uri uri)throws IOException{return nullStream?null:new FileOutputStream(destination);}}
class Activity {
final File cache;final String app;final Resolver resolver=new Resolver();Intent started;int request,starts;boolean failStart;String toast="";
Activity(File c,String a){cache=c;app=a;}File getCacheDir(){return cache;}String getPackageName(){return app;}Resolver getContentResolver(){return resolver;}
void startActivity(Intent i){if(failStart)throw new ActivityNotFoundException();started=i;starts++;}
void startActivityForResult(Intent i,int r){startActivity(i);request=r;}}
class CzmDialog {String error="";boolean dismissed;void fail(String s){error=s;}void dismiss(){dismissed=true;}}
class Toast {static final int LENGTH_SHORT=0,LENGTH_LONG=1;static Toast makeText(Activity a,String s,int length){a.toast=s;return new Toast();}void show(){}}
interface Cursor {}
class MatrixCursor implements Cursor {final String[] columns;Object[] row;MatrixCursor(String[] c){columns=c;}void addRow(Object[] r){row=r;}}
class OpenableColumns {static final String DISPLAY_NAME="_display_name",SIZE="_size";}
class ParcelFileDescriptor {static final int MODE_READ_ONLY=1;final File file;ParcelFileDescriptor(File f){file=f;}
static ParcelFileDescriptor open(File f,int mode)throws FileNotFoundException{if(mode!=MODE_READ_ONLY||!f.isFile())throw new FileNotFoundException();return new ParcelFileDescriptor(f);}}
'''

SCENARIO = r'''
public class LayoutFileFlowTest {
static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
public static void main(String[] args)throws Exception {
Path root=Path.of(CzmNet.gameDir());Files.createDirectories(root.resolve("touch_profiles"));
String config="czm_touch_scheme \"1\"\nczm_hud_style \"2\"\npassword \"private\"\n";
Files.writeString(root.resolve("config.cfg"),config);
String good="touch_addbutton \"prop\" \"gfx/czm/touch/props.png\" \"czm_props\" 0.5 0.65 0.56 0.78 255 255 255 200 1 1\n"
 +"touch_addbutton \"laser\" \"gfx/czm/touch/lasermine.png\" \"czm_lasermine\" 0.57 0.65 0.63 0.78 255 255 255 200 0 1\n";
Path profile=root.resolve("touch_profiles/czm_scheme1.cfg");Files.writeString(profile,good);
for(String app:new String[]{"ru.kurostreet.counterzombiemobile.test","dev.gaming.czm"}){
 LayoutActivity a=new LayoutActivity(root.resolve(app).toFile(),app);CzmDialog dialog=new CzmDialog();a.send(dialog);
 check(dialog.error.isEmpty()&&a.started!=null&&a.started.target!=null,"share chooser");Intent send=a.started.target;
 check(send.action.equals(Intent.ACTION_SEND)&&send.type.equals("application/json"),"share MIME");
 Uri uri=(Uri)send.extra.get(Intent.EXTRA_STREAM);
 check(uri.toString().equals("content://"+app+".layouts/CZM-layout.json"),"provider authority");
 check((send.flags&Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0&&send.clip.uri==uri,"read grant and ClipData");
 JSONObject shared=new JSONObject(Files.readString(a.shared().toPath()));SettingsData.validate(shared);
 check(shared.getJSONObject("layouts").getJSONArray("1").length()==2&&!shared.toString().contains("private"),"share layout only");
 LayoutProvider provider=new LayoutProvider(a);check(provider.getType(uri).equals("application/json"),"provider MIME");
 check(Files.readString(provider.openFile(uri,"r").file.toPath()).equals(Files.readString(a.shared().toPath())),"provider bytes");
 MatrixCursor metadata=(MatrixCursor)provider.query(uri,null,null,null,null);
 check(metadata.row[0].equals("CZM-layout.json")&&((Long)metadata.row[1])>0,"provider metadata");
 for(String bad:new String[]{"/../config.cfg","/config.cfg","/CZM-layout.json/other"}){
  try{provider.openFile(Uri.parse("content://"+app+".layouts"+bad),"r");throw new AssertionError("provider path");}catch(FileNotFoundException expected){}
 }
 try{provider.openFile(uri,"w");throw new AssertionError("provider write");}catch(FileNotFoundException expected){}
 dialog=new CzmDialog();a.document(dialog);
 check(dialog.error.isEmpty()&&dialog.dismissed&&a.request==6,"save picker launch");
 check(a.started.action.equals(Intent.ACTION_CREATE_DOCUMENT)&&a.started.type.equals("application/json")
   &&a.started.categories.contains(Intent.CATEGORY_OPENABLE)&&a.started.extra.get(Intent.EXTRA_TITLE).equals("CZM-layout.json"),"save intent");
 a.resolver.destination=root.resolve(app+"-saved.json").toFile();a.write(Uri.parse("content://documents/chosen"));
 check(new JSONObject(Files.readString(a.resolver.destination.toPath())).similar(shared)&&a.toast.equals("Layout saved."),"saved JSON and success");
 a.resolver.nullStream=true;a.write(Uri.parse("content://documents/denied"));
 check(a.toast.equals("Could not save the layout file."),"failed output stream");
 a.failStart=true;dialog=new CzmDialog();a.send(dialog);check(!dialog.error.isEmpty(),"unavailable share target");
 a.failStart=false;int previous=a.starts;
 Files.writeString(profile,good.replace("czm_props","czm_props;quit"));
 dialog=new CzmDialog();a.send(dialog);check(!dialog.error.isEmpty()&&a.starts==previous,"unsafe share blocked before chooser");
 dialog=new CzmDialog();a.document(dialog);check(!dialog.error.isEmpty()&&a.starts==previous,"unsafe save blocked before picker");
 Files.writeString(profile,good);
 check(Files.readString(root.resolve("config.cfg")).equals(config),"current settings preserved");
}
System.out.println("LAYOUT_FILE_FLOW_OK");}}
'''


if __name__ == "__main__":
    unittest.main()
