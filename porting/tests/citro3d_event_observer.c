/* Public per-event callbacks only. Original SDK GX IRQ handler runs first.
 * No stdio, allocation, waits or 64-bit atomics in callbacks. */
#include "citro3d_event_observer.h"
#include <string.h>

enum {COUNT,FIRST_LO,FIRST_HI,LAST_LO,LAST_HI,FIRST_ORDER,LAST_ORDER,FIRST_RUN,LAST_RUN,Q_TOTAL,Q_SUBMITTED,Q_COMPLETED,FIELDS};
typedef struct {u32 sequence,value[FIELDS];} Event;
static Event events[3];
static const char *names[]={"PSC0","PSC1","PPF"};
static const GSPGPU_Event ids[]={GSPGPU_EVENT_PSC0,GSPGPU_EVENT_PSC1,GSPGPU_EVENT_PPF};
static gxCmdQueue_s *tracked;
static u32 run_id,serial;
static u64 origin;
static FILE *journal;
static int installed,last_consistent;
static unsigned checkpoint_number;
static u32 saved_serial;
static u32 last_good[3][FIELDS];
static char last_file[80]="none";

static void record(unsigned index){
    u64 tick=svcGetSystemTick();
    Event *e=&events[index];
    /* Only the GSP thread produces events. Publish serial after the slot. */
    u32 order=__atomic_load_n(&serial,__ATOMIC_RELAXED)+1;
    u32 before=__atomic_fetch_add(&e->sequence,1,__ATOMIC_ACQ_REL);
    u32 n=__atomic_load_n(&e->value[COUNT],__ATOMIC_RELAXED);
    u32 run=__atomic_load_n(&run_id,__ATOMIC_ACQUIRE);
    if(!n){
        __atomic_store_n(&e->value[FIRST_LO],(u32)tick,__ATOMIC_RELAXED);
        __atomic_store_n(&e->value[FIRST_HI],(u32)(tick>>32),__ATOMIC_RELAXED);
        __atomic_store_n(&e->value[FIRST_ORDER],order,__ATOMIC_RELAXED);
        __atomic_store_n(&e->value[FIRST_RUN],run,__ATOMIC_RELAXED);
    }
    __atomic_store_n(&e->value[COUNT],n+1,__ATOMIC_RELAXED);
    __atomic_store_n(&e->value[LAST_LO],(u32)tick,__ATOMIC_RELAXED);
    __atomic_store_n(&e->value[LAST_HI],(u32)(tick>>32),__ATOMIC_RELAXED);
    __atomic_store_n(&e->value[LAST_ORDER],order,__ATOMIC_RELAXED);
    __atomic_store_n(&e->value[LAST_RUN],run,__ATOMIC_RELAXED);
    volatile gxCmdQueue_s *q=__atomic_load_n(&tracked,__ATOMIC_ACQUIRE);
    __atomic_store_n(&e->value[Q_TOTAL],q?q->numEntries:0,__ATOMIC_RELAXED);
    __atomic_store_n(&e->value[Q_SUBMITTED],q?q->curEntry:0,__ATOMIC_RELAXED);
    __atomic_store_n(&e->value[Q_COMPLETED],q?q->lastEntry:0,__ATOMIC_RELAXED);
    __atomic_store_n(&e->sequence,before+2,__ATOMIC_RELEASE);
    __atomic_store_n(&serial,order,__ATOMIC_RELEASE);
}
/* Ignore callback data: libctru's setter publishes the function before data. */
static void psc0(void *unused){(void)unused;record(0);}
static void psc1(void *unused){(void)unused;record(1);}
static void ppf(void *unused){(void)unused;record(2);}

void clear_events_install(FILE *logfile){
    journal=logfile;origin=svcGetSystemTick();
    __atomic_thread_fence(__ATOMIC_RELEASE);
    /* These three slots are unused by this standalone app and pinned SDK.
     * Do not touch Citro3D's VBlank slots or gxCmdQueueSetCallback. */
    gspSetEventCallback(ids[0],psc0,NULL,false);
    gspSetEventCallback(ids[1],psc1,NULL,false);
    gspSetEventCallback(ids[2],ppf,NULL,false);
    installed=1;
    fputs("OBSERVERS INSTALLED PSC0 PSC1 PPF; SDK IRQ/VBlank/queue callbacks unchanged\n",journal);fflush(journal);
}
void clear_events_remove(void){
    if(!installed)return;
    for(unsigned i=0;i<3;++i)gspSetEventCallback(ids[i],NULL,NULL,false);
    installed=0;
}
void clear_events_track(gxCmdQueue_s *q){
    __atomic_store_n(&tracked,q,__ATOMIC_RELEASE);
    if(q && q->numEntries)__atomic_fetch_add(&run_id,1,__ATOMIC_RELEASE);
}
static int read_event(unsigned index,u32 out[FIELDS]){
    Event *e=&events[index];
    for(unsigned attempt=0;attempt<4;++attempt){
        u32 first=__atomic_load_n(&e->sequence,__ATOMIC_ACQUIRE);
        if(first&1)continue;
        for(unsigned i=0;i<FIELDS;++i)out[i]=__atomic_load_n(&e->value[i],__ATOMIC_RELAXED);
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        u32 second=__atomic_load_n(&e->sequence,__ATOMIC_ACQUIRE);
        if(first==second){memcpy(last_good[index],out,sizeof(last_good[index]));return 1;}
    }
    memcpy(out,last_good[index],sizeof(last_good[index]));return 0;
}
#ifdef CLEAR_EVENTS_FAULT
int clear_events_software_selfcheck(void){
    /* Before callback registration: no SDK producer can touch these slots.
     * Test only our recorder, not SDK event dispatch or hardware IRQ delivery. */
    if(installed)return 0;
    for(unsigned repeat=0;repeat<2;++repeat){psc0(NULL);psc1(NULL);ppf(NULL);}
    for(unsigned i=0;i<3;++i){u32 value[FIELDS];
        if(!read_event(i,value) || value[COUNT]!=2 || value[FIRST_ORDER]!=i+1 || value[LAST_ORDER]!=i+4)return 0;
        u64 first=((u64)value[FIRST_HI]<<32)|value[FIRST_LO],last=((u64)value[LAST_HI]<<32)|value[LAST_LO];
        if(!first || last<first)return 0;
    }
    memset(events,0,sizeof(events));memset(last_good,0,sizeof(last_good));
    __atomic_store_n(&serial,0,__ATOMIC_RELEASE);return 1;
}
#endif
int clear_events_changed(void){return installed && (!last_consistent || __atomic_load_n(&serial,__ATOMIC_ACQUIRE)!=saved_serial);}
const char *clear_events_last_file(void){return last_file;}
int clear_events_checkpoint(const char *label){
    if(!installed)return 0;
    u32 values[3][FIELDS],stable[3];
    u32 start=__atomic_load_n(&serial,__ATOMIC_ACQUIRE);
    for(unsigned i=0;i<3;++i)stable[i]=read_event(i,values[i]);
    u32 end=__atomic_load_n(&serial,__ATOMIC_ACQUIRE);
    int consistent=stable[0] && stable[1] && stable[2] && start==end &&
        values[0][COUNT]+values[1][COUNT]+values[2][COUNT]==end;
    volatile gxCmdQueue_s *q=__atomic_load_n(&tracked,__ATOMIC_ACQUIRE);
    unsigned total=q?q->numEntries:0,submitted=q?q->curEntry:0,completed=q?q->lastEntry:0;
    u64 sampled=svcGetSystemTick();
    char name[80],path[160];snprintf(name,sizeof(name),"events-%04u-%s.json",++checkpoint_number,label);
    snprintf(path,sizeof(path),CLEAR_EVENTS_ROOT"%s",name);FILE *f=fopen(path,"w");
    if(!f){fprintf(journal,"CHECKPOINT WRITE FAILED %s\n",name);fflush(journal);return -1;}
    fprintf(f,"{\"version\":\"" CLEAR_EVENTS_VERSION "\",\"label\":\"%s\",\"run\":%lu,\"origin_tick\":%llu,\"sample_tick\":%llu,\"tick_hz\":%lu,\"serial\":%lu,\"events_consistent\":%s,\"queue\":{\"total\":%u,\"submitted\":%u,\"completed\":%u},\"events\":{",
        label,(unsigned long)__atomic_load_n(&run_id,__ATOMIC_ACQUIRE),(unsigned long long)origin,(unsigned long long)sampled,
        (unsigned long)SYSCLOCK_ARM11,(unsigned long)end,consistent?"true":"false",total,submitted,completed);
    for(unsigned i=0;i<3;++i){u32 *v=values[i];u64 first=((u64)v[FIRST_HI]<<32)|v[FIRST_LO],last=((u64)v[LAST_HI]<<32)|v[LAST_LO];
        fprintf(f,"%s\"%s\":{\"stable\":%s,\"count\":%lu,\"first_tick\":%llu,\"last_tick\":%llu,\"first_us\":%llu,\"last_us\":%llu,\"first_order\":%lu,\"last_order\":%lu,\"first_run\":%lu,\"last_run\":%lu,\"callback_queue\":{\"total\":%lu,\"submitted\":%lu,\"completed\":%lu}}",
            i?",":"",names[i],stable[i]?"true":"false",(unsigned long)v[COUNT],(unsigned long long)first,(unsigned long long)last,
            (unsigned long long)(v[COUNT]?(first-origin)*1000000/SYSCLOCK_ARM11:0),
            (unsigned long long)(v[COUNT]?(last-origin)*1000000/SYSCLOCK_ARM11:0),
            (unsigned long)v[FIRST_ORDER],(unsigned long)v[LAST_ORDER],(unsigned long)v[FIRST_RUN],(unsigned long)v[LAST_RUN],
            (unsigned long)v[Q_TOTAL],(unsigned long)v[Q_SUBMITTED],(unsigned long)v[Q_COMPLETED]);
    }
    fputs("},\"commands\":[",f);
    if(q && q->entries && total<=q->maxEntries && total<=32)for(unsigned i=0;i<total;++i){
        fprintf(f,"%s[",i?",":"");for(unsigned w=0;w<8;++w)fprintf(f,"%s%lu",w?",":"",(unsigned long)q->entries[i].data[w]);fputs("]",f);
    }
    fputs("]}\n",f);int bad=ferror(f);if(fclose(f))bad=1;
    fprintf(journal,"EVENTS %s stable=%d PSC0=%lu PSC1=%lu PPF=%lu queue=%u/%u/%u file=%s\n",label,consistent,
        (unsigned long)values[0][COUNT],(unsigned long)values[1][COUNT],(unsigned long)values[2][COUNT],total,submitted,completed,name);fflush(journal);
    if(bad)return -1;
    memcpy(last_file,name,strlen(name)+1);last_consistent=consistent;if(consistent)saved_serial=end;return 0;
}
