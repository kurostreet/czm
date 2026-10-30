/* Public, short-lived server owner associations. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

final class ServerOwners {
    interface Clock { long now(); }
    interface Loader { Map<String,Integer> load() throws Exception; }
    static final ServerOwners INSTANCE = new ServerOwners(() -> System.nanoTime()/1000000L,
        Executors.newSingleThreadExecutor(), ServerOwners::download);
    private final Clock clock; private final Executor executor; private final Loader loader;
    private Map<String,Integer> owners=Collections.emptyMap();
    private long attemptAt,successAt,retryAt,generation;
    private int revision; private boolean busy,loaded;
    ServerOwners(Clock c,Executor e,Loader l){clock=c;executor=e;loader=l;}
    synchronized int owner(String address){
        refresh();
        if(!loaded||clock.now()-successAt>=60000)return 0;
        Integer id=owners.get(ServerPolicy.endpoint(address));return id==null?0:id;
    }
    synchronized int revision(){refresh();return revision;}
    synchronized void invalidate(){generation++;loaded=false;retryAt=0;revision++;refresh();}
    private synchronized void refresh(){
        long time=clock.now();
        if(busy||time<retryAt||(loaded&&retryAt==0&&time-attemptAt<15000))return;
        busy=true;attemptAt=time;final long requested=generation;
        executor.execute(() -> {
            try{
                Map<String,Integer> snapshot=Collections.unmodifiableMap(new HashMap<>(loader.load()));
                synchronized(ServerOwners.this){
                    if(requested==generation){
                        if(!loaded||!snapshot.equals(owners))revision++;
                        owners=snapshot;loaded=true;successAt=clock.now();retryAt=0;
                    }
                }
            }catch(Exception ignored){synchronized(ServerOwners.this){if(requested==generation)retryAt=clock.now()+5000;}}
            finally{synchronized(ServerOwners.this){busy=false;}}
        });
    }
    private static Map<String,Integer> download() throws Exception{
        HttpURLConnection connection=(HttpURLConnection)new URL("https://counter-zombie.ru/api/v1/servers/owners").openConnection();
        try{
            connection.setConnectTimeout(8000);connection.setReadTimeout(8000);
            connection.setUseCaches(false);connection.setInstanceFollowRedirects(false);
            if(connection.getResponseCode()!=200)throw new java.io.IOException("owners");
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try(InputStream input=connection.getInputStream()){
                byte[] buffer=new byte[8192];int size;
                while((size=input.read(buffer))!=-1){if(bytes.size()+size>2097152)throw new java.io.IOException("owners size");bytes.write(buffer,0,size);}
            }
            JSONArray list=new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8)).getJSONArray("owners");
            Map<String,Integer> result=new HashMap<>();
            for(int i=0;i<list.length();i++){
                JSONObject row=list.getJSONObject(i);String endpoint=ServerPolicy.endpoint(row.getString("server"));int id=row.getInt("owner");
                if(endpoint.isEmpty()||id<=0)throw new java.io.IOException("owner entry");
                result.putIfAbsent(endpoint,id);
            }
            return result;
        }finally{connection.disconnect();}
    }
}
