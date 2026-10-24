"""Guard the three full-width CZM home buttons against future regressions."""
import struct
import subprocess
import unittest
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/"czm/menu/CzmMain.cpp").read_text(encoding="utf-8")
IMAGE_DIR=ROOT/"3rdparty/cs16client-extras/gfx/czm/ui"

def rgba(path):
    # Sparse developer checkouts may omit tracked, unchanged UI assets.
    data=path.read_bytes() if path.exists() else subprocess.check_output(
        ["git","show","HEAD:"+path.relative_to(ROOT).as_posix()],cwd=ROOT)
    assert data[:8]==b"\x89PNG\r\n\x1a\n"
    offset=8
    segments=[]
    w=h=None
    while offset<len(data):
        n=struct.unpack_from(">I",data,offset)[0]
        kind=data[offset+4:offset+8]
        payload=data[offset+8:offset+8+n]
        assert zlib.crc32(kind+payload)&0xffffffff==struct.unpack_from(">I",data,offset+8+n)[0]
        if kind==b"IHDR":
            w,h,depth,ctype,_,_,_=struct.unpack(">IIBBBBB",payload)
            assert (depth,ctype)==(8,6)
        if kind==b"IDAT":segments.append(payload)
        offset+=12+n
        if kind==b"IEND":break
    raw=zlib.decompress(b"".join(segments))
    stride=w*4
    out=bytearray()
    previous=bytearray(stride)
    pos=0
    for y in range(h):
        fil=raw[pos];pos+=1
        row=bytearray(raw[pos:pos+stride]);pos+=stride
        for i in range(stride):
            l=row[i-4] if i>=4 else 0
            up=previous[i]
            upleft=previous[i-4] if i>=4 else 0
            if fil==1: delta=l
            elif fil==2: delta=up
            elif fil==3: delta=(l+up)//2
            elif fil==4:
                p=l+up-upleft
                a=abs(p-l);b=abs(p-up);c=abs(p-upleft)
                delta=l if a<=b and a<=c else up if b<=c else upleft
            elif fil==0: delta=0
            else:raise AssertionError("Unsupported PNG filter")
            row[i]=(row[i]+delta)&255
        out.extend(row)
        previous=row
    return w,h,out

class HomeActionVisualSafetyTests(unittest.TestCase):
    def test_three_actions_use_identical_width_and_height(self):
        self.assertIn("m_quick.w,actionHeight",MAIN)
        self.assertIn("m_lobbyCreate=CZM_Rect(m_quick.x,m_quick.y+actionHeight+actionGap,",MAIN.replace(" ",""))
        self.assertIn("m_lobbySearch=CZM_Rect(m_quick.x,m_lobbyCreate.y+actionHeight+actionGap,",MAIN.replace(" ",""))
        self.assertIn("m_quick.w,actionHeight",MAIN.replace(" ",""))
        self.assertNotIn("lobbyWidth",MAIN)

    def test_touch_hit_regions_do_not_overlap(self):
        self.assertIn("const int actionGap = Q_max(12,(int)(H * 0.038f))",MAIN)
        # Grown(1.5% of screen height) on each visible rectangle.
        for height in (320,360,400,480,600,720,1080):
            grow=int(height*.015)
            gap=max(12,int(height*.038))
            self.assertGreater(gap,2*grow)

    def test_previous_auxiliary_note_does_not_split_buttons(self):
        self.assertIn("m_lobbySearch.y+m_lobbySearch.h",MAIN.replace(" ",""))
        self.assertNotIn("r.y + r.h + H * 0.014f",MAIN)

    def test_shared_surface_has_transparent_corners_and_opaque_body(self):
        w,h,pixels=rgba(IMAGE_DIR/"surface.png")
        self.assertEqual((w,h),(64,64))
        self.assertEqual(pixels[3],0)
        self.assertEqual(pixels[(32*w+32)*4+3],255)
        self.assertEqual(pixels[(32*w+0)*4+3],255)

    def test_distinct_buttons_keep_existing_handlers(self):
        self.assertIn("CZM_OpenLobbyCreate();",MAIN)
        self.assertIn("CZM_OpenLobbySearch();",MAIN)
        self.assertIn("HIT_QUICK",MAIN)
        self.assertIn('"Создать лобби"',MAIN)
        self.assertIn('"Поиск лобби"',MAIN)

if __name__=="__main__":
    unittest.main()
