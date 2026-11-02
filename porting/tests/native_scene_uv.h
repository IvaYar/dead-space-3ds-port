/* Returned-draw UV footprint. No IO/allocation while GPU commands are built. */
typedef struct {u32 draw,unit,name,w,h,ws,wt,filter,triangles;float x0,y0,x1,y1,q0,q1;} SceneUV;
static SceneUV scene_uv[384];
static u32 scene_uv_count,scene_uv_overflow,scene_uv_last[2]={~0u,~0u};
void scene_uv_triangle(unsigned draw,const DS34Vertex *v){
    if(!scene_started || current_frame<4386 || current_frame>4500)return;
    for(unsigned u=0;u<2;++u)if(graphics.texture.enabled[u]){
        u32 index=scene_uv_last[u];DS15Object *o=graphics.draw->sampler[u];if(!o || !o->levels[0].defined)continue;
        if(index>=scene_uv_count || scene_uv[index].draw!=draw){
            if(scene_uv_count==384){++scene_uv_overflow;continue;}
            index=scene_uv_count++;scene_uv_last[u]=index;
            u32 name=0;for(u32 j=0;j<DS15_TEXTURES;++j)if(graphics.texture.textures[j].object==o){name=graphics.texture.textures[j].name;break;}
            scene_uv[index]=(SceneUV){draw,u,name,o->levels[0].width,o->levels[0].height,o->wrap_s,o->wrap_t,o->mag_filter,0,INFINITY,INFINITY,-INFINITY,-INFINITY,INFINITY,-INFINITY};
        }
        SceneUV *r=&scene_uv[index];++r->triangles;
        for(unsigned i=0;i<3;++i){float q=v[i].tex[u][3],x=v[i].tex[u][0]/q,y=v[i].tex[u][1]/q;
            r->x0=fminf(r->x0,x);r->x1=fmaxf(r->x1,x);r->y0=fminf(r->y0,y);r->y1=fmaxf(r->y1,y);r->q0=fminf(r->q0,q);r->q1=fmaxf(r->q1,q);
        }
    }
}
static void scene_uv_flush(void){
    if(!scene_uv_count && !scene_uv_overflow)return;
    char name[192];path(name,"scene-uv.jsonl");FILE *f=fopen(name,"a");if(!f)fatal("scene UV output");
    for(u32 i=0;i<scene_uv_count;++i){SceneUV *r=&scene_uv[i];
        fprintf(f,"{\"frame\":%lu,\"draw\":%lu,\"unit\":%lu,\"name\":%lu,\"w\":%lu,\"h\":%lu,\"wrap\":[%lu,%lu],\"filter\":%lu,\"triangles\":%lu,\"uv\":[%.9g,%.9g,%.9g,%.9g],\"q\":[%.9g,%.9g]}\n",(unsigned long)current_frame,(unsigned long)r->draw,(unsigned long)r->unit,(unsigned long)r->name,(unsigned long)r->w,(unsigned long)r->h,(unsigned long)r->ws,(unsigned long)r->wt,(unsigned long)r->filter,(unsigned long)r->triangles,(double)r->x0,(double)r->y0,(double)r->x1,(double)r->y1,(double)r->q0,(double)r->q1);
    }
    if(fclose(f))fatal("scene UV close");
    if(scene_uv_overflow)fatal("scene UV overflow");
    scene_uv_count=0;scene_uv_last[0]=scene_uv_last[1]=~0u;
}
