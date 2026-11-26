#ifndef LAB_TEXTURE_H
#define LAB_TEXTURE_H
#include <stdint.h>
#ifndef LAB_TEXTURE_CAP
#define LAB_TEXTURE_CAP 1024u
#endif
/* Immutable build profile. Padding domain stays the original power-of-two
 * domain, so normalized UVs and wrap modes retain their meaning. No allocation. */
unsigned lab_texture_shift(unsigned pw,unsigned ph){
    unsigned shift=0;
    while((pw>LAB_TEXTURE_CAP || ph>LAB_TEXTURE_CAP) && pw>8 && ph>8){pw>>=1;ph>>=1;++shift;}
    return shift;
}
/* Source: canonical top-down RGBA8. Destination: PICA tiled bottom-up ABGR8.
 * Center-nearest reduction is explicit; alpha is sampled with RGB. */
void lab_texture_swizzle(uint8_t *data,const uint8_t *rgba,unsigned w,unsigned h,
                         unsigned pw,unsigned ph,unsigned shift,unsigned wraps){
    unsigned half=shift?1u<<(shift-1):0;
    for(unsigned j=0;j<pw*ph;++j){
        unsigned tile=j/64,m=j&63;
        unsigned x=((tile%(pw/8))*8+((m&1)|((m>>1)&2)|((m>>2)&4)))<<shift;
        unsigned y=(ph-1-((tile/(pw/8))*8+(((m>>1)&1)|((m>>2)&2)|((m>>3)&4))))<<shift;
        x+=half;y+=half;
        unsigned sx=(wraps&1)?x%w:x>=w?w-1:x;
        unsigned sy=(wraps&2)?y%h:y>=h?h-1:y;
        const uint8_t black[4]={0,0,0,255};
        const uint8_t *p=rgba?rgba+(sy*w+sx)*4:black;
        data[j*4]=p[3];data[j*4+1]=p[2];data[j*4+2]=p[1];data[j*4+3]=p[0];
    }
}
#endif
