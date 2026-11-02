/* Included after original DS34 drop(): that blocking retirement path is reused.
 * New linear images are populated before publication, then immutable until drop.
 * GPU LRU capacity stays 8 MiB. Disk metadata is separately bounded at 128 keys. */
#include "scene_morton_store.h"
typedef struct {DS15Object *object;uint32_t pw,ph,ws,wt,stamp;DSMortonPage page;} SceneMorton;
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
static Entry *scene_morton_texture(DS15Object *o){
    DS15Level *l=o?&o->levels[0]:NULL;int defined=l && l->defined;
    unsigned w=defined?l->width:1,h=defined?l->height:1,pw=pot(w),ph=pot(h),bytes=pw*ph*4;
    uint32_t ws=o?o->wrap_s:0x812f,wt=o?o->wrap_t:0x812f;
    if((pw!=w && ws==0x2901 && (w&(w-1))) || (ph!=h && wt==0x2901 && (h&(h-1)))){fail("GPU NPOT repeat unsupported",w);return NULL;}
    for(unsigned i=0;i<CACHE;++i){Entry *e=&g.entries[i];if(e->used && e->object==o){
        if((pw!=w || ph!=h) && (e->wrap_s!=ws || e->wrap_t!=wt)){drop(e);break;}
        scene_texture_event(1,o,e->bytes,g.bytes,0,e->tex.fmt);e->stamp=++g.stamp;return e;
    }}
    scene_texture_event(2,o,bytes,g.bytes,0,0);
    if(bytes>BUDGET){fail("GPU texture budget",bytes);return NULL;}
    SceneMorton *key=o?scene_morton_key(o,pw,ph,pw!=w?ws:0,ph!=h?wt:0):NULL;
    if((!key || !key->page.token) && defined && ds15_resident(&g.ctx->texture,o,0))return NULL;
    Entry *entry=NULL;
    for(;;){
        for(unsigned i=0;i<CACHE;++i)if(!g.entries[i].used){entry=&g.entries[i];break;}
        if(entry && g.bytes+bytes<=BUDGET)break;
        Entry *victim=NULL;for(unsigned i=0;i<CACHE;++i){Entry *e=&g.entries[i];if(e->used && e->object!=g.protected[0] && e->object!=g.protected[1] && (!victim || e->stamp<victim->stamp))victim=e;}
        if(!victim){fail("GPU pinned texture budget",bytes);return NULL;}drop(victim);
    }
    if(!C3D_TexInit(&entry->tex,pw,ph,GPU_RGBA8)){
        if(sync_gpu())return NULL;
        if(!C3D_TexInit(&entry->tex,pw,ph,GPU_RGBA8)){fail("GPU Morton allocation",bytes);return NULL;}
    }
    uint8_t *data=entry->tex.data;
    if(key && key->page.token){
        if(ds_morton_load(&key->page,data,bytes)){C3D_TexDelete(&entry->tex);fail("GPU Morton backing CRC/read",bytes);return NULL;}
    }else{
        for(unsigned j=0;j<bytes/4;++j){unsigned tile=j/64,m=j&63;
            unsigned x=(tile%(pw/8))*8+((m&1)|((m>>1)&2)|((m>>2)&4));
            unsigned y=ph-1-((tile/(pw/8))*8+(((m>>1)&1)|((m>>2)&2)|((m>>3)&4)));
            unsigned sx=ws==0x2901?x%w:x>=w?w-1:x,sy=wt==0x2901?y%h:y>=h?h-1:y;
            const uint8_t black[4]={0,0,0,255};const uint8_t *p=defined?l->rgba+(sy*w+sx)*4:black;
            data[j*4]=p[3];data[j*4+1]=p[2];data[j*4+2]=p[1];data[j*4+3]=p[0];
        }
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
