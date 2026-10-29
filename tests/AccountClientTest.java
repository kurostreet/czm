package ru.kurostreet.counterzombiemobile;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Field;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.json.JSONObject;

/** Real client request routing with an in-memory HTTP transport; no account or mail is created. */
public class AccountClientTest {
    static final List<Wire> wires = new ArrayList<>();
    static boolean switchDuringResponse;
    static class Wire extends HttpURLConnection {
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        Wire(URL u) { super(u); wires.add(this); }
        public void connect() {}
        public void disconnect() {}
        public boolean usingProxy() { return false; }
        public OutputStream getOutputStream() { return body; }
        public int getResponseCode() {
            if (switchDuringResponse) {
                switchDuringResponse = false;
                try { set("generation", 2); } catch(Exception e) { throw new RuntimeException(e); }
            }
            return 200;
        }
        public InputStream getInputStream() {
            return new ByteArrayInputStream((url.getPath().endsWith("/auth/me")
                ? "{\"id\":7,\"nick\":\"Saved\",\"avatar\":\"3\",\"login\":\"Kuro\"}" : "{\"id\":7}").getBytes(StandardCharsets.UTF_8));
        }
    }
    static Field field(Class<?> type, String name) throws Exception { Field f = type.getDeclaredField(name); f.setAccessible(true); return f; }
    static void set(String name, Object value) throws Exception { field(CzmAccount.class, name).set(null, value); }
    static void check(boolean ok, String why) { if (!ok) throw new AssertionError(why); }
    @SuppressWarnings("unchecked") public static void main(String[] args) throws Exception {
        URL.setURLStreamHandlerFactory(protocol -> "https".equals(protocol) ? new URLStreamHandler() {
            protected URLConnection openConnection(URL u) { return new Wire(u); }
        } : null);
        for (String valid : new String[]{"https://counter-zombie.ru/api/v1/hello", "https://kontrafps.ru:443/api/v1/chat/global"})
            check(CzmAccount.serviceUrl(valid), "service origin");
        for (String bad : new String[]{"http://counter-zombie.ru", "https://counter-zombie.ru.evil.com", "https://counter-zombie.ru:444/", "https://evil@counter-zombie.ru/", "https://example.com/"})
            check(!CzmAccount.serviceUrl(bad), "reject credential origin " + bad);
        String session = "czms1_" + "a".repeat(43);
        set("loaded", true); set("token", session); set("synced", false); set("generation", 1); set("event", "");
        check(CzmAccount.lobbyVoiceKey("https://counter-zombie.ru/api/v1/lobbies/test/voice").equals(session), "voice uses the account session without JNI exposure");
        check(CzmAccount.lobbyVoiceKey("https://example.com/voice").isEmpty(), "voice credential is origin restricted");
        byte[] hello = "{\"key\":\"legacy-secret\",\"nick\":\"StaleLocal\",\"avatar\":\"1\"}".getBytes(StandardCharsets.UTF_8);
        String url = "https://counter-zombie.ru/api/v1/hello";
        check(CzmAccount.call(1, "POST", url, "", hello, "application/json").startsWith("409\n"), "restore before hello");
        check(wires.size() == 1 && wires.get(0).getURL().getPath().endsWith("/auth/me"), "only profile read before restore");
        check(CzmAccount.call(1, "POST", url, "", hello, "application/json").startsWith("409\n"), "wait for game-thread handoff");
        String event = new String(CzmAccount.event(), StandardCharsets.UTF_8);
        check(new JSONObject(event).getJSONObject("profile").getInt("id") == 7 && !event.contains(session), "public event only");
        check(new JSONObject(event).getJSONObject("profile").getString("login").equals("Kuro"), "native account state without a session token");
        check(CzmAccount.call(1, "POST", url, "", hello, "application/json").startsWith("200\n"), "authorized hello");
        Wire wire = wires.get(wires.size()-1);
        check(new JSONObject(wire.body.toString("UTF-8")).getString("key").equals(session), "effective hello identity");
        check(wire.getRequestProperty("X-CZM-Key").equals(session) && !wire.getInstanceFollowRedirects(), "header and no redirects");
        int before = wires.size();
        check(CzmAccount.call(0, "POST", url, "", hello, "application/json").startsWith("409\n") && wires.size() == before, "cancel queued previous account");
        switchDuringResponse = true;
        check(CzmAccount.call(1, "POST", url, "", hello, "application/json").startsWith("409\n"), "cancel previous account completion");
        Map<Integer,String> results = (Map<Integer,String>) field(CzmNet.class,"RESULTS").get(null);
        Map<Integer,Integer> generations = (Map<Integer,Integer>) field(CzmNet.class,"GENERATIONS").get(null);
        results.put(50,"200\nold-profile"); generations.put(50,1);
        check(new String(CzmNet.poll(50),StandardCharsets.UTF_8).equals("409\n"), "discard already completed stale response");
        check(!results.containsKey(50) && !generations.containsKey(50), "drain completion maps");
        JSONObject hidden=new JSONObject("{\"hidden\":[{\"server\":\"203.0.113.5:27015\",\"enabled\":1}]}");
        ServerBlocks.acceptReport(hidden,2);
        check(ServerBlocks.hidden("203.0.113.5:27015"),"report hides server for its account");
        ServerBlocks.acceptReport(new JSONObject("{\"hidden\":[{\"server\":\"203.0.113.5:27015\",\"enabled\":0}]}"),2);
        check(!ServerBlocks.hidden("203.0.113.5:27015"),"personal off restores visibility");
        field(ServerPolicy.class,"blocked").set(ServerPolicy.INSTANCE,java.util.Collections.singleton(ServerPolicy.endpoint("203.0.113.5:27015")));
        check(CzmNet.serverPolicyBlocked("203.0.113.5:27015"),"personal off cannot cancel moderation");
        field(ServerPolicy.class,"blocked").set(ServerPolicy.INSTANCE,java.util.Collections.emptySet());
        ServerBlocks.acceptReport(hidden,2);set("generation",3);
        check(!ServerBlocks.hidden("203.0.113.5:27015"),"another account never inherits personal blocks");
        ServerBlocks.acceptReport(hidden,2);
        check(!ServerBlocks.hidden("203.0.113.5:27015"),"late old-account receipt cannot hide a new account's server");
        System.out.println("ACCOUNT_CLIENT_ROUTING_OK");
    }
}
