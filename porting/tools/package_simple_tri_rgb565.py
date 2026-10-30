"""Package one emulator-tested format experiment; never runs hardware or pushes."""
import hashlib,json,re,shutil,struct,subprocess,zipfile
import build_simple_tri_rgb565 as b
P=b.P;B=b.D;A=b.A
DKP=P/'toolchain/devkitpro'
D=P/'dist/simple-tri-rgb565-v0.1.0'
E=P/'analysis/azahar-simple-tri-rgb565'
sha=b.sha

def main():
    manifest=json.loads((B/'build-manifest.json').read_text())
    test=json.loads((E/'result.json').read_text())
    assert test['passed'] and test['diagnostic_cycle']==1 and test['START_guest_GSP_release_and_heap_free']
    assert test['CIA_sha256']==sha(B/'simple-tri-rgb565.cia') and test['invalid_accesses_in_host_log']==0
    for key,root in [('inputs_sha256',P),('outputs_sha256',B)]:
        for name,h in manifest[key].items():assert sha(root/name)==h,name
    original=(b.stock.A/'upstream/graphics/gpu/simple_tri/source/main.c').read_text()
    source=(B/'main.c').read_text()
    for before,after in reversed(manifest['source_edits']):
        assert source.count(after)==1
        source=source.replace(after,before)
    assert source==original,'Source changed beyond format whitelist'
    assert sha(B/'vshader.shbin.o')==sha(b.stock.D/'vshader.shbin.o')
    assert manifest['compiler_flags']==json.loads((b.stock.D/'build-manifest.json').read_text())['compiler_flags']
    current=b.stock.payload((B/'simple-tri-rgb565.cia').read_bytes())
    previous=b.stock.payload((b.stock.D/'simple_tri-profile.cia').read_bytes())
    assert current[0x408:0x600]==previous[0x408:0x600]
    assert current[0x20d:0x210]==previous[0x20d:0x210] and current[0x21c:0x220]==previous[0x21c:0x220]
    assert struct.unpack_from('<Q',current,0x108)[0]==int(b.TITLE,16)
    symbols=subprocess.check_output([str(DKP/'devkitARM/bin/arm-none-eabi-nm.exe'),'-g','--defined-only',str(B/'triangle.elf')],text=True)
    assert re.search(r' T gxCmdQueueInterrupt\b',symbols)
    assert not re.search(r'\b(?:__wrap_|ds34_|ds22_|ds_runtime_|clear_events_|NativeOnDrawFrame)\w*',symbols)
    result=subprocess.run([str(P/'toolchain/extras/ctrtool/ctrtool.exe'),'--verify',str(B/'simple-tri-rgb565.cia')],capture_output=True,text=True)
    output=result.stdout+result.stderr
    errors=[x for x in output.splitlines() if ' ERROR]' in x]
    expected=['Signature for Ticket was invalid','Signature for TitleMetaData was invalid','Signature for AccessDescriptor was invalid']
    assert len(errors)==3 and all(any(e in x for e in expected) for x in errors),errors
    hashes=[x.strip() for x in output.splitlines() if re.search(r'[Hh]ash.*\((GOOD|FAIL)\)',x)]
    assert len(hashes)>=3 and all('(GOOD)' in x for x in hashes)
    preservation=json.loads((A/'preservation.json').read_text())
    after={n:sha(P/n) for n in preservation['before']};assert after==preservation['before']
    preservation.update(after=after,passed=True,files_checked=len(after))
    (A/'preservation.json').write_text(json.dumps(preservation,indent=2)+'\n')
    copies={B/'simple-tri-rgb565.cia':'simple-tri-rgb565.cia',P/'3ds/README-simple-tri-rgb565.ru.md':'README.ru.md',
        b.stock.LIB/'LICENSE':'LICENSE-citro3d.md',B/'main.c':'source/main.c',A/'source.diff':'validation/source.diff',
        b.stock.A/'upstream/README.md':'reference/README.md',
        b.stock.A/'upstream/graphics/gpu/simple_tri/source/main.c':'reference/main.c',
        b.stock.A/'upstream/graphics/gpu/simple_tri/source/vshader.v.pica':'reference/vshader.v.pica'}
    for name in ['result.json','azahar-host.log','top-60.png','top-90.png','top-120.png']:
        copies[E/name]='validation/'+name
    D.mkdir(exist_ok=True)
    for source,name in copies.items():
        dest=D/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    report={'passed':True,'version':b.VERSION,'date':'2026-10-30','hardware_tested':False,'hardware_run_authorized':False,
        'not_a_DS34_fix':True,'game_resources_included':False,'title_id':b.TITLE,'title_version':1,
        'stock_source_plus_exact_format_whitelist':True,'same_SDK_shader_flags_profile':True,
        'no_runtime_instrumentation_or_wrappers':True,'real_SDK_queue_handler':True,'compiler_flags':manifest['compiler_flags'],
        'source_edits':manifest['source_edits'],'CIA_sha256':sha(B/'simple-tri-rgb565.cia'),
        'ELF_sha256':sha(B/'triangle.elf'),'stock_ELF_sha256':manifest['stock_ELF_sha256'],
        'container_hashes':hashes,'expected_unsigned_homebrew_signature_errors':errors,
        'preserved_files':len(after),'diagnostic_cycles':1,'native_logs_produced':False,
        'starts_immediately':True,'native_timeout':False,'original_game_ready_claimed':False}
    report['files']={name:{'bytes':(D/name).stat().st_size,'sha256':sha(D/name)} for name in sorted(copies.values())}
    (D/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    allowed=set(copies.values())|{'manifest.json'}
    assert {q.relative_to(D).as_posix() for q in D.rglob('*') if q.is_file()}==allowed
    archive=P/'dist/simple-tri-rgb565-v0.1.0.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(allowed):z.write(D/name,name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist())==allowed
        for name,info in report['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest()==info['sha256']
    report.update(archive=archive.relative_to(P).as_posix(),archive_bytes=archive.stat().st_size,archive_sha256=sha(archive))
    (A/'package.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['files','source_edits','container_hashes','compiler_flags']},indent=2))
if __name__=='__main__':main()
