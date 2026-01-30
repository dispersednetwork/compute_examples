#!/bin/bash
set -e

# Optional: log so we know it ran
echo "[zerworker] entrypoint wrapper starting"

# SSH key for zeruser
if [[ -n "${SSH_KEY}" ]]; then
    sudo mkdir -p /opt/zerworker/.ssh
    echo "${SSH_KEY}" | sudo tee /opt/zerworker/.ssh/authorized_keys > /dev/null
    sudo chmod 700 /opt/zerworker/.ssh
    sudo chmod 600 /opt/zerworker/.ssh/authorized_keys
    sudo chown -R zeruser:zeruser /opt/zerworker/.ssh
fi

echo "[zerworker] handing off to unsloth entrypoint"

# CRITICAL LINE
exec /usr/local/bin/entrypoint.sh
