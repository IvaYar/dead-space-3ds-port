#include "scene_morton_store.h"
static void scene_morton_profile(void){
    static DSMortonStats old;DSMortonStats now;ds_morton_stats(&now);
    if(!scene_started)return;
    static int limits_reported;
    if(!limits_reported){uint32_t limits[2];ds_morton_limits(limits);report("MORTON_LIMITS block=%lu scratch=%lu metadata_keys=128 gpu_budget=8388608\n",(unsigned long)limits[0],(unsigned long)limits[1]);limits_reported=1;}
    if(now.saves!=old.saves || now.loads!=old.loads || now.failures!=old.failures || current_frame%120==0)
        report("MORTONJSON {\"frame\":%lu,\"saves\":%llu,\"loads\":%llu,\"save_raw_bytes\":%llu,\"load_raw_bytes\":%llu,\"write_bytes\":%llu,\"read_bytes\":%llu,\"failures\":%llu}\n",(unsigned long)current_frame,(unsigned long long)(now.saves-old.saves),(unsigned long long)(now.loads-old.loads),(unsigned long long)(now.save_raw-old.save_raw),(unsigned long long)(now.load_raw-old.load_raw),(unsigned long long)(now.written-old.written),(unsigned long long)(now.read-old.read),(unsigned long long)(now.failures-old.failures));
    if(now.loads!=old.loads || now.saves!=old.saves)
        report("MORTONTIMEJSON {\"frame\":%lu,\"read_ms\":%.3f,\"write_ms\":%.3f,\"crc_ms\":%.3f,\"encode_ms\":%.3f,\"decode_ms\":%.3f}\n",(unsigned long)current_frame,(double)(now.read_ticks-old.read_ticks)*1000/SYSCLOCK_ARM11,(double)(now.write_ticks-old.write_ticks)*1000/SYSCLOCK_ARM11,(double)(now.crc_ticks-old.crc_ticks)*1000/SYSCLOCK_ARM11,(double)(now.encode_ticks-old.encode_ticks)*1000/SYSCLOCK_ARM11,(double)(now.decode_ticks-old.decode_ticks)*1000/SYSCLOCK_ARM11);
    old=now;
}
