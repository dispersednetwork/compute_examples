FROM otoy/zernet-base:latest AS base
FROM unsloth/unsloth:stable

USER root

COPY --from=base /etc/sudoers.d/10-ssh /etc/sudoers.d/10-ssh
RUN chmod 0440 /etc/sudoers.d/10-ssh

RUN echo "unsloth ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-unsloth \
 && chmod 0440 /etc/sudoers.d/90-unsloth

RUN mkdir -p /opt/zerworker/
WORKDIR /opt/zerworker/
RUN groupadd -r zeruser; useradd -r -g zeruser -d /opt/zerworker zeruser -s /bin/bash; chown -R zeruser:zeruser /opt/zerworker; cd /opt/zerworker

COPY entrypoint-wrapper.sh /opt/zerworker/entrypoint-wrapper.sh
RUN chmod 0755 /opt/zerworker/entrypoint-wrapper.sh

USER unsloth:runtimeusers

ENTRYPOINT ["/opt/zerworker/entrypoint-wrapper.sh"]
