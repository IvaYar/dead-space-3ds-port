/* No IO or allocation inside GPU cache operations. Object addresses stay private. */
typedef struct {u32 kind,object,name,bytes,cached,reason,fmt,w,h,backing,ws,wt;} SceneTextureEvent;
static SceneTextureEvent scene_texture_events[512];
static u32 scene_texture_count,scene_texture_overflow;
void scene_projective_trace(unsigned unit,const DS34Vertex *v){
    static u32 count;if(count++>=4)return;
    report("PROJECTIVE_REFUSAL frame=%lu unit=%u q=%g,%g,%g names=%lu,%lu\n",(unsigned long)current_frame,unit,(double)v[0].tex[unit][3],(double)v[1].tex[unit][3],(double)v[2].tex[unit][3],(unsigned long)graphics.texture.binding[0],(unsigned long)graphics.texture.binding[1]);
}
void scene_texture_event(unsigned kind,DS15Object *o,unsigned bytes,unsigned cached,unsigned reason,unsigned fmt){
    if(!scene_started)return;
    if(kind==1)for(u32 i=0;i<scene_texture_count;++i)if(scene_texture_events[i].kind==1 && scene_texture_events[i].object==(u32)o){++scene_texture_events[i].reason;return;}
    if(kind==5)for(u32 i=0;i<scene_texture_count;++i)if(scene_texture_events[i].kind==5 && scene_texture_events[i].object==(u32)o && scene_texture_events[i].reason==reason){scene_texture_events[i].bytes+=bytes;return;}
    if(kind==6 || kind==7)for(u32 i=0;i<scene_texture_count;++i)if(scene_texture_events[i].kind==kind && scene_texture_events[i].object==(u32)o && scene_texture_events[i].bytes==bytes && scene_texture_events[i].reason==reason)return;
    if(scene_texture_count==512){++scene_texture_overflow;return;}
    u32 name=0;for(u32 i=0;i<DS15_TEXTURES;++i)if(graphics.texture.textures[i].object==o){name=graphics.texture.textures[i].name;break;}
    DS15Level *l=o?&o->levels[0]:NULL;
    scene_texture_events[scene_texture_count++]=(SceneTextureEvent){kind,(u32)o,name,bytes,cached,reason,fmt,l?l->width:0,l?l->height:0,l?l->backing:0,o?o->wrap_s:0x812f,o?o->wrap_t:0x812f};
}
static void scene_texture_flush(void){
    if(!scene_texture_count && !scene_texture_overflow)return;
    char name[192];path(name,"scene-textures.jsonl");FILE *f=fopen(name,"a");if(!f)fatal("scene texture trace output");
    for(u32 i=0;i<scene_texture_count;++i){SceneTextureEvent *e=&scene_texture_events[i];
        fprintf(f,"{\"frame\":%lu,\"kind\":%lu,\"object\":%lu,\"name\":%lu,\"bytes\":%lu,\"cached\":%lu,\"reason\":%lu,\"fmt\":%lu,\"w\":%lu,\"h\":%lu,\"backing\":%lu,\"wrap\":[%lu,%lu]}\n",(unsigned long)current_frame,(unsigned long)e->kind,(unsigned long)e->object,(unsigned long)e->name,(unsigned long)e->bytes,(unsigned long)e->cached,(unsigned long)e->reason,(unsigned long)e->fmt,(unsigned long)e->w,(unsigned long)e->h,(unsigned long)e->backing,(unsigned long)e->ws,(unsigned long)e->wt);
    }
    if(fclose(f))fatal("scene texture trace close");
    if(scene_texture_overflow){report("SCENE_TEXTURE_OVERFLOW count=%lu\n",(unsigned long)scene_texture_overflow);deferred_gpu_failure="scene texture trace overflow; returned boundary";scene_texture_overflow=0;}
    scene_texture_count=0;
}
