#ifndef DS_P2_PROFILE_H
#define DS_P2_PROFILE_H
#include <stdint.h>
#include "optimization_config.h"
#if DS_RENDER_PROFILE
uint64_t p2_clock(void);
void p2_add(unsigned,uint64_t);
void p2_count(unsigned);
int p2_sample(void);
#else
static inline uint64_t p2_clock(void){return 0;}
static inline void p2_add(unsigned k,uint64_t t){(void)k;(void)t;}
static inline void p2_count(unsigned k){(void)k;}
static inline int p2_sample(void){return 0;}
#endif
#endif
