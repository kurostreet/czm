"""Convert real preset/upload pixels with the engine quantizer and WAD writer."""
from pathlib import Path
import hashlib
import struct
import subprocess
import tempfile
import unittest
from PIL import Image
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs/engine"
PREAMBLE = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define true 1
#define false 0
#define Q_min(a,b) ((a)<(b)?(a):(b))
#define Q_max(a,b) ((a)>(b)?(a):(b))
#define Mem_Malloc(pool,n) calloc(1,n)
#define Mem_Realloc(pool,p,n) realloc(p,n)
#define Mem_Free free
#define le_struct_swap(a,b) ((void)0)
#define LittleShort(x) (x)
#define LittleLong(x) (x)
#define IDWAD3HEADER 0x33444157
#define TYP_PALETTE 0x40
#define TYP_MIPTEX 0x43
#define IMAGE_GRADIENT_DECAL 1
#define IL_KEEP_8BIT 1
typedef unsigned char byte;typedef int qboolean;typedef long fs_offset_t;typedef FILE file_t;
enum {PF_RGBA_32=1,PF_INDEXED_24,PF_INDEXED_32};
typedef struct {int width,height,type,size,flags;byte *buffer,*palette;}rgbdata_t;
struct {int imagepool;}host;
struct {int width,height,size,bpp,ptr;byte *tempbuffer,*palette;}image;
struct {int bpp;}PFDesc[]={{0},{4},{1},{1}};
typedef struct {int ident,numlumps,infotableofs;}dwadinfo_t;
typedef struct {char name[16];uint32_t width,height,offsets[4];}mip_t;
typedef struct {int filepos,disksize,size;byte type,compression;uint16_t attribs;char name[16];}dlumpinfo_t;
static int freed;
static void Image_SetForceFlags(int f){}
static void Image_CopyParms(rgbdata_t *p){image.width=p->width;image.height=p->height;}
static rgbdata_t *FS_LoadImage(const char *name,void *unused,int n){
 FILE *f=fopen(name,"rb");if(!f)return NULL;rgbdata_t *p=calloc(1,sizeof(*p));
 assert(fread(&p->width,4,1,f)==1&&fread(&p->height,4,1,f)==1);
 p->type=PF_RGBA_32;p->size=p->width*p->height*4;p->buffer=malloc(p->size);
 assert(fread(p->buffer,1,p->size,f)==p->size);fclose(f);return p;
}
static void FS_FreeImage(rgbdata_t *p){free(p->buffer);free(p->palette);free(p);freed++;}
static rgbdata_t *FS_CopyImage(rgbdata_t *p){rgbdata_t *q=malloc(sizeof(*q));*q=*p;q->buffer=malloc(p->size);memcpy(q->buffer,p->buffer,p->size);return q;}
static byte *resampled;
static byte *Image_ResampleInternal(byte *src,int w,int h,int nw,int nh,int type,qboolean *changed){
 resampled=realloc(resampled,nw*nh*4);for(int y=0;y<nh;y++)for(int x=0;x<nw;x++)
 memcpy(resampled+(y*nw+x)*4,src+((y*h/nh)*w+x*w/nw)*4,4);*changed=true;return resampled;
}
#define FS_Open(name,mode,gameonly) fopen(name,mode)
#define FS_Write(f,p,n) fwrite(p,1,n,f)
#define FS_Tell ftell
#define FS_Seek fseek
#define FS_Close fclose
static qboolean FS_SaveImage(const char *,rgbdata_t *);
'''


class SprayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        quant = (ENGINE / "common/imagelib/img_quant.c").read_text().replace('#include "imagelib.h"', '')
        wad = (ENGINE / "common/imagelib/img_wad.c").read_text()
        spray = (ENGINE / "client/cl_spray.c").read_text()
        code = PREAMBLE + quant + function((ENGINE / "common/imagelib/img_utils.c").read_text(), "void Image_GenerateMipmaps(")
        code += wad[wad.index("qboolean Image_SaveWAD("):]
        code += '\nstatic qboolean FS_SaveImage(const char *name,rgbdata_t *p){return Image_SaveWAD(name,p);}\n'
        code += spray[spray.index("#define SPRAY_MAX_"):]
        code += r'''
int main(int argc,char **argv){
 assert(argc==2);assert(CL_ConvertImageToWAD3(argv[1]));assert(freed>=2);
 free(image.tempbuffer);free(resampled);return 0;
}
'''
        (cls.folder / "spray.c").write_text(code)
        cls.exe = cls.folder / "convert"
        subprocess.run(["gcc", "-std=gnu99", str(cls.folder / "spray.c"), "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def convert(self, path):
        with Image.open(path) as source:
            rgba = source.convert("RGBA")
            (self.folder / "input.rgba").write_bytes(struct.pack("<II", *rgba.size) + rgba.tobytes())
        subprocess.run([str(self.exe), "input.rgba"], cwd=self.folder, check=True)
        wad = (self.folder / "tempdecal.wad").read_bytes()
        magic, count, directory = struct.unpack_from("<4sII", wad)
        self.assertEqual((magic, count), (b"WAD3", 1))
        offset, packed, size, kind = struct.unpack_from("<IIIB", wad, directory)
        self.assertEqual(kind, 0x43)
        self.assertLessEqual(offset + size, directory)
        self.assertEqual(packed, size)
        name, w, h, *mips = struct.unpack_from("<16s6I", wad, offset)
        self.assertEqual(name.rstrip(b"\0"), b"{LOGO")
        self.assertTrue(16 <= w <= 64 and 16 <= h <= 64)
        self.assertEqual((w % 16, h % 16), (0, 0))
        self.assertEqual(mips, [40, 40+w*h, 40+w*h*5//4, 40+w*h*21//16])
        palette = offset + mips[-1] + w*h//64
        self.assertEqual(struct.unpack_from("<H", wad, palette)[0], 256)
        self.assertLessEqual(palette + 770, offset + size)
        self.assertEqual(wad[palette+2+765:palette+2+768], b"\0\0\xff")
        return wad, (w, h)

    def test_all_presets_are_distinct_compatible_goldsrc_wads(self):
        hashes = set()
        for path in sorted((ROOT / "3rdparty/cs16client-extras/logos").glob("czm_*.png")):
            with self.subTest(spray=path.name):
                wad, dimensions = self.convert(path)
                self.assertEqual(dimensions, (64, 64))
                hashes.add(hashlib.sha256(wad).hexdigest())
        self.assertEqual(len(hashes), 9)

    def test_uploaded_image_is_converted_without_losing_transparency(self):
        path = self.folder / "uploaded.png"
        picture = Image.new("RGBA", (320, 160), (30, 200, 60, 255))
        picture.putpixel((0, 0), (0, 0, 0, 0))
        picture.save(path)
        wad, dimensions = self.convert(path)
        self.assertEqual(dimensions, (64, 32))
        self.assertEqual(wad[12+40], 255)

    def test_failed_conversion_never_uploads_previous_wad(self):
        source = (ENGINE / "client/cl_main.c").read_text()
        harness = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define true 1
#define false 0
#define MAX_OSPATH 256
#define PROTO_GOLDSRC 48
#define FCVAR_CHANGED 1
#define RES_CUSTOM 1
#define ClearBits(x,b) ((x)&=~(b))
#define SetBits(x,b) ((x)|=(b))
#define Q_strcmp strcmp
#define Q_strncmp strncmp
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
#define Q_snprintf snprintf
typedef unsigned char byte;typedef int qboolean;typedef int file_t;
typedef struct{int ucFlags;byte rgucMD5_hash[16];}resource_t;
enum{t_decal};struct{int net_protocol;}cls;struct{int num_resources;}cl;
struct cvar{int flags;char *string;}cl_logoupdate,cl_logofile,cl_logocolor,cl_logoext,hpk_custom_file;
static int converted,opened,added;static qboolean valid;static resource_t resource;static file_t file;
static const char *expected="logos/remapped.png";
static void HPAK_FlushHostQueue(void){}
static void Cvar_DirectSet(struct cvar *v,char *s){v->string=s;}
static qboolean CL_ConvertImageToWAD3(const char *name){assert(!strcmp(name,expected));converted++;return valid;}
static void Con_Printf(const char *s){}
static file_t *FS_Open(const char *name,const char *mode,qboolean game){assert(!strcmp(name,"tempdecal.wad"));opened++;return &file;}
static int FS_FileLength(file_t *f){return 6256;}
static resource_t *CL_AddResource(int type,const char *name,int size,qboolean fatal,int index){added++;cl.num_resources++;return &resource;}
static void MD5_HashFile(byte *hash,const char *name,void *unused){}
static void HPAK_AddLump(int queued,const char *name,resource_t *r,void *unused,file_t *f){}
static void FS_Close(file_t *f){}
''' + function(source, "static void CL_CreateResourceList(") + r'''
int main(void){
 cls.net_protocol=PROTO_GOLDSRC;cl_logoext.string="png";cl_logofile.string="lambda";valid=false;
 CL_CreateResourceList();assert(converted==1&&opened==0&&added==0&&cl.num_resources==0);
 valid=true;CL_CreateResourceList();assert(converted==2&&opened==1&&added==1&&cl.num_resources==1);
 // Selection wins over a stale remapped file and a restored old extension.
 cl_logofile.string="czm_biohazard";cl_logoext.string="bmp";expected="logos/czm_biohazard.png";
 CL_CreateResourceList();assert(converted==3&&opened==2&&added==2);
 // Untrusted names cannot select a path outside the logos directory.
 cl_logofile.string="czm_../../secret";cl_logoext.string="png";expected="logos/remapped.png";
 CL_CreateResourceList();assert(converted==4&&opened==3&&added==3);
}
'''
        path = self.folder / "resource.c"
        path.write_text(harness)
        exe = self.folder / "resource"
        subprocess.run(["gcc", "-std=gnu99", str(path), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

    def test_saved_selection_is_prepared_and_restored_before_upload(self):
        source = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
        start = source.index("static const char *s_sprays[]")
        end = source.index("\n/*", source.index("void CZM_SprayFrame(", start))
        harness = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <strings.h>
#include <string>
#include <map>
using byte=unsigned char;
#define stricmp strcasecmp
#define Q_strncpy(d,s,n) snprintf(d,n,"%s",s)
static std::map<std::string,std::string> vars;
static std::string loaded;
static double now=10;static int reads,saves;static bool available=true;
struct EngFuncs {
 static const char*GetCvarString(const char*n){return vars[n].c_str();}
 static float GetCvarFloat(const char*n){return atof(GetCvarString(n));}
 static void CvarSetString(const char*n,const char*v){vars[n]=v;}
 static void CvarSetValue(const char*n,float v){vars[n]=std::to_string(v);}
 static double DoubleTime(){return now;}
 static byte*COM_LoadFile(const char*n,int*size){reads++;loaded=n;*size=available?4:0;static byte data[4];return available?data:nullptr;}
 static int COM_SaveFile(const char*n,byte*,int size){assert(!strcmp(n,"logos/remapped.png")&&size==4);saves++;return 1;}
 static void COM_FreeFile(void*){}static void DeleteFile(const char*){}
};
''' + source[start:end] + r'''
int main(){
 vars["cl_logofile"]="czm_biohazard";vars["cl_logoext"]="bmp";vars["cl_allowupload"]="0";
 CZM_SprayFrame();assert(loaded=="logos/czm_biohazard.png"&&saves==1&&EngFuncs::GetCvarFloat("cl_allowupload")==1);
 for(int i=0;i<100;i++){now+=.03;CZM_SprayFrame();}assert(reads==1);
 vars["cl_logofile"]="lambda";CZM_SprayFrame();assert(vars["cl_logofile"]=="czm_biohazard"&&saves==2);
 now+=3;vars["cl_logofile"]="custom_player_logo";CZM_SprayFrame();assert(reads==2);
 vars["cl_logofile"]="czm_skull";available=false;CZM_SprayFrame();assert(reads==3&&saves==2);
 now+=.2;CZM_SprayFrame();assert(reads==3);
 now+=3;available=true;CZM_SprayFrame();assert(loaded=="logos/czm_skull.png"&&saves==3);
 CZM_SetSpray(7);assert(loaded=="logos/czm_gg.png"&&vars["cl_logofile"]=="czm_gg");
}
'''
        path=self.folder/"selection.cpp";path.write_text(harness);exe=self.folder/"selection"
        subprocess.run(["g++","-std=c++11",str(path),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True)


if __name__ == "__main__":
    unittest.main()
