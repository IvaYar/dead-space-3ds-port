/* Original ARM softfp probe using explicit Bionic data structures. No EA code. */
#include "ds6.h"
#define DECL(ret,name,args) extern ret name args
DECL(int,snprintf,(char *,size_t,const char *,...)); DECL(int,sprintf,(char *,const char *,...));
DECL(int,sscanf,(const char *,const char *,...)); DECL(int,vsnprintf,(char *,size_t,const char *,va_list));
DECL(int,vsprintf,(char *,const char *,va_list)); DECL(int,vsscanf,(const char *,const char *,va_list));
DECL(int,atoi,(const char *)); DECL(long,strtol,(const char *,char **,int));
DECL(unsigned long,strtoul,(const char *,char **,int)); DECL(double,strtod,(const char *,char **));
DECL(void,qsort,(void *,size_t,size_t,int (*)(const void *,const void *))); DECL(size_t,wcslen,(const uint32_t *));
DECL(char *,getenv,(const char *)); DECL(int,setenv,(const char *,const char *,int)); DECL(long,lrand48,(void));
DECL(int,__android_log_write,(int,const char *,const char *)); DECL(int,__android_log_print,(int,const char *,const char *,...));
DECL(int,__android_log_vprint,(int,const char *,const char *,va_list));
DECL(int,__atomic_swap,(int,int *)); DECL(int,__atomic_inc,(int *)); DECL(int,__atomic_dec,(int *));
DECL(int,__atomic_cmpxchg,(int,int,int *)); DECL(int *,__errno,(void));
DECL(int,strcmp,(const char *,const char *));
DECL(DS6File *,fopen,(const char *,const char *)); DECL(int,fclose,(DS6File *));
DECL(size_t,fread,(void *,size_t,size_t,DS6File *)); DECL(size_t,fwrite,(const void *,size_t,size_t,DS6File *));
DECL(int,fseek,(DS6File *,int,int)); DECL(long,ftell,(DS6File *)); DECL(int,fflush,(DS6File *));
DECL(int,fgetc,(DS6File *)); DECL(char *,fgets,(char *,int,DS6File *)); DECL(int,ungetc,(int,DS6File *));
DECL(int,fputs,(const char *,DS6File *)); DECL(int,fprintf,(DS6File *,const char *,...)); DECL(int,fwide,(DS6File *,int));
DECL(int,stat,(const char *,void *)); DECL(int,fstat,(int,void *));
DECL(int,remove,(const char *)); DECL(int,rename,(const char *,const char *));
DECL(int,clock_gettime,(int,DS6Time *)); DECL(int,gettimeofday,(DS6Time *,void *));
DECL(long,time,(long *)); DECL(DS6TM *,gmtime,(const long *));
DECL(DS6TM *,localtime,(const long *)); DECL(long,mktime,(DS6TM *));
DECL(int,nanosleep,(const DS6Time *,DS6Time *)); DECL(int,usleep,(unsigned));
DECL(int,sched_yield,(void)); DECL(long,sysconf,(int));
extern DS6File __sF[];
extern const char *_ctype_;
extern const short *_tolower_tab_,*_toupper_tab_;
extern unsigned __page_size;
extern char *tzname[];
static volatile int constructor_marker=42;
__attribute__((constructor)) static void must_not_run(void) { constructor_marker=99; }
static int compare(const void *a,const void *b) { return *(const int *)a-*(const int *)b; }
static int print_args(char *out,int bounded,const char *fmt,...) {
    va_list args; va_start(args,fmt); int n=bounded?vsnprintf(out,80,fmt,args):vsprintf(out,fmt,args); va_end(args); return n;
}
static int scan_args(const char *in,const char *fmt,...) {
    va_list args; va_start(args,fmt); int n=vsscanf(in,fmt,args); va_end(args); return n;
}
static void log_args(const char *fmt,...) {
    va_list args; va_start(args,fmt); __android_log_vprint(4,"stage6",fmt,args); va_end(args);
}
int probe_basics(uint32_t *out) {
    int check=0; char text[96],*end; double number; unsigned hex; int integer;
#define CHECK(condition) do { ++check; if(!(condition)) { out[0]=check; return check; } } while(0)
    CHECK(snprintf(text,sizeof(text),"%d %.2f %llx",-17,1.25,UINT64_C(0x1234567887654321))>0);
    CHECK(strcmp(text,"-17 1.25 1234567887654321")==0);
    CHECK(snprintf(text,5,"abcdef")==6 && strcmp(text,"abcd")==0);
    CHECK(sprintf(text,"%s:%u","ds",42)==5 && strcmp(text,"ds:42")==0);
    CHECK(print_args(text,1,"%d %.2f",7,-2.5)==7 && strcmp(text,"7 -2.50")==0);
    CHECK(print_args(text,0,"%llx",UINT64_C(0x1122334455667788))==16 && strcmp(text,"1122334455667788")==0);
    CHECK(sscanf("17 1.25 ff","%d %lf %x",&integer,&number,&hex)==3 && integer==17 && number==1.25 && hex==255);
    CHECK(scan_args("2.5 19","%lf %d",&number,&integer)==2 && number==2.5 && integer==19);
    CHECK(atoi(" -17")==-17);
    CHECK(strtol("0x2ax",&end,0)==42 && *end=='x');
    CHECK(strtoul("4294967295",&end,10)==0xffffffffu && !*end);
    CHECK(strtod("1.25x",&end)==1.25 && *end=='x');
    *__errno()=0; long limit=strtol("2147483648",&end,10);
    CHECK(limit==0x7fffffff && *__errno()==34);
    uint32_t wide[]={0x41,0x410,0x1f600,0}; CHECK(wcslen(wide)==3);
    int array[]={3,-2,9,0}; qsort(array,4,sizeof(int),compare);
    CHECK(array[0]==-2 && array[1]==0 && array[2]==3 && array[3]==9);
    CHECK((_ctype_[1+'A']&1) && (_ctype_[1+'9']&4) && (_ctype_[1+' ']&128));
    CHECK((_ctype_[1+0x80]&32) && (_ctype_[1+0xa0]&16));
    CHECK(_tolower_tab_[1+'A']=='a' && _toupper_tab_[1+'z']=='Z' && _tolower_tab_[0]==-1);
    CHECK(__page_size==4096);
    CHECK(getenv("STAGE6_ENV")==0 && !setenv("STAGE6_ENV","first",1));
    CHECK(!setenv("STAGE6_ENV","second",0) && !strcmp(getenv("STAGE6_ENV"),"first"));
    CHECK(!setenv("STAGE6_ENV","second",1) && !strcmp(getenv("STAGE6_ENV"),"second"));
    CHECK(lrand48()==851401618);
    int atom=4; CHECK(__atomic_inc(&atom)==4 && atom==5);
    CHECK(__atomic_dec(&atom)==5 && atom==4); CHECK(__atomic_swap(9,&atom)==4 && atom==9);
    CHECK(__atomic_cmpxchg(9,11,&atom)==0 && atom==11); CHECK(__atomic_cmpxchg(9,12,&atom)==1 && atom==11);
    CHECK(__android_log_write(4,"stage6","stage6 log write")>=0);
    CHECK(__android_log_print(4,"stage6","stage6 log %.2f",1.25)>=0); log_args("stage6 vlog %d",42);
    CHECK(constructor_marker==42);
    out[0]=0; out[1]=(uint32_t)check; out[2]=(uint32_t)constructor_marker; return 0;
#undef CHECK
}
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
int probe_files(uint32_t *out) {
    const char *asset="appbundle:/published/data/achievements.sb";
    const char *scratch="appdata:/stage6-roundtrip.txt",*renamed="appdata:/stage6-renamed.txt";
    DS6File *file=NULL; uint8_t metadata[104],buffer[127]; char line[64];
    int check=0,failed=0; uint32_t crc=0xffffffffu,total=0;
#define CHECK(condition) do { ++check; if(!(condition)) { failed=check; goto done; } } while(0)
    CHECK(sizeof(DS6File)==84 && __sF[1].fd==1 && __sF[2].fd==2);
    CHECK(fprintf(&__sF[2],"stage6 stderr %.2f\n",2.5)>0);
    CHECK(!stat(asset,metadata) && get32(metadata+48)==3568 && get32(metadata+52)==0 && (get32(metadata+16)&0170000)==0100000);
    file=fopen(asset,"rb"); CHECK(file!=0);
    CHECK(file->fd>=1024 && !fstat(file->fd,metadata) && get32(metadata+48)==3568);
    for(;;) {
        size_t n=fread(buffer,1,sizeof(buffer),file); if(!n) break;
        CHECK(n<=sizeof(buffer) && total+n<=3568);
        for(size_t i=0;i<n;++i) { crc^=buffer[i]; for(int bit=0;bit<8;++bit) crc=(crc>>1)^(0xedb88320u&(0u-(crc&1))); }
        total+=(uint32_t)n;
    }
    CHECK(total==3568 && ~crc==0x4a8d9499u && (file->flags&32));
    CHECK(fgetc(file)==-1 && ungetc('Q',file)=='Q' && !(file->flags&32) && fgetc(file)=='Q');
    CHECK(!fseek(file,0,2) && ftell(file)==3568 && fwide(file,1)<0);
    CHECK(!fclose(file)); file=NULL;
    CHECK(fopen(asset,"wb")==0 && *__errno()==30);
    file=fopen(scratch,"w+b"); CHECK(file!=0);
    CHECK(fwide(file,0)==0 && fputs("stage6\n",file)>=0 && fwide(file,0)<0);
    CHECK(fprintf(file,"%d %.2f\n",42,1.25)>0 && fwrite("END",1,3,file)==3 && !fflush(file));
    CHECK(!fstat(file->fd,metadata) && get32(metadata+48)==18);
    CHECK(!fseek(file,0,0) && fgets(line,sizeof(line),file) && !strcmp(line,"stage6\n"));
    CHECK(fgets(line,sizeof(line),file) && !strcmp(line,"42 1.25\n"));
    CHECK(fread(buffer,2,2,file)==1 && buffer[0]=='E' && buffer[1]=='N' && buffer[2]=='D' && (file->flags&32));
    CHECK(!fclose(file)); file=NULL;
    CHECK(!rename(scratch,renamed) && !stat(renamed,metadata) && get32(metadata+48)==18);
    CHECK(!remove(renamed) && stat(renamed,metadata)==-1 && *__errno()==2);
done:
    if(file) fclose(file);
    remove(scratch); remove(renamed);
    out[0]=(uint32_t)failed; out[1]=total; out[2]=~crc; out[3]=(uint32_t)check;
    return failed;
#undef CHECK
}
int probe_time(uint32_t *out) {
    int check=0; DS6Time realtime,mono,after,wall,delay={0,1000000}; long stamp=0;
#define CHECK(condition) do { ++check; if(!(condition)) { out[0]=(uint32_t)check; return check; } } while(0)
    CHECK(!clock_gettime(0,&realtime) && realtime.nsec>=0 && realtime.nsec<1000000000);
    CHECK(!gettimeofday(&wall,0) && wall.nsec>=0 && wall.nsec<1000000);
    long now=time(&stamp); CHECK(now==stamp && stamp>=realtime.sec && stamp-realtime.sec<5);
    CHECK(!clock_gettime(1,&mono) && !nanosleep(&delay,0) && !clock_gettime(1,&after));
    CHECK(after.sec>mono.sec || (after.sec==mono.sec && after.nsec>=mono.nsec));
    CHECK(!usleep(1000) && !sched_yield());
    stamp=0; DS6TM *calendar=gmtime(&stamp);
    CHECK(calendar && calendar->field[5]==70 && calendar->field[3]==1 && calendar->offset==0);
    CHECK(mktime(calendar)==0 && localtime(&stamp)->field[5]==70 && !strcmp(tzname[0],"UTC"));
    CHECK(sysconf(0x27)==4096 && sysconf(0x28)==4096 && sysconf(0x0b)==11 && sysconf(0x61)==1);
    CHECK(clock_gettime(99,&wall)==-1 && *__errno()==22);
    delay.nsec=1000000000; CHECK(nanosleep(&delay,0)==-1 && *__errno()==22);
    out[0]=0; out[1]=(uint32_t)check; return 0;
#undef CHECK
}
