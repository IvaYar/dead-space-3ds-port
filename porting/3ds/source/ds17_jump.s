/* Independent ARM32 context bridge using the Android 64-word buffer layout.
 * VMOV + word stores support the donor's 4-byte aligned buffers without
 * assuming the double-word alignment of native newlib jmp_buf.
 * Words 30/31 are private owner/tag fields in Android's reserved tail.
 */
.syntax unified
.arm
.fpu vfp
.text
.align 2
.global ds17_setjmp
.type ds17_setjmp,%function
ds17_setjmp:
    mov r1,#1
    b .Lsave
.size ds17_setjmp,.-ds17_setjmp
.global ds17__setjmp
.type ds17__setjmp,%function
ds17__setjmp:
    mov r1,#0
.Lsave:
    cmp r0,#0
    beq .Lbad_pointer
    tst r0,#3
    bne .Lbad_pointer
    add r2,r0,#76
    stmia r2,{r4-r14}
    vmov r2,r3,d8
    str r2,[r0,#8]
    str r3,[r0,#12]
    vmov r2,r3,d9
    str r2,[r0,#16]
    str r3,[r0,#20]
    vmov r2,r3,d10
    str r2,[r0,#24]
    str r3,[r0,#28]
    vmov r2,r3,d11
    str r2,[r0,#32]
    str r3,[r0,#36]
    vmov r2,r3,d12
    str r2,[r0,#40]
    str r3,[r0,#44]
    vmov r2,r3,d13
    str r2,[r0,#48]
    str r3,[r0,#52]
    vmov r2,r3,d14
    str r2,[r0,#56]
    str r3,[r0,#60]
    vmov r2,r3,d15
    str r2,[r0,#64]
    str r3,[r0,#68]
    vmrs r2,fpscr
    str r2,[r0,#72]
    /* Preserve the original caller SP in the buffer and align helper calls. */
    mov r3,sp
    bic sp,sp,#7
    push {r3,lr}
    bl ds17_record
    pop {r3,lr}
    mov sp,r3
    mov r0,#0
    bx lr
.size ds17__setjmp,.-ds17__setjmp
.global ds17_longjmp
.type ds17_longjmp,%function
ds17_longjmp:
    mov r2,#1
    b .Lrestore
.size ds17_longjmp,.-ds17_longjmp
.global ds17__longjmp
.type ds17__longjmp,%function
ds17__longjmp:
    mov r2,#0
.Lrestore:
    mov r3,sp
    bic sp,sp,#7
    push {r0,r1,r3,lr}
    mov r1,r2
    bl ds17_prepare
    mov r2,r0
    pop {r0,r1,r3,lr}
    mov sp,r3
    cmp r2,#0
    movne r0,r2
    bicne sp,sp,#7
    bne ds17_bad_jump
    /* No C calls after validation: restore the saved machine context. */
    ldr r2,[r0,#8]
    ldr r3,[r0,#12]
    vmov d8,r2,r3
    ldr r2,[r0,#16]
    ldr r3,[r0,#20]
    vmov d9,r2,r3
    ldr r2,[r0,#24]
    ldr r3,[r0,#28]
    vmov d10,r2,r3
    ldr r2,[r0,#32]
    ldr r3,[r0,#36]
    vmov d11,r2,r3
    ldr r2,[r0,#40]
    ldr r3,[r0,#44]
    vmov d12,r2,r3
    ldr r2,[r0,#48]
    ldr r3,[r0,#52]
    vmov d13,r2,r3
    ldr r2,[r0,#56]
    ldr r3,[r0,#60]
    vmov d14,r2,r3
    ldr r2,[r0,#64]
    ldr r3,[r0,#68]
    vmov d15,r2,r3
    ldr r2,[r0,#72]
    vmsr fpscr,r2
    add r2,r0,#76
    ldmia r2,{r4-r14}
    cmp r1,#0
    moveq r1,#1
    mov r0,r1
    bx lr
.size ds17__longjmp,.-ds17__longjmp
.Lbad_pointer:
    mov r0,#1
    bic sp,sp,#7
    b ds17_bad_jump
.section .note.GNU-stack,"",%progbits
