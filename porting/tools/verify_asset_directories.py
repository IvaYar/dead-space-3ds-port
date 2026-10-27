"""Record the read-only virtual published asset tree, not APK AssetManager root."""
import hashlib,json,zlib
from pathlib import Path
PORTING=Path(__file__).resolve().parents[1]
def contract():
    root=PORTING/'analysis/candidate-sd/assets/published'
    directories={}
    for relative in ('','data','textures'):
        names=sorted(p.name for p in (root/relative).iterdir())
        data=b''.join(n.encode('utf-8')+b'\0' for n in names)
        directories[relative]={'names':names,'count':len(names),'names_crc32':f'{zlib.crc32(data):08x}'}
    font=root/'fonts/Ascender_Uni.ttf'
    return {'profile':'virtual published root; excludes APK bootstrap assets',
        'source':'analysis/candidate-sd/assets/published','read_only':True,
        'directories':directories,'font':{'bytes':font.stat().st_size,'sha256':hashlib.sha256(font.read_bytes()).hexdigest()},
        'jni_path_encoding':'modified UTF-8 -> UTF-16 -> filesystem UTF-8',
        'filesystem_name_encoding':'strict scalar UTF-8 -> UTF-16 -> modified UTF-8',
        'limits':{'arrays':8,'elements_per_array':2048,'extra_strings':2048,'local_global_refs':128,'mutf8_bytes':255},
        'list_spec':'https://developer.android.com/reference/android/content/res/AssetManager#list(java.lang.String)',
        'array_spec':'https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#newobjectarray'}
def write():
    d=contract();(PORTING/'analysis/asset-directory-contract.json').write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8');return d
if __name__=='__main__':
    d=write();print({p:(v['count'],v['names_crc32']) for p,v in d['directories'].items()})
