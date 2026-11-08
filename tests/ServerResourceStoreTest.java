package ru.kurostreet.counterzombiemobile;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.nio.file.Files;
import java.security.cert.Certificate;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import javax.net.ssl.HttpsURLConnection;

public final class ServerResourceStoreTest {
    static int checks;
    static File root;
    static void check(boolean yes, String why) { checks++; if (!yes) throw new AssertionError(why); }
    interface Action { void run() throws Exception; }
    static void fails(Action action, String why) throws Exception {
        try { action.run(); throw new AssertionError("accepted " + why); }
        catch (IOException expected) { checks++; }
    }
    static File file(String path, byte[] bytes) throws Exception {
        File f = new File(root, path); f.getParentFile().mkdirs(); Files.write(f.toPath(), bytes); return f;
    }
    static byte[] wave(int size) {
        byte[] data = new byte[size];
        System.arraycopy("RIFF0000WAVE".getBytes(java.nio.charset.StandardCharsets.US_ASCII), 0, data, 0, 12);
        for (int i = 0; i < 4; i++) data[4+i] = (byte)((size - 8) >>> (i * 8));
        for (int i = 12; i < size; i++) data[i] = (byte)(i * 13);
        return data;
    }
    static String sha(byte[] data) throws Exception { return ServerResourceStore.hash(file("hash.tmp", data)); }
    static File zip(String name, String path, byte[] data) throws Exception {
        File f = new File(root, name);
        try (ZipOutputStream out = new ZipOutputStream(new FileOutputStream(f))) {
            out.putNextEntry(new ZipEntry(path)); out.write(data); out.closeEntry();
        }
        return f;
    }
    static java.util.List<ServerResourceStore.Entry> manifest(byte[] bytes) throws Exception {
        return Collections.singletonList(new ServerResourceStore.Entry("sound/test.wav", bytes.length, sha(bytes)));
    }
    static final class FakeConnection extends HttpsURLConnection {
        final int code; final byte[] body; final Map<String, String> headers = new HashMap<>();
        boolean read, disconnected;
        FakeConnection(URL u, int c, byte[] b) { super(u); code = c; body = b; }
        public int getResponseCode() { return code; }
        public String getHeaderField(String name) { return headers.get(name); }
        public InputStream getInputStream() { read = true; return new ByteArrayInputStream(body); }
        public void disconnect() { disconnected = true; }
        public boolean usingProxy() { return false; }
        public void connect() {}
        public String getCipherSuite() { return "TLS_FAKE_TEST_ONLY"; }
        public Certificate[] getLocalCertificates() { return null; }
        public Certificate[] getServerCertificates() { return new Certificate[0]; }
    }
    static FakeConnection fake;
    static URL url(int status, byte[] body, String range) throws Exception {
        URL u = new URL(null, "https://kontrafps.ru/server-resources/test/rev/files/abc", new URLStreamHandler() {
            protected URLConnection openConnection(URL u) { return fake; }
        });
        fake = new FakeConnection(u, status, body); fake.headers.put("Content-Length", "" + body.length);
        if (range != null) fake.headers.put("Content-Range", range);
        return u;
    }
    static void pathsAndOrigins() throws Exception {
        for (String p : new String[]{"sound/music/test.mp3", "models/player/hero.mdl", "Maps/ZM Test.bsp", "halflife.wad"}) check(ServerResourceStore.allowedAsset(p), p);
        for (String p : new String[]{"../sound/a.wav", "sound/../a.wav", "/sound/a.wav", "sound\\a.wav", "sound/.hidden.wav", "sound/a.wav ", "sound/a.wav.", "sound//a.wav", "sound/а.wav", "addons/a.so", "autoexec.cfg", "models/a.jar", "maps/a.wad", "gfx/a.jpg"}) check(!ServerResourceStore.allowedAsset(p), p);
        check(ServerResourceStore.assetUrl("https://kontrafps.ru/server-resources/a/b/bundle.zip").getHost().equals("kontrafps.ru"), "trusted origin");
        for (String u : new String[]{"http://kontrafps.ru/server-resources/a", "https://evil.test/server-resources/a", "https://kontrafps.ru.evil.test/server-resources/a", "https://a@kontrafps.ru/server-resources/a", "https://kontrafps.ru:444/server-resources/a", "https://kontrafps.ru/server-resources/../a", "https://kontrafps.ru/server-resources/%2e%2e/a", "https://kontrafps.ru/server-resources/a?x=1", "https://kontrafps.ru/server-resources/a#x"}) fails(() -> ServerResourceStore.assetUrl(u), u);
    }
    static void transfer() throws Exception {
        byte[] bytes = wave(200000); String hash = sha(bytes); File part = file("download.part", Arrays.copyOf(bytes, 1000));
        URL source = url(206, Arrays.copyOfRange(bytes, 1000, bytes.length), "bytes 1000-199999/200000");
        ServerResourceStore.download(source, part, bytes.length, hash, ServerResourceStore.NONE);
        check("bytes=1000-".equals(fake.getRequestProperty("Range")), "resume Range request");
        check(!fake.getInstanceFollowRedirects() && "identity".equals(fake.getRequestProperty("Accept-Encoding")), "disable redirects/compression");
        check(fake.disconnected && ServerResourceStore.verify(part, bytes.length, hash), "resumed verified object");
        Files.write(part.toPath(), Arrays.copyOf(bytes, 1000));
        source = url(206, Arrays.copyOfRange(bytes, 1000, bytes.length), "bytes 999-199999/200000"); final URL wrong = source;
        fails(() -> ServerResourceStore.download(wrong, part, bytes.length, hash, ServerResourceStore.NONE), "wrong range");
        check(part.length() == 1000 && !fake.read, "bad range doesn't mix bytes");
        source = url(200, bytes, null); ServerResourceStore.download(source, part, bytes.length, hash, ServerResourceStore.NONE);
        check(ServerResourceStore.verify(part, bytes.length, hash), "ignored range safely restarts");
        part.delete(); final URL redirect = url(302, bytes, null);
        fails(() -> ServerResourceStore.download(redirect, part, bytes.length, hash, ServerResourceStore.NONE), "redirect");
        check(!fake.read && !part.exists(), "redirect never consumes body");
        final URL wrongHash = url(200, bytes, null);
        fails(() -> ServerResourceStore.download(wrongHash, part, bytes.length, String.join("", Collections.nCopies(64, "0")), ServerResourceStore.NONE), "bad SHA");
        check(!part.exists(), "corrupt partial removed");
        final URL cancel = url(200, bytes, null);
        ServerResourceStore.Control stop = new ServerResourceStore.Control() {
            long done;
            public void check() throws IOException { if (done >= 65536) throw new IOException("cancelled"); }
            public void progress(long d, long total) { done = d; }
        };
        fails(() -> ServerResourceStore.download(cancel, part, bytes.length, hash, stop), "cancel");
        int offset = (int)part.length(); check(offset > 0 && offset < bytes.length, "cancel retains resumable part");
        source = url(206, Arrays.copyOfRange(bytes, offset, bytes.length), "bytes " + offset + "-199999/200000");
        ServerResourceStore.download(source, part, bytes.length, hash, ServerResourceStore.NONE);
        check(ServerResourceStore.verify(part, bytes.length, hash), "resume after cancel");
        Files.write(part.toPath(), Arrays.copyOf(bytes, 100)); final URL length = url(200, bytes, null); fake.headers.put("Content-Length", "999999");
        fails(() -> ServerResourceStore.download(length, part, bytes.length, hash, ServerResourceStore.NONE), "wrong content length");
        check(part.length() == 100 && !fake.read, "length checked before write");
    }
    static void extraction() throws Exception {
        byte[] bytes = wave(1234); File archive = zip("good.zip", "sound/test.wav", bytes), output = new File(root, "good");
        ServerResourceStore.extractZip(archive, output, manifest(bytes), ServerResourceStore.NONE);
        check(ServerResourceStore.verify(new File(output, "sound/test.wav"), bytes.length, sha(bytes)), "verified extraction");
        check(ServerResourceStore.validFormat(new File(output, "sound/test.wav"), "sound/test.wav"), "format validated");
        fails(() -> ServerResourceStore.extractZip(archive, output, manifest(bytes), ServerResourceStore.NONE), "active dir not overwritten");
        File evil = zip("evil.zip", "../escape.wav", bytes); File dest = new File(root, "badpath");
        fails(() -> ServerResourceStore.extractZip(evil, dest, manifest(bytes), ServerResourceStore.NONE), "ZIP traversal");
        check(!dest.exists() && !new File(root, "escape.wav").exists(), "failed extraction cleaned only staging");
        byte[] changed = bytes.clone(); changed[100]++;
        File corrupt = zip("corrupt.zip", "sound/test.wav", changed); File bad = new File(root, "corrupt");
        fails(() -> ServerResourceStore.extractZip(corrupt, bad, manifest(bytes), ServerResourceStore.NONE), "ZIP hash mismatch");
        check(!bad.exists(), "corrupt staging removed");
        File extra = new File(root, "extra.zip");
        try (ZipOutputStream out = new ZipOutputStream(new FileOutputStream(extra))) {
            for (String path : new String[]{"sound/test.wav", "sound/extra.wav"}) { out.putNextEntry(new ZipEntry(path)); out.write(bytes); out.closeEntry(); }
        }
        fails(() -> ServerResourceStore.extractZip(extra, new File(root, "extra"), manifest(bytes), ServerResourceStore.NONE), "unmanifested ZIP file");
        java.util.List<ServerResourceStore.Entry> collision = Arrays.asList(new ServerResourceStore.Entry("sound/test.wav", bytes.length, sha(bytes)), new ServerResourceStore.Entry("sound/TEST.wav", bytes.length, sha(bytes)));
        fails(() -> ServerResourceStore.extractZip(archive, new File(root, "collision"), collision, ServerResourceStore.NONE), "case collision");
        File symlink = zip("symlink.zip", "sound/test.wav", bytes);
        try (RandomAccessFile f = new RandomAccessFile(symlink, "rw")) {
            for (long p = 0; p < f.length() - 46; p++) {
                f.seek(p); if (f.readInt() == 0x504b0102) {
                    f.seek(p + 5); f.write(3); // made by UNIX
                    f.seek(p + 40); f.write(0xff); f.write(0xa1); // high word: symlink mode 0120777
                    break;
                }
            }
        }
        fails(() -> ServerResourceStore.extractZip(symlink, new File(root, "symlink-out"), manifest(bytes), ServerResourceStore.NONE), "ZIP symlink metadata");
        File fake = zip("format.zip", "sound/test.wav", new byte[1234]); File fakeDir = new File(root, "format");
        fails(() -> ServerResourceStore.extractZip(fake, fakeDir, manifest(new byte[1234]), ServerResourceStore.NONE), "executable disguised as resource");
        check(!fakeDir.exists(), "format rejection cleans staging");
        File outside = file("outside/keep", bytes), link = new File(root, "linked");
        Files.createSymbolicLink(link.toPath(), outside.getParentFile().toPath());
        fails(() -> ServerResourceStore.resolve(root, "linked/keep"), "existing symlink path");
        fails(() -> ServerResourceStore.resolve(link, "keep"), "symlink root");
        ServerResourceStore.deleteTree(link);
        check(outside.exists() && !Files.exists(link.toPath()), "clear doesn't follow symlink");
        File copy = new File(root, "copy/test.wav");
        ServerResourceStore.copyVerified(new File(output, "sound/test.wav"), copy, bytes.length, sha(bytes), ServerResourceStore.NONE);
        Files.write(copy.toPath(), changed); check(ServerResourceStore.verify(new File(output, "sound/test.wav"), bytes.length, sha(bytes)), "revision reuse is a copy, not a hardlink");
        fails(() -> ServerResourceStore.copyVerified(copy, copy, copy.length(), sha(changed), ServerResourceStore.NONE), "copy cannot truncate source");
        byte[] sequence = new byte[76]; sequence[0] = 'I'; sequence[1] = 'D'; sequence[2] = 'S'; sequence[3] = 'Q'; sequence[4] = 10; sequence[72] = 76;
        check(ServerResourceStore.validFormat(file("sequence.mdl", sequence), "models/sequence.mdl"), "GoldSrc external sequence group");
        sequence[72] = 75; check(!ServerResourceStore.validFormat(file("sequence.mdl", sequence), "models/sequence.mdl"), "sequence group declared length checked");
    }
    public static void main(String[] args) throws Exception {
        root = new File(args[0]).getCanonicalFile(); root.mkdirs();
        pathsAndOrigins(); transfer(); extraction();
        for (int i = 1; i < args.length; i++) {
            File zip64 = new File(args[i]);
            ServerResourceStore.extractZip(zip64, new File(root, "zip64-" + i), manifest(wave(1234)), ServerResourceStore.NONE);
            check(new File(root, "zip64-" + i + "/sound/test.wav").isFile(), "publisher ZIP64 fixture " + i);
        }
        ServerResourceStore.deleteTree(root);
        System.out.println("ServerResourceStore: " + checks + " checks passed");
    }
}
