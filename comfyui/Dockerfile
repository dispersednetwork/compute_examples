FROM debian:bookworm
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y bash sudo git pip python3 openssh-server jq ffmpeg python3-opencv nginx
RUN DEBIAN_FRONTEND=noninteractive  apt autoremove -y &&  rm -rf /var/cache/apt/archives /var/lib/apt/lists

RUN mkdir -p /var/run/sshd && chown root:root /var/run/sshd && chmod 0755 /var/run/sshd
# delete ssh host keys so they can be generated at runtime
RUN rm -v /etc/ssh/ssh_host_*

RUN mkdir -p /opt/zerworker/
WORKDIR /opt/zerworker/

RUN groupadd -r zeruser; useradd -r -g zeruser -d /opt/zerworker zeruser -s /bin/bash; chown -R zeruser:zeruser /opt/zerworker; cd /opt/zerworker
COPY --chown=root:root --chmod=700 10-sshd /etc/sudoers.d/10-ssh
RUN touch /etc/nginx/htpasswd && chown root:zeruser /etc/nginx/htpasswd && chmod 775 /etc/nginx/htpasswd

USER zeruser

# Pull repo
RUN cd /opt/zerworker && git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
WORKDIR /opt/zerworker/ComfyUI
# copy models and extensions
COPY --chown=zeruser:zeruser models/ /opt/zerworker/ComfyUI/models/
COPY --chown=zeruser:zeruser extensions/ /opt/zerworker/ComfyUI/custom_nodes/
RUN mkdir -p /opt/zerworker/ComfyUI/user/default/workflows/
COPY --chown=zeruser:zeruser workflows/ /opt/zerworker/ComfyUI/user/default/workflows/

RUN python3 -m pip config set global.break-system-packages true && pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu128 && pip install -r ./requirements.txt && pip install gitpython typing-extensions toml uv chardet lark diffusers ftfy sageattention numpy==1.26.4 accelerate gguf onnx onnxruntime imageio-ffmpeg pyloudnorm color-matcher requirements-parser && pip cache purge

COPY --chown=root:root --chmod=755 entrypoint.sh /opt/zerworker/entrypoint.sh
COPY --chown=root:zeruser --chmod=775 nginx.conf /etc/nginx/nginx.conf
# Exposing port 5000
EXPOSE 5000/tcp
EXPOSE 22/tcp

# Launch at startup
CMD [ "/opt/zerworker/entrypoint.sh" ]