# Render Compute Unsloth Example

A minimal Dockerfile and entrypoint wrapper for the official Unsloth image, adapted for use on Render Compute.

This wrapper allows the SSH key to be passed in as `SSH_PUBKEY` (used by Render Compute) instead of `SSH_KEY` (expected by Unsloth).

**SSH user:** `unsloth`

Unsloth Docker image:  
https://hub.docker.com/r/unsloth/unsloth

Unsloth GitHub:  
https://github.com/unslothai/unsloth
