"""
workload_runner.py

Shared lifecycle for persistent (SSH-based) GPU workload scripts.
Import run_persistent_workload and pass in the benchmark code string.
"""

import argparse
import atexit
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Union

import dispersed as api
from dispersed import (
    POLL_INTERVAL, MAX_WAIT, SSH_TIMEOUT, SSH_USER,
    log, die, ssh_cmd, ssh_exec_script, ssh_capture, upload_results_to_s3,
)

_DOCKER_CREDENTIAL_FIELDS = [
    ("GPU_IMAGE",                 "image"),
    ("GPU_IMAGE_TAG",             "tag"),
    ("DISPERSED_REGISTRY_HOST",   "host"),
    ("DISPERSED_REGISTRY_USER",   "user"),
    ("DISPERSED_REGISTRY_SECRET", "secret"),
    ("DISPERSED_SSH_PUBKEY",      "sshkey"),
]

_DEFAULT_KEY = os.environ.get("DISPERSED_SSH_KEY") or str(Path(__file__).parent / "dispersed-key")


def run_persistent_workload(
    benchmark_code: str,
    workload_name: str,
    default_job: Union[str, Path],
    verify_pytorch: bool = False,
    extra_env: dict = None,
) -> None:
    """
    Full lifecycle for a persistent GPU workload:
      arg parse → validate → create job → poll → SSH → run benchmark → upload results.

    Args:
        benchmark_code:  Python source sent over SSH stdin to the remote GPU node.
        workload_name:   Label used for S3 results key (e.g. "workload-1").
        default_job:     Absolute path to the job JSON file (use Path(__file__).parent / "job-...json").
        verify_pytorch:  If True, runs a quick PyTorch+CUDA sanity check before the benchmark.
        extra_env:       Optional env vars merged into the job spec's container env block at runtime.
    """
    parser = argparse.ArgumentParser(description=f"GPU workload: {workload_name} on dispersed compute")
    parser.add_argument("--job-file",    default=str(default_job), help="Path to job JSON file")
    parser.add_argument("--no-stop",     action="store_true",      help="Don't stop the job on exit")
    parser.add_argument("--private-key", default=_DEFAULT_KEY,     help="Path to SSH private key")
    args = parser.parse_args()

    job_file     = Path(args.job_file)
    private_key  = args.private_key
    stop_on_exit = not args.no_stop

    if not job_file.exists():                die(f"Job file not found: {job_file}")
    if not os.environ.get("ZER_PUBLIC_KEY"): die("ZER_PUBLIC_KEY is not set")
    if not os.environ.get("ZER_SECRET_KEY"): die("ZER_SECRET_KEY is not set")
    if not Path(private_key).exists():       die(f"Private key not found: {private_key}")

    log(f"Creating job from {job_file} …")
    with open(job_file) as f:
        job_data = json.load(f)

    params = job_data.get("parameters", {}).get("parameters", {})
    for env_var, field in _DOCKER_CREDENTIAL_FIELDS:
        val = os.environ.get(env_var)
        if val:
            params[field] = val

    if extra_env:
        params.setdefault("env", {}).update(extra_env)

    response = api.create_job(job_data)
    print(json.dumps(response, indent=2))

    job_id = response.get("uuid") or response.get("data", {}).get("uuid")
    if not job_id:
        die(f"Could not extract job UUID from response: {response}")
    log(f"Job created: {job_id}")

    def cleanup():
        if stop_on_exit:
            log(f"Stopping job {job_id} …")
            try:
                api.stop_job(job_id)
            except Exception as e:
                print(f"  Warning: stop_job failed: {e}", file=sys.stderr)

    atexit.register(cleanup)

    log(f"Waiting for job to reach RUNNING (timeout: {MAX_WAIT}s) …")
    elapsed = 0
    status  = "UNKNOWN"
    while elapsed < MAX_WAIT:
        try:
            status = api.get_job(job_id).get("status", "UNKNOWN")
        except Exception as e:
            log(f"  Warning: get_job failed: {e}")
        log(f"  Job status: {status}")
        if status == "RUNNING":
            break
        if status in ("FAILED", "CANCELLED", "COMPLETED"):
            die(f"Job ended unexpectedly: {status}")
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    if status != "RUNNING":
        die("Timed out waiting for job to reach RUNNING state")

    log("Waiting for job-run SSH connection info …")
    ssh_host = ""
    ssh_port = 0
    while elapsed < MAX_WAIT:
        try:
            runs = api.get_job_runs(job_id, status="RUNNING").get("data", [])
            if runs:
                ssh_entry = next(
                    (u for u in runs[0].get("node_urls", []) if u.get("description") == "ssh"),
                    None,
                )
                if ssh_entry:
                    ssh_host = ssh_entry["hostname"]
                    ssh_port = int(ssh_entry["port"])
                    break
                log("  Job-run RUNNING but node_urls not ready yet …")
            else:
                log("  No RUNNING job-run yet …")
        except Exception as e:
            log(f"  Warning: get_job_runs failed: {e}")
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    if not ssh_host:
        die("Timed out waiting for job-run to expose SSH connection info")

    log(f"Job is RUNNING. SSH: {SSH_USER}@{ssh_host}:{ssh_port}")

    log(f"Waiting for SSH on {ssh_host}:{ssh_port} …")
    ssh_wait = 0
    while True:
        r = subprocess.run(
            ssh_cmd(ssh_host, ssh_port, private_key) + ["true"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            break
        if ssh_wait >= SSH_TIMEOUT:
            die(f"SSH not available after {SSH_TIMEOUT}s")
        time.sleep(5)
        ssh_wait += 5
    log("SSH is ready.")

    gpu_name = ssh_capture(
        ssh_host, ssh_port, private_key,
        "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo unknown",
    ) or "unknown"

    if verify_pytorch:
        log("Verifying PyTorch + CUDA on remote host …")
        ssh_exec_script(
            ssh_host, ssh_port, private_key,
            "import torch; print('PyTorch', torch.__version__, '| CUDA available:', torch.cuda.is_available())",
        )

    log("Running benchmark …")
    bench_start  = time.monotonic()
    bench_output = ssh_exec_script(ssh_host, ssh_port, private_key, benchmark_code)
    bench_elapsed = int(time.monotonic() - bench_start)

    log("Benchmark complete.")
    log("━" * 64)
    log(f"  GPU                       : {gpu_name}")
    log(f"  Job ID                    : {job_id}")
    log(f"  Wall time (incl. startup) : {bench_elapsed}s")
    log("━" * 64)

    upload_results_to_s3(bench_output, job_id, gpu_name, workload_name)
