"""Copy and verify the selected user's extracted assets into the private emulator SD."""
import hashlib,json,shutil,time
from pathlib import Path
PORTING=Path(__file__).resolve().parents[1]
def main():
    source=PORTING/'analysis/candidate-sd/assets'
    root=PORTING/'analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace'
    target=root/'assets';files=sorted(p for p in source.rglob('*') if p.is_file())
    assert len(files)==1728
    start=time.monotonic();manifest=[];total=0
    for path in files:
        relative=path.relative_to(source);out=target/relative;out.parent.mkdir(parents=True,exist_ok=True)
        data=path.read_bytes();digest=hashlib.sha256(data).hexdigest();total+=len(data)
        if not out.exists() or out.stat().st_size!=len(data) or hashlib.sha256(out.read_bytes()).hexdigest()!=digest:shutil.copyfile(path,out)
        assert hashlib.sha256(out.read_bytes()).hexdigest()==digest,str(relative)
        manifest.append({'path':relative.as_posix(),'bytes':len(data),'sha256':digest})
    assert total==414822611
    donor='dd42272365d0abd8ad9c89450bb7f869ee4ac0ad548525758e6a1e7df4d3c1eb'
    receipt=f'DS_ASSETS_V1 {donor} 1728 414822611\n'
    (root/'assets-verified.txt').write_bytes(receipt.encode('ascii'))
    report={'files':len(files),'bytes':total,'sha256_verified':True,'receipt':receipt.strip(),'elapsed_seconds':round(time.monotonic()-start,3),'manifest':manifest}
    (PORTING/'analysis/emulator-assets.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Verified emulator assets:',len(files),'files,',total,'bytes')
if __name__=='__main__':main()
