/* Previous-callback request order, one 512-byte metadata array, no pixels.
 * Overwrite only the consumed prefix: the untouched suffix remains the
 * prediction. A changed prefix/overflow disables prediction for this callback.
 * A wrong future estimate changes only victim preference; all integrity,
 * protected-texture, budget and blocking retirement checks remain outside. */
static uint32_t hw07_order[128],hw07_frame,hw07_count,hw07_length,hw07_index;
static int hw07_predict;
static __attribute__((noinline)) void hw07_cache_begin(uint32_t object,uint32_t frame){
    if(frame!=hw07_frame){
        hw07_length=hw07_count<=128?hw07_count:0;
        hw07_count=0;hw07_frame=frame;hw07_predict=hw07_length!=0;
    }
    hw07_index=hw07_count;
    if(hw07_count>=hw07_length || hw07_count>=128 || hw07_order[hw07_count]!=object)hw07_predict=0;
    if(hw07_count<128)hw07_order[hw07_count]=object;
    if(hw07_count<129)++hw07_count;
}
static __attribute__((noinline)) unsigned hw07_predict_rank(uint32_t object){
    if(!hw07_predict)return 0;
    for(unsigned i=hw07_index+1;i<hw07_length;++i)if(hw07_order[i]==object)return i;
    return UINT32_MAX;
}
static int hw07_prefer_victim(uint32_t candidate,uint32_t stamp,uint32_t current,uint32_t oldstamp){
    unsigned a=hw07_predict_rank(candidate),b=hw07_predict_rank(current);
    return a>b || (a==b && stamp<oldstamp);
}
