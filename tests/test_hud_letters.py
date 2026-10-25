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


if __name__ == "__main__":
    unittest.main()
