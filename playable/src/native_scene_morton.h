#if HW07_PREDICT_VICTIM
#include "hw07_replacement.h"
#endif
/* Included after original DS34 drop(): that blocking retirement path is reused.
 * New linear images are populated before publication, then immutable until drop.
 * GPU LRU capacity stays 8 MiB. Disk metadata is separately bounded at 128 keys. */
#include "scene_morton_store.h"
typedef struct {DS15Object *object;uint32_t pw,ph,ws,wt,stamp,fmt;DSMortonPage page;} SceneMorton;
static SceneMorton scene_morton[128];
static uint32_t scene_morton_stamp;
uint64_t ds_morton_clock(void){return svcGetSystemTick();}
static void scene_morton_dirty(DS15Object *o){
    for(unsigned i=0;i<128;++i)if(scene_morton[i].object==o){ds_morton_drop(&scene_morton[i].page);memset(&scene_morton[i],0,sizeof(scene_morton[i]));}
}
static SceneMorton *scene_morton_key(DS15Object *o,unsigned pw,unsigned ph,unsigned ws,unsigned wt){
    SceneMorton *empty=NULL,*oldest=NULL;
    for(unsigned i=0;i<128;++i){SceneMorton *r=&scene_morton[i];
        if(r->object==o && r->pw==pw && r->ph==ph && r->ws==ws && r->wt==wt){r->stamp=++scene_morton_stamp;return r;}
        if(!r->object)empty=r;
        if(!oldest || r->stamp<oldest->stamp)oldest=r;
    }
    SceneMorton *r=empty?empty:oldest;ds_morton_drop(&r->page);
    *r=(SceneMorton){.object=o,.pw=pw,.ph=ph,.ws=ws,.wt=wt,.stamp=++scene_morton_stamp};return r;
}
#include <errno.h>
#include "hq_prepared.h"
static Entry *scene_morton_texture(DS15Object *o){
    DS15Level *l=o?&o->levels[0]:NULL;int defined=l && l->defined;
    unsigned w=defined?l->width:1,h=defined?l->height:1,pw=pot(w),ph=pot(h);
    unsigned shift=lab_texture_shift(pw,ph);pw>>=shift;ph>>=shift;unsigned bytes=pw*ph*4;
    uint32_t ws=o?o->wrap_s:0x812f,wt=o?o->wrap_t:0x812f;
    if((ws==0x2901 && (w&(w-1))) || (wt==0x2901 && (h&(h-1)))){fail("GPU NPOT repeat unsupported",w);return NULL;}
#if HW07_PREDICT_VICTIM
    extern unsigned hw07_frame_id(void);hw07_cache_begin((uint32_t)o,hw07_frame_id());
#endif
    for(unsigned i=0;i<CACHE;++i){Entry *e=&g.entries[i];if(e->used && e->object==o){
        if((pw!=w || ph!=h) && (e->wrap_s!=ws || e->wrap_t!=wt)){if(drop(e))return NULL;break;}
        scene_texture_event(1,o,e->bytes,g.bytes,0,e->tex.fmt);e->stamp=++g.stamp;return e;
    }}
    SceneMorton *existing=NULL;for(unsigned i=0;o && i<128;++i)if(scene_morton[i].object==o && scene_morton[i].ws==ws && scene_morton[i].wt==wt){existing=&scene_morton[i];break;}
    HQPlan plan={0};unsigned fmt=GPU_RGBA8;
    if(existing && existing->page.token){pw=existing->pw;ph=existing->ph;fmt=existing->fmt;bytes=hq_size(pw,ph,fmt);}
    else if(defined){
        if(ds15_resident(&g.ctx->texture,o,0))return NULL;
        int status=hq_plan(&plan,l->rgba,w,h,(ws==0x2901?1u:0u)|(wt==0x2901?2u:0u));
        if(status<0){fail("HQ prepared header/read",w);return NULL;}
        if(status){pw=plan.pw;ph=plan.ph;fmt=plan.fmt;bytes=plan.bytes;}
        extern void hq_note(unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned);
        hq_note(w,h,pw,ph,fmt,bytes,plan.source,status);
    }
    scene_texture_event(2,o,bytes,g.bytes,0,fmt);
    if(bytes>BUDGET){hq_cancel(&plan);fail("GPU texture budget",bytes);return NULL;}
    SceneMorton *key=existing?existing:o?scene_morton_key(o,pw,ph,ws,wt):NULL;
    if(key)key->fmt=fmt;
    if((!key || !key->page.token) && defined && ds15_resident(&g.ctx->texture,o,0))return NULL;
    Entry *entry=NULL;
    for(;;){
        for(unsigned i=0;i<CACHE;++i)if(!g.entries[i].used){entry=&g.entries[i];break;}
        if(entry && g.bytes+bytes<=BUDGET)break;
        Entry *victim=NULL;for(unsigned i=0;i<CACHE;++i){Entry *e=&g.entries[i];if(e->used && e->object!=g.protected[0] && e->object!=g.protected[1] && (!victim ||
#if HW07_PREDICT_VICTIM
 hw07_prefer_victim((uint32_t)e->object,e->stamp,(uint32_t)victim->object,victim->stamp)
#else
 e->stamp<victim->stamp
#endif
 ))victim=e;}
        if(!victim){hq_cancel(&plan);fail("GPU pinned texture budget",bytes);return NULL;}if(drop(victim)){hq_cancel(&plan);return NULL;}
    }
    if(!C3D_TexInit(&entry->tex,pw,ph,fmt)){
        if(sync_gpu()){hq_cancel(&plan);return NULL;}
        if(!C3D_TexInit(&entry->tex,pw,ph,fmt)){hq_cancel(&plan);fail("GPU Morton allocation",bytes);return NULL;}
    }
    uint8_t *data=entry->tex.data;
    if(key && key->page.token){
        if(ds_morton_load(&key->page,data,bytes)){C3D_TexDelete(&entry->tex);fail("GPU Morton backing CRC/read",bytes);return NULL;}
    }else{
        if(plan.file){if(hq_read(&plan,data)){C3D_TexDelete(&entry->tex);fail("HQ prepared CRC/EOF",bytes);return NULL;}}
        else lab_texture_swizzle(data,defined?l->rgba:NULL,w,h,pw,ph,shift,(ws==0x2901?1u:0u)|(wt==0x2901?2u:0u));
        if(key && ds_morton_save(&key->page,data,bytes)){C3D_TexDelete(&entry->tex);fail("GPU Morton backing save",bytes);return NULL;}
    }
    if(R_FAILED(GSPGPU_FlushDataCache(data,bytes))){C3D_TexDelete(&entry->tex);fail("GPU Morton publish flush",bytes);return NULL;}
    if(key)scene_texture_event(7,o,key->page.token,bytes,key->page.crc,0);
#ifdef DS34_SEQUENCE_AUDIT
    entry->expected_hash=audit_hash(data,bytes);
#endif
    entry->object=o;entry->used=1;entry->bytes=bytes;entry->stamp=++g.stamp;entry->wrap_s=ws;entry->wrap_t=wt;g.bytes+=bytes;++g.uploads;
    scene_texture_event(4,o,bytes,g.bytes,0,entry->tex.fmt);return entry;
}
#ifdef DS_SCENE_STORE_TEST
void ds_scene_test_evict(void){for(unsigned i=0;i<CACHE;++i)drop(&g.entries[i]);}
#endif
