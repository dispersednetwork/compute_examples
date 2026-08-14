# Compute Examples

Examples and Docker images for running workloads on [Dispersed Compute](https://dispersed.com/).

## Docker images

| Image | Description | README |
|-------|-------------|--------|
| `docker-images/base/` | Minimal SSH server base image (`duser` account) | [README](docker-images/base/README.md) |
| `docker-images/comfyui/` | Extensible ComfyUI image with model/extension/workflow volume mounts | [README](docker-images/comfyui/README.md) |
| `docker-images/unsloth/` | Unsloth LLM fine-tuning image adapted for Dispersed (`SSH_PUBKEY` passthrough) | [README](docker-images/unsloth/README.md) |
| `docker-images/llama.cpp/` | Llama.cpp images adapted for Dispersed (`SSH_PUBKEY` passthrough) | [README](docker-images/llama.cpp/README.md) |

## Compute examples

| Example | Description | README |
|---------|-------------|--------|
| `compute-examples/python-gpu-workloads/` | GPU benchmark scripts and batch job runners — persistent SSH, baked-in batch, and S3 script runner modes | [README](compute-examples/python-gpu-workloads/README.md) |
