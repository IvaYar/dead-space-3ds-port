/* Main/render-thread page backing profile. No IO inside a page operation. */
typedef struct {u32 frame,kind,old_token,token,bytes,crc;u64 ticks,crc_ticks;int result;} LoadingPage;
static LoadingPage loading_pages[1024];
static u32 loading_count,loading_overflow,loading_crc_value;
static u64 loading_crc_ticks;
static const DS15Backing *loading_original_backing;
static void loading_crc_observe(u32 crc,u64 ticks){loading_crc_value=crc;loading_crc_ticks+=ticks;}
static void loading_record(u32 kind,u32 old,u32 token,u32 bytes,u64 begin,u64 crc0,int result){
    if(loading_count==1024){++loading_overflow;return;}
    loading_pages[loading_count++]=(LoadingPage){current_frame,kind,old,token,bytes,loading_crc_value,svcGetSystemTick()-begin,loading_crc_ticks-crc0,result};
}
static int loading_save(u32 *token,const void *pixels,u32 bytes){
    u32 old=*token;u64 t=svcGetSystemTick(),crc0=loading_crc_ticks;
    int r=loading_original_backing->save(token,pixels,bytes);loading_record(1,old,*token,bytes,t,crc0,r);return r;
}
static int loading_load(u32 token,void *pixels,u32 bytes){
    u64 t=svcGetSystemTick(),crc0=loading_crc_ticks;
    int r=loading_original_backing->load(token,pixels,bytes);loading_record(2,token,token,bytes,t,crc0,r);return r;
}
static void loading_drop(u32 token){loading_original_backing->drop(token);}
static const DS15Backing *loading_backing(void){
    loading_original_backing=ds27_sd_backing();
    static const DS15Backing ops={loading_save,loading_load,loading_drop};
    return loading_original_backing?&ops:NULL;
}
static void loading_flush(void){
    if(!loading_count && !loading_overflow)return;
    char name[192];path(name,"loading-pages.jsonl");FILE *f=fopen(name,"a");
    if(!f)fatal("loading page profile output");
    for(u32 i=0;i<loading_count;++i){LoadingPage *e=&loading_pages[i];
        fprintf(f,"{\"frame\":%lu,\"kind\":%lu,\"old_token\":%lu,\"token\":%lu,\"bytes\":%lu,\"crc\":%lu,\"total_ms\":%.3f,\"crc_ms\":%.3f,\"result\":%d}\n",(unsigned long)e->frame,(unsigned long)e->kind,(unsigned long)e->old_token,(unsigned long)e->token,(unsigned long)e->bytes,(unsigned long)e->crc,(double)e->ticks*1000/SYSCLOCK_ARM11,(double)e->crc_ticks*1000/SYSCLOCK_ARM11,e->result);
    }
    if(fclose(f))fatal("loading page profile close");
    if(loading_overflow)fatal("loading page profile overflow");
    loading_count=0;
}
