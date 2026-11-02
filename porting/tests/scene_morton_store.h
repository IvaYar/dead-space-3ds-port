#ifndef SCENE_MORTON_STORE_H
#define SCENE_MORTON_STORE_H
#include <stdint.h>
typedef struct {uint32_t token,bytes,crc;} DSMortonPage;
/* All byte counters include headers. Failed reads never constitute a cache hit. */
typedef struct {uint64_t saves,loads,save_raw,load_raw,written,read,failures,read_ticks,write_ticks,crc_ticks,encode_ticks,decode_ticks;} DSMortonStats;
int ds_morton_save(DSMortonPage *,const void *,uint32_t);
int ds_morton_load(const DSMortonPage *,void *,uint32_t);
void ds_morton_drop(DSMortonPage *);
void ds_morton_stats(DSMortonStats *);
void ds_morton_limits(uint32_t out[2]);
uint32_t ds_morton_checksum(const void *,uint32_t);
#endif
