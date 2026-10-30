"""Validate and package the upstream control only; no hardware run or upload."""
import hashlib,json,re,shutil,struct,subprocess,zipfile
from pathlib import Path
import build_official_simple_tri as b
P=b.P;B=b.D;A=b.A
D=P/'dist/official-simple-tri-v0.1.0'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    manifest=json.loads((B/'build-manifest.json').read_text())
    for key,root in [('inputs_sha256',P),('outputs_sha256',B)]:
        for name,value in manifest[key].items():assert sha(root/name)==value,name
    reports={n:json.loads((P/f'analysis/azahar-official-simple-tri-{n}/result.json').read_text()) for n in ['3dsx','cia']}
    for n,r in reports.items():
        assert r['passed'] and r['invalid_accesses_in_host_log']==0 and not r['hardware_tested']
        assert r['ELF_sha256']==sha(B/'simple_tri.elf')
        root=P/f'analysis/azahar-official-simple-tri-{n}'
        host=(root/'azahar-host.log').read_text()
        # These guest SVC/service messages precede frontend unload; they are
        # evidence of guest cleanup even without a libretro shutdown callback.
        assert 'ReleaseRight:999: called' in host and 'operation=0x00000001, addr0=0x08000000' in host
    assert reports['cia']['cia_sha256']==sha(B/'simple_tri-profile.cia')
    assert [r['top_pixels_sha256'] for r in reports['3dsx']['observations']]==[r['top_pixels_sha256'] for r in reports['cia']['observations']]
    current=b.payload((B/'simple_tri-profile.cia').read_bytes())
    previous=b.payload((P/'3ds/build-citro3d-control/control.cia').read_bytes())
    assert current[0x408:0x600]==previous[0x408:0x600]
    assert struct.unpack_from('<Q',current,0x108)[0]==int(b.TITLE,16)
    symbols=subprocess.check_output([str(P/'toolchain/devkitpro/devkitARM/bin/arm-none-eabi-nm.exe'),'-g','--defined-only',str(B/'simple_tri.elf')],text=True)
    assert re.search(r' T gxCmdQueueInterrupt\b',symbols)
    assert not re.search(r'\b(?:__wrap_|ds34_|ds22_|ds_runtime_|NativeOnDrawFrame)\w*',symbols)
    container=subprocess.run([str(P/'toolchain/extras/ctrtool/ctrtool.exe'),'--verify',str(B/'simple_tri-profile.cia')],capture_output=True,text=True)
    output=container.stdout+container.stderr
    errors=[x for x in output.splitlines() if ' ERROR]' in x]
    expected=['Signature for Ticket was invalid','Signature for TitleMetaData was invalid','Signature for AccessDescriptor was invalid']
    assert len(errors)==3 and all(any(e in x for e in expected) for x in errors),errors
    hashes=[x.strip() for x in output.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)',x)]
    assert len(hashes)>=3 and all('(GOOD)' in x for x in hashes),hashes
    preservation=json.loads((A/'preservation.json').read_text())
    after={n:sha(P/n) for n in preservation['before']}
    assert after==preservation['before'],'Existing baseline/evidence changed'
    preservation.update(after=after,passed=True,files_checked=len(after))
    (A/'preservation.json').write_text(json.dumps(preservation,indent=2)+'\n')
    D.mkdir(exist_ok=True)
    copies={B/'simple_tri.3dsx':'3dsx/simple_tri.3dsx',B/'simple_tri-profile.cia':'cia-same-profile/simple_tri-profile.cia',
        P/'3ds/README-official-simple-tri.ru.md':'README.ru.md',P/'toolchain/citro3d/LICENSE':'LICENSE-citro3d.md',
        A/'comparison.md':'validation/comparison.md',A/'upstream.json':'validation/upstream.json'}
    for name in ['README.md','graphics/gpu/simple_tri/Makefile','graphics/gpu/simple_tri/source/main.c','graphics/gpu/simple_tri/source/vshader.v.pica']:
        copies[A/'upstream'/name]='upstream/'+name
    for n in ['3dsx','cia']:
        for name in ['result.json','azahar-host.log','top-60.png','top-90.png','top-120.png']:
            copies[P/f'analysis/azahar-official-simple-tri-{n}'/name]=f'validation/{n}/{name}'
    for source,name in copies.items():
        dest=D/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    check={'passed':True,'date':'2026-10-30','hardware_tested':False,'hardware_run_authorized':False,
        'not_a_GPU_fix':True,'upstream_sources_unmodified':True,'upstream_commit':b.COMMIT,
        'same_ELF_for_3dsx_and_CIA':True,'CIA_title_id':b.TITLE,'CIA_title_version':1,
        'same_capabilities_except_program_id':True,'game_resources_included':False,'DS34_linked':False,
        'real_SDK_queue_handler':True,'wrappers_present':False,'container_hash_checks':hashes,
        'expected_unsigned_homebrew_signature_errors':errors,'guest_START_cleanup_seen_both_variants':True,
        'frontend_shutdown_callback_received':False,'same_software_LCD_pixels_both_variants':True,
        'known_corner_anomaly':{'x':399,'y':0,'RGB':[0,0,0],'cause':'unknown'},
        'preserved_files':len(after),'CIA_sha256':sha(B/'simple_tri-profile.cia'),'3DSX_sha256':sha(B/'simple_tri.3dsx'),
        'ELF_sha256':sha(B/'simple_tri.elf'),'build_adaptations':manifest['build_adaptations'],
        'SDK_hashes':{n:v for n,v in manifest['inputs_sha256'].items() if n.endswith('.a')}}
    check['files']={name:{'bytes':(D/name).stat().st_size,'sha256':sha(D/name)} for name in sorted(copies.values())}
    (D/'manifest.json').write_text(json.dumps(check,indent=2)+'\n')
    allowed=set(copies.values())|{'manifest.json'}
    assert {f.relative_to(D).as_posix() for f in D.rglob('*') if f.is_file()}==allowed,'Unexpected package file'
    archive=P/'dist/official-simple-tri-v0.1.0.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(allowed):z.write(D/name,name)
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None and set(z.namelist())==allowed
    check.update(archive=archive.relative_to(P).as_posix(),archive_bytes=archive.stat().st_size,archive_sha256=sha(archive))
    (A/'package.json').write_text(json.dumps(check,indent=2)+'\n')
    print(json.dumps({k:v for k,v in check.items() if k!='files'},indent=2))
if __name__=='__main__':main()
