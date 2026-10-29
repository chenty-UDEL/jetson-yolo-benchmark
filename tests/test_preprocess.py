import ctypes
import os
from pathlib import Path
import random
import struct

ROOT = Path(__file__).resolve().parents[1]


def main():
    library = "preprocess.dll" if os.name == "nt" else "preprocess.so"
    lib = ctypes.CDLL(str(ROOT / "build" / library))
    convert = lib.yolo_bgr8_to_rgb_chw_f32
    convert.argtypes = [ctypes.POINTER(ctypes.c_ubyte),
                        ctypes.POINTER(ctypes.c_float), ctypes.c_size_t]
    convert.restype = None
    convert(None, None, 0)

    rng = random.Random(662)
    cases = [
        [0, 127, 255],
        [0, 127, 255, 255, 0, 128],
        [v for v in range(256) for _ in range(3)],
        [rng.randrange(256) for _ in range(3 * 17)],
        [rng.randrange(256) for _ in range(3 * 640 * 640)],
    ]
    for values in cases:
        count = len(values) // 3
        source = (ctypes.c_ubyte * len(values))(*values)
        output = (ctypes.c_float * (3 * count + 2))()
        output[3 * count] = 12345.0
        output[3 * count + 1] = -54321.0
        convert(source, output, count)
        expected = b"".join(struct.pack("<f", values[3 * i + channel] / 255.0)
                            for channel in (2, 1, 0) for i in range(count))
        assert bytes(output)[:12 * count] == expected
        assert output[3 * count] == 12345.0
        assert output[3 * count + 1] == -54321.0
    print("6 preprocessing tests passed.")


if __name__ == "__main__":
    main()
