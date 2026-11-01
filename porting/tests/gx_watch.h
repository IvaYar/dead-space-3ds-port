#ifndef GX_WATCH_H
#define GX_WATCH_H
#include <3ds.h>
#include <citro3d.h>
#define GW_EVENTS 5u
#define GW_EVENT_RECORDS 64u
#define GW_QUEUE_RECORDS 32u
#define GW_SUBMITS 32u
#define GW_SAMPLES 512u
#define GW_PICA_BYTES 4096u
enum {GW_ARM=1,GW_END_ENTER,GW_END_RETURN,GW_SYNC_ENTER,GW_POLL,GW_VBLANK1,GW_VBLANK2,
      GW_WAIT_DONE,GW_SYNC_RETURN,GW_BEGIN_ENTER,GW_BEGIN_RETURN,GW_CLOSED,GW_LATE};
typedef struct {u32 total,submitted,completed,capacity;} GwQueue;
typedef struct {u32 commit,id,lo,hi,run;GwQueue queue;} GwEvent;
typedef struct {u32 commit,kind,lo,hi,run;GwQueue queue;u32 words[32][8];} GwRun;
typedef struct {u32 entered,returned,lo,hi,end_lo,end_hi,result,run,words[8];} GwSubmit;
typedef struct {u32 phase,lo,hi,stage,queue_address;GwQueue queue;u32 queue_stable,event_consistent;
    u32 counts[GW_EVENTS],event_serial,vblank[2],idle;} GwSample;
typedef struct {
    u32 armed,critical,stage,fault,window_timeout,elapsed_ms,vblank_phases;
    u32 event_reserved,event_committed,run_reserved,submit_reserved,sample_count,decision;
    u32 overflow,io_blocked,nonblock_attempted,nonblock_result,pica_bytes,pica_rejected,pica_address;
    GwEvent events[GW_EVENT_RECORDS];GwRun runs[GW_QUEUE_RECORDS];GwSubmit submits[GW_SUBMITS];
    GwSample samples[GW_SAMPLES];u8 pica[GW_PICA_BYTES];
} GwData;
void gw_arm(int fault);
void gw_sample(unsigned phase);
void gw_observe(unsigned timeout_ms);
void gw_begin_result(int attempted,int result);
void gw_close(void);
void gw_remove(void);
int gw_critical(void);
int gw_idle(void);
int gw_safe_exit(void);
int gw_has_queue(void);
void gw_blocked_io(void);
const GwData *gw_data(void);
int gw_save(const char *path);
int gw_save_pica(const char *path);
#endif
