"""ARM execution: button edges, observed selection, pointer ABI and bounds."""
import json
from pathlib import Path
import struct
import subprocess
import sys
from test_arm_loader import ARMCore,PORTING
from unicorn.arm_const import UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC
sys.path.insert(0,str(PORTING/'tools'))
from azahar_resource_store import sha

HARNESS=r'''
#include <3ds.h>
#include <string.h>
#include "ds10_jni.h"
static DS10Context bridge;
static u32 current_frame;
static touchPosition point;
static u32 count,trace[64][5];
void *memset(void *p,int v,size_t n){volatile unsigned char *d=p;while(n--)*d++=v;return p;}
int strcmp(const char *a,const char *b){while(*a && *a==*b){++a;++b;}return (unsigned char)*a-(unsigned char)*b;}
static void report(const char *fmt,...){(void)fmt;}
void hidTouchRead(touchPosition *p){*p=point;}
static void DS_JNI_SOFT pointer(DSJniHandle *e,void *o,int32_t event,int32_t module,int32_t id,float x,float y){
    (void)e;(void)o;(void)id;
    union {float f;u32 u;} a={x},b={y};
    trace[count][0]=event;trace[count][1]=module;trace[count][2]=a.u;trace[count++][3]=b.u;
}
static void DS_JNI_SOFT keydown(DSJniHandle *e,void *o,int32_t module,int32_t key,int32_t system){
    (void)e;(void)o;trace[count][0]=2;trace[count][1]=module;trace[count][2]=key;trace[count++][3]=system;
}
static void DS_JNI_SOFT keyup(DSJniHandle *e,void *o,int32_t module,int32_t key,int32_t system){
    (void)e;(void)o;trace[count][0]=3;trace[count][1]=module;trace[count][2]=key;trace[count++][3]=system;
}
static u32 exported(const char *name){
    if(!strcmp(name,"Java_com_ea_blast_TouchSurfaceAndroid_NativeOnPointerEvent"))return (u32)pointer;
    if(!strcmp(name,"Java_com_ea_blast_KeyboardAndroid_NativeOnKeyDown"))return (u32)keydown;
    return (u32)keyup;
}
#include "native_menu_input.h"
int init(void){bridge.magic=0x44533130;bridge.platform.width=400;bridge.platform.height=240;return menu_input_init();}
int sample(u32 down,u32 held){(void)down;return menu_input_sample(held);}
int close_input(void){return menu_input_close();}
u32 get(u32 row,u32 col){return trace[row][col];}
u32 events(void){return count;}
u32 capabilities(void){return bridge.platform.capabilities;}
void position(u32 x,u32 y){point.px=x;point.py=y;}
void frame_number(u32 f){current_frame=f;}
u32 confirmation(void){return menu_confirmation_frame;}
void observe(u32 crc){menu_input_observe(crc);}
'''

def main():
    d=PORTING.parent/'.local/native-menu-input-tests'
    d.mkdir(parents=True,exist_ok=True)
    (d/'harness.c').write_text(HARNESS)
    gcc=PORTING/'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-gcc.exe'
    command=[str(gcc),'-march=armv6k','-mfpu=vfp','-mfloat-abi=hard','-O2','-fno-builtin','-nostdlib',
        '-I'+str(PORTING/'tests'),'-I'+str(PORTING/'3ds/include'),'-I'+str(PORTING/'toolchain/devkitpro/libctru/include'),
        str(d/'harness.c'),str(PORTING/'3ds/source/ds23_touch.c'),'-Wl,-Ttext=0x100000,-e,init','-o',str(d/'input.elf')]
    subprocess.run(command,check=True)
    arm=ARMCore(b'',d/'input.elf')
    arm.uc.reg_write(UC_ARM_REG_C1_C0_2,0x00f00000);arm.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
    call=arm.call
    assert call('init')==0 and call('capabilities')&2
    def event(row):return [call('get',row,c) for c in range(4)]
    def xy(row):return tuple(struct.unpack('<f',struct.pack('<I',v))[0] for v in event(row)[2:])
    # Neither a fade nor an already-selected row may activate the scene.
    call('frame_number',100);call('sample',1,1);call('sample',0,0)
    assert call('events')==0
    call('observe',0x7296717d);call('sample',1<<6,1<<6);call('sample',0,0)
    assert call('events')==0
    for frame,crc,key,expected in [(110,0x7296717d,1<<7,(200.,134.)),(120,0x0ded835d,1<<6,(200.,103.)),(130,0x223b5e75,1,(355.,225.))]:
        call('frame_number',frame);call('observe',crc)
        n=call('events');assert call('sample',key,key)==0
        assert event(n)[:2]==[0x6000c,1000] and xy(n)==expected
        call('frame_number',frame+1)
        assert call('sample',0,key)==0 and event(n+1)[0]==0x8000c
        assert call('sample',0,key)==0 and call('events')==n+2
        call('sample',0,0)
    assert call('confirmation')==130
    n=call('events');call('sample',2,2);call('sample',0,2);call('sample',0,0)
    assert event(n)==[2,600,4,0] and event(n+1)==[3,600,4,0] and call('events')==n+2
    # This menu pilot exposes physical buttons only. A stylus cannot bypass it.
    n=call('events');call('position',284,225);call('sample',0,1<<20)
    assert call('events')==n
    call('sample',2,2);assert call('close_input')==0
    assert event(n)==[2,600,4,0] and event(n+1)==[3,600,4,0]
    assert call('capabilities')&2==0 and call('confirmation')==0
    assert call('init')==0
    n=call('events');call('frame_number',200);call('observe',0x7296717d);call('sample',0,1<<7)
    call('observe',0x7296717d) # stale framebuffer must not re-enable navigation
    call('frame_number',201);call('sample',0,0);call('sample',0,1<<6)
    assert call('events')==n+2
    call('sample',0,0);call('frame_number',205);call('observe',0x7296717d);call('sample',0,1<<6)
    assert call('events')==n+2 # Down ignored by engine: UP must not click Normal.
    assert call('close_input')==0 and call('confirmation')==0
    result={'passed':True,'checks':['D-pad Normal/Easy','A confirm and bounded release','no held-key repeat','B DOWN/UP ABI and close release','unknown/fading menu ignores selection','selected row never re-clicked','stale readback cannot re-enable input','stylus cannot bypass bounded button pilot'],
        'header_sha256':sha(PORTING/'tests/native_menu_input.h'),'touch_sha256':sha(PORTING/'3ds/source/ds23_touch.c'),
        'ARM_elf_sha256':sha(d/'input.elf'),'hardware_tested':False}
    (d/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
