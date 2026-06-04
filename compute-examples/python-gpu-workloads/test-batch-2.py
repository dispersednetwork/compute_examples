"""
test-batch-2.py — Run any Python script as a BATCH job on Dispersed GPU via S3

Uploads a local Python script to S3, submits a BATCH job that downloads and
runs it, then fetches and prints the results when the job completes.

AWS S3 is mandatory — both script delivery and results collection go through S3.

Required env vars:
  ZER_PUBLIC_KEY, ZER_SECRET_KEY
  S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

Usage:
  set -a && source .env && set +a
  source venv/bin/activate
  python3 test-batch-2.py my-script.py
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dispersed as api
from dispersed import POLL_INTERVAL, log, die

SCRIPT_DIR      = Path(__file__).parent
DEFAULT_JOB     = SCRIPT_DIR / "job-batch-2.json"
DEFAULT_TIMEOUT = 7200

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}

REQUIRED_ENV = [
    "ZER_PUBLIC_KEY",
    "ZER_SECRET_KEY",
    "S3_BUCKET",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a Python script to S3 and run it as a BATCH job on Dispersed GPU"
    )
    parser.add_argument("script", help="Local Python script to run on the GPU node")
    parser.add_argument("--job-file", default=str(DEFAULT_JOB))
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="Seconds to wait for completion (default: 7200)")
    args = parser.parse_args()

    for var in REQUIRED_ENV:
        if not os.environ.get(var):
            die(f"{var} is not set (required)")

    script_path = Path(args.script)
    if not script_path.exists():
        die(f"Script not found: {script_path}")

    job_file = Path(args.job_file)
    if not job_file.exists():
        die(f"Job file not found: {job_file}")

    import boto3
    s3 = boto3.client("s3")
    s3_bucket   = os.environ["S3_BUCKET"]
    script_key  = f"batch-scripts/{script_path.name}"
    run_id      = str(uuid.uuid4())[:8]
    results_key = f"batch-results/{script_path.stem}-{run_id}.txt"

    log(f"Uploading {script_path.name} → s3://{s3_bucket}/{script_key}")
    s3.upload_file(str(script_path), s3_bucket, script_key)

    with open(job_file) as f:
        job_data = json.load(f)

    params    = job_data.get("parameters", {}).get("parameters", {})
    env_block = params.setdefault("env", {})

    for env_var, field in [
        ("S3_BATCH_GPU_IMAGE",         "image"),
        ("S3_BATCH_GPU_IMAGE_TAG",     "tag"),
        ("DISPERSED_REGISTRY_HOST",    "host"),
        ("DISPERSED_REGISTRY_USER",    "user"),
        ("DISPERSED_REGISTRY_SECRET",  "secret"),
    ]:
        val = os.environ.get(env_var)
        if not val and env_var == "S3_BATCH_GPU_IMAGE":
            val = os.environ.get("BATCH_GPU_IMAGE") or os.environ.get("GPU_IMAGE")
        if not val and env_var == "S3_BATCH_GPU_IMAGE_TAG":
            val = os.environ.get("BATCH_GPU_IMAGE_TAG") or os.environ.get("GPU_IMAGE_TAG")
        if val:
            params[field] = val

    env_block["S3_BUCKET"]        = s3_bucket
    env_block["BATCH_SCRIPT_KEY"] = script_key
    env_block["BATCH_RESULTS_KEY"] = results_key
    env_block["AWS_ACCESS_KEY_ID"]     = os.environ["AWS_ACCESS_KEY_ID"]
    env_block["AWS_SECRET_ACCESS_KEY"] = os.environ["AWS_SECRET_ACCESS_KEY"]
    env_block["AWS_DEFAULT_REGION"]    = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    log(f"Submitting BATCH job for {script_path.name} …")
    response = api.create_job(job_data)
    print(json.dumps(response, indent=2))

    job_id = response.get("uuid") or response.get("data", {}).get("uuid")
    if not job_id:
        die(f"Could not extract job UUID from response: {response}")
    log(f"Job created: {job_id}")
    log(f"Results will appear at: s3://{s3_bucket}/{results_key}")

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

    if status not in TERMINAL_STATES:
        log(f"Timed out after {args.timeout}s — job still in status: {status}")
        log(f"Cancel manually:  python3 dispersed.py stop-job {job_id}")
        sys.exit(2)

    if status != "COMPLETED":
        log(f"Job ended with status: {status}")
        sys.exit(1)

    log("Job completed. Fetching results …")
    try:
        obj = s3.get_object(Bucket=s3_bucket, Key=results_key)
        output = obj["Body"].read().decode("utf-8", errors="replace")
        print()
        print("=" * 60)
        print(f"Results: s3://{s3_bucket}/{results_key}")
        print("=" * 60)
        print(output)
    except Exception as e:
        log(f"WARNING: could not fetch results from S3: {e}")
        log(f"Results may still be available at: s3://{s3_bucket}/{results_key}")


if __name__ == "__main__":
    main()
