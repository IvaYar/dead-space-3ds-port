/* Original JNI ARM softfp probe. Calls ..., V and A families through the table. */
#include "ds_jni.h"
#include <stdarg.h>
typedef union { int32_t i; int64_t j; void *l; double d; } Value;
typedef void *(*Find)(DSJniHandle *,const char *);
typedef void *(*Method)(DSJniHandle *,void *,const char *,const char *);
typedef void *(*ObjA)(DSJniHandle *,void *,void *,const Value *);
typedef void *(*ObjV)(DSJniHandle *,void *,void *,va_list);
typedef int (*IntV)(DSJniHandle *,void *,void *,va_list);
typedef int (*IntA)(DSJniHandle *,void *,void *,const Value *);
typedef int64_t (*LongV)(DSJniHandle *,void *,void *,va_list);
typedef int64_t (*LongA)(DSJniHandle *,void *,void *,const Value *);
typedef void (*Void)(DSJniHandle *,void *,void *,...);
typedef void (*VoidA)(DSJniHandle *,void *,void *,const Value *);
typedef void *(*NewString)(DSJniHandle *,const char *);
typedef void *(*NewBytes)(DSJniHandle *,int32_t);
typedef void (*Region)(DSJniHandle *,void *,int32_t,int32_t,void *);
typedef void (*Delete)(DSJniHandle *,void *);
typedef uint8_t (*Exception)(DSJniHandle *);
static void *object_v(DSJniHandle *e,void *o,void *m,...) {va_list a;va_start(a,m);void *v=((ObjV)e->functions[35])(e,o,m,a);va_end(a);return v;}
static int int_v(DSJniHandle *e,void *o,void *m,...) {va_list a;va_start(a,m);int v=((IntV)e->functions[50])(e,o,m,a);va_end(a);return v;}
static int64_t long_v(DSJniHandle *e,void *o,void *m,...) {va_list a;va_start(a,m);int64_t v=((LongV)e->functions[53])(e,o,m,a);va_end(a);return v;}
int probe_jni10(DSJniHandle *env,uint32_t *out) {
    uint32_t checks=0,total=0,crc=~0u;int failure=0;void *stream=0;
    void *activity_class,*activity,*get_instance,*get_assets,*manager,*manager_class,*open,*stream_class,*read,*skip,*close,*array,*string,*eaio,*startup;
    Value a[3];uint8_t bytes[67];int n;
#define CHECK(x) do {++checks;if(!(x)){failure=__LINE__;goto done;}} while(0)
#define CLASS(name) ((Find)env->functions[6])(env,name)
#define METHOD(c,n,s) ((Method)env->functions[33])(env,c,n,s)
#define STATIC(c,n,s) ((Method)env->functions[113])(env,c,n,s)
#define DELETE(h) ((Delete)env->functions[23])(env,h)
    activity_class=CLASS("com/ea/blast/MainActivity");CHECK(activity_class);
    get_instance=STATIC(activity_class,"GetInstance","()Lcom/ea/blast/MainActivity;");CHECK(get_instance);
    activity=((ObjA)env->functions[116])(env,activity_class,get_instance,0);CHECK(activity);
    get_assets=METHOD(activity_class,"getAssets","()Landroid/content/res/AssetManager;");CHECK(get_assets);
    manager=object_v(env,activity,get_assets);CHECK(manager);
    manager_class=CLASS("android/content/res/AssetManager");CHECK(manager_class);
    eaio=CLASS("com/ea/EAIO/EAIO");startup=STATIC(eaio,"Startup","(Landroid/content/res/AssetManager;)V");CHECK(eaio && startup);
    a[0].l=manager;((VoidA)env->functions[143])(env,eaio,startup,a);CHECK(!((Exception)env->functions[228])(env));
    open=METHOD(manager_class,"open","(Ljava/lang/String;)Ljava/io/InputStream;");CHECK(open);
    string=((NewString)env->functions[167])(env,"data/achievements.sb");CHECK(string);
    a[0].l=string;stream=((ObjA)env->functions[36])(env,manager,open,a);CHECK(stream);
    DELETE(string);
    stream_class=CLASS("java/io/InputStream");CHECK(stream_class);
    read=METHOD(stream_class,"read","([BII)I");skip=METHOD(stream_class,"skip","(J)J");close=METHOD(stream_class,"close","()V");CHECK(read && skip && close);
    array=((NewBytes)env->functions[176])(env,67);CHECK(array);
    for(;;) {
        for(unsigned i=0;i<67;++i)bytes[i]=0xcc;
        ((Region)env->functions[208])(env,array,0,67,bytes);
        n=int_v(env,stream,read,array,3,61);CHECK(n>=-1 && n<=61);
        if(n==-1)break;
        CHECK(n>0);((Region)env->functions[200])(env,array,0,67,bytes);
        CHECK(bytes[0]==0xcc && bytes[1]==0xcc && bytes[2]==0xcc && bytes[3+n]==0xcc);
        for(int i=0;i<n;++i){crc^=bytes[3+i];for(unsigned j=0;j<8;++j)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));}total+=(uint32_t)n;
    }
    CHECK(total==3568 && ~crc==0x4a8d9499);
    a[0].l=array;a[1].i=0;a[2].i=0;CHECK(((IntA)env->functions[51])(env,stream,read,a)==0);
    ((Void)env->functions[61])(env,stream,close);((Void)env->functions[61])(env,stream,close);DELETE(stream);stream=0;
    string=((NewString)env->functions[167])(env,"published/data/achievements.sb");CHECK(string);
    stream=object_v(env,manager,open,string);CHECK(stream);DELETE(string);
    CHECK(long_v(env,stream,skip,(int64_t)-1)==0);
    a[0].j=2;CHECK(((LongA)env->functions[54])(env,stream,skip,a)==2);
    CHECK(long_v(env,stream,skip,INT64_C(0x100000000))==3566);
    CHECK(int_v(env,stream,read,array,0,1)==-1);
    ((VoidA)env->functions[63])(env,stream,close,0);DELETE(stream);stream=0;
    DELETE(array);DELETE(stream_class);DELETE(eaio);DELETE(manager_class);DELETE(manager);DELETE(activity);DELETE(activity_class);
    CHECK(!((Exception)env->functions[228])(env));
done:
    out[0]=(uint32_t)failure;out[1]=checks;out[2]=total;out[3]=~crc;return failure;
}
