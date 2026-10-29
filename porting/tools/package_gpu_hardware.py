"""Verify and package an already built/tested synthetic GPU CIA; no donor."""
import hashlib,json,re,shutil,struct,subprocess,zipfile
from pathlib import Path
VERSION='0.1.3'
P=Path(__file__).resolve().parents[1];B=P/('3ds/build-gpu-hardware-v'+VERSION);E=P/('analysis/azahar-gpu-hardware-v'+VERSION);D=P/('dist/gpu-hardware-v'+VERSION)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((B/'build-manifest.json').read_text());test=json.loads((E/'result.json').read_text())
    for name,h in manifest['sources_sha256'].items():assert sha(P/name)==h,name
    for name,h in manifest['outputs_sha256'].items():assert sha(B/name)==h,name
    assert test['passed'] and test['stale_result_cleared'] and test['START_exit_gpu_drained'] and test['start_A_gate_verified']
    assert test['cia_sha256']==sha(B/'ds34-gpu-test.cia')
    assert manifest['version']==test['version']==VERSION and test['inactive_transfer_verified']
    assert not manifest['fault_injection_compiled'] and test['first_case_phase_order_verified']
    assert manifest['wait_timeout_ms']==2000 and test['v0.1.1_pixels_unchanged']
    assert test['queue_observer']['queue_wrapper_verified'] and test['queue_observer']['pica_capture_verified']
    assert test['queue_observer']['submit_return_results_success'] and not test['queue_observer']['irq_observation_available']
    assert manifest['cpu_vram_mapping']=='read-only'
    previous=json.loads((P/'analysis/azahar-gpu-hardware/result.json').read_text())
    assert previous['png_sha256']==test['png_sha256'],'Synthetic frames changed from v0.1.0'
    fault_checks={}
    for scenario in ['vblank0','vblank1','queue-after-submit']:
        report=json.loads((P/('analysis/azahar-gpu-hardware-v'+VERSION+'-'+scenario)/'result.json').read_text())
        assert report['passed'] and report['intentional_fault'] and report['START_exit_gpu_drained']
        if scenario=='queue-after-submit':assert report['busy_exit_deferred']
        fault_checks[scenario]=report
    proc=subprocess.run([str(P/'toolchain/extras/ctrtool/ctrtool.exe'),'--verify',str(B/'ds34-gpu-test.cia')],capture_output=True,text=True)
    output=proc.stdout+proc.stderr;errors=[s for s in output.splitlines() if ' ERROR]' in s]
    expected=['Signature for Ticket was invalid','Signature for TitleMetaData was invalid','Signature for AccessDescriptor was invalid']
    assert len(errors)==3 and all(any(e in s for e in expected) for s in errors),errors
    checks=[s.strip() for s in output.splitlines() if re.search(r'[Hh]ash.*\((?:GOOD|FAIL)\)',s)]
    assert len(checks)>=3 and all('(GOOD)' in s for s in checks)
    symbols=subprocess.check_output([str(P/'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-nm.exe'),'-g','--defined-only',str(B/'ds34-gpu-test.elf')],text=True)
    forbidden=['ds_exec_open','ds_exec_page','ds_audit_trap','ds_elf_prepare','NativeOnDrawFrame']
    assert not any(re.search(r'\b'+s+r'\b',symbols) for s in forbidden)
    assert '__wrap_gxCmdQueueRun' in symbols and '__wrap_gspSubmitGxCommand' in symbols
    assert '__wrap_gxCmdQueueInterrupt' not in symbols
    # Fault-test build and its input seam must never reach the release CIA.
    elf=(B/'ds34-gpu-test.elf').read_bytes()
    assert b'diag-fault.txt' not in elf and b'EMULATOR FAULT INJECTION' not in elf
    data=(B/'ds34-gpu-test.cia').read_bytes();h,_,_,c,t,m,_,size=struct.unpack_from('<IHHIIIIQ',data);align=lambda n:(n+63)&~63
    off=align(h)+align(c)+align(t)+align(m);payload=data[off:off+size]
    assert hashlib.sha256(payload).hexdigest()==test['payload_sha256']
    assert struct.unpack_from('<Q',payload,0x108)[0]==0x000400000FDE6800
    D.mkdir(exist_ok=True);v=D/'validation';v.mkdir(exist_ok=True)
    shutil.copyfile(B/'ds34-gpu-test.cia',D/('ds34-gpu-test-v'+VERSION+'.cia'))
    assert ('# DS34 GPU Test v'+VERSION) in (P/'3ds/README-gpu-hardware.ru.md').read_text(encoding='utf-8')
    shutil.copyfile(P/'3ds/README-gpu-hardware.ru.md',D/'README.ru.md')
    shutil.copyfile(P/'toolchain/citro3d-source/LICENSE',D/'LICENSE-citro3d.md')
    shutil.copyfile(E/'result.json',v/'azahar-result.json');shutil.copyfile(E/'gpu-test.log',v/'azahar-gpu-test.log')
    first=json.loads((E/'gx-first-frame.json').read_text());assert first['captures_complete']
    shutil.copyfile(E/'gx-first-frame.json',v/'expected-gx-first-frame.json')
    for entry in first['entries']:
        if 'pica_file' in entry:
            assert re.fullmatch(r'gx-first-\d+\.pica',entry['pica_file'])
            shutil.copyfile(E/entry['pica_file'],v/entry['pica_file'])
    for scenario,report in fault_checks.items():
        (v/('fault-'+scenario+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    for i in range(8):shutil.copyfile(E/f'case-{i}.png',v/f'expected-case-{i}.png')
    check={'passed':True,'version':VERSION,'title_id':'000400000FDE6800','cia_sha256':sha(B/'ds34-gpu-test.cia'),'hash_checks':checks,'homebrew_test_signatures':True,'rx_and_donor_execution_symbols_absent':True,'cpu_vram_mapping':'read-only','inactive_transfer_verified':True,'v0.1.0_pixel_sha_unchanged':True,'fault_injection_absent_from_release':True,'timeout_fault_scenarios_passed':list(fault_checks),'hardware_tested':False,'diagnostic_only':True,'hardware_hang_fixed':False,'queue_observer_verified':True,'irq_observation_available':False}
    (v/'package-check.json').write_text(json.dumps(check,indent=2)+'\n')
    release={**manifest,'emulator_tested':True,'hardware_tested':False,'package_tool_sha256':sha(Path(__file__))}
    release['files']={str(f.relative_to(D)).replace('\\','/'):{'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(D.rglob('*')) if f.is_file() and f.name!='build-manifest.json'}
    assert all(f.endswith(('.cia','.md','.json','.log','.png','.pica')) for f in release['files'])
    assert not any('/assets/' in f or f.endswith(('.so','.apk','.elf','.cxi')) for f in release['files'])
    (D/'build-manifest.json').write_text(json.dumps(release,indent=2)+'\n')
    archive=P/('dist/ds34-gpu-test-v'+VERSION+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(D.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(D).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist())==set(release['files'])|{'build-manifest.json'}
    (P/('analysis/gpu-hardware-v'+VERSION+'-package.json')).write_text(json.dumps({**check,'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'game_resources_included':False,'file_count':len(release['files'])+1},indent=2)+'\n')
    print('CIA:',D/('ds34-gpu-test-v'+VERSION+'.cia'));print('ZIP:',archive);print('CIA SHA256:',check['cia_sha256'])
if __name__=='__main__':main()
