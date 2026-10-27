#include "ds_jni.h"
typedef void *(*New16)(DSJniHandle *,const uint16_t *,int32_t);
typedef void *(*NewUTF)(DSJniHandle *,const char *);
typedef int32_t (*Length)(DSJniHandle *,void *);
typedef const uint16_t *(*Chars16)(DSJniHandle *,void *,uint8_t *);
typedef const char *(*CharsUTF)(DSJniHandle *,void *,uint8_t *);
typedef void (*Release16)(DSJniHandle *,void *,const uint16_t *);
typedef void (*ReleaseUTF)(DSJniHandle *,void *,const char *);
typedef void (*Region)(DSJniHandle *,void *,int32_t,int32_t,void *);
typedef void (*Delete)(DSJniHandle *,void *);
typedef uint8_t (*Exception)(DSJniHandle *);
#define F(slot,type) ((type)e->functions[slot])
#define CHECK(x) do{++checks;if(!(x)){failure=__LINE__;goto done;}}while(0)
int probe_strings(DSJniHandle *e,uint32_t out[4]){
    uint16_t input[]={0x41,0,0x416,0x20ac,0xd83d,0xde80,0xd800},wide[5];
    const char encoded[]="A\xc0\x80\xd0\x96\xe2\x82\xac\xed\xa0\xbd\xed\xba\x80\xed\xa0\x80";
    uint8_t copy=99;uint32_t checks=0;int failure=0;char region[10];void *a=0,*b=0;
    a=F(163,New16)(e,input,7);CHECK(a);CHECK(F(164,Length)(e,a)==7);CHECK(F(168,Length)(e,a)==17);
    input[0]=0x42;const uint16_t *chars=F(165,Chars16)(e,a,&copy);CHECK(chars && !copy);CHECK(chars[0]==0x41);
    for(unsigned i=1;i<7;++i)CHECK(chars[i]==input[i]);
    F(166,Release16)(e,a,chars);
    const char *utf=F(169,CharsUTF)(e,a,&copy);CHECK(utf && !copy);
    for(unsigned i=0;i<18;++i)CHECK(utf[i]==encoded[i]);
    F(170,ReleaseUTF)(e,a,utf);
    for(unsigned i=0;i<5;++i)wide[i]=0x7777;
    F(220,Region)(e,a,1,3,wide);CHECK(wide[0]==0 && wide[1]==0x416 && wide[2]==0x20ac && wide[3]==0x7777);
    for(unsigned i=0;i<10;++i)region[i]='Z';
    F(221,Region)(e,a,1,3,region);
    for(unsigned i=0;i<7;++i)CHECK(region[i]==encoded[i+1]);
    CHECK(region[7]=='Z');
    b=F(167,NewUTF)(e,encoded);CHECK(b);CHECK(F(164,Length)(e,b)==7);
    chars=F(224,Chars16)(e,b,&copy);CHECK(chars && !copy && chars[0]==0x41 && chars[6]==0xd800);F(225,Release16)(e,b,chars);
    CHECK(!F(228,Exception)(e));
done:
    if(a)F(23,Delete)(e,a);
    if(b)F(23,Delete)(e,b);
    out[0]=(uint32_t)failure;out[1]=checks;out[2]=7;out[3]=17;return failure;
}
