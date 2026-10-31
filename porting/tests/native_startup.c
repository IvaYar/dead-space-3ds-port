/* Startup only. No donor, original assets, DS34, Citro3D or PICA commands. */
#include <3ds.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

u32 __ctru_heap_size=2*1024*1024;
u32 __ctru_linear_heap_size=2*1024*1024;
u32 __stacksize__=256*1024;

typedef struct {
    s64 limit,current;
    Result handle_rc,limit_rc,current_rc;
    u32 calls;
} Memory;
static Memory before_heap,after_heap;
static int main_entered;
static char folder[144];
#define ROOT "sdmc:/3ds/ds-native-startup-v0.1.0/"

static void memory(Memory *m){
    Handle h=0;ResourceLimitType kind=RESLIMIT_COMMIT;
    m->handle_rc=svcGetResourceLimit(&h,CUR_PROCESS_HANDLE);
    m->limit_rc=m->current_rc=-1;
    if(R_SUCCEEDED(m->handle_rc)){
        m->limit_rc=svcGetResourceLimitLimitValues(&m->limit,h,&kind,1);
        m->current_rc=svcGetResourceLimitCurrentValues(&m->current,h,&kind,1);
        svcCloseHandle(h);
    }
}
/* allocateHeaps.o and ctru_init.o are separate library objects. Linker wrapping
 * records the actual pre-heap commit, then calls the unmodified SDK allocator. */
void __real___system_allocateHeaps(void);
void __wrap___system_allocateHeaps(void){
    ++before_heap.calls;memory(&before_heap);
    __real___system_allocateHeaps();
    memory(&after_heap);++after_heap.calls;
}
static int valid(const Memory *m){
    return m->calls==1 && R_SUCCEEDED(m->handle_rc) && R_SUCCEEDED(m->limit_rc) && R_SUCCEEDED(m->current_rc) && m->limit>=m->current && m->current>=0;
}
static s64 available(const Memory *m){return (m->limit-m->current)&~INT64_C(4095);}
static void path(char out[192],const char *name){snprintf(out,192,"%s%s",folder,name);}
static int make_folder(void){
    if((mkdir("sdmc:/3ds",0777) && errno!=EEXIST) || (mkdir(ROOT,0777) && errno!=EEXIST))return -1;
    for(u32 i=1;i<=9999;++i){
        snprintf(folder,sizeof(folder),ROOT"run-%04lu/",(unsigned long)i);
        if(!mkdir(folder,0777))return 0;
        if(errno!=EEXIST)return -1;
    }
    return -1;
}
static int save(const char *state,int emulator,int exiting){
    char out[192];path(out,"result.json");FILE *f=fopen(out,"w");if(!f)return -1;
    fprintf(f,"{\"test\":\"startup-only\",\"state\":\"%s\",\"environment\":\"%s\",\"main_entered\":%s,\"declared_New3DS_mode_MiB\":178,\"normal_heap_bytes\":%lu,\"linear_heap_bytes\":%lu,\"probe_valid\":%s,\"pre_heap_limit_bytes\":%" PRId64 ",\"pre_heap_current_bytes\":%" PRId64 ",\"pre_heap_available_bytes\":%" PRId64 ",\"post_heap_current_bytes\":%" PRId64 ",\"heap_commit_delta_bytes\":%" PRId64 ",\"APP_region_bytes\":%lu,\"APP_memtype_raw\":%lu,\"heap_wrapper_calls\":%lu,\"game_called\":false,\"DS34_called\":false,\"PICA_submits\":0,\"START_exit_requested\":%s,\"hardware_compatibility_claimed\":false}\n",
        state,emulator?"emulator":"native",main_entered?"true":"false",(unsigned long)__ctru_heap_size,(unsigned long)__ctru_linear_heap_size,valid(&before_heap)&&valid(&after_heap)?"true":"false",before_heap.limit,before_heap.current,available(&before_heap),after_heap.current,after_heap.current-before_heap.current,(unsigned long)osGetMemRegionSize(MEMREGION_APPLICATION),(unsigned long)osGetApplicationMemType(),(unsigned long)before_heap.calls,exiting?"true":"false");
    return fclose(f);
}
int main(void){
    main_entered=1;
    gfxInitDefault();consoleInit(GFX_BOTTOM,NULL);
    s64 info=0;int emulator=svcGetSystemInfo(&info,0x20000,0)==0;
    int measured=valid(&before_heap)&&valid(&after_heap);
    printf("DS Startup Test 0.1.0\nMAIN REACHED\nREADY - START exits\n\nNo game / no 3D\nHeap: 2 MiB + 2 MiB\nDeclared N3DS mode: 178 MiB\n\nPre-heap resource limit: %" PRId64 "\nPre-heap committed: %" PRId64 "\nAvailable: %" PRId64 "\nHeap delta: %" PRId64 "\nMemory probe: %s\n",before_heap.limit,before_heap.current,available(&before_heap),after_heap.current-before_heap.current,measured?"OK":"INVALID");
    gfxFlushBuffers();
    /* Optional persistence starts only after the first visible READY; it does
     * not decide whether main was reached, and no game files are needed. */
    int sd_ok=make_folder()==0 && save("ready",emulator,0)==0;
    if(sd_ok){char out[192];path(out,"ready.txt");FILE *f=fopen(out,"w");if(f){fputs("MAIN REACHED; READY; START exits; startup only\n",f);fclose(f);}}
    printf("SD log: %s\n",sd_ok?"saved":"unavailable; START still exits");gfxFlushBuffers();
    int start=0;
    while(aptMainLoop()){
        hidScanInput();if(hidKeysDown()&KEY_START){start=1;break;}
        svcSleepThread(16666667);
    }
    if(sd_ok){
        save(start?"START_exit_requested":"APT_exit_requested",emulator,start);
        char out[192];path(out,"exit.txt");FILE *f=fopen(out,"w");if(f){fputs("Startup test: returning main; guest cleanup must be verified separately\n",f);fclose(f);}
    }
    gfxExit();return measured?0:1;
}
