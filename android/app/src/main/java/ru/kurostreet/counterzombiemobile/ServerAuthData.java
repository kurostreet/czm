/* Server-specific credentials and wire userinfo. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

final class ServerAuthData {
    private ServerAuthData() {}

    /** Numeric IP only: no DNS lookup or hostname alias can widen a saved scope. */
    static String address(String text) throws Exception {
        if (text == null || text.length() > 100) throw new IllegalArgumentException();
        String host, port;
        if (text.startsWith("[")) {
            int end = text.indexOf(']');
            if (end < 2 || end + 2 >= text.length() || text.charAt(end + 1) != ':') throw new IllegalArgumentException();
            host = text.substring(1, end); port = text.substring(end + 2);
            if (!host.matches("[0-9a-fA-F:]+") || !host.contains(":")) throw new IllegalArgumentException();
        } else {
            int colon = text.indexOf(':');
            host = colon < 0 ? text : text.substring(0, colon);
            port = colon < 0 ? "27015" : text.substring(colon + 1);
            if (!host.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+")) throw new IllegalArgumentException();
            for (String part : host.split("\\."))
                if (part.length() > 3 || Integer.parseInt(part) > 255) throw new IllegalArgumentException();
        }
        if (!port.matches("[0-9]{1,5}")) throw new IllegalArgumentException();
        int number = Integer.parseInt(port);
        if (number < 1 || number > 65535) throw new IllegalArgumentException();
        String ip = InetAddress.getByName(host).getHostAddress();
        return (ip.contains(":") ? "[" + ip + "]" : ip) + ":" + number;
    }

    static boolean key(String text) {
        // Private userinfo fields; never override name, model, rate or star keys.
        return text != null && text.matches("_[A-Za-z0-9_]{1,30}");
    }

    static boolean password(String text) {
        if (text == null || text.isEmpty() || text.getBytes(StandardCharsets.UTF_8).length > 63) return false;
        for (int i = 0; i < text.length(); ++i) {
            char c = text.charAt(i);
            if (c < 32 || c == 127 || c == '\\' || c == '"' || c == ';' || Character.isSurrogate(c)) return false;
        }
        return true;
    }

    /** A packet copy only. The game's global userinfo/cvars never receive a password. */
    static String packet(String base, Set<String> managed, String parameter, String secret, int limit) {
        Map<String, String> info = new LinkedHashMap<>();
        boolean activeKey = key(parameter);
        String[] parts = base.split("\\\\", -1);
        for (int i = base.startsWith("\\") ? 1 : 0; i + 1 < parts.length; i += 2)
            if (!managed.contains(parts[i]) && !(activeKey && parts[i].equals(parameter)) && !parts[i].isEmpty())
                info.put(parts[i], parts[i + 1]);
        String clean = serialize(info);
        if (activeKey && password(secret)) {
            String field = "\\" + parameter + "\\" + secret;
            if (fits(clean + field, limit)) return clean + field;
            // A saved password takes priority over version/help/cosmetic hints. Remove only
            // known optional fields from this destination's packet, never identity, network rates,
            // account tickets, custom server fields, or the global userinfo/config.
            Map<String, String> compact = new LinkedHashMap<>(info);
            for (String optional : new String[] {"cscl_ver", "_ah", "_vgui_menus", "cl_dlmax", "topcolor", "bottomcolor"}) {
                if (compact.remove(optional) != null) {
                    String candidate = serialize(compact) + field;
                    if (fits(candidate, limit)) return candidate;
                }
            }
        }
        // Impossible even after compaction: retain the original public data and let the
        // editor report the failure. Never truncate a password, nickname, or account ticket.
        return clean;
    }

    private static boolean fits(String packet, int limit) {
        return packet.getBytes(StandardCharsets.UTF_8).length < limit; // reserve the native NUL byte
    }

    private static String serialize(Map<String, String> info) {
        StringBuilder wire = new StringBuilder();
        for (Map.Entry<String, String> item : info.entrySet())
            wire.append('\\').append(item.getKey()).append('\\').append(item.getValue());
        return wire.toString();
    }

    /** AES-GCM data bound to IP:port, with its random AES key wrapped by Android Keystore RSA. */
    static byte[][] seal(PublicKey wrappingKey, String address, String parameter, String password) throws Exception {
        if (!key(parameter) || !password(password)) throw new IllegalArgumentException();
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();
        byte[] iv = new byte[12]; new SecureRandom().nextBytes(iv);
        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        aes.updateAAD(address.getBytes(StandardCharsets.UTF_8));
        byte[] encrypted = aes.doFinal((parameter + "\n" + password).getBytes(StandardCharsets.UTF_8));
        Cipher rsa = Cipher.getInstance("RSA/ECB/PKCS1Padding");
        rsa.init(Cipher.ENCRYPT_MODE, wrappingKey);
        byte[] raw = key.getEncoded();
        try { return new byte[][] {rsa.doFinal(raw), iv, encrypted}; }
        finally { Arrays.fill(raw, (byte)0); }
    }

    static String[] open(PrivateKey wrappingKey, String address, byte[][] data) throws Exception {
        if (data.length != 3 || data[0].length > 512 || data[1].length != 12 || data[2].length > 512)
            throw new IllegalArgumentException();
        Cipher rsa = Cipher.getInstance("RSA/ECB/PKCS1Padding");
        rsa.init(Cipher.DECRYPT_MODE, wrappingKey);
        byte[] raw = rsa.doFinal(data[0]);
        try {
            Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
            aes.init(Cipher.DECRYPT_MODE, new SecretKeySpec(raw, "AES"), new GCMParameterSpec(128, data[1]));
            aes.updateAAD(address.getBytes(StandardCharsets.UTF_8));
            String[] result = new String(aes.doFinal(data[2]), StandardCharsets.UTF_8).split("\n", 2);
            if (result.length != 2 || !key(result[0]) || !password(result[1])) throw new IllegalArgumentException();
            return result;
        } finally { Arrays.fill(raw, (byte)0); }
    }
}
