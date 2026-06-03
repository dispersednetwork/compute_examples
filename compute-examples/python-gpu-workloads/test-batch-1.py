"""
test-batch-1.py — Submit a GPU benchmark as a BATCH job on Dispersed

The workload (FP16 matmul, memory bandwidth, MLP forward pass) is baked into
the batch Docker image. This script just submits the job and polls for completion.
If S3_BUCKET is set, the benchmark uploads results to s3://<bucket>/batch-results/.

Required env vars:
  ZER_PUBLIC_KEY, ZER_SECRET_KEY

Optional env vars forwarded to the job:
  S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION

Usage:
  set -a && source .env && set +a
  source venv/bin/activate
  python3 test-batch-1.py
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dispersed as api
from dispersed import POLL_INTERVAL, log, die

SCRIPT_DIR      = Path(__file__).parent
DEFAULT_JOB     = SCRIPT_DIR / "job-batch-1.json"
DEFAULT_TIMEOUT = 7200

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}

PASSTHROUGH_ENV = [
    "S3_BUCKET",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a GPU benchmark BATCH job on Dispersed")
    parser.add_argument("--job-file", default=str(DEFAULT_JOB))
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="Seconds to wait for completion (default: 7200)")
    args = parser.parse_args()

    if not os.environ.get("ZER_PUBLIC_KEY"): die("ZER_PUBLIC_KEY is not set")
    if not os.environ.get("ZER_SECRET_KEY"): die("ZER_SECRET_KEY is not set")

    job_file = Path(args.job_file)
    if not job_file.exists():
        die(f"Job file not found: {job_file}")

    with open(job_file) as f:
        job_data = json.load(f)

    params    = job_data.get("parameters", {}).get("parameters", {})
    env_block = params.setdefault("env", {})

    for env_var, field in [
        ("BATCH_GPU_IMAGE",           "image"),
        ("BATCH_GPU_IMAGE_TAG",       "tag"),
        ("DISPERSED_REGISTRY_HOST",   "host"),
        ("DISPERSED_REGISTRY_USER",   "user"),
        ("DISPERSED_REGISTRY_SECRET", "secret"),
    ]:
        val = os.environ.get(env_var)
        if not val and env_var == "BATCH_GPU_IMAGE":
            val = os.environ.get("GPU_IMAGE")
        if not val and env_var == "BATCH_GPU_IMAGE_TAG":
            val = os.environ.get("GPU_IMAGE_TAG")
        if val:
            params[field] = val

    for key in PASSTHROUGH_ENV:
        val = os.environ.get(key)
        if val:
            env_block[key] = val

    log("Submitting BATCH job …")
    response = api.create_job(job_data)
    print(json.dumps(response, indent=2))

    job_id = response.get("uuid") or response.get("data", {}).get("uuid")
    if not job_id:
        die(f"Could not extract job UUID from response: {response}")
    log(f"Job created: {job_id}")

    log(f"Polling for completion (timeout: {args.timeout}s) …")
    elapsed = 0
    status  = "UNKNOWN"

    while elapsed < args.timeout:
        try:
            status = api.get_job(job_id).get("status", "UNKNOWN")
        except Exception as e:
            log(f"  Warning: get_job failed: {e}")
        log(f"  [{elapsed}s] Job status: {status}")
        if status in TERMINAL_STATES:
            break
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    if status == "COMPLETED":
        log("Job completed successfully.")
    elif status in TERMINAL_STATES:
        log(f"Job ended with status: {status}")
        sys.exit(1)
    else:
        log(f"Timed out after {args.timeout}s — job still in status: {status}")
        log(f"Cancel manually:  python3 dispersed.py stop-job {job_id}")
        sys.exit(2)


if __name__ == "__main__":
    main()
