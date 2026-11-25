/* Prepared bytes are private derived data. No texture approximation occurs at
 * draw time. Missing input safely retains the proven BALANCED converter.
 * Malformed/corrupt input fails closed before publication. Dirty events still
 * invalidate both GPU entry and run-local Morton metadata. */
#ifndef HQ_PROFILE
#define HQ_PROFILE "etcq"
#endif
typedef struct {FILE *file;unsigned pw,ph,fmt,bytes,crc,source;} HQPlan;
static unsigned hq_size(unsigned pw,unsigned ph,unsigned fmt){
    return fmt==GPU_RGBA8?pw*ph*4:fmt==GPU_RGBA4 || fmt==GPU_RGB565 || fmt==GPU_RGBA5551?pw*ph*2:fmt==GPU_ETC1?pw*ph/2:fmt==GPU_ETC1A4?pw*ph:0;
}
static __attribute__((noinline)) int hq_plan(HQPlan *p,const uint8_t *rgba,unsigned w,unsigned h,unsigned wraps){
    memset(p,0,sizeof(*p));if(!rgba || !w || !h || w>1024 || h>1024)return 0;
    p->source=ds_morton_checksum(rgba,w*h*4);
    char n[192];snprintf(n,sizeof(n),"sdmc:/3ds/ds-hq-prepared/" HQ_PROFILE "/%08lx-%u-%u-%u.bin",(unsigned long)p->source,w,h,wraps);
    FILE *f=fopen(n,"rb");if(!f){if(errno==ENOENT)return 0;return -1;}
    uint32_t a[11];int bad=fread(a,1,sizeof(a),f)!=sizeof(a);
    if(!bad)bad=a[0]!=0x34514844u || a[1]!=1 || a[2]!=p->source || a[3]!=w || a[4]!=h || a[5]!=wraps || a[6]<8 || a[7]<8 || a[6]>1024 || a[7]>1024 || (a[6]&(a[6]-1)) || (a[7]&(a[7]-1)) || !hq_size(a[6],a[7],a[8]) || a[9]!=hq_size(a[6],a[7],a[8]);
    if(!bad && (a[8]==GPU_ETC1 || a[8]==GPU_RGB565 || a[8]==GPU_RGBA5551)){
        for(unsigned i=0;i<w*h;++i)if(a[8]==GPU_RGBA5551?(rgba[i*4+3]!=0 && rgba[i*4+3]!=255):rgba[i*4+3]!=255){bad=1;break;}
    }
    if(bad){fclose(f);return -1;}
    p->file=f;p->pw=a[6];p->ph=a[7];p->fmt=a[8];p->bytes=a[9];p->crc=a[10];return 1;
}
static __attribute__((noinline)) int hq_read(HQPlan *p,void *data){
    int bad=fread(data,1,p->bytes,p->file)!=p->bytes;
    if(!bad)bad=fgetc(p->file)!=EOF || ferror(p->file) || ds_morton_checksum(data,p->bytes)!=p->crc;
    if(fclose(p->file))bad=1;
    p->file=NULL;return bad?-1:0;
}
static void hq_cancel(HQPlan *p){if(p->file){fclose(p->file);p->file=NULL;}}
