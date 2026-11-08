"""Verify the actual shared nickname-color parser and picker color conversions."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProfileColorTests(unittest.TestCase):
    def test_strict_canonical_colors_and_hsv_roundtrip(self):
        source = r'''
#include "CzmNicknameColor.h"
#include <cassert>
#include <cstring>
#include <cstdlib>
#include <string>
int main() {
 const unsigned fallback=0x54123456u;
 for(const char *text:{"","#","#12345","#1234567","123456","#GGGGGG","#12 456"," #123456","#123456\n","red","#FF0000;role=support"}) {
  assert(!CzmNicknameColor::Valid(text));assert(CzmNicknameColor::Parse(text,fallback)==fallback);
 }
 assert(CzmNicknameColor::Parse(nullptr,fallback)==fallback);
 assert(CzmNicknameColor::Parse("#000000",fallback)==0xff000000u);
 assert(CzmNicknameColor::Parse("#ffffff",fallback)==0xffffffffu);
 assert(CzmNicknameColor::Parse("#3dd6ff",fallback)==0xffffd63du);
 char canonical[8];CzmNicknameColor::Hex(CzmNicknameColor::Parse("#aBc123",fallback),canonical);assert(!strcmp(canonical,"#ABC123"));
 // Color conversions preserve even the endpoints accepted by the service.
 for(unsigned r=0;r<=255;r+=17)for(unsigned g=0;g<=255;g+=17)for(unsigned b=0;b<=255;b+=17){
  const unsigned color=r|(g<<8)|(b<<16)|0xff000000u;float h,s,v;
  CzmNicknameColor::ToHsv(color,h,s,v);assert(h>=0&&h<1&&s>=0&&s<=1&&v>=0&&v<=1);
  unsigned restored=CzmNicknameColor::Hsv(h,s,v);
  for(int shift:{0,8,16})assert(abs((int)((restored>>shift)&255)-(int)((color>>shift)&255))<=1);
  CzmNicknameColor::Hex(color,canonical);assert(CzmNicknameColor::Parse(canonical,fallback)==color);
 }
 assert(CzmNicknameColor::Hsv(0,1,1)==0xff0000ffu);
 assert(CzmNicknameColor::Hsv(.5f,1,1)==0xffffff00u);
 assert(CzmNicknameColor::Hsv(-1,1,1)==CzmNicknameColor::Hsv(0,1,1));
 assert(CzmNicknameColor::Hsv(2,1,1)==CzmNicknameColor::Hsv(0,1,1));
 assert(CzmNicknameColor::Hsv(.75f,2,2)==CzmNicknameColor::Hsv(.75f,1,1));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "main.cpp").write_text(source)
            exe = folder / "profile_color"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I"+str(ROOT/"czm/menu"), str(folder/"main.cpp"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
