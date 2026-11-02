#include <3ds.h>
#include <stdio.h>
#include <string.h>
#include "scene_morton_store.h"
typedef uint32_t u32;typedef uint8_t u8;
#include "native_menu_page_crc.h"
int scene_store_probe(void){
    uint8_t *source=linearAlloc(4194304),*out=linearAlloc(4194304);if(!source || !out)return -1;
    unsigned checks=0;uint32_t rng=0x12345678;
    for(unsigned i=0;i<4194304;++i){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;source[i]=(uint8_t)rng;}
    unsigned crc_vectors=0;const unsigned crc_sizes[]={0,1,3,4,7,255,65536,262145};
    for(unsigned offset=0;offset<8;++offset){
        for(unsigned j=0;j<8;++j){if(ds_morton_checksum(source+offset,crc_sizes[j])!=menu_page_crc_exact(source+offset,crc_sizes[j]))return -1;++crc_vectors;}
        if(ds_morton_checksum(source+offset,4194304-offset)!=menu_page_crc_exact(source+offset,4194304-offset))return -1;
        ++crc_vectors;
    }
    if(ds_morton_checksum("123456789",9)!=0xcbf43926u)return -1;
    ++crc_vectors;
    unsigned sizes[]={256,65536,262144,262145,4194304};DSMortonPage page={0};
    for(unsigned i=0;i<5;++i){
        if(ds_morton_save(&page,source,sizes[i]) || ds_morton_load(&page,out,sizes[i]) || memcmp(source,out,sizes[i]))return -1;
        ++checks;ds_morton_drop(&page);
    }
    memset(source,0,4194304);
    if(ds_morton_save(&page,source,4194304) || ds_morton_load(&page,out,4194304) || memcmp(source,out,4194304))return -1;
    ++checks;ds_morton_drop(&page);
    for(unsigned i=0;i<256;++i)source[i]=(uint8_t)(i*37+i/7);
    if(ds_morton_save(&page,source,256))return -1;
    char name[192];snprintf(name,sizeof(name),"sdmc:/3ds/deadspace/test-output/morton-pages/image-%08lx.bin",(unsigned long)page.token);
    FILE *f=fopen(name,"rb");if(!f)return -1;uint8_t file[2048];unsigned bytes=fread(file,1,sizeof(file),f);if(fclose(f) || bytes>=sizeof(file) || bytes<32)return -1;
    const unsigned offsets[]={0,4,8,12,16,20,24,28,32};
    for(unsigned i=0;i<9;++i){
        file[offsets[i]]^=1;f=fopen(name,"wb");if(!f)return -1;
        if(fwrite(file,1,bytes,f)!=bytes || fclose(f))return -1;
        if(!ds_morton_load(&page,out,256))return -1;
        ++checks;file[offsets[i]]^=1;
    }
    /* Encoded checksum is made consistent with altered payload; decoded CRC
     * must still reject it even if LZ4 itself decodes the altered literals. */
    file[bytes-1]^=1;uint32_t crc=menu_page_crc_exact(file+32,bytes-32);memcpy(file+28,&crc,4);
    f=fopen(name,"wb");if(!f)return -1;if(fwrite(file,1,bytes,f)!=bytes || fclose(f))return -1;
    if(!ds_morton_load(&page,out,256))return -1;
    ++checks;file[bytes-1]^=1;crc=menu_page_crc_exact(file+32,bytes-32);memcpy(file+28,&crc,4);
    f=fopen(name,"wb");if(!f)return -1;if(fwrite(file,1,bytes-1,f)!=bytes-1 || fclose(f))return -1;
    if(!ds_morton_load(&page,out,256))return -1;
    ++checks;
    f=fopen(name,"wb");if(!f)return -1;if(fwrite(file,1,bytes,f)!=bytes || fputc(1,f)==EOF || fclose(f))return -1;
    if(!ds_morton_load(&page,out,256))return -1;
    ++checks;
    f=fopen(name,"wb");if(!f)return -1;
    if(fwrite(file,1,bytes,f)!=bytes || fclose(f))return -1;
    if(!ds_morton_load(&page,out,255))return -1;
    ++checks;
    if(ds_morton_load(&page,out,256) || memcmp(source,out,256))return -1;
    ++checks;remove(name);
    if(!ds_morton_load(&page,out,256))return -1;
    ++checks;ds_morton_drop(&page);
    linearFree(source);linearFree(out);
    f=fopen("sdmc:/3ds/deadspace/scene-store-contracts.json","w");if(!f)return -1;
    fprintf(f,"{\"passed\":true,\"checks\":%u,\"max_roundtrip_bytes\":4194304,\"corruptions_rejected\":14,\"crc_vectors\":%u}\n",checks,crc_vectors);
    return fclose(f)?-1:0;
}
