"""Check staged blobs, including force-added/renamed private binaries.

No index/worktree mutation. This conservative allowlist complements gitignore;
it cannot infer copyright ownership from arbitrary readable text or images.
"""
import argparse
import json
from pathlib import PurePosixPath
import re
import subprocess
import sys

TEXT = {'.py', '.c', '.cpp', '.h', '.hpp', '.s', '.md', '.txt', '.log', '.json',
        '.jsonl', '.pica', '.rsf', '.diff', '.yaml', '.yml', '.toml', '.ps1'}
PRIVATE_PARTS = {'sdmc', 'apk-assets', 'assets', 'test-output', '__pycache__',
                 '.local', 'emulator-checkpoints', 'candidate-sd'}
MAGIC = ((b'\x7fELF', 'ELF'), (b'MZ', 'Windows executable/DLL'),
         (b'PK\x03\x04', 'ZIP/APK archive'), (b'PK\x05\x06', 'ZIP archive'),
         (b'7z\xbc\xaf\x27\x1c', '7z archive'), (b'\x28\xb5\x2f\xfd', 'zstd archive'))


def git(repo, *arguments):
    return subprocess.run(['git', '-C', str(repo), *arguments], capture_output=True, check=True).stdout


def private_json(obj):
    if isinstance(obj, dict):
        if any(k in obj for k in ['argument_words', 'wait_stack', 'userdata_words', 'object_words']):
            return True
        return any(private_json(v) for v in obj.values())
    if isinstance(obj, list):
        return any(private_json(v) for v in obj)
    return False


def inspect_blob(path, data):
    p = PurePosixPath(path.replace('\\', '/'))
    lower = p.as_posix().lower()
    parts = {part.lower() for part in p.parts}
    reasons = []
    if PRIVATE_PARTS & parts or lower.startswith(('porting/private/', 'porting/toolchain/')):
        reasons.append('private data/cache/toolchain path')
    if re.search(r'(^|/)(threads-[^/]+|destructors)\.json$', lower):
        reasons.append('private worker/object snapshot')
    suffix = p.suffix.lower()
    if suffix not in TEXT and lower not in {'.gitignore', '.gitattributes', '.githooks/pre-commit'}:
        reasons.append('non-text artifact requires separate publication review')
    for prefix, name in MAGIC:
        if data.startswith(prefix):
            reasons.append(name+' content, including a renamed file')
    if len(data) > 5*1024*1024:
        reasons.append('staged blob exceeds5MiB; review before publication')
    if b'\0' in data:
        reasons.append('binary NUL bytes in a text-only publication path')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        reasons.append('blob is not UTF-8 text')
    else:
        if suffix == '.json':
            try:
                if private_json(json.loads(text)):
                    reasons.append('private object/stack data inside JSON')
            except json.JSONDecodeError:
                pass  # Syntax validation is a separate concern.
    return sorted(set(reasons))


def check(repo):
    index = {}
    for record in git(repo, 'ls-files', '--stage', '-z').split(b'\0'):
        if not record:
            continue
        meta, path = record.split(b'\t', 1)
        mode, oid, stage = meta.split()
        if stage == b'0':
            index[path.decode('utf-8')] = (mode, oid.decode('ascii'))
    names = [p.decode('utf-8') for p in git(repo, 'diff', '--cached', '--name-only',
        '-z', '--diff-filter=ACMR', '--no-renames').split(b'\0') if p]
    rejected = []
    for path in names:
        mode, oid = index[path]
        if mode not in {b'100644', b'100755'}:
            rejected.append({'path': path, 'reasons': ['staged link/submodule requires review']})
            continue
        size = int(git(repo, 'cat-file', '-s', oid))
        if size > 5*1024*1024:
            reasons = ['staged blob exceeds5MiB; review before publication']
        else:
            reasons = inspect_blob(path, git(repo, 'cat-file', 'blob', oid))
        if reasons:
            rejected.append({'path': path, 'reasons': reasons})
    return {'passed': not rejected, 'staged_files_checked': len(names),
            'rejected': rejected, 'worktree_not_used_as_blob_source': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    args = parser.parse_args()
    result = check(args.repo)
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
