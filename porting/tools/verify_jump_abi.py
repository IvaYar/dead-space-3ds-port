"""Pin the Android ARM32 context contract against primary AOSP headers/code."""
import hashlib,json,re,urllib.request
from pathlib import Path
P=Path(__file__).resolve().parents[1]
ROOT='https://raw.githubusercontent.com/aosp-mirror/platform_bionic/android-2.3.3_r1/libc/'
def main():
    paths=('arch-arm/include/machine/setjmp.h','include/setjmp.h','arch-arm/bionic/setjmp.S','arch-arm/bionic/_setjmp.S')
    sources={}
    for path in paths:
        data=urllib.request.urlopen(ROOT+path,timeout=30).read();sources[path]=(data,data.decode())
    layout=sources[paths[0]][1];header=sources[paths[1]][1];asm=sources[paths[2]][1]
    assert re.search(r'#define\s+_JBLEN\s+64\b',layout)
    assert 'typedef long jmp_buf[_JBLEN]' in header
    assert '_JB_MAGIC__SETJMP\t0x4278f500' in layout and '_JB_MAGIC_SETJMP\t0x4278f501' in layout
    assert re.search(r'stmia\s+r1,\s*\{r4-r14\}',asm) and re.search(r'ldmia\s+r2,\s*\{r4-r14\}',asm)
    assert 'd8-d15' in asm and 'fpscr' in asm
    donor=(P/'analysis/candidate-sd/libEAMGameDeadSpace_orig.so').read_bytes()
    assert hashlib.sha256(donor).hexdigest()=='dd42272365d0abd8ad9c89450bb7f869ee4ac0ad548525758e6a1e7df4d3c1eb'
    # .text file offset == virtual address in this selected ELF. Caller adds 20
    # to its context pointer then BLs setjmp@plt; return PC is 0x397168.
    assert donor[0x397160:0x397168]==bytes.fromhex('140080e25480f2eb')
    report={'aosp_tag':'android-2.3.3_r1','word_bytes':4,'jmp_buf_words':64,'jmp_buf_bytes':256,
        'layout_words':{'magic':0,'signal_mask':1,'vfp_d8_d15':2,'fpscr':18,'core_r4_r14':19,'reserved':30},
        'magic':{'setjmp':'4278f501','_setjmp':'4278f500'},'minimum_adapter_alignment':4,
        'adapter_reserved_words':{'owner_tls':30,'tag':31},'signal_profile':'empty mask only; no POSIX signal delivery',
        'selected_donor_caller_offset':'00397168','observed_donor_buffer_alignment':4,
        'native_newlib_buffer_reinterpretation':False,'sources':{path:{'url':ROOT+path,'sha256':hashlib.sha256(data).hexdigest()} for path,(data,_) in sources.items()}}
    target=P/'analysis/android-abi/jump-abi-contract.json';target.write_text(json.dumps(report,indent=2)+'\n');print(target)
if __name__=='__main__':main()
