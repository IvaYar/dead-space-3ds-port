.syntax unified
.arm
.text
.align 2
.global ds_invalidate_entire_instruction_cache
.type ds_invalidate_entire_instruction_cache, %function
ds_invalidate_entire_instruction_cache:
    mov r0, #0
    mov r1, #0
    svc 0x94
    bx lr
.size ds_invalidate_entire_instruction_cache, .-ds_invalidate_entire_instruction_cache
.section .note.GNU-stack,"",%progbits
