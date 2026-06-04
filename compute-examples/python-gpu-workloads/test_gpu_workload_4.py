"""
test_gpu_workload_4.py  —  Small model training benchmark + GitLab Model Registry upload

Trains a GPT-style transformer on synthetic data for 500 steps,
then saves the checkpoint and uploads it to the GitLab Model Registry.

Required env vars:
  GITLAB_TOKEN      -- Personal Access Token with api scope (write:packages, write:model_registry)
  ZER_PUBLIC_KEY    -- Dispersed API public key
  ZER_SECRET_KEY    -- Dispersed API secret key

Usage:
    python3 test_gpu_workload_4.py [--job-file PATH] [--no-stop] [--private-key PATH]
"""

import os
from pathlib import Path
from workload_runner import run_persistent_workload

BENCHMARK_CODE_TEMPLATE = """\
import torch, time, sys, math, os, json, tempfile
import urllib.request, urllib.error
import torch.nn as nn
import torch.nn.functional as F

GITLAB_TOKEN      = os.environ.get("GITLAB_TOKEN", "")
GITLAB_PROJECT_ID = os.environ.get("GITLAB_PROJECT_ID", "")
GITLAB_HOST       = os.environ.get("GITLAB_HOST", "gitlab.com")
GITLAB_NAMESPACE  = os.environ.get("GITLAB_NAMESPACE", "")
GITLAB_API        = f"https://{GITLAB_HOST}/api/v4"
MODEL_NAME        = "gpt-benchmark"

print("=" * 64)
print("GPU Training Benchmark -- Small GPT-style Transformer")
print("=" * 64)

if not torch.cuda.is_available():
    print("ERROR: CUDA not available", file=sys.stderr)
    sys.exit(1)

device = torch.device("cuda:0")
props  = torch.cuda.get_device_properties(device)
GPU_NAME = props.name
print(f"Device  : {GPU_NAME}")
print(f"VRAM    : {props.total_memory / 1024**3:.1f} GB")
print(f"CUDA    : {torch.version.cuda}")
print(f"PyTorch : {torch.__version__}")
print()

VOCAB   = 32768
SEQ_LEN = 512
BATCH   = 16
D_MODEL = 512
HEADS   = 8
LAYERS  = 6
D_FF    = D_MODEL * 4
STEPS   = 500
LR      = 3e-4

print(f"Model   : {LAYERS}L  d={D_MODEL}  heads={HEADS}  seq={SEQ_LEN}  vocab={VOCAB}")
print(f"Batch   : {BATCH}  Steps: {STEPS}  LR: {LR}")
print()

class GPTBlock(nn.Module):
    def __init__(self):
        super().__init__()
        self.ln1  = nn.LayerNorm(D_MODEL)
        self.attn = nn.MultiheadAttention(D_MODEL, HEADS, batch_first=True)
        self.ln2  = nn.LayerNorm(D_MODEL)
        self.ff   = nn.Sequential(
            nn.Linear(D_MODEL, D_FF), nn.GELU(), nn.Linear(D_FF, D_MODEL)
        )
    def forward(self, x):
        a, _ = self.attn(self.ln1(x), self.ln1(x), self.ln1(x), need_weights=False)
        x = x + a
        x = x + self.ff(self.ln2(x))
        return x

class GPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.tok_emb = nn.Embedding(VOCAB, D_MODEL)
        self.pos_emb = nn.Embedding(SEQ_LEN, D_MODEL)
        self.blocks  = nn.Sequential(*[GPTBlock() for _ in range(LAYERS)])
        self.ln_f    = nn.LayerNorm(D_MODEL)
        self.head    = nn.Linear(D_MODEL, VOCAB, bias=False)
    def forward(self, idx):
        pos = torch.arange(idx.size(1), device=idx.device)
        x   = self.tok_emb(idx) + self.pos_emb(pos)
        x   = self.blocks(x)
        x   = self.ln_f(x)
        return self.head(x)

model     = GPT().to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=LR, fused=True)
scaler    = torch.amp.GradScaler()
n_params  = sum(p.numel() for p in model.parameters())
print(f"Parameters: {n_params/1e6:.1f}M")
print()

print(f"{'Step':>6}  {'Loss':>8}  {'Tokens/s':>12}  {'ms/step':>10}")
print("-" * 46)

total_tokens = 0
train_start  = time.perf_counter()
log_every    = 50
final_loss   = 0.0

for step in range(1, STEPS + 1):
    x   = torch.randint(0, VOCAB, (BATCH, SEQ_LEN), device=device)
    tgt = torch.randint(0, VOCAB, (BATCH, SEQ_LEN), device=device)

    t0 = time.perf_counter()
    with torch.amp.autocast(device_type="cuda"):
        logits = model(x)
        loss   = F.cross_entropy(logits.view(-1, VOCAB), tgt.view(-1))

    scaler.scale(loss).backward()
    scaler.unscale_(optimizer)
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    scaler.step(optimizer)
    scaler.update()
    optimizer.zero_grad(set_to_none=True)
    torch.cuda.synchronize()
    step_time = time.perf_counter() - t0

    final_loss    = loss.item()
    total_tokens += BATCH * SEQ_LEN

    if step % log_every == 0 or step == 1:
        tps = (BATCH * SEQ_LEN) / step_time
        print(f"{step:>6}  {final_loss:>8.4f}  {tps:>12,.0f}  {step_time*1000:>10.1f}")

train_elapsed = time.perf_counter() - train_start
avg_tps       = total_tokens / train_elapsed

print()
print("=" * 64)
print(f"Training complete  ({STEPS} steps)")
print(f"  Total time       : {train_elapsed:.1f} s")
print(f"  Avg throughput   : {avg_tps:,.0f} tokens/s")
print(f"  Final loss       : {final_loss:.4f}")
print("=" * 64)

print()
print("Saving model checkpoint ...")
ckpt_path = "/tmp/gpt_benchmark.pt"
torch.save({
    "model_state": model.state_dict(),
    "config": {
        "vocab": VOCAB, "seq_len": SEQ_LEN, "d_model": D_MODEL,
        "heads": HEADS, "layers": LAYERS, "d_ff": D_FF,
    },
    "training": {
        "steps": STEPS, "batch": BATCH, "lr": LR,
        "final_loss": final_loss, "avg_tokens_per_s": avg_tps,
        "gpu": GPU_NAME, "n_params": n_params,
    },
}, ckpt_path)
ckpt_size_mb = os.path.getsize(ckpt_path) / 1024**2
print(f"  Saved to: {ckpt_path}  ({ckpt_size_mb:.1f} MB)")

if not GITLAB_TOKEN:
    print("WARN: GITLAB_TOKEN not set -- skipping upload", file=sys.stderr)
    sys.exit(0)

import time as _t
version_str = GPU_NAME.replace(" ", "-").replace("/", "-") + "-" + str(int(_t.time()))
pkg_version = version_str

headers_json = {"PRIVATE-TOKEN": GITLAB_TOKEN, "Content-Type": "application/json"}
headers_raw  = {"PRIVATE-TOKEN": GITLAB_TOKEN, "Content-Type": "application/octet-stream"}

def gl_request(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return json.loads(body) if body else {}, e.code

print()
print(f"Uploading checkpoint to GitLab packages (version: {pkg_version}) ...")
pkg_url = (f"{GITLAB_API}/projects/{GITLAB_PROJECT_ID}/packages/generic"
           f"/{MODEL_NAME}/{pkg_version}/model.pt")
with open(ckpt_path, "rb") as f:
    ckpt_bytes = f.read()
req = urllib.request.Request(pkg_url, data=ckpt_bytes, method="PUT", headers=headers_raw)
try:
    urllib.request.urlopen(req)
    print(f"  Package uploaded: {pkg_url}")
except urllib.error.HTTPError as e:
    print(f"  ERROR uploading package: {e.code} {e.read().decode()}", file=sys.stderr)
    sys.exit(1)

print("Registering model in GitLab Model Registry ...")
mlflow_base    = f"{GITLAB_API}/projects/{GITLAB_PROJECT_ID}/ml/mlflow/api/2.0/mlflow"
create_mod_url = f"{mlflow_base}/registered-models/create"
body = json.dumps({"name": MODEL_NAME}).encode()
result, status = gl_request(create_mod_url, method="POST", data=body, headers=headers_json)

if status == 200:
    print(f"  Created registered model '{MODEL_NAME}'")
elif status == 400 and result.get("error_code") == "RESOURCE_ALREADY_EXISTS":
    print(f"  Model '{MODEL_NAME}' already exists -- proceeding to version creation.")
else:
    print(f"  WARN: Unexpected response {status} from Model Registry: {result}", file=sys.stderr)

print(f"  Creating model version '{version_str}' ...")
create_ver_url = f"{mlflow_base}/model-versions/create"
version_body = json.dumps({
    "name":    MODEL_NAME,
    "version": version_str,
    "tags": [
        {"key": "gpu",     "value": GPU_NAME},
        {"key": "params",  "value": f"{n_params/1e6:.1f}M"},
        {"key": "tok_s",   "value": f"{avg_tps:,.0f}"},
        {"key": "loss",    "value": f"{final_loss:.4f}"},
        {"key": "package", "value": pkg_url},
    ],
}).encode()
ver_result, ver_status = gl_request(create_ver_url, method="POST", data=version_body, headers=headers_json)

if ver_status == 200:
    mv = ver_result.get("model_version", {})
    print(f"  Model version registered: {mv.get('name')} v{mv.get('version')} (status: {mv.get('status')})")
else:
    print(f"  WARN: version creation returned {ver_status}: {ver_result}", file=sys.stderr)

if ver_status == 200:
    mv = ver_result.get("model_version", {})
    internal_id = mv.get("version")   # e.g. "42"
    if internal_id:
        print(f"  Uploading checkpoint as model artifact (version id={internal_id}) ...")
        art_url = (
            f"{GITLAB_API}/projects/{GITLAB_PROJECT_ID}"
            f"/packages/ml_models/{internal_id}/files/model.pt"
        )
        with open(ckpt_path, "rb") as f:
            ckpt_bytes_art = f.read()
        art_req = urllib.request.Request(
            art_url, data=ckpt_bytes_art, method="PUT",
            headers={"Authorization": f"Bearer {GITLAB_TOKEN}", "Content-Type": "application/octet-stream"}
        )
        try:
            urllib.request.urlopen(art_req)
            print(f"  Artifact uploaded: model.pt")
        except urllib.error.HTTPError as e:
            print(f"  WARN: artifact upload returned {e.code}: {e.read().decode()}", file=sys.stderr)
    else:
        print("  WARN: could not determine version id -- skipping artifact upload", file=sys.stderr)

print()
print("Upload complete. Checkpoint available at:")
print(f"  {pkg_url}")
print(f"  Model registry: https://gitlab.com/{GITLAB_NAMESPACE}/-/ml/models")
"""

if __name__ == "__main__":
    benchmark_code = BENCHMARK_CODE_TEMPLATE
    run_persistent_workload(
        benchmark_code,
        "workload-4",
        Path(__file__).parent / "job-gpu-workload-4.json",
        extra_env={
            "GITLAB_TOKEN":      os.environ.get("GITLAB_TOKEN", ""),
            "GITLAB_PROJECT_ID": os.environ.get("GITLAB_PROJECT_ID", ""),
            "GITLAB_HOST":       os.environ.get("GITLAB_HOST", "gitlab.com"),
            "GITLAB_NAMESPACE":  os.environ.get("GITLAB_NAMESPACE", ""),
        },
    )
