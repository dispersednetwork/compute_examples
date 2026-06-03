FROM dispersednetwork/pytorch-pytorch:2.7.1-cuda12.8-cudnn9-runtime

USER root

COPY --chown=duser:duser requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY --chown=duser:duser --chmod=755 entrypoint.sh /entrypoint.sh

USER duser

ENTRYPOINT ["/entrypoint.sh"]
