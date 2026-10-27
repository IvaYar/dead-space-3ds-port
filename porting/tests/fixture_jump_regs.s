.syntax unified
.arm
.fpu vfp
.text
.align 2
.global probe_jump_registers
.type probe_jump_registers,%function
probe_jump_registers:
    push {r4-r11,lr}
    sub sp,sp,#4
    vpush {d8-d15}
    sub sp,sp,#308
    /* A deliberately 4 mod 8 caller SP AND jmp_buf. */
    str r0,[sp]
    vmrs r2,fpscr
    str r2,[sp,#268]
    ldr r2,=0xdeadbeef
    str r2,[sp,#4]
    str r2,[sp,#264]
    add r0,sp,#8
    mov r1,#64
    ldr r2,=0xf1f1f1f1
.Lfill:
    str r2,[r0],#4
    subs r1,r1,#1
    bne .Lfill
    mov r2,#0x00400000
    vmsr fpscr,r2
.macro seed reg,lo,hi
    ldr r2,=\lo
    ldr r3,=\hi
    vmov \reg,r2,r3
.endm
    seed d8,0x11110008,0xaaaa0008
    seed d9,0x11110009,0xaaaa0009
    seed d10,0x1111000a,0xaaaa000a
    seed d11,0x1111000b,0xaaaa000b
    seed d12,0x1111000c,0xaaaa000c
    seed d13,0x1111000d,0xaaaa000d
    seed d14,0x1111000e,0xaaaa000e
    seed d15,0x1111000f,0xaaaa000f
    ldr r4,=0x44444444
    ldr r5,=0x55555555
    ldr r6,=0x66666666
    ldr r7,=0x77777777
    ldr r8,=0x88888888
    ldr r9,=0x99999999
    ldr r10,=0xaaaaaaaa
    ldr r11,=0xbbbbbbbb
    ldr r12,=0xcccccccc
    add r0,sp,#8
    bl setjmp
    cmp r0,#0
    bne .Lreturned
    mov r4,#0
    mov r5,#0
    mov r6,#0
    mov r7,#0
    mov r8,#0
    mov r9,#0
    mov r10,#0
    mov r11,#0
    mov r12,#0
    mov r2,#0
    vmov d8,r2,r2
    vmov d9,r2,r2
    vmov d10,r2,r2
    vmov d11,r2,r2
    vmov d12,r2,r2
    vmov d13,r2,r2
    vmov d14,r2,r2
    vmov d15,r2,r2
    vmsr fpscr,r2
    sub sp,sp,#32
    add r0,sp,#40
    mov r1,#37
    bl longjmp
    b .
.Lreturned:
    ldr r2,[sp]
    str r0,[r2]
    add r1,r2,#4
    stmia r1,{r4-r12}
    vmrs r3,fpscr
    str r3,[r2,#40]
    str sp,[r2,#44]
    add r1,r2,#48
    vstmia r1,{d8-d15}
    ldr r3,[sp,#4]
    str r3,[r2,#112]
    ldr r3,[sp,#264]
    str r3,[r2,#116]
    ldr r3,[sp,#116] /* Entry r12 may be changed by the import PLT. */
    str r3,[r2,#120]
    /* Reserved words 32..63 must remain untouched. */
    mov r0,#0
    add r1,sp,#136
    mov r3,#32
    ldr r12,=0xf1f1f1f1
.Lreserved:
    ldr r2,[r1],#4
    cmp r2,r12
    movne r0,#1
    subs r3,r3,#1
    bne .Lreserved
    ldr r2,[sp,#268]
    vmsr fpscr,r2
    add sp,sp,#308
    vpop {d8-d15}
    add sp,sp,#4
    pop {r4-r11,pc}
.size probe_jump_registers,.-probe_jump_registers
.ltorg
.section .note.GNU-stack,"",%progbits
