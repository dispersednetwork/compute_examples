"""
test_gpu_workload_2.py  —  Hard GPU stress test (persistent, SSH-based)

Requires 13+ GB VRAM. Runs a sustained stress suite:
  1. Sustained FP16 matmul stress (16384x16384, 50 iters)
  2. BF16 tensor-core saturation
  3. Flash-attention simulation (large Q/K/V scaled dot-product)
  4. Transformer encoder forward pass (large model, large batch)
  5. Mixed-precision backward pass (gradient accumulation)
  6. Memory bandwidth stress (8 GB moves)

Usage:
    python3 test_gpu_workload_2.py [--job-file PATH] [--no-stop] [--private-key PATH]
"""

from pathlib import Path
from workload_runner import run_persistent_workload

BENCHMARK_CODE = """\
import torch, time, sys, math
import torch.nn as nn
import torch.nn.functional as F

def hline(): print("-" * 64)

def check_free():
    #Call AFTER inline del+empty_cache -- warns if VRAM wasn't released.
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    allocated_gb = torch.cuda.memory_allocated() / 1024**3
    if allocated_gb > 0.5:
        print(f"  WARNING: {allocated_gb:.2f} GB still allocated -- possible leak", file=sys.stderr, flush=True)

def bench(fn, iters=20, warmup=3):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / iters

print("=" * 64)
print("GPU Stress Benchmark (v2 -- harder)")
print("=" * 64)

if not torch.cuda.is_available():
    print("ERROR: CUDA not available", file=sys.stderr)
    sys.exit(1)

device = torch.device("cuda:0")
props  = torch.cuda.get_device_properties(device)
TOTAL  = props.total_memory          # bytes
BUDGET = TOTAL * 0.90                # 90% of card VRAM
BUDGET_GB = BUDGET / 1024**3
print(f"Device  : {props.name}")
print(f"VRAM    : {TOTAL/1024**3:.1f} GB  (budget per test: {BUDGET_GB:.1f} GB)")
print(f"CUDA    : {torch.version.cuda}")
print(f"PyTorch : {torch.__version__}")
hline()

_times = {}  # label -> wall seconds

# -- 1. FP16 matmul -----------------------------------------------------------
# Three N*N fp16 tensors: a, b, output -- 3 * N^2 * 2 bytes <= BUDGET
N = int(math.sqrt(BUDGET / (3 * 2))) // 256 * 256
print(f"[1] FP16 matmul  {N}x{N}  (50 iters) ...")
_t0 = time.monotonic()
a = torch.rand(N, N, device=device, dtype=torch.float16)
b = torch.rand(N, N, device=device, dtype=torch.float16)
t = bench(lambda: torch.matmul(a, b), iters=50)
_times["1. FP16 matmul"] = time.monotonic() - _t0
print(f"    {2*N**3/t/1e12:.2f} TFLOPS   ({t*1000:.1f} ms/iter)   wall: {_times['1. FP16 matmul']:.1f}s")
del a, b
check_free()
hline()

# -- 2. BF16 matmul -----------------------------------------------------------
N = int(math.sqrt(BUDGET / (3 * 2))) // 256 * 256
print(f"[2] BF16 matmul  {N}x{N}  (50 iters) ...")
_t0 = time.monotonic()
a = torch.rand(N, N, device=device, dtype=torch.bfloat16)
b = torch.rand(N, N, device=device, dtype=torch.bfloat16)
t = bench(lambda: torch.matmul(a, b), iters=50)
_times["2. BF16 matmul"] = time.monotonic() - _t0
print(f"    {2*N**3/t/1e12:.2f} TFLOPS   ({t*1000:.1f} ms/iter)   wall: {_times['2. BF16 matmul']:.1f}s")
del a, b
check_free()
hline()

# -- 3. Scaled dot-product attention ------------------------------------------
# Q, K, V inputs + output: 4 * B*H*S*D * 2 bytes <= BUDGET
# Scale B first (up to 32), then S to fill remaining budget
H, D = 32, 128
B = min(32, max(1, int(BUDGET / (4 * 2 * H * 4096 * D))))  # fit B at S=4096
S = int(BUDGET / (4 * 2 * B * H * D)) // 512 * 512
S = max(512, min(S, 65536))
print(f"[3] Scaled dot-product attention  B={B} H={H} S={S} D={D} ...")
_t0 = time.monotonic()
q = torch.rand(B, H, S, D, device=device, dtype=torch.float16)
k = torch.rand(B, H, S, D, device=device, dtype=torch.float16)
v = torch.rand(B, H, S, D, device=device, dtype=torch.float16)
t = bench(lambda: F.scaled_dot_product_attention(q, k, v), iters=20)
_times["3. SDPA attn"] = time.monotonic() - _t0
print(f"    {B*S/t/1e6:.2f} M tokens/s   ({t*1000:.1f} ms/iter)   wall: {_times['3. SDPA attn']:.1f}s")
del q, k, v
check_free()
hline()

# -- 4. Transformer encoder forward -------------------------------------------
# Scale d_model first (256->2048), then L to fill BUDGET
# Weight per layer ~= 4 * d_model^2 * 2 bytes (fp16 QKV+FFN)
d_model = min(2048, max(256, int(math.sqrt(BUDGET / (4 * 2 * 32)))))
d_model = d_model // 64 * 64  # must be divisible by nhead=16 -> use 64-alignment
nhead = min(16, d_model // 64)
L = max(4, int(BUDGET / (4 * 2 * d_model**2)))
L = min(L, 128)
batch = max(8, min(64, int(BUDGET / (4 * 2 * L * 512 * d_model))))
print(f"[4] Transformer encoder  L={L} d={d_model} heads={nhead} batch={batch} seq=512 ...")
_t0 = time.monotonic()
enc_layer = nn.TransformerEncoderLayer(
    d_model=d_model, nhead=nhead, dim_feedforward=d_model*4,
    batch_first=True, dtype=torch.float16,
).to(device)
enc = nn.TransformerEncoder(enc_layer, num_layers=L).to(device)
x = torch.rand(batch, 512, d_model, device=device, dtype=torch.float16)
with torch.no_grad():
    t = bench(lambda: enc(x), iters=10)
_times["4. Transformer fwd"] = time.monotonic() - _t0
print(f"    {t*1000:.1f} ms/iter   ({batch*512/t/1e3:.1f} K tokens/s)   wall: {_times['4. Transformer fwd']:.1f}s")
del enc, enc_layer, x
check_free()
hline()

# -- 6. Memory bandwidth ------------------------------------------------------
# clone() allocates another equal tensor so budget for 2 tensors simultaneously
bw_gb = BUDGET_GB / 2
n = int(bw_gb * 1024**3 / 4)
print(f"[6] Memory bandwidth  {bw_gb:.1f} GB tensor copy (2x{bw_gb:.1f} GB peak), 10 iters ...")
_t0 = time.monotonic()
x = torch.rand(n, device=device)
t = bench(lambda: x.clone(), iters=10, warmup=2)
_times["6. Bandwidth"] = time.monotonic() - _t0
print(f"    {bw_gb*2/t:.1f} GB/s   wall: {_times['6. Bandwidth']:.1f}s")
del x
check_free()
hline()

# -- Summary ------------------------------------------------------------------
total = sum(_times.values())
print()
print("+---------------------------------+--------------+")
print("| Test                            |  Wall time   |")
print("+---------------------------------+--------------+")
for label, secs in _times.items():
    print(f"| {label:<31s} |  {secs:>7.1f} s   |")
print("+---------------------------------+--------------+")
print(f"| {'TOTAL':<31s} |  {total:>7.1f} s   |")
print("+---------------------------------+--------------+")
print()
print("All stress tests complete.")
"""

if __name__ == "__main__":
    run_persistent_workload(
        BENCHMARK_CODE,
        "workload-2",
        Path(__file__).parent / "job-gpu-workload-2.json",
    )
