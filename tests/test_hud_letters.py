"""Western accented letters in the cp1251 HUD font, arrows in the menu font."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]


class HudLettersTests(unittest.TestCase):
    def test_accents_become_base_letters_in_the_client_and_the_engine(self):
        program = r'''
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "utflib.h"
static void convert(const char *in, char *out){
 utfstate_t st={0};int n=0;
 for(const char*p=in;*p;p++){uint32_t ch=Q_DecodeUTF8(&st,(unsigned char)*p);if(!ch)continue;out[n++]=(char)Q_UnicodeToCP1251(ch);}
 out[n]=0;
}
int main(){
 char out[128];
 convert("Infecção | Clássico | Modo Infecção",out);if(strcmp(out,"Infeccao | Classico | Modo Infeccao"))return 1;
 convert("ZÜRICH Łódź Ñandú",out);if(strcmp(out,"ZURICH Lodz Nandu"))return 2;
 convert("Привет ёЁ №",out);if((unsigned char)out[0]!=0xCF||(unsigned char)out[7]!=0xB8||(unsigned char)out[8]!=0xA8||(unsigned char)out[10]!=0xB9)return 3;
 convert("漢 ?",out);if(strcmp(out,"? ?"))return 4;  // what has no letter stays a question mark
 puts("FOLD_OK");return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "main.cpp").write_text(program)
            subprocess.run(["g++", "-std=gnu++11", "-DSTDINT_H=<cstdint>", "-I" + str(ROOT / "public"), "-I" + str(ROOT / "common"),
                            str(p / "main.cpp"), str(ROOT / "public/utflib.cpp"), "-o", str(p / "fold")], check=True)
            self.assertIn("FOLD_OK", subprocess.run([str(p / "fold")], check=True, capture_output=True, text=True).stdout)
        # the engine draws the glyphs: its own conversion folds the same way
        patch = (ROOT / "patches/xash3d-fwgs/0025-czm-hud-western-letters-fold.patch").read_text()
        client = (ROOT / "public/utflib.cpp").read_text()
        table = client[client.index("static const char base[] ="):client.index("if( uc >= 0xC0")]
        for line in table.splitlines()[1:]:
            self.assertIn("+" + line, patch)
        self.assertIn("+\treturn Q_FoldLatin( uc );", patch)

    def test_menu_arrows_become_angle_quotes(self):
        source = (ROOT / "czm/menu/CzmOnline.cpp").read_text()
        program = "#include <cstring>\n#include <cstdio>\n" + function(source, "static void PlainArrows(") + r'''
int main(){
 char a[]="Настройки → Звук → «Трек меню» ← назад";
 PlainArrows(a);
 if(strcmp(a,"Настройки › Звук › «Трек меню» ‹ назад"))return 1;
 char b[]="\xE2\x86";PlainArrows(b); // a cut sequence at the end is left alone
 puts("ARROWS_OK");return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "main.cpp").write_text(program)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", str(p / "main.cpp"), "-o", str(p / "arrows")], check=True)
            self.assertIn("ARROWS_OK", subprocess.run([str(p / "arrows")], check=True, capture_output=True, text=True).stdout)

    def test_cyrillic_hud_font_for_the_shipped_gfx_wad(self):
        """Server HUD texts are drawn with the credits font. The font inside our valve/gfx.wad (the 25th
        anniversary Half-Life, zlib crc32 0xe53ecdca) has no letters above 127, so the engine has to take
        creditsfont_cp1251.fnt for it too, as it does for the old gfx.wad."""
        patch = (ROOT / "patches/xash3d-fwgs/0027-czm-hud-font-cyrillic-hl25.patch").read_text()
        self.assertIn('+\tif( !CRC32_File( &crc, "gfx.wad" ) || crc == 0x49eb9f16 || crc == 0x1ac13235 )', patch)
        # CRC32_File returns the register before the final xor: the inverted zlib value
        self.assertEqual(0xe53ecdca ^ 0xffffffff, 0x1ac13235)
        engine = ROOT / "3rdparty/xash3d-fwgs"
        build = engine / "3rdparty/library_suffix/include"
        if not (build / "build.h").is_file():
            self.skipTest("the engine's library_suffix submodule is not checked out")
        program = r'''
#include <stdio.h>
#include <stdint.h>
#include "crclib.h"
int main(void){
 static unsigned char data[74314]; uint32_t seed = 12345, crc;
 for(unsigned i = 0; i < sizeof(data); i++){ seed = seed * 1103515245u + 12345u; data[i] = seed >> 16; }
 CRC32_Init(&crc);
 for(unsigned i = 0; i < sizeof(data); i += 1024) CRC32_ProcessBuffer(&crc, data + i, sizeof(data) - i < 1024 ? (int)(sizeof(data) - i) : 1024);
 printf("%08x\n", crc); return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "main.c").write_text(program)
            subprocess.run(["gcc", "-std=gnu11", "-I" + str(engine / "public"), "-I" + str(engine / "common"),
                            "-I" + str(engine / "engine"), "-I" + str(build), str(p / "main.c"),
                            str(engine / "public/crclib.c"), "-o", str(p / "crc")], check=True)
            raw = int(subprocess.run([str(p / "crc")], check=True, capture_output=True, text=True).stdout, 16)
        import zlib
        seed, data = 12345, bytearray()
        for _ in range(74314):
            seed = (seed * 1103515245 + 12345) & 0xffffffff
            data.append((seed >> 16) & 0xff)
        self.assertEqual(raw, zlib.crc32(bytes(data)) ^ 0xffffffff)

    def test_keyboard_pan_does_not_move_the_touch_safe_area(self):
        """While the chat keyboard is open the view is panned up; the safe area must not be measured from
        the panned surface, or the touch buttons stay shifted down after the keyboard hides (upstream e76d82f)."""
        patch = (ROOT / "patches/xash3d-fwgs/0026-czm-android-insets-cutouts-only.patch").read_text()
        self.assertIn("-\t\tsurface.getLocationInWindow(origin);", patch)
        self.assertIn("+\t\tmWindowInsets = new float[] { left / width, top / height, right / width, bottom / height };", patch)
        activity = (ROOT / "3rdparty/xash3d-fwgs/android/app/src/main/java/su/xash/engine/XashActivity.java").read_text()
        if "upstream e76d82f" in activity:  # the patches are applied (CI)
            body = activity[activity.index("private void updateWindowInsets("):activity.index("public void onDestroy()")]
            self.assertNotIn("getLocationInWindow", body)
            self.assertNotIn("getTranslation", body)


if __name__ == "__main__":
    unittest.main()
