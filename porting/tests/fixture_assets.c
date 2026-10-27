#include "ds_jni.h"
#include "assets_contract.h"
#include <stdarg.h>
typedef void *(*Find)(DSJniHandle *,const char *);
typedef void *(*Method)(DSJniHandle *,void *,const char *,const char *);
typedef void *(*Call)(DSJniHandle *,void *,void *,...);
typedef void *(*CallV)(DSJniHandle *,void *,void *,va_list);
typedef void *(*CallA)(DSJniHandle *,void *,void *,const void *);
typedef void *(*NewUTF)(DSJniHandle *,const char *);
typedef const char *(*Chars)(DSJniHandle *,void *,void *);
typedef void (*Release)(DSJniHandle *,void *,const char *);
typedef void (*Delete)(DSJniHandle *,void *);
typedef int32_t (*Length)(DSJniHandle *,void *);
typedef void *(*Element)(DSJniHandle *,void *,int32_t);
typedef void *(*NewArray)(DSJniHandle *,int32_t,void *,void *);
typedef void (*Set)(DSJniHandle *,void *,int32_t,void *);
typedef int (*Same)(DSJniHandle *,void *,void *);
typedef uint8_t (*Exception)(DSJniHandle *);
#define F(n,t) ((t)e->functions[n])
#define CHECK(x) do{++checks;if(!(x)){failure=__LINE__;goto done;}}while(0)
static void *call_v(DSJniHandle *e,void *o,void *m,...){va_list v;va_start(v,m);void *r=F(35,CallV)(e,o,m,v);va_end(v);return r;}
static uint32_t crc_byte(uint32_t crc,uint8_t b){crc^=b;for(unsigned i=0;i<8;++i)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));return crc;}
int probe_assets(DSJniHandle *e,uint32_t out[4]){
    uint32_t checks=0,total=0,crc_all=0;int failure=0;
    void *activity=F(6,Find)(e,"com/ea/blast/MainActivity");CHECK(activity);
    void *m=F(113,Method)(e,activity,"GetInstance","()Lcom/ea/blast/MainActivity;");CHECK(m);
    void *o=F(114,Call)(e,activity,m);CHECK(o);
    m=F(33,Method)(e,activity,"getAssets","()Landroid/content/res/AssetManager;");CHECK(m);
    void *manager=F(34,Call)(e,o,m);CHECK(manager);F(23,Delete)(e,o);F(23,Delete)(e,activity);
    void *clazz=F(6,Find)(e,"android/content/res/AssetManager");CHECK(clazz);
    m=F(33,Method)(e,clazz,"list","(Ljava/lang/String;)[Ljava/lang/String;");CHECK(m);
    const char *paths[]={"","published/data","appbundle:/published/textures"};
    const uint32_t counts[]={ASSET_COUNT_0,ASSET_COUNT_1,ASSET_COUNT_2},crcs[]={ASSET_CRC_0,ASSET_CRC_1,ASSET_CRC_2};
    for(unsigned dir=0;dir<3;++dir){
        void *s=F(167,NewUTF)(e,paths[dir]);CHECK(s);uint64_t args=(uint32_t)s;
        void *array=dir==0?F(34,Call)(e,manager,m,s):dir==1?call_v(e,manager,m,s):F(36,CallA)(e,manager,m,&args);
        CHECK(array);F(23,Delete)(e,s);CHECK(F(171,Length)(e,array)==(int32_t)counts[dir]);
        uint32_t crc=~0u;
        for(uint32_t i=0;i<counts[dir];++i){
            s=F(173,Element)(e,array,(int32_t)i);CHECK(s);
            const char *name=F(169,Chars)(e,s,0);CHECK(name);
            const char *cursor=name;do{crc=crc_byte(crc,(uint8_t)*cursor);}while(*cursor++);
            F(170,Release)(e,s,name);
            F(23,Delete)(e,s);
        }
        CHECK((crc^~0u)==crcs[dir]);total+=counts[dir];crc_all^=crc^~0u;F(23,Delete)(e,array);
    }
    void *strings=F(6,Find)(e,"java/lang/String");CHECK(strings);
    void *s=F(167,NewUTF)(e,"retained");CHECK(s);
    void *array=F(172,NewArray)(e,2,strings,s);CHECK(array);F(23,Delete)(e,s);
    void *a=F(173,Element)(e,array,0),*b=F(173,Element)(e,array,1);CHECK(a && b && F(24,Same)(e,a,b));
    F(174,Set)(e,array,0,0);CHECK(!F(173,Element)(e,array,0));
    F(23,Delete)(e,array);CHECK(F(168,Length)(e,a)==8);
    F(23,Delete)(e,a);F(23,Delete)(e,b);F(23,Delete)(e,strings);F(23,Delete)(e,manager);F(23,Delete)(e,clazz);
    CHECK(!F(228,Exception)(e));
done:out[0]=(uint32_t)failure;out[1]=checks;out[2]=total;out[3]=crc_all;return failure;
}
