package ru.kurostreet.counterzombiemobile;

/** User intent, separate from a transient WebSocket. Caller holds its voice lock. */
final class CzmLobbyMicState {
    private boolean foreground,session,wanted,permissionPending;

    boolean foreground(){return foreground;}
    boolean wanted(){return wanted;}
    boolean canCapture(){return foreground&&session&&wanted;}
    void beginSession(){session=true;wanted=false;permissionPending=false;}
    void endSession(){session=false;wanted=false;permissionPending=false;}
    void foreground(boolean value){
        foreground=value;
        // A system permission dialog pauses SDL too. Preserve only that explicit
        // pending request, never an enabled microphone during a normal app pause.
        if(!value&&!permissionPending)wanted=false;
    }
    boolean request(boolean on,boolean permissionGranted){
        if(!on){wanted=false;permissionPending=false;return false;}
        if(!foreground||!session)return false;
        if(permissionGranted){wanted=true;permissionPending=false;return false;}
        if(permissionPending)return false;
        wanted=false;permissionPending=true;return true;
    }
    void permissionResult(boolean granted){
        if(!permissionPending||!session)return;
        permissionPending=false;wanted=granted;
    }
}
