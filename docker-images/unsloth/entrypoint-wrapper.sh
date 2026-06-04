#!/bin/bash
set -e

# Optional: log so we know it ran
echo "[zerworker] entrypoint wrapper starting"

export SSH_KEY="${SSH_PUBKEY}"

echo "[zerworker] handing off to unsloth entrypoint"

# CRITICAL LINE
exec /usr/local/bin/entrypoint.sh
