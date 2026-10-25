#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "install.sh must be run as root" >&2
    exit 1
fi
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v journalctl >/dev/null || { echo "systemd/journalctl is required" >&2; exit 1; }

src=$(cd "$(dirname "$0")" && pwd)

install -d -m 755 /opt/login-notifier/login_notifier
install -m 644 "$src"/login_notifier/*.py /opt/login-notifier/login_notifier/

install -d -m 700 -o root -g root /etc/login-notifier
if [ ! -e /etc/login-notifier/config.json ]; then
    install -m 600 -o root -g root "$src/config.example.json" /etc/login-notifier/config.json
    echo "Created /etc/login-notifier/config.json - edit it with your bot token and chat ID."
else
    chown root:root /etc/login-notifier/config.json
    chmod 600 /etc/login-notifier/config.json
fi

install -m 644 "$src/systemd/login-notifier.service" /etc/systemd/system/login-notifier.service
systemctl daemon-reload

echo "Installed. Next steps:"
echo "  1. Edit /etc/login-notifier/config.json"
echo "  2. PYTHONPATH=/opt/login-notifier python3 -m login_notifier --test"
echo "  3. systemctl enable --now login-notifier"
