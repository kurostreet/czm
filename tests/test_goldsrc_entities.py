"""Run the actual GS delta writer with the capacity chosen by serverinfo."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_loading_errors import function

ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/'3rdparty/xash3d-fwgs/engine'
HARNESS=r'''
#include <cassert>
#include <cstring>
#include <stdexcept>
#include <vector>
using qboolean=bool;
enum{ENTITY_BEAM=1,ENTITY_NORMAL=0};
#define S_ERROR ""
#define S_WARN ""
#define FBitSet(v,b) ((v)&(b))
#define SETVISBIT(v,b) ((v)[b/8]|=(1<<(b%8)))
#define BIT(x) (1<<(x))
#define MAX_CLIENTS 32
struct entity_state_t{int number,entityType,messagenum;};
struct cl_entity_t{int index;entity_state_t baseline,curstate;};
struct frame_t{int num_entities;unsigned char flags[2048];};struct sizebuf_t{};
struct delta_header_t{bool remove,custom,instanced;int instanced_baseline_index,offset;};
static struct{int maxEntities;}clgame;
static struct{int maxclients;double mtime[2];entity_state_t instanced_baseline[8];}cl;
static struct{entity_state_t packet_entities[512];int next_client_entities,num_client_entities=512;}cls;
static std::vector<cl_entity_t> entities;
static void Con_DPrintf(const char*,int){}static void Con_Printf(const char*,... ){}
static void Host_Error(const char*,const char*,int){throw std::runtime_error("rejected entity");}
static cl_entity_t*CL_EDICT_NUM(int n){return &entities.at(n);}
static void CL_KillDeadBeams(cl_entity_t*){}
static int CL_GetEntityDelta(const delta_header_t*,int){return 0;}
static void Delta_ReadGSFields(sizebuf_t*,int,const entity_state_t*from,entity_state_t*to,double){*to=*from;}
'''

class GoldSrcEntityTests(unittest.TestCase):
    def test_high_edicts_are_allocated_and_invalid_edicts_stay_rejected(self):
        parser=(ENGINE/'client/parse/cl_parse.c').read_text()
        goldsrc=parser[parser.index('if( proto == PROTO_GOLDSRC )'):]
        # Only the capacity statement of the GoldSrc serverinfo branch.
        allocation=re.search(r'clgame\.maxEntities = MAX_GOLDSRC_EDICTS;',goldsrc)
        self.assertIsNotNone(allocation)
        protocol=(ENGINE/'common/protocol.h').read_text()
        constants='\n'.join(line for line in protocol.splitlines() if re.match(r'#define\s+(MAX_ENTITY_BITS|MAX_GOLDSRC_EDICTS)\s',line))
        writer=function((ENGINE/'client/parse/cl_parse_gs.c').read_text(),'static void CL_DeltaEntityGS(')
        scenario=r'''
int main(){cl.maxclients=32;
 ALLOCATION
 entities.resize(clgame.maxEntities);frame_t frame={};sizebuf_t packet;delta_header_t header={};
 for(int n:{1,1952,2047,clgame.maxEntities-1}){
  const int before=frame.num_entities;CL_DeltaEntityGS(&header,&packet,&frame,n,nullptr);
  assert(frame.num_entities==before+1&&entities.at(n).index==n);
  assert(cls.packet_entities[(cls.next_client_entities-1)%cls.num_client_entities].number==n);
 }
 for(int n:{-1,clgame.maxEntities,1000000}){
  const int before=frame.num_entities;bool rejected=false;
  try{CL_DeltaEntityGS(&header,&packet,&frame,n,nullptr);}catch(const std::runtime_error&){rejected=true;}
  assert(rejected&&frame.num_entities==before);
 }
}
'''.replace('ALLOCATION',allocation.group())
        with tempfile.TemporaryDirectory()as folder:
            p=Path(folder);(p/'main.cpp').write_text(HARNESS+constants+'\n'+writer+scenario)
            subprocess.run(['g++','-std=c++11',str(p/'main.cpp'),'-o',str(p/'check')],check=True)
            subprocess.run([str(p/'check')],check=True)

if __name__=='__main__':unittest.main()
