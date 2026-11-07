package ru.kurostreet.counterzombiemobile;
import org.json.*;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

public final class SettingsDataTest {
    static void check(boolean b){if(!b)throw new AssertionError();}
    static JSONObject payload()throws Exception{
        return new JSONObject("{\"schema\":1,\"cvars\":{\"czm_hud_style\":\"2\",\"czm_touch_scheme\":\"1\"},\"layouts\":{\"1\":[[\"attack\",\"touch/fire\",\"+attack\",0.8,0.6,0.95,0.9,255,255,255,170,0]]}}");
    }

    static void testActiveLayoutExport() throws Exception {
        Path root = Path.of(CzmNet.gameDir());
        Path profiles = Files.createDirectory(root.resolve("touch_profiles"));
        String config = "czm_touch_scheme \"1\"\nczm_hud_style \"2\"\nsensitivity \"3\"\npassword \"secret\"\n";
        String active = "touch_addbutton \"team\" \"gfx/czm/touch/fire\" \"chooseteam\" -0.02 0.82 0.08 1.00007 255 255 255 170 0 1\n"
            + "touch_addbutton \"custom\" \"gfx/czm/touch/custom\" \"say /help\" 0.00005 0.2 0.2 0.3 255 255 255 170\n";
        String inactive = "touch_addbutton \"bad\" \"touch/fire\" \"exec stolen.cfg\" 0.1 0.2 0.2 0.3 255 255 255 170 0\n";
        Files.writeString(root.resolve("config.cfg"), config);
        Files.writeString(profiles.resolve("czm_scheme1.cfg"), inactive);
        Files.writeString(profiles.resolve("czm_scheme2.cfg"), active);

        JSONObject exported = SettingsData.captureLayout(2);
        JSONObject cvars = exported.getJSONObject("cvars");
        JSONObject layouts = exported.getJSONObject("layouts");
        check(cvars.length() == 2 && cvars.getString("czm_touch_scheme").equals("2"));
        check(cvars.getString("czm_hud_style").equals("2"));
        check(layouts.length() == 1 && layouts.getJSONArray("2").length() == 2);
        JSONArray button = layouts.getJSONArray("2").getJSONArray(0);
        check(button.getString(1).equals("gfx/czm/touch/fire") && button.getString(2).equals("chooseteam"));
        check(button.getDouble(3) == 0 && Math.abs(button.getDouble(5) - 0.1) < 1e-9);
        check(button.getDouble(6) == 1 && Math.abs(button.getDouble(4) - 0.81993) < 1e-9);
        check(layouts.getJSONArray("2").getJSONArray(1).getInt(11) == 0);

        JSONObject roundTrip = SettingsData.engineEvent(new JSONObject(exported.toString()));
        String restored = roundTrip.getJSONObject("files").getString("2");
        check(restored.contains("\"gfx/czm/touch/fire\" \"chooseteam\""));
        check(restored.contains("\"say /help\" 0.00005"));
        check(Files.readString(root.resolve("config.cfg")).equals(config));
        check(Files.readString(profiles.resolve("czm_scheme1.cfg")).equals(inactive));
        check(Files.readString(profiles.resolve("czm_scheme2.cfg")).equals(active));

        button.put(6, 1.00007);
        try {
            SettingsData.validate(exported);
            throw new AssertionError("Invalid imported coordinates were accepted");
        } catch (IOException expected) {
            check("position".equals(expected.getMessage()));
        }
    }

    public static void main(String[] args)throws Exception{
        JSONObject p=payload();SettingsData.validate(p);JSONObject event=SettingsData.engineEvent(p);String cfg=event.getJSONObject("files").getString("1");check(cfg.startsWith("touch_removeall\n")&&cfg.contains("\"+attack\"")&&!cfg.contains("password"));
        check(SettingsData.tokens("touch_addbutton \"attack\" \"touch/fire\" \"say hello world\" 0 0 1 1").get(3).equals("say hello world"));
        for(String cmd:new String[]{"exec stolen.cfg","+attack;quit","say ok\nquit","connect 1.1.1.1"}){p=payload();p.getJSONObject("layouts").getJSONArray("1").getJSONArray(0).put(2,cmd);try{SettingsData.validate(p);throw new AssertionError(cmd);}catch(java.io.IOException expected){}}
        p=payload();p.getJSONObject("cvars").put("password","secret");try{SettingsData.validate(p);throw new AssertionError();}catch(java.io.IOException expected){}
        p=payload();p.getJSONObject("layouts").getJSONArray("1").getJSONArray(0).put(1,"../config.cfg");try{SettingsData.validate(p);throw new AssertionError();}catch(java.io.IOException expected){}
        for(String bad:new String[]{"NaN","Infinity","1;quit","1\nquit"})check(!SettingsData.validValue("volume",bad));
        p=payload();String canonical=SettingsData.canonical(p);check(SettingsData.canonical(new JSONObject(canonical)).equals(canonical));
        JSONObject abilities=payload();JSONArray buttons=abilities.getJSONObject("layouts").getJSONArray("1");
        JSONArray original=buttons.getJSONArray(0);
        for(int i=1;i<80;i++){JSONArray b=new JSONArray(original.toString());b.put(0,"saved_"+i);buttons.put(b);}
        for(String command:new String[]{"czm_skill_g","czm_skill_r","+czm_skill_e"}){
            JSONArray b=new JSONArray(original.toString());b.put(0,"skill_"+buttons.length());b.put(2,command);buttons.put(b);
        }
        SettingsData.validate(abilities);
        String restored=SettingsData.engineEvent(abilities).getJSONObject("files").getString("1");
        check(restored.contains("\"czm_skill_g\"")&&restored.contains("\"czm_skill_r\"")&&restored.contains("\"+czm_skill_e\""));
        testActiveLayoutExport();
        System.out.println("SETTINGS_DATA_OK");
    }
}
