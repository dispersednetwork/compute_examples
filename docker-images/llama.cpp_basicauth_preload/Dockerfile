FROM ghcr.io/ggml-org/llama.cpp:server-cuda
EXPOSE 22
EXPOSE 5000/tcp
RUN DEBIAN_FRONTEND=noninteractive apt update && apt install -y openssh-server sudo nginx
RUN DEBIAN_FRONTEND=noninteractive apt autoremove -y &&  rm -rf /var/cache/apt/archives /var/lib/apt/lists

RUN mkdir /var/run/sshd
COPY --chown=root:root --chmod=700 10-sshd /etc/sudoers.d/10-ssh

RUN mkdir -p /opt/dispersedworker/
WORKDIR /app
RUN groupadd -r duser; useradd -r -g duser -d /opt/dispersedworker/ duser -s /bin/bash; chown -R duser:duser /opt/dispersedworker/; cd /opt/dispersedworker/
RUN touch /etc/nginx/htpasswd && chown root:duser /etc/nginx/htpasswd && chmod 775 /etc/nginx/htpasswd

# delete ssh host keys so they can be generated at runtime
RUN rm -v /etc/ssh/ssh_host_*

COPY --chown=root:duser --chmod=775 nginx.conf /etc/nginx/nginx.conf
COPY --chown=root:root --chmod=755 entrypoint.sh /opt/dispersedworker/entrypoint.sh

USER duser

COPY --chown=duser:duser models/ /opt/dispersedworker/models/


ENTRYPOINT ["/opt/dispersedworker/entrypoint.sh"]
