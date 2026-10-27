.syntax unified
.arm
.text
.align 2
.global ds_invalidate_instruction_cache
.type ds_invalidate_instruction_cache, %function
ds_invalidate_instruction_cache:
    svc 0x93
    bx lr
.size ds_invalidate_instruction_cache, .-ds_invalidate_instruction_cache
.section .note.GNU-stack,"",%progbits
