#!/bin/bash

if [[ -z "${SSH_PUBKEY}" ]]; then
	echo "No SSH_PUBKEY set, not starting sshd"
else
	echo "Generating host keys"
	 /usr/bin/sudo /usr/sbin/dpkg-reconfigure openssh-server > /dev/null 2>&1
	echo "Starting sshd"
	/usr/bin/sudo /usr/sbin/sshd -D &
fi

if [[ -z "${SSH_PUBKEY}" ]]; then
	echo "No SSH_PUBKEY set, not creating authorized_keys"
else
	mkdir -p ~/.ssh
	echo -e $SSH_PUBKEY > ~/.ssh/authorized_keys
	chmod 700 ~/.ssh
	chmod 600 ~/.ssh/authorized_keys
fi

if [[ -z "${BASIC_AUTH}" ]]; then
	echo "No BASIC_AUTH set, not password protecting nginx"
else
	echo "Writing basic auth"
	echo -e $BASIC_AUTH > /etc/nginx/htpasswd
	TEMP_SED=$(sed 's/^##UNCOMMENT//' /etc/nginx/nginx.conf)
	echo "$TEMP_SED" > /etc/nginx/nginx.conf
fi

echo "Starting nginx"
/usr/bin/sudo /usr/sbin/nginx &


python3 /opt/zerworker/ComfyUI/main.py --listen


wait -n
exit $?
