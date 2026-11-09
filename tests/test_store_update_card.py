"""Execute the actual native bell update state: only Play offers create a card; history survives."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT = Path(__file__).resolve().parents[1]

PREAMBLE = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
static bool russian=true, selfUpdate=false, hasOffer=false;
static int installed=40300000, offeredCode, queryCount;
static double offeredBytes;
static void Q_strncpy(char *dst,const char *src,size_t size){snprintf(dst,size,"%s",src);}
bool CZM_IsRussian(){return russian;}
bool CZM_NetCanSelfUpdate(){return selfUpdate;}
int CZM_NetVersionCode(){return installed;}
bool CZM_NetStoreUpdate(int *code,double *bytes){queryCount++;*code=offeredCode;*bytes=offeredBytes;return hasOffer;}
'''

STATE = r'''
static struct {
 int newsLast=8, newsSeen=3;
 struct {int code;char version[16],notes[512],notes_en[512];} play[3]={};
 CzmUpdateInfo update={};
} s_online;
'''

SCENARIO = r'''
int main(int argc,char **){
 selfUpdate=argc>1;
 hasOffer=true;offeredCode=40300001;offeredBytes=12345678;
 s_online.play[0].code=40300002;strcpy(s_online.play[0].version,"1.37.0");strcpy(s_online.play[0].notes,"Wrong future release");
 s_online.play[1].code=40300001;strcpy(s_online.play[1].version,"1.36.1");
 strcpy(s_online.play[1].notes,"Обновление раскладки.");strcpy(s_online.play[1].notes_en,"Layout update.");
 StoreUpdateFrame(10);
 if(selfUpdate){assert(!queryCount&&!CZM_Update());return 0;}
 const auto *card=CZM_Update();assert(card&&card->store&&card->available);
 assert(card->code==40300001&&card->size==12345678);
 assert(!strcmp(card->version,"1.36.1")&&!strcmp(card->notes,"Обновление раскладки."));
 // Never fill a store card from another release's notes, even if those notes are newer.
 russian=false;StoreUpdateFrame(16);assert(!strcmp(CZM_Update()->notes,"Layout update."));
 s_online.play[1].code=0;StoreUpdateFrame(22);
 assert(CZM_Update()&&CZM_Update()->version[0]==0&&CZM_Update()->notes[0]==0);
 // A news item or prepared bundle alone cannot create/retain an update card.
 hasOffer=false;StoreUpdateFrame(28);assert(!CZM_Update());
 assert(s_online.newsLast==8&&s_online.newsSeen==3);
 // Installed/same or older codes are rejected even if a stale Play callback claims availability.
 hasOffer=true;offeredCode=installed;StoreUpdateFrame(34);assert(!CZM_Update());
 offeredCode=installed-1;StoreUpdateFrame(40);assert(!CZM_Update());
 // Updating the app clears the card, while the ordinary news history remains readable.
 offeredCode=installed+1;StoreUpdateFrame(46);assert(CZM_Update());
 installed=offeredCode;StoreUpdateFrame(52);assert(!CZM_Update());
 assert(s_online.newsLast==8&&s_online.newsSeen==3);
 puts("PLAY_NATIVE_CARD_AND_HISTORY_OK");
}
'''


class NativeStoreUpdateCardTests(unittest.TestCase):
    def test_account_offer_release_notes_and_installed_version(self):
        online = (ROOT / 'czm/menu/CzmOnline.cpp').read_text()
        menu = (ROOT / 'czm/menu/CzmMenu.h').read_text()
        source = PREAMBLE + function(menu, 'struct CzmUpdateInfo\n') + ';\n' + STATE
        source += function(online, 'static void StoreUpdateFrame(')
        source += function(online, 'const CzmUpdateInfo *CZM_Update(') + SCENARIO
        with tempfile.TemporaryDirectory(prefix='czm-store-card-') as folder:
            path = Path(folder)
            (path / 'check.cpp').write_text(source)
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', str(path / 'check.cpp'),
                            '-o', str(path / 'check')], check=True)
            result = subprocess.run([str(path / 'check')], text=True, capture_output=True, check=True)
            self.assertIn('PLAY_NATIVE_CARD_AND_HISTORY_OK', result.stdout)
            subprocess.run([str(path / 'check'), 'site-build'], check=True)


if __name__ == '__main__':
    unittest.main()
