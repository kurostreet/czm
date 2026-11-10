/* Managed, data-only resources for the owner's server registry. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Context;
import android.net.ConnectivityManager;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.ProgressBar;
import android.widget.TextView;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;
import org.libsdl.app.SDLActivity;

/**
 * The menu only polls this class. Network, hashing, extraction and deletion run off
 * the game/UI thread. Catalog identity comes from the project's HTTPS origin,
 * never from a game server's name, FastDL URL, favorite or displayed badge.
 */
final class ServerResources {
    private static final String CATALOG = "https://kontrafps.ru/api/v1/server-resources/catalog";
    private static final ExecutorService CATALOG_WORK = Executors.newSingleThreadExecutor();
    private static final ExecutorService FILE_WORK = Executors.newSingleThreadExecutor();
    private static final Handler UI = new Handler(Looper.getMainLooper());
    private static final long RESERVE = 64L << 20;
    private static final String CHECKING="checking", MISSING="missing", READY="ready", DOWNLOADING="downloading",
        PAUSED="paused", ERROR="error", CLEARING="clearing";
    private static Map<String, Item> registry=Collections.emptyMap();
    private static final Map<String, Pack> packs=new HashMap<>();
    private static long catalogAt, catalogMaxAge=60000, catalogRequest, catalogNext;
    private static boolean catalogLoading;
    private static long connectionGeneration;
    private static String connectionAddress="", mountedKey="";
    private static int connectionState;
    private static Item connectionItem;
    private static boolean grantConsumed;
    private static long grantExpires;
    private static CzmDialog editor;
    private static String editorAddress="";
    private static Operation active;
    private static final Set<String> clearing=new HashSet<>(), deleting=new HashSet<>();

    private ServerResources() {}
    private static long clock(){return System.nanoTime()/1000000L;}
    private static String endpoint(String address){return ServerPolicy.endpoint(address==null?"":address);}
    private static boolean id(String text){return text!=null&&text.matches("[a-z0-9][a-z0-9_-]{0,63}");}
    private static boolean sha(String text){return text!=null&&text.matches("[0-9a-f]{64}");}
    private static Context context(){return SDLActivity.getContext();}

    private static final class Item {
        final String server, address, pack, revision, manifest, hash;
        final boolean enabled;
        final long bytes;
        Item(String server,String address,boolean enabled,String pack,String revision,String manifest,String hash,long bytes){
            this.server=server;this.address=address;this.enabled=enabled;this.pack=pack;this.revision=revision;
            this.manifest=manifest;this.hash=hash;this.bytes=bytes;
        }
        String key(){return pack+"/"+revision+"/"+hash;}
    }
    private static final class Asset {
        final ServerResourceStore.Entry file;
        final String url;
        Asset(ServerResourceStore.Entry file,String url){this.file=file;this.url=url;}
    }
    private static final class Manifest {
        final List<Asset> assets;
        final long total, archiveBytes;
        final String archiveUrl, archiveHash;
        Manifest(List<Asset> assets,long total,long archiveBytes,String archiveUrl,String archiveHash){
            this.assets=Collections.unmodifiableList(assets);this.total=total;this.archiveBytes=archiveBytes;
            this.archiveUrl=archiveUrl;this.archiveHash=archiveHash;
        }
    }
    private static final class Pack {
        final Item item;
        Manifest manifest;
        String state=CHECKING, error="";
        String canonicalPath="";
        long done,total,missing;
        boolean verified, working;
        int operation;
        Pack(Item item){this.item=item;}
    }
    private static final class Stopped extends IOException { Stopped(){super("paused");} }
    private static final class Operation implements ServerResourceStore.Control {
        final Pack pack;
        final int serial;
        volatile boolean cancelled;
        boolean network;
        long base, expected, networkChecked;
        Operation(Pack pack,int serial){this.pack=pack;this.serial=serial;}
        @Override public void check() throws IOException {
            if(cancelled||Thread.currentThread().isInterrupted())throw new Stopped();
            synchronized(ServerResources.class){if(pack.operation!=serial)throw new Stopped();}
            long now=clock();
            if(network&&now-networkChecked>=1000){networkChecked=now;if(metered()&&!mobileAllowed())throw new IOException("mobile");}
        }
        @Override public void progress(long done,long total){
            synchronized(ServerResources.class){
                if(pack.operation==serial){pack.done=base+Math.max(0,done);pack.total=Math.max(expected,base+Math.max(0,total));}
            }
        }
    }

    /** Called once for each join attempt, before any path can be granted. */
    static synchronized void refresh(String address){
        connectionGeneration++;connectionAddress=endpoint(address);connectionItem=null;
        connectionState=2;grantConsumed=false;grantExpires=0;
        if(connectionAddress.isEmpty()){connectionState=0;return;}
        requestCatalog(true,connectionGeneration);
    }

    /** 2 checking/downloading; 3 needs user's action; 1 ready; 0 none; -1 failure; -2 cancelled. */
    static synchronized int prepare(String address){
        String key=endpoint(address);
        if(!key.equals(connectionAddress))return -1;
        if(connectionState<0)return connectionState;
        // Catalog refreshes from a standalone panel also revoke/move old permits.
        Item current=registry.get(key);
        if(connectionItem!=null&&!sameItem(connectionItem,current)){
            grantExpires=0;grantConsumed=true;
            if(current==null||!current.enabled){connectionItem=null;connectionState=0;return 0;}
            refresh(address);return 2;
        }
        if(connectionItem!=null&&clock()-catalogAt>=catalogMaxAge){refresh(address);return 2;}
        if(connectionItem!=null&&connectionState>0)updateConnection(connectionItem);
        return connectionState;
    }

    /** Pure poll, no network or disk work. Eligibility expires independently of hello. */
    static synchronized int eligibility(String address){
        if(clock()-catalogAt>=catalogMaxAge){requestCatalog(false,0);return 0;}
        return registry.containsKey(endpoint(address))?1:0;
    }

    static synchronized String path(String address){
        if(!endpoint(address).equals(connectionAddress)||connectionState!=1||connectionItem==null)return "";
        if(!currentItem(connectionItem)||clock()-catalogAt>=catalogMaxAge||clearing.contains(connectionItem.pack)||deleting.contains(connectionItem.pack+"/"+connectionItem.revision))return "";
        Pack pack=packs.get(connectionItem.key());
        if(pack==null||!pack.verified||!READY.equals(pack.state))return "";
        return pack.canonicalPath;
    }

    /** Engine-only, single-use permit. A rescan reuses the engine's pinned path. */
    static synchronized String mountPath(String address){
        if(grantConsumed||clock()>grantExpires||clock()-catalogAt>=catalogMaxAge)return "";
        String result=path(address);
        if(result.isEmpty())return "";
        grantConsumed=true;mountedKey=connectionItem.key();
        final CzmDialog dialog=editorAddress.equals(connectionAddress)?editor:null;
        if(dialog!=null)UI.post(()->{synchronized(ServerResources.class){if(editor==dialog&&connectionState==1)dialog.dismiss();}});
        return result;
    }

    /** Does not invalidate a new pending connection's grant. */
    static synchronized void unmounted(){mountedKey="";}
    static synchronized void cancelConnection(){connectionState=-2;grantExpires=0;grantConsumed=true;}

    private static boolean sameItem(Item a,Item b){return a!=null&&b!=null&&a.enabled==b.enabled&&a.server.equals(b.server)&&a.address.equals(b.address)&&a.key().equals(b.key());}
    private static boolean currentItem(Item item){return item.enabled&&sameItem(item,registry.get(item.address));}

    private static synchronized void requestCatalog(boolean connection,long generation){
        // A join always gets a new request. Browse polls are coalesced/backed off.
        if(!connection&&(catalogLoading||clock()<catalogNext))return;
        final long request=++catalogRequest;
        catalogLoading=true;catalogNext=clock()+5000;
        CATALOG_WORK.execute(()->{
            Map<String,Item> loaded=null;long maxAge=60000;
            try{
                JSONObject body=new JSONObject(new String(readJson(new URL(CATALOG),65536),StandardCharsets.UTF_8));
                if(body.getInt("schema")!=1)throw new IOException("schema");
                int seconds=body.getInt("max_age_seconds");if(seconds<1||seconds>60)throw new IOException("age");maxAge=seconds*1000L;
                JSONArray entries=body.getJSONArray("servers");if(entries.length()>2)throw new IOException("servers");
                Map<String,Item> values=new LinkedHashMap<>();Set<String> slots=new HashSet<>();
                for(int i=0;i<entries.length();i++){
                    JSONObject row=entries.getJSONObject(i);String server=row.getString("server_id");
                    if(!(server.equals("survival")||server.equals("escape"))||!slots.add(server))throw new IOException("slot");
                    String original=row.getString("address"),address=endpoint(original);
                    if(!original.isEmpty()&&address.isEmpty())throw new IOException("address");
                    boolean enabled=row.getBoolean("resources_enabled");
                    String pack="",revision="",manifest="",hash="";long bytes=0;
                    if(enabled){
                        pack=row.getString("pack_id");revision=row.getString("revision");manifest=row.getString("manifest_url");
                        hash=row.getString("manifest_sha256");bytes=row.getLong("download_bytes");
                        if(address.isEmpty()||!id(pack)||!id(revision)||!sha(hash)||bytes<1||bytes>ServerResourceStore.MAX_TOTAL+(64L<<20))throw new IOException("catalog");
                        resourceUrl(manifest,pack,revision,"manifest.json");
                    }
                    if(!address.isEmpty()&&values.put(address,new Item(server,address,enabled,pack,revision,manifest,hash,bytes))!=null)throw new IOException("address");
                }
                loaded=Collections.unmodifiableMap(values);
            }catch(Exception ignored){}
            Item check=null;
            synchronized(ServerResources.class){
                if(loaded!=null){applyRegistry(loaded,maxAge);}
                if(request==catalogRequest)catalogLoading=false;
                if(connection&&generation==connectionGeneration){
                    if(loaded==null){Item old=registry.get(connectionAddress);connectionState=old!=null&&old.enabled?-1:0;}
                    else{
                        connectionItem=loaded.get(connectionAddress);
                        if(connectionItem==null||!connectionItem.enabled)connectionState=0;
                        else{connectionState=2;check=connectionItem;}
                    }
                }
            }
            if(check!=null)inspect(check,false);
        });
    }

    private static byte[] readJson(URL url,int maximum) throws IOException {
        if(!"https".equals(url.getProtocol())||!"kontrafps.ru".equals(url.getHost())||url.getUserInfo()!=null||url.getRef()!=null||url.getQuery()!=null||!(url.getPort()==-1||url.getPort()==443))throw new IOException("origin");
        HttpURLConnection conn=(HttpURLConnection)url.openConnection();
        try{
            conn.setConnectTimeout(12000);conn.setReadTimeout(20000);conn.setInstanceFollowRedirects(false);conn.setUseCaches(false);
            conn.setRequestProperty("Accept-Encoding","identity");
            if(conn.getResponseCode()!=200)throw new IOException("network");
            String length=conn.getHeaderField("Content-Length");
            if(length!=null){try{long n=Long.parseLong(length);if(n<0||n>maximum)throw new IOException("size");}catch(NumberFormatException e){throw new IOException("size",e);}}
            String encoding=conn.getContentEncoding();if(encoding!=null&&!encoding.equalsIgnoreCase("identity"))throw new IOException("encoding");
            try(InputStream in=conn.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()){
                byte[] buffer=new byte[16384];int count;
                while((count=in.read(buffer))!=-1){if(count==0)continue;if(out.size()>maximum-count)throw new IOException("size");out.write(buffer,0,count);}
                return out.toByteArray();
            }
        }finally{conn.disconnect();}
    }

    private static URL resourceUrl(String value,String pack,String revision,String suffix) throws IOException {
        URL url=ServerResourceStore.assetUrl(value);
        if(!url.getPath().equals("/server-resources/"+pack+"/"+revision+"/"+suffix))throw new IOException("url");
        return url;
    }

    private static String digest(byte[] bytes) throws Exception {
        byte[] hash=MessageDigest.getInstance("SHA-256").digest(bytes);StringBuilder out=new StringBuilder(64);
        for(byte b:hash)out.append(String.format(Locale.ROOT,"%02x",b&255));return out.toString();
    }

    private static Manifest loadManifest(Item item) throws Exception {
        byte[] bytes=readJson(resourceUrl(item.manifest,item.pack,item.revision,"manifest.json"),8<<20);
        if(!digest(bytes).equals(item.hash))throw new IOException("manifest_hash");
        JSONObject data=new JSONObject(new String(bytes,StandardCharsets.UTF_8));
        if(data.getInt("schema")!=1||!item.pack.equals(data.getString("pack_id"))||!item.revision.equals(data.getString("revision")))throw new IOException("manifest_identity");
        JSONArray list=data.getJSONArray("files");if(list.length()<1||list.length()>ServerResourceStore.MAX_FILES)throw new IOException("file_count");
        Set<String> paths=new HashSet<>();List<Asset> assets=new ArrayList<>();long total=0;
        for(int i=0;i<list.length();i++){
            JSONObject row=list.getJSONObject(i);String path=row.getString("path"),hash=row.getString("sha256");long size=row.getLong("size");
            if(!ServerResourceStore.safePath(path)||!ServerResourceStore.allowedAsset(path)||!paths.add(path.toLowerCase(Locale.ROOT))||!sha(hash)||size<1||size>ServerResourceStore.MAX_FILE||total>ServerResourceStore.MAX_TOTAL-size)throw new IOException("file");
            String url=row.getString("url");resourceUrl(url,item.pack,item.revision,"files/"+hash);
            assets.add(new Asset(new ServerResourceStore.Entry(path,size,hash),url));total+=size;
        }
        if(data.getLong("total_bytes")!=total)throw new IOException("total");
        String archiveUrl="",archiveHash="";long archiveBytes=0;
        if(data.has("archive")&&!data.isNull("archive")){
            JSONObject archive=data.getJSONObject("archive");archiveUrl=archive.getString("url");archiveHash=archive.getString("sha256");archiveBytes=archive.getLong("size");
            if(!sha(archiveHash)||archiveBytes<1||archiveBytes>ServerResourceStore.MAX_TOTAL+(64L<<20))throw new IOException("archive");
            resourceUrl(archiveUrl,item.pack,item.revision,"bundle.zip");
        }
        if(archiveBytes!=item.bytes)throw new IOException("archive_size");
        return new Manifest(assets,total,archiveBytes,archiveUrl,archiveHash);
    }

    private static File root() throws IOException {
        Context ctx=context();if(ctx==null)throw new IOException("context");
        // Android reports files under /data/user/0, a link to /data/data: start from the real folder.
        File root=new File(ctx.getFilesDir().getCanonicalFile(),"server-resources");
        if(!root.exists()&&!root.mkdirs())throw new IOException("storage");
        if(!root.getCanonicalFile().equals(root.getAbsoluteFile()))throw new IOException("path");
        return root;
    }
    private static File revision(Item item) throws IOException {
        if(!id(item.pack)||!id(item.revision))throw new IOException("identity");
        return child(root(),item.pack+"/"+item.revision);
    }
    private static File files(Item item) throws IOException {return child(revision(item),"files");}
    private static File child(File parent,String path) throws IOException {
        File result=new File(parent,path);String root=parent.getCanonicalPath()+File.separator;
        if(!result.getCanonicalPath().startsWith(root)||!result.getCanonicalFile().equals(result.getAbsoluteFile()))throw new IOException("path");
        return result;
    }
    private static void mkdir(File dir) throws IOException {if(!dir.isDirectory()&&!dir.mkdirs())throw new IOException("storage");}

    /** Revisions are immutable even if a faulty publisher reuses a name. */
    private static File bindRevision(Item item) throws IOException {
        File directory=revision(item);mkdir(directory);File marker=child(directory,"manifest.sha256");
        if(marker.exists()){
            if(marker.length()!=64)throw new IOException("revision_reused");
            byte[] bytes=new byte[64];try(InputStream in=new java.io.FileInputStream(marker)){int offset=0,n;while(offset<64&&(n=in.read(bytes,offset,64-offset))!=-1)offset+=n;if(offset!=64)throw new IOException("revision_reused");}
            if(!new String(bytes,StandardCharsets.US_ASCII).equals(item.hash))throw new IOException("revision_reused");
        }else{
            File temporary=child(directory,"manifest.tmp");
            try(FileOutputStream out=new FileOutputStream(temporary)){out.write(item.hash.getBytes(StandardCharsets.US_ASCII));out.getFD().sync();}
            if(!temporary.renameTo(marker))throw new IOException("storage");
        }
        return directory;
    }

    private static synchronized Pack pack(Item item){
        Pack value=packs.get(item.key());if(value==null){value=new Pack(item);packs.put(item.key(),value);}return value;
    }

    private static void inspect(Item item,boolean full){
        final Pack pack;final int serial;
        synchronized(ServerResources.class){
            pack=pack(item);if(pack.working)return;
            pack.working=true;pack.state=CHECKING;pack.error="";serial=++pack.operation;
        }
        FILE_WORK.execute(()->{
            try{
                Manifest manifest=loadManifest(item);bindRevision(item);File directory=files(item);long missing=0,network=0;int available=0;
                boolean quick;
                synchronized(ServerResources.class){quick=pack.verified&&!full;}
                Operation control=new Operation(pack,serial);
                for(Asset asset:manifest.assets){
                    control.check();File file=child(directory,asset.file.path);
                    boolean valid=quick?file.isFile()&&file.length()==asset.file.size:ServerResourceStore.verify(file,asset.file.size,asset.file.sha256,control);
                    if(!valid){
                        missing+=asset.file.size;File staged=child(child(revision(item),"incoming"),asset.file.path);
                        if(ServerResourceStore.verify(staged,asset.file.size,asset.file.sha256,control)||findReusable(item,directory,asset,control)!=null)available++;
                        else network+=asset.file.size;
                    }else available++;
                }
                long expected=available==0&&!manifest.archiveUrl.isEmpty()&&manifest.archiveBytes<=network+Math.max(1L<<20,network/20)?manifest.archiveBytes:network;
                synchronized(ServerResources.class){
                    if(pack.operation==serial){pack.manifest=manifest;pack.missing=expected;pack.done=0;pack.total=expected;pack.canonicalPath=directory.getCanonicalPath();
                        pack.verified=missing==0;pack.state=missing==0?READY:MISSING;pack.error="";}
                }
            }catch(Exception e){fail(pack,serial,e);}
            finally{
                synchronized(ServerResources.class){if(pack.operation==serial){pack.working=false;updateConnection(item);}}
            }
        });
    }

    private static void updateConnection(Item item){
        if(connectionState<0||connectionItem==null||!connectionItem.key().equals(item.key())||!connectionItem.address.equals(item.address))return;
        if(!currentItem(item)||clock()-catalogAt>=catalogMaxAge){connectionState=2;grantExpires=0;return;}
        if(clearing.contains(item.pack)||deleting.contains(item.pack+"/"+item.revision)){connectionState=3;grantExpires=0;return;}
        Pack pack=packs.get(item.key());if(pack==null){connectionState=2;return;}
        if(pack.working){connectionState=2;return;}
        if(READY.equals(pack.state)&&pack.verified){
            if(connectionState!=1){grantConsumed=false;grantExpires=Math.min(clock()+60000,catalogAt+catalogMaxAge);}
            connectionState=1;
        }else if(ERROR.equals(pack.state))connectionState=-1;
        else connectionState=3;
    }

    private static synchronized void fail(Pack pack,int serial,Exception failure){
        if(pack.operation!=serial)return;
        pack.verified=false;pack.state=failure instanceof Stopped?PAUSED:ERROR;
        String message=failure.getMessage();pack.error=message==null?"network":message;
    }

    private static boolean mobileAllowed(){Context c=context();return c!=null&&c.getSharedPreferences("server-resources",0).getBoolean("mobile",false);}
    private static boolean metered(){
        Context c=context();if(c==null)return true;
        ConnectivityManager manager=(ConnectivityManager)c.getSystemService(Context.CONNECTIVITY_SERVICE);
        try{return manager==null||manager.isActiveNetworkMetered();}catch(SecurityException e){return true;}
    }

    private static void download(String address){
        final Item item;final Pack pack;final Operation operation;
        synchronized(ServerResources.class){
            item=registry.get(endpoint(address));
            if(item==null||!item.enabled||clock()-catalogAt>=catalogMaxAge){requestCatalog(false,0);return;}
            pack=pack(item);
            if(pack.working||active!=null||clearing.contains(item.pack))return;
            if(item.key().equals(mountedKey)){pack.error="in_use";return;}
            if(metered()&&!mobileAllowed()){pack.error="mobile";return;}
            pack.working=true;pack.state=DOWNLOADING;pack.error="";pack.verified=false;
            operation=new Operation(pack,++pack.operation);active=operation;
        }
        FILE_WORK.execute(()->{
            try{
                // A new immutable revision is selected only after this fresh catalog read.
                Item current=freshItem(item.address);
                if(current==null||!current.enabled||!current.key().equals(item.key()))throw new IOException("revision_changed");
                Manifest manifest=loadManifest(item);File revision=bindRevision(item);
                File staging=child(revision,"incoming");mkdir(staging);File installed=files(item);
                long remaining=0,stagedBytes=0;int reused=0;
                List<Asset> missing=new ArrayList<>();
                Map<Asset,File> copies=new LinkedHashMap<>();
                for(Asset asset:manifest.assets){
                    operation.check();File target=child(staging,asset.file.path);
                    if(ServerResourceStore.verify(target,asset.file.size,asset.file.sha256,operation)){reused++;stagedBytes+=asset.file.size;continue;}
                    File source=findReusable(item,installed,asset,operation);
                    if(source!=null){copies.put(asset,source);reused++;}
                    else{missing.add(asset);remaining+=asset.file.size;}
                }
                boolean archive=reused==0&&!manifest.archiveUrl.isEmpty()&&manifest.archiveBytes<=remaining+Math.max(1L<<20,remaining/20);
                long network=archive?manifest.archiveBytes:remaining;
                long needed=manifest.total-stagedBytes+RESERVE+(archive?manifest.archiveBytes:0);
                if(root().getUsableSpace()<needed)throw new IOException("space");
                for(Map.Entry<Asset,File> copy:copies.entrySet()){
                    operation.check();Asset asset=copy.getKey();
                    ServerResourceStore.copyVerified(copy.getValue(),child(staging,asset.file.path),asset.file.size,asset.file.sha256,operation);
                }
                synchronized(ServerResources.class){pack.manifest=manifest;pack.total=network;pack.done=0;pack.missing=remaining;}
                operation.expected=network;
                if(archive&&remaining>0){
                    File part=child(revision,"bundle-"+manifest.archiveHash+".part");
                    operation.network=true;
                    try{ServerResourceStore.download(resourceUrl(manifest.archiveUrl,item.pack,item.revision,"bundle.zip"),part,manifest.archiveBytes,manifest.archiveHash,operation);}
                    finally{operation.network=false;}
                    File extracted=child(revision,"extracting");ServerResourceStore.deleteTree(extracted);
                    List<ServerResourceStore.Entry> entries=new ArrayList<>();for(Asset a:manifest.assets)entries.add(a.file);
                    ServerResourceStore.extractZip(part,extracted,entries,operation);
                    ServerResourceStore.deleteTree(staging);if(!extracted.renameTo(staging))throw new IOException("storage");
                }else{
                    File parts=child(revision,"parts");mkdir(parts);long completed=0;
                    for(Asset asset:missing){
                        operation.check();operation.base=completed;
                        File part=child(parts,asset.file.sha256+".part");
                        operation.network=true;
                        try{ServerResourceStore.download(resourceUrl(asset.url,item.pack,item.revision,"files/"+asset.file.sha256),part,asset.file.size,asset.file.sha256,operation);}
                        finally{operation.network=false;}
                        File target=child(staging,asset.file.path);mkdir(target.getParentFile());
                        if(target.exists()&&!target.delete())throw new IOException("storage");
                        if(!part.renameTo(target))throw new IOException("storage");completed+=asset.file.size;
                    }
                }
                operation.check();
                for(Asset asset:manifest.assets){
                    operation.check();File checked=child(staging,asset.file.path);
                    if(!ServerResourceStore.verify(checked,asset.file.size,asset.file.sha256,operation)||!ServerResourceStore.validFormat(checked,asset.file.path))throw new IOException("file_hash");
                }
                assertTree(staging,manifest,operation);
                // A pack revoked or replaced during a long transfer must never gain a mount permit.
                Item latest=freshItem(item.address);
                if(latest==null||!latest.enabled||!latest.key().equals(item.key()))throw new IOException("revision_changed");
                File previous=child(revision,"previous");ServerResourceStore.deleteTree(previous);
                if(installed.exists()&&!installed.renameTo(previous))throw new IOException("storage");
                if(!staging.renameTo(installed)){if(previous.exists())previous.renameTo(installed);throw new IOException("storage");}
                ServerResourceStore.deleteTree(previous);ServerResourceStore.deleteTree(child(revision,"parts"));
                File[] leftovers=revision.listFiles();if(leftovers!=null)for(File f:leftovers)if(f.getName().startsWith("bundle-")&&f.getName().endsWith(".part"))f.delete();
                prune(item);
                synchronized(ServerResources.class){if(pack.operation==operation.serial){pack.manifest=manifest;pack.verified=true;pack.canonicalPath=installed.getCanonicalPath();pack.missing=0;pack.done=network;pack.total=network;pack.state=READY;pack.error="";}}
            }catch(Exception e){fail(pack,operation.serial,operation.cancelled?new Stopped():e);}
            finally{
                synchronized(ServerResources.class){
                    if(active==operation)active=null;
                    if(pack.operation==operation.serial){pack.working=false;updateConnection(item);}
                }
            }
        });
    }

    private static Item freshItem(String address) throws Exception {
        // Serialize catalog snapshots with browse/join refreshes: a slow old GET
        // must not overwrite a newer worker revalidation from another thread.
        return CATALOG_WORK.submit(()->freshItemDirect(address)).get();
    }

    private static Item freshItemDirect(String address) throws Exception {
        // File worker may wait on this network call, but the game/UI thread never does.
        JSONObject body=new JSONObject(new String(readJson(new URL(CATALOG),65536),StandardCharsets.UTF_8));
        if(body.getInt("schema")!=1)throw new IOException("schema");
        int age=body.getInt("max_age_seconds");if(age<1||age>60)throw new IOException("age");
        JSONArray rows=body.getJSONArray("servers");if(rows.length()>2)throw new IOException("servers");
        Item result=null;Set<String> ids=new HashSet<>();Map<String,Item> values=new LinkedHashMap<>();
        for(int i=0;i<rows.length();i++){
            JSONObject row=rows.getJSONObject(i);String server=row.getString("server_id");
            if(!(server.equals("survival")||server.equals("escape"))||!ids.add(server))throw new IOException("slot");
            String original=row.getString("address"),key=endpoint(original);
            if(!original.isEmpty()&&key.isEmpty())throw new IOException("address");
            boolean enabled=row.getBoolean("resources_enabled");String pack="",revision="",manifest="",hash="";long size=0;
            if(enabled){
                pack=row.getString("pack_id");revision=row.getString("revision");manifest=row.getString("manifest_url");hash=row.getString("manifest_sha256");size=row.getLong("download_bytes");
                if(key.isEmpty()||!id(pack)||!id(revision)||!sha(hash)||size<1||size>ServerResourceStore.MAX_TOTAL+(64L<<20))throw new IOException("catalog");
                resourceUrl(manifest,pack,revision,"manifest.json");
            }
            Item item=new Item(server,key,enabled,pack,revision,manifest,hash,size);
            if(!key.isEmpty()&&values.put(key,item)!=null)throw new IOException("address");
            if(key.equals(address))result=item;
        }
        synchronized(ServerResources.class){applyRegistry(Collections.unmodifiableMap(values),age*1000L);}
        return result;
    }

    private static void applyRegistry(Map<String,Item> values,long maxAge){
        registry=values;catalogAt=clock();catalogMaxAge=maxAge;catalogNext=catalogAt+maxAge;
        if(active!=null&&!currentItem(active.pack.item)){active.cancelled=true;active.pack.state=PAUSED;}
    }

    private static File findReusable(Item item,File installed,Asset asset,Operation control) throws IOException {
        File candidate=child(installed,asset.file.path);
        if(ServerResourceStore.verify(candidate,asset.file.size,asset.file.sha256,control))return candidate;
        File packRoot=child(root(),item.pack);File[] revisions=packRoot.listFiles();int checked=0;
        if(revisions!=null)for(File rev:revisions){
            control.check();if(++checked>64)break;
            if(!rev.isDirectory()||!id(rev.getName())||rev.getName().equals(item.revision))continue;
            File source=child(child(rev,"files"),asset.file.path);
            if(ServerResourceStore.verify(source,asset.file.size,asset.file.sha256,control))return source;
        }
        return null;
    }

    private static void assertTree(File directory,Manifest manifest,Operation operation) throws IOException {
        Set<String> expected=new HashSet<>();for(Asset asset:manifest.assets)expected.add(asset.file.path);
        assertTreeAt(directory,directory,"",expected,operation,0);
    }
    private static void assertTreeAt(File root,File directory,String prefix,Set<String> expected,Operation operation,int depth) throws IOException {
        operation.check();if(depth>8)throw new IOException("path");
        if(!directory.getCanonicalFile().equals(directory.getAbsoluteFile()))throw new IOException("path");
        File[] entries=directory.listFiles();if(entries==null)throw new IOException("storage");
        for(File entry:entries){
            operation.check();String name=prefix+entry.getName();
            if(!entry.getCanonicalFile().equals(entry.getAbsoluteFile()))throw new IOException("path");
            if(entry.isDirectory())assertTreeAt(root,entry,name+"/",expected,operation,depth+1);
            else if(!entry.isFile()||!expected.contains(name))throw new IOException("extra_file");
        }
    }

    /** Retain configured/mounted revisions and one previous unreferenced revision. */
    private static void prune(Item current) throws IOException {
        File directory=child(root(),current.pack);File[] revisions=directory.listFiles();if(revisions==null)return;
        Arrays.sort(revisions,(a,b)->Long.compare(b.lastModified(),a.lastModified()));int previous=0;
        for(File revision:revisions){
            if(!revision.isDirectory()||!id(revision.getName())||revision.getName().equals(current.revision))continue;
            String key=current.pack+"/"+revision.getName();boolean referenced=false;
            synchronized(ServerResources.class){
                if(mountedKey.startsWith(key+"/"))referenced=true;
                for(Item item:registry.values())if(item.enabled&&item.pack.equals(current.pack)&&item.revision.equals(revision.getName()))referenced=true;
                if(referenced||previous++==0)continue;
                deleting.add(key);
                for(Pack p:packs.values())if(p.item.pack.equals(current.pack)&&p.item.revision.equals(revision.getName())){p.verified=false;p.state=MISSING;}
            }
            try{ServerResourceStore.deleteTree(child(directory,revision.getName()));}
            finally{synchronized(ServerResources.class){deleting.remove(key);}}
        }
    }

    private static synchronized void pause(String address){
        Item item=registry.get(endpoint(address));
        if(active!=null&&item!=null&&active.pack.item.key().equals(item.key())){active.cancelled=true;active.pack.state=PAUSED;active.pack.error="";}
        if(endpoint(address).equals(connectionAddress))cancelConnection();
    }

    private static void clear(String address){
        final Item item;final Pack pack;final int serial;
        synchronized(ServerResources.class){
            item=registry.get(endpoint(address));if(item==null||!item.enabled)return;
            pack=pack(item);if(mountedKey.startsWith(item.pack+"/")){pack.error="in_use";return;}
            if(clearing.contains(item.pack))return;
            clearing.add(item.pack);
            if(active!=null&&active.pack.item.pack.equals(item.pack))active.cancelled=true;
            for(Pack existing:packs.values())if(existing.item.pack.equals(item.pack)){
                existing.operation++;existing.working=true;existing.verified=false;existing.state=CLEARING;existing.error="";
            }
            serial=pack.operation;
            if(connectionItem!=null&&item.pack.equals(connectionItem.pack))cancelConnection();
        }
        FILE_WORK.execute(()->{
            try{ServerResourceStore.deleteTree(child(root(),item.pack));
                synchronized(ServerResources.class){for(Pack p:packs.values())if(p.item.pack.equals(item.pack)){p.verified=false;p.state=MISSING;p.missing=p.manifest==null?0:p.manifest.total;}}
            }catch(Exception e){fail(pack,serial,e);}
            finally{synchronized(ServerResources.class){clearing.remove(item.pack);for(Pack p:packs.values())if(p.item.pack.equals(item.pack))p.working=false;}}
        });
    }

    private static String bytes(long bytes){
        if(bytes<1024)return bytes+" B";
        if(bytes<(1L<<20))return String.format(Locale.ROOT,"%.1f KB",bytes/1024d);
        if(bytes<(1L<<30))return String.format(Locale.ROOT,"%.1f MB",bytes/(double)(1L<<20));
        return String.format(Locale.ROOT,"%.2f GB",bytes/(double)(1L<<30));
    }
    private static String error(String key,boolean ru){
        if(key.equals("mobile"))return ru?"Для мобильной сети включите разрешение ниже.":"Allow mobile data below to continue.";
        if(key.equals("space"))return ru?"Недостаточно свободного места. Освободите память и продолжите.":"Not enough free space. Free storage and resume.";
        if(key.equals("in_use"))return ru?"Сначала отключитесь от сервера: этот набор используется.":"Disconnect from the server first: this pack is in use.";
        if(key.equals("revision_changed"))return ru?"Набор обновился. Обновите сведения и скачайте актуальные файлы.":"The pack changed. Refresh and download the current revision.";
        if(key.equals("revision_reused"))return ru?"У набора изменился манифест без новой ревизии. Обратитесь к администратору.":"The manifest changed without a new revision. Contact the administrator.";
        return ru?"Не удалось проверить или скачать файлы. Проверьте сеть и повторите.":"Could not verify or download files. Check the connection and retry.";
    }

    static void show(String address,boolean ru){
        String key=endpoint(address);if(key.isEmpty())return;
        Context ctx=context();if(!(ctx instanceof Activity))return;Activity activity=(Activity)ctx;
        activity.runOnUiThread(()->{
            if(activity.isFinishing())return;
            if(editor!=null&&editor.isShowing()){
                if(editorAddress.equals(key))return;
                editor.dismiss();editor=null;
            }
            CzmDialog dialog=new CzmDialog(activity,ru?"Ресурсы сервера":"Server resources",address,
                ru?"Скачать":"Download",ru?"Закрыть":"Close",ru,false);editor=dialog;editorAddress=key;
            TextView status=dialog.note(ru?"Проверяем каталог…":"Checking catalog…");
            TextView volume=dialog.note("");
            ProgressBar progress=new ProgressBar(activity,null,android.R.attr.progressBarStyleHorizontal);
            progress.setMax(1000);dialog.body.addView(progress,new android.widget.LinearLayout.LayoutParams(-1,CzmDialog.dp(activity,12)));
            CheckBox mobile=new CheckBox(activity);mobile.setText(ru?"Разрешить загрузку через мобильную сеть":"Allow downloads using mobile data");
            mobile.setTextColor(CzmDialog.MUTED);mobile.setTextSize(12);mobile.setChecked(mobileAllowed());dialog.body.addView(mobile);
            mobile.setOnCheckedChangeListener((button,checked)->activity.getSharedPreferences("server-resources",0).edit().putBoolean("mobile",checked).apply());
            Button verify=dialog.link(ru?"Проверить файлы":"Verify files",v->{Item item; synchronized(ServerResources.class){item=registry.get(key);}if(item!=null&&item.enabled)inspect(item,true);});
            Button clear=dialog.link(ru?"Очистить кэш этого набора":"Clear this pack's cache",v->{
                CzmDialog confirm=new CzmDialog(activity,ru?"Очистить ресурсы?":"Clear resources?",ru?"Файлы клиента и настройки сохранятся":"Your game files and settings remain",ru?"Очистить":"Clear",ru?"Отмена":"Cancel",ru,false);
                confirm.submit.setOnClickListener(b->{confirm.dismiss();clear(address);});confirm.show();
            });
            Button cancel=dialog.link(ru?"Отменить загрузку":"Cancel download",v->pause(address));
            Button refresh=dialog.link(ru?"Обновить сведения":"Refresh details",v->{synchronized(ServerResources.class){catalogNext=0;requestCatalog(false,0);}pollPack(address,false);});
            dialog.submit.setOnClickListener(v->download(address));
            final Runnable[] tick=new Runnable[1];
            final String[] shownError={""};   // fail() scrolls to the top: only when the message changes
            tick[0]=()->{
                if(!dialog.isShowing())return;
                Item item;Pack pack;boolean loading;
                synchronized(ServerResources.class){if(clock()-catalogAt>=catalogMaxAge)requestCatalog(false,0);item=registry.get(key);pack=item!=null&&item.enabled?packs.get(item.key()):null;loading=catalogLoading;}
                if(item==null){status.setText(loading?(ru?"Проверяем каталог…":"Checking catalog…"):(ru?"У этого сервера нет управляемого набора":"No managed pack for this server"));volume.setText("");}
                else if(!item.enabled){status.setText(ru?"Ресурсы ещё не опубликованы":"Resources have not been published yet");volume.setText(ru?"Обычное подключение доступно":"You can connect normally");}
                else if(pack==null){status.setText(ru?"Проверяем файлы…":"Checking files…");volume.setText(bytes(item.bytes));pollPack(address,false);}
                else{
                    String state;long done,total,missing;String failure;boolean working;
                    synchronized(ServerResources.class){state=pack.state;done=pack.done;total=pack.total;missing=pack.missing;failure=pack.error;working=pack.working;}
                    String text=ru?"Нужно скачать ресурсы":"Resources need downloading";
                    if(CHECKING.equals(state))text=ru?"Проверяем файлы…":"Checking files…";
                    else if(READY.equals(state))text=ru?"Ресурсы проверены и готовы":"Resources verified and ready";
                    else if(DOWNLOADING.equals(state))text=ru?"Скачиваем и проверяем…":"Downloading and verifying…";
                    else if(PAUSED.equals(state))text=ru?"Загрузка приостановлена":"Download paused";
                    else if(CLEARING.equals(state))text=ru?"Очищаем кэш…":"Clearing cache…";
                    else if(ERROR.equals(state))text=ru?"Нужна повторная попытка":"Please retry";
                    status.setText(text);
                    volume.setText(DOWNLOADING.equals(state)?bytes(done)+" / "+bytes(total):
                        (READY.equals(state)?(ru?"На устройстве: ":"On device: ")+bytes(pack.manifest==null?0:pack.manifest.total):
                        (ru?"Скачать: ":"Download: ")+bytes(missing)+(pack.manifest==null?"":(ru?" · после распаковки: ":" · unpacked: ")+bytes(pack.manifest.total))));
                    progress.setIndeterminate(CHECKING.equals(state)||CLEARING.equals(state));
                    progress.setProgress(total>0?(int)Math.min(1000,done*1000/total):0);
                    dialog.submit.setText(PAUSED.equals(state)?(ru?"Продолжить":"Resume"):ERROR.equals(state)?(ru?"Повторить":"Retry"):(ru?"Скачать / исправить":"Download / repair"));
                    String message=failure.isEmpty()?"":error(failure,ru);
                    if(!message.equals(shownError[0])){shownError[0]=message;if(message.isEmpty())dialog.error.setVisibility(View.GONE);else dialog.fail(message);}
                    dialog.submit.setEnabled(!working&&!READY.equals(state));verify.setEnabled(!working);clear.setEnabled(!CLEARING.equals(state));cancel.setEnabled(DOWNLOADING.equals(state));
                }
                if(item==null||!item.enabled||pack==null){dialog.submit.setEnabled(false);verify.setEnabled(false);clear.setEnabled(false);cancel.setEnabled(false);progress.setIndeterminate(loading||item!=null&&item.enabled);}
                UI.postDelayed(tick[0],400);
            };
            dialog.setOnDismissListener(d->{
                UI.removeCallbacks(tick[0]);synchronized(ServerResources.class){
                    if(editor==dialog){editor=null;editorAddress="";}
                    if(key.equals(connectionAddress)&&connectionState>=2)cancelConnection();
                }
            });
            dialog.show();pollPack(address,false);tick[0].run();
        });
    }

    private static void pollPack(String address,boolean full){
        Item item;
        synchronized(ServerResources.class){
            if(clock()-catalogAt>=catalogMaxAge){requestCatalog(false,0);return;}
            item=registry.get(endpoint(address));
            if(item==null||!item.enabled)return;
            Pack existing=packs.get(item.key());if(existing!=null&&!full)return;
        }
        inspect(item,full);
    }
}
