package ru.kurostreet.counterzombiemobile;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.security.cert.Certificate;
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
        check(ServerResources.prepare(ADDRESS)==-1,"known enabled server fails closed when catalog fetch fails");
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
        public void connect(){}
        public void disconnect(){}
        public boolean usingProxy(){return false;}
        public int getResponseCode() throws IOException {if(networkFailure)throw new IOException("simulated offline");return 200;}
        public long getContentLengthLong(){return reply.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;}
        public InputStream getInputStream(){return new ByteArrayInputStream(reply.getBytes(java.nio.charset.StandardCharsets.UTF_8));}
        public String getCipherSuite(){return "HOST_TEST_ONLY";}
        public Certificate[] getLocalCertificates(){return null;}
        public Certificate[] getServerCertificates(){return new Certificate[0];}
    }
    public static void main(String[] args) throws Exception {
        URL.setURLStreamHandlerFactory(protocol->protocol.equals("https")?new URLStreamHandler(){
            protected URLConnection openConnection(URL url){return new FakeConnection(url);}
        }:null);
        try{
            leasesAndCancellation();mappingRevocation();expiryDuringInitialVerification();catalogFailurePolicy();clearRevokesSharedPackBeforeQueuedIO();
            System.out.println("SERVER_RESOURCES_MANAGER_OK "+checks);
        }finally{
            ((ExecutorService)get("CATALOG_WORK")).shutdownNow();((ExecutorService)get("FILE_WORK")).shutdownNow();
        }
    }
}
