/* Original compiled softfp test module, resolved through the GL registry. */
#include <stdint.h>
extern void glGenBuffers(int32_t,uint32_t *);
extern void glBindBuffer(uint32_t,uint32_t);
extern void glBufferData(uint32_t,int32_t,const void *,uint32_t);
extern void glBufferSubData(uint32_t,int32_t,int32_t,const void *);
extern void glGetBufferParameteriv(uint32_t,uint32_t,int32_t *);
extern void glVertexPointer(int32_t,uint32_t,int32_t,const void *);
extern void glGetPointerv(uint32_t,void **);
extern void glDeleteBuffers(int32_t,const uint32_t *);
extern uint32_t glGetError(void);
int probe_arrays(uint32_t *out){
    uint32_t name=0;int32_t size=-1;uint32_t data[6]={1,2,3,4,5,6},patch=0x12345678;void *pointer=(void *)99;
    glGenBuffers(1,&name);if(!name)return 1;glBindBuffer(0x8892,name);
    glBufferData(0x8892,24,data,0x88e4);glBufferSubData(0x8892,12,4,&patch);
    glVertexPointer(3,0x1406,12,(void *)4);glGetPointerv(0x808e,&pointer);
    glGetBufferParameteriv(0x8892,0x8764,&size);
    out[0]=name;out[1]=(uint32_t)size;out[2]=(uint32_t)pointer;
    if(size!=24 || pointer!=(void *)4 || glGetError())return 2;
    glDeleteBuffers(1,&name);return glGetError()?3:0;
}
