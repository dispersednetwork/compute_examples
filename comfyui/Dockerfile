FROM debian:bookworm
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y bash sudo git pip python3 openssh-server jq ffmpeg python3-opencv nginx
RUN DEBIAN_FRONTEND=noninteractive  apt autoremove -y &&  rm -rf /var/cache/apt/archives /var/lib/apt/lists

RUN mkdir -p /var/run/sshd && chown root:root /var/run/sshd && chmod 0755 /var/run/sshd
# delete ssh host keys so they can be generated at runtime
RUN rm -v /etc/ssh/ssh_host_*

RUN mkdir -p /opt/dispersedworker/
WORKDIR /opt/dispersedworker/

RUN groupadd -r duser; useradd -r -g duser -d /opt/dispersedworker duser -s /bin/bash; chown -R duser:duser /opt/dispersedworker; cd /opt/dispersedworker
COPY --chown=root:root --chmod=700 10-sshd /etc/sudoers.d/10-ssh
RUN touch /etc/nginx/htpasswd && chown root:duser /etc/nginx/htpasswd && chmod 775 /etc/nginx/htpasswd

USER duser

# Pull repo
RUN cd /opt/dispersedworker && git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
WORKDIR /opt/dispersedworker/ComfyUI
# copy models and extensions
COPY --chown=duser:duser models/ /opt/dispersedworker/ComfyUI/models/
COPY --chown=duser:duser extensions/ /opt/dispersedworker/ComfyUI/custom_nodes/
RUN mkdir -p /opt/dispersedworker/ComfyUI/user/default/workflows/
COPY --chown=duser:duser workflows/ /opt/dispersedworker/ComfyUI/user/default/workflows/

RUN python3 -m pip config set global.break-system-packages true && pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu128 && pip install -r ./requirements.txt && pip install gitpython typing-extensions toml uv chardet lark diffusers ftfy sageattention numpy==1.26.4 accelerate gguf onnx onnxruntime imageio-ffmpeg pyloudnorm color-matcher requirements-parser && pip cache purge

COPY --chown=root:root --chmod=755 entrypoint.sh /opt/dispersedworker/entrypoint.sh
COPY --chown=root:duser --chmod=775 nginx.conf /etc/nginx/nginx.conf
# Exposing port 5000
EXPOSE 5000/tcp
EXPOSE 22/tcp

# Launch at startup
CMD [ "/opt/dispersedworker/entrypoint.sh" ]