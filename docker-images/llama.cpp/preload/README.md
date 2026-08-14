# Llama.cpp

An example to show how to add SSH for dispersed to a base image.

The default user is 'duser'

You can provide a basic auth password via the env var `BASIC_AUTH`

With this version you can preload models by putting them in the `models` directory, this helps speed startup see https://huggingface.co/ggml-org for models.
Remember to set the env var `LLAMA_ARG_MODELS_DIR` to `/opt/dispersedworker/models/` so llama.cpp knows about them.