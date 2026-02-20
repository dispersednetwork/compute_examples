FROM ubuntu:24.04

EXPOSE 22

RUN apt-get update && \
	apt-get upgrade -y && \
	apt-get install -y --no-install-recommends \
	ca-certificates \
	git \
	gcc \
	g++ \
	build-essential \
	openssh-server \
	sudo && \
	rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd
COPY --chown=root:root --chmod=700 10-sshd /etc/sudoers.d/10-ssh

COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/

RUN git clone https://github.com/ace-step/ACE-Step-1.5.git

WORKDIR /ACE-Step-1.5
RUN groupadd -r duser; useradd -r -g duser -d /ACE-Step-1.5 duser -s /bin/bash; chown -R duser:duser /ACE-Step-1.5; cd /ACE-Step-1.5

USER duser

RUN uv sync

COPY entrypoint.sh .

ENTRYPOINT ["/ACE-Step-1.5/entrypoint.sh"]
