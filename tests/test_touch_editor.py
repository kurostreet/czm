"""The editor must cover stale game frames before drawing editable controls."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]


class TouchEditorTests(unittest.TestCase):
    def test_connected_editor_repaints_opaque_preview_every_frame(self):
        source = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        draw = function(source, "void CCzmTouchEditor::Draw()")
        # Execute the actual paint entry up to the first controls; later overlays
        # cannot repair a missing background underneath these controls.
        draw = draw[:draw.index("\tDrawButtons();")] + "\tDrawButtons();\n}"
        harness = r'''
#include <cassert>
#include <cstring>
#define UI_DIR "gfx/czm/ui/"
static bool connected;static int backgrounds,buttons;
static bool CL_IsActive(){return connected;}
static int CZM_Image(const char *name){assert(!strcmp(name,"gfx/czm/ui/editor_bg.png"));return 7;}
static void CZM_DrawCover(int image,int x,int y,int w,int h){assert(image==7&&x==0&&y==0&&w==1536&&h==716);backgrounds++;}
class CCzmTouchEditor{public:int W=1536,H=716;void Layout(){}void Draw();
 void FindConflicts(){}void DrawHud(){assert(backgrounds==buttons+1);}
 void DrawButtons(){assert(backgrounds==buttons+1);buttons++;}};
''' + draw + r'''
int main(){CCzmTouchEditor editor;for(int i=0;i<8;i++){connected=(i%2)!=0;editor.Draw();}assert(backgrounds==8&&buttons==8);}
'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "editor.cpp").write_text(harness)
            subprocess.run(["g++", "-std=c++11", str(path / "editor.cpp"), "-o", str(path / "editor")], check=True)
            subprocess.run([str(path / "editor")], check=True)


if __name__ == "__main__":
    unittest.main()
