package ru.kurostreet.counterzombiemobile;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.security.cert.Certificate;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.concurrent.ConcurrentHashMap;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.json.JSONObject;
import org.json.JSONArray;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.HttpsURLConnection;

/** The actual manager is compiled with Android presentation stubs; no extracted state machine. */
public final class ServerResourcesManagerTest {
    static final Class<?> MANAGER = ServerResources.class;
    static final String ADDRESS = "176.118.222.43:27016", OTHER = "8.8.8.8:27015";
    static final String KEY = ServerPolicy.endpoint(ADDRESS), OTHER_KEY = ServerPolicy.endpoint(OTHER);
    static final String HASH = String.join("", Collections.nCopies(64, "a"));
    static int checks;
    static volatile boolean networkFailure=true;
    static final Map<String,byte[]> objects=new ConcurrentHashMap<>();
    static final Map<String,Integer> requests=new ConcurrentHashMap<>();
    static volatile String reply="{\"schema\":1,\"max_age_seconds\":60,\"servers\":[]}";

    static void check(boolean yes,String message){checks++;if(!yes)throw new AssertionError(message);}
    static Field field(Class<?> owner,String name) throws Exception {Field f=owner.getDeclaredField(name);f.setAccessible(true);return f;}
    static void set(String name,Object value) throws Exception {field(MANAGER,name).set(null,value);}
    static Object get(String name) throws Exception {return field(MANAGER,name).get(null);}
    static long clock(){return System.nanoTime()/1000000L;}
    static Object item(String address,String revision) throws Exception {
        Class<?> owner=Class.forName(MANAGER.getName()+"$Item");
        Constructor<?> ctor=owner.getDeclaredConstructors()[0];ctor.setAccessible(true);
        return ctor.newInstance("survival",ServerPolicy.endpoint(address),true,"survival",revision,
                "https://kontrafps.ru/server-resources/survival/"+revision+"/manifest.json",HASH,100L);
    }
    static String key(Object item) throws Exception {Method m=item.getClass().getDeclaredMethod("key");m.setAccessible(true);return (String)m.invoke(item);}
    @SuppressWarnings("unchecked") static Map<String,Object> packs() throws Exception {return (Map<String,Object>)get("packs");}
    static Object readyPack(Object item) throws Exception {
        Class<?> owner=Class.forName(MANAGER.getName()+"$Pack");Constructor<?> ctor=owner.getDeclaredConstructors()[0];ctor.setAccessible(true);
        Object pack=ctor.newInstance(item);field(owner,"state").set(pack,"ready");field(owner,"verified").set(pack,true);
        field(owner,"working").set(pack,false);field(owner,"canonicalPath").set(pack,"/verified/"+key(item)+"/files");
        packs().put(key(item),pack);return pack;
    }
    static void fixture() throws Exception {
        synchronized(MANAGER){
            networkFailure=true;
            packs().clear();Object item=item(ADDRESS,"r1");readyPack(item);
            Map<String,Object> registry=new LinkedHashMap<>();registry.put(KEY,item);set("registry",registry);
            set("catalogAt",clock());set("catalogMaxAge",60000L);set("catalogNext",clock()+60000L);
            set("connectionAddress",KEY);set("connectionItem",item);set("connectionState",1);
            set("grantConsumed",false);set("grantExpires",clock()+60000L);set("mountedKey","");
        }
    }
    static void awaitCatalog() throws Exception {
        ((ExecutorService)get("CATALOG_WORK")).submit(()->{}).get(10,TimeUnit.SECONDS);
    }
    static void leasesAndCancellation() throws Exception {
        fixture();String path=ServerResources.mountPath(ADDRESS);
        check(!path.isEmpty(),"verified fresh endpoint receives a mount permit");
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"mount permit is single use");
        fixture();check(ServerResources.mountPath(OTHER).isEmpty(),"another endpoint cannot consume permit");
        check(!ServerResources.mountPath(ADDRESS).isEmpty(),"wrong endpoint does not consume matching permit");
        fixture();ServerResources.cancelConnection();
        check(ServerResources.prepare(ADDRESS)==-2&&ServerResources.mountPath(ADDRESS).isEmpty(),"cancelled join cannot mount later");
        fixture();set("mountedKey","old/r0/"+HASH);ServerResources.unmounted();
        check(!ServerResources.mountPath(ADDRESS).isEmpty(),"old disconnect callback does not revoke new prepared grant");
        fixture();set("grantExpires",clock()-1L);
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"expired single use grant rejected");
    }
    static void mappingRevocation() throws Exception {
        fixture();set("registry",Collections.emptyMap());set("catalogAt",clock());
        check(ServerResources.path(ADDRESS).isEmpty(),"fresh catalog removal revokes old verified path");
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"fresh catalog removal revokes old permit");
        check(ServerResources.prepare(ADDRESS)!=1,"removed endpoint cannot remain ready");
        fixture();Map<String,Object> moved=new LinkedHashMap<>();moved.put(OTHER_KEY,item(OTHER,"r1"));set("registry",moved);
        check(ServerResources.path(ADDRESS).isEmpty(),"slot IP change revokes old endpoint path");
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"slot IP change revokes old endpoint permit");
        fixture();Map<String,Object> revision=new LinkedHashMap<>();revision.put(KEY,item(ADDRESS,"r2"));set("registry",revision);
        check(ServerResources.path(ADDRESS).isEmpty(),"same endpoint revision update revokes old path");
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"same endpoint revision update revokes old grant");
        check(ServerResources.prepare(ADDRESS)!=1,"same endpoint revision update cannot dispatch old pack");awaitCatalog();
    }
    static void expiryDuringInitialVerification() throws Exception {
        fixture();set("connectionState",2);set("catalogAt",clock()-60001L);
        Object item=get("connectionItem");Method update=MANAGER.getDeclaredMethod("updateConnection",item.getClass());update.setAccessible(true);update.invoke(null,item);
        check(ServerResources.prepare(ADDRESS)!=1,"finishing initial verification after TTL never dispatches expired grant");
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"expired catalog cannot issue initial permit");awaitCatalog();
    }
    static void catalogFailurePolicy() throws Exception {
        fixture();ServerResources.refresh(ADDRESS);awaitCatalog();
        check(ServerResources.prepare(ADDRESS)==0,"known enabled server joins as usual when the catalog fetch fails");
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"a join without a catalog grants no resource path");
        fixture();ServerResources.refresh(OTHER);awaitCatalog();
        check(ServerResources.prepare(OTHER)==0,"foreign server remains connectable without managed mount when catalog fails");
        check(ServerResources.mountPath(OTHER).isEmpty(),"foreign fallback grants no resource path");
        fixture();networkFailure=false;
        reply="{\"schema\":1,\"max_age_seconds\":60,\"servers\":[{\"server_id\":\"survival\",\"address\":\""+ADDRESS+"\",\"resources_enabled\":false},{\"server_id\":\"escape\",\"address\":\"\",\"resources_enabled\":false}]}";
        ServerResources.refresh(ADDRESS);awaitCatalog();
        check(ServerResources.prepare(ADDRESS)==0,"disabled pack uses normal connection");
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"disabled pack grants no mount");
        check(ServerResources.eligibility(ADDRESS)==1,"configured slot is eligible independent of display visibility");
    }
    static void downloadsNeverHoldJoin() throws Exception {
        fixture();Object item=get("connectionItem");Object pack=packs().get(key(item));Class<?> owner=pack.getClass();
        Method update=MANAGER.getDeclaredMethod("updateConnection",item.getClass());update.setAccessible(true);
        field(owner,"working").set(pack,true);field(owner,"state").set(pack,"downloading");set("connectionState",2);update.invoke(null,item);
        check(ServerResources.prepare(ADDRESS)==0,"a running download never holds a join");
        check(ServerResources.mountPath(ADDRESS).isEmpty(),"a pack being downloaded is never mounted");
        field(owner,"state").set(pack,"checking");set("connectionState",2);update.invoke(null,item);
        check(ServerResources.prepare(ADDRESS)==2,"checking a pack already on the device is waited for");
        field(owner,"working").set(pack,false);field(owner,"state").set(pack,"ready");update.invoke(null,item);
        check(ServerResources.prepare(ADDRESS)==1,"the checked pack is mounted");
        set("connectionState",0);update.invoke(null,item);
        check(ServerResources.prepare(ADDRESS)==0&&ServerResources.mountPath(ADDRESS).isEmpty(),"a download finishing later never mounts into a join that went without the pack");
        field(owner,"state").set(pack,"error");set("connectionState",2);update.invoke(null,item);
        check(ServerResources.prepare(ADDRESS)==0,"a broken pack joins as usual");
    }
    static void clearRevokesSharedPackBeforeQueuedIO() throws Exception {
        fixture();Object second=item(OTHER,"r2");readyPack(second);
        Map<String,Object> registry=new LinkedHashMap<>();registry.put(KEY,get("connectionItem"));registry.put(OTHER_KEY,second);set("registry",registry);
        set("connectionAddress",OTHER_KEY);set("connectionItem",second);
        CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);
        ExecutorService files=(ExecutorService)get("FILE_WORK");
        files.submit(()->{entered.countDown();try{release.await(10,TimeUnit.SECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}});
        check(entered.await(5,TimeUnit.SECONDS),"file worker blocker established");
        try{
            Method clear=MANAGER.getDeclaredMethod("clear",String.class);clear.setAccessible(true);clear.invoke(null,ADDRESS);
            check(ServerResources.path(OTHER).isEmpty(),"clearing pack revokes other assigned revision synchronously");
            check(ServerResources.mountPath(OTHER).isEmpty(),"queued pack deletion cannot race a mount of sibling revision");
        }finally{release.countDown();files.submit(()->{}).get(10,TimeUnit.SECONDS);}
    }
    static final class FakeConnection extends HttpsURLConnection {
        FakeConnection(URL url){super(url);}
        byte[] body(){return url.getPath().equals("/api/v1/server-resources/catalog/v2")?reply.getBytes(StandardCharsets.UTF_8):objects.get(url.getPath());}
        public void connect(){}
        public void disconnect(){}
        public boolean usingProxy(){return false;}
        public int getResponseCode() throws IOException {
            if(networkFailure)throw new IOException("simulated offline");
            requests.merge(url.getPath(),1,Integer::sum);return body()==null?404:200;
        }
        public long getContentLengthLong(){return body()==null?0:body().length;}
        public String getHeaderField(String key){return key.equalsIgnoreCase("Content-Length")?Long.toString(getContentLengthLong()):null;}
        public InputStream getInputStream() throws IOException {byte[] data=body();if(data==null)throw new IOException("missing fixture");return new ByteArrayInputStream(data);}
        public String getCipherSuite(){return "HOST_TEST_ONLY";}
        public Certificate[] getLocalCertificates(){return null;}
        public Certificate[] getServerCertificates(){return new Certificate[0];}
    }
    static String sha(byte[] bytes) throws Exception {
        StringBuilder out=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))out.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return out.toString();
    }
    static byte[] wave(int seed){
        byte[] bytes=new byte[1044];ByteBuffer out=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        out.put("RIFF".getBytes(StandardCharsets.US_ASCII));out.putInt(bytes.length-8);out.put("WAVEfmt ".getBytes(StandardCharsets.US_ASCII));
        out.putInt(16).putShort((short)1).putShort((short)1).putInt(8000).putInt(8000).putShort((short)1).putShort((short)8);
        out.put("data".getBytes(StandardCharsets.US_ASCII)).putInt(1000);while(out.hasRemaining())out.put((byte)(seed+out.position()*13));return bytes;
    }
    static void publishFixture(String revision,byte[] first,byte[] reused) throws Exception {
        String base="/server-resources/survival/"+revision+"/";
        String[] names={"sound/test.wav","sound/reused.wav"};byte[][] data={first,reused};
        ByteArrayOutputStream zipped=new ByteArrayOutputStream();
        try(ZipOutputStream zip=new ZipOutputStream(zipped)){
            for(int i=0;i<names.length;i++){zip.putNextEntry(new ZipEntry(names[i]));zip.write(data[i]);zip.closeEntry();}
        }
        byte[] archive=zipped.toByteArray();objects.put(base+"bundle.zip",archive);
        JSONArray files=new JSONArray();long total=0;
        for(int i=0;i<names.length;i++){
            String hash=sha(data[i]),path=base+"files/"+hash;objects.put(path,data[i]);total+=data[i].length;
            files.put(new JSONObject().put("path",names[i]).put("size",data[i].length).put("sha256",hash).put("url","https://kontrafps.ru"+path));
        }
        JSONObject manifest=new JSONObject().put("schema",1).put("pack_id","survival").put("revision",revision).put("total_bytes",total).put("files",files)
            .put("archive",new JSONObject().put("url","https://kontrafps.ru"+base+"bundle.zip").put("size",archive.length).put("sha256",sha(archive)));
        byte[] encoded=manifest.toString().getBytes(StandardCharsets.UTF_8);objects.put(base+"manifest.json",encoded);
        JSONObject slot=new JSONObject().put("server_id","survival").put("address",ADDRESS).put("resources_enabled",true).put("pack_id","survival").put("revision",revision)
            .put("manifest_url","https://kontrafps.ru"+base+"manifest.json").put("manifest_sha256",sha(encoded)).put("download_bytes",archive.length);
        reply=new JSONObject().put("schema",1).put("max_age_seconds",60).put("servers",new JSONArray().put(slot).put(new JSONObject().put("server_id","escape").put("address","").put("resources_enabled",false))).toString();
    }
    static void awaitFiles() throws Exception {((ExecutorService)get("FILE_WORK")).submit(()->{}).get(10,TimeUnit.SECONDS);}
    static int count(String path){return requests.getOrDefault(path,0);}
    /** aliased: the app folder is reached through a link, as Android's /data/user/0 -> /data/data. */
    static void bulkThenIncremental(boolean aliased) throws Exception {
        File root=Files.createTempDirectory("czm-manager-flow-").toFile().getCanonicalFile();
        File alias=new File(root.getParentFile(),root.getName()+"-alias");
        if(aliased)Files.createSymbolicLink(alias.toPath(),root.toPath());
        System.setProperty("czm.manager.root",(aliased?alias:root).getPath());org.libsdl.app.SDLActivity.context=new android.content.Context();android.net.ConnectivityManager.metered=false;
        try{
            fixture();objects.clear();requests.clear();networkFailure=false;set("registry",Collections.emptyMap());set("catalogAt",0L);set("connectionItem",null);set("connectionState",0);packs().clear();
            byte[] first=wave(1),same=wave(2),changed=wave(3);publishFixture("r1",first,same);
            ServerResources.refresh(ADDRESS);awaitCatalog();awaitFiles();
            check(ServerResources.prepare(ADDRESS)==0,"a pack not on the device never holds or asks at the join");
            check(ServerResources.mountPath(ADDRESS).isEmpty(),"joining without the pack grants no mount");
            check(count("/server-resources/survival/r1/manifest.json")==0,"a join without the pack does not touch it");
            ServerResources.status(ADDRESS);awaitFiles();
            check(ServerResources.status(ADDRESS)==1,"nothing on the device: the server card offers the download");
            Method download=MANAGER.getDeclaredMethod("download",String.class);download.setAccessible(true);download.invoke(null,ADDRESS);awaitFiles();
            check(ServerResources.status(ADDRESS)==3,"downloaded revision shows as ready on the server card");
            ServerResources.refresh(ADDRESS);awaitCatalog();awaitFiles();
            check(ServerResources.prepare(ADDRESS)==1,"a join after the download mounts the verified revision");
            check(count("/server-resources/survival/r1/bundle.zip")==1,"first download is one bulk ZIP");
            check(count("/server-resources/survival/r1/files/"+sha(first))==0&&count("/server-resources/survival/r1/files/"+sha(same))==0,"first ZIP avoids per-file HTTP round trips");
            File r1=new File(root,"server-resources/survival/r1/files");
            check(java.util.Arrays.equals(Files.readAllBytes(new File(r1,"sound/test.wav").toPath()),first),"first revision file bytes match");
            check(ServerResources.mountPath(ADDRESS).equals(r1.getCanonicalPath()),"bulk verified directory is granted to engine");ServerResources.unmounted();
            publishFixture("r2",changed,same);ServerResources.refresh(ADDRESS);awaitCatalog();awaitFiles();
            check(ServerResources.prepare(ADDRESS)==0&&ServerResources.mountPath(ADDRESS).isEmpty(),"a newer revision not yet downloaded joins without a pack");
            ServerResources.status(ADDRESS);awaitFiles();
            check(ServerResources.status(ADDRESS)==2,"an older revision on the device: the server card offers the update");
            download.invoke(null,ADDRESS);awaitFiles();check(ServerResources.status(ADDRESS)==3,"incremental update is ready on the card");
            ServerResources.refresh(ADDRESS);awaitCatalog();awaitFiles();check(ServerResources.prepare(ADDRESS)==1,"incremental update becomes ready");
            check(count("/server-resources/survival/r2/bundle.zip")==0,"incremental update skips whole archive");
            check(count("/server-resources/survival/r2/files/"+sha(changed))==1,"only changed file downloads");
            check(count("/server-resources/survival/r2/files/"+sha(same))==0,"unchanged file reused with hash verification");
            File r2=new File(root,"server-resources/survival/r2/files");
            check(java.util.Arrays.equals(Files.readAllBytes(new File(r2,"sound/test.wav").toPath()),changed),"new revision changed file matches");
            check(java.util.Arrays.equals(Files.readAllBytes(new File(r2,"sound/reused.wav").toPath()),same),"reused file remains correct");
            check(java.util.Arrays.equals(Files.readAllBytes(new File(r1,"sound/test.wav").toPath()),first),"incremental update preserves previous revision");
            check(ServerResources.mountPath(ADDRESS).equals(r2.getCanonicalPath()),"new verified revision is granted");ServerResources.unmounted();
        }finally{
            org.libsdl.app.SDLActivity.context=null;System.clearProperty("czm.manager.root");Files.deleteIfExists(alias.toPath());ServerResourceStore.deleteTree(root);
        }
    }
    public static void main(String[] args) throws Exception {
        URL.setURLStreamHandlerFactory(protocol->protocol.equals("https")?new URLStreamHandler(){
            protected URLConnection openConnection(URL url){return new FakeConnection(url);}
        }:null);
        try{
            leasesAndCancellation();mappingRevocation();expiryDuringInitialVerification();catalogFailurePolicy();downloadsNeverHoldJoin();clearRevokesSharedPackBeforeQueuedIO();bulkThenIncremental(false);bulkThenIncremental(true);
            System.out.println("SERVER_RESOURCES_MANAGER_OK "+checks);
        }finally{
            ((ExecutorService)get("CATALOG_WORK")).shutdownNow();((ExecutorService)get("FILE_WORK")).shutdownNow();
        }
    }
}
