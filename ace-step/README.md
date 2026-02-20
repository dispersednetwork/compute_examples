# ACE-Step 1.5 Docker Container

Docker container for [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5), an open-source music generation model that runs locally.

## Features

- Local music generation (text-to-music, audio covers, repaint, track separation)
- Gradio web UI with auto model download
- SSH access
- Optional authentication

## Quick Start

```bash
docker run -d \
  --name ace-step \
  -p 7860:7860 \
  -p 22:22 \
  -e ACESTEPUSER=user \
  -e ACESTEPPASSWORD=password \
  -e SSH_PUBKEY="<public key>"
  dispersednetwork/acestep:latest
```

Access the UI at `http://localhost:7860`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SSH_PUBKEY` | SSH public key for container access |
| `ACESTEPUSER` | Username for web UI (optional) |
| `ACESTEPPASSWORD` | Password for web UI (optional) |

## GPU Support

For GPU acceleration, use NVIDIA Docker runtime:

```bash
docker run --runtime=nvidia ...
```

## Building

```bash
docker build -t dispersednetwork/ace-step:latest .
```
