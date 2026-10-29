/* Compact CZM panels shared by account and server credentials. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.app.Dialog;
import android.graphics.Color;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextUtils;
import android.text.method.PasswordTransformationMethod;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ImageButton;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.ArrayList;

final class CzmDialog extends Dialog {
    static final int RED = Color.rgb(221, 31, 39), MUTED = Color.rgb(155, 163, 177);
    final Activity activity;
    final LinearLayout body;
    final Button cancel, submit;
    final TextView error;
    private final LinearLayout root;
    private final ScrollView scroll;
    private final boolean russian;
    private final ArrayList<Runnable> hidePasswords = new ArrayList<>();

    static int dp(Activity a, int value) { return Math.round(value * a.getResources().getDisplayMetrics().density); }
    static GradientDrawable shape(Activity a, int color, int border, int radius) {
        GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(a, radius));
        if (border != 0) d.setStroke(dp(a, 1), border);
        return d;
    }

    CzmDialog(Activity a, String title, String subtitle, String action, String back, boolean ru) {
        this(a, title, subtitle, action, back, ru, true);
    }
    CzmDialog(Activity a, String title, String subtitle, String action, String back, boolean ru, boolean sensitive) {
        super(a); activity = a; russian = ru;
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        root = new LinearLayout(a); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(a, 18), dp(a, 12), dp(a, 18), dp(a, 12));
        root.setBackground(shape(a, Color.rgb(15, 18, 24), Color.rgb(62, 65, 74), 16));
        root.setFocusableInTouchMode(true);
        TextView heading = text(title, 19, Color.WHITE); heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD_ITALIC);
        root.addView(heading);
        if (!subtitle.isEmpty()) {
            TextView sub = text(subtitle, 12, MUTED); sub.setMaxLines(2); sub.setEllipsize(TextUtils.TruncateAt.END);
            root.addView(sub);
        }
        View line = new View(a); line.setBackgroundColor(RED);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(a, 36), dp(a, 2));
        lp.topMargin = dp(a, 9); lp.bottomMargin = dp(a, 6); root.addView(line, lp);
        scroll = new ScrollView(a) {
            @Override protected void onMeasure(int widthSpec, int heightSpec) {
                android.graphics.Rect visible=new android.graphics.Rect();
                root.getWindowVisibleDisplayFrame(visible);
                int available=visible.height()>0?visible.height():a.getResources().getDisplayMetrics().heightPixels;
                int cap=Math.max(dp(a,48),Math.min(dp(a,200),available-dp(a,150)));
                if(View.MeasureSpec.getMode(heightSpec)!=View.MeasureSpec.UNSPECIFIED)cap=Math.min(cap,View.MeasureSpec.getSize(heightSpec));
                super.onMeasure(widthSpec,View.MeasureSpec.makeMeasureSpec(cap,View.MeasureSpec.AT_MOST));
            }
        }; scroll.setFillViewport(false);
        body = new LinearLayout(a); body.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(body);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, -2));
        error = text("", 12, Color.rgb(255, 137, 137)); error.setVisibility(View.GONE); body.addView(error);
        LinearLayout buttons = new LinearLayout(a); buttons.setGravity(Gravity.END);
        cancel = button(back, false); submit = button(action, true);
        LinearLayout.LayoutParams b = new LinearLayout.LayoutParams(0, dp(a, 44), 1);
        b.topMargin = dp(a, 8); b.rightMargin = dp(a, 8); buttons.addView(cancel, b);
        LinearLayout.LayoutParams s = new LinearLayout.LayoutParams(0, dp(a, 44), 1); s.topMargin = dp(a, 8);
        buttons.addView(submit, s); root.addView(buttons);
        cancel.setOnClickListener(v -> dismiss());
        setCanceledOnTouchOutside(true);
        setContentView(root);
        Window w = getWindow();
        if (w != null) {
            w.setBackgroundDrawableResource(android.R.color.transparent);
            w.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
            if (sensitive) w.addFlags(WindowManager.LayoutParams.FLAG_SECURE);
            WindowManager.LayoutParams attrs = w.getAttributes(); attrs.dimAmount = .68f; w.setAttributes(attrs);
            w.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE | WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
        }
    }

    TextView text(String value, int size, int color) {
        TextView v = new TextView(activity); v.setText(value); v.setTextSize(size); v.setTextColor(color);
        return v;
    }
    TextView note(String value) {
        TextView v = text(value, 12, MUTED); v.setPadding(0, dp(activity, 6), 0, dp(activity, 4)); body.addView(v); return v;
    }
    Button button(String value, boolean primary) {
        Button b = new Button(activity); b.setText(value); b.setTextSize(13); b.setTextColor(Color.WHITE);
        b.setAllCaps(false); b.setMinHeight(0); b.setMinimumHeight(0); b.setMinWidth(0); b.setMinimumWidth(0);
        b.setPadding(dp(activity, 8), 0, dp(activity, 8), 0);
        b.setBackground(shape(activity, primary ? RED : Color.rgb(26, 30, 38), primary ? 0 : Color.rgb(60, 66, 77), 22));
        return b;
    }
    Button link(String value, View.OnClickListener action) {
        Button b = button(value, false);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, dp(activity, 42)); p.topMargin = dp(activity, 6);
        body.addView(b, p); b.setOnClickListener(action); return b;
    }
    EditText field(String label, boolean password, int max) {
        note(label);
        EditText e = new EditText(activity); e.setTextSize(15); e.setTextColor(Color.WHITE); e.setHintTextColor(MUTED);
        e.setSingleLine(true); e.setPadding(dp(activity, 12), 0, dp(activity, 12), 0);
        e.setInputType(InputType.TYPE_CLASS_TEXT | (password ? InputType.TYPE_TEXT_VARIATION_PASSWORD : InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS));
        e.setFilters(new InputFilter[] {new InputFilter.LengthFilter(max)});
        if (Build.VERSION.SDK_INT >= 26) e.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        if (password) {
            LinearLayout row = new LinearLayout(activity); row.setGravity(Gravity.CENTER_VERTICAL);
            row.setBackground(shape(activity, Color.rgb(24, 28, 36), Color.rgb(61, 67, 80), 10));
            e.setBackgroundColor(Color.TRANSPARENT);
            row.addView(e, new LinearLayout.LayoutParams(0, -1, 1));
            ImageButton eye = new ImageButton(activity); eye.setBackgroundColor(Color.TRANSPARENT);
            EyeIcon icon = new EyeIcon(); eye.setImageDrawable(icon); eye.setPadding(dp(activity, 10), dp(activity, 10), dp(activity, 10), dp(activity, 10));
            eye.setContentDescription(russian ? "Показать пароль" : "Show password");
            Runnable hide = () -> {
                int start = e.getSelectionStart(), end = e.getSelectionEnd();
                e.setTransformationMethod(PasswordTransformationMethod.getInstance());
                if (start >= 0 && end >= 0) e.setSelection(Math.min(start, e.length()), Math.min(end, e.length()));
                icon.visible = false; icon.invalidateSelf();
                eye.setContentDescription(russian ? "Показать пароль" : "Show password");
            };
            hidePasswords.add(hide);
            eye.setOnClickListener(v -> {
                if (icon.visible) { hide.run(); return; }
                int start = e.getSelectionStart(), end = e.getSelectionEnd();
                // Keep the password input type: revealing text must not enable suggestions.
                e.setTransformationMethod(null);
                if (start >= 0 && end >= 0) e.setSelection(Math.min(start, e.length()), Math.min(end, e.length()));
                icon.visible = true; icon.invalidateSelf();
                eye.setContentDescription(russian ? "Скрыть пароль" : "Hide password");
            });
            row.addView(eye, new LinearLayout.LayoutParams(dp(activity, 44), dp(activity, 44)));
            body.addView(row, new LinearLayout.LayoutParams(-1, dp(activity, 44)));
        } else {
            e.setBackground(shape(activity, Color.rgb(24, 28, 36), Color.rgb(61, 67, 80), 10));
            body.addView(e, new LinearLayout.LayoutParams(-1, dp(activity, 44)));
        }
        return e;
    }
    EditText codeField(String label) {
        note(label);CzmCodeInput code=new CzmCodeInput(activity,russian);
        body.addView(code,new LinearLayout.LayoutParams(-1,dp(activity,52)));return code;
    }
    void fail(String message) {
        error.setText(message); error.setVisibility(View.VISIBLE);
        scroll.post(() -> scroll.smoothScrollTo(0, 0));
    }
    void busy(boolean value) { submit.setEnabled(!value); cancel.setEnabled(!value); setCancelable(!value); }

    private void maskPasswords() { for (Runnable hide : hidePasswords) hide.run(); }
    @Override public void dismiss() { maskPasswords(); super.dismiss(); }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (!focused) maskPasswords();
    }

    private static final class EyeIcon extends Drawable {
        boolean visible;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        @Override public void draw(Canvas canvas) {
            canvas.save(); canvas.translate(getBounds().left, getBounds().top);
            canvas.scale(getBounds().width() / 24f, getBounds().height() / 24f);
            paint.setColor(visible ? Color.WHITE : MUTED); paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(1.7f);
            Path eye = new Path(); eye.moveTo(2, 12); eye.cubicTo(7, 3, 17, 3, 22, 12); eye.cubicTo(17, 21, 7, 21, 2, 12);
            canvas.drawPath(eye, paint); canvas.drawCircle(12, 12, 3, paint);
            if (visible) canvas.drawLine(4, 3, 21, 21, paint);
            canvas.restore();
        }
        @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); }
        @Override public void setColorFilter(android.graphics.ColorFilter filter) { paint.setColorFilter(filter); }
        @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    }

    @Override public void show() {
        super.show();
        Window window = getWindow();
        if (window == null) return;
        android.util.DisplayMetrics m = activity.getResources().getDisplayMetrics();
        // A bounded compact panel; the body scrolls and the actions remain visible with the IME.
        window.setLayout(Math.min(dp(activity, 420), m.widthPixels - dp(activity, 32)),WindowManager.LayoutParams.WRAP_CONTENT);
        root.requestFocus();
    }
}
