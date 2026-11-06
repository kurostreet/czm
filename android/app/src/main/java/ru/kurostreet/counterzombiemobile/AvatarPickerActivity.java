package ru.kurostreet.counterzombiemobile;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.BitmapShader;
import android.graphics.Canvas;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.Shader;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * The player's avatar or spray from the phone gallery.
 *
 * The menu opens czmavatar://pick?file=czm_avatar_N.png (the engine hands such links to
 * Android). Android opens those links with "no history", which would lose the gallery's
 * answer, so the first copy only starts a second one and closes. The second copy asks
 * the gallery for a picture and writes the completed PNG. Avatar photos go
 * in the game folder and sprays in its logos folder.
 */
public class AvatarPickerActivity extends Activity {
    private static final String TAG = "CzmAvatar";
    private static final String EXTRA_FILE = "file";
    private static final int PICK = 1;
    private static final int SIZE = 192;
    private static final int SPRAY_SIZE = 96;
    private String fileName;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);

        if (state != null) {
            // back after Android closed us while the gallery was open
            fileName = state.getString(EXTRA_FILE);
            return;
        }

        if (getIntent().hasExtra(EXTRA_FILE)) {
            fileName = getIntent().getStringExtra(EXTRA_FILE);
            if (!validName(fileName)) {
                finish();
                return;
            }
            Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
            pick.setType("image/*");
            pick.addCategory(Intent.CATEGORY_OPENABLE);
            try {
                startActivityForResult(pick, PICK);
            } catch (ActivityNotFoundException e) {
                Log.w(TAG, "no gallery", e);
                finish();
            }
            return;
        }

        // the link from the menu: start the copy that can wait for the gallery
        Uri data = getIntent().getData();
        String file = data != null ? data.getQueryParameter(EXTRA_FILE) : null;
        if (validName(file)) {
            startActivity(new Intent(this, AvatarPickerActivity.class).putExtra(EXTRA_FILE, file));
        }
        finish();
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putString(EXTRA_FILE, fileName);
    }

    private static boolean validName(String file) {
        return file != null && file.matches("czm_(?:avatar|spray)_[0-9]{1,9}\\.png");
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK || result != RESULT_OK || data == null || data.getData() == null || !validName(fileName)) {
            close();
            return;
        }

        final Uri picture = data.getData();
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    save(picture);
                } catch (Exception e) {
                    Log.w(TAG, "could not use the picture", e);
                }
                runOnUiThread(new Runnable() {
                    @Override public void run() { close(); }
                });
            }
        }).start();
    }

    private void close() {
        if (Build.VERSION.SDK_INT >= 21) finishAndRemoveTask();
        else finish();
    }

    private void save(Uri picture) throws IOException {
        boolean spray = fileName.startsWith("czm_spray_");
        int size = spray ? SPRAY_SIZE : SIZE;
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        try (InputStream in = getContentResolver().openInputStream(picture)) {
            BitmapFactory.decodeStream(in, null, bounds);
        }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return;

        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = 1;
        while (Math.max(bounds.outWidth, bounds.outHeight) / options.inSampleSize > size * 4) {
            options.inSampleSize *= 2;
        }

        Bitmap source;
        try (InputStream in = getContentResolver().openInputStream(picture)) {
            source = BitmapFactory.decodeStream(in, null, options);
        }
        if (source == null) return;

        // photos from the camera keep their turn in EXIF
        Matrix matrix = new Matrix();
        if (Build.VERSION.SDK_INT >= 24) {
            try (InputStream in = getContentResolver().openInputStream(picture)) {
                int orientation = new ExifInterface(in).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL);
                if (orientation == ExifInterface.ORIENTATION_ROTATE_90) matrix.postRotate(90);
                else if (orientation == ExifInterface.ORIENTATION_ROTATE_180) matrix.postRotate(180);
                else if (orientation == ExifInterface.ORIENTATION_ROTATE_270) matrix.postRotate(270);
            } catch (Exception e) {
                Log.w(TAG, "no EXIF", e);
            }
        }

        saveImage(spray ? makeSpray(source, matrix) : makeAvatar(source, matrix), spray);
    }

    private static Bitmap makeSpray(Bitmap source, Matrix orientation) {
        Bitmap oriented = Bitmap.createBitmap(source, 0, 0, source.getWidth(), source.getHeight(), orientation, true);
        Bitmap spray = Bitmap.createBitmap(SPRAY_SIZE, SPRAY_SIZE, Bitmap.Config.ARGB_8888);
        float scale = (float) SPRAY_SIZE / Math.max(oriented.getWidth(), oriented.getHeight());
        Matrix fit = new Matrix();
        fit.setScale(scale, scale);
        fit.postTranslate((SPRAY_SIZE - oriented.getWidth() * scale) / 2, (SPRAY_SIZE - oriented.getHeight() * scale) / 2);
        new Canvas(spray).drawBitmap(oriented, fit, new Paint(Paint.FILTER_BITMAP_FLAG));
        return spray;
    }

    private static Bitmap makeAvatar(Bitmap source, Matrix matrix) {
        // The middle square, turned and made avatar size.
        int side = Math.min(source.getWidth(), source.getHeight());
        float scale = (float) SIZE / side;
        matrix.preScale(scale, scale);
        Bitmap square = Bitmap.createBitmap(source, (source.getWidth() - side) / 2, (source.getHeight() - side) / 2, side, side, matrix, true);

        // round, with the red ring of the game avatars
        Bitmap avatar = Bitmap.createBitmap(SIZE, SIZE, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(avatar);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
        Matrix fit = new Matrix();
        fit.setScale((float) SIZE / square.getWidth(), (float) SIZE / square.getHeight());
        BitmapShader shader = new BitmapShader(square, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP);
        shader.setLocalMatrix(fit);
        paint.setShader(shader);
        canvas.drawCircle(SIZE / 2f, SIZE / 2f, SIZE / 2f, paint);
        Paint ring = new Paint(Paint.ANTI_ALIAS_FLAG);
        ring.setStyle(Paint.Style.STROKE);
        ring.setStrokeWidth(7f);
        ring.setColor(0xFFFF3B2F);
        canvas.drawCircle(SIZE / 2f, SIZE / 2f, SIZE / 2f - 3.5f, ring);
        return avatar;
    }

    private void saveImage(Bitmap image, boolean spray) throws IOException {
        File dir = new File(getFilesDir(), spray ? "game/cstrike/logos" : "game/cstrike");
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("no game folder " + dir);
        File part = File.createTempFile("czm_photo", ".part", dir);
        try {
            try (FileOutputStream out = new FileOutputStream(part)) {
                if (!image.compress(Bitmap.CompressFormat.PNG, 100, out)) throw new IOException("PNG encoding failed");
            }
            if (!part.renameTo(new File(dir, fileName))) throw new IOException("rename failed");
        } finally {
            part.delete();
        }

        String prefix = spray ? "czm_spray_" : "czm_avatar_";
        File[] old = dir.listFiles();
        if (old != null) {
            for (File f : old) {
                String name = f.getName();
                if (name.startsWith(prefix) && validName(name) && !name.equals(fileName) && !f.delete()) {
                    Log.w(TAG, "could not delete " + name);
                }
            }
        }

        Log.i(TAG, "photo saved: " + fileName);
    }
}
