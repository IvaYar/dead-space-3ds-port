#include "ds17_jump.h"
#include <stdlib.h>
#include <string.h>
#define MAGIC 0x4278f500u
#define TAG 0x44533137u
static DS17Stats stats;
static void (*observer)(uint32_t);
void ds17_reset_stats(void){ds7_gate_lock();memset(&stats,0,sizeof(stats));ds7_gate_unlock();}
void ds17_stats(DS17Stats *out){ds7_gate_lock();*out=stats;ds7_gate_unlock();}
void ds17_observer(void (*fn)(uint32_t)){observer=fn;}
void DS_IO_SOFT ds17_record(DS17Jump *env,uint32_t kind){
    env->word[0]=MAGIC+(kind!=0);env->word[1]=0;
    env->word[30]=(uint32_t)ds7_tls();env->word[31]=TAG;
    ds7_gate_lock();++stats.saves;ds7_gate_unlock();
}
uint32_t DS_IO_SOFT ds17_validate(const DS17Jump *env,uint32_t kind){
    if(!env || ((uintptr_t)env&3))return 1;
    if(env->word[0]!=MAGIC+(kind!=0) || env->word[31]!=TAG)return 2;
    if(env->word[30]!=(uint32_t)ds7_tls())return 3;
    if(kind && env->word[1])return 4; /* No nonempty POSIX signal mask backend. */
    uint32_t sp=env->word[28],lr=env->word[29];
    if(!sp || (sp&3) || !lr || (!(lr&1) && (lr&3)))return 5;
    return 0;
}
uint32_t DS_IO_SOFT ds17_prepare(const DS17Jump *env,uint32_t kind){
    uint32_t error=ds17_validate(env,kind);ds7_gate_lock();
    if(error)++stats.refusals;else ++stats.restores;
    ds7_gate_unlock();return error;
}
void DS_IO_SOFT ds17_bad_jump(uint32_t error){if(observer)observer(error);abort();}
uint32_t ds17_bindings(DSBinding *out,uint32_t capacity){
    const DSBinding list[]={{"setjmp",(uint32_t)ds17_setjmp},{"longjmp",(uint32_t)ds17_longjmp},
        {"_setjmp",(uint32_t)ds17__setjmp},{"_longjmp",(uint32_t)ds17__longjmp}};
    if(!out || capacity<DS17_BINDINGS)return 0;
    memcpy(out,list,sizeof(list));return DS17_BINDINGS;
}
