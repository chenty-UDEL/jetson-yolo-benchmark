#include "preprocess_core.h"

/* Input has already been resized and padded. */
YOLO_EXPORT void yolo_bgr8_to_rgb_chw_f32(
    const unsigned char *restrict bgr,
    float *restrict rgb_chw,
    size_t pixel_count)
{
    for (size_t i = 0; i < pixel_count; ++i) {
        rgb_chw[i] = (float)bgr[3 * i + 2] / 255.0f;
        rgb_chw[pixel_count + i] = (float)bgr[3 * i + 1] / 255.0f;
        rgb_chw[2 * pixel_count + i] = (float)bgr[3 * i] / 255.0f;
    }
}
