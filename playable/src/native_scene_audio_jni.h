/* Emulator research AudioTrack sink. Runs the donor mixer and consumes signed
 * PCM16 at its declared rate. No audible device backend is claimed. Included
 * inside generated DS10 after its reference/array helpers. */
#include "ds6.h"
static unsigned scene_audio_playing;
static uint64_t scene_audio_samples,scene_audio_writes;
/* Audio uses retained globals, no Java TLS allocation. Its worker still
 * calls DetachCurrentThread on exit: the VM entry must never be NULL. */
static int DS_JNI_SOFT scene_vm_detach(DSJniHandle *vm){return vm && vm->owner?0:-1;}
static DS10Array *scene_short_array(DS10Context *c,void *handle){
    DS10Ref *r=reference(c,handle);
    return r && r->kind==3 && r->identity<8 && c->arrays[r->identity].used==2?&c->arrays[r->identity]:NULL;
}
static void *DS_JNI_SOFT scene_new_shorts(DSJniHandle *env,int32_t length){
    if(length<0 || length>512*1024){notify(owner(env),"NewShortArray size",NULL,NULL,NULL,2);return NULL;}
    void *ref=new_bytes(env,length*2);DS10Array *a=byte_array(owner(env),ref);
    if(a)a->used=2;
    return ref;
}
static void DS_JNI_SOFT scene_set_shorts(DSJniHandle *env,void *handle,int32_t start,int32_t length,const void *buffer){
    DS10Context *c=owner(env);DS10Array *a=scene_short_array(c,handle);
    if(!a || a->used!=2 || start<0 || length<0 || (uint32_t)start>a->size/2 || (uint32_t)length>a->size/2-(uint32_t)start || (length && !buffer)){
        notify(c,"SetShortArrayRegion bounds",NULL,NULL,NULL,2);return;
    }
    if(length)memcpy(a->bytes+start*2,buffer,(uint32_t)length*2);
}
void *scene_audio_track(DS10Context *c){return new_ref(c,2,AUDIO_TRACK,0);}
static int scene_audio_write(DS10Context *c,const DS10Value *args){
    DS10Array *a=args?scene_short_array(c,args[0].l):NULL;
    int32_t start=args?args[1].i:-1,n=args?args[2].i:-1;
    if(!a || a->used!=2 || start<0 || n<0 || (uint32_t)start>a->size/2 || (uint32_t)n>a->size/2-(uint32_t)start || n%2){
        notify(c,"AudioTrack.write bounds",NULL,NULL,NULL,2);return -2;
    }
    if(!__atomic_load_n(&scene_audio_playing,__ATOMIC_ACQUIRE))return -3;
    /* write([SII)I counts samples, not bytes or frames. Stereo 22050Hz.
     * The kernel sleep is bounded to one mixer block; stop joins precede
     * Release and DS10 array destruction. */
    scene_audio_samples+=(uint32_t)n;++scene_audio_writes;
    ds6_usleep((uint32_t)((uint64_t)n*1000000/(22050*2)));
    return n;
}
void scene_audio_stats(uint64_t out[2]){out[0]=scene_audio_writes;out[1]=scene_audio_samples;}
