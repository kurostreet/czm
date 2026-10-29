package ru.kurostreet.counterzombiemobile;

import java.util.ArrayDeque;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.Executor;

public final class ServerPolicyTest {
    static void check(boolean condition) { if (!condition) throw new AssertionError(); }
    static final class Worker implements Executor {
        final ArrayDeque<Runnable> work = new ArrayDeque<>();
        public void execute(Runnable task) { work.add(task); }
        void run() { check(work.size()==1); work.remove().run(); }
    }
    public static void main(String[] args) {
        final long[] time = {1}; final boolean[] fail = {false};
        final Set<String> remote = new HashSet<>(); Worker worker = new Worker();
        ServerPolicy p = new ServerPolicy(() -> time[0], worker, () -> {
            if (fail[0]) throw new java.io.IOException("offline");
            return new HashSet<>(remote);
        });
        String a="203.0.113.5:27015", b="203.0.113.5:27016";
        check(p.revision()==0); check(p.connectionState(a)==0); worker.run();
        check(p.revision()==1 && p.connectionState(a)==1);
        // A new connection cannot reuse an earlier successful policy fetch.
        p.beginConnection(); check(p.connectionState(a)==0);
        remote.add(ServerPolicy.endpoint(a)); worker.run();
        check(p.connectionState(a)==2 && p.connectionState(b)==1 && p.blocked(a));
        // Lifting restores access without rewriting favorites or restarting the game.
        remote.clear(); p.beginConnection(); check(p.connectionState(a)==0); worker.run();
        check(!p.blocked(a) && p.connectionState(a)==1);
        // Failure never turns an unchecked server into an allowed connection.
        fail[0]=true; p.beginConnection(); worker.run(); check(p.connectionState(a)==-1);
        for(int i=0;i<100;i++)check(p.connectionState(a)==-1);
        check(worker.work.isEmpty()); time[0]+=5001; fail[0]=false;
        check(p.connectionState(a)==0); worker.run(); check(p.connectionState(a)==1);
        // A force refresh that races a background request must wait for its own generation.
        time[0]+=30001; p.revision(); p.beginConnection(); worker.run();
        check(p.connectionState(a)==0); worker.run(); check(p.connectionState(a)==1);
        // Bounded freshness; stale success is not an indefinite offline bypass.
        time[0]+=60001; check(p.connectionState(a)==0); worker.run(); check(p.connectionState(a)==1);
        check(ServerPolicy.endpoint("[2001:db8::1]:27015").equals(ServerPolicy.endpoint("[2001:0db8:0:0:0:0:0:1]:27015")));
        check(ServerPolicy.endpoint("203.000.113.005:027015").isEmpty());
        check(ServerPolicy.endpoint("203.000.113.005:27015").equals(ServerPolicy.endpoint(a)));
        for(String bad:new String[]{"example.com:27015","bad:27015","1.2.3.4:0","1.2.3.4:65536","256.2.3.4:1",
            "127.1:27015","[fe80::1%wlan0]:1","203.0.113.5:27015;quit","http://1.2.3.4:1"})
            check(ServerPolicy.endpoint(bad).isEmpty());
        System.out.println("SERVER_POLICY_OK");
    }
}
