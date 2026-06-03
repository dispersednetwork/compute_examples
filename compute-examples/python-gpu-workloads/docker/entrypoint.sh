#!/bin/bash

if [[ -z "${SSH_PUBKEY}" ]]; then
    echo "No SSH_PUBKEY set, not starting sshd"
else
    echo "Generating host keys"
    /usr/bin/sudo /usr/sbin/dpkg-reconfigure openssh-server > /dev/null 2>&1
    echo "Starting sshd"
    /usr/bin/sudo /usr/sbin/sshd -D &

    mkdir -p ~/.ssh
    printf '%s\n' "${SSH_PUBKEY}" > ~/.ssh/authorized_keys
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys
fi

if [[ -n "${S3_BUCKET}" ]]; then
    S3_MOUNT_PATH="${S3_MOUNT_PATH:-/mnt/s3}"
    mkdir -p "${S3_MOUNT_PATH}"
    echo "Syncing s3://${S3_BUCKET} → ${S3_MOUNT_PATH}"
    AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
    AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
    AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
    aws s3 sync "s3://${S3_BUCKET}" "${S3_MOUNT_PATH}" ${S3_SYNC_OPTS} \
        && echo "  S3 sync OK" \
        || echo "  WARNING: S3 sync failed — continuing without it"
fi

if [[ -n "${INIT_SCRIPT}" ]]; then
    echo "Running INIT_SCRIPT …"
    # Intentional user escape hatch — runs arbitrary shell code supplied by the caller via env var.
    bash -c "${INIT_SCRIPT}"
fi

echo "I'm $(whoami) and I'm here inside a container"

wait -n
exit $?
