#include "ds21_matrices.h"
#if DS_P8_LOG_FIX
/* One borrowed-state copy per returned callback; no formatting or IO in draw. */
static struct {float mv[16];u32 cb,step,vertex,count,pending;} p8_view;
static u32 p8_view_enabled;
static int p8_detailed_trace(void){return p8_view_enabled!=0;}
static void p8_view_init(void){FILE *f=fopen(ROOT "view-trace.txt","rb");p8_view_enabled=f!=NULL;if(f)fclose(f);}
void p7_view_note(DS13Context *c,u32 caller,u32 count){
    (void)caller;
    if(!p8_view_enabled || !gameplay_begin || p8_view.cb==current_frame || count<60 || c->framebuffer_binding || !c->texture.enabled[0] || !c->pipeline.depth || c->blend || !c->matrix)return;
    const float *v=c->matrix->stack[0][c->matrix->top[0]];
    if(v[12]>-20 && v[12]<20 && v[14]>-20 && v[14]<20)return;
    __builtin_memcpy(p8_view.mv,v,64);p8_view.cb=current_frame;p8_view.step=gameplay_count;p8_view.vertex=c->vertex.arrays[0].pointer;p8_view.count=count;p8_view.pending=1;
}
static void p8_view_flush(void){
    if(!p8_view.pending)return;
    p8_view.pending=0;const float *v=p8_view.mv;
    report("P7_WORLD cb=%lu step=%lu vertex=%08lx count=%lu mv=%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g\n",(unsigned long)p8_view.cb,(unsigned long)p8_view.step,(unsigned long)p8_view.vertex,(unsigned long)p8_view.count,(double)v[0],(double)v[1],(double)v[2],(double)v[3],(double)v[4],(double)v[5],(double)v[6],(double)v[7],(double)v[8],(double)v[9],(double)v[10],(double)v[11],(double)v[12],(double)v[13],(double)v[14],(double)v[15]);
}
#else
static int p8_detailed_trace(void){return 1;}
static void p8_view_init(void){}
static void p8_view_flush(void){}
/* Read the first substantial textured modelview after admission. Draw identity
 * and body oracle are required when interpreting it as camera response. */
void p7_view_note(DS13Context *c,u32 caller,u32 count){
    static u32 seen;
    if(!gameplay_begin || seen==current_frame || count<60 || c->framebuffer_binding || !c->texture.enabled[0] || !c->pipeline.depth || c->blend || !c->matrix)return;
    DS21State *m=c->matrix;float *v=m->stack[0][m->top[0]];
    if(v[12]>-20 && v[12]<20 && v[14]>-20 && v[14]<20)return;
    seen=current_frame;(void)caller;
    report("P7_WORLD cb=%lu step=%lu vertex=%08lx count=%lu mv=",(unsigned long)current_frame,(unsigned long)gameplay_count,(unsigned long)c->vertex.arrays[0].pointer,(unsigned long)count);
    for(unsigned i=0;i<16;++i)report(i==15?"%.8g\n":"%.8g,",(double)v[i]);
}
#endif
