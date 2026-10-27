/* Explicit, correctly sized ARM exports call hidden Thumb test bodies.
 * Avoid GNU ld's exported Thumb veneers inheriting the body's oversized size.
 */
.syntax unified
.arm
.text
.align 2
.macro wrapper name,body
.global \name
.type \name,%function
\name:
    push {r4,lr}
    bl \body
    pop {r4,pc}
.size \name,.-\name
.endm
wrapper probe_jump,ds17_thumb_probe_jump
wrapper probe_jump_nested,ds17_thumb_probe_jump_nested
wrapper probe_jump_underscore,ds17_thumb_probe_jump_underscore
.section .note.GNU-stack,"",%progbits
