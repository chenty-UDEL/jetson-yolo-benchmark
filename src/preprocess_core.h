#ifndef YOLO_PREPROCESS_CORE_H
#define YOLO_PREPROCESS_CORE_H

#include <stddef.h>

#if defined(_WIN32)
#define YOLO_EXPORT __declspec(dllexport)
#else
#define YOLO_EXPORT
#endif

/* Input: 3*N BGR bytes. Output: 3*N RGB floats in CHW order.
 * Buffers must not overlap. Zero pixels permits null pointers. */
YOLO_EXPORT void yolo_bgr8_to_rgb_chw_f32(
    const unsigned char *restrict bgr,
    float *restrict rgb_chw,
    size_t pixel_count);

#endif
