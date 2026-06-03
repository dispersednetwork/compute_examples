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
echo "I'm $(whoami) and I'm here inside a container"

# wait until everything has exited then do likewise.
wait -n
exit $?
