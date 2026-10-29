import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Build with Zig 0.15.2.")
    parser.add_argument("--zig", default=shutil.which("zig"))
    args = parser.parse_args()
    if not args.zig:
        parser.error("Pass --zig with the path to the Zig executable.")
    compiler = str(Path(args.zig).resolve())
    env = os.environ.copy()
    env["ZIG_GLOBAL_CACHE_DIR"] = str(ROOT / ".cache/zig")

    def run(*arguments):
        subprocess.run([compiler, "cc", *arguments], cwd=ROOT, env=env, check=True)

    for directory in ("assembly", "build"):
        (ROOT / directory).mkdir(exist_ok=True)

    flags = [
        "-std=c11", "-O2", "-Wall", "-Wextra", "-mcpu=baseline",
        "-Wno-unused-command-line-argument", "-fno-vectorize",
        "-fno-slp-vectorize", "-fno-unroll-loops", "-ffp-contract=off",
        "-fno-ident", "-g0", "-fno-verbose-asm",
    ]
    targets = [
        ("x86_64", "x86_64-linux-gnu", ["-masm=intel"]),
        ("armv8_aarch64", "aarch64-linux-gnu", []),
    ]
    for name, triple, syntax in targets:
        assembly = f"assembly/preprocess_{name}.s"
        obj = f"build/preprocess_{name}.o"
        run("-target", triple, *flags, *syntax, "src/preprocess_core.c", "-S", "-o", assembly)
        run("-target", triple, "-c", assembly, "-o", obj)
        run("-target", triple, "-nostdlib", "-static", "-no-pie",
            "-Wno-unused-command-line-argument",
            "-Wl,--entry=yolo_bgr8_to_rgb_chw_f32", "-Wl,--build-id=none",
            obj, "-o", f"build/preprocess_{name}.elf")

    library = "preprocess.dll" if os.name == "nt" else "preprocess.so"
    run(*flags, "-shared", "-fPIC", "src/preprocess_core.c", "-o", f"build/{library}")
    print("Built x86-64 and ARMv8-A assembly.")


if __name__ == "__main__":
    main()
