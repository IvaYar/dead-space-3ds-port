"""Package one bounded original-menu CIA after independent evidence audits."""
import json
from pathlib import Path
import struct
import subprocess
from audit_native_game_menu import audit_run, P, A, read
from azahar_resource_store import sha
from build_native_game_target_init import makerom
from build_native_startup_legacy import payload

def main():
    normal=audit_run('r14-cpu100');home=audit_run('r14home-home')
    assert normal['menu_button_sequence_confirmed'] and normal['original_confirm_callback']==4321
    build=P/'3ds/build-native-game-v0.1.5-r14'
    m=read(build/'build-manifest.json')
    assert not m['scene_probe'] and m['confirm_tail_callbacks']==2 and not m['dense_capture']
    assert m['callbacks']==12000 and not m['test_HOME_callback'] and m['test_only_SDK_sha256'] is None
    assert '-DMENU_ALLOW_SCENE=0' in m['commands'][0]
    assert m['source_sha256']==sha(P/'tests/native_game_menu.c')
    for n,digest in m['headers_sha256'].items():assert sha(P/'tests'/n)==digest
    hm=read(P/'3ds/build-native-game-v0.1.5-r14home/build-manifest.json')
    assert hm['source_sha256']==m['source_sha256'] and hm['headers_sha256']==m['headers_sha256']
    assert hm['test_only_SDK_sha256']==sha(P/'3ds/build-native-game-v0.1.4r2-home/apt-test.o')
    tests=read(A/'input-tests.json');assert tests['passed'] and tests['header_sha256']==sha(P/'tests/native_menu_input.h')
    audited=read(A/'software-audit.json')
    assert audited['audited'] and audited['strict_verifier_unchanged'] and not audited['image_validation_passed']
    assert not (build/'native-game.cia').exists(),'Exactly one new CIA; preserve existing package'
    subprocess.run(makerom('cia',build),cwd=build,check=True)
    data=payload((build/'native-game.cia').read_bytes())
    assert data==(build/'native-game.cxi').read_bytes()
    assert struct.unpack_from('<Q',data,0x108)[0]==0x000400000FDE7800
    (build/'cia-payload.cxi').write_bytes(data)
    gate={'ready_for_one_separate_hardware_test':True,'hardware_tested':False,'hardware_run_authorized':False,
        'scope':'Original difficulty menu and physical-button selection; original confirm plus2 callbacks, then safe exit. No gameplay candidate.',
        'frame_status':'FAIL','baseline_crc_unchanged':'ea733050','strict_verifier_unchanged':True,
        'CIA':{'path':str((build/'native-game.cia').relative_to(P.parent)),'title':'DS Original Menu 0.1.5',
            'title_id':'000400000FDE7800','bytes':(build/'native-game.cia').stat().st_size,
            'sha256':sha(build/'native-game.cia'),'payload_sha256':sha(build/'cia-payload.cxi'),
            'payload_byte_identical_to_tested_CXI':True},
        'source_sha256':m['source_sha256'],'headers_sha256':m['headers_sha256'],'memory_MiB':m['memory_MiB'],
        'menu_and_buttons':normal,'deferred_HOME_SDK_cancel':home,'input_ARM_checks':tests,
        'known_scene_blockers':['Original-code NULL reads at donor-relative265f80/265f98 in the EAAudioCore region; not fixed.',
            'DS34 fog/stencil/offset not implemented; original first-scene render is not a completed playable scene.'],
        'host_renderer_limit':'Azahar Software renderer crashed with access violation in large-menu transition. Successful proofs use OpenGL; raw GPU readbacks, not black frontend PNGs, establish the images.',
        'hardware_FPS_measured':False}
    (A/'release-gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    print(json.dumps(gate['CIA'],indent=2))

if __name__=='__main__':main()
