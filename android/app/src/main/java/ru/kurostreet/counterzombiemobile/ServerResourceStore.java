/* Verified data-only server cache IO. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import javax.net.ssl.HttpsURLConnection;

/** Has no Android dependency, so the actual transfer/extraction code is host-tested. */
final class ServerResourceStore {
    static final int MAX_FILES = 16384;
    static final long MAX_FILE = 512L << 20, MAX_TOTAL = 8L << 30;
    private static final Pattern HASH = Pattern.compile("[0-9a-f]{64}");
    private static final Pattern RANGE = Pattern.compile("bytes ([0-9]+)-([0-9]+)/([0-9]+)");
    private static final int BUFFER = 64 << 10;

    interface Control {
        void check() throws IOException;
        void progress(long done, long total);
    }
    static final Control NONE = new Control() {
        public void check() throws IOException {}
        public void progress(long done, long total) {}
    };
    static final class Entry {
        final String path, sha256;
        final long size;
        Entry(String path, long size, String sha256) {
            this.path = path; this.size = size; this.sha256 = sha256;
        }
    }
    private ServerResourceStore() {}

    static boolean safePath(String path) {
        if (path == null || path.isEmpty() || path.length() > 240 || path.startsWith("/") || path.indexOf('\\') >= 0) return false;
        String[] parts = path.split("/", -1);
        if (parts.length > 8) return false;
        for (String part : parts) {
            if (part.isEmpty() || part.length() > 80 || part.startsWith(".") || part.endsWith(".") || part.endsWith(" ")) return false;
            for (int i = 0; i < part.length(); i++) {
                char c = part.charAt(i);
                if (!(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_' || c == '-' || c == '.' || c == ' ')) return false;
            }
        }
        return true;
    }

    static boolean allowedAsset(String path) {
        if (!safePath(path)) return false;
        String p = path.toLowerCase(Locale.ROOT);
        if (p.indexOf('/') < 0) return p.endsWith(".wad");
        if (p.startsWith("maps/")) return p.endsWith(".bsp");
        if (p.startsWith("models/")) return p.endsWith(".mdl");
        if (p.startsWith("sprites/")) return p.endsWith(".spr");
        if (p.startsWith("sound/")) return p.endsWith(".wav") || p.endsWith(".mp3") || p.endsWith(".ogg");
        if (p.startsWith("gfx/") || p.startsWith("textures/")) return p.endsWith(".tga") || p.endsWith(".bmp") || p.endsWith(".png");
        return false;
    }

    /** Default Android TLS verifies chain and hostname; redirects are deliberately disabled. */
    static URL assetUrl(String text) throws IOException {
        try {
            URI uri = new URI(text);
            String path = uri.getRawPath();
            if (!"https".equals(uri.getScheme()) || !"kontrafps.ru".equalsIgnoreCase(uri.getHost()) ||
                uri.getPort() != -1 && uri.getPort() != 443 || uri.getRawUserInfo() != null ||
                uri.getRawQuery() != null || uri.getRawFragment() != null || path == null ||
                !path.startsWith("/server-resources/") || path.contains("//") || path.contains("%") || path.contains("\\")) throw new IOException("resource origin");
            for (String part : path.substring(1).split("/", -1))
                if (part.isEmpty() || part.equals(".") || part.equals("..") || !part.matches("[A-Za-z0-9_.-]+")) throw new IOException("resource URL path");
            return uri.toURL();
        } catch (java.net.URISyntaxException | IllegalArgumentException e) {
            throw new IOException("resource URL", e);
        }
    }

    static boolean sha256(String hash) { return hash != null && HASH.matcher(hash).matches(); }

    private static MessageDigest digest() throws IOException {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch (java.security.NoSuchAlgorithmException e) { throw new IOException("SHA-256", e); }
    }
    private static String hex(byte[] bytes) {
        char[] out = new char[bytes.length * 2], alphabet = "0123456789abcdef".toCharArray();
        for (int i = 0; i < bytes.length; i++) { out[2*i] = alphabet[(bytes[i] & 255) >>> 4]; out[2*i+1] = alphabet[bytes[i] & 15]; }
        return new String(out);
    }
    static String hash(File file) throws IOException { return hash(file, NONE); }
    static String hash(File file, Control control) throws IOException {
        regular(file);
        MessageDigest digest = digest(); byte[] data = new byte[BUFFER];
        try (InputStream in = new FileInputStream(file)) {
            int n; while ((n = in.read(data)) != -1) { control.check(); digest.update(data, 0, n); }
        }
        control.check(); return hex(digest.digest());
    }
    static boolean verify(File file, long size, String sha) throws IOException { return verify(file, size, sha, NONE); }
    static boolean verify(File file, long size, String sha, Control control) throws IOException {
        if (size < 0 || !sha256(sha) || !file.isFile() || file.length() != size) return false;
        if (!file.getAbsoluteFile().equals(file.getCanonicalFile())) return false;
        return sha.equals(hash(file, control));
    }

    private static void regular(File file) throws IOException {
        if (!file.isFile() || !file.getAbsoluteFile().equals(file.getCanonicalFile())) throw new IOException("resource file type");
    }
    static File resolve(File root, String path) throws IOException {
        if (!safePath(path)) throw new IOException("resource path");
        File canonicalRoot = root.getCanonicalFile();
        if (!root.getAbsoluteFile().equals(canonicalRoot)) throw new IOException("resource root symlink");
        File file = new File(canonicalRoot, path);
        if (!file.getAbsoluteFile().equals(file.getCanonicalFile()) || !file.getPath().startsWith(canonicalRoot.getPath() + File.separator)) throw new IOException("resource symlink/path");
        return file;
    }
    private static void parent(File file) throws IOException {
        File dir = file.getParentFile();
        if (dir == null || !dir.getAbsoluteFile().equals(dir.getCanonicalFile())) throw new IOException("resource parent");
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("resource mkdir");
        if (!dir.getAbsoluteFile().equals(dir.getCanonicalFile())) throw new IOException("resource parent symlink");
    }
    private static void target(File file) throws IOException {
        if (!file.getAbsoluteFile().equals(file.getCanonicalFile()) || file.exists() && !file.isFile()) throw new IOException("resource target");
        parent(file);
    }

    /** Resume only the identical expected object. The caller names parts with the manifest hash. */
    static void download(URL url, File part, long size, String sha, Control control) throws IOException {
        assetUrl(url.toExternalForm());
        if (size <= 0 || size > MAX_TOTAL + (64L << 20) || !sha256(sha)) throw new IOException("resource size/hash");
        target(part); control.check();
        long start = part.isFile() ? part.length() : 0;
        if (start > size || start == size && !verify(part, size, sha, control)) { truncate(part); start = 0; }
        if (start == size) { control.progress(size, size); return; }
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        if (!(conn instanceof HttpsURLConnection)) throw new IOException("resource TLS");
        conn.setInstanceFollowRedirects(false); conn.setConnectTimeout(15000); conn.setReadTimeout(20000);
        conn.setRequestProperty("Accept-Encoding", "identity");
        if (start > 0) conn.setRequestProperty("Range", "bytes=" + start + "-");
        try {
            int status = conn.getResponseCode();
            if (start > 0 && status == 200) start = 0; // A server may ignore Range: safely restart the same object.
            else if (start > 0 && status == 206) {
                Matcher range = RANGE.matcher(value(conn.getHeaderField("Content-Range")));
                try {
                    if (!range.matches() || Long.parseLong(range.group(1)) != start || Long.parseLong(range.group(2)) != size - 1 || Long.parseLong(range.group(3)) != size) throw new IOException("resource Content-Range");
                } catch (NumberFormatException e) { throw new IOException("resource Content-Range", e); }
            } else if (status != 200) throw new IOException("resource HTTP " + status);
            String encoding = conn.getContentEncoding();
            if (encoding != null && !encoding.equalsIgnoreCase("identity")) throw new IOException("resource transfer encoding");
            long length = -1;
            String headerLength = conn.getHeaderField("Content-Length");
            if (headerLength != null) {
                try { length = Long.parseLong(headerLength); if (length < 0) throw new NumberFormatException(); }
                catch (NumberFormatException e) { throw new IOException("resource Content-Length", e); }
            }
            if (length >= 0 && length != size - start) throw new IOException("resource Content-Length");
            long done = start; control.progress(done, size);
            try (InputStream in = conn.getInputStream(); FileOutputStream out = new FileOutputStream(part, start > 0)) {
                byte[] data = new byte[BUFFER]; int n;
                while ((n = in.read(data)) != -1) {
                    control.check();
                    if (n > size - done) throw new IOException("resource too long");
                    out.write(data, 0, n); done += n; control.progress(done, size);
                }
                if (done != size) throw new IOException("resource truncated");
                out.getFD().sync();
            }
            control.check();
            if (!verify(part, size, sha, control)) { if (!part.delete()) throw new IOException("resource hash/delete"); throw new IOException("resource SHA-256"); }
        } finally { conn.disconnect(); }
    }
    private static String value(String text) { return text == null ? "" : text; }
    private static void truncate(File file) throws IOException { try (FileOutputStream out = new FileOutputStream(file, false)) { out.getFD().sync(); } }

    /** The destination must be a fresh staging directory; it is never an active revision. */
    static void extractZip(File archive, File dest, List<Entry> manifest, Control control) throws IOException {
        regular(archive);
        if (manifest.isEmpty() || manifest.size() > MAX_FILES || dest.exists()) throw new IOException("resource extraction state");
        Map<String, Entry> expected = new HashMap<>(); Set<String> folded = new HashSet<>(); long total = 0;
        for (Entry e : manifest) {
            if (!allowedAsset(e.path) || e.size <= 0 || e.size > MAX_FILE || !sha256(e.sha256) || expected.put(e.path, e) != null || !folded.add(e.path.toLowerCase(Locale.ROOT))) throw new IOException("resource manifest entry");
            total += e.size; if (total > MAX_TOTAL) throw new IOException("resource total");
        }
        checkZipTypes(archive, manifest.size());
        parent(dest); if (!dest.mkdir()) throw new IOException("resource staging mkdir");
        long done = 0; Set<String> seen = new HashSet<>();
        try (ZipInputStream zip = new ZipInputStream(new FileInputStream(archive))) {
            ZipEntry entry; byte[] data = new byte[BUFFER];
            while ((entry = zip.getNextEntry()) != null) {
                control.check(); String path = entry.getName(); Entry e = expected.get(path);
                if (entry.isDirectory() || e == null || !seen.add(path) || entry.getMethod() != ZipEntry.STORED && entry.getMethod() != ZipEntry.DEFLATED || entry.getSize() >= 0 && entry.getSize() != e.size) throw new IOException("resource ZIP entry");
                File file = resolve(dest, path); target(file); long count = 0; MessageDigest digest = digest();
                try (FileOutputStream out = new FileOutputStream(file)) {
                    int n; while ((n = zip.read(data)) != -1) {
                        control.check(); if (n > e.size - count) throw new IOException("resource ZIP size");
                        out.write(data, 0, n); digest.update(data, 0, n); count += n; done += n; control.progress(done, total);
                    }
                    if (count != e.size || !e.sha256.equals(hex(digest.digest()))) throw new IOException("resource ZIP hash/size");
                    out.getFD().sync();
                }
                if (!validFormat(file, path)) throw new IOException("resource format");
                zip.closeEntry();
            }
            if (seen.size() != expected.size()) throw new IOException("resource ZIP missing file");
        } catch (IOException | RuntimeException e) { deleteTree(dest); throw e; }
        control.check();
    }

    /** Reject Unix symlinks in central-directory metadata; extraction never follows links either. */
    private static void checkZipTypes(File archive, int expectedCount) throws IOException {
        try (RandomAccessFile in = new RandomAccessFile(archive, "r")) {
            long length = in.length(), start = Math.max(0, length - 65557), eocd = -1;
            for (long at = length - 22; at >= start; at--) {
                in.seek(at);
                if (le32(in) == 0x06054b50L) { in.seek(at + 20); if (at + 22L + le16(in) == length) { eocd = at; break; } }
            }
            if (eocd < 0) throw new IOException("resource ZIP directory");
            in.seek(eocd + 4);
            int disk = le16(in), centralDisk = le16(in), diskCount = le16(in), count = le16(in);
            long centralSize = le32(in), centralOffset = le32(in), directoryEnd = eocd;
            if (count == 0xffff || centralSize == 0xffffffffL || centralOffset == 0xffffffffL) {
                if (eocd < 20) throw new IOException("resource ZIP64 locator");
                in.seek(eocd - 20);
                if (le32(in) != 0x07064b50L || le32(in) != 0) throw new IOException("resource ZIP64 disk");
                long zip64 = le64(in);
                if (le32(in) != 1 || zip64 < 0 || zip64 >= eocd - 20) throw new IOException("resource ZIP64 bounds");
                in.seek(zip64);
                if (le32(in) != 0x06064b50L) throw new IOException("resource ZIP64 directory");
                long recordSize = le64(in);
                if (recordSize < 44 || zip64 + 12 + recordSize != eocd - 20) throw new IOException("resource ZIP64 size");
                le16(in); le16(in);
                if (le32(in) != 0 || le32(in) != 0) throw new IOException("resource ZIP64 disk");
                long diskEntries = le64(in), entries = le64(in);
                if (entries != expectedCount || diskEntries != entries) throw new IOException("resource ZIP64 count");
                count = (int)entries; diskCount = count;
                centralSize = le64(in); centralOffset = le64(in); directoryEnd = zip64;
            }
            if (disk != 0 || centralDisk != 0 || count != diskCount || count != expectedCount || count > MAX_FILES || centralOffset < 0 || centralSize < 0 || centralOffset > directoryEnd || centralSize != directoryEnd - centralOffset) throw new IOException("resource ZIP directory bounds");
            in.seek(centralOffset);
            for (int i = 0; i < count; i++) {
                if (le32(in) != 0x02014b50L) throw new IOException("resource ZIP directory header");
                le16(in); le16(in); int flags = le16(in); int method = le16(in);
                in.skipBytes(8); long compressed = le32(in), size = le32(in);
                int name = le16(in), extra = le16(in), comment = le16(in), diskStart = le16(in); le16(in); long attributes = le32(in); long offset = le32(in);
                int mode = (int)(attributes >>> 16), type = mode & 0170000;
                if ((flags & 1) != 0 || method != ZipEntry.STORED && method != ZipEntry.DEFLATED || diskStart != 0 || size > MAX_FILE || compressed == 0xffffffffL || name == 0 || (attributes & 0x10) != 0 || type != 0 && type != 0100000) throw new IOException("resource ZIP file type");
                long next = in.getFilePointer() + name + extra + comment;
                if (next > centralOffset + centralSize) throw new IOException("resource ZIP directory overrun");
                if (offset == 0xffffffffL) {
                    in.skipBytes(name); long extraEnd = in.getFilePointer() + extra; boolean found = false;
                    while (in.getFilePointer() + 4 <= extraEnd) {
                        int tag = le16(in), bytes = le16(in); long end = in.getFilePointer() + bytes;
                        if (end > extraEnd) throw new IOException("resource ZIP extra");
                        if (tag == 1) {
                            // Per-file sizes are bounded below ZIP64 size sentinels; only offset needs 64 bits.
                            if (bytes < 8) throw new IOException("resource ZIP64 offset");
                            offset = le64(in); found = true;
                        }
                        in.seek(end);
                    }
                    if (!found) throw new IOException("resource ZIP64 offset missing");
                }
                if (offset < 0 || offset >= centralOffset) throw new IOException("resource ZIP local offset");
                in.seek(next);
            }
            if (in.getFilePointer() != centralOffset + centralSize) throw new IOException("resource ZIP directory size");
        }
    }
    private static int le16(RandomAccessFile in) throws IOException { int a = in.readUnsignedByte(), b = in.readUnsignedByte(); return a | b << 8; }
    private static long le32(RandomAccessFile in) throws IOException { return (long)le16(in) | (long)le16(in) << 16; }
    private static long le64(RandomAccessFile in) throws IOException { long low = le32(in), high = le32(in); if ((high & 0x80000000L) != 0) throw new IOException("resource ZIP64 overflow"); return low | high << 32; }

    static void copyVerified(File source, File destination, long size, String sha, Control control) throws IOException {
        if (source.getCanonicalFile().equals(destination.getCanonicalFile())) throw new IOException("resource copy aliases source");
        if (!verify(source, size, sha, control)) throw new IOException("resource copy source");
        target(destination); long done = 0;
        try (InputStream in = new FileInputStream(source); FileOutputStream out = new FileOutputStream(destination)) {
            byte[] data = new byte[BUFFER]; int n;
            while ((n = in.read(data)) != -1) { control.check(); if (n > size - done) throw new IOException("resource copy size"); out.write(data, 0, n); done += n; control.progress(done, size); }
            out.getFD().sync();
        }
        if (!verify(destination, size, sha, control)) throw new IOException("resource copy hash");
    }

    static void deleteTree(File file) throws IOException {
        if (!file.exists() && file.getAbsoluteFile().equals(file.getCanonicalFile())) return;
        if (file.isDirectory() && file.getAbsoluteFile().equals(file.getCanonicalFile())) {
            File[] children = file.listFiles(); if (children == null) throw new IOException("resource list");
            for (File child : children) deleteTree(child);
        }
        if (!file.delete()) throw new IOException("resource delete");
    }

    static boolean validFormat(File file, String path) throws IOException {
        if (!allowedAsset(path)) return false;
        regular(file); byte[] h = new byte[512]; int n;
        try (InputStream in = new FileInputStream(file)) { n = in.read(h); }
        String p = path.toLowerCase(Locale.ROOT);
        long size = file.length();
        if (p.endsWith(".bsp")) {
            if (n < 124 || u32(h, 0) != 30) return false;
            for (int i = 0; i < 15; i++) { long offset = u32(h, 4 + i * 8), length = u32(h, 8 + i * 8); if (offset > size || length > size - offset) return false; }
            return true;
        }
        if (p.endsWith(".mdl")) return n >= 76 && u32(h, 4) == 10 && u32(h, 72) == file.length() && (n >= 244 && ascii(h, "IDST") || ascii(h, "IDSQ"));
        if (p.endsWith(".spr")) return n >= 40 && ascii(h, "IDSP") && u32(h, 4) == 2;
        if (p.endsWith(".wad")) { long count = u32(h, 4), offset = u32(h, 8); return n >= 12 && (ascii(h, "WAD2") || ascii(h, "WAD3")) && count <= 65536 && offset <= size && count * 32 <= size - offset; }
        if (p.endsWith(".wav")) return n >= 44 && ascii(h, "RIFF") && u32(h, 4) + 8 == size && h[8] == 'W' && h[9] == 'A' && h[10] == 'V' && h[11] == 'E';
        if (p.endsWith(".ogg")) return n >= 27 && ascii(h, "OggS") && h[4] == 0;
        if (p.endsWith(".mp3")) return n >= 10 && (ascii(h, "ID3") && (h[6] & 255) < 128 && (h[7] & 255) < 128 && (h[8] & 255) < 128 && (h[9] & 255) < 128 || (h[0] & 255) == 255 && (h[1] & 224) == 224 && (h[1] & 6) != 0);
        if (p.endsWith(".png")) return n >= 33 && (h[0] & 255) == 137 && h[1] == 'P' && h[2] == 'N' && h[3] == 'G' && h[4] == 13 && h[5] == 10 && h[6] == 26 && h[7] == 10 && h[12] == 'I' && h[13] == 'H' && h[14] == 'D' && h[15] == 'R' && big32(h, 16) > 0 && big32(h, 16) <= 16384 && big32(h, 20) > 0 && big32(h, 20) <= 16384;
        if (p.endsWith(".bmp")) return n >= 54 && h[0] == 'B' && h[1] == 'M' && u32(h, 2) == size;
        if (p.endsWith(".tga")) { int type = h[2] & 255, width = (h[12] & 255) | (h[13] & 255) << 8, height = (h[14] & 255) | (h[15] & 255) << 8; return n >= 18 && (h[1] & 255) <= 1 && (type == 1 || type == 2 || type == 3 || type == 9 || type == 10 || type == 11) && width > 0 && width <= 16384 && height > 0 && height <= 16384 && ((h[16] & 255) == 8 || (h[16] & 255) == 16 || (h[16] & 255) == 24 || (h[16] & 255) == 32); }
        return false;
    }
    private static long u32(byte[] b, int at) { return (b[at] & 255L) | (b[at+1] & 255L) << 8 | (b[at+2] & 255L) << 16 | (b[at+3] & 255L) << 24; }
    private static long big32(byte[] b, int at) { return (b[at] & 255L) << 24 | (b[at+1] & 255L) << 16 | (b[at+2] & 255L) << 8 | (b[at+3] & 255L); }
    private static boolean ascii(byte[] b, String s) { for (int i = 0; i < s.length(); i++) if (b[i] != s.charAt(i)) return false; return true; }
}
