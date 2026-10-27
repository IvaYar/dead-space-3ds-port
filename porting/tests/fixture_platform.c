/* Original ARM softfp JNI platform/frame/float probe, no commercial code. */
#include "ds10_jni.h"
#include <stdarg.h>
typedef void *(*Find)(DSJniHandle *,const char *);
typedef void *(*Method)(DSJniHandle *,void *,const char *,const char *);
typedef void *(*ObjectA)(DSJniHandle *,void *,void *,const DS10Value *);
typedef void *(*ObjectV)(DSJniHandle *,void *,void *,va_list);
typedef float (*FloatV)(DSJniHandle *,void *,void *,va_list);
typedef float (*Float)(DSJniHandle *,void *,void *,...);
typedef int (*IntA)(DSJniHandle *,void *,void *,const DS10Value *);
typedef void (*VoidA)(DSJniHandle *,void *,void *,const DS10Value *);
typedef void (*Delete)(DSJniHandle *,void *);
typedef const char *(*Chars)(DSJniHandle *,void *,uint8_t *);
typedef void (*Release)(DSJniHandle *,void *,const char *);
typedef int (*Push)(DSJniHandle *,int);
typedef void *(*Pop)(DSJniHandle *,void *);
typedef void *(*Global)(DSJniHandle *,void *);
typedef uint8_t (*Same)(DSJniHandle *,void *,void *);
typedef uint8_t (*Check)(DSJniHandle *);
typedef void (*Clear)(DSJniHandle *);
static void *object_v(DSJniHandle *e,void *o,void *m,...){va_list a;va_start(a,m);void *r=((ObjectV)e->functions[35])(e,o,m,a);va_end(a);return r;}
static float float_v(DSJniHandle *e,void *o,void *m,...){va_list a;va_start(a,m);float r=((FloatV)e->functions[56])(e,o,m,a);va_end(a);return r;}
static int equal(const char *a,const char *b){while(*a && *a==*b){++a;++b;}return *a==*b;}
int probe_platform(DSJniHandle *env,uint32_t *out) {
    uint32_t checks=0,properties=0;int failure=0;void *system,*system2,*sysclass,*ctor,*m,*s,*display,*displayclass,*power,*powerclass,*query;
    DS10Value args[1];const char *bytes;float x,y;
#define CHECK(x) do{++checks;if(!(x)){failure=__LINE__;goto done;}}while(0)
#define CLASS(n) ((Find)env->functions[6])(env,n)
#define METHOD(c,n,s) ((Method)env->functions[33])(env,c,n,s)
#define DELETE(o) ((Delete)env->functions[23])(env,o)
    sysclass=CLASS("com/ea/blast/SystemAndroidDelegate");CHECK(sysclass);
    ctor=METHOD(sysclass,"<init>","()V");CHECK(ctor);
    system=((ObjectA)env->functions[30])(env,sysclass,ctor,0);system2=((ObjectA)env->functions[30])(env,sysclass,ctor,0);CHECK(system && system2);
    CHECK(!((Same)env->functions[24])(env,system,system2));
    static const char *names[]={
#define NAME(n) #n,
        DS11_PROPERTIES(NAME)
#undef NAME
    };
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);++i){
        m=METHOD(sysclass,names[i],"()Ljava/lang/String;");CHECK(m);
        s=object_v(env,system,m);CHECK(s);bytes=((Chars)env->functions[169])(env,s,0);CHECK(bytes);
        if(equal(names[i],"GetAccelerometerCount"))CHECK(equal(bytes,"0"));
        if(equal(names[i],"GetTotalRAM"))CHECK(equal(bytes,"67108864"));
        ((Release)env->functions[170])(env,s,bytes);DELETE(s);++properties;
    }
    for(unsigned i=0;i<20;++i){
        CHECK(!((Push)env->functions[19])(env,4));s=CLASS("com/ea/EAIO/EAIO");CHECK(s);
        CHECK(!((Pop)env->functions[20])(env,0));
    }
    CHECK(!((Push)env->functions[19])(env,4));s=CLASS("com/ea/EAIO/EAIO");
    void *global=((Global)env->functions[21])(env,s);CHECK(global);
    void *escape=((Pop)env->functions[20])(env,s);CHECK(escape && ((Same)env->functions[24])(env,escape,global));
    DELETE(escape);((Delete)env->functions[22])(env,global);
    displayclass=CLASS("com/ea/blast/DisplayAndroidDelegate");m=METHOD(displayclass,"<init>","()V");display=((ObjectA)env->functions[30])(env,displayclass,m,0);CHECK(display);
    m=METHOD(displayclass,"GetDefaultWidth","()I");CHECK(((IntA)env->functions[51])(env,display,m,0)==240);
    m=METHOD(displayclass,"GetDefaultHeight","()I");CHECK(((IntA)env->functions[51])(env,display,m,0)==400);
    m=METHOD(displayclass,"GetDpiX","()F");x=((Float)env->functions[55])(env,display,m);
    m=METHOD(displayclass,"GetDpiY","()F");y=float_v(env,display,m);CHECK(x==96.0f && y==96.0f);
    m=METHOD(displayclass,"SetStdOrientation","(I)V");args[0].i=2;((VoidA)env->functions[63])(env,display,m,args);
    m=METHOD(displayclass,"GetStdOrientation","()I");CHECK(((IntA)env->functions[51])(env,display,m,0)==2);
    powerclass=CLASS("com/ea/blast/PowerManagerAndroid");m=METHOD(powerclass,"<init>","()V");power=((ObjectA)env->functions[30])(env,powerclass,m,0);CHECK(power);
    m=METHOD(powerclass,"ApplyKeepAwake","(Z)V");args[0].i=1;((VoidA)env->functions[63])(env,power,m,args);CHECK(((DS10Context *)env->owner)->platform.keep_awake==1);
    args[0].i=0;((VoidA)env->functions[63])(env,power,m,args);CHECK(((DS10Context *)env->owner)->platform.keep_awake==0);
    query=CLASS("com/eamobile/Query");m=((Method)env->functions[113])(env,query,"getVersion","()Ljava/lang/String;");CHECK(m);
    s=((ObjectA)env->functions[116])(env,query,m,0);CHECK(s);bytes=((Chars)env->functions[169])(env,s,0);CHECK(equal(bytes,"1.1.33 Universal SD (Default)"));
    ((Release)env->functions[170])(env,s,bytes);DELETE(s);
    DELETE(query);DELETE(power);DELETE(powerclass);DELETE(display);DELETE(displayclass);DELETE(system);DELETE(system2);DELETE(sysclass);
    CHECK(!((Check)env->functions[228])(env));
done:
    out[0]=(uint32_t)failure;out[1]=checks;out[2]=properties;return failure;
}
