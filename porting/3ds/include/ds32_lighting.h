#ifndef DS32_LIGHTING_H
#define DS32_LIGHTING_H
#include "ds_elf.h"
#define DS32_BINDINGS 18
struct DS13Context;
typedef struct {float ambient[4],diffuse[4],specular[4],position[4],direction[3],exponent,cutoff,attenuation[3];} DS32Light;
typedef struct {
    DS32Light light[8];
    float ambient[4],diffuse[4],specular[4],emission[4],shininess,scene[4],normal[3];
    float normal_matrix[9],rescale;
    uint32_t two_side,setters,vertices;
} DS32Lighting;
int ds32_attach(struct DS13Context *);
void ds32_close(struct DS13Context *);
void ds32_track(struct DS13Context *,const float color[4]);
int ds32_real(struct DS13Context *,uint32_t,float out[16],int *normalized);
int ds32_integer(struct DS13Context *,uint32_t,int32_t *out);
int ds32_prepare(struct DS13Context *);
int ds32_vertex(struct DS13Context *,const float eye[4],const float normal[3],const float primary[4],float front[4],float back[4]);
uint32_t ds32_bindings(DSBinding *,uint32_t);
#endif
