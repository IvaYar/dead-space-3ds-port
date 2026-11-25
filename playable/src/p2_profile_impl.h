/* Main-thread only, bounded metadata. Timings are nested, not additive. */
static u64 p2_ticks[8];
static u32 p2_counts[8],p2_seen;
u64 p2_clock(void){return svcGetSystemTick();}
void p2_add(unsigned k,u64 start){if(k<8)p2_ticks[k]+=svcGetSystemTick()-start;}
void p2_count(unsigned k){if(k<8)++p2_counts[k];}
int p2_sample(void){++p2_seen;return P2_DEEP && !(p2_seen&255u);}
static void p2_profile_reset(void){memset(p2_ticks,0,sizeof(p2_ticks));memset(p2_counts,0,sizeof(p2_counts));p2_seen=0;}
static void p2_profile_flush(u64 callback){
    if(!scene_started)return;
    u64 draw=menu_ops[0].ticks+menu_ops[1].ticks,other=0;
    for(unsigned i=2;i<7;++i)other+=menu_ops[i].ticks;
    if(current_frame%8 && !hw_policy.ready_seen)return;
    report("P2CPU cb=%lu callback=%llu draw=%llu other_gl=%llu residual=%llu validate=%llu emit=%llu vertex_sample=%llu attr_sample=%llu matrix_sample=%llu light_sample=%llu samples=%lu vertex_misses=%lu vertex_hits=%lu triangles=%lu reject=%lu accept=%lu clipped=%lu gpu_begin=%llu gpu_end=%llu resident=%llu crc=%llu\n",
      (unsigned long)current_frame,(unsigned long long)callback,(unsigned long long)draw,(unsigned long long)other,
      (unsigned long long)(callback>=draw+other?callback-draw-other:0),
      (unsigned long long)p2_ticks[0],(unsigned long long)p2_ticks[1],(unsigned long long)p2_ticks[2],
      (unsigned long long)p2_ticks[3],(unsigned long long)p2_ticks[4],(unsigned long long)p2_ticks[5],
      (unsigned long)p2_counts[2],(unsigned long)p2_counts[0],(unsigned long)p2_counts[1],
      (unsigned long)p2_counts[3],(unsigned long)p2_counts[4],(unsigned long)p2_counts[5],(unsigned long)p2_counts[6],
      (unsigned long long)menu_ops[7].ticks,(unsigned long long)menu_ops[8].ticks,
      (unsigned long long)menu_ops[9].ticks,(unsigned long long)menu_ops[10].ticks);
}
