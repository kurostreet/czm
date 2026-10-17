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
    private static String pending="";
    private boolean ru;
    static synchronized byte[] event(){if(pending.isEmpty())return null;byte[] b=pending.getBytes(StandardCharsets.UTF_8);pending="";return b;}
    private static synchronized void stage(JSONObject data)throws Exception{pending=SettingsData.engineEvent(data).toString();}
    // The match HUD is edited together with the buttons, so a layout carries its places too.
    private static boolean hud(JSONObject from,JSONObject to)throws Exception{boolean any=false;for(String k:SettingsSchema.KEYS)if(k.startsWith("czm_hud_")&&from.has(k)){to.put(k,from.getString(k));any=true;}return any;}
    @Override public void onCreate(Bundle state){super.onCreate(state);ru=java.util.Locale.getDefault().getLanguage().equals("ru");menu();}
    private void menu(){
        CzmDialog d=new CzmDialog(this,ru?"Раскладки управления":"Control layouts",ru?"Поделиться · импорт · отмена":"Share · import · undo",ru?"Закрыть":"Close",ru?"Назад":"Back",ru,false);
        d.link(ru?"Поделиться моей раскладкой":"Share my layout",v->{try{
            JSONObject source=SettingsData.capture();JSONObject cv=source.getJSONObject("cvars");String scheme=cv.optString("czm_touch_scheme","1");int n=(int)Double.parseDouble(scheme);scheme=""+Math.max(1,Math.min(3,n));
            JSONArray buttons=source.getJSONObject("layouts").getJSONArray(scheme);
            JSONObject shared=new JSONObject().put("czm_touch_scheme",scheme);hud(cv,shared);
            JSONObject out=new JSONObject().put("schema",1).put("cvars",shared).put("layouts",new JSONObject().put(scheme,buttons));
            File folder=new File(getCacheDir(),"layouts");folder.mkdirs();File target=new File(folder,"CZM-layout.json");try(OutputStream stream=new FileOutputStream(target)){stream.write(out.toString().getBytes(StandardCharsets.UTF_8));}
            Uri uri=Uri.parse("content://"+getPackageName()+".layouts/CZM-layout.json");Intent share=new Intent(Intent.ACTION_SEND).setType("application/json").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);share.setClipData(ClipData.newRawUri("CZM layout",uri));startActivity(Intent.createChooser(share,ru?"Поделиться раскладкой":"Share layout"));
        }catch(Exception e){d.fail(ru?"Сначала сохрани раскладку в редакторе кнопок.":"Save the layout in the button editor first.");}});
        d.link(ru?"Импортировать файл раскладки":"Import a layout file",v->{try{startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE),5);d.dismiss();}catch(Exception e){d.fail(ru?"Не удалось открыть файлы":"Could not open files");}});
        if(getPreferences(0).contains("backup"))d.link(ru?"Отменить последний импорт":"Undo last import",v->{try{stage(new JSONObject(getPreferences(0).getString("backup","")));getPreferences(0).edit().remove("backup").commit();d.dismiss();finish();}catch(Exception e){d.fail(ru?"Копия недоступна":"Backup unavailable");}});
        d.submit.setOnClickListener(v->{d.dismiss();finish();});d.cancel.setOnClickListener(v->{d.dismiss();finish();});d.setOnCancelListener(v->finish());d.show();
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);if(request!=5||result!=RESULT_OK||data==null||data.getData()==null){menu();return;}
        try(InputStream in=getContentResolver().openInputStream(data.getData());ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>131072)throw new IOException();}
            JSONObject imported=SettingsData.validate(new JSONObject(new String(out.toByteArray(),StandardCharsets.UTF_8)));
            JSONObject layout=imported.getJSONObject("layouts");JSONArray buttons=null;for(int i=1;i<=3;i++)if(layout.has(""+i)){buttons=layout.getJSONArray(""+i);break;}if(buttons==null)throw new IOException();
            JSONObject current=SettingsData.capture();String active=""+Math.max(1,Math.min(3,(int)Double.parseDouble(current.getJSONObject("cvars").optString("czm_touch_scheme","1"))));
            JSONObject cleanCvars=new JSONObject().put("czm_touch_scheme",active),previousCvars=new JSONObject().put("czm_touch_scheme",active);
            boolean withHud=hud(imported.getJSONObject("cvars"),cleanCvars);if(withHud)hud(current.getJSONObject("cvars"),previousCvars);
            JSONObject clean=new JSONObject().put("schema",1).put("cvars",cleanCvars).put("layouts",new JSONObject().put(active,buttons));
            JSONObject previous=new JSONObject().put("schema",1).put("cvars",previousCvars).put("layouts",new JSONObject().put(active,current.getJSONObject("layouts").getJSONArray(active)));
            preview(clean,buttons,previous,withHud);
        }catch(Exception e){Toast.makeText(this,ru?"Файл не является совместимой раскладкой CZM":"Not a compatible CZM layout file",Toast.LENGTH_LONG).show();menu();}
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
