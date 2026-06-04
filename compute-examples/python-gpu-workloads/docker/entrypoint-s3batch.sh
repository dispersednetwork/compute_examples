#!/bin/bash
set -euo pipefail

if [[ -z "${S3_BUCKET:-}" ]]; then
    echo "ERROR: S3_BUCKET is not set" >&2
    exit 1
fi

if [[ -z "${BATCH_SCRIPT_KEY:-}" ]]; then
    echo "ERROR: BATCH_SCRIPT_KEY is not set" >&2
    exit 1
fi

echo "Downloading s3://${S3_BUCKET}/${BATCH_SCRIPT_KEY} …"
aws s3 cp "s3://${S3_BUCKET}/${BATCH_SCRIPT_KEY}" /tmp/batch-script.py

echo "=== Running $(basename ${BATCH_SCRIPT_KEY}) ==="
set +e
python3 /tmp/batch-script.py 2>&1 | tee /tmp/output.txt
SCRIPT_EXIT=${PIPESTATUS[0]}
set -e

RESULTS_KEY="${BATCH_RESULTS_KEY:-batch-results/$(basename ${BATCH_SCRIPT_KEY} .py)-$(date +%Y%m%d-%H%M%S).txt}"
echo "Uploading results to s3://${S3_BUCKET}/${RESULTS_KEY} …"
aws s3 cp /tmp/output.txt "s3://${S3_BUCKET}/${RESULTS_KEY}" \
    && echo "Results uploaded." \
    || echo "WARNING: results upload failed" >&2

exit ${SCRIPT_EXIT}
