# ACE-Step 1.5 Docker Container

Docker container for [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5), an open-source music generation model.

## Features

- Local music generation (text-to-music, audio covers, repaint, track separation)
- Gradio web UI with auto model download
- SSH access

## Quick Start

Launch the container with all environment vars set. See below for environment variable info. Expose ports 22/tcp and 7860/tcp.

The UI will be made available via proxy.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SSH_PUBKEY` | SSH public key for container access |
| `ACESTEPUSER` | Username for web UI |
| `ACESTEPPASSWORD` | Password for web UI |

## GPU Requirements
ACE-Step can run at multiple tiers, but it is recommended to use a GPU with at least 20GB VRAM available to avoid CPU offload.

See [ACE-Step GPU Compatibility](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/GPU_COMPATIBILITY.md) for more information.
