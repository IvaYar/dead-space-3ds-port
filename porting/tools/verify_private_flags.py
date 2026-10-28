"""Check supported Android ARM flags against the selected Bionic headers."""
import hashlib,json,re,urllib.request
from pathlib import Path
P=Path(__file__).resolve().parents[1];ROOT=P/'analysis/android-abi'
def main():
    sources={}
    for stem,path in (('fcntl-arm-gingerbread.h','arch-arm/asm/fcntl.h'),('fcntl-generic-gingerbread.h','common/asm-generic/fcntl.h')):
        url='https://raw.githubusercontent.com/aosp-mirror/platform_bionic/android-2.3.3_r1/libc/kernel/'+path
        local=ROOT/stem
        if not local.exists():local.write_bytes(urllib.request.urlopen(url,timeout=12).read())
        data=local.read_bytes();sources[stem]={'url':url,'sha256':hashlib.sha256(data).hexdigest(),'text':data.decode()}
    expected={'O_RDONLY':0,'O_WRONLY':1,'O_RDWR':2,'O_CREAT':64,'O_EXCL':128,'O_TRUNC':512,'O_APPEND':1024,'O_LARGEFILE':131072}
    text='\n'.join(v['text'] for v in sources.values())
    for name,value in expected.items():
        match=re.search(r'^#define\s+'+name+r'\s+(0[0-7]+|[0-9]+)\s',text,re.M);assert match,name
        token=match[1];assert int(token,8 if token.startswith('0') else 10)==value,name
    for v in sources.values():del v['text']
    report={'supported_android_arm_flags':expected,'bionic_revision':'android-2.3.3_r1','sources':sources,
        'mount_policy':'writes confined to appdata test-output namespace; bundled assets remain read-only',
        'native_flags':'translated to newlib constants, never passed through as Android integers',
        'horizon_fs_errno':{'module':17,'not_found_descriptions':[112,113,120],'exists_descriptions':[180,185,190],
            'unknown_errors':'EIO','observed_exists_result_hex':'c82044be',
            'reference':'https://github.com/azahar-emu/azahar/blob/master/src/core/file_sys/errors.h'}}
    (ROOT/'private-file-contract.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
