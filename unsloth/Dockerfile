FROM unsloth/unsloth:stable

USER root

COPY entrypoint-wrapper.sh .
RUN chmod 0755 ./entrypoint-wrapper.sh

USER unsloth:runtimeusers

ENTRYPOINT ["./entrypoint-wrapper.sh"]
