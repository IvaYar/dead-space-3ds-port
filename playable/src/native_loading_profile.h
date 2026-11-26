static void loading_crc_observe(u32 crc,u64 ticks){(void)crc;(void)ticks;}
static const DS15Backing *loading_backing(void){return ds27_sd_backing();}
static void loading_flush(void){}
