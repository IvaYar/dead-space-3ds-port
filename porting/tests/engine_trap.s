.syntax unified
.arm
.text
.global ds_audit_trap
.type ds_audit_trap, %function
ds_audit_trap:
    mov r2, r1
    mov r0, r12
    mov r1, lr
    b ds_audit_stop
.size ds_audit_trap, .-ds_audit_trap
.section .note.GNU-stack,"",%progbits
