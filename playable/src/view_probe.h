#include "ds21_matrices.h"
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
