#ifndef DS17_JUMP_H
#define DS17_JUMP_H
#include "ds7.h"
#define DS17_BINDINGS 4
/* Android Gingerbread ARM32: 64 longs, 4-byte minimum alignment.
 * Empty signal-mask profile only: POSIX signal delivery is not provided.
 * Save/restore entry points MUST be assembly, never C call/return wrappers. */
typedef struct {uint32_t word[64];} DS17Jump;
typedef struct {uint32_t saves,restores,refusals;} DS17Stats;
_Static_assert(sizeof(DS17Jump)==256,"Android ARM jmp_buf");
int DS_IO_SOFT ds17_setjmp(DS17Jump *) __attribute__((returns_twice));
int DS_IO_SOFT ds17__setjmp(DS17Jump *) __attribute__((returns_twice));
void DS_IO_SOFT ds17_longjmp(DS17Jump *,int) __attribute__((noreturn));
void DS_IO_SOFT ds17__longjmp(DS17Jump *,int) __attribute__((noreturn));
void ds17_stats(DS17Stats *);
void ds17_reset_stats(void);
void ds17_observer(void (*)(uint32_t));
/* Internal assembly helpers. No locks remain held on return. */
void DS_IO_SOFT ds17_record(DS17Jump *,uint32_t kind);
uint32_t DS_IO_SOFT ds17_validate(const DS17Jump *,uint32_t kind);
uint32_t DS_IO_SOFT ds17_prepare(const DS17Jump *,uint32_t kind);
void DS_IO_SOFT ds17_bad_jump(uint32_t) __attribute__((noreturn));
uint32_t ds17_bindings(DSBinding *,uint32_t);
#endif
