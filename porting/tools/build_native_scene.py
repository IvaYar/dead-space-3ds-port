"""Isolated emulator-only scene continuation, retaining HID and clean backing. CXI only."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from azahar_resource_store import sha
from build_native_game_target_init import RUNTIME, makerom
from build_native_loading import texture_source, framebuffer_source, replace

P = Path(__file__).resolve().parents[1]
BASE = P / '3ds/build-native-game-v0.1.7-loadclean'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision', required=True)
    ap.add_argument('--callbacks', type=int, default=5400)
    ap.add_argument('--audio', action='store_true')
    ap.add_argument('--scene-gpu', action='store_true')
    ap.add_argument('--fog', action='store_true')
    ap.add_argument('--scene-resident-mib', type=int, choices=[5, 6], default=6)
    ap.add_argument('--pressure-evict', action='store_true')
    ap.add_argument('--lazy-scene-residency', action='store_true')
    ap.add_argument('--scene-seconds', type=int, default=120)
    ap.add_argument('--home-at', type=int, default=0)
    ap.add_argument('--texture-trace', action='store_true')
    ap.add_argument('--visible-textures', action='store_true')
    ap.add_argument('--projective-texture0', action='store_true')
    ap.add_argument('--uv-trace', action='store_true')
    ap.add_argument('--morton-backing', action='store_true')
    ap.add_argument('--fast-morton-codec', action='store_true')
    args = ap.parse_args()
    assert args.revision.isalnum() and 4400 <= args.callbacks <= 12000
    d = P / ('3ds/build-native-game-v0.1.7-' + args.revision)
    assert not d.exists(), 'Preserve prior builds'
    m = json.loads((BASE / 'build-manifest.json').read_text())
    for group in ['outputs_sha256', 'headers_sha256', 'loading_sources_sha256']:
        for name, digest in m[group].items():
            assert sha(BASE / name) == digest, name
    d.mkdir()
    names = set(RUNTIME + list(m['headers_sha256']) + list(m['loading_sources_sha256']) +
                ['native-game.smdh', 'native-game.bnr', 'native-game.rsf', 'ds27_pages_3ds.c'])
    for name in names:
        shutil.copyfile(BASE / name, d / name)
    # Explicitly integrate, and verify, BOTH clean-page transforms. Never inherit
    # the unoptimized HID builder implicitly.
    for name, transform in [('ds15_textures.c', texture_source), ('ds26_framebuffer.c', framebuffer_source)]:
        expected = transform((P / '3ds/source' / name).read_text(), True)
        assert (d / name).read_text() == expected, name
    source = (BASE / 'native-game-memory.c').read_text()
    source = replace(source, '!strcmp(op,"GPU fog/stencil/offset not implemented")', '!strncmp(op,"GPU ",4)')
    source = replace(source, 'static void java_request(', 'static int scene_started;\nstatic u32 scene_java_resources;\nstatic void java_request(')
    source = replace(source, 'if(missing || !strcmp(op,"FindClass"))report(', '''if(scene_started && scene_java_resources<512 && strstr(op,"AssetManager")){
        ++scene_java_resources;report("SCENE_JNI_RESOURCE frame=%lu op=%s name=%s result=%d\\n",(unsigned long)current_frame,op,name,missing);
    }
    if(missing || !strcmp(op,"FindClass"))report(''')
    source = replace(source, 'if(menu_confirmation_frame && current_frame<=menu_confirmation_frame+2)capture=1;',
                     'if(menu_confirmation_frame && (current_frame<=menu_confirmation_frame+64 || current_frame%30==0))capture=1;')
    source = replace(source, 'ds11_pump_events(&bridge);', '''if(menu_confirmation_frame && scene_started && loader_now_ms()-scene_begin_ms>=SCENE_SECONDS*1000u){
            report("SCENE_BUDGET frame=%lu limit_ms=%lu elapsed_ms=%llu\\n",(unsigned long)current_frame,(unsigned long)(SCENE_SECONDS*1000u),(unsigned long long)(loader_now_ms()-scene_begin_ms));
            failure_reason="SCENE_BUDGET: original scene time limit; returned main boundary";break;
        }
        ds11_pump_events(&bridge);''')
    # Mixed audio now submits real jobs: stop its producers/consumers before
    # closing the job pool. Never signal jobs first while audio waits on them.
    source = replace(source, 'if(native_stop_job_workers())return -1;\n    if(native_stop_audio_workers())return -1;',
                     'if(native_stop_audio_workers())return -1;\n    if(native_stop_job_workers())return -1;')
    source = replace(source, '#include "native_menu_profile.h"', '#include "native_menu_profile.h"\n#include "native_scene_observer.h"')
    shutil.copyfile(P / 'tests/native_scene_observer.h', d / 'native_scene_observer.h')
    source = replace(source, 'menu_profile_begin();', '''if(menu_confirmation_frame && !scene_started){
            scene_started=1;scene_begin_ms=loader_now_ms();graphics.texture.resident_limit=SCENE_RESIDENT_MIB*1024*1024;
            report("SCENE_BEGIN frame=%lu cpu_resident_limit=%lu linear_free=%lu\\n",(unsigned long)current_frame,(unsigned long)graphics.texture.resident_limit,(unsigned long)linearSpaceFree());
        }
        menu_profile_begin();''')
    source = replace(source, 'loading_flush();menu_input_ack();', 'loading_flush();menu_input_ack();scene_observe();')
    memory = (d / 'native_game_memory_observer.h').read_text()
    memory = replace(memory, 'static u32 observed_normal_live,', 'static u32 scene_malloc_failed_request,scene_malloc_failed_caller;\nstatic u32 observed_normal_live,')
    memory = replace(memory, 'void *p=__real_malloc(n);observe_normal(n);', 'void *p=__real_malloc(n);if(!p){scene_malloc_failed_request=n;scene_malloc_failed_caller=(u32)__builtin_return_address(0);}observe_normal(n);')
    (d / 'native_game_memory_observer.h').write_text(memory)
    monitor = (d / 'native_loader_io_monitor.h').read_text()
    monitor = replace(monitor, 'loader_io_end(token,0,r?0:-1);return r;', 'loader_io_end(token,0,r?0:-1);scene_resource_open(path,r?0:-1);return r;')
    # Observer is defined before loader IO; path records contain names only.
    source = replace(source, '#include "native_loader_io_monitor.h"', 'static void scene_resource_open(const char *,int);\n#include "native_loader_io_monitor.h"')
    (d / 'native_loader_io_monitor.h').write_text(monitor)
    if args.pressure_evict:
        tex = (d / 'ds15_textures.c').read_text()
        helper = '''/* Canonical allocation can fail below the residency budget due to
 * normal-heap pressure/fragmentation. Spill only unpinned LRU stores, retaining
 * exact clean backing and logical contents, before retrying. Failure remains
 * atomic: the old level/backing survives until replacement succeeds. */
static void *scene_page_alloc(DS15State *s,uint32_t bytes,DS15Level *protect,int zero){
    void *p=zero?ds_rt_calloc(1,bytes):ds_rt_malloc(bytes);
    while(!p && s->backing_ops){
        DS15Level *victim=NULL;
        for(DS15Object *o=&s->default_object;o;o=o==&s->default_object?s->objects:o->next)if(!pinned(s,o))for(unsigned j=0;j<DS15_LEVELS;++j){
            DS15Level *l=&o->levels[j];if(l->rgba && l!=protect && (!victim || l->stamp<victim->stamp))victim=l;
        }
        if(!victim && protect && protect->rgba)victim=protect;
        if(!victim || spill(s,victim))return NULL;
        p=zero?ds_rt_calloc(1,bytes):ds_rt_malloc(bytes);
    }
    return p;
}
'''
        tex = replace(tex, 'int ds15_resident(DS15State *s,DS15Object *o,uint32_t level){', helper + 'int ds15_resident(DS15State *s,DS15Object *o,uint32_t level){')
        tex = replace(tex, 'uint8_t *p=ds_rt_malloc(bytes);', 'uint8_t *p=scene_page_alloc(s,bytes,l,0);')
        tex = replace(tex, 'uint8_t *data=bytes?ds_rt_calloc(1,bytes):NULL;', 'uint8_t *data=bytes?scene_page_alloc(s,bytes,old,1):NULL;')
        (d / 'ds15_textures.c').write_text(tex)
    if args.audio:
        jni = (P / '3ds/source/ds10_jni.c').read_text()
        jni = replace(jni, 'TOUCH_SURFACE,CLASS_COUNT', 'TOUCH_SURFACE,AUDIO_TRACK,CLASS_COUNT')
        jni = replace(jni, '"com/ea/blast/TouchSurfaceAndroid"};', '"com/ea/blast/TouchSurfaceAndroid","android/media/AudioTrack"};')
        jni = replace(jni, 'FD_OFFSET,FD_INTEGER };', 'FD_OFFSET,FD_INTEGER,AUDIO_PLAY,AUDIO_STOP,AUDIO_WRITE };')
        jni = replace(jni, 'if(c->asset_open)fd=c->asset_open', 'notify(c,"AssetManager.open request",classes[MANAGER],relative,NULL,0);\n    if(c->asset_open)fd=c->asset_open')
        jni = replace(jni, 'static const Method methods[]={', '''static const Method methods[]={
    {AUDIO_TRACK,0,AUDIO_PLAY,"play","()V"},
    {AUDIO_TRACK,0,AUDIO_STOP,"stop","()V"},
    {AUDIO_TRACK,0,AUDIO_WRITE,"write","([SII)I"},''')
        jni = replace(jni, 'static DS10Value invoke(', '#include "native_scene_audio_jni.h"\nstatic DS10Value invoke(')
        jni = replace(jni, 'c->arrays[r->identity].used?&c->arrays[r->identity]:NULL;', 'c->arrays[r->identity].used==1?&c->arrays[r->identity]:NULL;')
        # Typed short operations share the existing pin ownership machinery,
        # but never accept a byte[] as short[] or vice versa.
        pin = jni[jni.index('static void *DS_JNI_SOFT get_elements('):jni.index('static DS10Stream *stream_for(')]
        pin = pin.replace('get_elements(', 'scene_get_shorts(').replace('release_elements(', 'scene_release_shorts(').replace('byte_array(c,handle)', 'scene_short_array(c,handle)')
        jni = replace(jni, '#include "native_scene_audio_jni.h"', '#include "native_scene_audio_jni.h"\n'+pin)
        jni = replace(jni, 'if(m->operation==READ){', 'if(m->operation==AUDIO_WRITE){out[0].l=va_arg(args,void *);out[1].i=va_arg(args,int);out[2].i=va_arg(args,int);}\n    if(m->operation==READ){')
        jni = replace(jni, 'case OPEN_FD:result.l=', '''case AUDIO_PLAY:__atomic_store_n(&scene_audio_playing,1,__ATOMIC_RELEASE);return result;
        case AUDIO_STOP:__atomic_store_n(&scene_audio_playing,0,__ATOMIC_RELEASE);return result;
        case AUDIO_WRITE:result.i=scene_audio_write(c,args);return result;
        case OPEN_FD:result.l=''')
        jni = replace(jni, 'if(!a){notify(c,"GetArrayLength"', 'if(r && r->kind==3 && r->identity<8 && c->arrays[r->identity].used==2)return (int32_t)c->arrays[r->identity].size/2;\n    if(!a){notify(c,"GetArrayLength"')
        jni = replace(jni, 't[200]=(uintptr_t)get_region;', '''t[178]=(uintptr_t)scene_new_shorts;t[186]=(uintptr_t)scene_get_shorts;
    t[194]=(uintptr_t)scene_release_shorts;t[210]=(uintptr_t)scene_set_shorts;
    c->base.vm_functions[5]=(uintptr_t)scene_vm_detach;
    t[200]=(uintptr_t)get_region;''')
        (d / 'ds10_jni.c').write_text(jni)
        shutil.copyfile(P / 'tests/native_scene_audio_jni.h', d / 'native_scene_audio_jni.h')
        source = replace(source, 'stage("lifecycle");lifecycle(', '''stage("audio Java startup");
    extern void *scene_audio_track(DS10Context *);
    typedef void (*AudioInit)(void *,void *,void *,int,int,int) DS_IO_SOFT;
    if(((PushFrame)bridge.base.env_functions[19])(&bridge.base.env,16))return -1;
    void *track=scene_audio_track(&bridge);if(!track)return -1;
    ((AudioInit)exported("Java_com_ea_EAAudioCore_AndroidEAAudioCore_Init"))(&bridge.base.env,NULL,track,1024,2,22050);
    ((PopFrame)bridge.base.env_functions[20])(&bridge.base.env,NULL);
    report("AUDIO_INIT original Java contract frames=1024 channels=2 rate=22050 PCM16 sink=timed-emulator\\n");
    stage("lifecycle");lifecycle(''')
        source = replace(source, 'u32 jni_freed=ds10_cleanup', '''typedef void (*AudioRelease)(void *,void *) DS_IO_SOFT;
    ((AudioRelease)exported("Java_com_ea_EAAudioCore_AndroidEAAudioCore_Release"))(&bridge.base.env,NULL);
    extern void scene_audio_stats(uint64_t [2]);uint64_t audio_stats[2];scene_audio_stats(audio_stats);
    report("AUDIO_SINK writes=%llu samples=%llu released_after_workers=1\\n",(unsigned long long)audio_stats[0],(unsigned long long)audio_stats[1]);
    u32 jni_freed=ds10_cleanup''')
    (d / 'native-game-memory.c').write_text(source)
    if args.scene_gpu:
        gpu = (d / 'ds34_gpu_native.c').read_text()
        helper = (P / 'tests/native_scene_gpu.h').read_text()
        gpu = replace(gpu, 'int ds34_begin_draw(DS13Context *c){', helper + '\nint ds34_begin_draw(DS13Context *c){')
        gpu = replace(gpu, 'if(mode!=0x2100 && mode!=0x1e01 && mode!=0x104)', 'if(mode==0x8570){if(scene_combine(c,u,e->tex.fmt))return -1;continue;}\n        if(mode!=0x2100 && mode!=0x1e01 && mode!=0x104)')
        (d / 'ds34_gpu_native.c').write_text(gpu)
    if args.fog:
        assert args.scene_gpu
        gpu = (d / 'ds34_gpu_native.c').read_text()
        gpu = replace(gpu, 'C3D_Tex inactive;', 'C3D_Tex inactive,fog_ramp;')
        gpu = replace(gpu, 'if(c->fog || c->pipeline.stencil || c->pipeline.offset_fill)', 'if(c->pipeline.stencil || c->pipeline.offset_fill)')
        gpu = replace(gpu, 'shaderProgramInit(&g.program);', '''/* Constant-sized factor ramp, uploaded before frames; no extra vertex bytes. */
    if(!C3D_TexInitVRAM(&g.fog_ramp,8,8,GPU_RGBA8))return -1;
    uint8_t *ramp=linearAlloc(256);if(!ramp)return -1;
    for(unsigned m=0;m<64;++m){unsigned x=(m&1)|((m>>1)&2)|((m>>2)&4);memset(ramp+m*4,(x*255+3)/7,4);}
    GSPGPU_FlushDataCache(ramp,256);C3D_TexUpload(&g.fog_ramp,ramp);linearFree(ramp);
    C3D_TexSetFilter(&g.fog_ramp,GPU_LINEAR,GPU_LINEAR);C3D_TexSetWrap(&g.fog_ramp,GPU_CLAMP_TO_EDGE,GPU_CLAMP_TO_EDGE);
    shaderProgramInit(&g.program);''')
        gpu = replace(gpu, 'C3D_FVUnifSet(GPU_VERTEX_SHADER,g.scale_loc,', '''C3D_TexBind(2,c->fog?&g.fog_ramp:&g.inactive);
    if(c->fog){
        const float *k=c->fog_state->color;C3D_TexEnv *e=C3D_GetTexEnv(2);
        C3D_TexEnvSrc(e,C3D_RGB,GPU_PREVIOUS,GPU_CONSTANT,GPU_TEXTURE2);
        C3D_TexEnvFunc(e,C3D_RGB,GPU_INTERPOLATE);
        C3D_TexEnvColor(e,byte(k[0])|byte(k[1])<<8|byte(k[2])<<16|byte(k[3])<<24);
        /* Alpha remains PREVIOUS. Fog factor is perspective interpolated
         * independently of primary alpha and both game texture coordinates. */
    }
    C3D_FVUnifSet(GPU_VERTEX_SHADER,g.scale_loc,''')
        (d / 'ds34_gpu_native.c').write_text(gpu)
        draw = (P / '3ds/source/ds22_draw.c').read_text()
        draw = replace(draw, 'memcpy(packed[i].color,v[i].color,16);memcpy(packed[i].tex,v[i].tex,32);', '''memcpy(packed[i].color,v[i].color,16);memcpy(packed[i].tex,v[i].tex,32);
            packed[i].tex[0][2]=(v[i].fog_factor*7+.5f)/8;packed[i].tex[1][2]=.5f;''')
        (d / 'ds22_draw.c').write_text(draw)
        shader = (P / '3ds/source/ds34_gpu.v.pica').read_text()
        shader = replace(shader, '.out uv1_out texcoord1', '.out uv1_out texcoord1\n.out fog_out texcoord2')
        shader = replace(shader, '    end', '    mov fog_out.x, uv0_in.z\n    mov fog_out.y, uv1_in.z\n    end')
        if args.projective_texture0:
            shader=replace(shader,'.out uv0_out texcoord0','.out uv0_out texcoord0.st\n.out - texcoord0w uv0_out.p')
            shader=replace(shader,'    end','    mov uv0_out.z, uv0_in.w\n    end')
        (d / 'scene.v.pica').write_text(shader)
        subprocess.run([str(P / 'toolchain/devkitpro/tools/bin/picasso.exe'), '-o', str(d / 'ds34.shbin'), str(d / 'scene.v.pica')], check=True)
        blob = (d / 'ds34.shbin').read_bytes()
        (d / 'ds34_shader.h').write_text('static const unsigned char ds34_shader[] __attribute__((aligned(4)))={' + ','.join(map(str, blob)) + '};\n')
    if args.lazy_scene_residency:
        assert args.fog
        draw=(d/'ds22_draw.c').read_text()
        draw=replace(draw, '#include "ds34_gpu.h"', '#include "ds34_gpu.h"\nint ds_scene_defer_resident(void) __attribute__((weak));')
        draw=replace(draw, 'if(o && o->levels[0].defined && ds15_resident(&c->texture,o,0))return;',
                     'if(o && o->levels[0].defined && !(ds_scene_defer_resident && ds_scene_defer_resident() && ds34_active && ds34_active(c) && !c->framebuffer_binding) && ds15_resident(&c->texture,o,0))return;')
        (d/'ds22_draw.c').write_text(draw)
        gpu=(d/'ds34_gpu_native.c').read_text()
        gpu=replace(gpu, 'unsigned bytes=pw*ph*4;if(bytes>BUDGET)', 'if(defined && ds15_resident(&g.ctx->texture,o,0))return NULL;\n    unsigned bytes=pw*ph*4;if(bytes>BUDGET)')
        (d/'ds34_gpu_native.c').write_text(gpu)
        source=replace(source, '#include "native_scene_observer.h"', '#include "native_scene_observer.h"\nint ds_scene_defer_resident(void){return scene_started;}')
        (d/'native-game-memory.c').write_text(source)
    if args.texture_trace:
        from scene_texture_working_set import instrument
        gpu = instrument((d/'ds34_gpu_native.c').read_text())
        (d/'ds34_gpu_native.c').write_text(gpu)
        source=(d/'native-game-memory.c').read_text()
        source=replace(source, 'loading_flush();menu_input_ack();scene_observe();',
                       'loading_flush();menu_input_ack();scene_observe();scene_texture_flush();')
        source=replace(source, '#include "native_scene_observer.h"',
                       '#include "native_scene_observer.h"\n#include "native_scene_textures.h"')
        shutil.copyfile(P/'tests/native_scene_textures.h',d/'native_scene_textures.h')
        (d/'native-game-memory.c').write_text(source)
    if args.visible_textures:
        assert args.lazy_scene_residency
        from scene_texture_working_set import visible_textures
        (d/'ds34_gpu_native.c').write_text(visible_textures((d/'ds34_gpu_native.c').read_text()))
    if args.projective_texture0:
        assert args.visible_textures and args.fog
        from scene_texture_working_set import projective_texture0
        (d/'ds34_gpu_native.c').write_text(projective_texture0((d/'ds34_gpu_native.c').read_text()))
    if args.uv_trace:
        assert args.projective_texture0 and args.texture_trace
        gpu=(d/'ds34_gpu_native.c').read_text()
        gpu=replace(gpu,'if(scene_draw_pending){scene_draw_pending=0;if(scene_materialize_draw(c)<0)return -1;}',
                    'void scene_uv_triangle(unsigned,const DS34Vertex *) __attribute__((weak));\n    if(scene_uv_triangle)scene_uv_triangle(g.draws,vertices);\n    if(scene_draw_pending){scene_draw_pending=0;if(scene_materialize_draw(c)<0)return -1;}')
        (d/'ds34_gpu_native.c').write_text(gpu)
        source=(d/'native-game-memory.c').read_text()
        source=replace(source,'#include "native_scene_textures.h"','#include "native_scene_textures.h"\n#include "native_scene_uv.h"')
        source=replace(source,'scene_texture_flush();','scene_texture_flush();scene_uv_flush();')
        shutil.copyfile(P/'tests/native_scene_uv.h',d/'native_scene_uv.h')
        (d/'native-game-memory.c').write_text(source)
    if args.morton_backing:
        assert args.projective_texture0 and args.texture_trace
        gpu=(d/'ds34_gpu_native.c').read_text()
        gpu=replace(gpu,'void ds34_texture_dirty(DS15State *s,DS15Object *o){',
                    'static void scene_morton_dirty(DS15Object *);\nvoid ds34_texture_dirty(DS15State *s,DS15Object *o){')
        gpu=replace(gpu,'drop(&g.entries[i]);scene_texture_reason=0;',
                    'drop(&g.entries[i]);scene_texture_reason=0;scene_morton_dirty(o);')
        gpu=replace(gpu,'static Entry *texture(DS15Object *o){',
                    '#include "native_scene_morton.h"\nint ds_scene_defer_resident(void) __attribute__((weak));\nstatic Entry *texture(DS15Object *o){\n    if(ds_scene_defer_resident && ds_scene_defer_resident())return scene_morton_texture(o);')
        (d/'ds34_gpu_native.c').write_text(gpu)
        for name in ['native_scene_morton.h','scene_morton_store.h','scene_morton_store.c','native_scene_morton_profile.h']:
            shutil.copyfile(P/'tests'/name,d/name)
        for name in ['lz4.c','lz4.h','LICENSE','source.json']:
            shutil.copyfile(P/'3ds/vendor/lz4-v1.10.0'/name,d/('lz4-'+name if name in ['LICENSE','source.json'] else name))
        source=(d/'native-game-memory.c').read_text()
        source=replace(source,'#include "native_scene_textures.h"','#include "native_scene_textures.h"\n#include "native_scene_morton_profile.h"')
        source=replace(source,'scene_texture_flush();','scene_texture_flush();scene_morton_profile();')
        (d/'native-game-memory.c').write_text(source)
    command = [s.replace(str(BASE), str(d)) for s in m['commands'][0]]
    command = ['-DMENU_ALLOW_SCENE=1' if s.startswith('-DMENU_ALLOW_SCENE=') else
               '-DMENU_CALLBACKS=' + str(args.callbacks) if s.startswith('-DMENU_CALLBACKS=') else s for s in command]
    command.insert(1, '-DSCENE_RESIDENT_MIB=' + str(args.scene_resident_mib))
    assert 30 <= args.scene_seconds <= 9000
    command.insert(1, '-DSCENE_SECONDS=' + str(args.scene_seconds))
    codec_command=None
    if args.morton_backing:
        codec=d/'lz4.c'
        if args.fast_morton_codec:
            codec=d/'lz4-fast.o'
            codec_command=[command[0],'-march=armv6k','-mtune=mpcore','-mfloat-abi=hard','-mtp=soft','-O3','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-c',str(d/'lz4.c'),'-o',str(codec)]
            subprocess.run(codec_command,cwd=d,check=True)
        command[1:1]=[str(d/'scene_morton_store.c'),str(codec)]
    assert not args.fast_morton_codec or args.morton_backing
    if args.audio:
        command = [str(d / 'ds10_jni.c') if s == str(P / '3ds/source/ds10_jni.c') else s for s in command]
    if args.fog:
        command = [str(d / 'ds22_draw.c') if s == str(P / '3ds/source/ds22_draw.c') else s for s in command]
    if args.home_at:
        assert 4323 < args.home_at < args.callbacks
        shutil.copyfile(P/'3ds/build-native-game-v0.1.7-releasehome/apt-test.o',d/'apt-test.o')
        command[1:1]=[str(d/'apt-test.o'),'-DTEST_APT_CLOSE=1','-DTEST_MENU_HOME_FRAME='+str(args.home_at)]
    subprocess.run(command, cwd=d, check=True)
    cxi = makerom('cxi', d)
    subprocess.run(cxi, cwd=d, check=True)
    m.update(revision=args.revision, callbacks=args.callbacks, scene_probe=True,
             confirm_tail_callbacks=None, emulator_only=True, CIA_created=False,
             audio_init=args.audio,
             scene_gpu=args.scene_gpu,
             fog=args.fog,
             scene_resident_mib=args.scene_resident_mib,
             pressure_evict=args.pressure_evict,
             lazy_scene_residency=args.lazy_scene_residency, scene_seconds=args.scene_seconds,
             texture_trace=args.texture_trace,
             visible_textures=args.visible_textures,
             projective_texture0=args.projective_texture0,
             uv_trace=args.uv_trace,
             morton_backing=args.morton_backing,
             fast_morton_codec=args.fast_morton_codec,
             test_HOME_callback=args.home_at, test_only_SDK_sha256=sha(d/'apt-test.o') if args.home_at else None,
             commands=[command, cxi], hardware_tested=False,
             codec_command=codec_command,
             source_sha256=sha(d / 'native-game-memory.c'),
             outputs_sha256={n: sha(d / n) for n in m['outputs_sha256']})
    m['headers_sha256']={p.name:sha(p) for p in d.glob('*.h')}
    m['runtime_sha256']={n:sha(d/n) for n in RUNTIME}
    m['loading_sources_sha256']={n:sha(d/n) for n in ['ds15_textures.c','ds26_framebuffer.c']}
    m['generated_sources_sha256']={p.name:sha(p) for p in d.glob('*.c')}
    m['compile_inputs_sha256']={s:sha(Path(s)) for s in command if Path(s).is_file() and s.endswith(('.c','.o','.a'))}
    m['builder_sha256']=sha(Path(__file__))
    (d / 'build-manifest.json').write_text(json.dumps(m, indent=2) + '\n')
    print('Built emulator scene CXI', d.name)


if __name__ == '__main__':
    main()
