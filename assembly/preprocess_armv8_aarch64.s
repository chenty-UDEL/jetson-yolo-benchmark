	.file	"preprocess_core.c"
	.text
	.globl	yolo_bgr8_to_rgb_chw_f32
	.p2align	2
	.type	yolo_bgr8_to_rgb_chw_f32,@function
yolo_bgr8_to_rgb_chw_f32:
	.cfi_startproc
	cbz	x2, .LBB0_3
	mov	w10, #1132396544
	lsl	x8, x2, #3
	add	x9, x0, #2
	fmov	s0, w10
	mov	x10, x2
.LBB0_2:
	ldr	b1, [x9]
	ldur	b2, [x9, #-1]
	subs	x10, x10, #1
	ldur	b3, [x9, #-2]
	add	x9, x9, #3
	ucvtf	s1, s1
	ucvtf	s2, s2
	ucvtf	s3, s3
	fdiv	s1, s1, s0
	fdiv	s2, s2, s0
	str	s1, [x1]
	fdiv	s3, s3, s0
	str	s2, [x1, x2, lsl #2]
	str	s3, [x1, x8]
	add	x1, x1, #4
	b.ne	.LBB0_2
.LBB0_3:
	ret
.Lfunc_end0:
	.size	yolo_bgr8_to_rgb_chw_f32, .Lfunc_end0-yolo_bgr8_to_rgb_chw_f32
	.cfi_endproc

	.section	".note.GNU-stack","",@progbits
	.addrsig
