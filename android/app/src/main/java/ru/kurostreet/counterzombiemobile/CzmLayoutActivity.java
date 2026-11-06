/* Share/import a data-only layout with preview and undo. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;
import android.app.Activity;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.widget.Toast;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

public final class CzmLayoutActivity extends Activity {
    static final String EXTRA_SCHEME = "scheme";
    private static final int IMPORT = 5, SAVE = 6;
    private static String pending="";
    private boolean ru;
    private int scheme;
    private CzmDialog menuDialog;
    static synchronized byte[] event(){if(pending.isEmpty())return null;byte[] b=pending.getBytes(StandardCharsets.UTF_8);pending="";return b;}
    private static synchronized void stage(JSONObject data)throws Exception{pending=SettingsData.engineEvent(data).toString();}
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        ru = java.util.Locale.getDefault().getLanguage().equals("ru");
        scheme = Math.max(1, Math.min(3, getIntent().getIntExtra(EXTRA_SCHEME, 1)));
        menu();
    }

    private File exportFile() {
        return new File(getCacheDir(), "layouts/CZM-layout.json");
    }

    private boolean prepareExport(CzmDialog dialog) {
        JSONObject layout;
        try {
            layout = SettingsData.captureLayout(scheme);
        } catch (FileNotFoundException e) {
            dialog.fail(ru ? "Сохранённый файл раскладки недоступен." : "The saved layout file is unavailable.");
            return false;
        } catch (Exception e) {
            if ("action".equals(e.getMessage())) {
                dialog.fail(ru ? "В раскладке есть команда, которую нельзя передать. Выбери действие из каталога."
                    : "This layout has an action that cannot be shared. Choose a supported action.");
            } else {
                dialog.fail(ru ? "Не удалось прочитать сохранённую раскладку." : "Could not read the saved layout.");
            }
            return false;
        }

        File target = exportFile();
        try {
            File folder = target.getParentFile();
            if (!folder.isDirectory() && !folder.mkdirs()) throw new IOException("cache");
            File draft = File.createTempFile("layout", ".json", folder);
            try {
                try (OutputStream stream = new FileOutputStream(draft)) {
                    stream.write(layout.toString().getBytes(StandardCharsets.UTF_8));
                }
                if (!draft.renameTo(target)) throw new IOException("rename");
            } finally {
                draft.delete();
            }
        } catch (IOException | SecurityException e) {
            dialog.fail(ru ? "Не удалось создать файл раскладки." : "Could not create the layout file.");
            return false;
        }
        return true;
    }

    private void share(CzmDialog dialog) {
        if (!prepareExport(dialog)) return;
        Uri uri = Uri.parse("content://" + getPackageName() + ".layouts/CZM-layout.json");
        Intent share = new Intent(Intent.ACTION_SEND).setType("application/json")
            .putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        share.setClipData(ClipData.newRawUri("CZM layout", uri));
        try {
            startActivity(Intent.createChooser(share, ru ? "Поделиться раскладкой" : "Share layout"));
        } catch (ActivityNotFoundException | SecurityException e) {
            dialog.fail(ru ? "Не удалось открыть отправку файла." : "Could not open sharing.");
        }
    }

    private void save(CzmDialog dialog) {
        if (!prepareExport(dialog)) return;
        Intent create = new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json")
            .addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE, "CZM-layout.json");
        try {
            startActivityForResult(create, SAVE);
            dialog.dismiss();
        } catch (ActivityNotFoundException | SecurityException e) {
            dialog.fail(ru ? "Не удалось открыть выбор папки." : "Could not open the file picker.");
        }
    }

    private void saveTo(Uri destination) {
        try {
            byte[] bytes = SettingsData.read(exportFile()).getBytes(StandardCharsets.UTF_8);
            try (OutputStream out = getContentResolver().openOutputStream(destination)) {
                if (out == null) throw new IOException("destination");
                out.write(bytes);
            }
            Toast.makeText(this, ru ? "Раскладка сохранена." : "Layout saved.", Toast.LENGTH_SHORT).show();
        } catch (IOException | SecurityException e) {
            Toast.makeText(this, ru ? "Не удалось записать файл раскладки." : "Could not save the layout file.", Toast.LENGTH_LONG).show();
        }
    }

    private void menu(){
        CzmDialog d=new CzmDialog(this,ru?"Раскладки управления":"Control layouts",ru?"Поделиться · сохранить · импортировать":"Share · save · import",ru?"Закрыть":"Close",ru?"Назад":"Back",ru,false);
        menuDialog = d;
        d.link(ru ? "Поделиться моей раскладкой" : "Share my layout", v -> share(d));
        d.link(ru ? "Сохранить файл раскладки" : "Save layout file", v -> save(d));
        d.link(ru?"Импортировать файл раскладки":"Import a layout file",v->{try{startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE),IMPORT);d.dismiss();}catch(Exception e){d.fail(ru?"Не удалось открыть файлы":"Could not open files");}});
        if(getPreferences(0).contains("backup"))d.link(ru?"Отменить последний импорт":"Undo last import",v->{try{stage(new JSONObject(getPreferences(0).getString("backup","")));getPreferences(0).edit().remove("backup").commit();d.dismiss();finish();}catch(Exception e){d.fail(ru?"Копия недоступна":"Backup unavailable");}});
        d.submit.setOnClickListener(v->{d.dismiss();finish();});d.cancel.setOnClickListener(v->{d.dismiss();finish();});d.setOnCancelListener(v->finish());d.show();
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request, result, data);
        if (request != IMPORT && request != SAVE) return;
        if (menuDialog != null) menuDialog.dismiss();
        Uri document = result == RESULT_OK && data != null ? data.getData() : null;
        if (request == SAVE || document == null) {
            if (document != null) saveTo(document);
            menu();
            return;
        }
        JSONObject imported;
        JSONArray buttons = null;
        try (InputStream in = getContentResolver().openInputStream(document);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            if (in == null) throw new IOException("document");
            byte[] bytes = new byte[4096];
            int read;
            while ((read = in.read(bytes)) != -1) {
                out.write(bytes, 0, read);
                if (out.size() > 131072) throw new IOException("size");
            }
            imported = SettingsData.validate(new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8)));
            JSONObject layouts = imported.getJSONObject("layouts");
            for (int i = 1; i <= 3 && buttons == null; i++) buttons = layouts.optJSONArray(Integer.toString(i));
            if (buttons == null) throw new IOException("layout");
        } catch (Exception e) {
            Toast.makeText(this,ru?"Файл не является совместимой раскладкой CZM":"Not a compatible CZM layout file",Toast.LENGTH_LONG).show();
            menu();
            return;
        }
        try {
            JSONObject current = SettingsData.captureLayout(scheme);
            String active = Integer.toString(scheme);
            JSONObject cleanCvars = new JSONObject().put("czm_touch_scheme", active);
            boolean withHud = SettingsData.copyHud(imported.getJSONObject("cvars"), cleanCvars);
            if (!withHud) current.put("cvars", new JSONObject().put("czm_touch_scheme", active));
            JSONObject clean = new JSONObject().put("schema", 1).put("cvars", cleanCvars)
                .put("layouts", new JSONObject().put(active, buttons));
            preview(clean, buttons, current, withHud);
        } catch (Exception e) {
            Toast.makeText(this,ru?"Не удалось создать копию текущей раскладки.":"Could not back up the current layout.",Toast.LENGTH_LONG).show();
            menu();
        }
    }
    private void preview(JSONObject data,JSONArray buttons,JSONObject backup,boolean withHud){
        CzmDialog d=new CzmDialog(this,ru?"Применить раскладку?":"Apply this layout?",(ru?"Кнопок: ":"Buttons: ")+buttons.length()+(withHud?(ru?" · интерфейс матча":" · match HUD"):""),ru?"Применить":"Apply",ru?"Отмена":"Cancel",ru,false);
        View picture=new View(this){final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
            @Override protected void onDraw(Canvas c){c.drawColor(Color.rgb(24,32,42));for(int i=0;i<buttons.length();i++)try{JSONArray b=buttons.getJSONArray(i);if((b.getInt(11)&1)!=0)continue;float x=b.getDouble(3)>1?1:(float)b.getDouble(3),y=(float)b.getDouble(4),w=(float)(b.getDouble(5)-b.getDouble(3)),h=(float)(b.getDouble(6)-b.getDouble(4));p.setColor(Color.argb(Math.max(80,b.getInt(10)),b.getInt(7),b.getInt(8),b.getInt(9)));p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(2);c.drawOval(x*getWidth(),y*getHeight(),(x+w)*getWidth(),(y+h)*getHeight(),p);p.setStyle(Paint.Style.FILL);p.setTextSize(9*getResources().getDisplayMetrics().density);String text=b.getString(2);if(text.length()>14)text=text.substring(0,14);c.drawText(text,x*getWidth(),(y+h/2)*getHeight(),p);}catch(Exception ignored){}}
        };d.body.addView(picture,new android.widget.LinearLayout.LayoutParams(-1,CzmDialog.dp(this,140)));
        d.note(withHud?(ru?"Будут заменены текущая схема кнопок и места интерфейса. Предыдущие можно вернуть.":"The current button scheme and the HUD places will be replaced. You can undo this import.")
            :(ru?"Будет заменена только текущая схема кнопок. Предыдущую можно вернуть.":"Only the current button scheme will be replaced. You can undo this import."));
        d.submit.setOnClickListener(v->{try{if(!getPreferences(0).edit().putString("backup",SettingsData.canonical(backup)).commit())throw new IOException();stage(data);d.dismiss();finish();}catch(Exception e){d.fail(ru?"Не удалось сохранить копию":"Could not save a backup");}});
        d.cancel.setOnClickListener(v->{d.dismiss();finish();});d.setOnCancelListener(v->finish());d.show();
    }
}
