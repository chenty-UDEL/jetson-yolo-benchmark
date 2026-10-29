	.intel_syntax noprefix
	.file	"preprocess_core.c"
	.section	.rodata.cst4,"aM",@progbits,4
	.p2align	2, 0x0
.LCPI0_0:
	.long	0x437f0000
	.text
	.globl	yolo_bgr8_to_rgb_chw_f32
	.p2align	4
	.type	yolo_bgr8_to_rgb_chw_f32,@function
yolo_bgr8_to_rgb_chw_f32:
	.cfi_startproc
	test	rdx, rdx
	je	.LBB0_4
	push	rbp
	.cfi_def_cfa_offset 16
	.cfi_offset rbp, -16
	mov	rbp, rsp
	.cfi_def_cfa_register rbp
	add	rdi, 2
	movss	xmm0, dword ptr [rip + .LCPI0_0]
	mov	rax, rdx
	.p2align	4
.LBB0_2:
	movzx	ecx, byte ptr [rdi]
	xorps	xmm1, xmm1
	cvtsi2ss	xmm1, ecx
	divss	xmm1, xmm0
	movzx	ecx, byte ptr [rdi - 1]
	xorps	xmm2, xmm2
	cvtsi2ss	xmm2, ecx
	movss	dword ptr [rsi], xmm1
	divss	xmm2, xmm0
	movss	dword ptr [rsi + 4*rdx], xmm2
	movzx	ecx, byte ptr [rdi - 2]
	xorps	xmm1, xmm1
	cvtsi2ss	xmm1, ecx
	divss	xmm1, xmm0
	movss	dword ptr [rsi + 8*rdx], xmm1
	add	rsi, 4
	add	rdi, 3
	add	rax, -1
	jne	.LBB0_2
	pop	rbp
	.cfi_def_cfa rsp, 8
	.cfi_restore rbp
.LBB0_4:
	ret
.Lfunc_end0:
	.size	yolo_bgr8_to_rgb_chw_f32, .Lfunc_end0-yolo_bgr8_to_rgb_chw_f32
	.cfi_endproc

	.section	".note.GNU-stack","",@progbits
	.addrsig
