"""Extract and verify the selected user's genuine APK assets on the emulator SD."""
import hashlib,io,json,shutil,zipfile
from pathlib import Path,PurePosixPath
P=Path(__file__).resolve().parents[1]
def main():
    contract=json.loads((P/'analysis/android-abi/apk-asset-namespace-contract.json').read_text())
    with zipfile.ZipFile(P.parent/contract['source_archive']) as archive:blob=archive.read(contract['apk_member'])
    assert hashlib.sha256(blob).hexdigest()==contract['apk_sha256'],'Wrong APK'
    root=P/'analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace/apk-assets';root.mkdir(parents=True,exist_ok=True)
    manifest=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as apk:
        expected={x['path']:x for x in contract['manifest']}
        actual={x.filename[7:]:x for x in apk.infolist() if x.filename.startswith('assets/') and not x.is_dir()}
        assert set(actual)==set(expected)
        for name,item in sorted(actual.items()):
            parts=PurePosixPath(name).parts
            assert parts and not name.startswith('/') and all(p not in ('.','..') and ':' not in p and '\\' not in p for p in parts)
            assert item.file_size==expected[name]['bytes'] and f'{item.CRC:08x}'==expected[name]['zip_crc32']
            assert item.compress_type==expected[name]['zip_method']
            out=root.joinpath(*parts);out.parent.mkdir(parents=True,exist_ok=True)
            # Own local copies only; originals remain untouched. ZipFile also
            # validates CRC when the source stream reaches EOF.
            with apk.open(item) as source,out.open('wb') as target:shutil.copyfileobj(source,target,1024*1024)
            digest=hashlib.sha256()
            with out.open('rb') as f:
                while chunk:=f.read(1024*1024):digest.update(chunk)
            assert out.stat().st_size==item.file_size
            manifest.append({'path':name,'bytes':item.file_size,'sha256':digest.hexdigest(),'zip_method':item.compress_type})
        assert {f.relative_to(root).as_posix() for f in root.rglob('*') if f.is_file()}==set(expected),'Unexpected files in APK asset root'
    receipt=f"DS_APK_ASSETS_V1 {contract['apk_sha256']} {len(manifest)}\n"
    (root.parent/'apk-assets-verified.txt').write_bytes(receipt.encode('ascii'))
    report={'apk_sha256':contract['apk_sha256'],'files':len(manifest),'bytes':sum(x['bytes'] for x in manifest),
        'receipt':receipt.strip(),'root_children':contract['asset_root_children'],'manifest':manifest,'game_files_published':False}
    (P/'analysis/emulator-apk-assets.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Verified APK assets:',report['files'],'files,',report['bytes'],'bytes')
if __name__=='__main__':main()
