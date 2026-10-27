/* Standalone Android softfp module: float arguments must cross the ABI. */
#include <stdint.h>
extern void glClearColor(float,float,float,float);
extern void glClearColorx(int32_t,int32_t,int32_t,int32_t);
extern void glClear(uint32_t);
extern void glViewport(int32_t,int32_t,int32_t,int32_t);
extern void glGetIntegerv(uint32_t,int32_t *);
extern uint32_t glGetError(void);
int probe_graphics(uint32_t *out){
    int32_t box[4]={0};glViewport(1,2,3,4);glGetIntegerv(0xba2,box);
    if(box[0]!=1 || box[1]!=2 || box[2]!=3 || box[3]!=4)return 1;
    glClearColor(1.0f,0.5f,0.0f,1.0f);glClear(0x4000);
    if(glGetError())return 2;
    out[0]=1;
    glClearColorx(0,65536,32768,65536);glClear(0x4000);
    if(glGetError())return 3;
    out[1]=1;return 0;
}
