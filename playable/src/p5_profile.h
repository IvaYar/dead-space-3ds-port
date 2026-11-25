/* Render-state facts, not guessed semantic effect labels. All on MAIN. */
typedef struct {u64 ticks;u32 calls,vertices,triangles,changes;} P5Class;
typedef struct {u32 caller,flags;u64 ticks;u32 calls,vertices;} P5Site;
static P5Class p5_classes[5];static P5Site p5_sites[32];
static u32 p5_prev_signature,p5_site_overflow,p5_current_caller;
void p5_note(DS13Context *c,u32 mode,u32 vertices,u32 triangles,u64 ticks){
    u32 flags=(c->blend?1u:0u)|(c->pipeline.depth?2u:0u)|(c->pipeline.alpha?4u:0u)|(c->pipeline.lighting?8u:0u)|(c->fog?16u:0u)|(c->framebuffer_binding?32u:0u);
    unsigned category=c->framebuffer_binding?4:c->blend?(c->pipeline.depth?1:2):c->pipeline.alpha?3:0;
    u32 sig=flags^mode*16777619u^c->texture.binding[0]*7919u^c->texture.binding[1]*104729u^c->pipeline.blend_src*37u^c->pipeline.blend_dst*101u^c->pipeline.depth_func*61u;
    P5Class *p=&p5_classes[category];p->calls++;p->vertices+=vertices;p->triangles+=triangles;p->ticks+=ticks;p->changes+=sig!=p5_prev_signature;p5_prev_signature=sig;
    u32 caller=p5_current_caller>=(u32)image && p5_current_caller-(u32)image<info.image_size?p5_current_caller-(u32)image:0;
    unsigned k;for(k=0;k<32;++k)if(!p5_sites[k].calls || (p5_sites[k].caller==caller && p5_sites[k].flags==flags))break;
    if(k==32){p5_site_overflow++;return;}P5Site *s=&p5_sites[k];s->caller=caller;s->flags=flags;s->ticks+=ticks;s->calls++;s->vertices+=vertices;
}
static void p5_reset(void){memset(p5_classes,0,sizeof(p5_classes));memset(p5_sites,0,sizeof(p5_sites));p5_site_overflow=p5_prev_signature=0;}
static void p5_flush(u64 callback){
    if(!scene_started || (current_frame%8 && !hw_policy.ready_seen))return;
    for(unsigned k=0;k<5;++k){P5Class *p=&p5_classes[k];if(p->calls)report("P5CLASS cb=%lu category=%u calls=%lu vertices=%lu triangles=%lu ticks=%llu changes=%lu callback=%llu\n",(unsigned long)current_frame,k,(unsigned long)p->calls,(unsigned long)p->vertices,(unsigned long)p->triangles,(unsigned long long)p->ticks,(unsigned long)p->changes,(unsigned long long)callback);}
    for(unsigned k=0;k<32;++k){P5Site *p=&p5_sites[k];if(p->calls)report("P5SITE cb=%lu caller=%08lx flags=%lu calls=%lu vertices=%lu ticks=%llu overflow=%lu\n",(unsigned long)current_frame,(unsigned long)p->caller,(unsigned long)p->flags,(unsigned long)p->calls,(unsigned long)p->vertices,(unsigned long long)p->ticks,(unsigned long)p5_site_overflow);}
}
