#include "ds23_touch.h"
#include <string.h>
#define MAGIC 0x44533233u
static int valid(DS23Touch *t){return t && t->magic==MAGIC && t->bridge && t->bridge->magic==0x44533130u;}
static void emit(DS23Touch *t,uint32_t event){
    DS10Context *c=t->bridge;
    float x=(float)t->x*(float)c->platform.width/(float)t->source_width;
    float y=(float)t->y*(float)c->platform.height/(float)t->source_height;
    t->emit(&c->base.env,NULL,(int32_t)event,DS23_SCREEN,0,x,y);++t->events;
}
int ds23_touch_init(DS23Touch *t,DS10Context *c,uint32_t w,uint32_t h,DS23Pointer fn){
    if(!t || t->magic || !c || c->magic!=0x44533130u || !fn || !w || !h || w>4096 || h>4096 ||
       !c->platform.width || !c->platform.height || c->platform.width>4096 || c->platform.height>4096 ||
       (c->platform.capabilities&DS11_CAP_TOUCHSCREEN))return -1;
    *t=(DS23Touch){MAGIC,w,h,0,0,0,0,c,fn};c->platform.capabilities|=DS11_CAP_TOUCHSCREEN;return 0;
}
int ds23_touch_sample(DS23Touch *t,uint32_t pressed,uint32_t x,uint32_t y){
    if(!valid(t) || pressed>1 || (pressed && (x>=t->source_width || y>=t->source_height)))return -1;
    if(!pressed){if(!t->active)return 0;emit(t,DS23_UP);t->active=0;return 1;}
    if(t->active && x==t->x && y==t->y)return 0;
    t->x=x;t->y=y;emit(t,t->active?DS23_MOVE:DS23_DOWN);t->active=1;return 1;
}
int ds23_touch_close(DS23Touch *t){
    if(!valid(t))return -1;
    if(t->active)emit(t,DS23_CANCEL);
    t->bridge->platform.capabilities&=~DS11_CAP_TOUCHSCREEN;memset(t,0,sizeof(*t));return 0;
}
