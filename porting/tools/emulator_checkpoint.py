"""Private Azahar 2126.2 state + matching mutable SD files, never a CIA/savegame.

Source API: azahar-emu/azahar, tag2126.2, src/citra_libretro/citra_libretro.cpp.
States require exactly the same emulator DLL, CXI and runner profile. All
commercial data and serialized memory remain in ignored analysis directories.
"""
import ctypes as C
import hashlib,json,shutil,uuid
from pathlib import Path

P=Path(__file__).resolve().parents[1]
PRIVATE=P/'analysis/emulator-checkpoints'
MUTABLE=('test-output/save-bridge','test-output/texture-pages')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def inside(path,root):
    path=Path(path).resolve();root=Path(root).resolve()
    if path==root or root not in path.parents:raise ValueError('Checkpoint path must be inside '+str(root))
    return path

def files(root):
    if not root.exists():return []
    result=[]
    for path in root.rglob('*'):
        if path.is_file():inside(path,root);result.append(path)
    return result

def api(core):
    core.retro_serialize_size.argtypes=[];core.retro_serialize_size.restype=C.c_size_t
    core.retro_serialize.argtypes=[C.c_void_p,C.c_size_t];core.retro_serialize.restype=C.c_bool
    core.retro_unserialize.argtypes=[C.c_void_p,C.c_size_t];core.retro_unserialize.restype=C.c_bool

def save(core,directory,card,profile,app,library):
    card=inside(card,P/'analysis/azahar-smoke')
    directory=inside(directory,PRIVATE);directory.mkdir(parents=True,exist_ok=True)
    generation=directory/('generation-'+uuid.uuid4().hex);generation.mkdir()
    api(core);size=core.retro_serialize_size()
    if not 0<size<=1024*1024*1024:raise RuntimeError('Emulator did not provide a bounded savestate')
    data=C.create_string_buffer(size)
    if not core.retro_serialize(data,size):raise RuntimeError('Emulator savestate failed')
    state=generation/'emulator.state';state.write_bytes(data.raw)
    manifest={'format':'DS_AZAHAR_PRIVATE_CHECKPOINT_V1','profile':profile,
        'cxi_sha256':digest(app),'library_sha256':digest(library),'state_bytes':size,
        'state_sha256':digest(state),'files':{}}
    for root in MUTABLE:
        for source in files(card/root):
            name=source.relative_to(card).as_posix();target=generation/'sd'/name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            manifest['files'][name]={'bytes':target.stat().st_size,'sha256':digest(target)}
    journal=card/'engine-azahar-log.txt';shutil.copyfile(journal,generation/'journal.log')
    manifest['journal_sha256']=digest(generation/'journal.log')
    (generation/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    pending=directory/'current.pending.json';pending.write_text(json.dumps({'generation':generation.name})+'\n')
    pending.replace(directory/'current.json')
    return {'generation':generation.name,'state_bytes':size,'state_sha256':manifest['state_sha256']}

def load(core,directory,card,profile,app,library):
    card=inside(card,P/'analysis/azahar-smoke')
    directory=inside(directory,PRIVATE)
    pointer=json.loads((directory/'current.json').read_text())
    generation=inside(directory/pointer['generation'],directory)
    manifest=json.loads((generation/'manifest.json').read_text())
    assert manifest['format']=='DS_AZAHAR_PRIVATE_CHECKPOINT_V1'
    assert manifest['profile']==profile,'Checkpoint runner profile differs'
    assert manifest['cxi_sha256']==digest(app),'Checkpoint CXI differs'
    assert manifest['library_sha256']==digest(library),'Checkpoint emulator DLL differs'
    state=generation/'emulator.state';assert state.stat().st_size==manifest['state_bytes']
    assert digest(state)==manifest['state_sha256']
    assert digest(generation/'journal.log')==manifest['journal_sha256']
    for name,meta in manifest['files'].items():
        source=inside(generation/'sd'/name,generation/'sd')
        assert any(name.startswith(root+'/') for root in MUTABLE)
        assert source.stat().st_size==meta['bytes'] and digest(source)==meta['sha256'],name
    # Preserve the complete pre-restore private data before replacing any leaf.
    # This never touches original assets, APKs or the user's console saves.
    backup=directory/('restore-backup-'+uuid.uuid4().hex);backup.mkdir()
    journal=card/'engine-azahar-log.txt'
    if journal.exists():shutil.copyfile(journal,backup/'journal.log')
    previous=[]
    for root in MUTABLE:
        for target in files(card/root):
            name=target.relative_to(card).as_posix();copy=backup/name
            copy.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(target,copy)
            previous.append(name)
    for root in MUTABLE:
        for target in files(card/root):
            name=target.relative_to(card).as_posix()
            if name not in manifest['files']:inside(target,card/root).unlink()
    for name in manifest['files']:
        target=inside(card/name,card);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(generation/'sd'/name,target)
    api(core);data=state.read_bytes();buffer=C.create_string_buffer(data,len(data))
    try:
        if not core.retro_unserialize(buffer,len(data)):raise RuntimeError('Emulator checkpoint restore failed')
    except BaseException:
        for root in MUTABLE:
            for target in files(card/root):inside(target,card/root).unlink()
        for name in previous:
            target=inside(card/name,card);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(backup/name,target)
        if (backup/'journal.log').exists():shutil.copyfile(backup/'journal.log',journal)
        elif journal.exists():journal.unlink()
        raise
    # HLE backends may reopen writable handles while loading. Reapply bytes
    # after those handles exist, before the guest executes another instruction.
    for name in manifest['files']:
        shutil.copyfile(generation/'sd'/name,inside(card/name,card))
    # Native FS file offsets are restored by the emulator; restore the journal
    # prefix after HLE backends have reopened their handles, before retro_run.
    shutil.copyfile(generation/'journal.log',journal)
    return {'generation':generation.name,'state_bytes':len(data),'backup':str(backup.relative_to(P))}
