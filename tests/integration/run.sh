#!/bin/sh
# End-to-end test: install into a systemd container, log in over SSH, check the mock Telegram API.
set -eu
cd "$(dirname "$0")/../.."
name=login-notifier-it

docker build -q -t "$name" tests/integration >/dev/null
docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw "$name" >/dev/null
trap 'docker rm -f "$name" >/dev/null' EXIT
docker cp . "$name":/src

exec docker exec -i "$name" sh -eu <<'EOF'
fail() { echo "FAIL: $*"; journalctl -u login-notifier --no-pager | tail -20; exit 1; }
msgs() { wc -l < /tmp/sent 2>/dev/null || echo 0; }
wait_for() { i=0; until eval "$1"; do i=$((i+1)); [ $i -gt 30 ] && fail "$2"; sleep 0.5; done; }
login() { sshpass -p test ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR "$1"@127.0.0.1 true; }

until systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded'; do sleep 0.5; done
systemctl start ssh
nohup python3 /src/tests/integration/mock_telegram.py /tmp/sent >/dev/null 2>&1 &

sh /src/install.sh
[ "$(stat -c '%a %U' /etc/login-notifier/config.json)" = "600 root" ] || fail "config permissions"
cat > /etc/login-notifier/config.json <<'JSON'
{"bot_token": "1:TEST", "chat_id": "42", "api_base": "http://127.0.0.1:8081", "blacklist": []}
JSON

PYTHONPATH=/opt/login-notifier python3 -m login_notifier --test || fail "--test"
wait_for '[ "$(msgs)" -eq 1 ]' "test message not delivered"
echo "ok: --test message delivered"

chmod 644 /etc/login-notifier/config.json
PYTHONPATH=/opt/login-notifier python3 -m login_notifier --test 2>/dev/null && fail "world-readable config accepted"
chmod 600 /etc/login-notifier/config.json
echo "ok: world-readable config rejected"

systemctl enable --now login-notifier
wait_for 'journalctl -u login-notifier --no-pager | grep -q "Watching journal"' "service did not start"
echo "ok: service enabled and running"

login alice
wait_for '[ "$(msgs)" -eq 2 ]' "no notification for ssh login"
tail -1 /tmp/sent | grep -q 'User: alice' || fail "message missing user"
tail -1 /tmp/sent | grep -q '127.0.0.1 (ssh, password)' || fail "message missing source ip"
tail -1 /tmp/sent | grep -q '/bot1:TEST/sendMessage' || fail "wrong API path"
sleep 2; [ "$(msgs)" -eq 2 ] || fail "duplicate notification"
echo "ok: ssh login notified once: $(tail -1 /tmp/sent)"

sed -i 's/"blacklist": \[\]/"blacklist": ["alice"]/' /etc/login-notifier/config.json
login alice; login root
wait_for '[ "$(msgs)" -eq 3 ]' "no notification for root"
tail -1 /tmp/sent | grep -q 'User: root' || fail "blacklisted user was notified"
journalctl -u login-notifier --no-pager | grep -q "Configuration reloaded" || fail "no reload logged"
echo "ok: blacklist applied without restart"

journalctl -u login-notifier -p info..info --no-pager | grep -q "Login by root" || fail "info severity"
echo "ok: logs land in journal with severity"

pid=$(systemctl show -p MainPID --value login-notifier)
kill -9 "$pid"
wait_for '[ "$(systemctl show -p MainPID --value login-notifier)" != "$pid" ] && [ "$(systemctl show -p MainPID --value login-notifier)" != 0 ]' "service did not restart"
systemctl show -p NRestarts --value login-notifier | grep -q '^1$' || fail "restart count"
echo "ok: restarted after crash"

login root
wait_for '[ "$(msgs)" -eq 4 ]' "no notification after restart"
sleep 2; [ "$(msgs)" -eq 4 ] || fail "old logins re-sent after restart"
echo "ok: resumes from cursor without re-sending old logins"

echo '{"chat_id": "42"}' > /etc/login-notifier/config.json
systemctl restart login-notifier || true
wait_for '[ "$(systemctl is-active login-notifier)" = failed ]' "service not failed on bad config"
journalctl -u login-notifier --no-pager | grep -q "missing required field 'bot_token'" || fail "no config error message"
sleep 6; [ "$(systemctl is-active login-notifier)" = failed ] || fail "restart-looped on bad config"
echo "ok: missing field stops service with a clear error"

echo '{"bot_token": "1:TEST", "chat_id": "42", "api_base": "http://127.0.0.1:8081"}' > /etc/login-notifier/config.json
rm -rf /opt/login-notifier && cp -a /src /opt/login-notifier
sh /opt/login-notifier/install.sh >/dev/null || fail "install from a clone at /opt/login-notifier"
systemctl restart login-notifier
wait_for '[ "$(systemctl is-active login-notifier)" = active ]' "service not running after in-place install"
n=$(msgs); login root
wait_for '[ "$(msgs)" -eq $((n+1)) ]' "no notification after in-place install"
echo "ok: install.sh works when run from a clone at /opt/login-notifier"

echo "ALL INTEGRATION CHECKS PASSED"
EOF
