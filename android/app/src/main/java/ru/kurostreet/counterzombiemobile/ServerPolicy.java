/* Community server policy. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

final class ServerPolicy {
    interface Loader { Set<String> load() throws Exception; }
    interface Clock { long now(); }
    static final ServerPolicy INSTANCE = new ServerPolicy(
        () -> System.nanoTime() / 1000000L, Executors.newSingleThreadExecutor(), ServerPolicy::download);
    private final Clock clock;
    private final Executor executor;
    private final Loader loader;
    private Set<String> blocked = Collections.emptySet();
    private long required, completed = -1, failed = -1, successAt, attemptAt, retryAt;
    private boolean busy, loaded;
    private int revision;

    ServerPolicy(Clock clock, Executor executor, Loader loader) {
        this.clock = clock; this.executor = executor; this.loader = loader;
    }

    /** Numeric endpoints only: this function must never resolve a hostname on the game thread. */
    static String endpoint(String value) {
        try {
            int colon = value.lastIndexOf(':');
            if (colon < 1) return "";
            String host = value.substring(0, colon), portText = value.substring(colon + 1);
            if (host.startsWith("[") && host.endsWith("]")) host = host.substring(1, host.length() - 1);
            if (host.indexOf(':') >= 0) {
                if (!host.matches("[0-9a-fA-F:.]+")) return "";
            } else {
                String[] parts = host.split("\\.", -1);
                if (parts.length != 4) return "";
                for (String part : parts) {
                    if (!part.matches("[0-9]{1,3}") || Integer.parseInt(part) > 255) return "";
                }
            }
            if (!portText.matches("[0-9]{1,5}")) return "";
            int port = Integer.parseInt(portText);
            if (port < 1 || port > 65535) return "";
            byte[] ip;
            if (host.indexOf(':') < 0) {
                String[] parts = host.split("\\."); ip = new byte[4];
                for (int i = 0; i < 4; i++) ip[i] = (byte)Integer.parseInt(parts[i]);
            } else ip = InetAddress.getByName(host).getAddress();
            StringBuilder key = new StringBuilder();
            String hex = "0123456789abcdef";
            for (byte b : ip) key.append(hex.charAt((b & 255) >> 4)).append(hex.charAt(b & 15));
            return key.append(':').append(port).toString();
        } catch (Exception ignored) { return ""; }
    }

    synchronized void beginConnection() { required++; refresh(true); }

    synchronized int revision() { refresh(false); return revision; }

    synchronized boolean blocked(String address) { return blocked.contains(endpoint(address)); }

    /** 0: checking, 1: allowed, 2: restricted, -1: policy unavailable. */
    synchronized int connectionState(String address) {
        String endpoint = endpoint(address);
        if (endpoint.isEmpty()) return -1;
        refresh(false);
        if (loaded && completed >= required && clock.now() - successAt < 60000)
            return blocked.contains(endpoint) ? 2 : 1;
        return !busy && failed >= required ? -1 : 0;
    }

    private synchronized void refresh(boolean force) {
        long time = clock.now();
        if (busy || time < retryAt) return;
        if (!force && completed >= required && loaded && time - attemptAt < 30000) return;
        busy = true; attemptAt = time;
        final long generation = required;
        executor.execute(() -> {
            try {
                Set<String> result = Collections.unmodifiableSet(new HashSet<>(loader.load()));
                synchronized (ServerPolicy.this) {
                    if (!loaded || !result.equals(blocked)) revision++;
                    blocked = result; loaded = true; completed = generation;
                    successAt = clock.now(); retryAt = 0; failed = -1;
                }
            } catch (Exception ignored) {
                synchronized (ServerPolicy.this) { failed = generation; retryAt = clock.now() + 5000; }
            } finally {
                synchronized (ServerPolicy.this) { busy = false; }
            }
        });
    }

    private static Set<String> download() throws Exception {
        HttpURLConnection connection = (HttpURLConnection)new URL(
            "https://counter-zombie.ru/api/v1/servers/policy").openConnection();
        try {
            connection.setConnectTimeout(8000); connection.setReadTimeout(8000);
            connection.setInstanceFollowRedirects(false); connection.setUseCaches(false);
            if (connection.getResponseCode() != 200) throw new java.io.IOException("policy");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] buffer = new byte[8192]; int size;
                while ((size = input.read(buffer)) != -1) {
                    if (bytes.size() + size > 1048576) throw new java.io.IOException("policy size");
                    bytes.write(buffer, 0, size);
                }
            }
            JSONArray entries = new JSONObject(new String(bytes.toByteArray(), StandardCharsets.UTF_8)).getJSONArray("blocked");
            Set<String> result = new HashSet<>();
            for (int i = 0; i < entries.length(); i++) {
                String key = endpoint(entries.getString(i));
                if (key.isEmpty()) throw new java.io.IOException("policy endpoint");
                result.add(key);
            }
            return result;
        } finally { connection.disconnect(); }
    }
}
