#include "ds10_jni.h"
#include "ds_runtime.h"
#include <stdarg.h>
#include <string.h>
#include <stdio.h>
enum { EAIO,ACTIVITY,MANAGER,STREAM,ASSET_FD,FILE_FD,SYSTEM,POWER,DISPLAY,QUERY,DIRECTORIES,DEVICE_ORIENTATION,ACCELEROMETER,STRING,STRING_ARRAY,CLASS_COUNT };
static const char *classes[]={"com/ea/EAIO/EAIO","com/ea/blast/MainActivity","android/content/res/AssetManager", 
    "java/io/InputStream","android/content/res/AssetFileDescriptor","java/io/FileDescriptor","com/ea/blast/SystemAndroidDelegate","com/ea/blast/PowerManagerAndroid","com/ea/blast/DisplayAndroidDelegate","com/eamobile/Query","com/ea/blast/GetAppDataDirectoryDelegate","com/ea/blast/DeviceOrientationHandlerAndroidDelegate","com/ea/blast/AccelerometerAndroidDelegate","java/lang/String","[Ljava/lang/String;"};
enum { GET_INSTANCE=1,GET_ASSETS,STARTUP,OPEN,READ,SKIP,CLOSE,CONSTRUCT,PROPERTY,KEEP_AWAKE,PACKAGE_VERSION,CONTENT_READY,DIRECTORY,WIDTH,HEIGHT,DPI_X,DPI_Y,ORIENTATION,SET_ORIENTATION,FOCUS,ORIENTATION_ENABLE,UNIMPLEMENTED,ACCEL_ENABLE,ACCEL_DELAY,LIST };
typedef struct { uint32_t owner,is_static,operation; const char *name,*signature; } Method;
static const Method methods[]={
    {EAIO,1,STARTUP,"Startup","(Landroid/content/res/AssetManager;)V"},
    {ACTIVITY,1,GET_INSTANCE,"GetInstance","()Lcom/ea/blast/MainActivity;"},
    {ACTIVITY,0,GET_ASSETS,"getAssets","()Landroid/content/res/AssetManager;"},
    {MANAGER,0,OPEN,"open","(Ljava/lang/String;I)Ljava/io/InputStream;"},
    {MANAGER,0,OPEN,"open","(Ljava/lang/String;)Ljava/io/InputStream;"},
    {MANAGER,0,UNIMPLEMENTED,"openFd","(Ljava/lang/String;)Landroid/content/res/AssetFileDescriptor;"},
    {MANAGER,0,LIST,"list","(Ljava/lang/String;)[Ljava/lang/String;"},
    {STREAM,0,READ,"read","([BII)I"},
    {STREAM,0,SKIP,"skip","(J)J"},
    {STREAM,0,CLOSE,"close","()V"},
    {ASSET_FD,0,UNIMPLEMENTED,"getLength","()J"},
    {ASSET_FD,0,UNIMPLEMENTED,"close","()V"},
    {ASSET_FD,0,UNIMPLEMENTED,"getFileDescriptor","()Ljava/io/FileDescriptor;"},
    {ASSET_FD,0,UNIMPLEMENTED,"getStartOffset","()J"},
    {FILE_FD,0,UNIMPLEMENTED,"getInt$","()I"},
    {SYSTEM,0,CONSTRUCT,"<init>","()V"},
    {POWER,0,CONSTRUCT,"<init>","()V"},
    {POWER,0,KEEP_AWAKE,"ApplyKeepAwake","(Z)V"},
    {DISPLAY,0,CONSTRUCT,"<init>","()V"},
    {QUERY,1,PACKAGE_VERSION,"getVersion","()Ljava/lang/String;"},
    {QUERY,1,CONTENT_READY,"isContentReady","()Z"},
    {DIRECTORIES,0,CONSTRUCT,"<init>","()V"},
    {DIRECTORIES,0,DIRECTORY,"GetAppDataDirectory","()Ljava/lang/String;"},
    {DIRECTORIES,0,DIRECTORY,"GetExternalStorageDirectory","()Ljava/lang/String;"},
    {DISPLAY,0,WIDTH,"GetDefaultWidth","()I"},
    {DISPLAY,0,HEIGHT,"GetDefaultHeight","()I"},
    {DISPLAY,0,DPI_X,"GetDpiX","()F"},
    {DISPLAY,0,DPI_Y,"GetDpiY","()F"},
    {DISPLAY,0,ORIENTATION,"GetStdOrientation","()I"},
    {DISPLAY,0,SET_ORIENTATION,"SetStdOrientation","(I)V"},
    {DISPLAY,0,FOCUS,"OnLifeCycleFocusGained","()V"},
    {DEVICE_ORIENTATION,0,CONSTRUCT,"<init>","()V"},
    {DEVICE_ORIENTATION,0,ORIENTATION_ENABLE,"SetEnabled","(Z)V"},
    {DEVICE_ORIENTATION,0,FOCUS,"OnLifeCycleFocusGained","()V"},
    {ACCELEROMETER,0,CONSTRUCT,"<init>","()V"},
    {ACCELEROMETER,0,ACCEL_ENABLE,"SetEnabled","(Z)V"},
    {ACCELEROMETER,0,ACCEL_DELAY,"SetUpdateFrequency","(I)V"},
#define SYSTEM_PROPERTY(name) {SYSTEM,0,PROPERTY,#name,"()Ljava/lang/String;"},
    DS11_PROPERTIES(SYSTEM_PROPERTY)
#undef SYSTEM_PROPERTY
};
static uint32_t next_token;
static DS10Context *owner(DSJniHandle *env) { return (DS10Context *)env->owner; }
static void notify(DS10Context *c,const char *op,const char *cls,const char *name,const char *sig,int missing) {
    if(missing) { c->pending_exception=1; ++c->failures; }
    if(c->observe) c->observe(op,cls?cls:"",name?name:"",sig?sig:"",missing);
}
static DS10Ref *reference(DS10Context *c,void *handle) {
    if(!handle) return NULL;
    for(unsigned i=0;i<128;++i) if(c->refs[i].token==(uint32_t)handle) return &c->refs[i];
    return NULL;
}
static void *new_ref(DS10Context *c,uint32_t kind,uint32_t identity,int global);
static void release_payload(DS10Context *,uint32_t,uint32_t);
static DS19String *extra_string(DS10Context *c,uint32_t identity){for(DS19String *p=c->extra_strings;p;p=p->next)if((uint32_t)p==identity)return p;return NULL;}
static DSJniString *ref_string(DS10Context *c,const DS10Ref *r){
    if(r && r->kind==4 && r->identity<DS_JNI_STRING_COUNT && c->base.strings[r->identity].used)return &c->base.strings[r->identity];
    DS19String *p=r && r->kind==6?extra_string(c,r->identity):NULL;return p?&p->string:NULL;
}
static DS18Text *text_for(DS10Context *c,DSJniString *s){for(unsigned i=0;i<DS_JNI_STRING_COUNT;++i)if(s==&c->base.strings[i])return &c->text[i];return &((DS19String *)s)->text;}
static void retain_element(DS10Context *c,DS19Element e){if(e.kind==4)++c->string_holds[e.identity];else if(e.kind==6)++extra_string(c,e.identity)->holds;}
static void drop_element(DS10Context *c,DS19Element e){
    if(e.kind==4)--c->string_holds[e.identity];else if(e.kind==6)--extra_string(c,e.identity)->holds;
    if(e.kind)release_payload(c,e.kind,e.identity);
}
static void free_objects(DS10Context *c,unsigned index){
    DS19Array a=c->objects[index];memset(&c->objects[index],0,sizeof(a));
    for(uint32_t i=0;i<a.length;++i)drop_element(c,a.items[i]);
    ds_rt_free(a.items);
}
static void string_error(DS10Context *c,const char *op){++c->string_stats[5];notify(c,op,NULL,NULL,NULL,2);}
static void free_text(DS10Context *c,unsigned i){
    if(c->text[i].units)ds_rt_free(c->text[i].units);
    memset(&c->text[i],0,sizeof(c->text[i]));memset(&c->base.strings[i],0,sizeof(c->base.strings[i]));c->string_holds[i]=0;
}
static void *make_text(DSJniHandle *env,const uint16_t *units,uint32_t length,int from_utf){
    DS10Context *c=owner(env);char encoded[DS_JNI_STRING_BYTES];int bytes=ds18_encode(units,length,encoded,sizeof(encoded)-1);
    if(bytes<0){string_error(c,"NewString encoded size");return NULL;}
    for(unsigned i=0;i<DS_JNI_STRING_COUNT;++i)if(!c->base.strings[i].used){
        uint16_t *copy=ds_rt_calloc(length+1,2);if(!copy){string_error(c,"NewString allocation");return NULL;}
        if(length)memcpy(copy,units,length*2);
        DSJniString *s=&c->base.strings[i];memcpy(s->bytes,encoded,(uint32_t)bytes);s->bytes[bytes]=0;s->length=(uint32_t)bytes;s->pins=0;s->used=1;
        c->text[i]=(DS18Text){copy,length,0,0,0};void *ref=new_ref(c,4,i,0);
        if(!ref){++c->string_stats[5];free_text(c,i);return NULL;}
        ++c->base.new_strings;++c->string_stats[from_utf?1:0];return ref;
    }
    string_error(c,"NewString pool exhausted");return NULL;
}
static void *DS_JNI_SOFT new_wide(DSJniHandle *env,const uint16_t *units,int32_t length){
    DS10Context *c=owner(env);
    if(length<0 || length>DS18_MAX_UNITS || (length && (!units || ((uintptr_t)units&1))) || (uint64_t)(uintptr_t)units+(uint64_t)(uint32_t)length*2>UINT32_MAX+1ull){string_error(c,"NewString input range");return NULL;}
    return make_text(env,units,(uint32_t)length,0);
}
static void *DS_JNI_SOFT new_utf(DSJniHandle *env,const char *bytes) {
    DS10Context *c=owner(env);if(!bytes){string_error(c,"NewStringUTF null input");return NULL;}
    uint32_t n=0;while(n<DS_JNI_STRING_BYTES && (uint64_t)(uintptr_t)bytes+n<=UINT32_MAX && bytes[n])++n;
    if(n==DS_JNI_STRING_BYTES || (uint64_t)(uintptr_t)bytes+n>UINT32_MAX){string_error(c,"NewStringUTF input range");return NULL;}
    uint16_t units[DS18_MAX_UNITS];int length=ds18_decode(bytes,n,units,DS18_MAX_UNITS);
    if(length<0){string_error(c,"NewStringUTF malformed encoding");return NULL;}
    return make_text(env,units,(uint32_t)length,1);
}
static void release_payload(DS10Context *c,uint32_t kind,uint32_t identity) {
    for(unsigned i=0;i<128;++i) if(c->refs[i].token && c->refs[i].kind==kind && c->refs[i].identity==identity)return;
    if(kind==3 && identity<8 && c->arrays[identity].used) {
        ds_rt_free(c->arrays[identity].bytes);memset(&c->arrays[identity],0,sizeof(c->arrays[identity]));
    }
    if(kind==4 && identity<DS_JNI_STRING_COUNT && !c->string_holds[identity])free_text(c,identity);
    if(kind==5 && identity<DS19_ARRAYS)free_objects(c,identity);
    if(kind==6){DS19String **link=&c->extra_strings;while(*link && (uint32_t)*link!=identity)link=&(*link)->next;
        if(*link && !(*link)->holds){DS19String *p=*link;*link=p->next;ds_rt_free(p->text.units);ds_rt_free(p);--c->extra_count;}}
    if(kind==2 && (identity&255)==STREAM)for(unsigned i=0;i<8;++i)if(c->streams[i].token==(identity>>8)) {
        if(c->streams[i].fd>=0)ds_io_close(c->streams[i].fd);
        c->streams[i].token=0;c->streams[i].fd=-1;
    }
}
static void *new_ref(DS10Context *c,uint32_t kind,uint32_t identity,int global) {
    for(unsigned i=0;i<128;++i) if(!c->refs[i].token) {
        /* Tokens are never reused, including after context reinitialization. */
        if(next_token==0x0fffffffu) break;
        DS10Ref *r=&c->refs[i]; r->token=0xa0000000u|++next_token;r->kind=kind;r->identity=identity;r->global=global;
        ++c->live_refs;if(c->live_refs>c->peak_refs)c->peak_refs=c->live_refs;
        return (void *)r->token;
    }
    notify(c,"reference capacity",NULL,NULL,NULL,2);return NULL;
}
static void *DS_JNI_SOFT find_class(DSJniHandle *env,const char *name) {
    DS10Context *c=owner(env);++c->lookups;
    for(unsigned i=0;name && i<CLASS_COUNT;++i) if(!strcmp(name,classes[i])) {
        notify(c,"FindClass",name,NULL,NULL,0);return new_ref(c,1,i,0);
    }
    notify(c,"FindClass",name,NULL,NULL,1);return NULL;
}
static void *DS_JNI_SOFT new_global(DSJniHandle *env,void *handle) {
    DS10Context *c=owner(env);if(!handle)return NULL;
    DS10Ref *r=reference(c,handle);
    if(!r){notify(c,"NewGlobalRef",NULL,NULL,NULL,1);return NULL;}
    return new_ref(c,r->kind,r->identity,1);
}
static void delete_ref(DSJniHandle *env,void *handle,int global) {
    if(!handle)return;
    DS10Context *c=owner(env);DS10Ref *r=reference(c,handle);
    if(!r || r->global!=(uint32_t)global){notify(c,global?"DeleteGlobalRef":"DeleteLocalRef",NULL,NULL,NULL,1);return;}
    if(r->kind==3)for(unsigned i=0;i<16;++i)if(c->pins[i].copy && c->pins[i].array==r->identity) {
        notify(c,"DeleteRef pinned array",NULL,NULL,NULL,2);return;
    }
    DSJniString *string=ref_string(c,r);if(string && string->pins){notify(c,"DeleteRef pinned string",NULL,NULL,NULL,2);return;}
    uint32_t kind=r->kind,identity=r->identity;r->token=0;--c->live_refs;release_payload(c,kind,identity);
}
static void DS_JNI_SOFT delete_global(DSJniHandle *env,void *handle){delete_ref(env,handle,1);}
static void DS_JNI_SOFT delete_local(DSJniHandle *env,void *handle){
    DS10Context *c=owner(env);
    if(!handle)return;
    if(reference(c,handle)){delete_ref(env,handle,0);return;}
    /* Preserve the bootstrap string API; arbitrary pointers remain invalid. */
    for(unsigned i=0;i<DS_JNI_STRING_COUNT;++i) if(handle==&c->base.strings[i] && c->base.strings[i].used) {
        if(c->base.strings[i].pins){notify(c,"DeleteLocalRef pinned string",NULL,NULL,NULL,1);return;}
        if(c->text[i].units){notify(c,"DeleteLocalRef raw string token",NULL,NULL,NULL,2);return;}
        c->base.strings[i].used=0;return;
    }
    notify(c,"DeleteLocalRef",NULL,NULL,NULL,1);
}
static int DS_JNI_SOFT ensure_capacity(DSJniHandle *env,int32_t capacity) {
    DS10Context *c=owner(env);
    if(capacity<0 || (uint32_t)capacity>128-c->live_refs){notify(c,"local reference capacity",NULL,NULL,NULL,2);return -1;}
    return 0;
}
static int DS_JNI_SOFT push_frame(DSJniHandle *env,int32_t capacity) {
    DS10Context *c=owner(env);
    if(c->frame_depth==16){notify(c,"local frame depth",NULL,NULL,NULL,2);return -1;}
    if(ensure_capacity(env,capacity))return -1;
    c->frames[c->frame_depth++].mark=next_token;
    notify(c,"PushLocalFrame",NULL,NULL,NULL,0);return 0;
}
static void *DS_JNI_SOFT pop_frame(DSJniHandle *env,void *result) {
    DS10Context *c=owner(env);
    if(!c->frame_depth){notify(c,"PopLocalFrame without frame",NULL,NULL,NULL,2);return NULL;}
    uint32_t mark=c->frames[c->frame_depth-1].mark;DS10Ref *escape=reference(c,result);
    if(result && !escape){notify(c,"PopLocalFrame result",NULL,NULL,NULL,2);return NULL;}
    for(unsigned i=0;i<128;++i) {
        DS10Ref *r=&c->refs[i];
        if(!r->token || r->global || (r->token&0x0fffffffu)<=mark || r==escape)continue;
        if(r->kind==3)for(unsigned j=0;j<16;++j)if(c->pins[j].copy && c->pins[j].array==r->identity){notify(c,"PopLocalFrame pinned array",NULL,NULL,NULL,2);return NULL;}
        DSJniString *string=ref_string(c,r);if(string && string->pins){notify(c,"PopLocalFrame pinned string",NULL,NULL,NULL,2);return NULL;}
    }
    for(unsigned i=0;i<128;++i) {
        DS10Ref *r=&c->refs[i];
        if(r->token && !r->global && (r->token&0x0fffffffu)>mark && r!=escape)delete_ref(env,(void *)r->token,0);
    }
    --c->frame_depth;notify(c,"PopLocalFrame",NULL,NULL,NULL,0);
    if(escape && (escape->global || (escape->token&0x0fffffffu)<=mark))return new_ref(c,escape->kind,escape->identity,0);
    return result;
}
static uint8_t DS_JNI_SOFT is_same(DSJniHandle *env,void *a,void *b) {
    if(!a || !b)return a==b;
    DS10Context *c=owner(env);DS10Ref *x=reference(c,a),*y=reference(c,b);
    if(!x || !y){notify(c,"IsSameObject",NULL,NULL,NULL,1);return 0;}
    return x->kind==y->kind && x->identity==y->identity;
}
static void *DS_JNI_SOFT object_class(DSJniHandle *env,void *handle) {
    DS10Context *c=owner(env);DS10Ref *r=reference(c,handle);
    if(ref_string(c,r))return new_ref(c,1,STRING,0);
    if(r && r->kind==5)return new_ref(c,1,STRING_ARRAY,0);
    if(!r || r->kind!=2){notify(c,"GetObjectClass",NULL,NULL,NULL,1);return NULL;}
    return new_ref(c,1,r->identity&255,0);
}
static void *lookup(DSJniHandle *env,void *clazz,const char *name,const char *signature,int is_static) {
    DS10Context *c=owner(env);++c->lookups;DS10Ref *r=reference(c,clazz);
    const char *cls=r && r->kind==1 && r->identity<CLASS_COUNT?classes[r->identity]:NULL;
    if(cls && name && signature) for(unsigned i=0;i<sizeof(methods)/sizeof(methods[0]);++i) {
        const Method *m=&methods[i];
        if(m->owner==r->identity && m->is_static==(uint32_t)is_static && !strcmp(m->name,name) && !strcmp(m->signature,signature)) {
            notify(c,is_static?"GetStaticMethodID":"GetMethodID",cls,name,signature,0);return (void *)m;
        }
    }
    notify(c,is_static?"GetStaticMethodID":"GetMethodID",cls,name,signature,1);return NULL;
}
static void *DS_JNI_SOFT get_static_method(DSJniHandle *e,void *cl,const char *n,const char *s){return lookup(e,cl,n,s,1);}
static void *DS_JNI_SOFT get_method(DSJniHandle *e,void *cl,const char *n,const char *s){return lookup(e,cl,n,s,0);}
static const Method *valid_method(void *id) {
    for(unsigned i=0;i<sizeof(methods)/sizeof(methods[0]);++i) if(id==&methods[i])return &methods[i];
    return NULL;
}
static DS10Array *byte_array(DS10Context *c,void *handle) {
    DS10Ref *r=reference(c,handle);
    return r && r->kind==3 && r->identity<8 && c->arrays[r->identity].used?&c->arrays[r->identity]:NULL;
}
static const char *java_string(DS10Context *c,void *handle) {
    DS10Ref *r=reference(c,handle);
    DSJniString *s=ref_string(c,r);if(s)return s->bytes;
    for(unsigned i=0;i<DS_JNI_STRING_COUNT;++i) if(handle==&c->base.strings[i] && c->base.strings[i].used)return c->base.strings[i].bytes;
    return NULL;
}
static void *raw_string(DS10Context *c,void *handle){
    DS10Ref *r=reference(c,handle);
    DSJniString *s=ref_string(c,r);if(s)return s;
    notify(c,"invalid string reference",NULL,NULL,NULL,2);return NULL;
}
static int DS_JNI_SOFT utf_length(DSJniHandle *env,void *handle){
    DS10Context *c=owner(env);DSJniString *s=raw_string(c,handle);return s?(int)s->length:0;
}
static const char *DS_JNI_SOFT utf_chars(DSJniHandle *env,void *handle,uint8_t *copy){
    DS10Context *c=owner(env);DSJniString *s=raw_string(c,handle);if(!s)return NULL;
    if(s->pins==UINT32_MAX){string_error(c,"GetStringUTFChars pin overflow");return NULL;}
    ++s->pins;++text_for(c,s)->utf_pins;++c->base.get_chars;++c->string_stats[3];if(copy)*copy=0;return s->bytes;
}
static void DS_JNI_SOFT utf_release(DSJniHandle *env,void *handle,const char *chars){
    DS10Context *c=owner(env);void *s=raw_string(c,handle);if(!s)return;
    DSJniString *string=s;
    DS18Text *t=text_for(c,string);
    if(!t->utf_pins || chars!=string->bytes){string_error(c,"ReleaseStringUTFChars pin");return;}
    --t->utf_pins;--string->pins;++c->base.releases;
}
static int DS_JNI_SOFT wide_length(DSJniHandle *env,void *handle){DS10Context *c=owner(env);DSJniString *s=raw_string(c,handle);return s?(int)text_for(c,s)->length:0;}
static const uint16_t *get_wide(DSJniHandle *env,void *handle,uint8_t *copy,int critical){
    DS10Context *c=owner(env);DSJniString *s=raw_string(c,handle);if(!s)return NULL;DS18Text *t=text_for(c,s);
    if(!t->units || s->pins==UINT32_MAX){string_error(c,"GetStringChars state");return NULL;}
    ++s->pins;if(critical)++t->critical_pins;else ++t->wide_pins;
    ++c->string_stats[2];if(copy)*copy=0;return t->units;
}
static void release_wide(DSJniHandle *env,void *handle,const uint16_t *chars,int critical){
    DS10Context *c=owner(env);DSJniString *s=raw_string(c,handle);if(!s)return;DS18Text *t=text_for(c,s);uint32_t *pins=critical?&t->critical_pins:&t->wide_pins;
    if(!*pins || !chars || chars!=t->units){string_error(c,"ReleaseStringChars pin");return;}--*pins;--s->pins;
}
static const uint16_t *DS_JNI_SOFT wide_chars(DSJniHandle *e,void *s,uint8_t *copy){return get_wide(e,s,copy,0);}
static const uint16_t *DS_JNI_SOFT critical_chars(DSJniHandle *e,void *s,uint8_t *copy){return get_wide(e,s,copy,1);}
static void DS_JNI_SOFT wide_release(DSJniHandle *e,void *s,const uint16_t *p){release_wide(e,s,p,0);}
static void DS_JNI_SOFT critical_release(DSJniHandle *e,void *s,const uint16_t *p){release_wide(e,s,p,1);}
static void string_region(DSJniHandle *env,void *handle,int32_t start,int32_t length,void *out,int utf){
    DS10Context *c=owner(env);DSJniString *s=raw_string(c,handle);if(!s)return;DS18Text *t=text_for(c,s);
    if(start<0 || length<0 || (uint32_t)start>t->length || (uint32_t)length>t->length-(uint32_t)start || (length && (!out || (!utf && ((uintptr_t)out&1))))){string_error(c,"GetStringRegion range");return;}
    char encoded[DS_JNI_STRING_BYTES];uint32_t bytes=(uint32_t)length*2;
    if(utf){int n=ds18_encode(t->units+start,(uint32_t)length,encoded,sizeof(encoded));if(n<0){string_error(c,"GetStringUTFRegion size");return;}bytes=(uint32_t)n;}
    if((uint64_t)(uintptr_t)out+bytes>UINT32_MAX+1ull){string_error(c,"GetStringRegion output range");return;}
    if(bytes)memcpy(out,utf?(const void *)encoded:(const void *)(t->units+start),bytes);
    ++c->string_stats[4];
}
static void DS_JNI_SOFT wide_region(DSJniHandle *e,void *s,int32_t start,int32_t length,uint16_t *out){string_region(e,s,start,length,out,0);}
static void DS_JNI_SOFT utf_region(DSJniHandle *e,void *s,int32_t start,int32_t length,char *out){string_region(e,s,start,length,out,1);}
static DS19Array *object_array(DS10Context *c,void *handle){DS10Ref *r=reference(c,handle);return r && r->kind==5 && r->identity<DS19_ARRAYS && c->objects[r->identity].used?&c->objects[r->identity]:NULL;}
static void *make_objects(DS10Context *c,int32_t length,DS19Element initial){
    if(length<0 || length>DS19_ELEMENTS){notify(c,"NewObjectArray size",NULL,NULL,NULL,2);return NULL;}
    for(unsigned i=0;i<DS19_ARRAYS;++i)if(!c->objects[i].used){
        DS19Element *items=length?ds_rt_calloc((uint32_t)length,sizeof(*items)):NULL;
        if(length && !items){notify(c,"NewObjectArray allocation",NULL,NULL,NULL,2);return NULL;}
        c->objects[i]=(DS19Array){1,(uint32_t)length,items};
        for(int32_t j=0;j<length;++j){items[j]=initial;if(initial.kind)retain_element(c,initial);}
        void *ref=new_ref(c,5,i,0);if(!ref)free_objects(c,i);return ref;
    }
    notify(c,"NewObjectArray capacity",NULL,NULL,NULL,2);return NULL;
}
static void *DS_JNI_SOFT new_objects(DSJniHandle *env,int32_t length,void *clazz,void *initial){
    DS10Context *c=owner(env);DS10Ref *cl=reference(c,clazz),*r=reference(c,initial);
    if(!cl || cl->kind!=1 || cl->identity!=STRING || (initial && !ref_string(c,r))){notify(c,"NewObjectArray String component",NULL,NULL,NULL,2);return NULL;}
    return make_objects(c,length,initial?(DS19Element){r->kind,r->identity}:(DS19Element){0,0});
}
static void *DS_JNI_SOFT object_element(DSJniHandle *env,void *handle,int32_t index){
    DS10Context *c=owner(env);DS19Array *a=object_array(c,handle);
    if(!a || index<0 || (uint32_t)index>=a->length){notify(c,"GetObjectArrayElement range",NULL,NULL,NULL,2);return NULL;}
    ++c->asset_stats[2];DS19Element e=a->items[index];return e.kind?new_ref(c,e.kind,e.identity,0):NULL;
}
static void DS_JNI_SOFT set_object_element(DSJniHandle *env,void *handle,int32_t index,void *value){
    DS10Context *c=owner(env);DS19Array *a=object_array(c,handle);DS10Ref *r=reference(c,value);
    if(!a || index<0 || (uint32_t)index>=a->length || (value && !ref_string(c,r))){notify(c,"SetObjectArrayElement type or range",NULL,NULL,NULL,2);return;}
    DS19Element next=value?(DS19Element){r->kind,r->identity}:(DS19Element){0,0},old=a->items[index];
    if(next.kind)retain_element(c,next);
    a->items[index]=next;drop_element(c,old);++c->asset_stats[3];
}
static DS19String *filename_string(DS10Context *c,const char *name){
    if(c->extra_count==DS19_EXTRA_STRINGS)return NULL;
    uint16_t units[255];int length=ds19_name_units(name,units);char encoded[256];
    int bytes=length<0?-1:ds18_encode(units,(uint32_t)length,encoded,255);if(bytes<0)return NULL;
    DS19String *p=ds_rt_calloc(1,sizeof(*p));if(!p)return NULL;
    p->text.units=ds_rt_calloc((uint32_t)length+1,2);if(!p->text.units){ds_rt_free(p);return NULL;}
    memcpy(p->text.units,units,(uint32_t)length*2);p->text.length=(uint32_t)length;
    memcpy(p->string.bytes,encoded,(uint32_t)bytes);p->string.length=(uint32_t)bytes;p->string.used=1;
    p->next=c->extra_strings;c->extra_strings=p;++c->extra_count;return p;
}
static void *list_assets(DSJniHandle *env,const DS10Value *args){
    DS10Context *c=owner(env);const char *name=args?java_string(c,args[0].l):NULL;char relative[256];
    if(!name || ds19_path(name,relative)){notify(c,"AssetManager.list path",classes[MANAGER],NULL,NULL,2);return NULL;}
    notify(c,"AssetManager.list requested",classes[MANAGER],name,NULL,0);
    if(!c->asset_list){notify(c,"AssetManager.list backend missing",classes[MANAGER],"list",NULL,1);return NULL;}
    ++c->asset_stats[0];DS19Name *names=NULL;uint32_t count=0;
    if(ds19_snapshot(c->asset_list,c->asset_user,relative,&names,&count)){notify(c,"AssetManager.list IOException",classes[MANAGER],name,NULL,2);return NULL;}
    void *ref=make_objects(c,(int32_t)count,(DS19Element){0,0});if(!ref){ds_rt_free(names);return NULL;}
    DS19Array *a=object_array(c,ref);
    for(uint32_t i=0;i<count;++i){DS19String *s=filename_string(c,names[i].name);
        if(!s){delete_ref(env,ref,0);ds_rt_free(names);notify(c,"AssetManager.list string allocation",classes[MANAGER],name,NULL,2);return NULL;}
        ++s->holds;a->items[i]=(DS19Element){6,(uint32_t)s};
    }
    ds_rt_free(names);c->asset_stats[1]+=count;
    char number[24];snprintf(number,sizeof(number),"%lu",(unsigned long)count);notify(c,"AssetManager.list returned",classes[MANAGER],relative,number,0);return ref;
}
static void *DS_JNI_SOFT new_bytes(DSJniHandle *env,int32_t length) {
    DS10Context *c=owner(env);
    if(length<0 || length>1024*1024){notify(c,"NewByteArray size",NULL,NULL,NULL,2);return NULL;}
    for(unsigned i=0;i<8;++i)if(!c->arrays[i].used) {
        uint8_t *bytes=ds_rt_calloc(1,length?(uint32_t)length:1);
        if(!bytes)break;
        c->arrays[i]=(DS10Array){bytes,(uint32_t)length,1};void *ref=new_ref(c,3,i,0);
        if(!ref){ds_rt_free(bytes);memset(&c->arrays[i],0,sizeof(c->arrays[i]));}return ref;
    }
    notify(c,"NewByteArray capacity",NULL,NULL,NULL,2);return NULL;
}
static int32_t DS_JNI_SOFT array_length(DSJniHandle *env,void *handle) {
    DS10Context *c=owner(env);DS10Array *a=byte_array(c,handle);
    DS10Ref *r=reference(c,handle);if(r && r->kind==5 && r->identity<DS19_ARRAYS && c->objects[r->identity].used)return (int32_t)c->objects[r->identity].length;
    if(!a){notify(c,"GetArrayLength",NULL,NULL,NULL,2);return 0;}return (int32_t)a->size;
}
static int region(DS10Context *c,DS10Array *a,int32_t start,int32_t length,const void *buffer) {
    if(!a || start<0 || length<0 || (uint32_t)start>a->size || (uint32_t)length>a->size-(uint32_t)start || (length && !buffer)) {
        notify(c,"byte array region",NULL,NULL,NULL,2);return 0;
    }return 1;
}
static void DS_JNI_SOFT get_region(DSJniHandle *env,void *handle,int32_t start,int32_t length,void *buffer) {
    DS10Context *c=owner(env);DS10Array *a=byte_array(c,handle);
    if(region(c,a,start,length,buffer) && length)memcpy(buffer,a->bytes+start,(uint32_t)length);
}
static void DS_JNI_SOFT set_region(DSJniHandle *env,void *handle,int32_t start,int32_t length,const void *buffer) {
    DS10Context *c=owner(env);DS10Array *a=byte_array(c,handle);
    if(region(c,a,start,length,buffer) && length)memcpy(a->bytes+start,buffer,(uint32_t)length);
}
static void *DS_JNI_SOFT get_elements(DSJniHandle *env,void *handle,uint8_t *is_copy) {
    DS10Context *c=owner(env);DS10Array *a=byte_array(c,handle);
    if(!a){notify(c,"GetByteArrayElements",NULL,NULL,NULL,2);return NULL;}
    for(unsigned i=0;i<16;++i)if(!c->pins[i].copy) {
        void *copy=ds_rt_malloc(a->size?a->size:1);if(!copy)break;
        if(a->size)memcpy(copy,a->bytes,a->size);
        c->pins[i]=(DS10Pin){copy,(uint32_t)(a-c->arrays)};if(is_copy)*is_copy=1;return copy;
    }
    notify(c,"GetByteArrayElements capacity",NULL,NULL,NULL,2);return NULL;
}
static void DS_JNI_SOFT release_elements(DSJniHandle *env,void *handle,void *bytes,int mode) {
    DS10Context *c=owner(env);DS10Array *a=byte_array(c,handle);
    if(a && mode>=0 && mode<=2)for(unsigned i=0;i<16;++i)if(c->pins[i].copy==bytes && bytes && c->pins[i].array==(uint32_t)(a-c->arrays)) {
        if(mode!=2 && a->size)memcpy(a->bytes,bytes,a->size);
        if(mode!=1){ds_rt_free(bytes);c->pins[i].copy=NULL;}return;
    }
    notify(c,"ReleaseByteArrayElements",NULL,NULL,NULL,2);
}
static DS10Stream *stream_for(DS10Context *c,const DS10Ref *r) {
    if(r && r->kind==2 && (r->identity&255)==STREAM)for(unsigned i=0;i<8;++i)
        if(c->streams[i].token==(r->identity>>8))return &c->streams[i];
    return NULL;
}
static void *open_asset(DS10Context *c,const DS10Value *args,int with_mode) {
    const char *name=args?java_string(c,args[0].l):NULL;
    if(!name || (with_mode && (args[1].i<0 || args[1].i>3))){notify(c,"AssetManager.open argument",NULL,NULL,NULL,2);return NULL;}
    char path[DS_IO_PATH_BYTES],relative[256];
    if(ds19_path(name,relative) || !relative[0]){notify(c,"AssetManager.open path",NULL,NULL,NULL,2);return NULL;}
    strcpy(path,"published/");strcat(path,relative);
    int fd=ds_io_open(path,0);
    if(fd<0){notify(c,"AssetManager.open IOException",MANAGER<CLASS_COUNT?classes[MANAGER]:NULL,name,NULL,2);return NULL;}
    for(unsigned i=0;i<8;++i)if(!c->streams[i].token && c->stream_serial<0x00ffffffu) {
        uint32_t token=++c->stream_serial;c->streams[i]=(DS10Stream){token,fd};
        void *ref=new_ref(c,2,(token<<8)|STREAM,0);
        if(!ref){ds_io_close(fd);c->streams[i].token=0;}return ref;
    }
    ds_io_close(fd);notify(c,"InputStream capacity",NULL,NULL,NULL,2);return NULL;
}
static DS10Value invoke(DSJniHandle *env,void *receiver,void *id,int is_static,char result_type,const DS10Value *args) {
    DS10Value result={0};
    DS10Context *c=owner(env);DS10Ref *r=reference(c,receiver);const Method *m=valid_method(id);++c->calls;
    const char *ret=m?strchr(m->signature,')'):NULL;
    /* The pinned SD donor calls Query.isContentReady()Z through JNI slot 115
     * (CallStaticObjectMethodV). Keep this verified legacy quirk opt-in and
     * restricted to that one method; all other return families stay strict. */
    int query_compat=m && m->operation==CONTENT_READY && is_static && result_type=='L' && c->query_object_bool_compat;
    if(!m || !r || r->kind!=(is_static?1u:2u) || (r->identity&255)!=m->owner || m->is_static!=(uint32_t)is_static || !ret ||
       (ret[1]!=result_type && !(result_type=='L' && ret[1]=='[') && !query_compat)) {
        notify(c,"invalid method invocation",NULL,NULL,NULL,2);return result;
    }
    notify(c,"CallMethod",classes[m->owner],m->name,m->signature,0);
    if(query_compat)notify(c,"JNI compatibility",classes[m->owner],m->name,"ObjectMethodV for boolean",0);
    switch(m->operation) {
        case LIST:result.l=list_assets(env,args);return result;
        case ACCEL_ENABLE:
        case ACCEL_DELAY: {
            DS10Ref *current=reference(c,c->acceleration_object);
            if(!args || !c->accelerometer || !current || current->identity!=r->identity)break;
            int status;
            if(m->operation==ACCEL_ENABLE)status=ds12_sensor_enable(c->accelerometer,args[0].i);
            else{
                int restart=c->accelerometer->enabled!=0;
                if(args[0].i<0)status=-1;
                else if(restart && ds12_sensor_enable(c->accelerometer,0))status=-2;
                else{
                    status=ds12_sensor_android_delay(c->accelerometer,args[0].i);
                    if(!status)c->acceleration_delay=args[0].i;
                    if(!status && restart)status=ds12_sensor_enable(c->accelerometer,1);
                }
            }
            if(status){notify(c,"accelerometer service error",classes[m->owner],m->name,m->signature,2);return result;}
            char value[24];snprintf(value,sizeof(value),"%ld",(long)args[0].i);
            notify(c,m->operation==ACCEL_DELAY?"SensorDelay":"SensorEnabled",classes[m->owner],m->name,value,0);
            return result;
        }
        case ORIENTATION_ENABLE:
            if(!args || (args[0].i!=0 && args[0].i!=1))break;
            if(args[0].i && !(c->platform.capabilities&DS11_CAP_ACCELEROMETER)){
                notify(c,"accelerometer backend missing",classes[m->owner],m->name,m->signature,1);return result;
            }
            if(args[0].i && !c->orientation_callback){notify(c,"orientation backend missing",classes[m->owner],m->name,m->signature,1);return result;}
            if(c->orientation_enabled!=(uint32_t)args[0].i)c->orientation_pending=(uint32_t)args[0].i;
            c->orientation_enabled=(uint32_t)args[0].i;return result;
        case DIRECTORY:result.l=new_utf(env,!strcmp(m->name,"GetExternalStorageDirectory")?"/sdcard/Android/data/com.ea.deadspace/files":"appdata:/");return result;
        /* EA's Android display uses a portrait natural coordinate system;
         * rotated-left (2) corresponds to our fixed 400x240 native surface. */
        case WIDTH:result.i=(int32_t)c->platform.height;return result;
        case HEIGHT:result.i=(int32_t)c->platform.width;return result;
        case DPI_X:result.f=c->platform.dpi_x;return result;
        case DPI_Y:result.f=c->platform.dpi_y;return result;
        case ORIENTATION:result.i=(int32_t)c->platform.orientation;return result;
        case SET_ORIENTATION:
            if(!args)break;
            if(args[0].i<0 || args[0].i>2){notify(c,"unimplemented orientation",classes[DISPLAY],m->name,m->signature,1);return result;}
            c->platform.orientation=args[0].i?(uint32_t)args[0].i:2;return result;
        case FOCUS:
            c->platform.focused=1;
            if(m->owner==DEVICE_ORIENTATION && c->orientation_enabled)c->orientation_pending=1;
            return result;
        case PACKAGE_VERSION:result.l=new_utf(env,ds11_package_version());return result;
        case CONTENT_READY:result.i=ds11_native_content_ready()!=0;return result;
        case KEEP_AWAKE:
            if(!args || (args[0].i!=0 && args[0].i!=1) || ds11_native_keep_awake(args[0].i))break;
            c->platform.keep_awake=(uint32_t)args[0].i;return result;
        case PROPERTY: {
            char value[256];
            if(ds11_property(&c->platform,m->name,value,sizeof(value)))break;
            notify(c,"PropertyValue",classes[m->owner],m->name,value,0);
            result.l=new_utf(env,value);return result;
        }
        case GET_INSTANCE:result.l=new_ref(c,2,ACTIVITY,0);return result;
        case GET_ASSETS:result.l=new_ref(c,2,MANAGER,0);return result;
        case STARTUP: {
            DS10Ref *manager=args?reference(c,args[0].l):NULL;
            if(!manager || manager->kind!=2 || manager->identity!=MANAGER || !c->startup)break;
            ++c->startup_calls;c->startup(env,NULL,args[0].l);
            notify(c,"NativeEAIOStartup returned",classes[EAIO],m->name,m->signature,0);return result;
        }
        case OPEN:result.l=open_asset(c,args,strstr(m->signature,";I)")!=NULL);return result;
        case READ: {
            DS10Stream *s=stream_for(c,r);DS10Array *a=args?byte_array(c,args[0].l):NULL;result.i=-1;
            if(!args || !s || s->fd<0)break;
            if(!region(c,a,args[1].i,args[2].i,a?a->bytes:NULL))return result;
            if(!args[2].i){result.i=0;return result;}
            int n=ds_io_read(s->fd,a->bytes+args[1].i,(uint32_t)args[2].i);
            if(n<0)break;
            result.i=n?n:-1;c->read_bytes+=(uint32_t)n;return result;
        }
        case SKIP: {
            DS10Stream *s=stream_for(c,r);if(!args || !s || s->fd<0)break;
            if(args[0].j<=0)return result;
            int32_t old=ds_io_seek(s->fd,0,1);if(old<0)break;
            int32_t end=ds_io_seek(s->fd,0,2);
            if(end<0){ds_io_seek(s->fd,old,0);break;}
            int64_t remain=end>old?(int64_t)end-old:0,skip=args[0].j<remain?args[0].j:remain;
            if(ds_io_seek(s->fd,old+(int32_t)skip,0)<0)break;
            result.j=skip;return result;
        }
        case CLOSE: {
            DS10Stream *s=stream_for(c,r);if(!s)break;
            if(s->fd>=0){int fd=s->fd;s->fd=-1;if(ds_io_close(fd))break;}return result;
        }
        default:break;
    }
    notify(c,m->operation==UNIMPLEMENTED?"unimplemented method":"method exception",classes[m->owner],m->name,m->signature,m->operation==UNIMPLEMENTED?1:2);return result;
}
static void arguments(void *id,va_list args,DS10Value out[3]) {
    memset(out,0,sizeof(DS10Value)*3);const Method *m=valid_method(id);if(!m)return;
    if(m->operation==STARTUP || m->operation==OPEN || m->operation==READ)out[0].l=va_arg(args,void *);
    if(m->operation==LIST)out[0].l=va_arg(args,void *);
    if(m->operation==OPEN && strstr(m->signature,";I)"))out[1].i=va_arg(args,int);
    if(m->operation==READ){out[1].i=va_arg(args,int);out[2].i=va_arg(args,int);}
    if(m->operation==SKIP)out[0].j=va_arg(args,int64_t);
    if(m->operation==KEEP_AWAKE)out[0].i=va_arg(args,int);
    if(m->operation==SET_ORIENTATION)out[0].i=va_arg(args,int);
    if(m->operation==ORIENTATION_ENABLE)out[0].i=va_arg(args,int);
    if(m->operation==ACCEL_ENABLE || m->operation==ACCEL_DELAY)out[0].i=va_arg(args,int);
}
static void *construct(DSJniHandle *env,void *clazz,void *id,const DS10Value *args) {
    (void)args;DS10Context *c=owner(env);DS10Ref *r=reference(c,clazz);const Method *m=valid_method(id);
    if(!r || r->kind!=1 || !m || m->owner!=r->identity || m->operation!=CONSTRUCT || m->is_static || c->object_serial==0x00ffffffu) {
        notify(c,"invalid constructor",NULL,NULL,NULL,2);return NULL;
    }
    notify(c,"NewObject",classes[m->owner],m->name,m->signature,0);
    if(m->owner==ACCELEROMETER && (!c->accelerometer || !c->acceleration_callback || c->acceleration_object)){
        notify(c,"accelerometer constructor unavailable",classes[m->owner],m->name,m->signature,1);return NULL;
    }
    void *object=new_ref(c,2,(++c->object_serial<<8)|m->owner,0);
    if(object && m->owner==ACCELEROMETER){
        c->acceleration_object=new_global(env,object);
        if(!c->acceleration_object){delete_local(env,object);return NULL;}
    }
    return object;
}
static void *DS_JNI_SOFT new_object_v(DSJniHandle *e,void *cl,void *m,va_list a){DS10Value v[3];arguments(m,a,v);return construct(e,cl,m,v);}
static void *DS_JNI_SOFT new_object(DSJniHandle *e,void *cl,void *m,...){va_list a;va_start(a,m);void *v=new_object_v(e,cl,m,a);va_end(a);return v;}
static void *DS_JNI_SOFT new_object_a(DSJniHandle *e,void *cl,void *m,const DS10Value *a){return construct(e,cl,m,a);}
#define FAMILY(prefix,ctype,field,stat,tag) \
static ctype DS_JNI_SOFT prefix##_v(DSJniHandle *e,void *r,void *m,va_list a){DS10Value v[3];arguments(m,a,v);return invoke(e,r,m,stat,tag,v).field;} \
static ctype DS_JNI_SOFT prefix(DSJniHandle *e,void *r,void *m,...){va_list a;va_start(a,m);ctype v=prefix##_v(e,r,m,a);va_end(a);return v;} \
static ctype DS_JNI_SOFT prefix##_a(DSJniHandle *e,void *r,void *m,const DS10Value *a){return invoke(e,r,m,stat,tag,a).field;}
FAMILY(static_object,void *,l,1,'L')
FAMILY(instance_object,void *,l,0,'L')
FAMILY(instance_int,int32_t,i,0,'I')
FAMILY(instance_long,int64_t,j,0,'J')
FAMILY(instance_float,float,f,0,'F')
FAMILY(static_boolean,uint8_t,i,1,'Z')
#undef FAMILY
#define VOID_FAMILY(prefix,stat) \
static void DS_JNI_SOFT prefix##_v(DSJniHandle *e,void *r,void *m,va_list a){DS10Value v[3];arguments(m,a,v);invoke(e,r,m,stat,'V',v);} \
static void DS_JNI_SOFT prefix(DSJniHandle *e,void *r,void *m,...){va_list a;va_start(a,m);prefix##_v(e,r,m,a);va_end(a);} \
static void DS_JNI_SOFT prefix##_a(DSJniHandle *e,void *r,void *m,const DS10Value *a){invoke(e,r,m,stat,'V',a);}
VOID_FAMILY(static_void,1)
VOID_FAMILY(instance_void,0)
#undef VOID_FAMILY
static void *DS_JNI_SOFT exception(DSJniHandle *e){DS10Context *c=owner(e);return c->pending_exception?&c->pending_exception:NULL;}
static uint8_t DS_JNI_SOFT exception_check(DSJniHandle *e){return owner(e)->pending_exception!=0;}
static void DS_JNI_SOFT exception_clear(DSJniHandle *e){owner(e)->pending_exception=0;}
int ds10_init(DS10Context *c,DS10Observe observe,DS10Startup startup) {
    if(c->magic==0x44533130 && (c->live_refs || c->frame_depth || c->platform.keep_awake || c->orientation_enabled || c->accelerometer))return 16;
    memset(c,0,sizeof(*c));ds_jni_init(&c->base);c->observe=observe;c->startup=startup;
    c->magic=0x44533130;
    ds11_platform_default(&c->platform);
    uintptr_t *t=c->base.env_functions;
    t[163]=(uintptr_t)new_wide;t[164]=(uintptr_t)wide_length;t[165]=(uintptr_t)wide_chars;t[166]=(uintptr_t)wide_release;
    t[220]=(uintptr_t)wide_region;t[221]=(uintptr_t)utf_region;t[224]=(uintptr_t)critical_chars;t[225]=(uintptr_t)critical_release;
    t[168]=(uintptr_t)utf_length;t[169]=(uintptr_t)utf_chars;t[170]=(uintptr_t)utf_release;
    t[6]=(uintptr_t)find_class;t[21]=(uintptr_t)new_global;t[22]=(uintptr_t)delete_global;t[23]=(uintptr_t)delete_local;t[24]=(uintptr_t)is_same;
    t[31]=(uintptr_t)object_class;t[33]=(uintptr_t)get_method;t[113]=(uintptr_t)get_static_method;
    t[28]=(uintptr_t)new_object;t[29]=(uintptr_t)new_object_v;t[30]=(uintptr_t)new_object_a;
    t[34]=(uintptr_t)instance_object;t[35]=(uintptr_t)instance_object_v;t[36]=(uintptr_t)instance_object_a;
    t[114]=(uintptr_t)static_object;t[115]=(uintptr_t)static_object_v;t[116]=(uintptr_t)static_object_a;
    t[117]=(uintptr_t)static_boolean;t[118]=(uintptr_t)static_boolean_v;t[119]=(uintptr_t)static_boolean_a;
    t[141]=(uintptr_t)static_void;t[142]=(uintptr_t)static_void_v;t[143]=(uintptr_t)static_void_a;
    t[49]=(uintptr_t)instance_int;t[50]=(uintptr_t)instance_int_v;t[51]=(uintptr_t)instance_int_a;
    t[52]=(uintptr_t)instance_long;t[53]=(uintptr_t)instance_long_v;t[54]=(uintptr_t)instance_long_a;
    t[55]=(uintptr_t)instance_float;t[56]=(uintptr_t)instance_float_v;t[57]=(uintptr_t)instance_float_a;
    t[61]=(uintptr_t)instance_void;t[62]=(uintptr_t)instance_void_v;t[63]=(uintptr_t)instance_void_a;
    t[15]=(uintptr_t)exception;t[17]=(uintptr_t)exception_clear;t[228]=(uintptr_t)exception_check;
    t[19]=(uintptr_t)push_frame;t[20]=(uintptr_t)pop_frame;t[26]=(uintptr_t)ensure_capacity;t[167]=(uintptr_t)new_utf;
    t[171]=(uintptr_t)array_length;t[176]=(uintptr_t)new_bytes;t[184]=(uintptr_t)get_elements;t[192]=(uintptr_t)release_elements;
    t[172]=(uintptr_t)new_objects;t[173]=(uintptr_t)object_element;t[174]=(uintptr_t)set_object_element;
    t[200]=(uintptr_t)get_region;t[208]=(uintptr_t)set_region;return 0;
}
uint32_t ds10_cleanup(DS10Context *c) {
    if(c->accelerometer && ds12_sensor_enable(c->accelerometer,0)){
        notify(c,"accelerometer cleanup failed",classes[ACCELEROMETER],NULL,NULL,2);return UINT32_MAX;
    }
    uint32_t count=c->live_refs;
    if(c->platform.keep_awake)ds11_native_keep_awake(0);
    for(unsigned i=0;i<16;++i)if(c->pins[i].copy){ds_rt_free(c->pins[i].copy);++count;}
    for(unsigned i=0;i<8;++i){
        if(c->objects[i].used){ds_rt_free(c->objects[i].items);++count;}
        if(c->text[i].units){free_text(c,i);++count;}
        if(c->arrays[i].used){ds_rt_free(c->arrays[i].bytes);++count;}
        if(c->streams[i].token){if(c->streams[i].fd>=0)ds_io_close(c->streams[i].fd);++count;}
    }
    while(c->extra_strings){DS19String *p=c->extra_strings;c->extra_strings=p->next;ds_rt_free(p->text.units);ds_rt_free(p);++count;}
    memset(c,0,sizeof(*c));return count;
}
uint32_t ds10_context_size(void){return sizeof(DS10Context);}
void ds10_query_compat(DS10Context *c,int enabled){c->query_object_bool_compat=enabled==1;}
void ds11_orientation_backend(DS10Context *c,DS11Orientation callback,int orientation){c->orientation_callback=callback;c->orientation_value=(uint32_t)orientation;}
void ds11_pump_events(DS10Context *c){
    if(c->orientation_enabled && c->orientation_pending && c->orientation_callback){
        c->orientation_pending=0;c->orientation_callback(&c->base.env,NULL,(int)c->orientation_value);++c->orientation_events;
        notify(c,"OrientationEvent",classes[DEVICE_ORIENTATION],"NativeOnDeviceOrientationChange","fixed display",0);
    }
}
int ds12_jni_sensor(DS10Context *c,DS12Sensor *sensor,DS12Acceleration callback){
    if(!c || c->magic!=0x44533130 || c->accelerometer || !sensor || sensor->enabled || !callback || ds12_sensor_android_delay(sensor,3))return -1;
    c->accelerometer=sensor;c->acceleration_callback=callback;c->acceleration_delay=3;
    c->platform.capabilities|=DS11_CAP_ACCELEROMETER;return 0;
}
int ds12_jni_pump(DS10Context *c,uint64_t now){
    if(!c || !c->accelerometer || !c->accelerometer->enabled)return 0;
    if(!c->acceleration_object || push_frame(&c->base.env,16))return -1;
    DS10Ref *global=reference(c,c->acceleration_object);
    void *receiver=global?new_ref(c,global->kind,global->identity,0):NULL;
    int result=receiver?ds12_sensor_dispatch(c->accelerometer,now,&c->base.env,receiver,c->acceleration_callback):-1;
    pop_frame(&c->base.env,NULL);
    if(result==1){++c->acceleration_events;notify(c,"AccelerationEvent",classes[ACCELEROMETER],"NativeOnAcceleration","(FFF)V",0);}
    else if(result<0)notify(c,"accelerometer read failed",classes[ACCELEROMETER],NULL,NULL,2);
    return result;
}
void ds10_stats(DS10Context *c,uint32_t out[7]) {
    out[0]=c->pending_exception;out[1]=c->lookups;out[2]=c->calls;out[3]=c->failures;
    out[4]=c->live_refs;out[5]=c->peak_refs;out[6]=c->startup_calls;
}
void ds18_jni_stats(DS10Context *c,uint32_t out[6]){memcpy(out,c->string_stats,sizeof(c->string_stats));}
void ds19_assets_backend(DS10Context *c,DS19List list,void *user){c->asset_list=list;c->asset_user=user;}
void ds19_jni_stats(DS10Context *c,uint32_t out[6]){memcpy(out,c->asset_stats,16);out[4]=c->extra_count;out[5]=0;for(unsigned i=0;i<DS19_ARRAYS;++i)out[5]+=c->objects[i].used;}
