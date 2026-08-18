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

if [[ -z "${CONTAINER_ACCESS_TOKEN}" ]]; then
	echo "No CONTAINER_ACCESS_TOKEN set, not password protecting nginx"
else
	echo "Writing access token"
	AUTH_TOKEN=$(/usr/bin/printf "duser:$(openssl passwd -apr1 ${CONTAINER_ACCESS_TOKEN})")
	echo -e $AUTH_TOKEN > /etc/nginx/htpasswd
	TEMP_SED=$(sed 's/^##UNCOMMENT//' /etc/nginx/nginx.conf)
	echo "$TEMP_SED" > /etc/nginx/nginx.conf
fi

echo "Starting nginx"
/usr/bin/sudo /usr/sbin/nginx &

echo "Starting llama"
/app/llama-server

# wait until everything has exited then do likewise.
wait -n
exit $?
