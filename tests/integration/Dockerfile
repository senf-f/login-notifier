FROM debian:12
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends systemd systemd-sysv python3 openssh-server openssh-client sshpass \
 && rm -rf /var/lib/apt/lists/* \
 && echo 'root:test' | chpasswd && useradd -m alice && echo 'alice:test' | chpasswd \
 && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
