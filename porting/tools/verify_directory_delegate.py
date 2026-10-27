"""Verify the selected APK's distinct internal and app-specific external roots."""
import hashlib,json,struct
from inspect_android_sensor import Dex,PORTING
def contract():
    root=PORTING/'analysis/android-abi';blob=(root/'candidate-sd-classes.dex').read_bytes()
    origin=json.loads((root/'candidate-sd-dex-source.json').read_text());assert hashlib.sha256(blob).hexdigest()==origin['sha256']
    d=Dex(blob);cls=d.inspect('Lcom/ea/blast/GetAppDataDirectoryDelegate;')
    selected=[next(m for m in cls['methods'] if m['name']==n) for n in ('GetAppDataDirectory','GetExternalStorageDirectory')]
    external=next(m for m in d.inspect('Lcom/ea/deadspace/BootstrapActivity;')['methods'] if m['name']=='externalRoot')
    selected.append(external)
    expected=[(0x62,0x76,0x106e,0x1bf,0,0xc,0x106e,0x4d6,0,0xc,0x11),
        (0x71,0x8c,0,0xc,0x11a,0x709,0x206e,0x529,1,0x10a,0x138,0xd,0x62,0x76,0x1071,0x27e,0,0x10c,0x106e,0x4d6,1,0x10c,0x111,0x11a,0,0xfd28),
        (0x12,0x206e,0x3f,1,0x10c,0x138,3,0x111,0x122,0x120,0x1a,0x6f,0x2070,0x50b,1,0x127)]
    for m,want in zip(selected,expected):
        actual=struct.unpack_from('<'+'H'*len(want),blob,m['code_offset']+16)
        assert actual==want and m['instruction_bytes']==len(want)*2
    assert d.methods[0x1bf]['name']=='getFilesDir'
    assert d.methods[0x4d6]['class']=='Ljava/io/File;' and d.methods[0x4d6]['name']=='getAbsolutePath'
    assert d.methods[0x27e]=={k:external[k] for k in ('class','name','signature')}
    assert d.methods[0x3f]=={'class':'Landroid/content/Context;','name':'getExternalFilesDir','signature':'(Ljava/lang/String;)Ljava/io/File;'}
    assert d.strings[0x709]=='mounted'
    return {'dex_sha256':origin['sha256'],'methods':selected,
        'internal':'MainActivity.getFilesDir().getAbsolutePath()',
        'external':'mounted storage -> BootstrapActivity.externalRoot(context).getAbsolutePath(); helper calls Context.getExternalFilesDir(null)',
        'adapter_internal':'appdata:/','adapter_external':'/sdcard/Android/data/com.ea.deadspace/files',
        'observed_game_suffix':'ea/deadspace/published/fonts/Ascender_Uni.ttf',
        'scope':'static DEX proof; external SD path is a compatibility alias into the verified read-only published tree'}
if __name__=='__main__':
    d=contract();(PORTING/'analysis/android-abi/directory-delegate-contract.json').write_text(json.dumps(d,indent=2)+'\n');print('Directory delegate DEX contract verified')
