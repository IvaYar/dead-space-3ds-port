"""Build the pinned upstream GPU library separately from the passed runtime SDK."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,io,json,shutil,subprocess,urllib.request,zipfile
from pathlib import Path
import build_stage1 as base
P=base.PORTING
COMMIT='9f21cf7b380ce6f9e01a0420f19f0763e5443ca7'
ARCHIVE_SHA='61674258367a22639da00214ba84d2556ebf0c85ddc63739085dd8feeeb5bb86'
SOURCE=P/'toolchain/citro3d-source'
PREFIX=P/'toolchain/citro3d'

def main():
    cache=P/'toolchain/cache'/('citro3d-'+COMMIT+'.zip');cache.parent.mkdir(exist_ok=True)
    if not cache.exists():cache.write_bytes(urllib.request.urlopen('https://codeload.github.com/devkitPro/citro3d/zip/'+COMMIT).read())
    raw=cache.read_bytes();assert hashlib.sha256(raw).hexdigest()==ARCHIVE_SHA
    SOURCE.mkdir(exist_ok=True);z=zipfile.ZipFile(io.BytesIO(raw));root=z.namelist()[0];inputs={}
    for name in z.namelist():
        if name.endswith('/'):continue
        relative=Path(name).relative_to(root);target=(SOURCE/relative).resolve()
        assert SOURCE.resolve() in target.parents
        data=z.read(name)
        if target.exists():assert target.read_bytes()==data,'Upstream source has local edits: '+str(relative)
        else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        inputs[relative.as_posix()]=hashlib.sha256(data).hexdigest()
    objects=PREFIX/'objects';objects.mkdir(parents=True,exist_ok=True)
    sources=sorted((SOURCE/'source').glob('*.c'))+sorted((SOURCE/'source/maths').glob('*.c'))
    assert len({s.stem for s in sources})==len(sources)
    flags=base.ARCH+['-O2','-g','-Wall','-Werror','-Wno-sizeof-array-div','-mword-relocations',
        '-ffunction-sections','-fdata-sections','-fomit-frame-pointer','-fno-math-errno','-DNDEBUG=1','-D__3DS__','-DCITRO3D_BUILD',
        '-I'+str(SOURCE/'include'),'-I'+str(base.DKP/'libctru/include')]
    def compile_one(source):
        target=objects/(source.stem+'.o')
        result=subprocess.run([str(base.GCC),*flags,'-c',str(source),'-o',str(target)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(source.name+'\n'+result.stdout.decode(errors='replace'))
        return target
    with ThreadPoolExecutor(max_workers=4) as pool:built=list(pool.map(compile_one,sources))
    (PREFIX/'lib').mkdir(exist_ok=True)
    subprocess.run([str(base.DKP/'devkitARM/bin/arm-none-eabi-ar.exe'),'rcs',str(PREFIX/'lib/libcitro3d.a'),*map(str,built)],check=True)
    shutil.copytree(SOURCE/'include',PREFIX/'include',dirs_exist_ok=True)
    shutil.copyfile(SOURCE/'LICENSE',PREFIX/'LICENSE')
    manifest={'repository':'https://github.com/devkitPro/citro3d','commit':COMMIT,'archive_sha256':ARCHIVE_SHA,
        'license':'Zlib; upstream LICENSE retained; sources unmodified','source_sha256':inputs,
        'library_sha256':hashlib.sha256((PREFIX/'lib/libcitro3d.a').read_bytes()).hexdigest(),'source_files':len(sources)}
    (PREFIX/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Built isolated Citro3D:',len(sources),'sources',manifest['library_sha256'])

if __name__=='__main__':main()
