import os
import sys
import time
import json
import torch
import torch.nn as nn
import torch.nn.functional as F

print("=" * 60)
print("GPU Benchmark — FP16, Memory Bandwidth, MLP Forward Pass")
print("=" * 60)

if not torch.cuda.is_available():
    print("ERROR: CUDA is not available!", file=sys.stderr)
    sys.exit(1)

device = torch.device("cuda:0")
props  = torch.cuda.get_device_properties(device)
GPU_NAME = props.name
print(f"Device       : {GPU_NAME}")
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

# Upload results to S3 if configured
s3_bucket = os.environ.get("S3_BUCKET", "")
if s3_bucket:
    import boto3
    import datetime
    results = {
        "gpu": GPU_NAME,
        "vram_gb": round(props.total_memory / 1024**3, 1),
        "tflops_fp16": round(tflops, 2),
        "memory_bandwidth_gbs": round(bw, 1),
        "compute_time_s": round(_compute_elapsed, 2),
    }
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"batch-results/{ts}-benchmark.json"
    try:
        boto3.client("s3").put_object(
            Bucket=s3_bucket,
            Key=key,
            Body=json.dumps(results, indent=2).encode(),
            ContentType="application/json",
        )
        print(f"Results uploaded to s3://{s3_bucket}/{key}")
    except Exception as e:
        print(f"WARNING: S3 upload failed: {e}", file=sys.stderr)
