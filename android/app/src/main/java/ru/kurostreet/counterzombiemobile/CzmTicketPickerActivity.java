/* A narrow document-picker grant; no storage permission. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

public final class CzmTicketPickerActivity extends Activity {
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        if(saved!=null)return;
        String kind=getIntent().getStringExtra("kind");
        Intent pick=new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
            .setType("photo".equals(kind)?"image/*":"text/plain").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try{startActivityForResult(pick,1);}catch(Exception ignored){finish();}
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request==1&&result==RESULT_OK&&data!=null&&data.getData()!=null){
            CzmCommunity.selected(this,data.getData(),getIntent().getStringExtra("kind"),getIntent().getIntExtra("generation",-1));
        }else finish();
    }
}
