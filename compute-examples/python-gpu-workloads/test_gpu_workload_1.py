"""
test_gpu_workload_1.py  —  Basic GPU benchmark (persistent, SSH-based)

Runs on any available GPU. Tests:
  - FP16 8192x8192 matrix multiply -> TFLOPS
  - Memory bandwidth -> GB/s
  - MLP forward pass latency

Usage:
    python3 test_gpu_workload_1.py [--job-file PATH] [--no-stop] [--private-key PATH]
"""

from pathlib import Path
from workload_runner import run_persistent_workload

BENCHMARK_CODE = """\
import torch, time, sys

print("=" * 60)
print("GPU Benchmark")
print("=" * 60)

if not torch.cuda.is_available():
    print("ERROR: CUDA is not available!", file=sys.stderr)
    sys.exit(1)

device = torch.device("cuda:0")
props  = torch.cuda.get_device_properties(device)
print(f"Device       : {props.name}")
print(f"VRAM         : {props.total_memory / 1024**3:.1f} GB")
print(f"CUDA version : {torch.version.cuda}")
print(f"PyTorch      : {torch.__version__}")
print()

# 1. Sanity check
a = torch.rand(1000, 1000, device=device)
b = torch.rand(1000, 1000, device=device)
torch.matmul(a, b)
torch.cuda.synchronize()
print("[PASS] Basic tensor matmul on GPU")

# -- Timed section starts here ------------------------------------------------
_compute_start = time.perf_counter()

# 2. FP16 TFLOPS (tensor cores)
N = 8192
a = torch.rand(N, N, device=device, dtype=torch.float16)
b = torch.rand(N, N, device=device, dtype=torch.float16)
torch.matmul(a, b); torch.cuda.synchronize()  # warmup

iters = 5000
start = time.perf_counter()
for _ in range(iters):
    c = torch.matmul(a, b)
torch.cuda.synchronize()
elapsed = time.perf_counter() - start
tflops = 2 * N**3 * iters / elapsed / 1e12
print(f"[BENCH] FP16 {N}x{N} matmul : {tflops:.2f} TFLOPS  ({elapsed/iters*1000:.1f} ms/iter)")

# 3. Memory bandwidth
n_elems = int(1.0 * 1024**3 / 4)
x = torch.rand(n_elems, device=device)
torch.cuda.synchronize()
iters = 2500
start = time.perf_counter()
for _ in range(iters):
    y = x * 2.0
torch.cuda.synchronize()
elapsed = time.perf_counter() - start
bw = 1.0 * iters * 2 / elapsed
print(f"[BENCH] Memory bandwidth    : {bw:.1f} GB/s")

# 4. MLP forward pass
import torch.nn as nn
model = nn.Sequential(
    nn.Linear(4096, 4096), nn.ReLU(),
    nn.Linear(4096, 4096), nn.ReLU(),
    nn.Linear(4096, 1024),
).to(device).half()
x = torch.rand(64, 4096, device=device, dtype=torch.float16)
with torch.no_grad():
    model(x); torch.cuda.synchronize()  # warmup
start = time.perf_counter()
for _ in range(50000):
    with torch.no_grad():
        model(x)
torch.cuda.synchronize()
elapsed = time.perf_counter() - start
print(f"[BENCH] MLP forward pass    : {elapsed/50000*1000:.2f} ms/iter")

_compute_elapsed = time.perf_counter() - _compute_start
print()
print(f"[BENCH] GPU compute time    : {_compute_elapsed:.2f} s")
print()
print("All GPU tests passed.")
"""

if __name__ == "__main__":
    run_persistent_workload(
        BENCHMARK_CODE,
        "workload-1",
        Path(__file__).parent / "job-gpu-workload-1.json",
        verify_pytorch=True,
    )
