/* File output is deliberately separate from the memory-only observer. */
#include "gx_watch.h"
#include <stdio.h>
static const char *names[GW_EVENTS]={"PSC0","P3D","PPF","PSC1","DMA"};
static unsigned long long ticks(u32 lo,u32 hi){return ((u64)hi<<32)|lo;}
static void queue(FILE *f,GwQueue q){fprintf(f,"{\"total\":%lu,\"submitted\":%lu,\"completed\":%lu,\"capacity\":%lu}",
    (unsigned long)q.total,(unsigned long)q.submitted,(unsigned long)q.completed,(unsigned long)q.capacity);}
static void words(FILE *f,const u32 *p){fputc('[',f);for(unsigned j=0;j<8;++j)fprintf(f,"%s%lu",j?",":"",(unsigned long)p[j]);fputc(']',f);}
int gw_save(const char *path){
    if(gw_critical()){gw_blocked_io();return -1;}
    const GwData *d=gw_data();FILE *f=fopen(path,"w");if(!f)return -1;
    fprintf(f,"{\"version\":\"0.2.0\",\"armed\":%s,\"tick_hz\":%lu,\"fault\":%s,\"window_timeout\":%s,\"elapsed_ms\":%lu,\"vblank_phases\":%lu,\"overflow\":%lu,\"critical_io_blocked\":%lu,\"nonblock_attempted\":%s,\"nonblock_result\":%s,\"pica_bytes\":%lu,\"pica_rejected\":%lu,\"pica_address\":%lu,\"decision_index\":%lu,\"samples\":[",
        d->armed?"true":"false",(unsigned long)SYSCLOCK_ARM11,d->fault?"true":"false",d->window_timeout?"true":"false",
        (unsigned long)d->elapsed_ms,(unsigned long)d->vblank_phases,(unsigned long)d->overflow,(unsigned long)d->io_blocked,
        d->nonblock_attempted?"true":"false",d->nonblock_result?"true":"false",(unsigned long)d->pica_bytes,(unsigned long)d->pica_rejected,(unsigned long)d->pica_address,(unsigned long)d->decision);
    for(unsigned i=0;i<d->sample_count;++i){const GwSample *s=&d->samples[i];
        fprintf(f,"%s{\"phase\":%lu,\"tick\":%llu,\"queue_address\":%lu,\"queue\":",i?",":"",(unsigned long)s->phase,ticks(s->lo,s->hi),(unsigned long)s->queue_address);queue(f,s->queue);
        fprintf(f,",\"queue_stable\":%s,\"events_consistent\":%s,\"idle\":%s,\"event_serial\":%lu,\"vblank\":[%lu,%lu],\"counts\":{",
            s->queue_stable?"true":"false",s->event_consistent?"true":"false",s->idle?"true":"false",(unsigned long)s->event_serial,(unsigned long)s->vblank[0],(unsigned long)s->vblank[1]);
        for(unsigned j=0;j<GW_EVENTS;++j)fprintf(f,"%s\"%s\":%lu",j?",":"",names[j],(unsigned long)s->counts[j]);
        fputs("}}",f);
    }
    fputs("],\"queue_records\":[",f);int comma=0;
    u32 end=__atomic_load_n(&d->run_reserved,__ATOMIC_ACQUIRE);
    for(unsigned i=0;i<end && i<GW_QUEUE_RECORDS;++i){const GwRun *r=&d->runs[i];if(__atomic_load_n(&r->commit,__ATOMIC_ACQUIRE)!=i+1)continue;
        fprintf(f,"%s{\"index\":%u,\"kind\":%lu,\"tick\":%llu,\"queue\":",comma?",":"",i,(unsigned long)r->kind,ticks(r->lo,r->hi));comma=1;queue(f,r->queue);fputs(",\"entries\":[",f);
        for(unsigned j=0;j<r->queue.total && j<32;++j){if(j)fputc(',',f);words(f,r->words[j]);}fputs("]}",f);
    }
    fputs("],\"submits\":[",f);comma=0;end=__atomic_load_n(&d->submit_reserved,__ATOMIC_ACQUIRE);
    for(unsigned i=0;i<end && i<GW_SUBMITS;++i){const GwSubmit *s=&d->submits[i];if(__atomic_load_n(&s->entered,__ATOMIC_ACQUIRE)!=i+1)continue;
        u32 returned=__atomic_load_n(&s->returned,__ATOMIC_ACQUIRE);
        fprintf(f,"%s{\"index\":%u,\"tick\":%llu,\"returned\":%s,\"result\":%lu,\"return_tick\":%llu,\"words\":",comma?",":"",i,ticks(s->lo,s->hi),returned?"true":"false",(unsigned long)(returned?s->result:0),returned?ticks(s->end_lo,s->end_hi):0);comma=1;words(f,s->words);fputc('}',f);
    }
    fputs("],\"events\":[",f);comma=0;end=__atomic_load_n(&d->event_committed,__ATOMIC_ACQUIRE);
    for(unsigned i=0;i<end && i<GW_EVENT_RECORDS;++i){const GwEvent *e=&d->events[i];if(__atomic_load_n(&e->commit,__ATOMIC_ACQUIRE)!=i+1)continue;
        fprintf(f,"%s{\"order\":%u,\"name\":\"%s\",\"tick\":%llu,\"queue_after_SDK_handler\":",comma?",":"",i+1,names[e->id],ticks(e->lo,e->hi));comma=1;queue(f,e->queue);fputc('}',f);
    }
    fputs("]}\n",f);int bad=ferror(f);if(fclose(f))bad=1;return bad?-1:0;
}
int gw_save_pica(const char *path){
    if(gw_critical()){gw_blocked_io();return -1;}
    const GwData *d=gw_data();if(!d->pica_bytes || d->pica_rejected)return -1;
    FILE *f=fopen(path,"wb");if(!f)return -1;int bad=fwrite(d->pica,1,d->pica_bytes,f)!=d->pica_bytes;if(fclose(f))bad=1;return bad?-1:0;
}
