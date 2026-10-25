ARG BASE=debian:12
FROM ${BASE}
# EOL debian:11 mirrors are partly gone; use the snapshot sources the image ships commented out.
RUN if grep -q bullseye /etc/apt/sources.list 2>/dev/null; then \
      sed -i -e '/^deb /d' -e 's/^# deb /deb /' /etc/apt/sources.list \
      && echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99snapshot; fi \
 && apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends systemd systemd-sysv python3 openssh-server openssh-client sshpass \
 && rm -rf /var/lib/apt/lists/* \
 && echo 'root:test' | chpasswd && useradd -m alice && echo 'alice:test' | chpasswd \
 && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
