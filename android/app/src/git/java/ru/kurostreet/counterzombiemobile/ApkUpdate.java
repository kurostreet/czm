package ru.kurostreet.counterzombiemobile;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InterruptedIOException;
import java.io.RandomAccessFile;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** Streaming, byte-exact APK updates. This class also runs in the desktop tests. */
public final class ApkUpdate {
    private static final byte[] MAGIC = "CZMPAT01".getBytes(StandardCharsets.US_ASCII);
    private static final long MAX_APK = 2L << 30;
    private static final int MAX_HEADER = 2 << 20, MAX_OPS = 50000;
    private static final int BUFFER = 128 * 1024;

    public interface Progress {
        boolean cancelled();
        void update(boolean verifying, long done, long total);
    }

    public static final class UpdateException extends IOException {
        public final String reason;
        UpdateException(String reason) { super(reason); this.reason = reason; }
    }

    private ApkUpdate() {}

    private static void check(Progress progress) throws InterruptedIOException {
        if (progress.cancelled()) throw new InterruptedIOException("cancelled");
    }

    private static boolean hash(String value) {
        return value != null && value.matches("[0-9a-fA-F]{64}");
    }

    private static MessageDigest digest() {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch (NoSuchAlgorithmException e) { throw new AssertionError(e); }
    }

    private static String hex(byte[] bytes) {
        char[] digits = "0123456789abcdef".toCharArray();
        char[] out = new char[bytes.length * 2];
        for (int i = 0; i < bytes.length; i++) {
            out[i * 2] = digits[(bytes[i] & 255) >>> 4];
            out[i * 2 + 1] = digits[bytes[i] & 15];
        }
        return new String(out);
    }

    public static String sha256(File file, Progress progress) throws IOException {
        MessageDigest md = digest();
        byte[] buffer = new byte[BUFFER];
        try (InputStream in = new FileInputStream(file)) {
            int n;
            while ((n = in.read(buffer)) != -1) {
                check(progress);
                md.update(buffer, 0, n);
            }
        }
        check(progress);
        return hex(md.digest());
    }

    private static void space(File dir, long needed) throws UpdateException {
        if (dir.getUsableSpace() < needed + (8L << 20)) throw new UpdateException("storage");
    }

    /** Keeps interrupted downloads for this target only; never alters the installed APK. */
    public static File prepare(File dir, File base, String url, String sha, long size,
                               String patchUrl, String patchSha, long patchSize, String baseSha,
                               Progress progress) throws IOException {
        if (!hash(sha) || size <= 0 || size > MAX_APK) throw new UpdateException("broken");
        if (!dir.isDirectory() && !dir.mkdirs()) throw new UpdateException("storage");
        String prefix = "czm-" + sha.toLowerCase(java.util.Locale.ROOT);
        File apk = new File(dir, prefix + ".apk");
        File patch = new File(dir, prefix + ".patch");
        File partial = new File(dir, prefix + ".building");
        File[] previous = dir.listFiles();
        if (previous != null) for (File file : previous) {
            if (!file.equals(apk) && !file.equals(patch)) file.delete();
        }
        try {
            check(progress);
            progress.update(true, 0, patchSize > 0 ? patchSize : size);
            if (apk.length() == size) {
                if (sha.equalsIgnoreCase(sha256(apk, progress))) return apk;
                apk.delete();
            }
            if (base != null && base.isFile() && hash(baseSha) && hash(patchSha)
                    && patchUrl != null && !patchUrl.isEmpty() && patchSize > 0 && patchSize < size) {
                try {
                    if (baseSha.equalsIgnoreCase(sha256(base, progress))) {
                        // Partial full downloads cannot be used as patch output.
                        apk.delete();
                        space(dir, size + Math.max(0, patchSize - patch.length()));
                        fetch(patchUrl, patch, patchSize, progress);
                        progress.update(true, patchSize, patchSize);
                        if (!patchSha.equalsIgnoreCase(sha256(patch, progress))) throw new UpdateException("broken");
                        apply(base, patch, partial, baseSha, sha, size, progress);
                        check(progress);
                        if (!partial.renameTo(apk)) throw new UpdateException("storage");
                        patch.delete();
                        return apk;
                    }
                } catch (IOException | JSONException e) {
                    check(progress); // cancellation never turns into a full APK download
                    partial.delete();
                    patch.delete();
                    // Missing patch, wrong base, damaged payload or result: use the full APK.
                }
            }
            check(progress);
            patch.delete();
            progress.update(false, 0, size);
            space(dir, Math.max(0, size - apk.length()));
            fetch(url, apk, size, progress);
            progress.update(true, size, size);
            if (!sha.equalsIgnoreCase(sha256(apk, progress))) {
                apk.delete();
                throw new UpdateException("broken");
            }
            check(progress);
            return apk;
        } finally {
            partial.delete();
        }
    }

    /** Resume only a response whose range and total match our immutable release file. */
    static void fetch(String url, File file, long size, Progress progress) throws IOException {
        IOException last = null;
        for (int attempt = 0; attempt < 5; attempt++) {
            check(progress);
            long have = file.isFile() ? file.length() : 0;
            if (have > size) { file.delete(); have = 0; }
            if (have == size) return;
            space(file.getParentFile(), size - have);
            HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(30000);
            conn.setRequestProperty("Accept-Encoding", "identity");
            conn.setRequestProperty("User-Agent", "CounterZombieMobile/Updater");
            if (have > 0) conn.setRequestProperty("Range", "bytes=" + have + "-");
            try {
                int status = conn.getResponseCode();
                if (status == 200) have = 0;
                else if (status != 206 || !("bytes " + have + "-" + (size - 1) + "/" + size).equals(conn.getHeaderField("Content-Range"))) {
                    // An invalid range is not appended to previously verified offsets.
                    if (status == 206 || status == 416) file.delete();
                    throw new IOException("HTTP range " + status);
                }
                long responseSize = -1;
                String responseLength = conn.getHeaderField("Content-Length");
                try { if (responseLength != null) responseSize = Long.parseLong(responseLength); }
                catch (NumberFormatException e) { throw new IOException("HTTP length", e); }
                if (responseSize >= 0 && responseSize != size - have) throw new IOException("HTTP length");
                try (InputStream in = conn.getInputStream(); RandomAccessFile out = new RandomAccessFile(file, "rw")) {
                    out.setLength(have);
                    out.seek(have);
                    byte[] buffer = new byte[BUFFER];
                    int n;
                    progress.update(false, have, size);
                    while ((n = in.read(buffer)) != -1) {
                        check(progress);
                        if (n > size - have) throw new UpdateException("broken");
                        out.write(buffer, 0, n);
                        have += n;
                        progress.update(false, have, size);
                    }
                }
                check(progress);
                if (file.length() == size) return;
                throw new IOException("incomplete");
            } catch (IOException e) {
                check(progress);
                last = e;
                if (e instanceof UpdateException) { file.delete(); throw e; }
            } finally {
                conn.disconnect();
            }
            if (attempt < 4) {
                try { Thread.sleep(500); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new InterruptedIOException(); }
            }
        }
        throw last == null ? new IOException("incomplete") : last;
    }

    private static long integer(Object value) throws IOException {
        if (!(value instanceof Integer) && !(value instanceof Long)) throw new UpdateException("broken");
        return ((Number) value).longValue();
    }

    /** Applies a bounded recipe to raw bytes, including the original APK signing block. */
    public static void apply(File base, File patch, File target, String baseSha, String sha, long size,
                             Progress progress) throws IOException, JSONException {
        if (target.equals(base) || target.equals(patch) || size <= 0 || size > MAX_APK) throw new UpdateException("broken");
        try (RandomAccessFile data = new RandomAccessFile(patch, "r"); RandomAccessFile original = new RandomAccessFile(base, "r")) {
            byte[] magic = new byte[8];
            data.readFully(magic);
            int length = data.readInt();
            if (!Arrays.equals(magic, MAGIC) || length <= 0 || length > MAX_HEADER || length > data.length() - 12)
                throw new UpdateException("broken");
            byte[] header = new byte[length];
            data.readFully(header);
            JSONObject recipe = new JSONObject(new String(header, StandardCharsets.UTF_8));
            long baseSize = original.length(), dataStart = 12L + length;
            long dataSize = integer(recipe.get("data_size"));
            JSONArray ops = recipe.getJSONArray("ops");
            if (integer(recipe.get("format")) != 1 || !baseSha.equalsIgnoreCase(recipe.getString("base_sha256"))
                    || !sha.equalsIgnoreCase(recipe.getString("sha256")) || integer(recipe.get("size")) != size
                    || integer(recipe.get("base_size")) != baseSize || dataSize < 0 || dataSize > size
                    || dataSize != data.length() - dataStart || ops.length() == 0 || ops.length() > MAX_OPS)
                throw new UpdateException("broken");
            // Caller also checks the base before downloading; keep apply safe on its own.
            if (!baseSha.equalsIgnoreCase(sha256(base, progress))) throw new UpdateException("broken");
            long produced = 0, used = 0;
            byte[] buffer = new byte[BUFFER];
            MessageDigest md = digest();
            try (FileOutputStream out = new FileOutputStream(target)) {
                for (int i = 0; i < ops.length(); i++) {
                    check(progress);
                    JSONArray op = ops.getJSONArray(i);
                    if (op.length() != 3) throw new UpdateException("broken");
                    long kind = integer(op.get(0)), offset = integer(op.get(1)), count = integer(op.get(2));
                    long limit = kind == 0 ? baseSize : dataSize;
                    if ((kind != 0 && kind != 1) || offset < 0 || count <= 0 || count > size - produced
                            || offset > limit || count > limit - offset || (kind == 1 && offset != used))
                        throw new UpdateException("broken");
                    RandomAccessFile source = kind == 0 ? original : data;
                    source.seek(kind == 0 ? offset : dataStart + offset);
                    long left = count;
                    while (left > 0) {
                        check(progress);
                        int n = (int) Math.min(buffer.length, left);
                        source.readFully(buffer, 0, n);
                        md.update(buffer, 0, n);
                        out.write(buffer, 0, n);
                        left -= n;
                    }
                    produced += count;
                    if (kind == 1) used += count;
                }
                if (produced != size || used != dataSize || !sha.equalsIgnoreCase(hex(md.digest()))) throw new UpdateException("broken");
                check(progress);
                out.getFD().sync();
            }
        }
    }
}
