package ru.kurostreet.counterzombiemobile;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class ServerAuthDataTest {
    interface Check { void run() throws Exception; }
    static void expect(boolean ok) { if (!ok) throw new AssertionError(); }
    static void rejects(Check check) throws Exception {
        try { check.run(); } catch (Exception expected) { return; }
        throw new AssertionError("invalid data accepted");
    }
    public static void main(String[] args) throws Exception {
        expect(ServerAuthData.address("104.234.65.245:27300").equals("104.234.65.245:27300"));
        expect(ServerAuthData.address("127.0.0.1").equals("127.0.0.1:27015"));
        expect(ServerAuthData.address("[2001:db8::1]:27015").equals(ServerAuthData.address("[2001:db8:0:0:0:0:0:1]:27015")));
        for (String bad : new String[] {"example.com:27015", "localhost", "1.2.3.256:1", "1.2.3.4:0", "1.2.3.4:65536", "1.2.3.4:1;quit", "[fe80::1%wlan0]:27015"})
            rejects(() -> ServerAuthData.address(bad));
        expect(ServerAuthData.key("_pw") && ServerAuthData.key("_admin_pass"));
        for (String bad : new String[] {"name", "*sid", "_pw x", "_pw;quit", "_pw\\test", "_"}) expect(!ServerAuthData.key(bad));
        expect(ServerAuthData.password("hello 123%^^"));
        for (String bad : new String[] {"", "hello\nquit", "abc;quit", "abc\\key", "abc\"", "x".repeat(64), "я".repeat(32)}) expect(!ServerAuthData.password(bad));

        String base = "\\name\\Kuro\\model\\gign\\_pw\\stale-password\\rate\\100000";
        Set<String> managed = new HashSet<>(Arrays.asList("_pw", "_old"));
        Map<String, String[]> servers = new HashMap<>();
        servers.put("104.234.65.245:27300", new String[] {"_pw", "alpha-secret"});
        servers.put("104.234.65.245:27301", new String[] {"_pw", "beta-secret"});
        // Connect, reconnect, other port, other IP, missing credential, and a later return.
        for (String destination : new String[] {"104.234.65.245:27300", "104.234.65.245:27300", "104.234.65.245:27301", "104.234.65.246:27300", "127.0.0.1:27015", "104.234.65.245:27300"}) {
            String[] pair = servers.getOrDefault(ServerAuthData.address(destination), new String[] {"", ""});
            String wire = ServerAuthData.packet(base, managed, pair[0], pair[1], 256);
            expect(!wire.contains("stale-password"));
            expect(wire.contains("\\name\\Kuro") && wire.contains("\\model\\gign"));
            expect(wire.contains("alpha-secret") == pair[1].equals("alpha-secret"));
            expect(wire.contains("beta-secret") == pair[1].equals("beta-secret"));
            expect(base.contains("stale-password") && !base.contains("alpha-secret")); // config/global input immutable
        }
        String wire = ServerAuthData.packet(base, managed, "_pw", "alpha-secret", 50);
        expect(!wire.contains("secret") && wire.getBytes(StandardCharsets.UTF_8).length < 50);
        // Renaming/deleting a setting removes every managed field from old global data.
        expect(!ServerAuthData.packet(base + "\\_old\\old-secret", managed, "", "", 256).contains("secret"));

        // A real CZM connect packet is nearly full before Admin/VIP adds its field. The
        // previous implementation silently omitted the password in exactly this case.
        for (int limit : new int[] {256, 512}) for (String nickname : new String[] {"Kuro", "Игрок"}) {
            String publicInfo = "\\name\\" + nickname + "\\model\\gign\\rate\\100000\\cl_updaterate\\100"
                + "\\cl_lw\\1\\cl_lc\\1\\czm_tag\\public-binding\\lang\\ru"
                + "\\cscl_ver\\1.35-2dbcbc6\\_ah\\0\\_vgui_menus\\1\\cl_dlmax\\512"
                + "\\topcolor\\30\\bottomcolor\\6\\_cl_autowepswitch\\1\\_czm\\";
            String ticket = "T".repeat(limit - 1 - publicInfo.getBytes(StandardCharsets.UTF_8).length);
            String dense = publicInfo + ticket;
            expect(dense.getBytes(StandardCharsets.UTF_8).length == limit - 1);
            String password = "p".repeat(24);
            String packed = ServerAuthData.packet(dense, managed, "_pw", password, limit);
            expect(packed.endsWith("\\_pw\\" + password));
            expect(packed.getBytes(StandardCharsets.UTF_8).length < limit);
            for (String required : new String[] {"\\name\\" + nickname, "\\model\\gign", "\\rate\\100000",
                    "\\cl_updaterate\\100", "\\cl_lw\\1", "\\cl_lc\\1", "\\czm_tag\\public-binding", "\\lang\\ru", "\\_czm\\" + ticket,
                    "\\_vgui_menus\\1", "\\cl_dlmax\\512", "\\_cl_autowepswitch\\1"})
                expect(packed.contains(required));
            expect(dense.contains("\\cscl_ver\\1.35-2dbcbc6") && !dense.contains("\\_pw\\"));
            expect(!ServerAuthData.packet(dense, managed, "", "", limit).contains(password));
        }
        // The selected field cannot keep a stale value, even before it enters the managed set.
        String replaced = ServerAuthData.packet(base, new HashSet<>(), "_pw", "new-password", 256);
        expect(!replaced.contains("stale-password") && replaced.endsWith("\\_pw\\new-password"));
        // If protected data alone uses the budget, fail without dropping or truncating it.
        String protectedInfo = "\\name\\Kuro\\model\\gign\\rate\\100000\\_czm\\" + "T".repeat(205);
        String unchanged = ServerAuthData.packet(protectedInfo, managed, "_pw", "p".repeat(24), 256);
        expect(unchanged.equals(protectedInfo) && !unchanged.contains("\\_pw\\"));

        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA"); generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();
        String address = "104.234.65.245:27300";
        byte[][] encrypted = ServerAuthData.seal(pair.getPublic(), address, "_pw", "alpha-secret");
        expect(Arrays.equals(ServerAuthData.open(pair.getPrivate(), address, encrypted), new String[] {"_pw", "alpha-secret"}));
        rejects(() -> ServerAuthData.open(pair.getPrivate(), "104.234.65.245:27301", encrypted));
        rejects(() -> ServerAuthData.open(generator.generateKeyPair().getPrivate(), address, encrypted));
        encrypted[2][0] ^= 1;
        rejects(() -> ServerAuthData.open(pair.getPrivate(), address, encrypted));
        System.out.println("Server auth: address scope, packet isolation, validation, authenticated encryption and tampering OK");
    }
}
