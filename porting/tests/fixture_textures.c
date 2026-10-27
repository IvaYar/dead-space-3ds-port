/* Independently compiled Android softfp caller, exercises >4 argument ABI. */
typedef unsigned U;
extern void glGenTextures(int,U *);
extern void glBindTexture(U,U);
extern void glDeleteTextures(int,const U *);
extern void glTexImage2D(U,int,int,int,int,int,U,U,const void *);
extern void glTexSubImage2D(U,int,int,int,int,int,U,U,const void *);
extern void glTexParameterf(U,U,float);
extern void glGetTexParameterfv(U,U,float *);
extern U glGetError(void);
int probe_textures(U *out){
    U name;unsigned char image[16]={255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255};
    unsigned char patch[4]={17,34,51,68};float filter=0;
    glGenTextures(1,&name);glBindTexture(0xde1,name);glTexParameterf(0xde1,0x2800,9728.0f);
    glGetTexParameterfv(0xde1,0x2800,&filter);if(filter!=9728.0f)return 1;
    glTexImage2D(0xde1,0,0x1908,2,2,0,0x1908,0x1401,image);
    glTexSubImage2D(0xde1,0,1,1,1,1,0x1908,0x1401,patch);
    out[0]=name;out[1]=glGetError();return out[1]?2:0;
}
