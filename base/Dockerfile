FROM ubuntu:22.04
EXPOSE 22
RUN DEBIAN_FRONTEND=noninteractive apt update && apt install -y openssh-server sudo
RUN DEBIAN_FRONTEND=noninteractive apt autoremove -y &&  rm -rf /var/cache/apt/archives /var/lib/apt/lists

RUN mkdir /var/run/sshd
COPY --chown=root:root --chmod=700 10-sshd /etc/sudoers.d/10-ssh

RUN mkdir -p /opt/dispersedworker/
WORKDIR /opt/dispersedworker/
RUN groupadd -r duser; useradd -r -g duser -d /opt/dispersedworker/ duser -s /bin/bash; chown -R duser:duser /opt/dispersedworker/; cd /opt/dispersedworker/

# delete ssh host keys so they can be generated at runtime
RUN rm -v /etc/ssh/ssh_host_*

COPY --chown=root:root --chmod=755 entrypoint.sh /opt/dispersedworker/entrypoint.sh
USER duser

ENTRYPOINT ["/opt/dispersedworker/entrypoint.sh"]
