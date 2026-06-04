import argparse
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlencode, parse_qs

import requests

# Configuration
# RECOMMENDED: Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
# ALTERNATIVE: Use environment variables (less secure, but better than hardcoding)
PUBLIC_KEY = os.environ.get("ZER_PUBLIC_KEY", "")
SECRET_KEY = os.environ.get("ZER_SECRET_KEY", "")
BASE_URL = os.environ.get("ZER_API_BASE_URL", "https://api.compute.x.io")


def canonicalize_json(value: Any) -> Any:
    """
    Recursively sorts object keys for canonical JSON serialization.
    Produces deterministic output regardless of original key order.

    Args:
        value: Any JSON-serializable value

    Returns:
        The value with all nested object keys sorted alphabetically
    """
    if isinstance(value, dict):
        return {k: canonicalize_json(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [canonicalize_json(item) for item in value]
    return value


def canonicalize_query_string(query_string: str) -> str:
    """
    Canonicalizes a query string by sorting keys and values alphabetically.

    Args:
        query_string: Raw query string without leading '?'

    Returns:
        Sorted, URL-encoded query string
    """
    if not query_string:
        return ""

    # Parse query string (handles duplicate keys)
    parsed = parse_qs(query_string, keep_blank_values=True)

    # Sort keys, and for each key sort its values
    sorted_items = []
    for key in sorted(parsed.keys()):
        for value in sorted(parsed[key]):
            sorted_items.append((key, value))

    return urlencode(sorted_items)


def generate_auth_headers(
    method: str,
    pathname: str,
    query: Optional[dict[str, str]] = None,
    body: Optional[dict[str, Any]] = None,
    ) -> dict[str, str]:
    """
    Generates HMAC authentication headers for an API request.

    Args:
        method: HTTP method (GET, POST, etc.)
        pathname: URL path without query string (e.g., /v1/jobs)
        query: Query parameters as dict
        body: Request body (will be canonicalized for JSON)

    Returns:
        Headers dict ready to use with requests library
    """
    # Generate timestamp (milliseconds) and cryptographic nonce
    timestamp = str(int(time.time() * 1000))
    nonce = secrets.token_hex(16)  # 32 hex characters (16 bytes)

    # Canonicalize query string (sort keys and values)
    query_string = urlencode(sorted((query or {}).items()))

    # Canonicalize and hash the body
    if body is not None:
        canonical_body = json.dumps(
            canonicalize_json(body),
            separators=(",", ":"),  # Compact format, no whitespace
            ensure_ascii=True,      # ASCII-safe output
            allow_nan=False,        # Reject NaN/Infinity
        )
        body_sha256 = hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()
    else:
        # Empty body: hash of empty bytes
        body_sha256 = hashlib.sha256(b"").hexdigest()

    # Build canonical string: publicKey|timestamp|nonce|METHOD|pathname|query|bodySha256
    canonical_string = "|".join([
        PUBLIC_KEY,
        timestamp,
        nonce,
        method.upper(),
        pathname,
        query_string,
        body_sha256,
    ])

    # Generate HMAC-SHA256 signature
    signature = hmac.new(
        key=SECRET_KEY.encode("utf-8"),
        msg=canonical_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return {
        "X-API-Key": PUBLIC_KEY,
        "X-Time": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def list_jobs(
    page: int = 1,
    limit: int = 20,
    sort: Optional[str] = None,
    filter_cpu_count: Optional[str] = None,
    filter_created_at: Optional[str] = None,
    filter_min_ram_gb: Optional[str] = None,
    filter_min_storage_gb: Optional[str] = None,
    filter_min_vram_gb: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_task: Optional[str] = None,
    filter_uuid: Optional[str] = None,
) -> dict[str, Any]:
    """
    Lists all jobs with pagination and filtering.

    Args:
        page: Page number (1-indexed, default: 1)
        limit: Number of results per page (1-50, default: 20)
        sort: Sort order, "created_at" or "-created_at" (descending)
        filter_cpu_count: Filter by CPU count (e.g., "1")
        filter_created_at: Filter by creation date range (e.g., "2023-01-01,2024-01-01")
        filter_min_ram_gb: Filter by RAM range (e.g., "8,16")
        filter_min_storage_gb: Filter by storage (e.g., "16")
        filter_min_vram_gb: Filter by VRAM range (e.g., "4,8")
        filter_status: Filter by status (e.g., "PENDING,RUNNING")
        filter_task: Filter by task type (e.g., "BATCH" or "PERSISTENT")
        filter_uuid: Filter by specific job UUID

    Returns:
        API response with jobs data

    Raises:
        requests.HTTPError: If the API returns an error response
    """
    pathname = "/v1/jobs"
    query = {"page": str(page), "limit": str(limit)}
    
    # Add optional query parameters
    if sort:
        query["sort"] = sort
    if filter_cpu_count:
        query["filter[cpu_count]"] = filter_cpu_count
    if filter_created_at:
        query["filter[created_at]"] = filter_created_at
    if filter_min_ram_gb:
        query["filter[min_ram_gb]"] = filter_min_ram_gb
    if filter_min_storage_gb:
        query["filter[min_storage_gb]"] = filter_min_storage_gb
    if filter_min_vram_gb:
        query["filter[min_vram_gb]"] = filter_min_vram_gb
    if filter_status:
        query["filter[status]"] = filter_status
    if filter_task:
        query["filter[task]"] = filter_task
    if filter_uuid:
        query["filter[uuid]"] = filter_uuid
    
    headers = generate_auth_headers("GET", pathname, query=query)

    response = requests.get(
        f"{BASE_URL}{pathname}",
        params=query,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def create_job(job_data: dict[str, Any]) -> dict[str, Any]:
    """
    Creates a new job.

    Args:
        job_data: Job configuration

    Returns:
        API response with created job data

    Raises:
        requests.HTTPError: If the API returns an error response
    """
    pathname = "/v1/jobs"
    headers = generate_auth_headers("POST", pathname, body=job_data)

    # Use canonical body for consistency with signature
    canonical_body = json.dumps(
        canonicalize_json(job_data),
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )

    response = requests.post(
        f"{BASE_URL}{pathname}",
        headers=headers,
        data=canonical_body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_job(job_id: str) -> dict[str, Any]:
    """
    Gets details of a specific job by ID.

    Args:
        job_id: The unique identifier of the job

    Returns:
        API response with job data

    Raises:
        requests.HTTPError: If the API returns an error response
    """
    pathname = f"/v1/jobs/{job_id}"
    headers = generate_auth_headers("GET", pathname)

    response = requests.get(
        f"{BASE_URL}{pathname}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_job_runs(job_id: str, status: Optional[str] = None) -> dict[str, Any]:
    """
    Lists job runs for a specific job, optionally filtered by status.
    The job run contains node_urls with the SSH hostname and randomised port.

    Args:
        job_id: The UUID of the parent job
        status: Optional status filter (e.g. "RUNNING")

    Returns:
        API response with job runs data (includes node_urls)

    Raises:
        requests.HTTPError: If the API returns an error response
    """
    pathname = "/v1/job-runs"
    query: dict[str, str] = {"filter[job_uuid]": job_id, "limit": "10"}
    if status:
        query["filter[status]"] = status
    headers = generate_auth_headers("GET", pathname, query=query)

    response = requests.get(
        f"{BASE_URL}{pathname}",
        params=query,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def stop_job(job_id: str) -> dict[str, Any]:
    """
    Stops a running job by ID.

    Args:
        job_id: The unique identifier of the job to stop

    Returns:
        API response confirming job stop

    Raises:
        requests.HTTPError: If the API returns an error response
    """
    pathname = f"/v1/jobs/{job_id}/cancel"
    body = {"reason": "Cancelled by user"}
    headers = generate_auth_headers("PUT", pathname, body=body)

    canonical_body = json.dumps(
        canonicalize_json(body),
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )

    response = requests.put(
        f"{BASE_URL}{pathname}",
        headers=headers,
        data=canonical_body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# ── Shared workload utilities ─────────────────────────────────────────────────

POLL_INTERVAL = 15
MAX_WAIT      = 600
SSH_TIMEOUT   = 120
SSH_USER      = "duser"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def ssh_cmd(host: str, port: int, key: str) -> list[str]:
    return [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        "-i", key,
        "-p", str(port),
        f"{SSH_USER}@{host}",
    ]


def ssh_exec_script(host: str, port: int, key: str, script: str) -> str:
    """Send a Python script over stdin to python on the remote host. Returns captured output."""
    cmd = ssh_cmd(host, port, key) + ["/opt/conda/bin/python3", "-u"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    proc.stdin.write(script)
    proc.stdin.close()
    lines = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    proc.wait()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return "".join(lines)


def ssh_capture(host: str, port: int, key: str, remote_cmd: str) -> str:
    """Run a shell command over SSH and return stdout as a string."""
    result = subprocess.run(
        ssh_cmd(host, port, key) + [remote_cmd],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()


def upload_results_to_s3(output: str, job_id: str, gpu_name: str, workload: str) -> None:
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        return
    try:
        import boto3
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        safe_gpu = gpu_name.replace(" ", "-").replace("/", "-")
        key = f"results/{workload}/{ts}_{safe_gpu}_{job_id}.txt"
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=output.encode())
        log(f"Results uploaded to s3://{bucket}/{key}")
    except Exception as e:
        log(f"WARNING: S3 upload failed: {e}")


def main():
    """
    Main function to parse command-line arguments and execute appropriate actions.
    """
    parser = argparse.ArgumentParser(
        description="Dispersed Job Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Add subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # list-jobs command
    list_parser = subparsers.add_parser("list-jobs", help="List all jobs with filtering and sorting")
    list_parser.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    list_parser.add_argument("--limit", type=int, default=20, help="Results per page, 1-50 (default: 20)")
    list_parser.add_argument("--sort", type=str, help="Sort order: 'created_at' (ascending) or '-created_at' (descending)")
    list_parser.add_argument("--filter-cpu-count", type=str, help="Filter by CPU count (e.g., '1')")
    list_parser.add_argument("--filter-created-at", type=str, help="Filter by creation date range (e.g., '2023-01-01,2024-01-01')")
    list_parser.add_argument("--filter-min-ram-gb", type=str, help="Filter by RAM range in GB (e.g., '8,16')")
    list_parser.add_argument("--filter-min-storage-gb", type=str, help="Filter by minimum storage in GB (e.g., '16')")
    list_parser.add_argument("--filter-min-vram-gb", type=str, help="Filter by VRAM range in GB (e.g., '4,8')")
    list_parser.add_argument("--filter-status", type=str, help="Filter by status (e.g., 'PENDING,RUNNING')")
    list_parser.add_argument("--filter-task", type=str, help="Filter by task type (e.g., 'BATCH' or 'PERSISTENT')")
    list_parser.add_argument("--filter-uuid", type=str, help="Filter by specific job UUID")
    
    # create-job command
    create_parser = subparsers.add_parser("create-job", help="Create a new job")
    create_parser.add_argument("--job-file", type=str, help="Path to JSON file containing job data")
    
    # get-job command
    get_parser = subparsers.add_parser("get-job", help="Get details of a specific job")
    get_parser.add_argument("job_id", type=str, help="Job ID to retrieve")

    # get-job-runs command
    runs_parser = subparsers.add_parser("get-job-runs", help="List runs for a specific job (includes SSH connection info)")
    runs_parser.add_argument("job_id", type=str, help="Job ID to list runs for")
    runs_parser.add_argument("--filter-status", type=str, help="Filter by status (e.g. 'RUNNING')")

    # stop-job command
    stop_parser = subparsers.add_parser("stop-job", help="Stop a running job")
    stop_parser.add_argument("job_id", type=str, help="Job ID to stop")
    
    args = parser.parse_args()
    
    # If no command is provided, show help
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        # Execute the appropriate function based on the command
        if args.command == "list-jobs":
            result = list_jobs(
                page=args.page,
                limit=args.limit,
                sort=args.sort,
                filter_cpu_count=args.filter_cpu_count,
                filter_created_at=args.filter_created_at,
                filter_min_ram_gb=args.filter_min_ram_gb,
                filter_min_storage_gb=args.filter_min_storage_gb,
                filter_min_vram_gb=args.filter_min_vram_gb,
                filter_status=args.filter_status,
                filter_task=args.filter_task,
                filter_uuid=args.filter_uuid,
            )
            print(json.dumps(result, indent=2))
            
        elif args.command == "create-job":
            if args.job_file:
                # Load job data from file
                with open(args.job_file, 'r') as f:
                    job_data = json.load(f)
            result = create_job(job_data)
            print(json.dumps(result, indent=2))
            
        elif args.command == "get-job":
            result = get_job(args.job_id)
            print(json.dumps(result, indent=2))

        elif args.command == "get-job-runs":
            result = get_job_runs(args.job_id, status=args.filter_status)
            print(json.dumps(result, indent=2))

        elif args.command == "stop-job":
            result = stop_job(args.job_id)
            print(json.dumps(result, indent=2))
            
    except requests.HTTPError as e:
        print(f"API Error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"File Error: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()