"""Build a separate CPU/PICA fog and COMBINE contract fixture. CXI only."""
import json
import shutil
import subprocess
import build_stage1 as b
from azahar_resource_store import sha
from build_native_game_target_init import makerom
P=b.PORTING

def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--revision',required=True);ap.add_argument('--scene-build',default='scene09');args=ap.parse_args()
    d=P/('3ds/build-scene-gpu-test-'+args.revision);assert args.revision.isalnum() and not d.exists();d.mkdir()
    base=P/('3ds/build-native-game-v0.1.7-'+args.scene_build)
    for name in ['ds34_gpu_native.c','ds34_shader.h','ds22_draw.c','ds15_textures.c','ds26_framebuffer.c','native-game.rsf','native-game.smdh','native-game.bnr']:
        shutil.copyfile(base/name,d/name)
    names=['ds_elf.c','ds_io.c','ds_runtime_libc.c','ds13_gles.c','ds14_arrays.c','ds15_textures.c','ds16_pipeline.c','ds21_matrices.c','ds22_draw.c','ds26_framebuffer.c','ds30_fog.c','ds31_combine.c','ds32_lighting.c','ds33_surface.c']
    sources=[d/name if (d/name).exists() else P/'3ds/source'/name for name in names]
    shutil.copyfile(P/'tests/native_scene_gpu_probe.c',d/'native_scene_gpu_probe.c')
    sources += [d/'ds34_gpu_native.c',d/'native_scene_gpu_probe.c']
    morton=(base/'scene_morton_store.c').exists()
    if morton:
        for name in ['scene_morton_store.c','scene_morton_store.h','native_scene_morton.h','native_menu_page_crc.h','lz4.c','lz4.h']:
            shutil.copyfile(base/name,d/name)
        codec=d/'lz4.c'
        if (base/'lz4-fast.o').exists():
            shutil.copyfile(base/'lz4-fast.o',d/'lz4-fast.o');codec=d/'lz4-fast.o'
        shutil.copyfile(P/'tests/native_scene_store_probe.c',d/'native_scene_store_probe.c')
        sources += [d/'scene_morton_store.c',codec,d/'native_scene_store_probe.c']
    command=list(map(str,[b.GCC,*b.FLAGS,'-D__3DS__','-DDS34_CAPTURE_RGBA','-mword-relocations','-specs=3dsx.specs','-Wl,-z,noexecstack',
        '-I'+str(b.DKP/'libctru/include'),'-I'+str(P/'toolchain/citro3d/include'),'-I'+str(P/'3ds/include'),'-I'+str(d),*sources,
        '-L'+str(P/'toolchain/citro3d/lib'),'-L'+str(b.DKP/'libctru/lib'),'-lcitro3d','-lctru','-lm','-Wl,--gc-sections','-o',d/'native-game.elf']))
    if morton:command[1:1]=['-DDS_SCENE_STORE_TEST','-DDS34_SEQUENCE_AUDIT']
    subprocess.run(command,cwd=d,check=True);cxi=makerom('cxi',d);subprocess.run(cxi,cwd=d,check=True)
    (d/'build-manifest.json').write_text(json.dumps({'commands':[command,cxi],'fixture_cases':16 if morton else 15,'morton_store_contracts':morton,'game_called':False,'CIA_created':False,'inputs':{str(p.relative_to(P)):sha(p) for p in sources},'cxi_sha256':sha(d/'native-game.cxi')},indent=2)+'\n')

if __name__=='__main__':main()
