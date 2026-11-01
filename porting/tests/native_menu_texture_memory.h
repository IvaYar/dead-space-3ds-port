/* Allocation policy for the menu's 1024x1024 RGBA atlas. DS34 still owns the
 * texture, immutable staging, upload, synchronization and retirement. */
static C3D_Tex *menu_linear_textures[32];
extern bool __real_C3D_TexInitWithParams(C3D_Tex *,C3D_TexCube *,C3D_TexInitParams);
bool __wrap_C3D_TexInitWithParams(C3D_Tex *tex,C3D_TexCube *cube,C3D_TexInitParams p){
    int large=p.onVram && !cube && p.type==GPU_TEX_2D && p.format==GPU_RGBA8 &&
        p.maxLevel==0 && p.width==1024 && p.height==1024;
    unsigned slot=0;
    if(large){
        while(slot<32 && menu_linear_textures[slot])++slot;
        if(slot==32)return false;
        p.onVram=false;
    }
    bool ok=__real_C3D_TexInitWithParams(tex,cube,p);
    report("TEXALLOC frame=%lu w=%u h=%u linear=%d ok=%d\n",(unsigned long)current_frame,p.width,p.height,!p.onVram,ok);
    if(large && ok){
        menu_linear_textures[slot]=tex;
        report("ATLAS linear GPU allocation bytes=%lu physical=%08lx\n",(unsigned long)tex->size,(unsigned long)osConvertVirtToPhys(tex->data));
    }
    return ok;
}
extern void __real_C3D_SyncTextureCopy(u32 *,u32,u32 *,u32,u32,u32);
void __wrap_C3D_SyncTextureCopy(u32 *src,u32 sd,u32 *dst,u32 dd,u32 size,u32 flags){
    for(unsigned i=0;i<32;++i)if(menu_linear_textures[i] && dst==menu_linear_textures[i]->data){
        if(sd || dd || size!=menu_linear_textures[i]->size || flags!=8)fatal("linear atlas upload contract");
        /* Citro3D texture.c uses memcpy for FCRAM texture storage. Keep its
         * canonical upload path and explicitly publish CPU writes to GPU. */
        C3D_TexLoadImage(menu_linear_textures[i],src,GPU_TEXFACE_2D,0);
        if(R_FAILED(GSPGPU_FlushDataCache(dst,size)))fatal("linear atlas flush");
        return;
    }
    __real_C3D_SyncTextureCopy(src,sd,dst,dd,size,flags);
}
extern void __real_C3D_TexDelete(C3D_Tex *);
void __wrap_C3D_TexDelete(C3D_Tex *tex){
    for(unsigned i=0;i<32;++i)if(tex==menu_linear_textures[i])menu_linear_textures[i]=NULL;
    __real_C3D_TexDelete(tex);
}
