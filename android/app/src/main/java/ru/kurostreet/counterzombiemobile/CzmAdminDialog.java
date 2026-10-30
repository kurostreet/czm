/* Responsive administration workspace: navigation, scrolling content, fixed actions. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.app.Dialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Build;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.ArrayList;

final class CzmAdminDialog extends Dialog {
    private static final int INK=Color.rgb(238,242,249),MUTED=Color.rgb(158,173,193),BASE=Color.rgb(19,27,39),EDGE=Color.rgb(48,62,82);
    final Activity activity;final LinearLayout body;final Button cancel,submit;final TextView error;
    private final LinearLayout root,nav,search;private final ScrollView scroll;
    private final TextView subtitle;private final Button close;
    private final boolean wide;
    private final ArrayList<Button> navigation=new ArrayList<>();
    interface Navigate {void open(String page);}
    private int dp(int value){return CzmDialog.dp(activity,value);}
    CzmAdminDialog(Activity activity,boolean russian){
        super(activity);this.activity=activity;requestWindowFeature(Window.FEATURE_NO_TITLE);
        wide=activity.getResources().getDisplayMetrics().widthPixels>=CzmDialog.dp(activity,640);
        root=new LinearLayout(activity);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(14),dp(10),dp(14),dp(10));
        root.setBackground(CzmDialog.shape(activity,Color.rgb(12,18,28),EDGE,14));
        LinearLayout header=new LinearLayout(activity);header.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout titles=new LinearLayout(activity);titles.setOrientation(LinearLayout.VERTICAL);
        TextView title=text(russian?"Админ-панель":"Admin panel",20,INK);title.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        subtitle=text("CZM",11,MUTED);titles.addView(title);titles.addView(subtitle);
        header.addView(titles,new LinearLayout.LayoutParams(0,-2,1));
        close=button("×",false);close.setTextSize(24);close.setContentDescription(russian?"Закрыть админ-панель":"Close admin panel");
        close.setOnClickListener(v->dismiss());header.addView(close,new LinearLayout.LayoutParams(dp(40),dp(40)));root.addView(header);
        View divider=new View(activity);divider.setBackgroundColor(EDGE);LinearLayout.LayoutParams separator=new LinearLayout.LayoutParams(-1,dp(1));separator.topMargin=dp(9);separator.bottomMargin=dp(10);root.addView(divider,separator);
        LinearLayout workspace=new LinearLayout(activity);workspace.setOrientation(wide?LinearLayout.HORIZONTAL:LinearLayout.VERTICAL);
        nav=new LinearLayout(activity);nav.setOrientation(wide?LinearLayout.VERTICAL:LinearLayout.HORIZONTAL);
        if(wide){
            ScrollView navigationScroll=new ScrollView(activity);navigationScroll.setHorizontalScrollBarEnabled(false);navigationScroll.addView(nav);
            LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(dp(154),-1);params.rightMargin=dp(14);workspace.addView(navigationScroll,params);
        }else{
            HorizontalScrollView navigationScroll=new HorizontalScrollView(activity);navigationScroll.setHorizontalScrollBarEnabled(false);navigationScroll.addView(nav);
            LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,dp(46));params.bottomMargin=dp(8);workspace.addView(navigationScroll,params);
        }
        LinearLayout content=new LinearLayout(activity);content.setOrientation(LinearLayout.VERTICAL);
        search=new LinearLayout(activity);search.setOrientation(LinearLayout.VERTICAL);content.addView(search,new LinearLayout.LayoutParams(-1,-2));
        scroll=new ScrollView(activity);scroll.setFillViewport(false);scroll.setClipToPadding(false);scroll.setPadding(0,0,0,dp(6));
        body=new LinearLayout(activity);body.setOrientation(LinearLayout.VERTICAL);scroll.addView(body,new ScrollView.LayoutParams(-1,-2));
        content.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        workspace.addView(content,wide?new LinearLayout.LayoutParams(0,-1,1):new LinearLayout.LayoutParams(-1,0,1));
        root.addView(workspace,new LinearLayout.LayoutParams(-1,0,1));
        error=text("",13,Color.rgb(255,155,161));error.setPadding(dp(12),dp(10),dp(12),dp(10));error.setVisibility(View.GONE);body.addView(error);
        LinearLayout footer=new LinearLayout(activity);footer.setGravity(Gravity.END|Gravity.CENTER_VERTICAL);footer.setPadding(0,dp(9),0,0);
        cancel=button(russian?"Закрыть":"Close",false);submit=button(russian?"Обновить":"Refresh",true);
        LinearLayout.LayoutParams back=new LinearLayout.LayoutParams(dp(wide?140:100),dp(44));back.rightMargin=dp(10);footer.addView(cancel,back);
        footer.addView(new View(activity),new LinearLayout.LayoutParams(0,1,1));footer.addView(submit,new LinearLayout.LayoutParams(dp(wide?180:120),dp(44)));root.addView(footer);
        cancel.setOnClickListener(v->dismiss());setContentView(root);setCanceledOnTouchOutside(true);
        Window window=getWindow();if(window!=null){
            window.setBackgroundDrawableResource(android.R.color.transparent);window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
            WindowManager.LayoutParams params=window.getAttributes();params.dimAmount=.75f;window.setAttributes(params);
            window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE|WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
        }
    }
    void navigation(String selected,String[] keys,String[] labels,Navigate action){
        nav.removeAllViews();navigation.clear();
        for(int i=0;i<keys.length;i++){
            final String key=keys[i];Button button=button(labels[i],false);button.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);button.setTextSize(13);
            final boolean active=key.equals(selected);button.setTextColor(active?Color.rgb(255,167,178):MUTED);
            button.setBackground(CzmDialog.shape(activity,active?Color.rgb(55,29,43):Color.rgb(16,24,35),active?Color.rgb(124,47,64):0,8));
            LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(wide?-1:-2,dp(40));if(wide)params.bottomMargin=dp(7);else params.rightMargin=dp(6);
            nav.addView(button,params);navigation.add(button);button.setOnClickListener(v->action.open(key));
            if(active)subtitle.setText(labels[i]);
        }
    }
    void section(String title){subtitle.setText(title);}
    void clear(){body.removeAllViews();body.addView(error);error.setVisibility(View.GONE);search.removeAllViews();scroll.scrollTo(0,0);}
    TextView text(String value,int size,int color){TextView view=new TextView(activity);view.setText(value);view.setTextSize(size);view.setTextColor(color);view.setFontFeatureSettings("kern");return view;}
    TextView note(String value){
        TextView view=text(value,13,MUTED);view.setLineSpacing(dp(3),1);view.setPadding(dp(12),dp(10),dp(12),dp(10));
        view.setBackground(CzmDialog.shape(activity,BASE,EDGE,9));LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.bottomMargin=dp(8);body.addView(view,params);return view;
    }
    Button button(String value,boolean primary){
        Button button=new Button(activity);button.setText(value);button.setTextSize(14);button.setTextColor(INK);button.setAllCaps(false);
        button.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));button.setMinWidth(0);button.setMinimumWidth(0);button.setMinHeight(0);button.setMinimumHeight(0);
        button.setPadding(dp(12),dp(8),dp(12),dp(8));button.setBackground(CzmDialog.shape(activity,primary?Color.rgb(190,43,60):Color.rgb(26,36,51),primary?Color.rgb(228,67,86):EDGE,9));return button;
    }
    Button link(String value,View.OnClickListener action){
        Button button=button(value,false);button.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);button.setMinHeight(dp(46));button.setMaxLines(3);button.setEllipsize(TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.bottomMargin=dp(8);body.addView(button,params);button.setOnClickListener(action);return button;
    }
    ImageView person(String nick,int id,String roles,boolean account,View.OnClickListener action){
        LinearLayout row=new LinearLayout(activity);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(10),dp(9),dp(12),dp(9));
        row.setBackground(CzmDialog.shape(activity,BASE,EDGE,9));
        ImageView avatar=new ImageView(activity);avatar.setScaleType(ImageView.ScaleType.CENTER_CROP);avatar.setBackground(CzmDialog.shape(activity,Color.rgb(33,45,63),0,24));avatar.setClipToOutline(true);
        row.addView(avatar,new LinearLayout.LayoutParams(dp(42),dp(42)));
        LinearLayout names=new LinearLayout(activity);names.setOrientation(LinearLayout.VERTICAL);
        TextView name=text(nick,16,INK);name.setSingleLine(true);name.setEllipsize(TextUtils.TruncateAt.END);name.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));names.addView(name);
        TextView detail=text("ID "+id+" · "+(account?"CZM":"Guest")+(roles.isEmpty()?"":" · "+roles),11,roles.contains("support")?Color.rgb(255,153,169):MUTED);detail.setMaxLines(2);detail.setEllipsize(TextUtils.TruncateAt.END);names.addView(detail);
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,1);params.leftMargin=dp(12);row.addView(names,params);row.addView(text("›",23,MUTED));
        LinearLayout.LayoutParams outer=new LinearLayout.LayoutParams(-1,-2);outer.bottomMargin=dp(8);body.addView(row,outer);row.setOnClickListener(action);return avatar;
    }
    EditText field(String label,boolean password,int max){return field(body,label,max,false);}
    EditText search(String label,String value,int max){EditText edit=field(search,label,max,true);edit.setText(value);return edit;}
    private EditText field(LinearLayout parent,String label,int max,boolean hint){
        if(!hint){TextView title=text(label,12,MUTED);LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.bottomMargin=dp(5);parent.addView(title,params);}
        EditText edit=new EditText(activity);edit.setTextSize(15);edit.setTextColor(INK);edit.setHintTextColor(MUTED);edit.setHint(hint?label:"");edit.setSingleLine(true);
        edit.setPadding(dp(12),0,dp(12),0);edit.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);edit.setFilters(new InputFilter[]{new InputFilter.LengthFilter(max)});
        if(Build.VERSION.SDK_INT>=26)edit.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        edit.setBackground(CzmDialog.shape(activity,Color.rgb(17,25,38),EDGE,9));LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,dp(44));params.bottomMargin=dp(10);parent.addView(edit,params);return edit;
    }
    void stats(String[] labels,int[] values){
        final int columns=wide?3:2;
        for(int i=0;i<labels.length;i+=columns){
            LinearLayout row=new LinearLayout(activity);row.setOrientation(LinearLayout.HORIZONTAL);
            for(int n=i;n<Math.min(labels.length,i+columns);n++){
                LinearLayout card=new LinearLayout(activity);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(12),dp(10),dp(12),dp(10));card.setBackground(CzmDialog.shape(activity,BASE,EDGE,9));
                TextView number=text(Integer.toString(values[n]),24,n==3&&values[n]>0?Color.rgb(255,151,166):INK);number.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));card.addView(number);card.addView(text(labels[n],11,MUTED));
                LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,1);if(n<i+columns-1)params.rightMargin=dp(8);row.addView(card,params);
            }
            LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.bottomMargin=dp(8);body.addView(row,params);
        }
    }
    void fail(String message){error.setText(message);error.setVisibility(View.VISIBLE);scroll.post(()->scroll.smoothScrollTo(0,0));}
    void busy(boolean value){submit.setEnabled(!value);cancel.setEnabled(!value);close.setEnabled(!value);for(Button item:navigation)item.setEnabled(!value);enabled(search,!value);setCancelable(!value);}
    private static void enabled(View view,boolean state){view.setEnabled(state);if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)enabled(group.getChildAt(i),state);}}
    @Override public void show(){
        super.show();Window window=getWindow();if(window==null)return;
        android.util.DisplayMetrics size=activity.getResources().getDisplayMetrics();window.setLayout(Math.min(dp(1120),size.widthPixels-dp(24)),size.heightPixels-dp(24));
        window.getDecorView().setSystemUiVisibility(activity.getWindow().getDecorView().getSystemUiVisibility());
    }
}
