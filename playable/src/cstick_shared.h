/* Read-only IRRST snapshot. No SDK scan, getters or JNI on the collector. */
typedef struct {u64 sampled,publication;u32 index,valid;s16 x,y;} P7CStick;
static P7CStick p7_cstick;
static void p7_ir_publish(P7CStick *saved,const P7CStick *next,int valid){
    if(!valid){saved->valid=0;return;}
    if(!saved->sampled || next->publication!=saved->publication)*saved=*next;
    else saved->valid=1; /* Recovery cannot renew the age of old data. */
}
static int p7_ir_read(volatile u32 *mem,P7CStick *out,u64 now){
    if(!mem)return 0;
    for(unsigned a=0;a<3;++a){
        u32 i=mem[4],lo=mem[0],hi=mem[1];
        if(i>7 || (s32)hi<0 || (!i && ((s32)mem[3]<0 || (lo==mem[2] && hi==mem[3]))))return 0;
        __sync_synchronize();u32 axes=mem[9+i*4];__sync_synchronize();
        if(i!=mem[4] || lo!=mem[0] || hi!=mem[1])continue;
        *out=(P7CStick){now,((u64)hi<<32)|lo,i,1,(s16)axes,(s16)(axes>>16)};return 1;
    }return 0;
}
