"""Bounded loading experiments from the frozen HID0.1.7 CXI. Never builds CIA."""
import argparse
import difflib
import json
from pathlib import Path
import shutil
import subprocess
from azahar_resource_store import sha
from build_native_game_target_init import RUNTIME, makerom

P = Path(__file__).resolve().parents[1]
BASE = P / '3ds/build-native-game-v0.1.7-release'


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def texture_source(text, clean):
    if not clean:
        return text
    helper = '''/* A backing token denotes the exact current canonical pixels.
 * CPU writes invalidate it; reads and GPU uploads do not. */
void ds15_invalidate_backing(DS15State *s,DS15Object *o,uint32_t level){
    DS15Level *l=&o->levels[level];
    if(l->backing){s->backing_ops->drop(l->backing);l->backing=0;}
}
'''
    text = replace(text, 'static int spill(DS15State *s,DS15Level *l){', helper + 'static int spill(DS15State *s,DS15Level *l){')
    text = replace(text,
        'if(s->backing_ops->save(&l->backing,l->rgba,bytes)){++s->page_failures;return -1;}\n    ds_rt_free(l->rgba);l->rgba=NULL;s->resident-=bytes;++s->page_saves;return 0;',
        'if(!l->backing){\n        if(s->backing_ops->save(&l->backing,l->rgba,bytes)){++s->page_failures;return -1;}\n        ++s->page_saves;\n    }\n    ds_rt_free(l->rgba);l->rgba=NULL;s->resident-=bytes;return 0;')
    text = replace(text, 'if(w && h)copy_image(l->rgba,l->width,', 'if(w && h)ds15_invalidate_backing(state(),o,(uint32_t)level);\n    if(w && h)copy_image(l->rgba,l->width,')
    return text


def framebuffer_source(text, clean):
    if not clean:
        return text
    text = replace(text, 'void ds34_fbo_dirty(DS13Context *c){', 'void ds15_invalidate_backing(DS15State *,DS15Object *,uint32_t);\nvoid ds34_fbo_dirty(DS13Context *c){')
    return replace(text, 'if(f && f->attachments[0].texture && ds34_texture_dirty)ds34_texture_dirty',
                   'if(f && f->attachments[0].texture)ds15_invalidate_backing(&c->texture,f->attachments[0].texture,0);if(f && f->attachments[0].texture && ds34_texture_dirty)ds34_texture_dirty')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision', required=True)
    ap.add_argument('--clean', action='store_true')
    ap.add_argument('--home-at', type=int, default=0, help='Test-only inherited HOME/X fixture')
    args = ap.parse_args(); assert args.revision.isalnum()
    d = P / ('3ds/build-native-game-v0.1.7-' + args.revision)
    assert not d.exists(), 'Preserve existing builds'
    original = json.loads((BASE / 'build-manifest.json').read_text())
    for field in ['outputs_sha256', 'headers_sha256', 'runtime_sha256']:
        for name, digest in original[field].items(): assert sha(BASE / name) == digest
    d.mkdir()
    for name in set(RUNTIME + list(original['headers_sha256']) + ['native-game.smdh', 'native-game.bnr', 'native-game.rsf', 'ds27_pages_3ds.c']):
        shutil.copyfile(BASE / name, d / name)
    shutil.copyfile(P / 'tests/native_loading_profile.h', d / 'native_loading_profile.h')
    source = (BASE / 'native-game-memory.c').read_text()
    source = replace(source, '#include "native_menu_profile.h"', '#include "native_loading_profile.h"\n#include "native_menu_profile.h"')
    source = replace(source, 'ds27_sd_backing(),6*1024*1024', 'loading_backing(),6*1024*1024')
    source = replace(source, 'menu_profile_end(callback_ticks);menu_input_ack();', 'menu_profile_end(callback_ticks);loading_flush();menu_input_ack();')
    (d / 'native-game-memory.c').write_text(source)
    profile = (BASE / 'native_menu_profile.h').read_text()
    profile = replace(profile, 'menu_profile_record(11,t,(u32)__builtin_return_address(0));return r;',
                      'menu_profile_record(11,t,(u32)__builtin_return_address(0));loading_crc_observe(r,svcGetSystemTick()-t);return r;')
    (d / 'native_menu_profile.h').write_text(profile)
    changes = {}
    for name, transform in [('ds15_textures.c', texture_source), ('ds26_framebuffer.c', framebuffer_source)]:
        path = P / '3ds/source' / name
        before = path.read_text(); after = transform(before, args.clean)
        (d / name).write_text(after)
        changes[name] = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='original/' + name, tofile='experiment/' + name))
    (d / 'paging.diff').write_text(''.join(changes.values()))
    command = [s.replace(str(BASE), str(d)) for s in original['commands'][0]]
    command = [str(d / Path(s).name) if s in [str(P / '3ds/source' / n) for n in changes] else s for s in command]
    if args.home_at:
        assert 600 < args.home_at < original['callbacks']
        shutil.copyfile(P / '3ds/build-native-game-v0.1.7-releasehome/apt-test.o', d / 'apt-test.o')
        command[1:1] = [str(d / 'apt-test.o'), '-DTEST_APT_CLOSE=1', '-DTEST_MENU_HOME_FRAME=' + str(args.home_at)]
    subprocess.run(command, cwd=d, check=True)
    cxi = makerom('cxi', d); subprocess.run(cxi, cwd=d, check=True)
    m = dict(original)
    m.update({'revision': args.revision, 'commands': [command, cxi], 'clean_backing': args.clean,
              'test_HOME_callback': args.home_at,
              'test_only_SDK_sha256': sha(d / 'apt-test.o') if args.home_at else None,
              'CIA_created': False, 'hardware_tested': False, 'source_sha256': sha(d / 'native-game-memory.c'),
              'source_origin_sha256': sha(BASE / 'native-game-memory.c'),
              'headers_sha256': {n: sha(d / n) for n in list(original['headers_sha256']) + ['native_loading_profile.h']},
              'loading_sources_sha256': {n: sha(d / n) for n in changes},
              'outputs_sha256': {n: sha(d / n) for n in original['outputs_sha256']}})
    (d / 'build-manifest.json').write_text(json.dumps(m, indent=2) + '\n')
    print('Built loading CXI only', d.name)


if __name__ == '__main__':
    main()
