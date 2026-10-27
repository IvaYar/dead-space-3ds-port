/* Android softfp calling convention: mixed enum/float and multi-value queries. */
extern void glEnable(unsigned);
extern void glCullFace(unsigned);
extern void glFrontFace(unsigned);
extern void glDepthRangef(float,float);
extern void glAlphaFunc(unsigned,float);
extern void glPolygonOffset(float,float);
extern void glGetFloatv(unsigned,float *);
extern void glGetFixedv(unsigned,int *);
extern unsigned glGetError(void);
int probe_pipeline(unsigned *out){
    float range[2],alpha,factor;int mode;
    glEnable(0xb44);glCullFace(0x404);glFrontFace(0x900);
    glDepthRangef(.75f,.25f);glAlphaFunc(0x204,.375f);glPolygonOffset(-1.5f,2.25f);
    glGetFloatv(0xb70,range);glGetFloatv(0xbc2,&alpha);glGetFloatv(0x8038,&factor);glGetFixedv(0xb45,&mode);
    if(range[0]!=.75f || range[1]!=.25f || alpha!=.375f || factor!=-1.5f || mode!=0x404)return 1;
    out[0]=(unsigned)mode;out[1]=glGetError();return out[1]?2:0;
}
