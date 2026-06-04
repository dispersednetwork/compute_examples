"""
test_gpu_workload_3.py  —  GPU reduction benchmark (persistent, SSH-based)

Benchmarks how fast the GPU can sum the first 10,000,000 integers,
repeated 100,000 times. Verifies correctness and reports throughput.

Usage:
    python3 test_gpu_workload_3.py [--job-file PATH] [--no-stop] [--private-key PATH]
"""

from pathlib import Path
from workload_runner import run_persistent_workload

BENCHMARK_CODE = """\
import torch, time, sys

print("=" * 60)
print("GPU Benchmark -- Sum of first 10,000,000 integers")
print("=" * 60)

if not torch.cuda.is_available():
    print("ERROR: CUDA not available", file=sys.stderr)
    sys.exit(1)

device = torch.device("cuda:0")
props  = torch.cuda.get_device_properties(device)
print(f"Device  : {props.name}")
print(f"VRAM    : {props.total_memory / 1024**3:.1f} GB")
print(f"CUDA    : {torch.version.cuda}")
print(f"PyTorch : {torch.__version__}")
print()

N     = 10_000_000
ITERS = 100_000
EXPECTED = N * (N + 1) // 2  # 50,000,005,000,000

# Build the tensor once -- keep it on GPU for all iterations
x = torch.arange(1, N + 1, dtype=torch.int64, device=device)

# Correctness check
result = x.sum().item()
if result != EXPECTED:
    print(f"ERROR: Expected {EXPECTED}, got {result}", file=sys.stderr)
    sys.exit(1)
print(f"[PASS] Sum of 1..{N:,} = {result:,}  (correct)")

# Warmup
for _ in range(100):
    _ = x.sum()
torch.cuda.synchronize()

# Benchmark
print(f"[BENCH] Running {ITERS:,} reductions ...")
t0 = time.perf_counter()
for _ in range(ITERS):
    s = x.sum()
torch.cuda.synchronize()
elapsed = time.perf_counter() - t0

per_iter_us = elapsed / ITERS * 1e6
# Each iter reads N int64 values (8 bytes each)
read_bytes  = N * 8 * ITERS
throughput  = read_bytes / elapsed / 1e9  # GB/s

print(f"[BENCH] Total time      : {elapsed:.2f} s")
print(f"[BENCH] Per iteration   : {per_iter_us:.2f} us")
print(f"[BENCH] Throughput      : {throughput:.1f} GB/s  (effective read bandwidth)")
print(f"[BENCH] Reductions/sec  : {ITERS/elapsed/1e6:.2f} M/s")
print()
print("Done.")
"""

if __name__ == "__main__":
    run_persistent_workload(
        BENCHMARK_CODE,
        "workload-3",
        Path(__file__).parent / "job-gpu-workload-3.json",
    )
