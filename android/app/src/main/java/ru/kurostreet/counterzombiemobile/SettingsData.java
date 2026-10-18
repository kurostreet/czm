/* Versioned settings and data-only touch layouts. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.*;
import org.json.*;

final class SettingsData {
    static final Set<String> KEYS=new HashSet<>(Arrays.asList(SettingsSchema.KEYS));
    static final Set<String> COMMANDS=new HashSet<>(Arrays.asList(SettingsSchema.COMMANDS));
    private static final Pattern TOKEN=Pattern.compile("\"((?:\\\\.|[^\"\\\\])*)\"|([^\\s]+)");
    static List<String> tokens(String line){
        ArrayList<String> out=new ArrayList<>();Matcher m=TOKEN.matcher(line);
        while(m.find())out.add(m.group(1)==null?m.group(2):m.group(1).replace("\\\"","\"").replace("\\\\","\\"));return out;
    }
    static boolean validValue(String key,String v){
        if(v.length()>128 || v.matches("(?s).*[\\x00-\\x1f\";\\\\].*"))return false;
        if(key.equals("czm_lang"))return Arrays.asList("","ru","en").contains(v);
        if(key.equals("cl_crosshair_size"))return Arrays.asList("auto","small","medium","large","0","1","2","3").contains(v);
        if(key.equals("cl_crosshair_color")) {if(!v.matches("\\d{1,3} \\d{1,3} \\d{1,3}"))return false;for(String n:v.split(" "))if(Integer.parseInt(n)>255)return false;return true;}
        try{double n=Double.parseDouble(v);return (!Double.isNaN(n)&&!Double.isInfinite(n))&&Math.abs(n)<=1000000;}catch(Exception e){return false;}
    }
    static JSONObject validate(JSONObject p) throws Exception {
        if(p.optInt("schema")!=1 || p.toString().getBytes(StandardCharsets.UTF_8).length>131072)throw new IOException("format");
        JSONObject cv=p.getJSONObject("cvars"),layouts=p.getJSONObject("layouts");
        if(cv.length()==0)throw new IOException("empty");
        for(Iterator<String> i=cv.keys();i.hasNext();) {String k=i.next();if(!KEYS.contains(k)||!(cv.get(k) instanceof String)||!validValue(k,cv.getString(k)))throw new IOException("setting");}
        for(Iterator<String> i=layouts.keys();i.hasNext();) {
            String k=i.next();if(!Arrays.asList("1","2","3").contains(k))throw new IOException("layout");JSONArray buttons=layouts.getJSONArray(k);
            if(buttons.length()<1||buttons.length()>80)throw new IOException("buttons");Set<String> seen=new HashSet<>();
            for(int n=0;n<buttons.length();n++){
                JSONArray b=buttons.getJSONArray(n);if(b.length()!=12)throw new IOException("button");String name=b.getString(0),tex=b.getString(1),cmd=b.getString(2);
                if(!name.matches("[A-Za-z0-9_+#.-]{1,64}")||!seen.add(name)||tex.length()>128||tex.contains("..")||tex.startsWith("/")||tex.matches("(?s).*[\\x00-\\x1f\";\\\\].*"))throw new IOException("name");
                if(!COMMANDS.contains(cmd)&&!cmd.matches("say(?:_team)? [^\";\\\\\\x00-\\x1f]{1,96}"))throw new IOException("action");
                for(int j=3;j<12;j++)if(!(b.get(j) instanceof Number)||(Double.isNaN(b.getDouble(j))||Double.isInfinite(b.getDouble(j))))throw new IOException("number");
                if(b.getDouble(3)<0||b.getDouble(4)<0||b.getDouble(5)>1||b.getDouble(6)>1||b.getDouble(3)>=b.getDouble(5)||b.getDouble(4)>=b.getDouble(6))throw new IOException("position");
                for(int j=7;j<12;j++)if(b.getDouble(j)!=b.getInt(j)||b.getInt(j)<0||b.getInt(j)>(j==11?65535:255))throw new IOException("colour");
            }
        }
        return p;
    }
    static String read(File file) throws IOException {
        if(file.length()>262144)throw new IOException("size");try(InputStream in=new FileInputStream(file);ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>262144)throw new IOException("size");}return new String(out.toByteArray(),StandardCharsets.UTF_8);}
    }
    static JSONObject capture() throws Exception {
        File root=new File(CzmNet.gameDir());JSONObject cvars=new JSONObject(),layouts=new JSONObject();
        for(String line:read(new File(root,"config.cfg")).split("\n")){List<String> t=tokens(line);if(t.size()==2&&KEYS.contains(t.get(0))&&validValue(t.get(0),t.get(1)))cvars.put(t.get(0),t.get(1));}
        for(int scheme=1;scheme<=3;scheme++){
            File cfg=new File(root,"touch_profiles/czm_scheme"+scheme+".cfg");if(!cfg.isFile())continue;JSONArray buttons=new JSONArray();
            for(String line:read(cfg).split("\n")){
                List<String> t=tokens(line);if(t.size()<13||!t.get(0).equals("touch_addbutton"))continue;
                JSONArray b=new JSONArray();for(int i=1;i<=3;i++)b.put(t.get(i));for(int i=4;i<=7;i++)b.put(Double.parseDouble(t.get(i)));for(int i=8;i<=12;i++)b.put(Integer.parseInt(t.get(i)));buttons.put(b);
            }
            if(buttons.length()>0)layouts.put(""+scheme,buttons);
        }
        return validate(new JSONObject().put("schema",1).put("cvars",cvars).put("layouts",layouts));
    }
    static JSONObject engineEvent(JSONObject p) throws Exception {
        validate(p);JSONObject files=new JSONObject(),all=p.getJSONObject("layouts");
        for(int i=1;i<=3;i++)if(all.has(""+i)){
            StringBuilder cfg=new StringBuilder("touch_removeall\n");JSONArray buttons=all.getJSONArray(""+i);
            for(int n=0;n<buttons.length();n++){
                JSONArray b=buttons.getJSONArray(n);cfg.append("touch_addbutton");
                for(int k=0;k<3;k++)cfg.append(" \"").append(b.getString(k)).append('"');
                for(int k=3;k<12;k++)cfg.append(' ').append(b.get(k));
                // round buttons stay round on another screen: the engine recalculates the height (aspect 1)
                String tex=b.getString(1);if(!tex.isEmpty()&&!tex.startsWith("#"))cfg.append(" 1");cfg.append('\n');
            }files.put(""+i,cfg.toString());
        }
        return new JSONObject().put("cvars",p.getJSONObject("cvars")).put("files",files);
    }
    static String canonical(JSONObject p) throws Exception {
        JSONObject cv=new JSONObject(),layouts=new JSONObject();JSONObject in=p.getJSONObject("cvars"),all=p.getJSONObject("layouts");
        for(String k:SettingsSchema.KEYS)if(in.has(k))cv.put(k,in.get(k));for(int i=1;i<=3;i++)if(all.has(""+i))layouts.put(""+i,all.get(""+i));
        return new JSONObject().put("schema",1).put("cvars",cv).put("layouts",layouts).toString();
    }
}
