# Dispersed Compute — GPU Workload Test Harness

GPU benchmark scripts and batch job runners built on the [Dispersed Compute API](https://otoyinc.mintlify.app). Supports three modes: persistent SSH-based benchmarks, baked-in batch jobs, and a generic S3 script runner that lets you upload any Python script and run it on a GPU node with results returned to your terminal.

---

> **Working directory — all commands in this README must be run from:**
> ```
> compute-examples/python-gpu-workloads/
> ```
> Every path, script, and file reference below is relative to that directory.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Repository structure](#repository-structure)
3. [Step 1 — Get Dispersed API credentials](#step-1--get-dispersed-api-credentials)
4. [Step 2 — Generate an SSH key pair](#step-2--generate-an-ssh-key-pair)
5. [Step 3 — Set up a Docker registry](#step-3--set-up-a-docker-registry)
6. [Step 4 — Configure the environment](#step-4--configure-the-environment)
7. [Step 5 — Build and push the Docker images](#step-5--build-and-push-the-docker-images)
8. [Step 6 — Run the benchmarks](#step-6--run-the-benchmarks)
9. [Optional — S3 results upload](#optional--s3-results-upload)
10. [Optional — S3 data sync at startup](#optional--s3-data-sync-at-startup)
11. [Optional — Custom init script](#optional--custom-init-script)
12. [File reference](#file-reference)

---

## Prerequisites

- Python 3.11+ with `pip`
- Docker with `buildx` support for cross-platform builds (Docker Desktop on macOS/Windows handles this automatically; Linux requires `docker buildx` setup)
- A Docker registry accessible from the internet (Docker Hub, GitLab, GitHub Container Registry, AWS ECR, etc.)
- A [Dispersed Compute](https://dispersed.com/) account ([console](https://console.dispersed.com/))

---

## Repository structure

```
.
├── dispersed.py               # Dispersed REST API wrapper (HMAC auth, used by all scripts)
├── workload_runner.py         # Shared persistent-job lifecycle (create, poll, SSH, run, upload)
├── test_gpu_workload_1.py     # Basic GPU benchmark (persistent, SSH-based)
├── test_gpu_workload_2.py     # Hard stress test (persistent, SSH-based)
├── test_gpu_workload_3.py     # Reduction benchmark (persistent, SSH-based)
├── test_gpu_workload_4.py     # Training benchmark + GitLab Model Registry upload
├── test-batch-1.py            # Batch benchmark — baked-in workload, submit and poll
├── test-batch-2.py            # S3 script runner — upload any script, run on GPU, fetch results
├── job-gpu-workload-1.json    # Job spec for workload 1
├── job-gpu-workload-2.json    # Job spec for workload 2
├── job-gpu-workload-3.json    # Job spec for workload 3
├── job-gpu-workload-4.json    # Job spec for workload 4
├── job-batch-1.json           # Job spec for the baked-in batch benchmark
├── job-batch-2.json           # Job spec for the S3 script runner
├── docker/
│   ├── Dockerfile             # Persistent workload image (SSH + S3 sync + init script)
│   ├── entrypoint.sh          # Persistent container startup (sshd, S3 sync, init)
│   ├── Dockerfile.batch       # Batch benchmark image (benchmark baked in, no SSH)
│   ├── entrypoint-batch.sh    # Batch benchmark startup (run benchmark, exit)
│   ├── batch-benchmark.py     # Self-contained GPU benchmark baked into the batch image
│   ├── Dockerfile.s3batch     # S3 script runner image (generic, no workload baked in)
│   ├── entrypoint-s3batch.sh  # S3 runner startup (download script, run, upload results)
│   └── requirements.txt       # Python packages baked into all images
└── .env.example               # Environment variable template
```

---

## Step 1 — Get Dispersed API credentials

Log in to the [Dispersed Console](https://console.dispersed.com/) and create an API key — see the [API key docs](https://otoyinc.mintlify.app/api-key) for step-by-step instructions.

You will receive a **Public Key** (`pk_…`) and a **Secret Key** (`sk_…`). Keep these — you will add them to `.env` in Step 5.

---

## Step 2 — Generate an SSH key pair

The benchmark scripts SSH into the container running on the Dispersed node. You need a dedicated key pair for this.

```bash
# macOS / Linux
ssh-keygen -t ed25519 -f dispersed-key -N ""
```
```powershell
# Windows (PowerShell) — ssh-keygen ships with Windows 10+
ssh-keygen -t ed25519 -f dispersed-key -N '""'
```

This creates:
- `dispersed-key` — private key (never committed; gitignored)
- `dispersed-key.pub` — public key (used in `.env`)

Get the public key string:

```bash
# macOS / Linux
cat dispersed-key.pub
```
```powershell
# Windows (PowerShell)
Get-Content dispersed-key.pub
```

You will paste this value into `DISPERSED_SSH_PUBKEY` in `.env`.

---

## Step 3 — Set up a Docker registry

The Docker image is pushed to a registry that the Dispersed node can pull from. Any Docker-compatible registry works (Docker Hub, GitHub Container Registry, AWS ECR, etc.). The steps below use GitLab's container registry as an example.

1. Create a GitLab project (e.g. `your-namespace/your-project`)
2. Go to **Profile → Access Tokens** and create **two** Personal Access Tokens:

   | Token | Scopes | Used for |
   |-------|--------|----------|
   | **Registry read token** | `read_registry` | `DISPERSED_REGISTRY_SECRET` — the Dispersed node pulls the image at runtime |
   | **Registry push token** | `read_registry` + `write_registry` | `docker login` when building and pushing the image |

3. Note down:
   - Registry host: `registry.gitlab.com`
   - Username: `__token__`
   - Image path: `your-namespace/your-project/pytorch-custom`

---

## Step 4 — Configure the environment

```bash
# macOS / Linux
cp .env.example .env
```
```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```

Open `.env` and fill in every value:

```bash
# ── Dispersed API (https://console.dispersed.com/) ────────────────────────────
ZER_PUBLIC_KEY=pk_...
ZER_SECRET_KEY=sk_...

# ── Docker registry ────────────────────────────────────────────────────────────
DISPERSED_REGISTRY_HOST=registry.gitlab.com
DISPERSED_REGISTRY_USER=__token__
DISPERSED_REGISTRY_SECRET=glpat-...         # PAT with read_registry scope
DISPERSED_SSH_KEY=./dispersed-key           # path to SSH private key file
DISPERSED_SSH_PUBKEY=ssh-ed25519 AAAA...    # output of: cat dispersed-key.pub

# ── GPU workload image (workloads 1-4) ────────────────────────────────────────
GPU_IMAGE=your-namespace/your-project/pytorch-custom
GPU_IMAGE_TAG=latest

# ── Batch benchmark image (test-batch-1.py) ───────────────────────────────────
BATCH_GPU_IMAGE=your-namespace/your-project/pytorch-custom-batch
BATCH_GPU_IMAGE_TAG=latest

# ── S3 script runner image (test-batch-2.py) ──────────────────────────────────
S3_BATCH_GPU_IMAGE=your-namespace/your-project/pytorch-custom-s3batch
S3_BATCH_GPU_IMAGE_TAG=latest

# ── GitLab Model Registry (workload 4 only) ────────────────────────────────────
GITLAB_TOKEN=glpat-...          # PAT with write:packages + write:model_registry
GITLAB_PROJECT_ID=              # Numeric project ID (Settings → General)
GITLAB_NAMESPACE=your-namespace/your-project
GITLAB_HOST=gitlab.com

# ── AWS S3 (mandatory for test-batch-2.py; optional results upload for others) ─
S3_BUCKET=my-bucket
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

> **Never commit `.env`** — it should be gitignored. Only `.env.example` is committed.
>
> **Sensitive values** (passwords, API keys, tokens) should ideally be stored in an external secret manager such as 1Password or AWS Secrets Manager. For simplicity this guide uses `.env`.

### Set up Python environment

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
```powershell
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Step 5 — Build and push the Docker images

Both images must be built for **linux/amd64** (Dispersed nodes are x86-64). Docker Desktop on Apple Silicon supports cross-platform builds via buildx out of the box.

> **Windows users — WSL2 backend required.**
> The base image contains Linux package files with `:` in their names (e.g. `gcc-12-base:amd64.list`), which Windows filesystems reject. Docker Desktop must be configured to use the WSL2 backend (not Hyper-V) so that Linux layers are stored inside the WSL2 VM rather than on the Windows filesystem.
>
> **Docker Desktop → Settings → General → Use the WSL 2 based engine**
>
> Once enabled, `docker buildx build` works normally from PowerShell. If you are stuck on Hyper-V, run the build from a WSL2 terminal instead (`wsl` from PowerShell, then `cd /mnt/c/...`).

Load `.env` and log in to the registry:

```bash
# macOS / Linux
set -a && source .env && set +a
docker login registry.gitlab.com -u __token__ -p <registry-push-token>
```
```powershell
# Windows (PowerShell)
Get-Content .env | Where-Object {$_ -match '^[^#\s].+='} | ForEach-Object { $k,$v=$_ -split '=',2; $v=($v -replace '\s*#.*$','').Trim().Trim('"').Trim("'"); [Environment]::SetEnvironmentVariable($k.Trim(),$v,'Process') }
docker login registry.gitlab.com -u __token__ -p <registry-push-token>
```

### Persistent image (workloads 1–4)

```bash
# macOS / Linux
docker buildx build \
  --platform linux/amd64 \
  --push \
  -t registry.gitlab.com/${GPU_IMAGE}:${GPU_IMAGE_TAG} \
  -f docker/Dockerfile \
  docker/
```
```powershell
# Windows (PowerShell)
docker buildx build `
  --platform linux/amd64 `
  --push `
  -t "registry.gitlab.com/$Env:GPU_IMAGE`:$Env:GPU_IMAGE_TAG" `
  -f docker/Dockerfile `
  docker/
```

### Batch benchmark image (`test-batch-1.py`)

Benchmark baked in — no SSH server, exits when done.

```bash
# macOS / Linux
docker buildx build \
  --platform linux/amd64 \
  --push \
  -t registry.gitlab.com/${BATCH_GPU_IMAGE}:${BATCH_GPU_IMAGE_TAG} \
  -f docker/Dockerfile.batch \
  docker/
```
```powershell
# Windows (PowerShell)
docker buildx build `
  --platform linux/amd64 `
  --push `
  -t "registry.gitlab.com/$Env:BATCH_GPU_IMAGE`:$Env:BATCH_GPU_IMAGE_TAG" `
  -f docker/Dockerfile.batch `
  docker/
```

### S3 script runner image (`test-batch-2.py`)

Generic runner — no workload baked in. Downloads and runs any script from S3.

```bash
# macOS / Linux
docker buildx build \
  --platform linux/amd64 \
  --push \
  -t registry.gitlab.com/${S3_BATCH_GPU_IMAGE}:${S3_BATCH_GPU_IMAGE_TAG} \
  -f docker/Dockerfile.s3batch \
  docker/
```
```powershell
# Windows (PowerShell)
docker buildx build `
  --platform linux/amd64 `
  --push `
  -t "registry.gitlab.com/$Env:S3_BATCH_GPU_IMAGE`:$Env:S3_BATCH_GPU_IMAGE_TAG" `
  -f docker/Dockerfile.s3batch `
  docker/
```

Both images are based on `dispersednetwork/pytorch-pytorch:2.7.1-cuda12.8-cudnn9-runtime` (CUDA 12.8, PyTorch 2.7.1). Both install packages from `docker/requirements.txt`.

### Customising the image (optional)

**Add Python packages** — edit `docker/requirements.txt` and rebuild:

```
boto3
awscli
numpy
pandas
matplotlib
# add your packages here
```

**Runtime setup without rebuilding** — use the `INIT_SCRIPT` env var (see [Optional — Custom init script](#optional--custom-init-script)).

---

## Step 6 — Run the benchmarks

Three modes are available:

| Mode | Scripts | How it works |
|------|---------|--------------|
| **Persistent** | `test_gpu_workload_*.py` | Provisions a node, SSHs in, runs benchmark, stops job on exit |
| **Batch (baked-in)** | `test-batch-1.py` | Submits a BATCH job, container runs built-in benchmark and exits |
| **Batch (S3 runner)** | `test-batch-2.py` | Uploads your script to S3, container runs it, results printed locally |

Always load `.env` before running. On macOS/Linux use `set -a` to export vars to subprocesses:

```bash
# compute-examples/python-gpu-workloads/
set -a && source .env && set +a
source venv/bin/activate
```
```powershell
# compute-examples/python-gpu-workloads/
Get-Content .env | Where-Object {$_ -match '^[^#\s].+='} | ForEach-Object { $k,$v=$_ -split '=',2; $v=($v -replace '\s*#.*$','').Trim().Trim('"').Trim("'"); [Environment]::SetEnvironmentVariable($k.Trim(),$v,'Process') }
.\venv\Scripts\Activate.ps1
```

### Workload 1 — Basic GPU benchmark

```bash
# compute-examples/python-gpu-workloads/
python3 test_gpu_workload_1.py
```
```powershell
# compute-examples/python-gpu-workloads/
python test_gpu_workload_1.py
```

Runs on any available GPU (no VRAM minimum). Tests:
- FP16 8192×8192 matrix multiply → TFLOPS
- Memory bandwidth → GB/s
- MLP forward pass latency

### Workload 2 — Hard stress test

```bash
# compute-examples/python-gpu-workloads/
python3 test_gpu_workload_2.py
```
```powershell
# compute-examples/python-gpu-workloads/
python test_gpu_workload_2.py
```

Requires 13+ GB VRAM (`min_vram_gb: 13` in the job spec). Runs a sustained stress suite:
- FP16 and BF16 87296×87296 matrix multiply
- Scaled dot-product attention (large sequence length)
- Transformer encoder forward pass (128 layers, d=2048)
- Memory bandwidth (large tensor copy)

### Workload 3 — Reduction benchmark

```bash
# compute-examples/python-gpu-workloads/
python3 test_gpu_workload_3.py
```
```powershell
# compute-examples/python-gpu-workloads/
python test_gpu_workload_3.py
```

Requires 13+ GB VRAM. Benchmarks GPU reduction throughput:
- Sums the first 10,000,000 integers 100,000 times
- Verifies correctness
- Reports per-iteration latency and effective read bandwidth

### Workload 4 — Training benchmark + model upload

```bash
# compute-examples/python-gpu-workloads/
python3 test_gpu_workload_4.py
```
```powershell
# compute-examples/python-gpu-workloads/
python test_gpu_workload_4.py
```

Requires 13+ GB VRAM and `GITLAB_TOKEN` to be set. Trains a small GPT-style transformer on synthetic data for 500 steps, then:
- Saves a model checkpoint (~200 MB)
- Uploads it to the GitLab Package Registry
- Registers it in the GitLab Model Registry (MLflow-compatible)

Results are viewable at `https://gitlab.com/<GITLAB_NAMESPACE>/-/ml/models`.

### Batch benchmark — FP16, memory bandwidth, MLP

The batch benchmark runs entirely inside the container — no SSH, no persistent node. The job starts, runs the benchmark, and exits. Results are printed to the Dispersed job logs and, if `S3_BUCKET` is configured, uploaded as JSON to `s3://<S3_BUCKET>/batch-results/`.

```bash
# compute-examples/python-gpu-workloads/
python3 test-batch-1.py
```
```powershell
# compute-examples/python-gpu-workloads/
python test-batch-1.py
```

The benchmark tests:
- FP16 8192×8192 matrix multiply → TFLOPS
- Memory bandwidth → GB/s
- MLP forward pass latency

| Flag | Description |
|------|-------------|
| `--job-file PATH` | Use a custom job JSON file (default: `job-batch-1.json`) |
| `--timeout SECONDS` | Max seconds to wait for completion (default: 7200) |

### S3 script runner — any Python script on GPU

Upload any self-contained Python script to S3, run it on a GPU node, and get the results printed back to your terminal when it completes. **AWS S3 is mandatory** — `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` must all be set.

```bash
# compute-examples/python-gpu-workloads/
python3 test-batch-2.py my-script.py
```
```powershell
# compute-examples/python-gpu-workloads/
python test-batch-2.py my-script.py
```

What happens:
1. `my-script.py` is uploaded to `s3://<S3_BUCKET>/batch-scripts/my-script.py`
2. A BATCH job is submitted — the container downloads the script from S3 and runs it
3. stdout + stderr are captured and uploaded to `s3://<S3_BUCKET>/batch-results/my-script-<run-id>.txt`
4. On completion the results are downloaded and printed to your local terminal

| Flag | Description |
|------|-------------|
| `--job-file PATH` | Use a custom job JSON file (default: `job-batch-2.json`) |
| `--timeout SECONDS` | Max seconds to wait for completion (default: 7200) |

---

### Command-line options (persistent scripts)

| Flag | Description |
|------|-------------|
| `--job-file PATH` | Use a custom job JSON file instead of the default |
| `--private-key PATH` | Path to SSH private key (default: `dispersed-key`) |
| `--no-stop` | Keep the job running after the benchmark finishes |

---

## Optional — S3 results upload

If `S3_BUCKET` is set in `.env`, each script automatically uploads the full benchmark output as a text file to S3 after the run completes:

```
s3://<S3_BUCKET>/results/workload-<N>/<timestamp>_<gpu>_<job-id>.txt
```

Add to `.env`:

```bash
S3_BUCKET=my-results-bucket
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

The upload uses `boto3` (pre-installed in the image via `requirements.txt`). If the upload fails, a warning is printed and the script exits cleanly.

---

## Optional — S3 data sync at startup

If `S3_BUCKET` is set, the container entrypoint also syncs that bucket to a local directory (`/mnt/s3` by default) when it starts, using `aws s3 sync`. This makes your datasets or model weights available on the node before your workload runs.

```bash
S3_BUCKET=my-dataset-bucket
S3_MOUNT_PATH=/mnt/s3           # local destination inside the container
S3_SYNC_OPTS=--exclude "*.tmp"  # optional extra flags
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

---

## Optional — Custom init script

Run arbitrary setup commands inside the container before your workload starts — without rebuilding the image:

```bash
INIT_SCRIPT="pip install transformers && huggingface-cli download gpt2"
```

The script runs as `duser` after the S3 sync but before the job becomes available for SSH.

---

## File reference

### `dispersed.py`

Reusable Python wrapper around the Dispersed REST API. Handles HMAC-SHA256 request signing. Imported by all test scripts. Can also be used as a CLI:

```bash
# macOS / Linux
source .env && python3 dispersed.py list-jobs --filter-status RUNNING
source .env && python3 dispersed.py get-job-runs <JOB_ID> --filter-status RUNNING
source .env && python3 dispersed.py stop-job <JOB_ID>
```
```powershell
# Windows (PowerShell) — load .env first, then:
python dispersed.py list-jobs --filter-status RUNNING
python dispersed.py get-job-runs <JOB_ID> --filter-status RUNNING
python dispersed.py stop-job <JOB_ID>
```

### `job-batch-1.json`

Job spec for the batch benchmark. Uses `"task": "BATCH"` — the container exits when the benchmark finishes and the job is marked `COMPLETED` or `FAILED`. Credential fields and S3 env vars are empty and injected by `test-batch-1.py` at runtime.

### `job-gpu-workload-*.json`

Job specification files submitted to the Dispersed API. Credential fields (`image`, `tag`, `host`, `user`, `secret`, `sshkey`) are empty strings — the scripts overlay values from `.env` at runtime. Never put credentials in these files.

Key fields:

| Field | Description |
|-------|-------------|
| `gpu_count` | Number of GPUs requested (1 for all workloads) |
| `min_vram_gb` | Minimum VRAM in GB (set on workloads 2–4) |
| `min_storage_gb` | Minimum disk space in GB |
| `max_timeout_assign_ms` | Time to wait for a node to be assigned (ms) |
| `max_timeout_start_ms` | Time for the container to become healthy (ms) |

`allowed_ips` is set to `0.0.0.0/0` for all persistent job specs — SSH access is gated by `authorized_keys`, so the open IP range is intentional for ephemeral demo nodes. Restrict this to your own IP in production workloads.

### `docker/Dockerfile`

Extends `dispersednetwork/pytorch-pytorch:2.7.1-cuda12.8-cudnn9-runtime` (CUDA 12.8, PyTorch 2.7.1, openssh-server, duser account). Installs Python packages from `requirements.txt` and sets `entrypoint.sh` as the container entrypoint. Used by persistent workloads 1–4.

### `docker/entrypoint.sh`

Runs as `duser` on container startup:
1. If `SSH_PUBKEY` is set → regenerates SSH host keys, starts `sshd`, writes `authorized_keys`
2. If `S3_BUCKET` is set → runs `aws s3 sync s3://<S3_BUCKET> <S3_MOUNT_PATH>`
3. If `INIT_SCRIPT` is set → runs it with `bash -c`
4. Waits indefinitely (keeping `sshd` alive)

### `docker/Dockerfile.batch`

Same base image as `Dockerfile` but uses `entrypoint-batch.sh` and bakes `batch-benchmark.py` into `/app/benchmark.py`. No SSH server. Used by `test-batch-1.py`.

### `docker/entrypoint-batch.sh`

Runs `python3 /app/benchmark.py` and exits with its exit code. The Dispersed platform marks the job `COMPLETED` on exit 0 or `FAILED` on non-zero.

### `docker/batch-benchmark.py`

Self-contained GPU benchmark (no external imports beyond PyTorch and boto3). Runs FP16 matmul, memory bandwidth, and MLP forward pass benchmarks, prints results to stdout, and if `S3_BUCKET` is set uploads a JSON results file to `s3://<S3_BUCKET>/batch-results/<timestamp>-benchmark.json`.

### `docker/Dockerfile.s3batch`

Generic batch runner image — no workload baked in. Copies only `entrypoint-s3batch.sh`. Used by `test-batch-2.py`.

### `docker/entrypoint-s3batch.sh`

Downloads `s3://<S3_BUCKET>/<BATCH_SCRIPT_KEY>` to `/tmp/batch-script.py`, runs it with `python3`, captures all output via `tee`, uploads the output to `s3://<S3_BUCKET>/<BATCH_RESULTS_KEY>`, then exits with the script's exit code. Mandatory env vars: `S3_BUCKET`, `BATCH_SCRIPT_KEY`, `BATCH_RESULTS_KEY`, AWS credentials.

### `job-batch-2.json`

Job spec for the S3 script runner. `"task": "BATCH"`. Env slots for `S3_BUCKET`, `BATCH_SCRIPT_KEY`, `BATCH_RESULTS_KEY`, and AWS credentials — all injected by `test-batch-2.py` at runtime. AWS credentials are mandatory for this workflow.

### `docker/requirements.txt`

Python packages pip-installed into the image at build time. Edit this file and rebuild to add packages permanently.

### `.env.example`

Template for the `.env` file. Copy to `.env` and fill in all values. Never commit `.env`.
