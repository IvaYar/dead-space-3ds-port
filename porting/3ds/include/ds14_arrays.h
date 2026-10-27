#ifndef DS14_ARRAYS_H
#define DS14_ARRAYS_H
#include "ds_elf.h"
#define DS14_BUFFERS 32
#define DS14_ARRAYS 5
#define DS14_RANGES 8
#define DS14_BINDINGS 14
typedef struct {uint32_t name,used,created,size,usage;uint8_t *data;} DS14Buffer;
typedef struct {uint32_t enabled,size,type,stride,buffer;uintptr_t pointer;} DS14Array;
typedef struct {uintptr_t base;uint32_t size;} DS14Range;
typedef struct {
    DS14Buffer buffers[DS14_BUFFERS];
    DS14Array arrays[DS14_ARRAYS]; /* vertex, normal, color, texcoord0/1 */
    DS14Range ranges[DS14_RANGES];
    uint32_t array_buffer,element_buffer,next_name,bytes,limit;
} DS14State;
void ds14_init(DS14State *);
void ds14_close(DS14State *);
uint32_t ds14_bindings(DSBinding *,uint32_t);
int ds14_query(DS14State *,uint32_t name,int32_t *out,uint32_t client_unit);
int ds14_enabled(DS14State *,uint32_t name,uint32_t client_unit); /* -1=not an array */
/* Only backend-owned readable client ranges may be registered. No ownership
 * transfer. Remove/close before the allocation dies. Not a game GL export. */
int ds14_client_range(DS14State *,const void *base,uint32_t size);
int ds14_client_remove(DS14State *,const void *base);
/* Internal staging helper: bounds-check then copy one packed raw attribute.
 * Does not draw; output remains unchanged on failure. */
int ds14_read_array(DS14State *,uint32_t slot,uint32_t index,void *out,uint32_t capacity);
#endif
