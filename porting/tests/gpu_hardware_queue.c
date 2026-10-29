/* Read-only observation of the pinned SDK. No callback replacement, no IRQ I/O.
 * Queue completion is aggregate: lastEntry is not the identity of a stuck job. */
#include <3ds.h>
#include <citro3d.h>
#include "gpu_hardware_diag.h"
#include <stdint.h>

#define RECORDS 256u
#define MAX_COMMANDS 32u
static FILE *journal;
static gxCmdQueue_s *tracked;
static uint32_t runs,captured;
typedef struct {uint32_t words[8],result,commit;} Submit;
static Submit records[RECORDS];
static uint32_t submit_count,printed_submits;

extern void __real_gxCmdQueueRun(gxCmdQueue_s *queue);
extern Result __real_gspSubmitGxCommand(const u32 words[8]);
extern u32 __ctru_linear_heap,__ctru_linear_heap_size;

static const char *kind(unsigned type){
    static const char *names[]={"DMA","PICA","FILL","DISPLAY","TEXCOPY","CACHE"};
    return type<6?names[type]:"UNKNOWN";
}
void gpu_queue_init(FILE *logfile){journal=logfile;}

/* Also called with the SDK queue lock held, including from the event thread. */
Result __wrap_gspSubmitGxCommand(const u32 words[8]){
    uint32_t n=__atomic_fetch_add(&submit_count,1,__ATOMIC_RELAXED);
    Submit *r=&records[n%RECORDS];__atomic_store_n(&r->commit,0,__ATOMIC_RELEASE);
    for(unsigned i=0;i<8;++i)r->words[i]=words[i];
    Result result=__real_gspSubmitGxCommand(words);
    r->result=(uint32_t)result;__atomic_store_n(&r->commit,n+1,__ATOMIC_RELEASE);
    return result;
}
static void capture_first(gxCmdQueue_s *q){
    if(captured || !q || !q->entries || q->numEntries>MAX_COMMANDS)return;
    unsigned count=q->numEntries;int has_pica=0;
    for(unsigned i=0;i<count;++i)has_pica|=q->entries[i].type==1;
    if(!has_pica)return; /* Init/white texture is not the first rendered frame. */
    FILE *meta=fopen(GPU_HARDWARE_ROOT "gx-first-frame.json","w");if(!meta)return;
    int bad=0;
    fprintf(meta,"{\"version\":\"" GPU_TEST_VERSION "\",\"num_entries\":%u,\"entries\":[",count);
    for(unsigned i=0;i<count;++i){
        const gxCmdEntry_s *entry=&q->entries[i];
        fprintf(meta,"%s{\"index\":%u,\"type\":%u,\"name\":\"%s\",\"words\":[",i?",":"",i,entry->type,kind(entry->type));
        for(unsigned w=0;w<8;++w)fprintf(meta,"%s%lu",w?",":"",(unsigned long)entry->data[w]);
        fputs("]",meta);
        if(entry->type==1){
            uintptr_t address=entry->args[0];uint32_t bytes=entry->args[1];
            /* SDK GX_ProcessCommandList stores the CPU virtual pointer. Read
             * only bounded linear heap bytes, never arbitrary GPU addresses. */
            if(address>=__ctru_linear_heap && bytes && bytes<=C3D_DEFAULT_CMDBUF_SIZE &&
               !(address&7) && !(bytes&3) && address-__ctru_linear_heap<=__ctru_linear_heap_size &&
               bytes<=__ctru_linear_heap_size-(address-__ctru_linear_heap)){
                char path[128];snprintf(path,sizeof(path),GPU_HARDWARE_ROOT "gx-first-%u.pica",i);
                FILE *f=fopen(path,"wb");int saved=0;
                if(f){saved=fwrite((void*)address,1,bytes,f)==bytes;if(fclose(f))saved=0;}
                if(saved)fprintf(meta,",\"pica_file\":\"gx-first-%u.pica\",\"bytes\":%lu",i,(unsigned long)bytes);
                else bad=1;
            }else{fputs(",\"pica_capture_rejected\":true",meta);bad=1;}
        }
        fputs("}",meta);
    }
    fprintf(meta,"],\"captures_complete\":%s}\n",bad?"false":"true");if(fclose(meta))bad=1;
    captured=bad?0:1;
    if(journal){fprintf(journal,"GX FIRST FRAME CAPTURE %s\n",captured?"OK":"INCOMPLETE");fflush(journal);}
}
void gpu_queue_snapshot(const char *phase){
    if(!journal)return;
    gxCmdQueue_s *q=tracked;
    unsigned count=0,submitted=0,completed=0,capacity=0;
    if(q){
        volatile gxCmdQueue_s *v=q;count=v->numEntries;submitted=v->curEntry;completed=v->lastEntry;capacity=v->maxEntries;
    }
    fprintf(journal,"GX SNAPSHOT %s runs=%lu queue=%08lx total=%u submitted=%u completed=%u capacity=%u\n",
        phase,(unsigned long)runs,(unsigned long)(uintptr_t)q,count,submitted,completed,capacity);
    if(q && q->entries && count<=capacity && count<=MAX_COMMANDS){
        for(unsigned i=0;i<count;++i){
            const gxCmdEntry_s *e=&q->entries[i];fprintf(journal,"GX ENTRY %u %s",i,kind(e->type));
            for(unsigned w=0;w<8;++w)fprintf(journal," %08lx",(unsigned long)e->data[w]);
            fputc('\n',journal);
        }
    }
    uint32_t end=__atomic_load_n(&submit_count,__ATOMIC_ACQUIRE),begin=end>RECORDS?end-RECORDS:0;
    if(begin<printed_submits)begin=printed_submits;
    uint32_t next=end;
    for(uint32_t i=begin;i<end;++i){
        Submit *r=&records[i%RECORDS];
        if(__atomic_load_n(&r->commit,__ATOMIC_ACQUIRE)!=i+1){
            fprintf(journal,"GX SUBMIT %lu INCOMPLETE\n",(unsigned long)i);if(next>i)next=i;continue;}
        fprintf(journal,"GX SUBMIT %lu %s result=%08lx",(unsigned long)i,kind(r->words[0]&255),(unsigned long)r->result);
        for(unsigned w=0;w<8;++w)fprintf(journal," %08lx",(unsigned long)r->words[w]);
        fputc('\n',journal);
    }
    printed_submits=next;
    fflush(journal);
}
void __wrap_gxCmdQueueRun(gxCmdQueue_s *q){
    tracked=q;++runs;
    gpu_queue_snapshot("RUN BEGIN");capture_first(q);
    __real_gxCmdQueueRun(q);
    gpu_queue_snapshot("RUN RETURNED");
}
