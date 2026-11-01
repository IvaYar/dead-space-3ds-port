"""Opt-in Windows immutable assets for fresh Azahar SDs; no hard links.

Only assets/apk-assets are junctions. The donor, receipts, font and all writable
data are private files per card. Mutating/negative runners must use full copies.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

P = Path(__file__).resolve().parents[1]
STORE = P.parent/'.local/azahar-resource-store'
SHARED = ('assets', 'apk-assets')
PRIVATE = ('libEAMGameDeadSpace_orig.so', 'assets-verified.txt',
           'apk-assets-verified.txt', 'test-output/font-subset/Ascender_Uni.ttf')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _plain_tree(root):
    root = Path(root)
    if root.lstat().st_file_attributes & 0x400:
        raise ValueError('Dataset tree root cannot be a reparse point')
    result = []
    for parent, directories, names in os.walk(root, followlinks=False):
        for name in directories+names:
            p = Path(parent)/name
            if p.lstat().st_file_attributes & 0x400:
                raise ValueError('Reparse point in dataset: '+str(p))
        result.extend(Path(parent)/name for name in names)
    return sorted(result)


def _entries(root):
    return sorted(({'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
                    'sha256': sha(p)} for p in _plain_tree(root)), key=lambda e: e['path'])


def _identity(entries):
    return hashlib.sha256(json.dumps({'format': 1, 'files': entries}, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _win():
    if os.name != 'nt':
        raise OSError('This pilot requires Windows/NTFS; no writable fallback')
    k = C.WinDLL('kernel32', use_last_error=True)
    k.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, C.c_void_p]
    k.CreateFileW.restype = W.HANDLE
    k.CloseHandle.argtypes = [W.HANDLE]
    return k


def _seal(root):
    """Apply protected, inheritable read/execute ACL to this NEW dataset only.

    Deny data/append/EA/attribute writes and delete, without denying the read
    control/synchronize bits that generic FILE_WRITE would also deny. The
    owner can deliberately change ACLs; this is protection against normal
    runner writes, not a security boundary against a malicious machine owner.
    """
    root = Path(root).resolve()
    if STORE.resolve() not in root.parents or not re.fullmatch('[a-f0-9]{64}', root.name):
        raise ValueError('Refuse ACL changes outside a newly created dataset')
    sid = re.search(rb'S-1-(?:\d+-)*\d+', subprocess.check_output(
        ['whoami', '/user', '/fo', 'csv', '/nh'])).group().decode('ascii')
    adv = C.WinDLL('advapi32', use_last_error=True)
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(C.c_void_p), C.c_void_p]
    adv.GetSecurityDescriptorDacl.argtypes = [C.c_void_p, C.POINTER(W.BOOL), C.POINTER(C.c_void_p), C.POINTER(W.BOOL)]
    adv.SetNamedSecurityInfoW.argtypes = [W.LPWSTR, C.c_int, W.DWORD, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
    adv.SetNamedSecurityInfoW.restype = W.DWORD
    descriptor = C.c_void_p()
    sddl = f'D:P(D;OICI;0x10156;;;{sid})(A;OICI;0x1200a9;;;{sid})(A;OICI;FA;;;SY)'
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, C.byref(descriptor), None):
        raise C.WinError(C.get_last_error())
    try:
        present, defaulted, dacl = W.BOOL(), W.BOOL(), C.c_void_p()
        if not adv.GetSecurityDescriptorDacl(descriptor, C.byref(present), C.byref(dacl), C.byref(defaulted)):
            raise C.WinError(C.get_last_error())
        code = adv.SetNamedSecurityInfoW(str(root), 1, 0x80000004, None, None, dacl, None)
        if code:
            raise C.WinError(code)
    finally:
        k = _win()
        k.LocalFree.argtypes = [C.c_void_p]
        k.LocalFree(descriptor)


def _write_denied(path):
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_BINARY)
    except PermissionError:
        return True
    else:
        os.close(descriptor)  # Never write/truncate if the ACL is wrong.
        return False


def verify_dataset(dataset):
    dataset = Path(dataset).resolve()
    if STORE.resolve() not in dataset.parents:
        raise ValueError('Dataset outside private store')
    manifest = json.loads((dataset/'manifest.json').read_text())
    actual = _entries(dataset/'data')
    if actual != manifest['files'] or _identity(actual) != dataset.name:
        raise ValueError('Dataset content/manifest/directory ID mismatch')
    if not all(_write_denied(dataset/'data'/name) for name in
               ['assets/published/data/achievements.sb', 'apk-assets/bundled-game.zip', PRIVATE[0]]):
        raise PermissionError('Shared dataset must deny writes; no writable fallback')
    return manifest


def ensure_dataset(source):
    """Copy once to a new content ID, then seal; never chmod the source."""
    source = Path(source).resolve()
    selected = []
    for name in SHARED:
        selected.extend(p for p in _plain_tree(source/name))
    selected += [source/name for name in PRIVATE]
    entries = sorted(({'path': p.relative_to(source).as_posix(), 'bytes': p.stat().st_size,
                       'sha256': sha(p)} for p in selected), key=lambda e: e['path'])
    dataset = STORE/'datasets'/_identity(entries)
    if dataset.exists():
        verify_dataset(dataset)
        return dataset
    dataset.mkdir(parents=True)
    for entry in entries:
        target = dataset/'data'/entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/entry['path'], target)
        if sha(target) != entry['sha256']:
            raise ValueError('Dataset copy verification failed')
    (dataset/'manifest.json').write_text(json.dumps({'format': 1, 'dataset_id': dataset.name,
        'shared_directories': list(SHARED), 'private_copies': list(PRIVATE),
        'files': entries}, indent=2)+'\n')
    _seal(dataset)
    verify_dataset(dataset)
    return dataset


def _junction(link, target):
    k = _win()
    link, target = Path(link), Path(target).resolve()
    if link.exists() or link.is_symlink():
        raise FileExistsError(link)
    link.mkdir()
    substitute = ('\\??\\'+str(target)).encode('utf-16-le')
    display = str(target).encode('utf-16-le')
    names = substitute+b'\0\0'+display+b'\0\0'
    raw = struct.pack('<IHHHHHH', 0xa0000003, 8+len(names), 0,
                      0, len(substitute), len(substitute)+2, len(display))+names
    handle = k.CreateFileW(str(link), 0x40000000, 7, None, 3, 0x02200000, None)
    if handle == W.HANDLE(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        k.DeviceIoControl.argtypes = [W.HANDLE, W.DWORD, C.c_void_p, W.DWORD, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
        count = W.DWORD()
        if not k.DeviceIoControl(handle, 0x900a4, raw, len(raw), None, 0, C.byref(count), None):
            raise C.WinError(C.get_last_error())
    finally:
        k.CloseHandle(handle)
    if not os.path.isjunction(link) or link.resolve() != target:
        raise ValueError('Unexpected junction target')


def prepare_card(card, dataset):
    """Fresh card only. Callers that mutate assets must not use this mode."""
    card = Path(card).absolute()
    if card.exists():
        raise FileExistsError('Never overwrite/reuse an existing card: '+str(card))
    if (P/'analysis').resolve() not in card.resolve().parents:
        raise ValueError('Card must be a fresh workspace analysis SD')
    dataset = Path(dataset).resolve()
    manifest = verify_dataset(dataset)
    card.mkdir(parents=True)
    for name in SHARED:
        _junction(card/name, dataset/'data'/name)
    for name in PRIVATE:
        target = card/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dataset/'data'/name, target)
        if os.stat(target).st_nlink != 1 or target.resolve() == (dataset/'data'/name).resolve():
            raise ValueError('Private leaf must be an independent regular file')
    for entry in manifest['files']:
        if sha(card/entry['path']) != entry['sha256']:
            raise ValueError('Card path SHA mismatch')
    if not _write_denied(card/'assets/published/data/achievements.sb'):
        raise PermissionError('Writes through junction are not blocked')
    shared_bytes = sum(e['bytes'] for e in manifest['files'] if e['path'].split('/')[0] in SHARED)
    private_bytes = sum(e['bytes'] for e in manifest['files'])-shared_bytes
    return {'format': 1, 'dataset_id': dataset.name, 'files_verified': len(manifest['files']),
            'shared_bytes': shared_bytes, 'private_seed_bytes': private_bytes,
            'junctions': list(SHARED), 'hard_links_used': False,
            'writes_to_shared_asset_denied': True, 'dataset_path': str(dataset)}
