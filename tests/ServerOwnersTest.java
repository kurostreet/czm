package ru.kurostreet.counterzombiemobile;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executor;

public final class ServerOwnersTest {
    static void check(boolean value){if(!value)throw new AssertionError();}
    static final class Worker implements Executor {
        final ArrayDeque<Runnable> pending=new ArrayDeque<>();
        public void execute(Runnable work){pending.add(work);}
        void run(){check(pending.size()==1);pending.remove().run();}
    }
    public static void main(String[] args){
        long[] time={1};boolean[] fail={false};Worker work=new Worker();
        String address="203.0.113.5:27015";
        Map<String,Integer> remote=new HashMap<>();
        ServerOwners owners=new ServerOwners(()->time[0],work,()->{
            if(fail[0])throw new java.io.IOException("offline");
            return new HashMap<>(remote);
        });
        for(int i=0;i<100;i++)check(owners.owner(address)==0);
        remote.put(ServerPolicy.endpoint(address),42);work.run();
        check(owners.owner(address)==42&&owners.owner("203.000.113.005:27015")==42);
        check(owners.owner("example.com:27015")==0&&owners.owner("203.0.113.5:27016")==0);
        for(int i=0;i<100;i++)check(owners.owner(address)==42);
        check(work.pending.isEmpty());
        time[0]+=15001;owners.revision();remote.clear();work.run();check(owners.owner(address)==0);
        remote.put(ServerPolicy.endpoint(address),55);owners.invalidate();work.run();check(owners.owner(address)==55);
        // An expired association disappears during an outage, without blocking any connection.
        fail[0]=true;time[0]+=60001;check(owners.owner(address)==0);work.run();
        for(int i=0;i<100;i++)check(owners.owner(address)==0);check(work.pending.isEmpty());
        fail[0]=false;time[0]+=5001;owners.revision();work.run();check(owners.owner(address)==55);
        // A completed request cannot restore the old association after a local removal.
        time[0]+=15001;owners.revision();owners.invalidate();work.run();
        check(owners.owner(address)==0);remote.clear();work.run();check(owners.owner(address)==0);
        System.out.println("SERVER_OWNERS_OK");
    }
}
