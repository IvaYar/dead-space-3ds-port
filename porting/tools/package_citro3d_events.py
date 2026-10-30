"""Package the tested passive CLEAR observer; no hardware execution or upload."""
import hashlib,json,re,shutil,subprocess,zipfile
from pathlib import Path
P=Path(__file__).resolve().parents[1]
B=P/'3ds/build-citro3d-events';E=P/'analysis/azahar-citro3d-events';F=P/'analysis/azahar-citro3d-events-fault'
D=P/'dist/citro3d-control-v0.1.1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    m=json.loads((B/'build-manifest.json').read_text());t=json.loads((E/'result.json').read_text());fault=json.loads((F/'result.json').read_text())
    assert t['passed'] and t['A_gate_verified'] and t['START_exit_drained'] and t['event_timestamp_and_snapshot_consistency_verified']
    assert fault['passed'] and fault['intentional_fault'] and fault['timeout_checkpoint_verified'] and fault['START_exit_drained']
    assert m['clear_only'] and not m['fault_injection_compiled'] and m['same_v0.1.0_binary_capabilities']
    assert t['exact_native_v0_1_0_GPU_packets_unchanged'] and fault['exact_native_v0_1_0_GPU_packets_unchanged']
    for n,h in m['inputs_sha256'].items():assert sha(P/n)==h,n
    for n,h in m['outputs_sha256'].items():assert sha(B/n)==h,n
    assert t['cia_sha256']==sha(B/'control.cia')
    nm=subprocess.check_output([str(P/'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-nm.exe'),str(B/'control.elf')],text=True)
    assert not re.search(r'\b(?:ds34_|ds13_|ds22_|ds_exec_|NativeOnDrawFrame|DVLB_ParseFile|clear_events_software_selfcheck|__wrap_gxCmdQueueInterrupt|__atomic_\w+_8)\w*',nm)
    elf=(B/'control.elf').read_bytes();assert b'Emulator-only fault build' not in elf and b'OBSERVER SOFTWARE SELFTEST PASS' not in elf
    edges=json.loads((P/'analysis/citro3d-events/callback-call-edges.json').read_text())
    assert 'gxCmdQueueInterrupt' in edges['gspEventThreadMain'] and 'svcGetSystemTick' in edges['record']
    proc=subprocess.run([str(P/'toolchain/extras/ctrtool/ctrtool.exe'),'--verify',str(B/'control.cia')],capture_output=True,text=True)
    output=proc.stdout+proc.stderr;errors=[s for s in output.splitlines() if ' ERROR]' in s]
    expected=['Signature for Ticket was invalid','Signature for TitleMetaData was invalid','Signature for AccessDescriptor was invalid']
    assert len(errors)==3 and all(any(x in e for x in expected) for e in errors),errors
    hashes=[s.strip() for s in output.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)',s)]
    assert len(hashes)>=3 and all('(GOOD)' in s for s in hashes)
    D.mkdir(exist_ok=True);v=D/'validation';v.mkdir(exist_ok=True)
    shutil.copyfile(B/'control.cia',D/'citro3d-control-v0.1.1.cia')
    shutil.copyfile(P/'3ds/README-citro3d-events.ru.md',D/'README.ru.md');shutil.copyfile(P/'toolchain/citro3d/LICENSE',D/'LICENSE-citro3d.md')
    for label,folder in [('normal',E),('fault',F)]:
        for f in [folder/'result.json',folder/'control.log',*sorted(folder.glob('events-*.json'))]:
            shutil.copyfile(f,v/(label+'-'+f.name))
    shutil.copyfile(E/'clear.png',v/'clear.png');shutil.copyfile(P/'analysis/citro3d-events/callback-call-edges.json',v/'callback-call-edges.json')
    release={**m,'emulator_tested':True,'hardware_tested':False,'not_a_GPU_fix':True,'GPU_packets_unchanged':True,'hash_checks':hashes,
        'normal_event_counts':t['delivered_event_counts'],'fault_test_passed':True,'test_binary_not_included':True}
    release['files']={f.relative_to(D).as_posix():{'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(D.rglob('*')) if f.is_file() and f.name!='build-manifest.json'}
    assert all(n.endswith(('.cia','.md','.json','.log','.png')) for n in release['files'])
    assert len([n for n in release['files'] if n.endswith('.cia')])==1
    (D/'build-manifest.json').write_text(json.dumps(release,indent=2)+'\n')
    archive=P/'dist/citro3d-control-v0.1.1.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(D.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(D).as_posix())
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None and set(z.namelist())==set(release['files'])|{'build-manifest.json'}
    report={'passed':True,'hardware_tested':False,'cia_sha256':sha(B/'control.cia'),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,
        'title_id':m['title_id'],'title_version':2,'GPU_packets_unchanged':True,'SDK_handlers_replaced':False,'original_game_resources_included':False,'test_binary_included':False}
    (P/'analysis/citro3d-events/package.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
