/* Private disposable GPU backing. Independent LZ4 blocks, bounded scratch,
 * strict header/length/EOF/encoded and decoded CRC. No texture approximation. */
#include "scene_morton_store.h"
#include "lz4.h"
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>
typedef uint32_t u32;typedef uint8_t u8;
#include "native_menu_page_crc.h"
#ifndef DS_MORTON_ROOT
#define DS_MORTON_ROOT "sdmc:/3ds/deadspace/test-output/morton-pages"
#endif
#define BLOCK 262144u
#define MAGIC 0x504d5344u
static unsigned char packed[LZ4_COMPRESSBOUND(BLOCK)];
static LZ4_stream_t compression_state;
static uint32_t serial;
static DSMortonStats stats;
static uint32_t crc_slice[3][256];
static int crc_ready;
uint32_t ds_morton_checksum(const void *input,uint32_t bytes){
    if(bytes<16)return menu_page_crc_exact(input,bytes);
    if(!crc_ready){
        for(unsigned i=0;i<256;++i){uint32_t c=menu_page_crc_table[i];for(unsigned k=0;k<3;++k){c=menu_page_crc_table[c&255]^(c>>8);crc_slice[k][i]=c;}}
        crc_ready=1;
    }
    const uint8_t *p=input;uint32_t crc=~0u;
    while(bytes && ((uintptr_t)p&3)){crc=menu_page_crc_table[(crc^*p++)&255]^(crc>>8);--bytes;}
    p=__builtin_assume_aligned(p,4);
    while(bytes>=4){uint32_t word;__builtin_memcpy(&word,p,4);crc^=word;
        crc=crc_slice[2][crc&255]^crc_slice[1][(crc>>8)&255]^crc_slice[0][(crc>>16)&255]^menu_page_crc_table[crc>>24];p+=4;bytes-=4;
    }
    while(bytes--){crc=menu_page_crc_table[(crc^*p++)&255]^(crc>>8);}
    return ~crc;
}
uint64_t ds_morton_clock(void) __attribute__((weak));
static uint64_t clock_now(void){return ds_morton_clock?ds_morton_clock():0;}
static uint32_t crc_exact(const void *data,uint32_t bytes){uint64_t t=clock_now();uint32_t c=ds_morton_checksum(data,bytes);stats.crc_ticks+=clock_now()-t;return c;}
static void filename(char out[192],uint32_t token){snprintf(out,192,DS_MORTON_ROOT"/image-%08lx.bin",(unsigned long)token);}
static int write_bytes(FILE *f,const void *p,uint32_t bytes){uint64_t t=clock_now();size_t n=fwrite(p,1,bytes,f);stats.write_ticks+=clock_now()-t;stats.written+=n;return n==bytes?0:-1;}
static int read_bytes(FILE *f,void *p,uint32_t bytes){uint64_t t=clock_now();size_t n=fread(p,1,bytes,f);stats.read_ticks+=clock_now()-t;stats.read+=n;return n==bytes?0:-1;}
void ds_morton_drop(DSMortonPage *p){if(p->token){char name[192];filename(name,p->token);remove(name);}memset(p,0,sizeof(*p));}
void ds_morton_stats(DSMortonStats *out){*out=stats;}
void ds_morton_limits(uint32_t out[2]){out[0]=BLOCK;out[1]=sizeof(packed)+sizeof(compression_state)+sizeof(crc_slice);}
int ds_morton_save(DSMortonPage *page,const void *pixels,uint32_t bytes){
    if(!pixels || !bytes || bytes>4194304 || serial==UINT32_MAX)goto failed;
    if(mkdir("sdmc:/3ds/deadspace/test-output",0700) && errno!=EEXIST)goto failed;
    if(mkdir(DS_MORTON_ROOT,0700) && errno!=EEXIST)goto failed;
    DSMortonPage next={++serial,bytes,crc_exact(pixels,bytes)};
    uint32_t header[5]={MAGIC,2,bytes,next.crc,BLOCK};char name[192];filename(name,next.token);
    FILE *f=fopen(name,"wb");if(!f)goto failed;
    int bad=write_bytes(f,header,sizeof(header));
    for(uint32_t offset=0;offset<bytes && !bad;){
        uint32_t n=bytes-offset;if(n>BLOCK)n=BLOCK;
        uint64_t t=clock_now();int encoded=LZ4_compress_fast_extState(&compression_state,(const char *)pixels+offset,(char *)packed,n,sizeof(packed),1);stats.encode_ticks+=clock_now()-t;
        if(encoded<=0){bad=1;break;}
        uint32_t block[3]={n,(uint32_t)encoded,crc_exact(packed,encoded)};
        bad=write_bytes(f,block,sizeof(block)) || write_bytes(f,packed,encoded);offset+=n;
    }
    if(fclose(f))bad=1;
    if(bad){remove(name);goto failed;}
    ds_morton_drop(page);*page=next;++stats.saves;stats.save_raw+=bytes;return 0;
failed:++stats.failures;return -1;
}
int ds_morton_load(const DSMortonPage *page,void *pixels,uint32_t bytes){
    if(!page->token || !pixels || !bytes || bytes!=page->bytes || bytes>4194304)goto failed;
    char name[192];filename(name,page->token);FILE *f=fopen(name,"rb");if(!f)goto failed;
    uint32_t header[5];int bad=read_bytes(f,header,sizeof(header));
    if(!bad && (header[0]!=MAGIC || header[1]!=2 || header[2]!=bytes || header[3]!=page->crc || header[4]!=BLOCK))bad=1;
    for(uint32_t offset=0;offset<bytes && !bad;){
        uint32_t block[3],n=bytes-offset;if(n>BLOCK)n=BLOCK;
        bad=read_bytes(f,block,sizeof(block));if(bad)break;
        if(block[0]!=n || !block[1] || block[1]>(uint32_t)LZ4_compressBound(n)){bad=1;break;}
        bad=read_bytes(f,packed,block[1]);if(bad)break;
        if(crc_exact(packed,block[1])!=block[2]){bad=1;break;}
        uint64_t t=clock_now();int decoded=LZ4_decompress_safe((const char *)packed,(char *)pixels+offset,block[1],n);stats.decode_ticks+=clock_now()-t;
        if(decoded!=(int)n){bad=1;break;}
        offset+=n;
    }
    if(!bad && (fgetc(f)!=EOF || ferror(f) || crc_exact(pixels,bytes)!=page->crc))bad=1;
    if(fclose(f))bad=1;
    if(bad)goto failed;
    ++stats.loads;stats.load_raw+=bytes;return 0;
failed:++stats.failures;return -1;
}
