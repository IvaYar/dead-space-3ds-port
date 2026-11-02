/* Direct GLES1.1 COMBINE -> PICA TEV. Existing texture upload, stream,
 * clipping, projection and synchronization paths remain in DS34. */
static GPU_TEVSRC scene_source(uint32_t s,unsigned unit){
    return s==0x1702?(unit?GPU_TEXTURE1:GPU_TEXTURE0):s==0x8576?GPU_CONSTANT:s==0x8577?GPU_PRIMARY_COLOR:unit?GPU_PREVIOUS:GPU_PRIMARY_COLOR;
}
static GPU_COMBINEFUNC scene_function(uint32_t f){
    switch(f){case 0x1e01:return GPU_REPLACE;case 0x2100:return GPU_MODULATE;case 0x104:return GPU_ADD;
    case 0x8574:return GPU_ADD_SIGNED;case 0x8575:return GPU_INTERPOLATE;case 0x84e7:return GPU_SUBTRACT;
    case 0x86ae:case 0x86af:return GPU_DOT3_RGB;default:return GPU_REPLACE;}
}
static int scene_combine(DS13Context *c,unsigned u,GPU_TEXCOLOR format){
    (void)format;
    const DS31Unit *v=&c->draw->combine->unit[u];C3D_TexEnv *e=C3D_GetTexEnv(u);
    C3D_TexEnvSrc(e,C3D_RGB,scene_source(v->src_rgb[0],u),scene_source(v->src_rgb[1],u),scene_source(v->src_rgb[2],u));
    C3D_TexEnvSrc(e,C3D_Alpha,scene_source(v->src_alpha[0],u),scene_source(v->src_alpha[1],u),scene_source(v->src_alpha[2],u));
    static const GPU_TEVOP_RGB rgb[]={GPU_TEVOP_RGB_SRC_COLOR,GPU_TEVOP_RGB_ONE_MINUS_SRC_COLOR,GPU_TEVOP_RGB_SRC_ALPHA,GPU_TEVOP_RGB_ONE_MINUS_SRC_ALPHA};
    C3D_TexEnvOpRgb(e,rgb[v->op_rgb[0]-0x300],rgb[v->op_rgb[1]-0x300],rgb[v->op_rgb[2]-0x300]);
    C3D_TexEnvOpAlpha(e,(GPU_TEVOP_A)(v->op_alpha[0]-0x302),(GPU_TEVOP_A)(v->op_alpha[1]-0x302),(GPU_TEVOP_A)(v->op_alpha[2]-0x302));
    C3D_TexEnvFunc(e,C3D_RGB,scene_function(v->rgb));C3D_TexEnvFunc(e,C3D_Alpha,scene_function(v->alpha));
    if(v->rgb==0x86af)C3D_TexEnvFunc(e,C3D_Both,GPU_DOT3_RGBA);
    C3D_TexEnvScale(e,C3D_RGB,v->rgb_scale==4?GPU_TEVSCALE_4:v->rgb_scale==2?GPU_TEVSCALE_2:GPU_TEVSCALE_1);
    C3D_TexEnvScale(e,C3D_Alpha,v->alpha_scale==4?GPU_TEVSCALE_4:v->alpha_scale==2?GPU_TEVSCALE_2:GPU_TEVSCALE_1);
    const float *k=c->draw->env_color[u];C3D_TexEnvColor(e,byte(k[0])|byte(k[1])<<8|byte(k[2])<<16|byte(k[3])<<24);
    return 0;
}
