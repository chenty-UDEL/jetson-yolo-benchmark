#!/usr/bin/env python3
"""Read-only PC/Jetson preflight; the optional --output writes a JSON report.

Local PC:
    python check_environment.py --output local_environment.json
Rented Jetson (run on the Jetson, not through a network timing loop):
    python3 check_environment.py --check-cuda --expect-jetson \
        --expect-model "Orin Nano" --output jetson_environment.json

No third-party packages are required to run this checker. --check-cuda probes
installed packages and performs a tiny CUDA operation plus torchvision NMS.
No packages are installed, clocks changed, or administrative commands run.
"""

import argparse
import datetime as dt
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys


PACKAGES = (
    "torch", "torchvision", "ultralytics", "tensorrt", "onnx",
    "onnxruntime", "numpy", "pandas", "matplotlib", "opencv-python",
    "opencv-python-headless",
)
TOOLS = (
    "git", "ssh", "scp", "sftp", "tar", "docker", "tmux",
    "nvidia-smi", "tegrastats", "nvpmodel", "jetson_clocks",
)


def read_text(path):
    try:
        return Path(path).read_text(errors="replace").replace("\x00", " ").strip()
    except (OSError, UnicodeError):
        return None


def run_command(argv):
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, errors="replace", timeout=15,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "error": str(exc)}


def package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def probe_gpu():
    result = {"torch_cuda_ok": False, "torchvision_cuda_nms_ok": False}
    try:
        import torch

        result["torch_version"] = torch.__version__
        result["torch_cuda_build"] = torch.version.cuda
        result["cuda_available"] = torch.cuda.is_available()
        if not result["cuda_available"]:
            result["torch_error"] = "PyTorch cannot access CUDA."
        else:
            result["gpu_name"] = torch.cuda.get_device_name(0)
            result["compute_capability"] = list(torch.cuda.get_device_capability(0))
            result["compiled_architectures"] = torch.cuda.get_arch_list()
            with torch.inference_mode():
                value = torch.ones(4, device="cuda") + 1
                torch.cuda.synchronize()
                result["torch_cuda_ok"] = value.sum().item() == 8
            try:
                import torchvision

                result["torchvision_version"] = torchvision.__version__
                boxes = torch.tensor(
                    [[0, 0, 10, 10], [1, 1, 9, 9]], dtype=torch.float32,
                    device="cuda",
                )
                scores = torch.tensor([0.9, 0.8], device="cuda")
                kept = torchvision.ops.nms(boxes, scores, 0.5)
                torch.cuda.synchronize()
                result["torchvision_cuda_nms_ok"] = kept.cpu().tolist() == [0]
            except Exception as exc:
                result["torchvision_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        result["torch_error"] = f"{type(exc).__name__}: {exc}"

    try:
        import tensorrt as trt

        result["tensorrt_import_ok"] = True
        result["tensorrt_version"] = trt.__version__
    except Exception as exc:
        result["tensorrt_import_ok"] = False
        result["tensorrt_error"] = f"{type(exc).__name__}: {exc}"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    parser.add_argument("--check-cuda", action="store_true")
    parser.add_argument("--expect-jetson", action="store_true")
    parser.add_argument("--expect-model", help='For example: "Orin Nano".')
    args = parser.parse_args()
    if args.expect_model and not args.expect_jetson:
        parser.error("--expect-model requires --expect-jetson")

    tools = {name: shutil.which(name) for name in TOOLS}
    model = read_text("/proc/device-tree/model") if sys.platform == "linux" else None
    tegra_release = read_text("/etc/nv_tegra_release") if sys.platform == "linux" else None
    is_jetson = bool(model and "jetson" in model.lower()) or bool(tegra_release)
    free_gib = round(shutil.disk_usage(Path.cwd()).free / (1024 ** 3), 2)
    report = {
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "disk_free_gib": free_gib,
        "jetson": {"detected": is_jetson, "model": model, "l4t_release": tegra_release},
        "packages": {name: package_version(name) for name in PACKAGES},
        "tools": tools,
        "commands": {},
        "cuda_probe": probe_gpu() if args.check_cuda else {"status": "not_requested"},
    }
    if tools["nvidia-smi"]:
        report["commands"]["nvidia_smi"] = run_command([
            tools["nvidia-smi"], "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ])
    if is_jetson:
        report["jetson"]["os_release"] = read_text("/etc/os-release")
        if shutil.which("dpkg-query"):
            report["commands"]["jetpack_packages"] = run_command([
                "dpkg-query", "-W", "-f=${Package} ${Version}\n",
                "nvidia-jetpack", "nvidia-l4t-core", "libnvinfer*",
            ])
        if tools["nvpmodel"]:
            report["commands"]["power_mode"] = run_command([tools["nvpmodel"], "-q"])
        if tools["jetson_clocks"]:
            report["commands"]["clock_settings"] = run_command([
                tools["jetson_clocks"], "--show",
            ])

    errors = []
    notes = []
    if args.expect_jetson:
        if not is_jetson:
            errors.append("A real Jetson was not detected on this host.")
        if platform.machine().lower() not in ("aarch64", "arm64"):
            errors.append("The host architecture is not ARM64.")
        if args.expect_model and args.expect_model.lower() not in (model or "").lower():
            errors.append(f"Device model does not match {args.expect_model!r}.")
        if not args.check_cuda:
            errors.append("GPU execution has not been tested; rerun with --check-cuda.")
        else:
            for key in ("torch_cuda_ok", "torchvision_cuda_nms_ok", "tensorrt_import_ok"):
                if not report["cuda_probe"].get(key):
                    errors.append(f"Required runtime check failed: {key}.")
        if not report["packages"]["ultralytics"]:
            errors.append("Ultralytics is not installed in this Python environment.")
        if not tools["tegrastats"]:
            notes.append("tegrastats is not on PATH; device telemetry is not confirmed.")
    else:
        notes.append("This is an inventory, not a completed Jetson readiness check.")
    notes.extend([
        "Dependency versions must be checked against the chosen JetPack release.",
        "Exclusive device access, cooling and permission to control power/clocks must be confirmed with the provider.",
        "TensorRT import alone does not verify engine build or inference; test the actual model before full measurements.",
        "No model execution or performance benchmarking has been performed.",
    ])
    report["assessment"] = {"errors": errors, "notes": notes}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
