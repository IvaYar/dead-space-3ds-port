/* Independent Android ARM ABI caller. No native newlib jmp_buf. */
#ifdef DS17_THUMB_FIXTURE
#define probe_jump ds17_thumb_probe_jump
#define probe_jump_nested ds17_thumb_probe_jump_nested
#define probe_jump_underscore ds17_thumb_probe_jump_underscore
#endif
typedef struct {unsigned word[64];} Jump;
extern int setjmp(Jump *) __attribute__((returns_twice));
extern int _setjmp(Jump *) __attribute__((returns_twice));
extern void longjmp(Jump *,int) __attribute__((noreturn));
extern void _longjmp(Jump *,int) __attribute__((noreturn));
static void __attribute__((noinline)) deep(Jump *env,int value,int level){
    if(level<0)return;
    volatile unsigned scratch[16];for(unsigned i=0;i<16;++i)scratch[i]=i+(unsigned)level;
    if(level)deep(env,value,level-1);
    else longjmp(env,value);
    /* Deliberately no tail-call context to rely upon. */
    scratch[0]=scratch[1];
}
int probe_jump(unsigned *out,volatile int value){
    Jump env;volatile unsigned marker=0;
    int result=setjmp(&env);if(!result){marker=17;deep(&env,value,4);}
    out[0]=(unsigned)result;out[1]=marker;return marker==17 && result==(value?value:1)?0:1;
}
int probe_jump_nested(unsigned *out){
    Jump outer,inner;volatile unsigned phase=0;int a=setjmp(&outer);
    if(!a){int b=setjmp(&inner);if(!b){phase=1;longjmp(&inner,7);}if(b!=7 || phase!=1)return 1;phase=2;longjmp(&outer,11);}
    out[0]=(unsigned)a;out[1]=phase;return a==11 && phase==2?0:2;
}
int probe_jump_underscore(unsigned *out,volatile int value){
    Jump env;volatile unsigned marker=0;int result=_setjmp(&env);
    if(!result){marker=23;_longjmp(&env,value);}out[0]=(unsigned)result;out[1]=marker;return marker==23 && result==(value?value:1)?0:1;
}
